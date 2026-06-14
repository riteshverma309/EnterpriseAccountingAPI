"""
tests/test_plugins.py
Plugin architecture tests.

Agent: PluginTestAgent
Covers:
- PluginRegistry registration and lookup
- US GAAP: sales tax computation, FX conversion
- EU IFRS: VAT computation (intra-state, reverse charge), ECB FX
- India GST: CGST+SGST (intra-state), IGST (inter-state), export zero-rating
- Plugin pre-post hook enriches journal entry metadata
- Invalid plugin_id returns 400
- Statutory report generation via API
"""
from __future__ import annotations

import json
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from app.plugins.base import PluginContext, PluginRegistry


# ════════════════════════════════════════════════════════════════════════════
# T100 — PluginRegistry
# ════════════════════════════════════════════════════════════════════════════

class TestPluginRegistry:
    def test_all_three_plugins_registered(self):
        """T100a: All three localization plugins are registered at startup."""
        registered = PluginRegistry.list_all()
        assert "us_gaap" in registered
        assert "eu_ifrs" in registered
        assert "in_gst" in registered

    def test_get_plugin_by_id(self):
        """T100b: Registered plugins can be retrieved by ID."""
        plugin = PluginRegistry.get("us_gaap")
        assert plugin is not None
        assert plugin.plugin_id == "us_gaap"

    def test_get_unknown_plugin_returns_none(self):
        """T100c: Unknown plugin ID returns None (not exception)."""
        assert PluginRegistry.get("nonexistent_plugin") is None

    def test_get_or_raise_raises_for_unknown(self):
        """T100d: get_or_raise raises KeyError for unknown plugin."""
        with pytest.raises(KeyError, match="not found"):
            PluginRegistry.get_or_raise("totally_unknown")


# ════════════════════════════════════════════════════════════════════════════
# T101 — US GAAP Plugin
# ════════════════════════════════════════════════════════════════════════════

class TestUSGAAPPlugin:
    def _make_context(self, state: str = "CA") -> PluginContext:
        return PluginContext(
            tenant_id="test-tenant",
            base_currency="USD",
            entry_currency="USD",
            description="Software subscription",
            reference_id="INV-001",
            lines=[
                {"account_id": "acc-1", "amount": "1000.00", "description": "SaaS fee"},
            ],
            plugin_metadata={"state": state},
        )

    def test_us_gaap_plugin_display_name(self):
        plugin = PluginRegistry.get("us_gaap")
        assert "United States" in plugin.display_name or "GAAP" in plugin.display_name

    def test_sales_tax_california(self):
        """T101a: California sales tax = 7.25%."""
        plugin = PluginRegistry.get("us_gaap")
        ctx = self._make_context("CA")
        results = plugin.tax_plugin.compute_tax(ctx)
        assert len(results) == 1
        assert results[0].tax_code == "US_SALES_TAX_CA"
        assert results[0].tax_rate == Decimal("0.0725")
        expected = (Decimal("1000.00") * Decimal("0.0725")).quantize(Decimal("0.0001"))
        assert results[0].tax_amount == expected

    def test_sales_tax_new_york(self):
        """T101b: New York sales tax = 8%."""
        plugin = PluginRegistry.get("us_gaap")
        ctx = self._make_context("NY")
        results = plugin.tax_plugin.compute_tax(ctx)
        assert results[0].tax_rate == Decimal("0.08")

    def test_sales_tax_credit_lines_not_taxed(self):
        """T101c: Credit lines (negative amounts) are not taxed."""
        plugin = PluginRegistry.get("us_gaap")
        ctx = PluginContext(
            tenant_id="t",
            base_currency="USD",
            entry_currency="USD",
            description="Credit note",
            reference_id=None,
            lines=[{"account_id": "acc-1", "amount": "-500.00", "description": "Credit"}],
            plugin_metadata={"state": "TX"},
        )
        results = plugin.tax_plugin.compute_tax(ctx)
        assert results == []

    def test_usd_fx_same_currency(self):
        """T101d: USD→USD conversion returns rate=1.0."""
        plugin = PluginRegistry.get("us_gaap")
        rate = plugin.currency_plugin.get_rate("USD", "USD")
        assert rate == Decimal("1.000000")

    def test_usd_fx_usd_to_eur(self):
        """T101e: USD→EUR conversion uses defined rate."""
        plugin = PluginRegistry.get("us_gaap")
        result = plugin.currency_plugin.convert(Decimal("100"), "USD", "EUR")
        assert result.converted_amount == (Decimal("100") * Decimal("0.92")).quantize(Decimal("0.0001"))

    def test_usd_fx_unsupported_pair_raises(self):
        """T101f: Unsupported FX pair raises LookupError."""
        plugin = PluginRegistry.get("us_gaap")
        with pytest.raises(LookupError):
            plugin.currency_plugin.get_rate("USD", "JPY")

    def test_pre_post_hook_enriches_metadata(self):
        """T101g: on_pre_post enriches context with tax results."""
        plugin = PluginRegistry.get("us_gaap")
        ctx = self._make_context("TX")
        enriched = plugin.on_pre_post(ctx)
        assert "us_tax_results" in enriched.plugin_metadata
        assert len(enriched.plugin_metadata["us_tax_results"]) > 0


