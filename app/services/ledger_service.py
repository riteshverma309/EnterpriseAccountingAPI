"""
app/services/ledger_service.py
Core accounting service layer.

Responsibilities:
- Tenant and Account CRUD with validation.
- Journal entry posting with strict double-entry enforcement.
- PostgreSQL row-level locking (SELECT FOR UPDATE) on Account.balance
  to prevent race conditions during concurrent transaction processing.
- Immutable correction via reversal entries.
- Plugin middleware hook invocation.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ledger import Account, AccountType, EntryStatus, JournalEntry, JournalLine, Tenant
from app.plugins.base import PluginContext, PluginRegistry
from app.schemas.ledger import (
    AccountCreate,
    JournalEntryCreate,
    TenantCreate,
)


# ── Custom Exceptions ─────────────────────────────────────────────────────────

class UnbalancedLedgerError(Exception):
    """Raised when the sum of journal line amounts ≠ 0."""

    def __init__(self, variance: Decimal):
        self.variance = variance
        super().__init__(
            f"Double-entry violation: net variance = {variance}. "
            "Sum of all line amounts (DR positive, CR negative) must equal 0."
        )


class TenantNotFoundError(Exception):
    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant {tenant_id!r} not found.")


class AccountNotFoundError(Exception):
    def __init__(self, account_id: str):
        super().__init__(f"Account {account_id!r} not found.")


class AccountCodeConflictError(Exception):
    def __init__(self, code: str, tenant_id: str):
        super().__init__(
            f"Account code {code!r} already exists for tenant {tenant_id!r}."
        )


class JournalEntryNotFoundError(Exception):
    def __init__(self, entry_id: str):
        super().__init__(f"JournalEntry {entry_id!r} not found.")


class EntryAlreadyReversedError(Exception):
    def __init__(self, entry_id: str):
        super().__init__(f"JournalEntry {entry_id!r} has already been reversed.")


class InactiveAccountError(Exception):
    def __init__(self, account_id: str):
        super().__init__(
            f"Account {account_id!r} is inactive and cannot receive new postings."
        )


# ── Tenant Service ────────────────────────────────────────────────────────────

def create_tenant(db: Session, payload: TenantCreate) -> Tenant:
    """Create a new tenant (accounting entity)."""
    tenant = Tenant(
        name=payload.name,
        base_currency=payload.base_currency.upper(),
        fiscal_year_start_month=payload.fiscal_year_start_month,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def get_tenant(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(tenant_id))
    return tenant


def list_tenants(db: Session, skip: int = 0, limit: int = 100) -> List[Tenant]:
    return db.execute(select(Tenant).offset(skip).limit(limit)).scalars().all()


# ── Account Service ───────────────────────────────────────────────────────────

def create_account(db: Session, payload: AccountCreate) -> Account:
    """
    Create a new Chart of Accounts entry for a tenant.
    Validates tenant existence and code uniqueness within the tenant.
    """
    # Validate tenant
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    # Validate parent account (if provided)
    if payload.parent_id:
        parent = db.get(Account, payload.parent_id)
        if not parent or parent.tenant_id != payload.tenant_id:
            raise AccountNotFoundError(str(payload.parent_id))

    # Check code uniqueness within tenant
    existing = db.execute(
        select(Account).where(
            Account.tenant_id == payload.tenant_id,
            Account.code == payload.code,
        )
    ).scalar_one_or_none()
    if existing:
        raise AccountCodeConflictError(payload.code, str(payload.tenant_id))

    account = Account(
        tenant_id=payload.tenant_id,
        parent_id=payload.parent_id,
        code=payload.code,
        name=payload.name,
        account_type=AccountType(payload.account_type),
        currency=payload.currency.upper(),
        description=payload.description,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def get_account(db: Session, account_id: uuid.UUID) -> Account:
    account = db.get(Account, account_id)
    if not account:
        raise AccountNotFoundError(str(account_id))
    return account


def list_accounts(
    db: Session,
    tenant_id: uuid.UUID,
    skip: int = 0,
    limit: int = 200,
) -> List[Account]:
    return (
        db.execute(
            select(Account)
            .where(Account.tenant_id == tenant_id)
            .order_by(Account.code)
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )


# ── Journal Entry Service ─────────────────────────────────────────────────────

def post_journal_entry(
    db: Session,
    payload: JournalEntryCreate,
    plugin_id: Optional[str] = None,
) -> JournalEntry:
    """
    Core double-entry posting engine.

    Algorithm:
    1. Validate tenant.
    2. Invoke localization plugin pre-post hook (if plugin_id provided).
    3. Validate debit == credit (sum of amounts == 0). [Redundant with schema
       validator, but enforced here as a DB-layer safety net.]
    4. Lock all affected account rows with SELECT FOR UPDATE (row-level lock)
       to prevent concurrent balance corruption.
    5. Validate all accounts are active and belong to the tenant.
    6. Update account balances atomically within the same transaction.
    7. Persist JournalEntry + JournalLine records.
    8. Invoke plugin post-post hook.
    9. Commit and return the posted entry.
    """
    # Step 1: Validate tenant
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    # Step 2: Build plugin context and invoke pre-post hook
    plugin_metadata: dict = {}
    if payload.plugin_metadata:
        try:
            plugin_metadata = json.loads(payload.plugin_metadata)
        except json.JSONDecodeError:
            plugin_metadata = {}

    plugin = PluginRegistry.get(plugin_id) if plugin_id else None
    context = PluginContext(
        tenant_id=str(payload.tenant_id),
        base_currency=tenant.base_currency,
        entry_currency=payload.currency,
        description=payload.description,
        reference_id=payload.reference_id,
        lines=[
            {
                "account_id": str(line.account_id),
                "amount": str(line.amount),
                "description": line.description,
            }
            for line in payload.lines
        ],
        plugin_metadata=plugin_metadata,
    )
    if plugin:
        context = plugin.on_pre_post(context)

    # Step 3: Enforce double-entry invariant
    total = sum(line.amount for line in payload.lines)
    if total != Decimal("0"):
        raise UnbalancedLedgerError(total)

    # Step 4: Collect unique account IDs and acquire row-level locks
    account_ids = list({line.account_id for line in payload.lines})
    locked_accounts: dict[uuid.UUID, Account] = {}
    for acc_id in account_ids:
        # SELECT ... FOR UPDATE — blocks concurrent writes to this account row
        stmt = (
            select(Account)
            .where(Account.id == acc_id)
            .with_for_update()
        )
        account = db.execute(stmt).scalar_one_or_none()
        if not account:
            raise AccountNotFoundError(str(acc_id))

        # Step 5: Validate account is active and belongs to this tenant
        if account.tenant_id != payload.tenant_id:
            raise AccountNotFoundError(str(acc_id))  # Security: hide cross-tenant info
        if not account.is_active:
            raise InactiveAccountError(str(acc_id))

        locked_accounts[acc_id] = account

    # Step 6: Update account balances (within the locked transaction)
    for line in payload.lines:
        locked_accounts[line.account_id].balance += line.amount

    # Step 7: Persist JournalEntry and JournalLine records
    plugin_meta_str = (
        json.dumps(context.plugin_metadata, default=str)
        if context.plugin_metadata
        else None
    )
    entry = JournalEntry(
        tenant_id=payload.tenant_id,
        reference_id=payload.reference_id,
        description=payload.description,
        currency=payload.currency.upper(),
        status=EntryStatus.POSTED,
        plugin_metadata=plugin_meta_str,
    )
    db.add(entry)
    db.flush()  # Get entry.id without committing

    for line in payload.lines:
        journal_line = JournalLine(
            journal_entry_id=entry.id,
            account_id=line.account_id,
            amount=line.amount,
            description=line.description,
            tax_amount=line.tax_amount,
            exchange_rate=line.exchange_rate,
        )
        db.add(journal_line)

    db.commit()
    db.refresh(entry)

    # Step 8: Post-post plugin hook (for side-effects: events, notifications)
    if plugin:
        plugin.on_post_post(context, str(entry.id))

    return entry


def reverse_journal_entry(
    db: Session,
    entry_id: uuid.UUID,
    description: str,
    reference_id: Optional[str] = None,
    plugin_id: Optional[str] = None,
) -> JournalEntry:
    """
    Create a reversal journal entry that exactly offsets the original entry.
    The original entry is marked as REVERSED.
    Immutability is preserved — the original entry is NEVER modified or deleted.
    """
    # Fetch original entry
    original = db.get(JournalEntry, entry_id)
    if not original:
        raise JournalEntryNotFoundError(str(entry_id))

    # Check if already reversed
    if original.status == EntryStatus.REVERSED:
        raise EntryAlreadyReversedError(str(entry_id))

    # Build reversal payload with negated amounts
    reversal_lines = [
        type(
            "LineProxy",
            (),
            {
                "account_id": line.account_id,
                "amount": -line.amount,        # Negate: DR ↔ CR
                "description": f"Reversal: {line.description or ''}",
                "tax_amount": Decimal("0"),
                "exchange_rate": line.exchange_rate,
            },
        )()
        for line in original.lines
    ]

    # Acquire locks and update balances for reversal
    for rev_line in reversal_lines:
        stmt = (
            select(Account)
            .where(Account.id == rev_line.account_id)
            .with_for_update()
        )
        account = db.execute(stmt).scalar_one_or_none()
        if account:
            account.balance += rev_line.amount

    # Create reversal entry
    reversal = JournalEntry(
        tenant_id=original.tenant_id,
        reference_id=reference_id or f"REV-{original.reference_id or str(entry_id)[:8]}",
        description=description,
        currency=original.currency,
        status=EntryStatus.POSTED,
        reversal_of_id=original.id,
    )
    db.add(reversal)
    db.flush()

    for rev_line in reversal_lines:
        db.add(
            JournalLine(
                journal_entry_id=reversal.id,
                account_id=rev_line.account_id,
                amount=rev_line.amount,
                description=rev_line.description,
                tax_amount=rev_line.tax_amount,
                exchange_rate=rev_line.exchange_rate,
            )
        )

    # Mark original as reversed
    original.status = EntryStatus.REVERSED

    db.commit()
    db.refresh(reversal)
    return reversal


def get_journal_entry(db: Session, entry_id: uuid.UUID) -> JournalEntry:
    entry = db.get(JournalEntry, entry_id)
    if not entry:
        raise JournalEntryNotFoundError(str(entry_id))
    return entry


def list_journal_entries(
    db: Session,
    tenant_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[JournalEntry]:
    return (
        db.execute(
            select(JournalEntry)
            .where(JournalEntry.tenant_id == tenant_id)
            .order_by(JournalEntry.posted_at.desc())
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )
