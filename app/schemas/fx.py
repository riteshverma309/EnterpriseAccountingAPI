"""
app/schemas/fx.py
Pydantic schemas for FX rates and Revaluation.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class _BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ExchangeRateCreate(BaseModel):
    tenant_id: uuid.UUID
    date: date
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    rate: Decimal = Field(..., gt=0)


class ExchangeRateRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    date: date
    from_currency: str
    to_currency: str
    rate: Decimal
    created_at: datetime


class FxRevaluationRequest(BaseModel):
    tenant_id: uuid.UUID
    target_currency: str = Field(..., min_length=3, max_length=3)
    date: date
    unrealized_gain_loss_account_id: uuid.UUID


class FxRevaluationResultLine(BaseModel):
    account_id: uuid.UUID
    account_code: str
    foreign_balance: Decimal
    old_base_balance: Decimal
    new_base_balance: Decimal
    unrealized_gain_loss: Decimal


class FxRevaluationResponse(BaseModel):
    tenant_id: uuid.UUID
    target_currency: str
    date: date
    exchange_rate: Decimal
    journal_entry_id: Optional[uuid.UUID]
    revalued_accounts: List[FxRevaluationResultLine]