# ════════════════════════════════════════════════════════════════════════════
# T102 — EU IFRS Plugin
# ════════════════════════════════════════════════════════════════════════════

class TestEUIFRSPlugin:
    def _make_context(self, country: str = "DE", **kwargs) -> PluginContext:
        metadata = {"country_code": country}
        metadata.update(kwargs)
        return PluginContext(
            tenant_id="test-tenant",
            base_currency="EUR",
            entry_currency="EUR",
            description="Consulting services",
            reference_id="INV-EU-001",
            lines=[
                {"account_id": "acc-2", "amount": "5000.00", "description": "Consulting"},
            ],
            plugin_metadata=metadata,
        )

    def test_eu_ifrs_registered(self):
        assert PluginRegistry.get("eu_ifrs") is not None

    def test_vat_germany_19_percent(self):
        """T102a: German VAT = 19%."""
        plugin = PluginRegistry.get("eu_ifrs")
        ctx = self._make_context("DE")
        results = plugin.tax_plugin.compute_tax(ctx)
        assert results[0].tax_code == "EU_VAT_DE"
        assert results[0].tax_rate == Decimal("0.19")

    def test_vat_sweden_25_percent(self):
        """T102b: Swedish VAT = 25%."""
        plugin = PluginRegistry.get("eu_ifrs")
        ctx = self._make_context("SE")
        results = plugin.tax_plugin.compute_tax(ctx)
        assert results[0].tax_rate == Decimal("0.25")

    def test_intra_eu_b2b_reverse_charge(self):
        """T102c: B2B intra-EU with VAT number results in reverse charge (0%)."""
        plugin = PluginRegistry.get("eu_ifrs")
        ctx = self._make_context(
            "FR",
            vat_number="FR12345678901",
            intra_eu_b2b=True,
        )
        results = plugin.tax_plugin.compute_tax(ctx)
        assert results[0].tax_amount == Decimal("0")
        assert "REVERSE_CHARGE" in results[0].tax_code

    def test_vat_missing_country_raises_on_validate(self):
        """T102d: validate_context raises ValueError if country_code missing."""
        plugin = PluginRegistry.get("eu_ifrs")
        ctx = PluginContext(
            tenant_id="t", base_currency="EUR", entry_currency="EUR",
            description="Test", reference_id=None, lines=[], plugin_metadata={}
        )
        with pytest.raises(ValueError, match="country_code"):
            plugin.tax_plugin.validate_context(ctx)

    def test_ecb_fx_eur_to_usd(self):
        """T102e: EUR→USD conversion returns expected result."""
        plugin = PluginRegistry.get("eu_ifrs")
        result = plugin.currency_plugin.convert(Decimal("1000"), "EUR", "USD")
        assert result.converted_amount == (Decimal("1000") * Decimal("1.087")).quantize(Decimal("0.0001"))

    def test_pre_post_hook_requires_country_code(self):
        """T102f: pre-post hook raises if country_code missing."""
        plugin = PluginRegistry.get("eu_ifrs")
        ctx = PluginContext(
            tenant_id="t", base_currency="EUR", entry_currency="EUR",
            description="Test", reference_id=None, lines=[], plugin_metadata={}
        )
        with pytest.raises(ValueError):
            plugin.on_pre_post(ctx)


