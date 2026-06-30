"""
app/api/v1/journal_entries.py
Journal entry posting, retrieval, and reversal endpoints.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_session
from app.core.auth import ScopeError, validate_scope
from app.schemas.ledger import JournalEntryCreate, JournalEntryRead, JournalEntryReverseRequest
from app.services import ledger_service
from app.services.ledger_service import (
    AccountNotFoundError,
    EntryAlreadyReversedError,
    InactiveAccountError,
    JournalEntryNotFoundError,
    TenantNotFoundError,
    UnbalancedLedgerError,
    ClosedPeriodError,
)

router = APIRouter(prefix="/journal-entries", tags=["Journal Entries"])


@router.post(
    "/",
    response_model=JournalEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Post a double-entry journal entry",
)
def post_journal_entry(
    request: Request,
    payload: JournalEntryCreate,
    plugin_id: Optional[str] = Query(
        None,
        description="Localization plugin ID (e.g. 'us_gaap', 'eu_ifrs', 'in_gst')",
        examples=["in_gst"],
    ),
    db: Session = Depends(get_db_session),
    current_user: str = Depends(get_current_user),
) -> JournalEntryRead:
    """
    Post a multi-line double-entry journal entry to the ledger.

    **Accounting rules enforced:**
    - Sum of all line amounts must equal exactly zero (DR = CR).
    - All accounts must exist, be active, and belong to the stated tenant.
    - Account balances are updated atomically with row-level locking (FOR UPDATE).
    - Entries are immutable once posted — use the `/reverse` endpoint to correct.

    **Optional plugin:** Pass `?plugin_id=in_gst` (or `us_gaap`, `eu_ifrs`) to apply
    localization hooks (tax computation, statutory metadata enrichment).
    """
    try:
        context = getattr(request.state, "context", {})
        validate_scope(context, tenant_id=str(payload.tenant_id))
        entry = ledger_service.post_journal_entry(db, payload, plugin_id=plugin_id)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InactiveAccountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except UnbalancedLedgerError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ClosedPeriodError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return JournalEntryRead.model_validate(entry)


@router.get(
    "/tenant/{tenant_id}",
    response_model=List[JournalEntryRead],
    summary="List journal entries for a tenant",
)
def list_journal_entries(
    tenant_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session),
) -> List[JournalEntryRead]:
    """Returns all journal entries for a tenant, newest first."""
    entries = ledger_service.list_journal_entries(db, tenant_id, skip=skip, limit=limit)
    return [JournalEntryRead.model_validate(e) for e in entries]


@router.get(
    "/{entry_id}",
    response_model=JournalEntryRead,
    summary="Get a journal entry by ID",
)
def get_journal_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db_session),
) -> JournalEntryRead:
    try:
        entry = ledger_service.get_journal_entry(db, entry_id)
    except JournalEntryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return JournalEntryRead.model_validate(entry)


@router.post(
    "/{entry_id}/reverse",
    response_model=JournalEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Reverse an existing journal entry",
)
def reverse_journal_entry(
    entry_id: uuid.UUID,
    payload: JournalEntryReverseRequest,
    db: Session = Depends(get_db_session),
) -> JournalEntryRead:
    """
    Create a reversal entry that exactly negates the original entry.

    **Immutability guarantee:**
    - The original entry is marked `REVERSED` but never deleted or modified.
    - A new POSTED entry with negated line amounts is created and returned.
    - Attempting to reverse an already-reversed entry returns HTTP 409.
    """
    try:
        reversal = ledger_service.reverse_journal_entry(
            db,
            entry_id=entry_id,
            description=payload.description,
            reference_id=payload.reference_id,
        )
    except JournalEntryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except EntryAlreadyReversedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return JournalEntryRead.model_validate(reversal)
