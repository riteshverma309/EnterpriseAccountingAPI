"""
app/schemas/ledger.py
Pydantic v2 request/response schemas (Data Transfer Objects).
All UUIDs are serialized as strings for JSON compatibility.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── Shared Config ─────────────────────────────────────────────────────────────

class _BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ── Tenant ────────────────────────────────────────────────────────────────────

class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Acme Corp"])
    base_currency: str = Field("USD", min_length=3, max_length=3, examples=["USD"])
    fiscal_year_start_month: int = Field(1, ge=1, le=12)


class TenantRead(_BaseSchema):
    id: uuid.UUID
    name: str
    base_currency: str
    fiscal_year_start_month: int
    is_active: bool
    created_at: datetime


# ── Chart of Accounts ─────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    tenant_id: uuid.UUID
    parent_id: Optional[uuid.UUID] = None
    code: str = Field(..., min_length=1, max_length=20, examples=["1010"])
    name: str = Field(..., min_length=1, max_length=255, examples=["Cash and Equivalents"])
    account_type: str = Field(..., examples=["ASSET"])
    currency: str = Field("USD", min_length=3, max_length=3)
    description: Optional[str] = None

    @field_validator("account_type")
    @classmethod
    def validate_account_type(cls, v: str) -> str:
        valid = {"ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"}
        if v.upper() not in valid:
            raise ValueError(f"account_type must be one of {valid}")
        return v.upper()


class AccountRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    parent_id: Optional[uuid.UUID]
    code: str
    name: str
    account_type: str
    currency: str
    balance: Decimal
    is_active: bool
    description: Optional[str]
    created_at: datetime


class AccountBalanceRead(_BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    account_type: str
    balance: Decimal
    currency: str


# ── Journal Lines ─────────────────────────────────────────────────────────────

class JournalLineCreate(BaseModel):
    account_id: uuid.UUID
    amount: Decimal = Field(
        ...,
        examples=[150.0],
        description="Positive = Debit, Negative = Credit. Must not be zero.",
    )
    description: Optional[str] = None
    tax_amount: Decimal = Field(Decimal("0.0000"), ge=0)
    exchange_rate: Decimal = Field(Decimal("1.000000"), gt=0)

    @field_validator("amount")
    @classmethod
    def amount_nonzero(cls, v: Decimal) -> Decimal:
        if v == Decimal("0"):
            raise ValueError("Line amount must not be zero.")
        return v


class JournalLineRead(_BaseSchema):
    id: uuid.UUID
    journal_entry_id: uuid.UUID
    account_id: uuid.UUID
    amount: Decimal
    description: Optional[str]
    tax_amount: Optional[Decimal]
    exchange_rate: Optional[Decimal]


# ── Journal Entry ─────────────────────────────────────────────────────────────

class JournalEntryCreate(BaseModel):
    tenant_id: uuid.UUID
    description: str = Field(
        ..., min_length=1, examples=["Q3 Software Subscription Payment"]
    )
    reference_id: Optional[str] = Field(None, max_length=100, examples=["INV-2026-001"])
    currency: str = Field("USD", min_length=3, max_length=3)
    lines: List[JournalLineCreate] = Field(..., min_length=2)
    plugin_metadata: Optional[str] = Field(
        None, description="JSON string for localization plugin data (GST, VAT, etc.)"
    )

    @model_validator(mode="after")
    def validate_double_entry(self) -> "JournalEntryCreate":
        """Core accounting invariant: sum of all line amounts must be exactly zero."""
        total = sum(line.amount for line in self.lines)
        if total != Decimal("0"):
            raise ValueError(
                f"Double-entry violation: debits do not equal credits. "
                f"Net variance = {total}. "
                "Sum of all line amounts (DR positive, CR negative) must equal 0."
            )
        return self


class JournalEntryRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    reference_id: Optional[str]
    description: str
    currency: str
    status: str
    reversal_of_id: Optional[uuid.UUID]
    plugin_metadata: Optional[str]
    posted_at: datetime
    lines: List[JournalLineRead]


class JournalEntryReverseRequest(BaseModel):
    description: str = Field(
        ...,
        examples=["Reversal of INV-2026-001 due to duplicate posting"],
    )
    reference_id: Optional[str] = Field(None, max_length=100)


# ── Reports ───────────────────────────────────────────────────────────────────

class TrialBalanceLine(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    account_type: str
    debit: Decimal
    credit: Decimal


class TrialBalanceReport(BaseModel):
    tenant_id: uuid.UUID
    as_of: datetime
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool
    lines: List[TrialBalanceLine]


# ── Error Response ────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: Optional[str] = None
