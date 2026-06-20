"""
app/models/fx.py
Models for Foreign Exchange rates.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column,
    String,
    Numeric,
    DateTime,
    Date,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class ExchangeRate(Base):
    """
    Daily exchange rate for a currency pair.
    Always defined as from_currency -> to_currency.
    If a tenant's base_currency is USD, a rate for EUR -> USD of 1.10 means 1 EUR = 1.10 USD.
    """
    __tablename__ = "exchange_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(Date, nullable=False)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    
    # E.g. 1 from_currency = {rate} to_currency
    rate = Column(Numeric(precision=20, scale=6), nullable=False)
    
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "date", "from_currency", "to_currency", name="uq_fx_rate"),
        Index("ix_exchange_rates_tenant_id", "tenant_id"),
    )

    tenant = relationship("Tenant")
