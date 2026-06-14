"""
tests/conftest.py
Pytest fixtures for the Enterprise Accounting API test suite.

Strategy:
- Uses a SEPARATE test database (TEST_DATABASE_URL from config).
- Creates all tables before each test session and drops them after.
- Each test runs in a rolled-back transaction (no persistent state leakage).
- Provides a TestClient for HTTP-level endpoint tests.
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.api.deps import get_db_session

# ── Test Engine ───────────────────────────────────────────────────────────────
TEST_ENGINE = create_engine(
    settings.TEST_DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


# ── Session-scoped: create/drop tables once per test run ─────────────────────
@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables in the test DB before the test session starts."""
    # Import models to register them with Base.metadata
    from app.models import ledger  # noqa: F401
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


# ── Function-scoped: each test gets a clean, rolled-back transaction ──────────
@pytest.fixture()
def db() -> Session:
    """
    Provides a SQLAlchemy Session that wraps each test in a SAVEPOINT.
    The transaction is always rolled back after the test — zero state leakage.
    """
    connection = TEST_ENGINE.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    # Begin a nested SAVEPOINT so rollback only undoes test-specific changes
    nested = connection.begin_nested()

    yield session

    session.close()
    # Roll back to the savepoint — the test DB is unchanged
    if nested.is_active:
        nested.rollback()
    transaction.rollback()
    connection.close()


# ── TestClient (HTTP-level tests) ─────────────────────────────────────────────
@pytest.fixture()
def client(db: Session) -> TestClient:
    """
    Provides a FastAPI TestClient with the DB session overridden
    to use the same rolled-back transaction as the `db` fixture.
    """
    def override_get_db():
        yield db

    app.dependency_overrides[get_db_session] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Reusable Data Fixtures ────────────────────────────────────────────────────
@pytest.fixture()
def sample_tenant(client: TestClient) -> dict:
    """Creates and returns a sample tenant via the API."""
    resp = client.post("/api/v1/tenants/", json={
        "name": "Test Corp",
        "base_currency": "USD",
        "fiscal_year_start_month": 1,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def sample_accounts(client: TestClient, sample_tenant: dict) -> dict:
    """
    Creates a minimal Chart of Accounts for double-entry tests:
    - 1010: Cash (ASSET)
    - 4000: Revenue (REVENUE)
    - 5000: Expense (EXPENSE)
    - 2000: Accounts Payable (LIABILITY)
    - 3000: Retained Earnings (EQUITY)
    """
    tenant_id = sample_tenant["id"]
    accounts = {}
    specs = [
        ("1010", "Cash and Equivalents", "ASSET"),
        ("2000", "Accounts Payable", "LIABILITY"),
        ("3000", "Retained Earnings", "EQUITY"),
        ("4000", "Revenue", "REVENUE"),
        ("5000", "Operating Expenses", "EXPENSE"),
    ]
    for code, name, atype in specs:
        resp = client.post("/api/v1/accounts/", json={
            "tenant_id": tenant_id,
            "code": code,
            "name": name,
            "account_type": atype,
            "currency": "USD",
        })
        assert resp.status_code == 201, f"Failed to create account {code}: {resp.text}"
        accounts[code] = resp.json()
    return accounts
