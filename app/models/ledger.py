"""
app/models/ledger.py
Core ORM models for the double-entry accounting ledger.

Design Principles:
- Tenant-isolated: every entity is scoped by tenant_id.
- Hierarchical CoA: accounts have a nullable parent_id (self-referential FK).
- Immutable JournalEntries: entries are NEVER deleted or updated.
  Corrections are made via reversal entries (reversal_of_id FK).
- PostgreSQL row-level locking via SELECT FOR UPDATE is applied in the
  service layer, NOT here at the model level.
"""
import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


# ── Enumerations ─────────────────────────────────────────────────────────────

class AccountType(str, enum.Enum):
    """Normal balance side per GAAP/IFRS conventions."""
    ASSET = "ASSET"           # Normal: Debit (positive)
    LIABILITY = "LIABILITY"   # Normal: Credit (negative)
    EQUITY = "EQUITY"         # Normal: Credit (negative)
    REVENUE = "REVENUE"       # Normal: Credit (negative)
    EXPENSE = "EXPENSE"       # Normal: Debit (positive)


class EntryStatus(str, enum.Enum):
    POSTED = "POSTED"       # Live, affects balances
    REVERSED = "REVERSED"   # Has been offset by a reversal entry
    VOID = "VOID"           # Administratively voided before posting


# ── Models ───────────────────────────────────────────────────────────────────

class Tenant(Base):
    """
    Top-level multi-tenant isolation unit.
    Each tenant has its own Chart of Accounts and journal entries.
    """
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    base_currency = Column(String(3), nullable=False, default="USD")  # ISO 4217
    fiscal_year_start_month = Column(Integer, nullable=False, default=1)  # 1=Jan
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    accounts = relationship(
        "Account", back_populates="tenant", cascade="all, delete-orphan"
    )
    journal_entries = relationship(
        "JournalEntry", back_populates="tenant", cascade="all, delete-orphan"
    )
    organizations = relationship(
        "Organization", back_populates="tenant", cascade="all, delete-orphan"
    )
    branches = relationship(
        "Branch", back_populates="tenant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} name={self.name!r} currency={self.base_currency}>"


class Organization(Base):
    """Legal entity or subsidiary within a tenant."""
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    country_code = Column(String(2), nullable=False, default="US")
    base_currency = Column(String(3), nullable=False, default="USD")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_organization_name_per_tenant"),
        Index("ix_organizations_tenant_id", "tenant_id"),
    )

    tenant = relationship("Tenant", back_populates="organizations")
    branches = relationship("Branch", back_populates="organization", cascade="all, delete-orphan")


class Branch(Base):
    """Sub-business or cost center tied to an organization."""
    __tablename__ = "branches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    code = Column(String(20), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_branch_code_per_organization"),
        Index("ix_branches_tenant_id", "tenant_id"),
        Index("ix_branches_organization_id", "organization_id"),
    )

    tenant = relationship("Tenant", back_populates="branches")
    organization = relationship("Organization", back_populates="branches")


class Account(Base):
    """
    Chart of Accounts (CoA) node.
    Supports hierarchical account codes via self-referential parent_id.
    The `balance` column is updated atomically via row-level locking in the
    service layer (SELECT FOR UPDATE) to prevent race conditions.
    """
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    code = Column(String(20), nullable=False)    # e.g. "1010", "2000", "4100"
    name = Column(String(255), nullable=False)
    account_type = Column(Enum(AccountType), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    # Running balance: positive = net debit, negative = net credit
    balance = Column(
        Numeric(precision=20, scale=4), nullable=False, default=Decimal("0.0000")
    )
    is_active = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Each account code must be unique within a tenant
        UniqueConstraint("tenant_id", "code", name="uq_account_code_per_tenant"),
        Index("ix_accounts_tenant_id", "tenant_id"),
        Index("ix_accounts_parent_id", "parent_id"),
        Index("ix_accounts_account_type", "account_type"),
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="accounts")
    parent = relationship("Account", remote_side="Account.id", backref="children")
    journal_lines = relationship("JournalLine", back_populates="account")

    def __repr__(self) -> str:
        return (
            f"<Account code={self.code!r} name={self.name!r} "
            f"type={self.account_type} balance={self.balance}>"
        )


class JournalEntry(Base):
    """
    Immutable journal entry header.
    NEVER deleted or updated after posting.
    Corrections are made by creating a new entry with reversal_of_id set.
    """
    __tablename__ = "journal_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Optional reference to an external source document
    reference_id = Column(String(100), nullable=True)
    description = Column(Text, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    status = Column(Enum(EntryStatus), nullable=False, default=EntryStatus.POSTED)
    # If this entry reverses a prior entry, point to it here
    reversal_of_id = Column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    # JSON blob: plugin-specific metadata (tax codes, GST breakdowns, etc.)
    plugin_metadata = Column(Text, nullable=True)
    posted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_journal_entries_tenant_id", "tenant_id"),
        Index("ix_journal_entries_reference_id", "reference_id"),
        Index("ix_journal_entries_posted_at", "posted_at"),
        Index("ix_journal_entries_status", "status"),
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="journal_entries")
    lines = relationship(
        "JournalLine",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
        lazy="joined",          # Always eager-load lines with the entry
    )
    reversal_of = relationship(
        "JournalEntry",
        remote_side="JournalEntry.id",
        backref="reversed_by",
        foreign_keys="JournalEntry.reversal_of_id",
    )

    def __repr__(self) -> str:
        return (
            f"<JournalEntry id={self.id} ref={self.reference_id!r} "
            f"status={self.status} lines={len(self.lines)}>"
        )


class JournalLine(Base):
    """
    Individual debit/credit line within a journal entry.
    Convention: amount > 0 = Debit, amount < 0 = Credit.
    The sum of all line amounts for a given JournalEntry MUST equal zero.
    """
    __tablename__ = "journal_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Positive = Debit, Negative = Credit (zero not allowed)
    amount = Column(Numeric(precision=20, scale=4), nullable=False)
    description = Column(Text, nullable=True)
    # Plugin-computed tax portion of this line
    tax_amount = Column(
        Numeric(precision=20, scale=4), nullable=True, default=Decimal("0.0000")
    )
    # FX rate used: base_currency / line_currency
    exchange_rate = Column(
        Numeric(precision=20, scale=6), nullable=True, default=Decimal("1.000000")
    )

    __table_args__ = (
        # Enforce non-zero amounts at the DB level
        CheckConstraint("amount != 0", name="ck_journal_line_nonzero_amount"),
        Index("ix_journal_lines_journal_entry_id", "journal_entry_id"),
        Index("ix_journal_lines_account_id", "account_id"),
    )

    # Relationships
    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="journal_lines")

    def __repr__(self) -> str:
        side = "DR" if self.amount > 0 else "CR"
        return (
            f"<JournalLine {side} amount={abs(self.amount)} "
            f"account_id={self.account_id}>"
        )
