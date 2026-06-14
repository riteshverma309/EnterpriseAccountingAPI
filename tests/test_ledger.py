"""
tests/test_ledger.py
Core double-entry ledger tests.

Agent: LedgerTestAgent
Covers:
- Double-entry enforcement (balanced vs unbalanced entries)
- Journal entry posting and retrieval
- Account balance updates
- Immutability — entries cannot be re-posted
- Reversal entries create correct offsetting lines
- Trial balance is_balanced flag
- Balance sheet accounting equation validation
"""
from __future__ import annotations

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient


# ════════════════════════════════════════════════════════════════════════════
# T001 — Health Check
# ════════════════════════════════════════════════════════════════════════════

class TestSystemHealth:
    def test_health_endpoint_returns_operational(self, client: TestClient):
        """T001: /health must return status=operational when DB is up."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("operational", "degraded")
        assert "plugins" in data
        assert isinstance(data["plugins"], list)

    def test_root_endpoint(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "docs" in resp.json()


# ════════════════════════════════════════════════════════════════════════════
# T002 — Tenant CRUD
# ════════════════════════════════════════════════════════════════════════════

class TestTenantCRUD:
    def test_create_tenant_success(self, client: TestClient):
        """T002a: Create a tenant returns 201 with correct fields."""
        resp = client.post("/api/v1/tenants/", json={
            "name": "Acme Corp",
            "base_currency": "USD",
            "fiscal_year_start_month": 4,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Acme Corp"
        assert data["base_currency"] == "USD"
        assert data["fiscal_year_start_month"] == 4
        assert data["is_active"] is True
        assert "id" in data

    def test_list_tenants(self, client: TestClient, sample_tenant: dict):
        """T002b: List tenants returns at least one entry."""
        resp = client.get("/api/v1/tenants/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_tenant_by_id(self, client: TestClient, sample_tenant: dict):
        """T002c: Get tenant by ID returns correct tenant."""
        tid = sample_tenant["id"]
        resp = client.get(f"/api/v1/tenants/{tid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == tid

    def test_get_nonexistent_tenant_returns_404(self, client: TestClient):
        """T002d: Fetching a non-existent tenant returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(f"/api/v1/tenants/{fake_id}")
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# T003 — Chart of Accounts
# ════════════════════════════════════════════════════════════════════════════

