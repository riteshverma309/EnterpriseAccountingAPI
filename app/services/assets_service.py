"""
app/services/assets_service.py
Service layer for Fixed Assets and Depreciation.
"""
import uuid
from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import FixedAsset, DepreciationSchedule, DepreciationMethod
from app.models.ledger import Tenant, Account
from app.schemas.assets import FixedAssetCreate, DepreciationRunRequest, DepreciationRunResponse, DepreciationRunResultLine
from app.schemas.ledger import JournalEntryCreate, JournalLineCreate
from app.services.ledger_service import TenantNotFoundError, AccountNotFoundError, post_journal_entry


def create_fixed_asset(db: Session, payload: FixedAssetCreate) -> FixedAsset:
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    # Verify accounts
    for acc_id in [payload.asset_account_id, payload.accumulated_depreciation_account_id, payload.depreciation_expense_account_id]:
        acc = db.get(Account, acc_id)
        if not acc or acc.tenant_id != payload.tenant_id:
            raise AccountNotFoundError(str(acc_id))

    asset = FixedAsset(
        tenant_id=payload.tenant_id,
        name=payload.name,
        description=payload.description,
        purchase_date=payload.purchase_date,
        purchase_price=payload.purchase_price,
        salvage_value=payload.salvage_value,
        useful_life_months=payload.useful_life_months,
        depreciation_method=payload.depreciation_method,
        asset_account_id=payload.asset_account_id,
        accumulated_depreciation_account_id=payload.accumulated_depreciation_account_id,
        depreciation_expense_account_id=payload.depreciation_expense_account_id,
    )
    db.add(asset)
    db.flush()

    # Generate Depreciation Schedule
    if payload.depreciation_method == DepreciationMethod.STRAIGHT_LINE:
        depreciable_base = payload.purchase_price - payload.salvage_value
        monthly_depreciation = (depreciable_base / Decimal(payload.useful_life_months)).quantize(Decimal("0.0000"))
        
        # Adjust last month for rounding
        total_depreciation = monthly_depreciation * payload.useful_life_months
        rounding_diff = depreciable_base - total_depreciation
        
        current_date = payload.purchase_date
        for i in range(payload.useful_life_months):
            # End of the current month
            end_of_month = current_date + relativedelta(day=31)
            
            amount = monthly_depreciation
            if i == payload.useful_life_months - 1:
                amount += rounding_diff
                
            schedule_line = DepreciationSchedule(
                asset_id=asset.id,
                scheduled_date=end_of_month,
                depreciation_amount=amount,
            )
            db.add(schedule_line)
            # Move to next month
            current_date = current_date + relativedelta(months=1)
    else:
        raise NotImplementedError(f"Depreciation method {payload.depreciation_method} not implemented.")

    db.commit()
    db.refresh(asset)
    return asset


def run_depreciation(db: Session, payload: DepreciationRunRequest) -> DepreciationRunResponse:
    """
    Posts all pending depreciation schedules up to the given date.
    """
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise TenantNotFoundError(str(payload.tenant_id))

    # Find pending schedule lines
    pending_schedules = db.execute(
        select(DepreciationSchedule)
        .join(FixedAsset)
        .where(
            FixedAsset.tenant_id == payload.tenant_id,
            DepreciationSchedule.scheduled_date <= payload.date_upto,
            DepreciationSchedule.journal_entry_id == None
        )
    ).scalars().all()

    results = []
    total_posted = Decimal("0.0000")

    for schedule in pending_schedules:
        asset = schedule.asset
        
        # Create Journal Entry
        # Expense: Debit (+), Acc. Depr: Credit (-)
        je_payload = JournalEntryCreate(
            tenant_id=tenant.id,
            description=f"Depreciation for {asset.name} - {schedule.scheduled_date}",
            currency=tenant.base_currency,
            lines=[
                JournalLineCreate(
                    account_id=asset.depreciation_expense_account_id,
                    amount=schedule.depreciation_amount,
                    description=f"Depreciation Expense - {asset.name}"
                ),
                JournalLineCreate(
                    account_id=asset.accumulated_depreciation_account_id,
                    amount=-schedule.depreciation_amount,
                    description=f"Accumulated Depreciation - {asset.name}"
                )
            ]
        )
        
        je = post_journal_entry(db, je_payload)
        
        schedule.journal_entry_id = je.id
        db.add(schedule)
        
        total_posted += schedule.depreciation_amount
        results.append(
            DepreciationRunResultLine(
                asset_id=asset.id,
                asset_name=asset.name,
                depreciation_amount=schedule.depreciation_amount,
                journal_entry_id=je.id
            )
        )

    db.commit()

    return DepreciationRunResponse(
        tenant_id=payload.tenant_id,
        date_upto=payload.date_upto,
        processed_assets_count=len(pending_schedules),
        total_depreciation_posted=total_posted,
        details=results
    )


def list_fixed_assets(db: Session, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[FixedAsset]:
    return db.execute(
        select(FixedAsset)
        .where(FixedAsset.tenant_id == tenant_id)
        .order_by(FixedAsset.purchase_date.desc())
        .offset(skip)
        .limit(limit)
    ).scalars().unique().all()
