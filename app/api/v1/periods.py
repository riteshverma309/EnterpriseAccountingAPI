"""
app/api/v1/periods.py
Endpoints for Fiscal Periods.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.periods import FiscalPeriod
from app.models.ledger import Tenant
from app.schemas.periods import FiscalPeriodCreate, FiscalPeriodRead, FiscalPeriodUpdate

router = APIRouter(prefix="/periods", tags=["Fiscal Periods"])


@router.post(
    "/",
    response_model=FiscalPeriodRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new fiscal period",
)
def create_period(
    payload: FiscalPeriodCreate,
    db: Session = Depends(get_db_session),
) -> FiscalPeriodRead:
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        
    period = FiscalPeriod(
        tenant_id=payload.tenant_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_closed=payload.is_closed
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return FiscalPeriodRead.model_validate(period)


@router.put(
    "/{period_id}",
    response_model=FiscalPeriodRead,
    summary="Update a fiscal period (Close/Open)",
)
def update_period(
    period_id: uuid.UUID,
    payload: FiscalPeriodUpdate,
    db: Session = Depends(get_db_session),
) -> FiscalPeriodRead:
    period = db.get(FiscalPeriod, period_id)
    if not period:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found")
        
    period.is_closed = payload.is_closed
    db.commit()
    db.refresh(period)
    return FiscalPeriodRead.model_validate(period)


@router.get(
    "/tenant/{tenant_id}",
    response_model=List[FiscalPeriodRead],
    summary="List all fiscal periods for a tenant",
)
def list_periods(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db_session),
) -> List[FiscalPeriodRead]:
    periods = db.execute(
        select(FiscalPeriod).where(FiscalPeriod.tenant_id == tenant_id).order_by(FiscalPeriod.start_date.desc())
    ).scalars().all()
    return [FiscalPeriodRead.model_validate(p) for p in periods]
