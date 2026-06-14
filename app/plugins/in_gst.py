"""
app/plugins/in_gst.py
Indian GST Localization Plugin.

Covers:
- GST computation: CGST + SGST (intra-state) or IGST (inter-state).
- Rates: 0%, 5%, 12%, 18%, 28% slabs.
- RBI-reference INR FX conversion.
- GSTR-1 statutory report stub.

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


# ── GST Slabs ─────────────────────────────────────────────────────────────────

GST_SLABS: Dict[str, Decimal] = {
    "EXEMPT": Decimal("0.00"),
    "GST_0":  Decimal("0.00"),
    "GST_5":  Decimal("0.05"),
    "GST_12": Decimal("0.12"),
    "GST_18": Decimal("0.18"),   # Most IT services
    "GST_28": Decimal("0.28"),   # Luxury / demerit goods
}


# ── Indian GST Tax Plugin ─────────────────────────────────────────────────────

class IndianGSTPlugin(TaxPlugin):
    """
    Indian GST computation engine.

    Intra-state: splits equally into CGST + SGST.
    Inter-state (or export): single IGST.
    Input Tax Credit (ITC) flagging is supported via metadata.
    """

    @property
    def plugin_id(self) -> str:
        return "in_gst_tax"

    @property
    def jurisdiction(self) -> str:
        return "India"

    def validate_context(self, context: PluginContext) -> None:
        if not context.plugin_metadata.get("gstin"):
            raise ValueError(
                "Indian GST plugin requires 'gstin' (GST Identification Number) "
                "in plugin_metadata."
            )
        slab = context.plugin_metadata.get("gst_slab", "GST_18")
        if slab not in GST_SLABS:
            raise ValueError(
                f"Invalid GST slab {slab!r}. Valid options: {list(GST_SLABS.keys())}"
            )

    def compute_tax(self, context: PluginContext) -> List[TaxResult]:
        slab = context.plugin_metadata.get("gst_slab", "GST_18")
        rate = GST_SLABS.get(slab, Decimal("0.18"))
        inter_state: bool = context.plugin_metadata.get("inter_state", False)
        gstin: str = context.plugin_metadata.get("gstin", "")
        is_export: bool = context.plugin_metadata.get("is_export", False)

        results: List[TaxResult] = []

        for line in context.lines:
            amount = Decimal(str(line["amount"]))
            if amount <= 0:
                continue  # Only tax debit (revenue/expense) lines

            total_tax = (amount * rate).quantize(Decimal("0.0001"))

            if is_export:
                # Zero-rated exports — no GST but record for GSTR-1
                results.append(
                    TaxResult(
                        tax_code="GST_ZERO_RATED_EXPORT",
                        tax_rate=Decimal("0"),
                        taxable_amount=amount,
                        tax_amount=Decimal("0"),
                        metadata={
                            "gstin": gstin,
                            "slab": slab,
                            "type": "EXPORT",
                            "account_id": line["account_id"],
                        },
                    )
                )
            elif inter_state:
                # IGST — single integrated tax
                results.append(
                    TaxResult(
                        tax_code=f"IGST_{slab}",
                        tax_rate=rate,
                        taxable_amount=amount,
                        tax_amount=total_tax,
                        metadata={
                            "gstin": gstin,
                            "slab": slab,
                            "type": "IGST",
                            "account_id": line["account_id"],
                        },
                    )
                )
            else:
                # Intra-state — split 50/50 CGST + SGST
                half_rate = (rate / 2).quantize(Decimal("0.0001"))
                half_tax = (total_tax / 2).quantize(Decimal("0.0001"))
                results.append(
                    TaxResult(
                        tax_code=f"CGST_{slab}",
                        tax_rate=half_rate,
                        taxable_amount=amount,
                        tax_amount=half_tax,
                        metadata={
                            "gstin": gstin,
                            "slab": slab,
                            "type": "CGST",
                            "account_id": line["account_id"],
                        },
                    )
                )
                results.append(
                    TaxResult(
                        tax_code=f"SGST_{slab}",
                        tax_rate=half_rate,
                        taxable_amount=amount,
                        tax_amount=half_tax,
                        metadata={
                            "gstin": gstin,
                            "slab": slab,
                            "type": "SGST",
                            "account_id": line["account_id"],
                        },
                    )
                )

        return results


# ── INR FX Plugin ─────────────────────────────────────────────────────────────

class INRFXPlugin(CurrencyPlugin):
    """
    RBI-reference rate plugin for INR.
    Demo rates only — replace with RBI FBIL rate API in production.
    """

    _RATES: Dict[str, Decimal] = {
        "INR_USD": Decimal("0.01197"),
        "INR_EUR": Decimal("0.01102"),
        "INR_GBP": Decimal("0.00944"),
        "USD_INR": Decimal("83.50"),
        "EUR_INR": Decimal("90.75"),
        "GBP_INR": Decimal("105.90"),
    }

    @property
    def plugin_id(self) -> str:
        return "rbi_fx"

    def get_rate(self, source: str, target: str) -> Decimal:
        if source == target:
            return Decimal("1.000000")
        key = f"{source.upper()}_{target.upper()}"
        if key not in self._RATES:
            raise LookupError(
                f"RBI FX pair {key!r} not supported. "
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
            rate_source="RBI_FBIL_demo",
        )


# ── GSTR-1 Statutory Report Plugin ────────────────────────────────────────────

class GSTR1ReportPlugin(StatutoryReportPlugin):
    """Generates a GSTR-1 (Outward Supplies) stub for Indian GST compliance."""

    @property
    def plugin_id(self) -> str:
        return "in_gstr1"

    @property
    def report_name(self) -> str:
        return "GSTR-1 Outward Supplies Statement"

    def generate(
        self,
        tenant_id: str,
        period_start: str,
        period_end: str,
        db_session: Any,
    ) -> Dict[str, Any]:
        # In production: query journal lines with GST metadata filtered by period
        return {
            "report": self.report_name,
            "standard": "GST Act 2017 (India)",
            "tenant_id": tenant_id,
            "period": {"start": period_start, "end": period_end},
            "sections": {
                "B2B": [],         # Business-to-business supplies
                "B2C_LARGE": [],   # B2C above ₹2.5L inter-state
                "B2C_SMALL": [],   # B2C small
                "EXPORT": [],      # Zero-rated exports
                "NIL_EXEMPT": [],  # Nil-rated / exempted supplies
            },
            "status": "stub — implement GSTIN-filtered journal query here",
        }


# ── Composite Indian GST Localization Plugin ──────────────────────────────────

class IndianGSTLocalizationPlugin(LocalizationPlugin):
    """India GST composite plugin: CGST/SGST/IGST tax, RBI FX, GSTR-1 reporting."""

    _tax = IndianGSTPlugin()
    _currency = INRFXPlugin()
    _report = GSTR1ReportPlugin()

    @property
    def plugin_id(self) -> str:
        return "in_gst"

    @property
    def display_name(self) -> str:
        return "India — GST"

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
        """Validate GSTIN and enrich context with GST breakdown metadata."""
        self._tax.validate_context(context)
        tax_results = self._tax.compute_tax(context)

        cgst = sum(r.tax_amount for r in tax_results if "CGST" in r.tax_code)
        sgst = sum(r.tax_amount for r in tax_results if "SGST" in r.tax_code)
        igst = sum(r.tax_amount for r in tax_results if "IGST" in r.tax_code)

        context.plugin_metadata["gst_breakdown"] = {
            "cgst": str(cgst),
            "sgst": str(sgst),
            "igst": str(igst),
            "total_gst": str(cgst + sgst + igst),
            "slab": context.plugin_metadata.get("gst_slab", "GST_18"),
            "gstin": context.plugin_metadata.get("gstin"),
        }
        context.plugin_metadata["gst_line_results"] = [
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
PluginRegistry.register(IndianGSTLocalizationPlugin())
