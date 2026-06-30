"""
app/api/v1/parties.py
Endpoints for Contact Management (Parties).
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.core.auth import ScopeError, validate_scope
from app.schemas.invoicing import PartyCreate, PartyRead
from app.services import invoicing_service
from app.services.ledger_service import TenantNotFoundError

router = APIRouter(prefix="/parties", tags=["Parties (Customers/Vendors)"])


@router.post(
    "/",
    response_model=PartyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new party",
)
def create_party(
    request: Request,
    payload: PartyCreate,
    db: Session = Depends(get_db_session),
) -> PartyRead:
    try:
        context = getattr(request.state, "context", {})
        validate_scope(context, tenant_id=str(payload.tenant_id))
        party = invoicing_service.create_party(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return PartyRead.model_validate(party)


@router.get(
    "/tenant/{tenant_id}",
    response_model=List[PartyRead],
    summary="List all parties for a tenant",
)
def list_parties(
    tenant_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
) -> List[PartyRead]:
    parties = invoicing_service.list_parties(db, tenant_id, skip=skip, limit=limit)
    return [PartyRead.model_validate(p) for p in parties]
