"""
app/models/budget.py
Models for Budgeting and Forecasting.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column,
    String,
    Numeric,
    DateTime,
    Integer,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Budget(Base):
    """
    A budget defined for a specific fiscal year.
    """
    __tablename__ = "budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    fiscal_year = Column(Integer, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "fiscal_year", "name", name="uq_budget_name_year"),
        Index("ix_budgets_tenant_id", "tenant_id"),
    )

    lines = relationship("BudgetLine", back_populates="budget", cascade="all, delete-orphan")


class BudgetLine(Base):
    """
    The planned amount for a specific account for the entire fiscal year.
    """
    __tablename__ = "budget_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The expected balance for the year. (Revenues typically negative, Expenses positive, or based on normal balance).
    # We will assume this matches the 'Normal Balance' (Positive = Debit, Negative = Credit).
    amount = Column(Numeric(precision=20, scale=4), nullable=False, default=Decimal("0.0000"))

    __table_args__ = (
        UniqueConstraint("budget_id", "account_id", name="uq_budget_line_account"),
    )

    budget = relationship("Budget", back_populates="lines")
    account = relationship("Account")
