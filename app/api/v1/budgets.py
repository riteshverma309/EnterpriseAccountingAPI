"""
app/api/v1/budgets.py
Endpoints for Budgeting.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.budget import (
    BudgetCreate,
    BudgetRead,
    BudgetVsActualReport,
)
from app.services import budget_service
from app.services.ledger_service import TenantNotFoundError, AccountNotFoundError

router = APIRouter(prefix="/budgets", tags=["Budgets"])


@router.post(
    "/",
    response_model=BudgetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new budget",
)
def create_budget(
    payload: BudgetCreate,
    db: Session = Depends(get_db_session),
) -> BudgetRead:
    try:
        budget = budget_service.create_budget(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return BudgetRead.model_validate(budget)


@router.get(
    "/{budget_id}/vs-actual",
    response_model=BudgetVsActualReport,
    summary="Get Budget vs Actual report",
)
def get_budget_vs_actual(
    budget_id: uuid.UUID,
    db: Session = Depends(get_db_session),
) -> BudgetVsActualReport:
    try:
        report = budget_service.get_budget_vs_actual(db, budget_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return BudgetVsActualReport.model_validate(report)
