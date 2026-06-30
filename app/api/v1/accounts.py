"""
app/api/v1/accounts.py
Chart of Accounts (CoA) management endpoints.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_editor_role
from app.core.auth import ScopeError, validate_scope
from app.schemas.ledger import AccountCreate, AccountRead
from app.services import ledger_service
from app.services.ledger_service import (
    AccountCodeConflictError,
    AccountNotFoundError,
    TenantNotFoundError,
)

router = APIRouter(prefix="/accounts", tags=["Chart of Accounts"])


@router.post(
    "/",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Chart of Accounts entry",
)
def create_account(
    request: Request,
    payload: AccountCreate,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_editor_role),
) -> AccountRead:
    """
    Create a new account in the Chart of Accounts.
    Supports hierarchical accounts via `parent_id`.
    Account codes must be unique within a tenant.
    """
    try:
        context = getattr(request.state, "context", {})
        validate_scope(context, tenant_id=str(payload.tenant_id))
        account = ledger_service.create_account(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AccountCodeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return AccountRead.model_validate(account)


@router.get(
    "/tenant/{tenant_id}",
    response_model=List[AccountRead],
    summary="List all accounts for a tenant",
)
def list_accounts(
    tenant_id: uuid.UUID,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db_session),
) -> List[AccountRead]:
    """Returns all active and inactive accounts ordered by account code."""
    accounts = ledger_service.list_accounts(db, tenant_id, skip=skip, limit=limit)
    return [AccountRead.model_validate(a) for a in accounts]


@router.get(
    "/{account_id}",
    response_model=AccountRead,
    summary="Get account by ID",
)
def get_account(
    account_id: uuid.UUID,
    db: Session = Depends(get_db_session),
) -> AccountRead:
    try:
        account = ledger_service.get_account(db, account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return AccountRead.model_validate(account)
