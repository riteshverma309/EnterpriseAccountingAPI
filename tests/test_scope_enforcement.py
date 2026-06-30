from __future__ import annotations

from fastapi.testclient import TestClient


def test_account_creation_rejects_scope_mismatch(client: TestClient, sample_tenant: dict):
    resp = client.post(
        "/api/v1/accounts/",
        headers={"x-tenant-id": "00000000-0000-0000-0000-000000000000"},
        json={
            "tenant_id": sample_tenant["id"],
            "code": "9100",
            "name": "Scoped Account",
            "account_type": "ASSET",
            "currency": "USD",
        },
    )
    assert resp.status_code == 403


def test_journal_entry_creation_rejects_scope_mismatch(client: TestClient, sample_tenant: dict, sample_accounts: dict):
    resp = client.post(
        "/api/v1/journal-entries/",
        headers={"x-tenant-id": "00000000-0000-0000-0000-000000000000"},
        json={
            "tenant_id": sample_tenant["id"],
            "description": "Scoped journal",
            "currency": "USD",
            "lines": [
                {"account_id": sample_accounts["1010"]["id"], "amount": "100.00"},
                {"account_id": sample_accounts["4000"]["id"], "amount": "-100.00"},
            ],
        },
    )
    assert resp.status_code == 403


def test_organization_creation_rejects_scope_mismatch(client: TestClient, sample_tenant: dict):
    resp = client.post(
        "/api/v1/organizations/",
        headers={"x-tenant-id": "00000000-0000-0000-0000-000000000000"},
        json={
            "tenant_id": sample_tenant["id"],
            "name": "Scoped Org",
            "country_code": "US",
            "base_currency": "USD",
        },
    )
    assert resp.status_code == 403


def test_period_creation_rejects_scope_mismatch(client: TestClient, sample_tenant: dict):
    resp = client.post(
        "/api/v1/periods/",
        headers={"x-tenant-id": "00000000-0000-0000-0000-000000000000"},
        json={
            "tenant_id": sample_tenant["id"],
            "name": "2026-M01",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "is_closed": False,
        },
    )
    assert resp.status_code == 403


def test_branch_creation_rejects_scope_mismatch(client: TestClient, sample_tenant: dict):
    organization_resp = client.post(
        "/api/v1/organizations/",
        json={
            "tenant_id": sample_tenant["id"],
            "name": "Scoped Org",
            "country_code": "US",
            "base_currency": "USD",
        },
    )
    assert organization_resp.status_code == 201, organization_resp.text
    organization = organization_resp.json()

    resp = client.post(
        "/api/v1/branches/",
        headers={"x-tenant-id": "00000000-0000-0000-0000-000000000000"},
        json={
            "organization_id": organization["id"],
            "name": "Scoped Branch",
            "code": "S1",
        },
    )
    assert resp.status_code == 403
