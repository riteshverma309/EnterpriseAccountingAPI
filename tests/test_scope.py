from __future__ import annotations

from app.core.auth import ScopeError, validate_scope


def test_scope_validation_allows_matching_context():
    context = {"tenant_id": "t1", "organization_id": "o1", "branch_id": "b1"}
    validate_scope(context, tenant_id="t1", organization_id="o1", branch_id="b1")


def test_scope_validation_rejects_mismatch():
    context = {"tenant_id": "t1", "organization_id": "o1", "branch_id": "b1"}
    try:
        validate_scope(context, tenant_id="t2")
    except ScopeError:
        return
    raise AssertionError("Expected ScopeError")
