"""
app/api/deps.py
FastAPI dependency injection helpers.
"""
from typing import Generator
from sqlalchemy.orm import Session
from fastapi import Depends
from app.core.database import get_db


def get_db_session() -> Generator[Session, None, None]:
    """Re-exports get_db for use as a FastAPI Depends."""
    yield from get_db()


# Convenience alias for route signatures
DBSession = Depends(get_db_session)
