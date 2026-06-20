"""
app/services/banking_service.py
Service layer for Bank Reconciliation.
"""
import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.banking import BankStatement, BankStatementLine, BankReconciliation
from app.models.ledger import Tenant, Account, JournalLine
from app.schemas.banking import BankStatementCreate, BankReconciliationCreate
from app.services.ledger_service import TenantNotFoundError, AccountNotFoundError


class BankStatementNotFoundError(Exception):
    def __init__(self, statement_id: str):
        super().__init__(f"BankStatement {statement_id!r} not found.")


class ReconciliationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


def import_bank_statement(db: Session, payload: BankStatementCreate) -> BankStatement:
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    account = db.get(Account, payload.account_id)
    if not account or account.tenant_id != payload.tenant_id:
        raise AccountNotFoundError(str(payload.account_id))

    statement = BankStatement(
        tenant_id=payload.tenant_id,
        account_id=payload.account_id,
        statement_date=payload.statement_date,
        starting_balance=payload.starting_balance,
        ending_balance=payload.ending_balance,
    )
    db.add(statement)
    db.flush()

    for line_payload in payload.lines:
        line = BankStatementLine(
            statement_id=statement.id,
            date=line_payload.date,
            description=line_payload.description,
            amount=line_payload.amount,
        )
        db.add(line)

    db.commit()
    db.refresh(statement)
    return statement


def get_bank_statements(db: Session, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[BankStatement]:
    return db.execute(
        select(BankStatement).where(BankStatement.tenant_id == tenant_id).order_by(BankStatement.statement_date.desc()).offset(skip).limit(limit)
    ).scalars().unique().all()


def reconcile_line(db: Session, payload: BankReconciliationCreate) -> BankReconciliation:
    bank_line = db.get(BankStatementLine, payload.bank_statement_line_id)
    if not bank_line:
        raise ReconciliationError("Bank statement line not found.")
        
    if bank_line.is_reconciled:
        raise ReconciliationError("Bank statement line is already reconciled.")
        
    journal_line = db.get(JournalLine, payload.journal_line_id)
    if not journal_line:
        raise ReconciliationError("Journal line not found.")

    # In a real app, we might also verify that the bank line amount matches the journal line amount.
    # We will enforce this strictly.
    if bank_line.amount != journal_line.amount:
        raise ReconciliationError(f"Amount mismatch: Bank Line = {bank_line.amount}, Journal Line = {journal_line.amount}")
        
    # Check if journal line is already reconciled (for simplicity we check existence in BankReconciliation)
    existing_recon = db.execute(
        select(BankReconciliation).where(BankReconciliation.journal_line_id == payload.journal_line_id)
    ).scalar_one_or_none()
    
    if existing_recon:
        raise ReconciliationError("Journal line is already reconciled to another bank statement line.")

    recon = BankReconciliation(
        tenant_id=payload.tenant_id,
        bank_statement_line_id=payload.bank_statement_line_id,
        journal_line_id=payload.journal_line_id,
    )
    db.add(recon)
    
    # Mark the bank line as reconciled
    bank_line.is_reconciled = True
    
    # Optionally, check if the whole statement is reconciled
    statement = bank_line.statement
    unreconciled_lines = [l for l in statement.lines if not l.is_reconciled and l.id != bank_line.id]
    if len(unreconciled_lines) == 0:
        statement.is_reconciled = True

    db.commit()
    db.refresh(recon)
    return recon
