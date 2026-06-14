"""
app/api/v1/tenants.py
Tenant management endpoints.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.ledger import TenantCreate, TenantRead
from app.services import ledger_service
from app.services.ledger_service import TenantNotFoundError

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post(
    "/",
    response_model=TenantRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tenant",
)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db_session),
) -> TenantRead:
    """
    Create a new accounting tenant (legal entity / business unit).
    Each tenant has an isolated Chart of Accounts and ledger.
    """
    tenant = ledger_service.create_tenant(db, payload)
    return TenantRead.model_validate(tenant)


@router.get(
    "/",
    response_model=List[TenantRead],
    summary="List all tenants",
)
def list_tenants(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
) -> List[TenantRead]:
    tenants = ledger_service.list_tenants(db, skip=skip, limit=limit)
    return [TenantRead.model_validate(t) for t in tenants]


@router.get(
    "/{tenant_id}",
    response_model=TenantRead,
    summary="Get tenant by ID",
)
def get_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db_session),
) -> TenantRead:
    try:
        tenant = ledger_service.get_tenant(db, tenant_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return TenantRead.model_validate(tenant)
