"""
tests/test_banking.py
Integration tests for Bank Reconciliation logic.
"""
import pytest
from datetime import date
from fastapi.testclient import TestClient


class TestBankReconciliation:
    def test_import_bank_statement_and_reconcile(self, client: TestClient, sample_tenant: dict, sample_accounts: dict):
        tenant_id = sample_tenant["id"]
        cash_account_id = sample_accounts["1010"]["id"]
        revenue_account_id = sample_accounts["4000"]["id"]

        today = date.today().isoformat()
        
        # 1. Post a Journal Entry
        je_payload = {
            "tenant_id": tenant_id,
            "description": "Customer Payment",
            "currency": "USD",
            "lines": [
                {"account_id": cash_account_id, "amount": "500.0000", "description": "Cash Receipt"},
                {"account_id": revenue_account_id, "amount": "-500.0000", "description": "Revenue"},
            ]
        }
        je_resp = client.post("/api/v1/journal-entries/", json=je_payload)
        assert je_resp.status_code == 201
        je_data = je_resp.json()
        
        # Extract the cash journal line ID
        cash_journal_line_id = next(line["id"] for line in je_data["lines"] if line["account_id"] == cash_account_id)

        # 2. Import Bank Statement
        bs_payload = {
            "tenant_id": tenant_id,
            "account_id": cash_account_id,
            "statement_date": today,
            "starting_balance": "0.0000",
            "ending_balance": "500.0000",
            "lines": [
                {
                    "date": today,
                    "description": "Wire Transfer from Customer",
                    "amount": "500.0000"
                }
            ]
        }
        bs_resp = client.post("/api/v1/banking/statements", json=bs_payload)
        assert bs_resp.status_code == 201
        bs_data = bs_resp.json()
        
        bank_line_id = bs_data["lines"][0]["id"]
        assert bs_data["lines"][0]["is_reconciled"] is False
        assert bs_data["is_reconciled"] is False

        # 3. Reconcile Bank Line against Journal Line
        recon_payload = {
            "tenant_id": tenant_id,
            "bank_statement_line_id": bank_line_id,
            "journal_line_id": cash_journal_line_id
        }
        recon_resp = client.post("/api/v1/banking/reconcile", json=recon_payload)
        assert recon_resp.status_code == 201
        
        # 4. Verify Bank Statement is updated
        get_bs_resp = client.get(f"/api/v1/banking/statements/tenant/{tenant_id}")
        assert get_bs_resp.status_code == 200
        get_bs_data = get_bs_resp.json()[0]
        
        assert get_bs_data["is_reconciled"] is True
        assert get_bs_data["lines"][0]["is_reconciled"] is True

    def test_reconcile_with_mismatched_amount_returns_409(self, client: TestClient, sample_tenant: dict, sample_accounts: dict):
        tenant_id = sample_tenant["id"]
        cash_account_id = sample_accounts["1010"]["id"]
        revenue_account_id = sample_accounts["4000"]["id"]

        today = date.today().isoformat()
        
        je_resp = client.post("/api/v1/journal-entries/", json={
            "tenant_id": tenant_id,
            "description": "Customer Payment 2",
            "currency": "USD",
            "lines": [
                {"account_id": cash_account_id, "amount": "100.0000", "description": "Cash"},
                {"account_id": revenue_account_id, "amount": "-100.0000", "description": "Revenue"},
            ]
        })
        cash_journal_line_id = next(line["id"] for line in je_resp.json()["lines"] if line["account_id"] == cash_account_id)

        bs_resp = client.post("/api/v1/banking/statements", json={
            "tenant_id": tenant_id,
            "account_id": cash_account_id,
            "statement_date": today,
            "starting_balance": "0.0000",
            "ending_balance": "500.0000",
            "lines": [
                {
                    "date": today,
                    "description": "Wire Transfer",
                    "amount": "200.0000"  # MISMATCH: 200 vs 100
                }
            ]
        })
        bank_line_id = bs_resp.json()["lines"][0]["id"]

        recon_resp = client.post("/api/v1/banking/reconcile", json={
            "tenant_id": tenant_id,
            "bank_statement_line_id": bank_line_id,
            "journal_line_id": cash_journal_line_id
        })
        assert recon_resp.status_code == 409
        assert "Amount mismatch" in recon_resp.json()["detail"]
