"""
app/schemas/periods.py
Pydantic schemas for Fiscal Periods.
"""
import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FiscalPeriodCreate(BaseModel):
    tenant_id: uuid.UUID
    name: str = Field(..., max_length=50, examples=["2026-M01"])
    start_date: date
    end_date: date
    is_closed: bool = False


class FiscalPeriodRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_closed: bool


class FiscalPeriodUpdate(BaseModel):
    is_closed: bool
