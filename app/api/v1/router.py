"""
app/api/v1/router.py
Aggregates all v1 routers into a single APIRouter for inclusion in main.py.
"""
from fastapi import APIRouter

from app.api.v1 import tenants, accounts, journal_entries, reports

api_router = APIRouter()

api_router.include_router(tenants.router)
api_router.include_router(accounts.router)
api_router.include_router(journal_entries.router)
api_router.include_router(reports.router)