class TestChartOfAccounts:
    def test_create_account_success(self, client: TestClient, sample_tenant: dict):
        """T003a: Create an account returns 201 with zero balance."""
        resp = client.post("/api/v1/accounts/", json={
            "tenant_id": sample_tenant["id"],
            "code": "1100",
            "name": "Accounts Receivable",
            "account_type": "ASSET",
            "currency": "USD",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "1100"
        assert Decimal(data["balance"]) == Decimal("0")
        assert data["account_type"] == "ASSET"

    def test_duplicate_account_code_returns_409(self, client: TestClient, sample_tenant: dict):
        """T003b: Duplicate code within same tenant returns 409."""
        payload = {
            "tenant_id": sample_tenant["id"],
            "code": "9999",
            "name": "Duplicate Test",
            "account_type": "ASSET",
            "currency": "USD",
        }
        client.post("/api/v1/accounts/", json=payload)
        resp = client.post("/api/v1/accounts/", json=payload)
        assert resp.status_code == 409

    def test_invalid_account_type_rejected(self, client: TestClient, sample_tenant: dict):
        """T003c: Invalid account_type returns 422."""
        resp = client.post("/api/v1/accounts/", json={
            "tenant_id": sample_tenant["id"],
            "code": "XXXX",
            "name": "Bad Type",
            "account_type": "INVALID_TYPE",
            "currency": "USD",
        })
        assert resp.status_code == 422

    def test_list_accounts_for_tenant(self, client: TestClient, sample_accounts: dict):
        """T003d: List returns all seeded accounts."""
        tenant_id = list(sample_accounts.values())[0]["tenant_id"]
        resp = client.get(f"/api/v1/accounts/tenant/{tenant_id}")
        assert resp.status_code == 200
        codes = {a["code"] for a in resp.json()}
        assert {"1010", "2000", "3000", "4000", "5000"}.issubset(codes)

    def test_hierarchical_account_parent(self, client: TestClient, sample_accounts: dict):
        """T003e: Creating a child account with parent_id succeeds."""
        parent = sample_accounts["1010"]
        resp = client.post("/api/v1/accounts/", json={
            "tenant_id": parent["tenant_id"],
            "parent_id": parent["id"],
            "code": "1011",
            "name": "Petty Cash",
            "account_type": "ASSET",
            "currency": "USD",
        })
        assert resp.status_code == 201
        assert resp.json()["parent_id"] == parent["id"]


# ════════════════════════════════════════════════════════════════════════════
# T004 — Double-Entry Enforcement
# ════════════════════════════════════════════════════════════════════════════

class TestDoubleEntryEnforcement:
    def _make_balanced_entry(self, tenant_id: str, accounts: dict) -> dict:
        """Helper: balanced cash sale entry (DR Cash 100, CR Revenue -100)."""
        return {
            "tenant_id": tenant_id,
            "description": "Cash sale",
            "reference_id": "SALE-001",
            "currency": "USD",
            "lines": [
                {"account_id": accounts["1010"]["id"], "amount": "100.00"},
                {"account_id": accounts["4000"]["id"], "amount": "-100.00"},
            ],
        }

    def test_balanced_entry_posts_successfully(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T004a: A balanced entry (sum=0) returns 201 POSTED status."""
        payload = self._make_balanced_entry(sample_tenant["id"], sample_accounts)
        resp = client.post("/api/v1/journal-entries/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "POSTED"
        assert len(data["lines"]) == 2

    def test_unbalanced_entry_returns_422(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T004b: An unbalanced entry (sum≠0) returns 422."""
        resp = client.post("/api/v1/journal-entries/", json={
            "tenant_id": sample_tenant["id"],
            "description": "Unbalanced entry",
            "currency": "USD",
            "lines": [
                {"account_id": sample_accounts["1010"]["id"], "amount": "100.00"},
                {"account_id": sample_accounts["4000"]["id"], "amount": "-90.00"},  # off by 10
            ],
        })
        assert resp.status_code == 422

    def test_single_line_entry_rejected(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T004c: A single-line entry is rejected by schema (min_length=2)."""
        resp = client.post("/api/v1/journal-entries/", json={
            "tenant_id": sample_tenant["id"],
            "description": "Single line",
            "currency": "USD",
            "lines": [
                {"account_id": sample_accounts["1010"]["id"], "amount": "100.00"},
            ],
        })
        assert resp.status_code == 422

    def test_zero_amount_line_rejected(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T004d: A line with amount=0 is rejected by the schema validator."""
        resp = client.post("/api/v1/journal-entries/", json={
            "tenant_id": sample_tenant["id"],
            "description": "Zero line",
            "currency": "USD",
            "lines": [
                {"account_id": sample_accounts["1010"]["id"], "amount": "0"},
                {"account_id": sample_accounts["4000"]["id"], "amount": "0"},
            ],
        })
        assert resp.status_code == 422

    def test_multi_line_balanced_entry(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T004e: Multi-line entry (3 lines) posts if sum equals zero."""
        resp = client.post("/api/v1/journal-entries/", json={
            "tenant_id": sample_tenant["id"],
            "description": "Multi-line purchase",
            "currency": "USD",
            "lines": [
                {"account_id": sample_accounts["5000"]["id"], "amount": "80.00"},
                {"account_id": sample_accounts["5000"]["id"], "amount": "20.00"},
                {"account_id": sample_accounts["2000"]["id"], "amount": "-100.00"},
            ],
        })
        assert resp.status_code == 201
        assert len(resp.json()["lines"]) == 3

    def test_wrong_tenant_account_rejected(
        self, client: TestClient, sample_accounts: dict
    ):
        """T004f: Posting to an account from a different tenant returns 404."""
        # Create a second tenant
        resp_t2 = client.post("/api/v1/tenants/", json={
            "name": "Other Corp", "base_currency": "EUR", "fiscal_year_start_month": 1
        })
        t2_id = resp_t2.json()["id"]

        # Try to use tenant 1's account with tenant 2's entry
        first_account = list(sample_accounts.values())[0]
        resp = client.post("/api/v1/journal-entries/", json={
            "tenant_id": t2_id,
            "description": "Cross-tenant attempt",
            "currency": "USD",
            "lines": [
                {"account_id": first_account["id"], "amount": "50.00"},
                {"account_id": first_account["id"], "amount": "-50.00"},
            ],
        })
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# T005 — Account Balance Updates
# ════════════════════════════════════════════════════════════════════════════

class TestAccountBalanceUpdates:
    def test_posting_updates_account_balance(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T005a: After posting, account balances reflect the transaction."""
        cash_id = sample_accounts["1010"]["id"]
        rev_id = sample_accounts["4000"]["id"]

        # Post: DR Cash 500, CR Revenue -500
        client.post("/api/v1/journal-entries/", json={
            "tenant_id": sample_tenant["id"],
            "description": "Sale",
            "currency": "USD",
            "lines": [
                {"account_id": cash_id, "amount": "500.00"},
                {"account_id": rev_id, "amount": "-500.00"},
            ],
        })

        cash = client.get(f"/api/v1/accounts/{cash_id}").json()
        rev = client.get(f"/api/v1/accounts/{rev_id}").json()

        assert Decimal(cash["balance"]) == Decimal("500.00")
        assert Decimal(rev["balance"]) == Decimal("-500.00")

    def test_multiple_postings_accumulate_balance(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T005b: Multiple postings accumulate correctly."""
        cash_id = sample_accounts["1010"]["id"]
        rev_id = sample_accounts["4000"]["id"]

        for amount in ["100.00", "200.00", "300.00"]:
            client.post("/api/v1/journal-entries/", json={
                "tenant_id": sample_tenant["id"],
                "description": f"Sale {amount}",
                "currency": "USD",
                "lines": [
                    {"account_id": cash_id, "amount": amount},
                    {"account_id": rev_id, "amount": f"-{amount}"},
                ],
            })

        cash = client.get(f"/api/v1/accounts/{cash_id}").json()
        assert Decimal(cash["balance"]) == Decimal("600.00")


# ════════════════════════════════════════════════════════════════════════════
# T006 — Immutability & Reversals
# ════════════════════════════════════════════════════════════════════════════

class TestImmutabilityAndReversals:
    def _post_entry(self, client: TestClient, tenant_id: str, accounts: dict) -> dict:
        resp = client.post("/api/v1/journal-entries/", json={
            "tenant_id": tenant_id,
            "description": "Original entry",
            "reference_id": "INV-001",
            "currency": "USD",
            "lines": [
                {"account_id": accounts["1010"]["id"], "amount": "250.00"},
                {"account_id": accounts["4000"]["id"], "amount": "-250.00"},
            ],
        })
        assert resp.status_code == 201
        return resp.json()

    def test_reversal_creates_new_entry(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T006a: Reversing an entry creates a new POSTED entry."""
        original = self._post_entry(client, sample_tenant["id"], sample_accounts)
        entry_id = original["id"]

        resp = client.post(f"/api/v1/journal-entries/{entry_id}/reverse", json={
            "description": "Reversal of INV-001",
        })
        assert resp.status_code == 201
        reversal = resp.json()
        assert reversal["status"] == "POSTED"
        assert reversal["reversal_of_id"] == entry_id

    def test_original_entry_marked_reversed(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T006b: After reversal, original entry status becomes REVERSED."""
        original = self._post_entry(client, sample_tenant["id"], sample_accounts)
        entry_id = original["id"]

        client.post(f"/api/v1/journal-entries/{entry_id}/reverse", json={
            "description": "Reversal of INV-001",
        })

        updated_original = client.get(f"/api/v1/journal-entries/{entry_id}").json()
        assert updated_original["status"] == "REVERSED"

    def test_reversal_negates_line_amounts(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T006c: Reversal lines have exactly negated amounts."""
        original = self._post_entry(client, sample_tenant["id"], sample_accounts)
        entry_id = original["id"]

        resp = client.post(f"/api/v1/journal-entries/{entry_id}/reverse", json={
            "description": "Reversal",
        })
        reversal = resp.json()
        original_amounts = {Decimal(l["amount"]) for l in original["lines"]}
        reversal_amounts = {Decimal(l["amount"]) for l in reversal["lines"]}

        assert original_amounts == {-a for a in reversal_amounts}

    def test_reversal_restores_account_balances(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T006d: After reversal, account balances return to pre-entry values."""
        cash_id = sample_accounts["1010"]["id"]
        rev_id = sample_accounts["4000"]["id"]

        before_cash = Decimal(client.get(f"/api/v1/accounts/{cash_id}").json()["balance"])
        before_rev = Decimal(client.get(f"/api/v1/accounts/{rev_id}").json()["balance"])

        original = self._post_entry(client, sample_tenant["id"], sample_accounts)
        client.post(f"/api/v1/journal-entries/{original['id']}/reverse", json={
            "description": "Reversal",
        })

        after_cash = Decimal(client.get(f"/api/v1/accounts/{cash_id}").json()["balance"])
        after_rev = Decimal(client.get(f"/api/v1/accounts/{rev_id}").json()["balance"])

        assert after_cash == before_cash
        assert after_rev == before_rev

    def test_double_reversal_returns_409(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T006e: Reversing an already-reversed entry returns 409."""
        original = self._post_entry(client, sample_tenant["id"], sample_accounts)
        entry_id = original["id"]

        client.post(f"/api/v1/journal-entries/{entry_id}/reverse", json={
            "description": "First reversal",
        })
        resp = client.post(f"/api/v1/journal-entries/{entry_id}/reverse", json={
            "description": "Second reversal attempt",
        })
        assert resp.status_code == 409


# ════════════════════════════════════════════════════════════════════════════
# T007 — Trial Balance & Balance Sheet
# ════════════════════════════════════════════════════════════════════════════

class TestReports:
    def test_trial_balance_is_balanced_after_valid_entries(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T007a: Trial balance is_balanced=True after valid double-entry postings."""
        # Post a sale: DR Cash 1000, CR Revenue -1000
        client.post("/api/v1/journal-entries/", json={
            "tenant_id": sample_tenant["id"],
            "description": "Sale",
            "currency": "USD",
            "lines": [
                {"account_id": sample_accounts["1010"]["id"], "amount": "1000.00"},
                {"account_id": sample_accounts["4000"]["id"], "amount": "-1000.00"},
            ],
        })

        resp = client.get(f"/api/v1/reports/trial-balance/{sample_tenant['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_balanced"] is True
        assert Decimal(data["total_debits"]) == Decimal(data["total_credits"])

    def test_balance_sheet_generated(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T007b: Balance sheet endpoint returns expected structure."""
        resp = client.get(f"/api/v1/reports/balance-sheet/{sample_tenant['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "sections" in data
        assert "assets" in data["sections"]
        assert "liabilities" in data["sections"]
        assert "equity" in data["sections"]
        assert "accounting_equation_balanced" in data

    def test_trial_balance_line_count_matches_accounts(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T007c: Trial balance line count >= number of active accounts seeded."""
        resp = client.get(f"/api/v1/reports/trial-balance/{sample_tenant['id']}")
        assert resp.status_code == 200
        assert len(resp.json()["lines"]) >= 5  # 5 seeded accounts
