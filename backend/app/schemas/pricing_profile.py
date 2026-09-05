"""Schema for pricing profiles (Phase 10.10A).

Pricing profiles define regional/state-specific labor rates, material multipliers,
equipment rates, and markups. These are data-driven and stored as YAML files.
"""

from typing import Any

from pydantic import BaseModel, Field


class LaborRates(BaseModel):
    """Labor rates by trade/division."""

    masonry: float | None = Field(
        default=None, description="Masonry labor rate per hour"
    )
    carpentry: float | None = Field(
        default=None, description="Carpentry labor rate per hour"
    )
    concrete: float | None = Field(
        default=None, description="Concrete labor rate per hour"
    )
    steel: float | None = Field(default=None, description="Steel labor rate per hour")
    general_labor: float | None = Field(
        default=None, description="General labor rate per hour"
    )
    # Allow additional trades via dict
    custom_rates: dict[str, float] = Field(
        default_factory=dict,
        description="Custom trade rates keyed by trade name or division",
    )


class MaterialMultipliers(BaseModel):
    """Material cost multipliers by material keywords or division."""

    brick: float | None = Field(
        default=None, description="Brick material multiplier (e.g., 1.15 for 15% markup)"
    )
    mortar: float | None = Field(
        default=None, description="Mortar material multiplier"
    )
    concrete: float | None = Field(
        default=None, description="Concrete material multiplier"
    )
    steel: float | None = Field(
        default=None, description="Steel material multiplier"
    )
    cmu: float | None = Field(
        default=None, description="CMU (concrete masonry unit) material multiplier"
    )
    # Allow additional materials via dict
    custom_multipliers: dict[str, float] = Field(
        default_factory=dict,
        description="Custom material multipliers keyed by material keyword or division",
    )


class EquipmentRates(BaseModel):
    """Equipment rental rates."""

    scaffold_daily: float | None = Field(
        default=None, description="Scaffold daily rental rate"
    )
    scaffold_weekly: float | None = Field(
        default=None, description="Scaffold weekly rental rate"
    )
    crane_daily: float | None = Field(
        default=None, description="Crane daily rental rate"
    )
    dumpster_weekly: float | None = Field(
        default=None, description="Dumpster weekly rental rate"
    )
    # Allow additional equipment via dict
    custom_rates: dict[str, float] = Field(
        default_factory=dict,
        description="Custom equipment rates keyed by equipment name",
    )


class PricingProfile(BaseModel):
    """Pricing profile for regional/state-specific pricing (Phase 10.10A)."""

    profile_id: str = Field(description="Unique profile identifier (e.g., 'nyc_2025q1', 'default_national')")
    label: str = Field(description="Human-readable label (e.g., 'NYC 2025 Q1', 'National Default')")
    region: str = Field(
        description="Region identifier (e.g., 'NYC', 'NJ', 'TX', 'US_DEFAULT')"
    )
    currency: str = Field(default="USD", description="Currency code")
    labor_rates: LaborRates = Field(description="Labor rates by trade/division")
    material_multipliers: MaterialMultipliers = Field(
        description="Material cost multipliers by material keywords/division"
    )
    equipment_rates: EquipmentRates = Field(description="Equipment rental rates")
    overhead_pct_range: tuple[float, float] = Field(
        default=(10.0, 20.0),
        description="Overhead percentage range (min, max)",
    )
    profit_pct_range: tuple[float, float] = Field(
        default=(5.0, 15.0),
        description="Profit percentage range (min, max)",
    )
    overhead_pct_default: float = Field(
        default=15.0, description="Default overhead percentage"
    )
    profit_pct_default: float = Field(
        default=10.0, description="Default profit percentage"
    )
    escalation_index: float | None = Field(
        default=None,
        description="Optional escalation index (e.g., ENR index value) for future cost adjustments",
    )
    notes: str | None = Field(
        default=None, description="Notes about this pricing profile"
    )





