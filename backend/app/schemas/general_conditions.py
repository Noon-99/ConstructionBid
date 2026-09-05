"""Schema for general conditions (Phase 10.1).

General conditions represent project-level overhead costs including
management, site protection, permits, logistics, and other indirect costs.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GeneralConditionsItem(BaseModel):
    """A single general conditions line item."""

    item_id: str = Field(description="Unique identifier for this GC item")
    title: str = Field(description="Item title (e.g., 'Project Management', 'Site Protection')")
    division: str = Field(description="CSI division (typically '01 General Requirements')")
    category: Literal[
        "management",
        "site_protection",
        "temporary_facilities",
        "utilities",
        "cleanup",
        "security",
        "safety",
        "permits",
        "inspections",
        "mobilization",
        "other",
    ] = Field(description="Category of general conditions item")
    quantity: float | None = Field(
        default=None, description="Quantity (e.g., weeks, days, each, SF, LF)"
    )
    unit: str | None = Field(default=None, description="Unit of measurement")
    unit_cost: float | None = Field(default=None, description="Unit cost in dollars")
    total_cost: float = Field(ge=0.0, description="Total cost for this item")
    basis: str = Field(
        description="Basis for this GC item (e.g., 'Project duration: 4 weeks', 'Building height: 30 ft')"
    )
    trigger: str | None = Field(
        default=None,
        description="Scope trigger that caused this item (e.g., 'exterior_masonry', 'height_over_20ft')",
    )
    region_factor: float | None = Field(
        default=None,
        ge=0.0,
        description="Regional multiplier applied (e.g., 1.2 for NYC, 1.0 for default)",
    )


class GeneralConditions(BaseModel):
    """Complete general conditions breakdown for a project (Phase 10.1)."""

    project_id: str = Field(description="Project ID this GC applies to")
    building_type: str = Field(
        description="Building type (e.g., 'row_house', 'institutional', 'commercial')"
    )
    building_height_ft: float | None = Field(
        default=None, description="Building height in feet (if available)"
    )
    estimated_duration_weeks: float | None = Field(
        default=None, description="Estimated project duration in weeks"
    )
    region_id: str = Field(
        description="Region identifier (e.g., 'NYC', 'NJ', 'TX', 'US_DEFAULT')"
    )
    items: list[GeneralConditionsItem] = Field(
        default_factory=list, description="List of general conditions items"
    )
    total_cost: float = Field(
        ge=0.0, description="Total general conditions cost (sum of all items)"
    )
    total_cost_percent_of_base: float | None = Field(
        default=None,
        ge=0.0,
        description="GC total as percentage of base bid (if base bid available)",
    )
    generated_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp when GC was generated"
    )





