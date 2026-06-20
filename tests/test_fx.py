"""
tests/test_fx.py
Integration tests for Multi-Currency FX Revaluation logic.
"""
import pytest
from datetime import date
from fastapi.testclient import TestClient


class TestFxRevaluation:
    def test_fx_revaluation(self, client: TestClient, sample_tenant: dict):
        tenant_id = sample_tenant["id"]
        today = date.today().isoformat()

        # 1. Create a EUR Account and an Unrealized Gain/Loss Account
        eur_resp = client.post("/api/v1/accounts/", json={
            "tenant_id": tenant_id,
            "code": "1020",
            "name": "EUR Bank Account",
            "account_type": "ASSET",
            "currency": "EUR"
        })
        eur_account_id = eur_resp.json()["id"]

        gain_loss_resp = client.post("/api/v1/accounts/", json={
            "tenant_id": tenant_id,
            "code": "8000",
            "name": "Unrealized FX Gain/Loss",
            "account_type": "REVENUE",
            "currency": "USD"
        })
        gain_loss_account_id = gain_loss_resp.json()["id"]
        
        cash_resp = client.post("/api/v1/accounts/", json={
            "tenant_id": tenant_id,
            "code": "1011",
            "name": "USD Cash",
            "account_type": "ASSET",
            "currency": "USD"
        })
        cash_account_id = cash_resp.json()["id"]

        # 2. Post a Journal Entry in EUR
        # We bought 100 EUR at an exchange rate of 1.10 (so we paid 110 USD)
        # In our simplified system, we record the amount in base currency (110) 
        # and the exchange rate on the line (1.10)
        je_resp = client.post("/api/v1/journal-entries/", json={
            "tenant_id": tenant_id,
            "description": "Buy EUR",
            "currency": "USD",  # Base currency
            "lines": [
                {
                    "account_id": eur_account_id, 
                    "amount": "110.0000", 
                    "description": "Buy 100 EUR",
                    "exchange_rate": "1.100000"
                },
                {
                    "account_id": cash_account_id, 
                    "amount": "-110.0000", 
                    "description": "Pay USD",
                    "exchange_rate": "1.000000"
                },
            ]
        })
        assert je_resp.status_code == 201

        # 3. Set new exchange rate at month-end: 1 EUR = 1.20 USD
        rate_resp = client.post("/api/v1/fx/rates", json={
            "tenant_id": tenant_id,
            "date": today,
            "from_currency": "EUR",
            "to_currency": "USD",
            "rate": "1.200000"
        })
        assert rate_resp.status_code == 201

        # 4. Run Revaluation
        rev_resp = client.post("/api/v1/fx/revalue", json={
            "tenant_id": tenant_id,
            "target_currency": "EUR",
            "date": today,
            "unrealized_gain_loss_account_id": gain_loss_account_id
        })
        assert rev_resp.status_code == 200
        rev_data = rev_resp.json()
        
        # 100 EUR is now worth 120 USD. Old balance was 110 USD.
        # So Unrealized Gain = 10 USD.
        assert len(rev_data["revalued_accounts"]) == 1
        acc_rev = rev_data["revalued_accounts"][0]
        assert float(acc_rev["foreign_balance"]) == 100.0
        assert float(acc_rev["old_base_balance"]) == 110.0
        assert float(acc_rev["new_base_balance"]) == 120.0
        assert float(acc_rev["unrealized_gain_loss"]) == 10.0

        # Verify Journal Entry was created
        je_id = rev_data["journal_entry_id"]
        assert je_id is not None
        
        get_je = client.get(f"/api/v1/journal-entries/{je_id}")
        je_lines = get_je.json()["lines"]
        
        # Should debit EUR account by 10.0
        # Should credit Unrealized Gain by 10.0 (-10.0)
        lines = sorted(je_lines, key=lambda x: float(x["amount"]), reverse=True)
        assert lines[0]["account_id"] == eur_account_id
        assert float(lines[0]["amount"]) == 10.0
        
        assert lines[1]["account_id"] == gain_loss_account_id
        assert float(lines[1]["amount"]) == -10.0
