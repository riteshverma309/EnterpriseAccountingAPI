"""
app/main.py
Enterprise Accounting API — Application Entry Point.

Wires together:
- FastAPI application with metadata
- Startup/shutdown lifecycle hooks (DB table creation, plugin loading)
- Global exception handlers for accounting-specific errors
- API v1 router
- Plugin auto-registration (import triggers self-registration)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import create_all_tables, ping_db

# ── Configure root logger ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Plugin Auto-Registration (imports trigger PluginRegistry.register()) ──────
# Each module calls PluginRegistry.register() at module level.
import app.plugins.us_gaap  # noqa: F401, E402
import app.plugins.eu_ifrs  # noqa: F401, E402
import app.plugins.in_gst   # noqa: F401, E402


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """
    Startup: create DB tables, verify DB connectivity.
    Shutdown: log clean exit.
    """
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    logger.info("Creating database tables if not exist...")
    try:
        create_all_tables()
        logger.info("Database tables: OK")
    except Exception as db_err:
        logger.error(
            "Database connection FAILED at startup — running in DEGRADED mode. "
            "Check DATABASE_URL in .env and ensure PostgreSQL is running. Error: %s",
            db_err,
        )

    if ping_db():
        logger.info("Database connection: OK")
    else:
        logger.warning(
            "Database unreachable — API is running but all DB endpoints will fail. "
            "Start PostgreSQL and the app will reconnect automatically (pool_pre_ping=True)."
        )

    from app.plugins.base import PluginRegistry
    logger.info("Registered plugins: %s", PluginRegistry.list_all())

    yield  # Application runs

    logger.info("Shutting down %s", settings.APP_NAME)


# ── FastAPI Application ───────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Enterprise-grade double-entry accounting engine.\n\n"
        "**Key Features:**\n"
        "- Strict double-entry (Debits = Credits) enforced at schema and service level\n"
        "- Immutable journal entries with reversal-based corrections\n"
        "- Multi-tenant Chart of Accounts with hierarchical account structure\n"
        "- Multi-currency support with per-line exchange rates\n"
        "- PostgreSQL row-level locking (SELECT FOR UPDATE) for concurrency safety\n"
        "- Plugin architecture: US GAAP, EU IFRS, Indian GST"
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Exception Handlers ─────────────────────────────────────────────────
from app.services.ledger_service import (  # noqa: E402
    UnbalancedLedgerError,
    TenantNotFoundError,
    AccountNotFoundError,
    InactiveAccountError,
    EntryAlreadyReversedError,
)


@app.exception_handler(UnbalancedLedgerError)
async def unbalanced_ledger_handler(request: Request, exc: UnbalancedLedgerError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "UnbalancedLedgerError",
            "message": str(exc),
            "variance": str(exc.variance),
        },
    )


@app.exception_handler(TenantNotFoundError)
async def tenant_not_found_handler(request: Request, exc: TenantNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "TenantNotFoundError", "message": str(exc)},
    )


@app.exception_handler(AccountNotFoundError)
async def account_not_found_handler(request: Request, exc: AccountNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "AccountNotFoundError", "message": str(exc)},
    )


@app.exception_handler(InactiveAccountError)
async def inactive_account_handler(request: Request, exc: InactiveAccountError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "InactiveAccountError", "message": str(exc)},
    )


@app.exception_handler(EntryAlreadyReversedError)
async def already_reversed_handler(request: Request, exc: EntryAlreadyReversedError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "EntryAlreadyReversedError", "message": str(exc)},
    )


# ── Include API Routers ───────────────────────────────────────────────────────
from app.api.v1.router import api_router  # noqa: E402

app.include_router(api_router, prefix="/api/v1")


# ── System Endpoints ──────────────────────────────────────────────────────────
@app.get("/health", tags=["System"], summary="System health check")
async def health_check():
    """Returns operational status and registered plugin list."""
    from app.plugins.base import PluginRegistry
    db_ok = ping_db()
    return {
        "status": "operational" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected" if db_ok else "unreachable",
        "plugins": PluginRegistry.list_all(),
    }


@app.get("/", tags=["System"], summary="API root")
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs": "/docs",
        "version": settings.APP_VERSION,
    }
