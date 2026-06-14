"""
app/api/v1/reports.py
Financial reporting endpoints.
"""
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.ledger import TrialBalanceReport
from app.services import reporting_service

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get(
    "/trial-balance/{tenant_id}",
    response_model=TrialBalanceReport,
    summary="Generate Trial Balance",
)
def trial_balance(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db_session),
) -> TrialBalanceReport:
    """
    Generate a Trial Balance for the specified tenant.
    Returns all account balances, total debits, total credits,
    and a boolean `is_balanced` flag.
    A balanced ledger has total_debits == total_credits.
    """
    return reporting_service.generate_trial_balance(db, tenant_id)


@router.get(
    "/balance-sheet/{tenant_id}",
    summary="Generate Balance Sheet",
    response_model=Dict[str, Any],
)
def balance_sheet(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Generate a classified Balance Sheet.
    Validates the fundamental accounting equation:
    **Assets = Liabilities + Equity + Net Income**.
    """
    return reporting_service.generate_balance_sheet(db, tenant_id)


@router.get(
    "/statutory/{tenant_id}/{plugin_id}",
    summary="Generate Statutory Report via Plugin",
    response_model=Dict[str, Any],
)
def statutory_report(
    tenant_id: uuid.UUID,
    plugin_id: str,
    period_start: str,
    period_end: str,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    Generate a jurisdiction-specific statutory report.
    Delegates to the registered localization plugin.

    - `plugin_id`: `us_gaap`, `eu_ifrs`, or `in_gst`
    - `period_start` / `period_end`: ISO 8601 date strings (e.g. `2026-01-01`)
    """
    try:
        return reporting_service.generate_statutory_report(
            db, tenant_id, plugin_id, period_start, period_end
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
