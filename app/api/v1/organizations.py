"""
app/api/v1/organizations.py
Organization-level hierarchy endpoints.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.core.auth import ScopeError, validate_scope
from app.schemas.ledger import OrganizationCreate, OrganizationRead
from app.services import ledger_service
from app.services.ledger_service import TenantNotFoundError

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post(
    "/",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a legal organization",
)
def create_organization(
    request: Request,
    payload: OrganizationCreate,
    db: Session = Depends(get_db_session),
) -> OrganizationRead:
    try:
        context = getattr(request.state, "context", {})
        validate_scope(context, tenant_id=str(payload.tenant_id))
        organization = ledger_service.create_organization(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return OrganizationRead.model_validate(organization)


@router.get(
    "/tenant/{tenant_id}",
    response_model=List[OrganizationRead],
    summary="List organizations for a tenant",
)
def list_organizations(
    tenant_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
) -> List[OrganizationRead]:
    organizations = ledger_service.list_organizations(db, tenant_id, skip=skip, limit=limit)
    return [OrganizationRead.model_validate(org) for org in organizations]
