"""
app/models/periods.py
Models for Fiscal Periods and accounting ledger closing.
"""
import uuid
from datetime import date
from sqlalchemy import Column, String, Date, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class FiscalPeriod(Base):
    """
    Represents an accounting period (e.g., month, quarter, year).
    If a period is closed, no journal entries can be posted within its date range.
    """
    __tablename__ = "fiscal_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(50), nullable=False)  # e.g., "2026-M01", "Q1-2026"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_closed = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_period_name_per_tenant"),
        Index("ix_fiscal_periods_tenant_id_dates", "tenant_id", "start_date", "end_date"),
    )

    # Relationships
    tenant = relationship("Tenant", backref="fiscal_periods")

    def __repr__(self) -> str:
        status = "CLOSED" if self.is_closed else "OPEN"
        return f"<FiscalPeriod {self.name} ({self.start_date} to {self.end_date}) [{status}]>"