# ════════════════════════════════════════════════════════════════════════════
# T103 — India GST Plugin
# ════════════════════════════════════════════════════════════════════════════

class TestIndiaGSTPlugin:
    def _make_context(self, inter_state: bool = False, is_export: bool = False) -> PluginContext:
        return PluginContext(
            tenant_id="test-tenant",
            base_currency="INR",
            entry_currency="INR",
            description="Software services",
            reference_id="INV-IN-001",
            lines=[
                {"account_id": "acc-3", "amount": "100000.00", "description": "Dev services"},
            ],
            plugin_metadata={
                "gstin": "29ABCDE1234F1Z5",
                "gst_slab": "GST_18",
                "inter_state": inter_state,
                "is_export": is_export,
            },
        )

    def test_india_gst_registered(self):
        assert PluginRegistry.get("in_gst") is not None

    def test_intra_state_gst_splits_cgst_sgst(self):
        """T103a: Intra-state GST 18% splits into CGST 9% + SGST 9%."""
        plugin = PluginRegistry.get("in_gst")
        ctx = self._make_context(inter_state=False)
        results = plugin.tax_plugin.compute_tax(ctx)
        codes = {r.tax_code for r in results}
        assert "CGST_GST_18" in codes
        assert "SGST_GST_18" in codes
        assert "IGST_GST_18" not in codes
        # Each half = 9%
        for r in results:
            assert r.tax_rate == Decimal("0.09")

    def test_inter_state_gst_uses_igst(self):
        """T103b: Inter-state GST 18% is applied as single IGST."""
        plugin = PluginRegistry.get("in_gst")
        ctx = self._make_context(inter_state=True)
        results = plugin.tax_plugin.compute_tax(ctx)
        codes = {r.tax_code for r in results}
        assert "IGST_GST_18" in codes
        assert "CGST_GST_18" not in codes
        assert results[0].tax_rate == Decimal("0.18")

    def test_export_is_zero_rated(self):
        """T103c: Exports are zero-rated."""
        plugin = PluginRegistry.get("in_gst")
        ctx = self._make_context(is_export=True)
        results = plugin.tax_plugin.compute_tax(ctx)
        assert results[0].tax_amount == Decimal("0")
        assert "ZERO_RATED" in results[0].tax_code

    def test_gst_total_amount_correct(self):
        """T103d: Total CGST+SGST = 18% of taxable amount."""
        plugin = PluginRegistry.get("in_gst")
        ctx = self._make_context()
        results = plugin.tax_plugin.compute_tax(ctx)
        total_tax = sum(r.tax_amount for r in results)
        expected = (Decimal("100000.00") * Decimal("0.18")).quantize(Decimal("0.0001"))
        assert total_tax == expected

    def test_gst_missing_gstin_raises_on_validate(self):
        """T103e: Missing GSTIN raises ValueError."""
        plugin = PluginRegistry.get("in_gst")
        ctx = PluginContext(
            tenant_id="t", base_currency="INR", entry_currency="INR",
            description="Test", reference_id=None, lines=[],
            plugin_metadata={"gst_slab": "GST_18"}  # no gstin
        )
        with pytest.raises(ValueError, match="gstin"):
            plugin.tax_plugin.validate_context(ctx)

    def test_gst_invalid_slab_raises(self):
        """T103f: Invalid GST slab raises ValueError."""
        plugin = PluginRegistry.get("in_gst")
        ctx = PluginContext(
            tenant_id="t", base_currency="INR", entry_currency="INR",
            description="Test", reference_id=None, lines=[],
            plugin_metadata={"gstin": "29ABCDE1234F1Z5", "gst_slab": "GST_99"}
        )
        with pytest.raises(ValueError, match="slab"):
            plugin.tax_plugin.validate_context(ctx)

    def test_inr_fx_inr_to_usd(self):
        """T103g: INR→USD FX conversion."""
        plugin = PluginRegistry.get("in_gst")
        result = plugin.currency_plugin.convert(Decimal("8350"), "INR", "USD")
        expected = (Decimal("8350") * Decimal("0.01197")).quantize(Decimal("0.0001"))
        assert result.converted_amount == expected

    def test_pre_post_hook_adds_gst_breakdown(self):
        """T103h: on_pre_post enriches context with gst_breakdown metadata."""
        plugin = PluginRegistry.get("in_gst")
        ctx = self._make_context()
        enriched = plugin.on_pre_post(ctx)
        assert "gst_breakdown" in enriched.plugin_metadata
        bd = enriched.plugin_metadata["gst_breakdown"]
        assert "cgst" in bd
        assert "sgst" in bd
        assert "igst" in bd
        assert "total_gst" in bd


