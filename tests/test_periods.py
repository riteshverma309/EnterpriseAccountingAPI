"""
tests/test_periods.py
Integration tests for Fiscal Periods and Ledger Closing validations.
"""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient


class TestFiscalPeriods:
    def test_create_period_success(self, client: TestClient, sample_tenant: dict):
        tenant_id = sample_tenant["id"]
        today = date.today()
        start_date = today.replace(day=1)
        end_date = start_date + timedelta(days=30)
        
        resp = client.post(
            "/api/v1/periods/",
            json={
                "tenant_id": tenant_id,
                "name": "2026-M01",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "is_closed": False,
            }
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "2026-M01"
        assert data["is_closed"] is False

    def test_close_period(self, client: TestClient, sample_tenant: dict):
        tenant_id = sample_tenant["id"]
        today = date.today()
        
        resp = client.post(
            "/api/v1/periods/",
            json={
                "tenant_id": tenant_id,
                "name": "2026-M02",
                "start_date": today.isoformat(),
                "end_date": today.isoformat(),
                "is_closed": False,
            }
        )
        period_id = resp.json()["id"]

        put_resp = client.put(f"/api/v1/periods/{period_id}", json={"is_closed": True})
        assert put_resp.status_code == 200
        assert put_resp.json()["is_closed"] is True

    def test_post_journal_entry_in_closed_period_returns_403(self, client: TestClient, sample_tenant: dict, sample_accounts: dict):
        tenant_id = sample_tenant["id"]
        cash_id = sample_accounts["1010"]["id"]
        revenue_id = sample_accounts["4000"]["id"]
        
        # 1. Close a period that encompasses TODAY
        # The logic checks if current_date is between start_date and end_date and is_closed=True
        today = date.today()
        client.post(
            "/api/v1/periods/",
            json={
                "tenant_id": tenant_id,
                "name": "CLOSED-NOW",
                "start_date": (today - timedelta(days=5)).isoformat(),
                "end_date": (today + timedelta(days=5)).isoformat(),
                "is_closed": True,
            }
        )

        # 2. Attempt to post a journal entry
        payload = {
            "tenant_id": tenant_id,
            "description": "Late entry",
            "currency": "USD",
            "lines": [
                {"account_id": cash_id, "amount": "100.00", "description": "DR"},
                {"account_id": revenue_id, "amount": "-100.00", "description": "CR"},
            ]
        }
        
        resp = client.post("/api/v1/journal-entries/", json=payload)
        
        # 3. Verify it is rejected with 403 Forbidden
        assert resp.status_code == 403, resp.text
        assert "is closed" in resp.json()["detail"]
