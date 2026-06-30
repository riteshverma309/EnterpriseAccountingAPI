from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.auth import create_access_token, get_authenticated_user, InvalidTokenError


def test_create_and_validate_access_token():
    token = create_access_token("alice")
    assert get_authenticated_user(token) == "alice"


def test_invalid_token_raises():
    try:
        get_authenticated_user("not-a-valid-token")
    except InvalidTokenError:
        return
    raise AssertionError("Expected InvalidTokenError")


def test_viewer_role_cannot_create_account(client: TestClient, sample_tenant: dict):
    token = create_access_token("viewer-user", role="viewer")
    resp = client.post(
        "/api/v1/accounts/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tenant_id": sample_tenant["id"],
            "code": "9100",
            "name": "Restricted Account",
            "account_type": "ASSET",
            "currency": "USD",
        },
    )
    assert resp.status_code == 403


def test_accountant_role_can_create_account(client: TestClient, sample_tenant: dict):
    token = create_access_token("accountant-user", role="accountant")
    resp = client.post(
        "/api/v1/accounts/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tenant_id": sample_tenant["id"],
            "code": "9101",
            "name": "Accountant Account",
            "account_type": "ASSET",
            "currency": "USD",
        },
    )
    assert resp.status_code == 201
