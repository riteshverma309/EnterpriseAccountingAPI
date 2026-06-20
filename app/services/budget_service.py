"""
app/services/budget_service.py
Service layer for Budgeting.
"""
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.budget import Budget, BudgetLine
from app.models.ledger import Tenant, Account
from app.schemas.budget import BudgetCreate, BudgetVsActualReport, BudgetVsActualLine
from app.services.ledger_service import TenantNotFoundError, AccountNotFoundError


def create_budget(db: Session, payload: BudgetCreate) -> Budget:
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    budget = Budget(
        tenant_id=payload.tenant_id,
        name=payload.name,
        fiscal_year=payload.fiscal_year,
    )
    db.add(budget)
    db.flush()

    for line_payload in payload.lines:
        account = db.get(Account, line_payload.account_id)
        if not account or account.tenant_id != payload.tenant_id:
            raise AccountNotFoundError(str(line_payload.account_id))
            
        line = BudgetLine(
            budget_id=budget.id,
            account_id=line_payload.account_id,
            amount=line_payload.amount,
        )
        db.add(line)

    db.commit()
    db.refresh(budget)
    return budget


def get_budget_vs_actual(db: Session, budget_id: uuid.UUID) -> BudgetVsActualReport:
    budget = db.get(Budget, budget_id)
    if not budget:
        raise ValueError(f"Budget {budget_id} not found")

    report_lines = []
    
    for line in budget.lines:
        account = line.account
        actual_amount = account.balance
        budgeted_amount = line.amount
        
        variance = budgeted_amount - actual_amount
        # Simplified absolute percentage variance
        if budgeted_amount != 0:
            variance_percentage = (variance / budgeted_amount) * Decimal("100.0")
        else:
            variance_percentage = Decimal("0.0")
            
        report_lines.append(
            BudgetVsActualLine(
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                budgeted_amount=budgeted_amount,
                actual_amount=actual_amount,
                variance=variance,
                variance_percentage=variance_percentage.quantize(Decimal("0.00")),
            )
        )
        
    return BudgetVsActualReport(
        tenant_id=budget.tenant_id,
        budget_id=budget.id,
        budget_name=budget.name,
        fiscal_year=budget.fiscal_year,
        lines=report_lines
    )
