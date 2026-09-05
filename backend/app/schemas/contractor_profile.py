"""Schema for contractor profile (Phase 9.1A).

Contractor profiles define region-specific rates, productivity, and defaults
for synthesizing contractor-grade bids from conceptual bids.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LaborRates(BaseModel):
    """Labor rates by trade (optional, region-specific)."""

    masonry: float | None = Field(default=None, description="Masonry labor rate per hour")
    laborer: float | None = Field(default=None, description="Laborer rate per hour")
    foreman: float | None = Field(default=None, description="Foreman rate per hour")
    concrete: float | None = Field(default=None, description="Concrete labor rate per hour")
    steel: float | None = Field(default=None, description="Steel/ironworker rate per hour")
    carpenter: float | None = Field(default=None, description="Carpenter rate per hour")
    electrician: float | None = Field(default=None, description="Electrician rate per hour")
    plumber: float | None = Field(default=None, description="Plumber rate per hour")


class CrewProductivity(BaseModel):
    """Crew productivity rates (optional, activity-specific).

    All rates are in units per day (8-hour day) unless otherwise specified.
    """

    # Masonry activities
    repointing_sf_per_day: float | None = Field(
        default=None, description="Brick repointing productivity (SF per day)"
    )
    parapet_rebuild_lf_per_day: float | None = Field(
        default=None, description="Parapet rebuild productivity (linear feet per day)"
    )
    lintel_each_per_day: float | None = Field(
        default=None, description="Lintel replacement productivity (each per day)"
    )
    brick_rebuild_sf_per_day: float | None = Field(
        default=None, description="Brick veneer rebuild productivity (SF per day)"
    )
    cmu_wall_sf_per_day: float | None = Field(
        default=None, description="CMU wall construction productivity (SF per day)"
    )

    # Concrete activities
    concrete_footing_cy_per_day: float | None = Field(
        default=None, description="Concrete footing productivity (CY per day)"
    )
    slab_on_grade_sf_per_day: float | None = Field(
        default=None, description="Slab on grade productivity (SF per day)"
    )

    # Demo activities
    demo_cmu_sf_per_day: float | None = Field(
        default=None, description="CMU wall demo productivity (SF per day)"
    )

    # Other activities (extensible)
    flashing_lf_per_day: float | None = Field(
        default=None, description="Flashing installation productivity (linear feet per day)"
    )
    window_replacement_each_per_day: float | None = Field(
        default=None, description="Window replacement productivity (each per day)"
    )
    door_replacement_each_per_day: float | None = Field(
        default=None, description="Door replacement productivity (each per day)"
    )


class ContractorProfile(BaseModel):
    """Contractor profile for bid synthesis (Phase 9.1A).

    Defines region-specific rates, productivity, and defaults for converting
    conceptual bids into contractor-grade bids.
    """

    profile_id: str = Field(description="Unique profile identifier (e.g., 'nyc_row_house_masonry_v1')")
    region: str = Field(description="Region identifier (e.g., 'NYC', 'LA', 'Chicago')")
    project_type: str = Field(
        description="Project type this profile applies to (e.g., 'row_house_masonry', 'institutional_new_construction')"
    )
    labor_rates: LaborRates = Field(description="Labor rates by trade")
    overhead_pct: float = Field(
        ge=0.0, le=100.0, description="Overhead percentage (e.g., 18.0 for 18%)"
    )
    profit_pct: float = Field(
        ge=0.0, le=100.0, description="Profit margin percentage (e.g., 12.0 for 12%)"
    )
    contingency_pct: float = Field(
        ge=0.0, le=100.0, description="Contingency percentage (e.g., 5.0 for 5%)"
    )
    allowances_defaults: dict[str, float] = Field(
        default_factory=dict, description="Default allowance amounts by name (optional)"
    )
    logistics_rates: dict[str, float] = Field(
        default_factory=dict,
        description="Logistics rates (e.g., 'scaffold_weekly': 1200.0, 'dumpster_each': 485.0, 'sidewalk_shed_weekly': 400.0)",
    )
    crew_productivity: CrewProductivity = Field(description="Crew productivity rates")
    created_at: datetime = Field(
        default_factory=datetime.now, description="When this profile was created"
    )






