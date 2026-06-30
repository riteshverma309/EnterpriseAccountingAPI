"""
app/api/v1/branches.py
Branch or sub-business endpoints.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.core.auth import ScopeError, validate_scope
from app.models.ledger import Organization
from app.schemas.ledger import BranchCreate, BranchRead
from app.services import ledger_service
from app.services.ledger_service import BranchCodeConflictError, OrganizationNotFoundError

router = APIRouter(prefix="/branches", tags=["Branches"])


@router.post(
    "/",
    response_model=BranchRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a branch under an organization",
)
def create_branch(
    request: Request,
    payload: BranchCreate,
    db: Session = Depends(get_db_session),
) -> BranchRead:
    try:
        context = getattr(request.state, "context", {})
        organization = db.get(Organization, payload.organization_id)
        if not organization:
            raise OrganizationNotFoundError(str(payload.organization_id))
        validate_scope(context, tenant_id=str(organization.tenant_id))
        branch = ledger_service.create_branch(db, payload)
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except BranchCodeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return BranchRead.model_validate(branch)


@router.get(
    "/organization/{organization_id}",
    response_model=List[BranchRead],
    summary="List branches for an organization",
)
def list_branches(
    organization_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
) -> List[BranchRead]:
    branches = ledger_service.list_branches(db, organization_id, skip=skip, limit=limit)
    return [BranchRead.model_validate(branch) for branch in branches]
