"""
app/schemas/invoicing.py
Pydantic schemas for Parties and Invoices.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ── Party ─────────────────────────────────────────────────────────────────────

class PartyCreate(BaseModel):
    tenant_id: uuid.UUID
    name: str = Field(..., max_length=255)
    party_type: str = Field(..., examples=["CUSTOMER", "VENDOR", "EMPLOYEE"])
    email: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("party_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = {"CUSTOMER", "VENDOR", "EMPLOYEE"}
        if v.upper() not in valid:
            raise ValueError(f"party_type must be one of {valid}")
        return v.upper()


class PartyRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    party_type: str
    email: Optional[str]
    phone: Optional[str]
    is_active: bool
    created_at: datetime


# ── Invoice Lines ─────────────────────────────────────────────────────────────

class InvoiceLineCreate(BaseModel):
    account_id: uuid.UUID
    description: str = Field(..., max_length=255)
    quantity: Decimal = Field(Decimal("1.0000"), gt=0)
    unit_price: Decimal = Field(..., ge=0)
    tax_amount: Decimal = Field(Decimal("0.0000"), ge=0)


class InvoiceLineRead(_BaseSchema):
    id: uuid.UUID
    invoice_id: uuid.UUID
    account_id: uuid.UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_amount: Decimal
    line_total: Decimal


# ── Invoices ──────────────────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    tenant_id: uuid.UUID
    party_id: uuid.UUID
    invoice_type: str = Field(..., examples=["RECEIVABLE", "PAYABLE"])
    invoice_number: str = Field(..., max_length=100)
    issue_date: date
    due_date: date
    currency: str = Field("USD", min_length=3, max_length=3)
    notes: Optional[str] = None
    lines: List[InvoiceLineCreate] = Field(..., min_length=1)

    @field_validator("invoice_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = {"RECEIVABLE", "PAYABLE"}
        if v.upper() not in valid:
            raise ValueError(f"invoice_type must be one of {valid}")
        return v.upper()


class InvoiceRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    party_id: uuid.UUID
    invoice_type: str
    status: str
    invoice_number: str
    issue_date: date
    due_date: date
    currency: str
    notes: Optional[str]
    journal_entry_id: Optional[uuid.UUID]
    created_at: datetime
    lines: List[InvoiceLineRead]
