"""
app/plugins/base.py
Abstract Base Classes for the localization plugin architecture.

Plugin authors must implement:
  - LocalizationPlugin   : entry point that combines tax + currency + reporting
  - TaxPlugin            : country-specific tax computation
  - CurrencyPlugin       : cross-border FX conversion
  - StatutoryReportPlugin: statutory / regulatory report generation

Plugins are registered via the PluginRegistry singleton and invoked through
middleware hooks at journal-entry post time.
"""
from __future__ import annotations

import abc
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


# ── Data Transfer Objects used by plugins ────────────────────────────────────

@dataclass
class TaxResult:
    """Output of a TaxPlugin computation."""
    tax_code: str                     # e.g. "GST_18", "VAT_20", "US_SALES_TAX"
    tax_rate: Decimal                 # e.g. Decimal("0.18")
    taxable_amount: Decimal
    tax_amount: Decimal
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FxConversionResult:
    """Output of a CurrencyPlugin computation."""
    source_currency: str
    target_currency: str
    source_amount: Decimal
    converted_amount: Decimal
    exchange_rate: Decimal
    rate_source: str = "manual"       # e.g. "ECB", "RBI", "manual"


@dataclass
class PluginContext:
    """
    Shared context object passed to every plugin hook.
    Contains the raw journal entry payload plus tenant metadata.
    """
    tenant_id: str
    base_currency: str
    entry_currency: str
    description: str
    reference_id: Optional[str]
    lines: List[Dict[str, Any]]       # Each: {account_id, amount, description}
    plugin_metadata: Dict[str, Any] = field(default_factory=dict)


# ── Abstract Base Classes ─────────────────────────────────────────────────────

class TaxPlugin(abc.ABC):
    """
    Abstract base for country/jurisdiction-specific tax computation.

    Implementors receive the raw journal entry context and return
    a list of TaxResult objects that the service layer uses to
    populate journal_lines.tax_amount.
    """

    @property
    @abc.abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier, e.g. 'in_gst', 'us_gaap', 'eu_vat'."""

    @property
    @abc.abstractmethod
    def jurisdiction(self) -> str:
        """Human-readable jurisdiction name, e.g. 'India', 'United States'."""

    @abc.abstractmethod
    def compute_tax(self, context: PluginContext) -> List[TaxResult]:
        """
        Compute applicable taxes for the given journal entry context.
        Must NOT mutate the context object.
        Returns an empty list if no tax applies.
        """

    def validate_context(self, context: PluginContext) -> None:
        """
        Optional hook: raise ValueError if the context is invalid
        for this jurisdiction (e.g. missing GST registration number).
        """

    def __repr__(self) -> str:
        return f"<TaxPlugin id={self.plugin_id!r} jurisdiction={self.jurisdiction!r}>"


class CurrencyPlugin(abc.ABC):
    """
    Abstract base for FX rate resolution and currency conversion.
    Implementations may fetch live rates from ECB, RBI, or a custom feed.
    """

    @property
    @abc.abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier, e.g. 'ecb_fx', 'rbi_fx', 'manual_fx'."""

    @abc.abstractmethod
    def get_rate(self, source: str, target: str) -> Decimal:
        """
        Return the exchange rate source → target.
        Raise LookupError if the pair is not supported.
        """

    @abc.abstractmethod
    def convert(
        self,
        amount: Decimal,
        source: str,
        target: str,
    ) -> FxConversionResult:
        """Convert `amount` from `source` currency to `target` currency."""

    def __repr__(self) -> str:
        return f"<CurrencyPlugin id={self.plugin_id!r}>"


class StatutoryReportPlugin(abc.ABC):
    """
    Abstract base for generating jurisdiction-specific statutory reports
    (e.g. GSTR-1 for India, 10-K for US, IAS-1 for EU IFRS).
    """

    @property
    @abc.abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier, e.g. 'in_gstr1', 'us_10k', 'eu_ias1'."""

    @property
    @abc.abstractmethod
    def report_name(self) -> str:
        """Human-readable report name."""

    @abc.abstractmethod
    def generate(
        self,
        tenant_id: str,
        period_start: str,
        period_end: str,
        db_session: Any,
    ) -> Dict[str, Any]:
        """
        Generate the statutory report as a JSON-serialisable dict.
        The db_session is the SQLAlchemy Session (typed as Any to avoid
        circular imports in plugin implementations).
        """

    def __repr__(self) -> str:
        return f"<StatutoryReportPlugin id={self.plugin_id!r} report={self.report_name!r}>"


class LocalizationPlugin(abc.ABC):
    """
    Top-level composite plugin that bundles a TaxPlugin, CurrencyPlugin,
    and StatutoryReportPlugin for a given locale/standard.

    This is the single registration point for each locale (e.g. India GST,
    US GAAP, EU IFRS).
    """

    @property
    @abc.abstractmethod
    def plugin_id(self) -> str:
        """Unique locale identifier, e.g. 'in_gst', 'us_gaap', 'eu_ifrs'."""

    @property
    @abc.abstractmethod
    def display_name(self) -> str:
        """Human-readable name, e.g. 'India GST'."""

    @property
    def tax_plugin(self) -> Optional[TaxPlugin]:
        """Return associated TaxPlugin, or None if not applicable."""
        return None

    @property
    def currency_plugin(self) -> Optional[CurrencyPlugin]:
        """Return associated CurrencyPlugin, or None if not applicable."""
        return None

    @property
    def statutory_report_plugin(self) -> Optional[StatutoryReportPlugin]:
        """Return associated StatutoryReportPlugin, or None if not applicable."""
        return None

    def on_pre_post(self, context: PluginContext) -> PluginContext:
        """
        Middleware hook called BEFORE a journal entry is posted.
        May enrich the context (e.g. add tax metadata).
        Must return the (possibly mutated) context.
        """
        return context

    def on_post_post(self, context: PluginContext, entry_id: str) -> None:
        """
        Middleware hook called AFTER a journal entry is successfully posted.
        Use for side-effects: notifications, audit logs, downstream events.
        """

    def serialize_metadata(self, data: Dict[str, Any]) -> str:
        """Serialize plugin metadata dict to JSON string for storage."""
        return json.dumps(data, default=str)

    def __repr__(self) -> str:
        return f"<LocalizationPlugin id={self.plugin_id!r} name={self.display_name!r}>"


# ── Plugin Registry (Singleton) ───────────────────────────────────────────────

class PluginRegistry:
    """
    Central registry for all LocalizationPlugin implementations.
    Plugins self-register at import time via `PluginRegistry.register()`.
    """

    _registry: Dict[str, LocalizationPlugin] = {}

    @classmethod
    def register(cls, plugin: LocalizationPlugin) -> None:
        if plugin.plugin_id in cls._registry:
            logger.warning(
                "Plugin %r is already registered. Overwriting.", plugin.plugin_id
            )
        cls._registry[plugin.plugin_id] = plugin
        logger.info("Plugin registered: %s", plugin)

    @classmethod
    def get(cls, plugin_id: str) -> Optional[LocalizationPlugin]:
        return cls._registry.get(plugin_id)

    @classmethod
    def get_or_raise(cls, plugin_id: str) -> LocalizationPlugin:
        plugin = cls.get(plugin_id)
        if plugin is None:
            available = list(cls._registry.keys())
            raise KeyError(
                f"Plugin {plugin_id!r} not found. Available: {available}"
            )
        return plugin

    @classmethod
    def list_all(cls) -> List[str]:
        return list(cls._registry.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear registry — used in tests only."""
        cls._registry.clear()
