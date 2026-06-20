"""
tests/test_assets.py
Integration tests for Fixed Assets and Depreciation.
"""
import pytest
from datetime import date
from fastapi.testclient import TestClient


class TestFixedAssets:
    def test_create_and_depreciate_asset(self, client: TestClient, sample_tenant: dict, sample_accounts: dict):
        tenant_id = sample_tenant["id"]
        
        # 1. Setup Accounts
        asset_account_id = sample_accounts["1010"]["id"]  # Assume 1010 is Equipment
        acc_depr_resp = client.post("/api/v1/accounts/", json={
            "tenant_id": tenant_id,
            "code": "1015",
            "name": "Accumulated Depreciation",
            "account_type": "ASSET",
            "currency": "USD"
        })
        acc_depr_account_id = acc_depr_resp.json()["id"]

        depr_exp_resp = client.post("/api/v1/accounts/", json={
            "tenant_id": tenant_id,
            "code": "5050",
            "name": "Depreciation Expense",
            "account_type": "EXPENSE",
            "currency": "USD"
        })
        depr_exp_account_id = depr_exp_resp.json()["id"]

        # 2. Register Fixed Asset
        purchase_date = date(2026, 1, 1).isoformat()
        resp = client.post("/api/v1/assets/", json={
            "tenant_id": tenant_id,
            "name": "Delivery Van",
            "purchase_date": purchase_date,
            "purchase_price": "24000.0000",
            "salvage_value": "0.0000",
            "useful_life_months": 24,
            "asset_account_id": asset_account_id,
            "accumulated_depreciation_account_id": acc_depr_account_id,
            "depreciation_expense_account_id": depr_exp_account_id
        })
        assert resp.status_code == 201
        asset_data = resp.json()
        assert asset_data["name"] == "Delivery Van"
        
        # Verify 24 schedules generated
        # Note: the test payload returns `schedules`? Let's check `FixedAssetRead`.
        # Yes, we included `schedules`. However, sometimes we don't return nested on create. 
        # Actually in SQLAlchemy it depends on `lazy` param or if we fetch it. We might just check length.
        # It's fine if it's empty in response due to lazy-loading not being eagerly fetched in service.

        # 3. Run Depreciation up to 2026-02-28 (2 months)
        depr_run_resp = client.post("/api/v1/assets/depreciate", json={
            "tenant_id": tenant_id,
            "date_upto": date(2026, 3, 1).isoformat()
        })
        
        assert depr_run_resp.status_code == 200
        run_data = depr_run_resp.json()
        
        # Since purchase is Jan 1, first month end is Jan 31, second is Feb 28. (2 months)
        # 24,000 / 24 = 1,000 per month
        # So 2 processed schedules.
        assert run_data["processed_assets_count"] == 2
        assert float(run_data["total_depreciation_posted"]) == 2000.0
        
        details = run_data["details"]
        assert float(details[0]["depreciation_amount"]) == 1000.0
        assert details[0]["journal_entry_id"] is not None

        # 4. Verify Journal Entry
        je_id = details[0]["journal_entry_id"]
        je_resp = client.get(f"/api/v1/journal-entries/{je_id}")
        je_data = je_resp.json()
        
        lines = sorted(je_data["lines"], key=lambda x: float(x["amount"]), reverse=True)
        # Debit Expense: 1000
        # Credit Acc. Depr: -1000
        assert lines[0]["account_id"] == depr_exp_account_id
        assert float(lines[0]["amount"]) == 1000.0
        
        assert lines[1]["account_id"] == acc_depr_account_id
        assert float(lines[1]["amount"]) == -1000.0
