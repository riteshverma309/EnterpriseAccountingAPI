"""
app/models/banking.py
Models for Bank Reconciliation.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column,
    String,
    Text,
    Numeric,
    DateTime,
    Date,
    Boolean,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class BankStatement(Base):
    """
    A bank statement imported from an external source (e.g. CSV/MT940).
    """
    __tablename__ = "bank_statements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The GL account this statement belongs to (e.g., Cash / Checking)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    
    statement_date = Column(Date, nullable=False)
    starting_balance = Column(Numeric(precision=20, scale=4), nullable=False, default=Decimal("0.0000"))
    ending_balance = Column(Numeric(precision=20, scale=4), nullable=False)
    
    is_reconciled = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_bank_statements_tenant_id", "tenant_id"),
        Index("ix_bank_statements_account_id", "account_id"),
    )

    lines = relationship("BankStatementLine", back_populates="statement", cascade="all, delete-orphan")


class BankStatementLine(Base):
    """
    Individual transaction line on a bank statement.
    """
    __tablename__ = "bank_statement_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_statements.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(Date, nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Numeric(precision=20, scale=4), nullable=False)
    
    # If this line is matched against a ledger entry, we link it here
    is_reconciled = Column(Boolean, nullable=False, default=False)

    statement = relationship("BankStatement", back_populates="lines")
    reconciliations = relationship("BankReconciliation", back_populates="bank_line")


class BankReconciliation(Base):
    """
    Maps a bank statement line to a journal line.
    """
    __tablename__ = "bank_reconciliations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    bank_statement_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_statement_lines.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    journal_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("journal_lines.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    reconciled_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    bank_line = relationship("BankStatementLine", back_populates="reconciliations")
    journal_line = relationship("JournalLine")
