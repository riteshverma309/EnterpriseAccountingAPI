"""
app/api/v1/assets.py
Endpoints for Fixed Asset Management and Depreciation.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.core.auth import ScopeError, validate_scope
from app.schemas.assets import (
    FixedAssetCreate,
    FixedAssetRead,
    DepreciationRunRequest,
    DepreciationRunResponse,
)
from app.services import assets_service
from app.services.ledger_service import TenantNotFoundError, AccountNotFoundError, ClosedPeriodError

router = APIRouter(prefix="/assets", tags=["Fixed Assets"])


@router.post(
    "/",
    response_model=FixedAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new Fixed Asset",
)
def create_fixed_asset(
    request: Request,
    payload: FixedAssetCreate,
    db: Session = Depends(get_db_session),
) -> FixedAssetRead:
    try:
        context = getattr(request.state, "context", {})
        validate_scope(context, tenant_id=str(payload.tenant_id))
        asset = assets_service.create_fixed_asset(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return FixedAssetRead.model_validate(asset)


@router.get(
    "/tenant/{tenant_id}",
    response_model=List[FixedAssetRead],
    summary="List fixed assets for a tenant",
)
def list_fixed_assets(
    tenant_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
) -> List[FixedAssetRead]:
    assets = assets_service.list_fixed_assets(db, tenant_id, skip=skip, limit=limit)
    return [FixedAssetRead.model_validate(a) for a in assets]


@router.post(
    "/depreciate",
    response_model=DepreciationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run depreciation for all pending schedules up to a specific date",
)
def run_depreciation(
    request: Request,
    payload: DepreciationRunRequest,
    db: Session = Depends(get_db_session),
) -> DepreciationRunResponse:
    try:
        context = getattr(request.state, "context", {})
        validate_scope(context, tenant_id=str(payload.tenant_id))
        result = assets_service.run_depreciation(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ClosedPeriodError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return DepreciationRunResponse.model_validate(result)
