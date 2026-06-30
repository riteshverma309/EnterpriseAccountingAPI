"""
app/api/deps.py
FastAPI dependency injection helpers.
"""
from typing import Generator, Optional
from sqlalchemy.orm import Session
from fastapi import Depends, Header, HTTPException, status
from app.core.auth import AuthorizationError, InvalidTokenError, get_authenticated_principal, require_role
from app.core.database import get_db


def get_db_session() -> Generator[Session, None, None]:
    """Re-exports get_db for use as a FastAPI Depends."""
    yield from get_db()


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Validate an optional Bearer token and return the authenticated subject payload."""
    if not authorization:
        return {"subject": "anonymous", "role": "viewer"}
    try:
        return get_authenticated_principal(authorization)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))


def require_editor_role(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that allows accountant/admin roles to write while denying viewer roles."""
    try:
        require_role(user, allowed_roles={"accountant", "admin"})
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return user


# Convenience alias for route signatures
DBSession = Depends(get_db_session)