# ════════════════════════════════════════════════════════════════════════════
# T104 — Plugin Integration via HTTP API
# ════════════════════════════════════════════════════════════════════════════

class TestPluginHTTPIntegration:
    def test_journal_entry_with_in_gst_plugin(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T104a: Posting with plugin_id=in_gst enriches entry with GST metadata."""
        resp = client.post(
            "/api/v1/journal-entries/?plugin_id=in_gst",
            json={
                "tenant_id": sample_tenant["id"],
                "description": "GST service invoice",
                "currency": "INR",
                "plugin_metadata": json.dumps({
                    "gstin": "29ABCDE1234F1Z5",
                    "gst_slab": "GST_18",
                    "inter_state": False,
                }),
                "lines": [
                    {"account_id": sample_accounts["1010"]["id"], "amount": "118000.00"},
                    {"account_id": sample_accounts["4000"]["id"], "amount": "-118000.00"},
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["plugin_metadata"] is not None
        meta = json.loads(data["plugin_metadata"])
        assert "gst_breakdown" in meta

    def test_journal_entry_with_us_gaap_plugin(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T104b: Posting with plugin_id=us_gaap enriches entry with tax metadata."""
        resp = client.post(
            "/api/v1/journal-entries/?plugin_id=us_gaap",
            json={
                "tenant_id": sample_tenant["id"],
                "description": "US software sale",
                "currency": "USD",
                "plugin_metadata": json.dumps({"state": "NY"}),
                "lines": [
                    {"account_id": sample_accounts["1010"]["id"], "amount": "1000.00"},
                    {"account_id": sample_accounts["4000"]["id"], "amount": "-1000.00"},
                ],
            },
        )
        assert resp.status_code == 201
        meta = json.loads(resp.json()["plugin_metadata"])
        assert "us_tax_results" in meta

    def test_invalid_plugin_id_returns_400(
        self, client: TestClient, sample_tenant: dict, sample_accounts: dict
    ):
        """T104c: Posting with an unknown plugin_id returns 400."""
        resp = client.post(
            "/api/v1/journal-entries/?plugin_id=nonexistent_plugin",
            json={
                "tenant_id": sample_tenant["id"],
                "description": "Unknown plugin",
                "currency": "USD",
                "lines": [
                    {"account_id": sample_accounts["1010"]["id"], "amount": "50.00"},
                    {"account_id": sample_accounts["4000"]["id"], "amount": "-50.00"},
                ],
            },
        )
        assert resp.status_code == 400

    def test_statutory_report_us_gaap(
        self, client: TestClient, sample_tenant: dict
    ):
        """T104d: Statutory report endpoint returns report for us_gaap plugin."""
        tid = sample_tenant["id"]
        resp = client.get(
            f"/api/v1/reports/statutory/{tid}/us_gaap"
            f"?period_start=2026-01-01&period_end=2026-12-31"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "report" in data
        assert "US GAAP" in data.get("standard", "") or "GAAP" in data.get("report", "")

    def test_statutory_report_in_gst(
        self, client: TestClient, sample_tenant: dict
    ):
        """T104e: Statutory report endpoint returns GSTR-1 for in_gst plugin."""
        tid = sample_tenant["id"]
        resp = client.get(
            f"/api/v1/reports/statutory/{tid}/in_gst"
            f"?period_start=2026-04-01&period_end=2026-06-30"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "GSTR" in data.get("report", "") or "GST" in data.get("standard", "")
