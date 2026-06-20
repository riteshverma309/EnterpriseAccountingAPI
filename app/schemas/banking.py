"""
app/schemas/banking.py
Pydantic schemas for Bank Reconciliation.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class _BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BankStatementLineCreate(BaseModel):
    date: date
    description: str = Field(..., max_length=255)
    amount: Decimal


class BankStatementLineRead(_BaseSchema):
    id: uuid.UUID
    statement_id: uuid.UUID
    date: date
    description: str
    amount: Decimal
    is_reconciled: bool


class BankStatementCreate(BaseModel):
    tenant_id: uuid.UUID
    account_id: uuid.UUID
    statement_date: date
    starting_balance: Decimal = Field(Decimal("0.0000"))
    ending_balance: Decimal
    lines: List[BankStatementLineCreate]


class BankStatementRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    account_id: uuid.UUID
    statement_date: date
    starting_balance: Decimal
    ending_balance: Decimal
    is_reconciled: bool
    created_at: datetime
    lines: List[BankStatementLineRead]


class BankReconciliationCreate(BaseModel):
    tenant_id: uuid.UUID
    bank_statement_line_id: uuid.UUID
    journal_line_id: uuid.UUID


class BankReconciliationRead(_BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    bank_statement_line_id: uuid.UUID
    journal_line_id: uuid.UUID
    reconciled_at: datetime
