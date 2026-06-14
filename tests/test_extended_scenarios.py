"""
tests/test_extended_scenarios.py
Extensive parameterized testing suite containing 640+ test scenarios.
Covers:
- Double entry Pydantic schema validation (300 scenarios)
- Chart of Accounts hierarchical combinations (100 scenarios)
- US GAAP State Taxes (60 scenarios)
- EU IFRS Country VAT & Reverse Charges (80 scenarios)
- India GST Matrix of slabs, states, and exports (100 scenarios)
"""

import uuid
import pytest
from decimal import Decimal
from typing import List, Dict, Any

from app.schemas.ledger import JournalEntryCreate, JournalLineCreate
from app.plugins.base import PluginContext, PluginRegistry
from app.services.ledger_service import create_account, create_tenant
from app.schemas.ledger import AccountCreate
from sqlalchemy.orm import Session


# ════════════════════════════════════════════════════════════════════════════
# 1. Double Entry Balance Grid Validation (300 Scenarios)
# ════════════════════════════════════════════════════════════════════════════

# Generate 150 valid balancing lines (DR + CR = 0)
VALID_BALANCING_SCENARIOS = []
for i in range(1, 151):
    val = Decimal(f"{i}.50")
    VALID_BALANCING_SCENARIOS.append([val, -val])

# Generate 150 invalid non-balancing lines (DR + CR != 0)
INVALID_BALANCING_SCENARIOS = []
for i in range(1, 151):
    val = Decimal(f"{i}.50")
    variance = Decimal("0.01") if i % 2 == 0 else Decimal("-0.01")
    INVALID_BALANCING_SCENARIOS.append([val, -val + variance])


@pytest.mark.parametrize("amounts", VALID_BALANCING_SCENARIOS)
def test_schema_double_entry_validation_valid(amounts: List[Decimal]):
    """150 scenarios verifying valid balancing debit/credit journal entries."""
    tid = uuid.uuid4()
    acc1 = uuid.uuid4()
    acc2 = uuid.uuid4()
    
    # Instantiate the Pydantic schema to check validation
    entry = JournalEntryCreate(
        tenant_id=tid,
        description="Valid entry test",
        currency="USD",
        lines=[
            JournalLineCreate(account_id=acc1, amount=amounts[0]),
            JournalLineCreate(account_id=acc2, amount=amounts[1]),
        ]
    )
    assert entry is not None
    assert sum(line.amount for line in entry.lines) == Decimal("0")


@pytest.mark.parametrize("amounts", INVALID_BALANCING_SCENARIOS)
def test_schema_double_entry_validation_invalid(amounts: List[Decimal]):
    """150 scenarios verifying unbalanced debit/credit configurations fail validation."""
    tid = uuid.uuid4()
    acc1 = uuid.uuid4()
    acc2 = uuid.uuid4()
    
    with pytest.raises(ValueError, match="Double-entry violation"):
        JournalEntryCreate(
            tenant_id=tid,
            description="Invalid entry test",
            currency="USD",
            lines=[
                JournalLineCreate(account_id=acc1, amount=amounts[0]),
                JournalLineCreate(account_id=acc2, amount=amounts[1]),
            ]
        )


# ════════════════════════════════════════════════════════════════════════════
# 2. Chart of Accounts Hierarchical Combinations (100 Scenarios)
# ════════════════════════════════════════════════════════════════════════════

# Generate 100 configurations of codes, account types, and parent-child relations
COA_SCENARIOS = []
for i in range(1, 101):
    account_type = ["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"][i % 5]
    code = f"ACC{i:04d}"
    name = f"Account {i}"
    # 50 valid parent-child relationships, 50 invalid (invalid parent UUID)
    has_valid_parent = (i <= 50)
    COA_SCENARIOS.append((code, name, account_type, has_valid_parent))


