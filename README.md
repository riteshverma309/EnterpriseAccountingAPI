# Enterprise Accounting API

Enterprise-grade double-entry accounting engine built with FastAPI, SQLAlchemy, and PostgreSQL.

## Quick Start

```bash
# 1. Create .env from template
cp .env.example .env

# 2. Start PostgreSQL + pgAdmin
docker compose up -d

# 3. Activate virtualenv and install dependencies
source venv/bin/activate
pip install -r requirements.txt

# 4. Start the API server (creates DB tables automatically on startup)
uvicorn app.main:app --reload

# 5. Open API docs
# http://localhost:8000/docs
# http://localhost:5050 (pgAdmin — admin@accounting.local / admin123)
```

## Running Tests

```bash
# Ensure PostgreSQL test DB exists first:
# CREATE DATABASE enterprise_accounting_test;

source venv/bin/activate
pytest tests/ -v
```

## Architecture

```
app/
├── core/
│   ├── config.py        # Pydantic-settings (env vars / .env)
│   └── database.py      # SQLAlchemy engine, SessionLocal, Base
├── models/
│   └── ledger.py        # ORM: Tenant, Account, JournalEntry, JournalLine
├── schemas/
│   └── ledger.py        # Pydantic v2 DTOs with double-entry validator
├── services/
│   ├── ledger_service.py    # Core engine: SELECT FOR UPDATE, balance updates
│   └── reporting_service.py # Trial balance, balance sheet, statutory reports
├── plugins/
│   ├── base.py          # ABCs: TaxPlugin, CurrencyPlugin, LocalizationPlugin
│   ├── us_gaap.py       # US GAAP + Sales Tax + USD FX
│   ├── eu_ifrs.py       # EU IFRS + VAT + ECB FX
│   └── in_gst.py        # India GST (CGST/SGST/IGST) + RBI FX + GSTR-1
└── api/v1/
    ├── tenants.py        # POST/GET /api/v1/tenants/
    ├── accounts.py       # POST/GET /api/v1/accounts/
    ├── journal_entries.py # POST/GET /api/v1/journal-entries/ + /reverse
    └── reports.py        # GET /api/v1/reports/trial-balance|balance-sheet|statutory
```

## Key Design Decisions

| Concern | Approach |
|---|---|
| Double-entry | Schema `model_validator` + service layer guard |
| Immutability | Entries never deleted; reversal entries negate originals |
| Concurrency | `SELECT ... FOR UPDATE` on Account rows per transaction |
| Multi-tenancy | All entities scoped by `tenant_id` with FK enforcement |
| Plugin system | `LocalizationPlugin` ABC + `PluginRegistry` singleton |
| Test isolation | Each test rolls back via SQLAlchemy SAVEPOINT |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | System health + plugin list |
| POST | `/api/v1/tenants/` | Create tenant |
| GET | `/api/v1/tenants/` | List tenants |
| POST | `/api/v1/accounts/` | Create account |
| GET | `/api/v1/accounts/tenant/{id}` | List CoA for tenant |
| POST | `/api/v1/journal-entries/?plugin_id=in_gst` | Post journal entry |
| POST | `/api/v1/journal-entries/{id}/reverse` | Reverse entry |
| GET | `/api/v1/reports/trial-balance/{tenant_id}` | Trial balance |
| GET | `/api/v1/reports/balance-sheet/{tenant_id}` | Balance sheet |
| GET | `/api/v1/reports/statutory/{tenant_id}/{plugin_id}` | Statutory report |

## Localization Plugins

| Plugin ID | Standard | Tax | FX | Report |
|---|---|---|---|---|
| `us_gaap` | US GAAP | Sales Tax (state-level) | USD rates | 10-K stub |
| `eu_ifrs` | EU IFRS | VAT (per-country, reverse charge) | ECB rates | IAS-1 stub |
| `in_gst` | India GST | CGST/SGST/IGST/Export | RBI rates | GSTR-1 stub |
