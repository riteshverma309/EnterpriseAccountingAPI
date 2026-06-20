"""
app/schemas/budget.py
Pydantic schemas for Budgeting.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class _BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BudgetLineCreate(BaseModel):
    account_id: uuid.UUID
    amount: Decimal


class BudgetLineRead(_BaseSchema):
    id: uuid.UUID
    budget_id: uuid.UUID
    account_id: uuid.UUID
    amount: Decimal


class BudgetCreate(BaseModel):
    tenant_id: uuid.UUID
    name: str = Field(..., max_length=255)
    fiscal_year: int = Field(..., gt=1900)
    lines: List[BudgetLineCreate]


class BudgetRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    fiscal_year: int
    created_at: datetime
    lines: List[BudgetLineRead]


class BudgetVsActualLine(BaseModel):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    budgeted_amount: Decimal
    actual_amount: Decimal
    variance: Decimal
    variance_percentage: Decimal


class BudgetVsActualReport(BaseModel):
    tenant_id: uuid.UUID
    budget_id: uuid.UUID
    budget_name: str
    fiscal_year: int
    lines: List[BudgetVsActualLine]
