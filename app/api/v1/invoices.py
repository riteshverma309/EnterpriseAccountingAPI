"""
app/api/v1/invoices.py
Endpoints for Invoices and Bills.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.core.auth import ScopeError, validate_scope
from app.schemas.invoicing import InvoiceCreate, InvoiceRead
from app.services import invoicing_service
from app.services.invoicing_service import (
    PartyNotFoundError,
    InvoiceNotFoundError,
    InvoiceAlreadyPostedError,
)
from app.services.ledger_service import TenantNotFoundError, UnbalancedLedgerError, ClosedPeriodError

router = APIRouter(prefix="/invoices", tags=["Invoices (AR/AP)"])


@router.post(
    "/",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new invoice or bill",
)
def create_invoice(
    request: Request,
    payload: InvoiceCreate,
    db: Session = Depends(get_db_session),
) -> InvoiceRead:
    try:
        context = getattr(request.state, "context", {})
        validate_scope(context, tenant_id=str(payload.tenant_id))
        invoice = invoicing_service.create_invoice(db, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PartyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return InvoiceRead.model_validate(invoice)


@router.post(
    "/{invoice_id}/post",
    response_model=InvoiceRead,
    summary="Post an invoice to the general ledger",
)
def post_invoice(
    request: Request,
    invoice_id: uuid.UUID,
    ar_ap_account_id: uuid.UUID,
    db: Session = Depends(get_db_session),
) -> InvoiceRead:
    """
    Posts the invoice to the ledger by creating a balanced Journal Entry.
    For an Invoice (AR): Debits the provided ar_ap_account_id, Credits line items.
    For a Bill (AP): Credits the provided ar_ap_account_id, Debits line items.
    """
    try:
        context = getattr(request.state, "context", {})
        invoice = invoicing_service.post_invoice(db, invoice_id, ar_ap_account_id)
        validate_scope(context, tenant_id=str(invoice.tenant_id))
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvoiceAlreadyPostedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except UnbalancedLedgerError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ClosedPeriodError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return InvoiceRead.model_validate(invoice)


@router.get(
    "/tenant/{tenant_id}",
    response_model=List[InvoiceRead],
    summary="List all invoices for a tenant",
)
def list_invoices(
    tenant_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
) -> List[InvoiceRead]:
    invoices = invoicing_service.list_invoices(db, tenant_id, skip=skip, limit=limit)
    return [InvoiceRead.model_validate(i) for i in invoices]
