"""
app/schemas/assets.py
Pydantic schemas for Fixed Assets.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.assets import DepreciationMethod


class _BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FixedAssetCreate(BaseModel):
    tenant_id: uuid.UUID
    name: str = Field(..., max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    purchase_date: date
    purchase_price: Decimal = Field(..., gt=0)
    salvage_value: Decimal = Field(Decimal("0.0000"), ge=0)
    useful_life_months: int = Field(..., gt=0)
    depreciation_method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE
    
    asset_account_id: uuid.UUID
    accumulated_depreciation_account_id: uuid.UUID
    depreciation_expense_account_id: uuid.UUID


class DepreciationScheduleRead(_BaseSchema):
    id: uuid.UUID
    scheduled_date: date
    depreciation_amount: Decimal
    journal_entry_id: Optional[uuid.UUID]


class FixedAssetRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: Optional[str]
    purchase_date: date
    purchase_price: Decimal
    salvage_value: Decimal
    useful_life_months: int
    depreciation_method: DepreciationMethod
    asset_account_id: uuid.UUID
    accumulated_depreciation_account_id: uuid.UUID
    depreciation_expense_account_id: uuid.UUID
    created_at: datetime
    schedules: List[DepreciationScheduleRead] = []


class DepreciationRunRequest(BaseModel):
    tenant_id: uuid.UUID
    date_upto: date


class DepreciationRunResultLine(BaseModel):
    asset_id: uuid.UUID
    asset_name: str
    depreciation_amount: Decimal
    journal_entry_id: uuid.UUID


class DepreciationRunResponse(BaseModel):
    tenant_id: uuid.UUID
    date_upto: date
    processed_assets_count: int
    total_depreciation_posted: Decimal
    details: List[DepreciationRunResultLine]
