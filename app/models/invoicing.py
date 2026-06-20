"""
app/models/invoicing.py
Models for Accounts Receivable (AR) and Accounts Payable (AP).
"""
import enum
import uuid
from datetime import datetime, timezone, date
from decimal import Decimal

from sqlalchemy import (
    Column,
    String,
    Text,
    Numeric,
    DateTime,
    Date,
    Enum,
    Boolean,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class PartyType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    VENDOR = "VENDOR"
    EMPLOYEE = "EMPLOYEE"


class Party(Base):
    """
    A contact: Customer, Vendor, or Employee.
    Used for AR/AP tracking.
    """
    __tablename__ = "parties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    party_type = Column(Enum(PartyType), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_parties_tenant_id", "tenant_id"),
        Index("ix_parties_party_type", "party_type"),
    )

    tenant = relationship("Tenant", backref="parties")
    invoices = relationship("Invoice", back_populates="party")

    def __repr__(self) -> str:
        return f"<Party {self.name} ({self.party_type})>"


class InvoiceType(str, enum.Enum):
    RECEIVABLE = "RECEIVABLE"  # Customer Invoice (AR)
    PAYABLE = "PAYABLE"        # Vendor Bill (AP)


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"          # Ledger impact created
    PAID = "PAID"
    VOID = "VOID"


class Invoice(Base):
    """
    An invoice (Receivable) or bill (Payable).
    """
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    party_id = Column(
        UUID(as_uuid=True),
        ForeignKey("parties.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_type = Column(Enum(InvoiceType), nullable=False)
    status = Column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT)
    
    invoice_number = Column(String(100), nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")

    # Link to the generated Journal Entry once POSTED
    journal_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_invoices_tenant_id", "tenant_id"),
        Index("ix_invoices_party_id", "party_id"),
        Index("ix_invoices_number", "invoice_number"),
    )

    party = relationship("Party", back_populates="invoices")
    lines = relationship(
        "InvoiceLine", back_populates="invoice", cascade="all, delete-orphan"
    )
    journal_entry = relationship("JournalEntry")


class InvoiceLine(Base):
    """
    Line item for an Invoice.
    """
    __tablename__ = "invoice_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The account this line maps to (e.g., Revenue for AR, Expense for AP)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    description = Column(String(255), nullable=False)
    quantity = Column(Numeric(precision=20, scale=4), nullable=False, default=Decimal("1.0000"))
    unit_price = Column(Numeric(precision=20, scale=4), nullable=False)
    tax_amount = Column(Numeric(precision=20, scale=4), nullable=False, default=Decimal("0.0000"))

    invoice = relationship("Invoice", back_populates="lines")
    account = relationship("Account")

    @property
    def line_total(self) -> Decimal:
        return (self.quantity * self.unit_price) + self.tax_amount