@pytest.mark.parametrize("code, name, account_type, has_valid_parent", COA_SCENARIOS)
def test_coa_hierarchical_combinations(db: Session, code: str, name: str, account_type: str, has_valid_parent: bool):
    """100 scenarios of valid/invalid account and parent configurations."""
    # Create tenant
    tenant = create_tenant(
        db,
        type("TenantProxy", (), {"name": f"Tenant {code}", "base_currency": "USD", "fiscal_year_start_month": 1})()
    )
    
    parent_id = None
    if has_valid_parent:
        # First create a valid parent account
        parent = create_account(
            db,
            AccountCreate(
                tenant_id=tenant.id,
                code=f"PAR-{code[:16]}",
                name=f"Parent {name}",
                account_type=account_type,
                currency="USD"
            )
        )
        parent_id = parent.id
    else:
        # Invalid/nonexistent parent UUID
        parent_id = uuid.uuid4()

    if has_valid_parent:
        # Should succeed
        acc = create_account(
            db,
            AccountCreate(
                tenant_id=tenant.id,
                parent_id=parent_id,
                code=code,
                name=name,
                account_type=account_type,
                currency="USD"
            )
        )
        assert acc.parent_id == parent_id
        assert acc.code == code
    else:
        # Should fail with AccountNotFoundError (parent not found)
        from app.services.ledger_service import AccountNotFoundError
        with pytest.raises(AccountNotFoundError):
            create_account(
                db,
                AccountCreate(
                    tenant_id=tenant.id,
                    parent_id=parent_id,
                    code=code,
                    name=name,
                    account_type=account_type,
                    currency="USD"
                )
            )


# ════════════════════════════════════════════════════════════════════════════
# 3. US GAAP State Taxes (60 Scenarios)
# ════════════════════════════════════════════════════════════════════════════

# 50 standard US states + 10 territories/edge codes
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "PR", "VI", "GU", "AS", "MP", "DC", "AA", "AE", "AP", "UM"
]

@pytest.mark.parametrize("state", US_STATES)
def test_us_gaap_state_taxes(state: str):
    """60 scenarios checking sales tax rates and calculations for US jurisdictions."""
    plugin = PluginRegistry.get("us_gaap")
    assert plugin is not None
    
    ctx = PluginContext(
        tenant_id="us-tenant",
        base_currency="USD",
        entry_currency="USD",
        description=f"Sales in {state}",
        reference_id=None,
        lines=[{"account_id": "acc-1", "amount": "1000.00", "description": "SaaS sale"}],
        plugin_metadata={"state": state}
    )
    
    results = plugin.tax_plugin.compute_tax(ctx)
    assert len(results) == 1
    
    # Expected rates
    rates_map = {
        "CA": Decimal("0.0725"),
        "NY": Decimal("0.08"),
        "TX": Decimal("0.0625"),
        "WA": Decimal("0.065"),
        "FL": Decimal("0.06"),
    }
    expected_rate = rates_map.get(state, Decimal("0.0825")) # Default rate
    
    assert results[0].tax_rate == expected_rate
    expected_tax = (Decimal("1000.00") * expected_rate).quantize(Decimal("0.0001"))
    assert results[0].tax_amount == expected_tax


# ════════════════════════════════════════════════════════════════════════════
# 4. EU IFRS Country VAT & Reverse Charges (80 Scenarios)
# ════════════════════════════════════════════════════════════════════════════

# Generate 80 combinations of EU/non-EU country codes, reverse charge triggers
EU_VAT_SCENARIOS = []
countries = [
    "DE", "FR", "IT", "ES", "NL", "BE", "PL", "SE", "DK", "IE",
    "AT", "FI", "PT", "GR", "CZ", "HU", "RO", "SK", "BG", "HR",
    "LT", "LV", "EE", "CY", "LU", "MT", "SI", "US", "IN", "JP",
    "CA", "AU", "ZA", "NZ", "BR", "MX", "CN", "SG", "CH", "NO"
]
for idx, c in enumerate(countries):
    # Case A: Standard consumer VAT
    EU_VAT_SCENARIOS.append((c, False, None))
    # Case B: B2B reverse charge
    EU_VAT_SCENARIOS.append((c, True, f"VAT-{c}-12345"))


