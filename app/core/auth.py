"""Simple authentication helpers for the next round of improvements."""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from app.core.config import settings


class InvalidTokenError(Exception):
    """Raised when a bearer token cannot be validated."""


class ScopeError(Exception):
    """Raised when a request attempts to access data outside its allowed scope."""


class AuthorizationError(Exception):
    """Raised when a subject does not have permission for the requested action."""


def create_access_token(subject: str, *, role: str = "viewer", expires_in_seconds: int = 3600) -> str:
    """Create a signed, opaque token for a subject identifier and role."""
    payload = f"{subject}:{role}:{int(time.time()) + expires_in_seconds}"
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def get_authenticated_principal(token: str) -> dict:
    """Validate and decode a token. Returns a subject/role payload if valid."""
    if not token:
        raise InvalidTokenError("Missing bearer token")

    raw_token = token[7:] if token.startswith("Bearer ") else token
    parts = raw_token.split(":")
    if len(parts) < 4:
        raise InvalidTokenError("Malformed token")

    payload = ":".join(parts[:-1])
    signature = parts[-1]
    expected = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise InvalidTokenError("Invalid token signature")

    subject, role, expires_at = payload.split(":", 2)
    if int(expires_at) <= int(time.time()):
        raise InvalidTokenError("Token expired")

    return {"subject": subject, "role": role}


def get_authenticated_user(token: str) -> str:
    """Backward-compatible helper that returns the authenticated subject name."""
    return get_authenticated_principal(token)["subject"]


def validate_scope(request_context: dict, tenant_id: str | None = None, organization_id: str | None = None, branch_id: str | None = None) -> None:
    """Ensure the request context does not exceed the allowed scope."""
    if tenant_id and request_context.get("tenant_id") and request_context.get("tenant_id") != tenant_id:
        raise ScopeError("tenant scope mismatch")
    if organization_id and request_context.get("organization_id") and request_context.get("organization_id") != organization_id:
        raise ScopeError("organization scope mismatch")
    if branch_id and request_context.get("branch_id") and request_context.get("branch_id") != branch_id:
        raise ScopeError("branch scope mismatch")


def require_role(user: dict | str, *, allowed_roles: set[str] | tuple[str, ...]) -> None:
    """Ensure the authenticated principal has one of the allowed roles."""
    role = user.get("role") if isinstance(user, dict) else user
    if role not in allowed_roles:
        raise AuthorizationError("insufficient privileges")
