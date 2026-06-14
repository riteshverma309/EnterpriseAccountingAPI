"""
app/services/reporting_service.py
Financial reporting service.

Generates:
- Trial Balance: all accounts with debit/credit summaries.
- Balance Sheet: Assets vs Liabilities + Equity.
- Plugin-driven statutory reports (GSTR-1, 10-K, IAS-1).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ledger import Account, AccountType
from app.plugins.base import PluginRegistry
from app.schemas.ledger import TrialBalanceLine, TrialBalanceReport


def generate_trial_balance(
    db: Session,
    tenant_id: uuid.UUID,
) -> TrialBalanceReport:
    """
    Generate a trial balance for the tenant.
    Reads live account balances (updated atomically by the posting engine).
    Positive balance = net Debit, Negative balance = net Credit.
    """
    accounts: List[Account] = (
        db.execute(
            select(Account)
            .where(Account.tenant_id == tenant_id, Account.is_active == True)
            .order_by(Account.code)
        )
        .scalars()
        .all()
    )

    lines: List[TrialBalanceLine] = []
    total_debits = Decimal("0")
    total_credits = Decimal("0")

    for account in accounts:
        balance = account.balance
        if balance > 0:
            debit = balance
            credit = Decimal("0")
            total_debits += debit
        elif balance < 0:
            debit = Decimal("0")
            credit = abs(balance)
            total_credits += credit
        else:
            debit = Decimal("0")
            credit = Decimal("0")

        lines.append(
            TrialBalanceLine(
                account_id=account.id,
                code=account.code,
                name=account.name,
                account_type=account.account_type.value,
                debit=debit,
                credit=credit,
            )
        )

    is_balanced = total_debits == total_credits

    return TrialBalanceReport(
        tenant_id=tenant_id,
        as_of=datetime.now(timezone.utc),
        total_debits=total_debits,
        total_credits=total_credits,
        is_balanced=is_balanced,
        lines=lines,
    )


def generate_balance_sheet(
    db: Session,
    tenant_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Generate a classified balance sheet.
    Assets = Liabilities + Equity (the fundamental accounting equation).
    """
    accounts: List[Account] = (
        db.execute(
            select(Account)
            .where(Account.tenant_id == tenant_id, Account.is_active == True)
            .order_by(Account.code)
        )
        .scalars()
        .all()
    )

    sections: Dict[str, List[Dict]] = {
        "ASSET": [],
        "LIABILITY": [],
        "EQUITY": [],
        "REVENUE": [],
        "EXPENSE": [],
    }

    totals: Dict[str, Decimal] = {k: Decimal("0") for k in sections}

    for account in accounts:
        atype = account.account_type.value
        balance = account.balance
        sections[atype].append(
            {
                "code": account.code,
                "name": account.name,
                "balance": str(balance),
                "currency": account.currency,
            }
        )
        totals[atype] += balance

    total_assets = totals["ASSET"]
    total_liabilities = totals["LIABILITY"]
    total_equity = totals["EQUITY"]
    # Net income = Revenue - Expense (fed into Retained Earnings)
    net_income = totals["REVENUE"] + totals["EXPENSE"]   # EXPENSE balances are negative
    total_liabilities_equity = total_liabilities + total_equity + net_income

    return {
        "tenant_id": str(tenant_id),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "accounting_equation_balanced": total_assets == total_liabilities_equity,
        "total_assets": str(total_assets),
        "total_liabilities": str(total_liabilities),
        "total_equity": str(total_equity),
        "net_income": str(net_income),
        "total_liabilities_and_equity": str(total_liabilities_equity),
        "sections": {
            "assets": sections["ASSET"],
            "liabilities": sections["LIABILITY"],
            "equity": sections["EQUITY"],
            "revenue": sections["REVENUE"],
            "expenses": sections["EXPENSE"],
        },
    }


def generate_statutory_report(
    db: Session,
    tenant_id: uuid.UUID,
    plugin_id: str,
    period_start: str,
    period_end: str,
) -> Dict[str, Any]:
    """
    Delegate statutory report generation to the appropriate plugin.
    Raises KeyError if the plugin is not registered.
    """
    plugin = PluginRegistry.get_or_raise(plugin_id)
    if not plugin.statutory_report_plugin:
        raise ValueError(
            f"Plugin {plugin_id!r} does not provide a statutory report generator."
        )
    return plugin.statutory_report_plugin.generate(
        tenant_id=str(tenant_id),
        period_start=period_start,
        period_end=period_end,
        db_session=db,
    )