@pytest.mark.parametrize("country, intra_eu_b2b, vat_number", EU_VAT_SCENARIOS)
def test_eu_ifrs_country_vat(country: str, intra_eu_b2b: bool, vat_number: str):
    """80 scenarios testing IFRS VAT rates, B2B reverse charge rules, and validation."""
    plugin = PluginRegistry.get("eu_ifrs")
    assert plugin is not None
    
    ctx = PluginContext(
        tenant_id="eu-tenant",
        base_currency="EUR",
        entry_currency="EUR",
        description=f"Transaction in {country}",
        reference_id=None,
        lines=[{"account_id": "acc-2", "amount": "1000.00", "description": "Consulting"}],
        plugin_metadata={
            "country_code": country,
            "intra_eu_b2b": intra_eu_b2b,
            "vat_number": vat_number
        }
    )
    
    results = plugin.tax_plugin.compute_tax(ctx)
    assert len(results) == 1
    
    if intra_eu_b2b and vat_number:
        # Reverse charge matches
        assert results[0].tax_amount == Decimal("0")
        assert results[0].tax_rate == Decimal("0")
        assert "REVERSE_CHARGE" in results[0].tax_code
    else:
        # Standard VAT
        rates_map = {
            "DE": Decimal("0.19"),
            "FR": Decimal("0.20"),
            "IT": Decimal("0.22"),
            "ES": Decimal("0.21"),
            "NL": Decimal("0.21"),
            "BE": Decimal("0.21"),
            "PL": Decimal("0.23"),
            "SE": Decimal("0.25"),
            "DK": Decimal("0.25"),
            "IE": Decimal("0.23"),
        }
        expected_rate = rates_map.get(country, Decimal("0.20")) # Default rate
        assert results[0].tax_rate == expected_rate
        expected_vat = (Decimal("1000.00") * expected_rate).quantize(Decimal("0.0001"))
        assert results[0].tax_amount == expected_vat


# ════════════════════════════════════════════════════════════════════════════
# 5. India GST Slabs, Routes, and Exports (100 Scenarios)
# ════════════════════════════════════════════════════════════════════════════

# Generate 100 permutations of slabs, inter_state and export routes
GST_SCENARIOS = []
slabs = ["EXEMPT", "GST_0", "GST_5", "GST_12", "GST_18", "GST_28"]
for i in range(100):
    slab = slabs[i % len(slabs)]
    inter_state = (i % 2 == 0)
    is_export = (i % 5 == 0)
    gstin = f"29ABCDE1234F1Z{i%10}"
    GST_SCENARIOS.append((slab, inter_state, is_export, gstin))


@pytest.mark.parametrize("slab, inter_state, is_export, gstin", GST_SCENARIOS)
def test_india_gst_matrix(slab: str, inter_state: bool, is_export: bool, gstin: str):
    """100 scenarios verifying GST split (CGST+SGST), integrated GST (IGST), and zero-rated exports."""
    plugin = PluginRegistry.get("in_gst")
    assert plugin is not None
    
    ctx = PluginContext(
        tenant_id="in-tenant",
        base_currency="INR",
        entry_currency="INR",
        description="GST computation",
        reference_id=None,
        lines=[{"account_id": "acc-3", "amount": "10000.00", "description": "Services"}],
        plugin_metadata={
            "gstin": gstin,
            "gst_slab": slab,
            "inter_state": inter_state,
            "is_export": is_export
        }
    )
    
    # Validate context logic
    plugin.tax_plugin.validate_context(ctx)
    
    results = plugin.tax_plugin.compute_tax(ctx)
    
    rates_map = {
        "EXEMPT": Decimal("0.00"),
        "GST_0":  Decimal("0.00"),
        "GST_5":  Decimal("0.05"),
        "GST_12": Decimal("0.12"),
        "GST_18": Decimal("0.18"),
        "GST_28": Decimal("0.28"),
    }
    full_rate = rates_map[slab]
    
    if is_export:
        assert len(results) == 1
        assert results[0].tax_amount == Decimal("0")
        assert results[0].tax_rate == Decimal("0")
        assert results[0].tax_code == "GST_ZERO_RATED_EXPORT"
    elif inter_state:
        assert len(results) == 1
        assert results[0].tax_rate == full_rate
        expected_tax = (Decimal("10000.00") * full_rate).quantize(Decimal("0.0001"))
        assert results[0].tax_amount == expected_tax
        assert results[0].tax_code == f"IGST_{slab}"
    else:
        assert len(results) == 2
        cgst_res = [r for r in results if "CGST" in r.tax_code][0]
        sgst_res = [r for r in results if "SGST" in r.tax_code][0]
        
        expected_rate = (full_rate / 2).quantize(Decimal("0.0001"))
        expected_tax = ((Decimal("10000.00") * full_rate) / 2).quantize(Decimal("0.0001"))
        
        assert cgst_res.tax_rate == expected_rate
        assert sgst_res.tax_rate == expected_rate
        assert cgst_res.tax_amount == expected_tax
        assert sgst_res.tax_amount == expected_tax
