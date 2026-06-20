"""
app/services/fx_service.py
Service layer for Multi-Currency FX Revaluation.
"""
import uuid
from decimal import Decimal
from typing import List

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.fx import ExchangeRate
from app.models.ledger import Tenant, Account, JournalLine
from app.schemas.fx import ExchangeRateCreate, FxRevaluationRequest, FxRevaluationResponse, FxRevaluationResultLine
from app.schemas.ledger import JournalEntryCreate, JournalLineCreate
from app.services.ledger_service import TenantNotFoundError, AccountNotFoundError, post_journal_entry


class ExchangeRateNotFoundError(Exception):
    def __init__(self, currency: str, date: str):
        super().__init__(f"No exchange rate found for {currency} on {date}.")


def set_exchange_rate(db: Session, payload: ExchangeRateCreate) -> ExchangeRate:
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    # Upsert logic for MVP: if rate exists for this date and pair, update it.
    rate = db.execute(
        select(ExchangeRate).where(
            ExchangeRate.tenant_id == payload.tenant_id,
            ExchangeRate.date == payload.date,
            ExchangeRate.from_currency == payload.from_currency,
            ExchangeRate.to_currency == payload.to_currency,
        )
    ).scalar_one_or_none()

    if rate:
        rate.rate = payload.rate
    else:
        rate = ExchangeRate(
            tenant_id=payload.tenant_id,
            date=payload.date,
            from_currency=payload.from_currency,
            to_currency=payload.to_currency,
            rate=payload.rate,
        )
        db.add(rate)
    
    db.commit()
    db.refresh(rate)
    return rate


def run_fx_revaluation(db: Session, payload: FxRevaluationRequest) -> FxRevaluationResponse:
    """
    Revalues all accounts denominated in `target_currency` based on the exchange rate
    on the specified `date`. Posts an adjustment journal entry to reflect unrealized gains/losses.
    """
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    # Find the exchange rate
    rate = db.execute(
        select(ExchangeRate).where(
            ExchangeRate.tenant_id == payload.tenant_id,
            ExchangeRate.date == payload.date,
            ExchangeRate.from_currency == payload.target_currency,
            ExchangeRate.to_currency == tenant.base_currency,
        )
    ).scalar_one_or_none()

    if not rate:
        raise ExchangeRateNotFoundError(payload.target_currency, str(payload.date))

    current_rate = rate.rate

    # Find accounts to revalue
    accounts_to_revalue = db.execute(
        select(Account).where(
            Account.tenant_id == payload.tenant_id,
            Account.currency == payload.target_currency,
            Account.is_active == True
        )
    ).scalars().all()

    results = []
    journal_lines = []
    total_adjustment = Decimal("0.0000")

    for account in accounts_to_revalue:
        # Calculate foreign balance: sum(amount / exchange_rate)
        # Note: In a real system, the ledger model natively stores both base and foreign balances.
        # We simulate it here by reconstructing it from the journal lines.
        lines = db.execute(
            select(JournalLine).where(JournalLine.account_id == account.id)
        ).scalars().all()
        
        foreign_balance = Decimal("0.0000")
        for line in lines:
            if line.exchange_rate and line.exchange_rate > 0:
                foreign_balance += (line.amount / line.exchange_rate)
            else:
                foreign_balance += line.amount
                
        # The new required balance in base currency
        new_base_balance = foreign_balance * current_rate
        
        # The difference to post
        unrealized_gain_loss = new_base_balance - account.balance
        
        # Quantize to 4 decimals
        unrealized_gain_loss = unrealized_gain_loss.quantize(Decimal("0.0000"))
        
        if unrealized_gain_loss != Decimal("0.0000"):
            results.append(
                FxRevaluationResultLine(
                    account_id=account.id,
                    account_code=account.code,
                    foreign_balance=foreign_balance,
                    old_base_balance=account.balance,
                    new_base_balance=new_base_balance,
                    unrealized_gain_loss=unrealized_gain_loss
                )
            )
            
            # Adjustment to the target account
            journal_lines.append(
                JournalLineCreate(
                    account_id=account.id,
                    amount=unrealized_gain_loss,
                    description=f"FX Revaluation for {payload.date}",
                    exchange_rate=current_rate,  # new current rate
                )
            )
            total_adjustment += unrealized_gain_loss

    journal_entry_id = None
    
    if journal_lines:
        # The offset goes to the Unrealized Gain/Loss account
        # If total adjustment is positive (debit), we credit the gain/loss account
        journal_lines.append(
            JournalLineCreate(
                account_id=payload.unrealized_gain_loss_account_id,
                amount=-total_adjustment,
                description=f"Offset for FX Revaluation {payload.target_currency} on {payload.date}",
                exchange_rate=Decimal("1.000000")
            )
        )
        
        je_payload = JournalEntryCreate(
            tenant_id=payload.tenant_id,
            description=f"FX Revaluation for {payload.target_currency} at rate {current_rate}",
            currency=tenant.base_currency,
            lines=journal_lines
        )
        
        je = post_journal_entry(db, je_payload)
        journal_entry_id = je.id

    return FxRevaluationResponse(
        tenant_id=payload.tenant_id,
        target_currency=payload.target_currency,
        date=payload.date,
        exchange_rate=current_rate,
        journal_entry_id=journal_entry_id,
        revalued_accounts=results
    )
