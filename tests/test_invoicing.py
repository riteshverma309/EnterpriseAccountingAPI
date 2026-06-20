"""
tests/test_invoicing.py
Integration tests for the AR/AP invoicing logic and party management.
"""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient


class TestParties:
    def test_create_party_success(self, client: TestClient, sample_tenant: dict):
        tenant_id = sample_tenant["id"]
        
        # Create Customer
        resp = client.post(
            "/api/v1/parties/",
            json={
                "tenant_id": tenant_id,
                "name": "Acme Corp",
                "party_type": "CUSTOMER",
                "email": "billing@acme.corp",
            }
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Acme Corp"
        assert data["party_type"] == "CUSTOMER"

    def test_list_parties(self, client: TestClient, sample_tenant: dict):
        tenant_id = sample_tenant["id"]
        
        client.post(
            "/api/v1/parties/",
            json={"tenant_id": tenant_id, "name": "V1", "party_type": "VENDOR"}
        )
        
        resp = client.get(f"/api/v1/parties/tenant/{tenant_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["party_type"] == "VENDOR"


class TestInvoicing:
    @pytest.fixture()
    def sample_party(self, client: TestClient, sample_tenant: dict):
        tenant_id = sample_tenant["id"]
        resp = client.post(
            "/api/v1/parties/",
            json={"tenant_id": tenant_id, "name": "Test Customer", "party_type": "CUSTOMER"}
        )
        return resp.json()

    def test_create_invoice_success(self, client: TestClient, sample_tenant: dict, sample_party: dict, sample_accounts: dict):
        tenant_id = sample_tenant["id"]
        party_id = sample_party["id"]
        revenue_account_id = sample_accounts["4000"]["id"]

        today = date.today().isoformat()
        due = (date.today() + timedelta(days=30)).isoformat()

        payload = {
            "tenant_id": tenant_id,
            "party_id": party_id,
            "invoice_type": "RECEIVABLE",
            "invoice_number": "INV-1001",
            "issue_date": today,
            "due_date": due,
            "currency": "USD",
            "lines": [
                {
                    "account_id": revenue_account_id,
                    "description": "Software Subscription",
                    "quantity": "1.0000",
                    "unit_price": "150.0000",
                    "tax_amount": "15.0000"
                }
            ]
        }
        
        resp = client.post("/api/v1/invoices/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "DRAFT"
        assert data["invoice_number"] == "INV-1001"
        assert len(data["lines"]) == 1
        assert float(data["lines"][0]["line_total"]) == 165.0

    def test_post_invoice_creates_journal_entry(self, client: TestClient, sample_tenant: dict, sample_party: dict, sample_accounts: dict):
        tenant_id = sample_tenant["id"]
        party_id = sample_party["id"]
        revenue_account_id = sample_accounts["4000"]["id"]
        ar_account_id = sample_accounts["1010"]["id"]  # Simulating AR Account with Cash for now

        # Create Invoice
        today = date.today().isoformat()
        resp = client.post("/api/v1/invoices/", json={
            "tenant_id": tenant_id,
            "party_id": party_id,
            "invoice_type": "RECEIVABLE",
            "invoice_number": "INV-1002",
            "issue_date": today,
            "due_date": today,
            "currency": "USD",
            "lines": [
                {
                    "account_id": revenue_account_id,
                    "description": "Consulting",
                    "quantity": "2.0000",
                    "unit_price": "500.0000",
                    "tax_amount": "0.0000"
                }
            ]
        })
        assert resp.status_code == 201
        invoice_id = resp.json()["id"]

        # Post Invoice
        post_url = f"/api/v1/invoices/{invoice_id}/post?ar_ap_account_id={ar_account_id}"
        post_resp = client.post(post_url)
        
        assert post_resp.status_code == 200, post_resp.text
        data = post_resp.json()
        assert data["status"] == "POSTED"
        assert data["journal_entry_id"] is not None

        # Verify Journal Entry
        je_resp = client.get(f"/api/v1/journal-entries/{data['journal_entry_id']}")
        assert je_resp.status_code == 200
        je_data = je_resp.json()
        assert je_data["status"] == "POSTED"
        assert len(je_data["lines"]) == 2

        # AR should be Debited (+1000.0000)
        # Revenue should be Credited (-1000.0000)
        lines = sorted(je_data["lines"], key=lambda x: float(x["amount"]), reverse=True)
        assert lines[0]["account_id"] == ar_account_id
        assert lines[0]["amount"] == "1000.0000"
        
        assert lines[1]["account_id"] == revenue_account_id
        assert lines[1]["amount"] == "-1000.0000"

    def test_post_already_posted_invoice_returns_409(self, client: TestClient, sample_tenant: dict, sample_party: dict, sample_accounts: dict):
        tenant_id = sample_tenant["id"]
        party_id = sample_party["id"]
        revenue_account_id = sample_accounts["4000"]["id"]
        ar_account_id = sample_accounts["1010"]["id"]

        today = date.today().isoformat()
        resp = client.post("/api/v1/invoices/", json={
            "tenant_id": tenant_id,
            "party_id": party_id,
            "invoice_type": "RECEIVABLE",
            "invoice_number": "INV-1003",
            "issue_date": today,
            "due_date": today,
            "currency": "USD",
            "lines": [
                {
                    "account_id": revenue_account_id,
                    "description": "Test",
                    "quantity": "1.0",
                    "unit_price": "100.0",
                    "tax_amount": "0.0"
                }
            ]
        })
        invoice_id = resp.json()["id"]

        post_url = f"/api/v1/invoices/{invoice_id}/post?ar_ap_account_id={ar_account_id}"
        # First post succeeds
        client.post(post_url)
        
        # Second post fails
        post_resp2 = client.post(post_url)
        assert post_resp2.status_code == 409
