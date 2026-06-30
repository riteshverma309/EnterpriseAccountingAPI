"""
app/api/v1/fx.py
Endpoints for Multi-Currency FX Revaluation.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.core.auth import ScopeError, validate_scope
from app.schemas.fx import (
    ExchangeRateCreate,
    ExchangeRateRead,
    FxRevaluationRequest,
    FxRevaluationResponse,
)
from app.services import fx_service
from app.services.ledger_service import TenantNotFoundError, AccountNotFoundError, ClosedPeriodError

router = APIRouter(prefix="/fx", tags=["Multi-Currency FX"])


@router.post(
    "/rates",
    response_model=ExchangeRateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Set an exchange rate for a date",
)
def set_exchange_rate(
    request: Request,
    payload: ExchangeRateCreate,
    db: Session = Depends(get_db_session),
) -> ExchangeRateRead:
    try:
        context = getattr(request.state, "context", {})
        validate_scope(context, tenant_id=str(payload.tenant_id))
        rate = fx_service.set_exchange_rate(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return ExchangeRateRead.model_validate(rate)


@router.post(
    "/revalue",
    response_model=FxRevaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Month-End FX Revaluation",
)
def run_fx_revaluation(
    request: Request,
    payload: FxRevaluationRequest,
    db: Session = Depends(get_db_session),
) -> FxRevaluationResponse:
    try:
        context = getattr(request.state, "context", {})
        validate_scope(context, tenant_id=str(payload.tenant_id))
        result = fx_service.run_fx_revaluation(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except fx_service.ExchangeRateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ClosedPeriodError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return FxRevaluationResponse.model_validate(result)
