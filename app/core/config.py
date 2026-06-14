"""
app/core/config.py
Application configuration via pydantic-settings.
All values can be overridden via environment variables or a .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Application ─────────────────────────────────────────────────────────
    APP_NAME: str = "EnterpriseAccountingAPI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Primary PostgreSQL Database ──────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql://accounting_user:accounting_pass@localhost:5432/enterprise_accounting"
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── Test Database (used only by pytest) ──────────────────────────────────
    TEST_DATABASE_URL: str = (
        "postgresql://accounting_user:accounting_pass@localhost:5432/enterprise_accounting_test"
    )

    # ── Security ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = "changeme-in-production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — import `settings` everywhere."""
    return Settings()


settings = get_settings()
