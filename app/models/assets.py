"""
app/models/assets.py
Models for Fixed Asset Management and Depreciation.
"""
import uuid
import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column,
    String,
    Numeric,
    DateTime,
    Date,
    Enum,
    Integer,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class DepreciationMethod(str, enum.Enum):
    STRAIGHT_LINE = "STRAIGHT_LINE"
    # Future support for DOUBLE_DECLINING, etc.


class FixedAsset(Base):
    """
    A fixed asset (e.g., Equipment, Vehicle, Building) that depreciates over time.
    """
    __tablename__ = "fixed_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    
    purchase_date = Column(Date, nullable=False)
    purchase_price = Column(Numeric(precision=20, scale=4), nullable=False)
    salvage_value = Column(Numeric(precision=20, scale=4), nullable=False, default=Decimal("0.0000"))
    useful_life_months = Column(Integer, nullable=False)
    
    depreciation_method = Column(Enum(DepreciationMethod), nullable=False, default=DepreciationMethod.STRAIGHT_LINE)

    # GL Accounts
    asset_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    accumulated_depreciation_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    depreciation_expense_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_fixed_assets_tenant_id", "tenant_id"),
    )

    schedules = relationship("DepreciationSchedule", back_populates="asset", cascade="all, delete-orphan")


class DepreciationSchedule(Base):
    """
    The monthly depreciation schedule lines for an asset.
    """
    __tablename__ = "depreciation_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fixed_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    scheduled_date = Column(Date, nullable=False)
    depreciation_amount = Column(Numeric(precision=20, scale=4), nullable=False)
    
    # If this schedule line has been posted to the ledger
    journal_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )

    asset = relationship("FixedAsset", back_populates="schedules")
    journal_entry = relationship("JournalEntry")
