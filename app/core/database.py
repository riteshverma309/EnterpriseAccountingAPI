"""
app/core/database.py
SQLAlchemy engine, session factory, and declarative Base.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from typing import Generator
from app.core.config import settings


# ── Engine ───────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,           # Discard stale connections proactively
    echo=settings.DEBUG,          # Log SQL in debug mode
)

# ── Session Factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ── ORM Base ──────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """All ORM models inherit from this base."""
    pass


# ── FastAPI Dependency ────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    Yields a SQLAlchemy session per request and guarantees it is closed
    afterwards, even on exceptions.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    """Create all tables defined in ORM models. Called at startup."""
    # Import models here to register them with Base.metadata
    from app.models import ledger  # noqa: F401
    from app.models import periods  # noqa: F401
    from app.models import invoicing  # noqa: F401
    from app.models import banking  # noqa: F401
    from app.models import fx  # noqa: F401
    from app.models import assets  # noqa: F401
    Base.metadata.create_all(bind=engine)


def ping_db() -> bool:
    """Health check – returns True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
