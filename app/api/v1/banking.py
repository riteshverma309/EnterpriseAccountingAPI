"""
app/api/v1/banking.py
Endpoints for Bank Reconciliation.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.banking import (
    BankStatementCreate,
    BankStatementRead,
    BankReconciliationCreate,
    BankReconciliationRead,
)
from app.services import banking_service
from app.services.ledger_service import TenantNotFoundError, AccountNotFoundError

router = APIRouter(prefix="/banking", tags=["Bank Reconciliation"])


@router.post(
    "/statements",
    response_model=BankStatementRead,
    status_code=status.HTTP_201_CREATED,
    summary="Import a bank statement",
)
def import_bank_statement(
    payload: BankStatementCreate,
    db: Session = Depends(get_db_session),
) -> BankStatementRead:
    try:
        statement = banking_service.import_bank_statement(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return BankStatementRead.model_validate(statement)


@router.get(
    "/statements/tenant/{tenant_id}",
    response_model=List[BankStatementRead],
    summary="List bank statements for a tenant",
)
def list_bank_statements(
    tenant_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
) -> List[BankStatementRead]:
    statements = banking_service.get_bank_statements(db, tenant_id, skip=skip, limit=limit)
    return [BankStatementRead.model_validate(s) for s in statements]


@router.post(
    "/reconcile",
    response_model=BankReconciliationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Reconcile a bank statement line with a journal entry line",
)
def reconcile_line(
    payload: BankReconciliationCreate,
    db: Session = Depends(get_db_session),
) -> BankReconciliationRead:
    try:
        recon = banking_service.reconcile_line(db, payload)
    except banking_service.ReconciliationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return BankReconciliationRead.model_validate(recon)
