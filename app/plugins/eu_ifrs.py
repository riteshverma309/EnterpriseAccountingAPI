"""
app/plugins/eu_ifrs.py
EU IFRS Localization Plugin.

Covers:
- EU VAT computation (standard 20% with reduced rates).
- EUR-based FX conversion (ECB-style rates, hardcoded for demo).
- IAS-1 / IFRS statutory report stub.

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


# ── EU VAT Plugin ─────────────────────────────────────────────────────────────

class EUVATPlugin(TaxPlugin):
    """
    EU VAT computation per country.
    Standard rates from EU Commission directive (2024).
    Reduced rates for essential goods are not modelled here.
    """

    # Standard VAT rates by ISO country code
    COUNTRY_RATES: Dict[str, Decimal] = {
        "DE": Decimal("0.19"),   # Germany
        "FR": Decimal("0.20"),   # France
        "IT": Decimal("0.22"),   # Italy
        "ES": Decimal("0.21"),   # Spain
        "NL": Decimal("0.21"),   # Netherlands
        "BE": Decimal("0.21"),   # Belgium
        "PL": Decimal("0.23"),   # Poland
        "SE": Decimal("0.25"),   # Sweden
        "DK": Decimal("0.25"),   # Denmark
        "IE": Decimal("0.23"),   # Ireland
    }
    DEFAULT_RATE = Decimal("0.20")  # EU default

    @property
    def plugin_id(self) -> str:
        return "eu_vat"

    @property
    def jurisdiction(self) -> str:
        return "European Union"

    def compute_tax(self, context: PluginContext) -> List[TaxResult]:
        country = context.plugin_metadata.get("country_code", "DE")
        rate = self.COUNTRY_RATES.get(country.upper(), self.DEFAULT_RATE)
        vat_number = context.plugin_metadata.get("vat_number")

        # B2B intra-EU: reverse charge — zero VAT if valid VAT number provided
        if vat_number and context.plugin_metadata.get("intra_eu_b2b"):
            return [
                TaxResult(
                    tax_code=f"EU_VAT_REVERSE_CHARGE_{country.upper()}",
                    tax_rate=Decimal("0"),
                    taxable_amount=Decimal("0"),
                    tax_amount=Decimal("0"),
                    metadata={"mechanism": "reverse_charge", "vat_number": vat_number},
                )
            ]

        results = []
        for line in context.lines:
            amount = Decimal(str(line["amount"]))
            if amount <= 0:
                continue
            tax = (amount * rate).quantize(Decimal("0.0001"))
            results.append(
                TaxResult(
                    tax_code=f"EU_VAT_{country.upper()}",
                    tax_rate=rate,
                    taxable_amount=amount,
                    tax_amount=tax,
                    metadata={
                        "country": country.upper(),
                        "account_id": line["account_id"],
                        "vat_number": vat_number,
                    },
                )
            )
        return results

    def validate_context(self, context: PluginContext) -> None:
        country = context.plugin_metadata.get("country_code")
        if not country:
            raise ValueError(
                "EU IFRS plugin requires 'country_code' in plugin_metadata "
                "(e.g. 'DE', 'FR', 'IT')."
            )


# ── EUR FX Plugin ─────────────────────────────────────────────────────────────

class EURFXPlugin(CurrencyPlugin):
    """
    ECB-style EUR-based FX plugin.
    Hardcoded demo rates — replace with ECB daily XML feed in production.
    """

    _RATES: Dict[str, Decimal] = {
        "EUR_USD": Decimal("1.087"),
        "EUR_GBP": Decimal("0.856"),
        "EUR_INR": Decimal("90.75"),
        "EUR_JPY": Decimal("161.50"),
        "USD_EUR": Decimal("0.920"),
        "GBP_EUR": Decimal("1.168"),
        "INR_EUR": Decimal("0.01102"),
    }

    @property
    def plugin_id(self) -> str:
        return "ecb_fx"

    def get_rate(self, source: str, target: str) -> Decimal:
        if source == target:
            return Decimal("1.000000")
        key = f"{source.upper()}_{target.upper()}"
        if key not in self._RATES:
            raise LookupError(
                f"ECB FX pair {key!r} not supported. "
                f"Available: {list(self._RATES.keys())}"
            )
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
            rate_source="ECB_demo",
        )


# ── IFRS Statutory Report Plugin ──────────────────────────────────────────────

class IFRSStatutoryReportPlugin(StatutoryReportPlugin):
    """Generates an IAS-1 compliant Statement of Financial Position stub."""

    @property
    def plugin_id(self) -> str:
        return "eu_ifrs_report"

    @property
    def report_name(self) -> str:
        return "IAS-1 Statement of Financial Position (IFRS)"

    def generate(
        self,
        tenant_id: str,
        period_start: str,
        period_end: str,
        db_session: Any,
    ) -> Dict[str, Any]:
        return {
            "report": self.report_name,
            "standard": "IFRS — IAS 1",
            "tenant_id": tenant_id,
            "period": {"start": period_start, "end": period_end},
            "sections": {
                "assets": {"current": {}, "non_current": {}},
                "liabilities": {"current": {}, "non_current": {}},
                "equity": {},
            },
            "status": "stub — implement IFRS classification queries here",
        }


# ── Composite EU IFRS Localization Plugin ─────────────────────────────────────

class EUIFRSPlugin(LocalizationPlugin):
    """EU IFRS composite plugin: VAT, ECB FX, and IAS-1 reporting."""

    _tax = EUVATPlugin()
    _currency = EURFXPlugin()
    _report = IFRSStatutoryReportPlugin()

    @property
    def plugin_id(self) -> str:
        return "eu_ifrs"

    @property
    def display_name(self) -> str:
        return "European Union — IFRS"

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
        self._tax.validate_context(context)
        tax_results = self._tax.compute_tax(context)
        context.plugin_metadata["eu_vat_results"] = [
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
PluginRegistry.register(EUIFRSPlugin())
