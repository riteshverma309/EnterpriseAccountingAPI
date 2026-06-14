"""
app/plugins/us_gaap.py
US GAAP Localization Plugin.

Covers:
- Simple US Sales Tax computation (state-level flat rate example).
- USD-based currency passthrough (no conversion needed for domestic).
- Stub for 10-K / GAAP statutory report generation.

Register by importing this module; the plugin self-registers on load.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.plugins.base import (
    CurrencyPlugin,
    FxConversionResult,
    LocalizationPlugin,
    PluginContext,
    PluginRegistry,
    StatutoryReportPlugin,
    TaxPlugin,
    TaxResult,
)


# ── US Sales Tax Plugin ───────────────────────────────────────────────────────

class USSalesTaxPlugin(TaxPlugin):
    """
    Simplified US state sales tax computation.
    In production this would integrate with TaxJar or Avalara.
    """

    # Default: California 8.25%
    DEFAULT_RATE = Decimal("0.0825")
    STATE_RATES: Dict[str, Decimal] = {
        "CA": Decimal("0.0725"),
        "NY": Decimal("0.08"),
        "TX": Decimal("0.0625"),
        "WA": Decimal("0.065"),
        "FL": Decimal("0.06"),
    }

    @property
    def plugin_id(self) -> str:
        return "us_sales_tax"

    @property
    def jurisdiction(self) -> str:
        return "United States"

    def compute_tax(self, context: PluginContext) -> List[TaxResult]:
        state = context.plugin_metadata.get("state", "CA")
        rate = self.STATE_RATES.get(state.upper(), self.DEFAULT_RATE)

        results = []
        for line in context.lines:
            amount = Decimal(str(line["amount"]))
            if amount <= 0:
                continue  # Only tax debit (expense) lines
            tax = (amount * rate).quantize(Decimal("0.0001"))
            results.append(
                TaxResult(
                    tax_code=f"US_SALES_TAX_{state.upper()}",
                    tax_rate=rate,
                    taxable_amount=amount,
                    tax_amount=tax,
                    metadata={"state": state.upper(), "account_id": line["account_id"]},
                )
            )
        return results


# ── USD Currency Passthrough ──────────────────────────────────────────────────

class USDCurrencyPlugin(CurrencyPlugin):
    """
    USD currency plugin — passthrough for domestic USD transactions.
    For cross-border FX, a real implementation would call a rate API.
    """

    # Hardcoded demo rates — replace with live API in production
    _RATES: Dict[str, Decimal] = {
        "USD_EUR": Decimal("0.92"),
        "USD_GBP": Decimal("0.79"),
        "USD_INR": Decimal("83.50"),
        "EUR_USD": Decimal("1.087"),
        "GBP_USD": Decimal("1.265"),
        "INR_USD": Decimal("0.01197"),
    }

    @property
    def plugin_id(self) -> str:
        return "usd_fx"

    def get_rate(self, source: str, target: str) -> Decimal:
        if source == target:
            return Decimal("1.000000")
        key = f"{source.upper()}_{target.upper()}"
        if key not in self._RATES:
            raise LookupError(f"FX pair {key!r} not supported by USDCurrencyPlugin.")
        return self._RATES[key]

    def convert(self, amount: Decimal, source: str, target: str) -> FxConversionResult:
        rate = self.get_rate(source, target)
        converted = (amount * rate).quantize(Decimal("0.0001"))
        return FxConversionResult(
            source_currency=source,
            target_currency=target,
            source_amount=amount,
            converted_amount=converted,
            exchange_rate=rate,
            rate_source="hardcoded_demo",
        )


# ── GAAP Statutory Report Plugin ──────────────────────────────────────────────

class GAAPStatutoryReportPlugin(StatutoryReportPlugin):
    """Generates a simplified GAAP Balance Sheet / Trial Balance stub."""

    @property
    def plugin_id(self) -> str:
        return "us_gaap_report"

    @property
    def report_name(self) -> str:
        return "US GAAP Financial Statements"

    def generate(
        self,
        tenant_id: str,
        period_start: str,
        period_end: str,
        db_session: Any,
    ) -> Dict[str, Any]:
        # In production: query journal_entries & lines filtered by date range
        return {
            "report": self.report_name,
            "standard": "US GAAP (ASC 810)",
            "tenant_id": tenant_id,
            "period": {"start": period_start, "end": period_end},
            "status": "stub — implement full P&L and BS queries here",
        }


# ── Composite US GAAP Localization Plugin ─────────────────────────────────────

class USGAAPPlugin(LocalizationPlugin):
    """
    Composite US GAAP localization plugin.
    Bundles sales tax, USD FX, and GAAP reporting.
    """

    _tax = USSalesTaxPlugin()
    _currency = USDCurrencyPlugin()
    _report = GAAPStatutoryReportPlugin()

    @property
    def plugin_id(self) -> str:
        return "us_gaap"

    @property
    def display_name(self) -> str:
        return "United States — GAAP"

    @property
    def tax_plugin(self) -> Optional[TaxPlugin]:
        return self._tax

    @property
    def currency_plugin(self) -> Optional[CurrencyPlugin]:
        return self._currency

    @property
    def statutory_report_plugin(self) -> Optional[StatutoryReportPlugin]:
        return self._report

    def on_pre_post(self, context: PluginContext) -> PluginContext:
        """Enrich context with computed tax metadata before posting."""
        tax_results = self._tax.compute_tax(context)
        context.plugin_metadata["us_tax_results"] = [
            {
                "tax_code": r.tax_code,
                "tax_rate": str(r.tax_rate),
                "taxable_amount": str(r.taxable_amount),
                "tax_amount": str(r.tax_amount),
            }
            for r in tax_results
        ]
        return context


# ── Auto-register ─────────────────────────────────────────────────────────────
PluginRegistry.register(USGAAPPlugin())
