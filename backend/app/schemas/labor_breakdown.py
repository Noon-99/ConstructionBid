"""Schema for labor breakdown (Phase 9.3A).

Labor breakdown represents the detailed labor cost analysis for a contractor bid,
breaking down work activities, crew composition, productivity, and estimated labor costs.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class LaborActivity(BaseModel):
    """A single labor activity with crew, productivity, and cost breakdown."""

    activity_id: str = Field(description="Unique identifier for this labor activity")
    title: str = Field(description="Activity title (e.g., 'Parapet Rebuild', 'Brick Repointing')")
    related_bid_item_ids: list[str] = Field(
        default_factory=list,
        description="List of bid item IDs this activity relates to",
    )
    quantity: float = Field(
        ge=0.0, description="Quantity of work for this activity (e.g., 50.0 LF, 500.0 SF)"
    )
    unit: str = Field(description="Unit of measure (e.g., 'LF', 'SF', 'each', 'CY')")
    productivity_per_day: float | None = Field(
        default=None,
        ge=0.0,
        description="Productivity rate in units per day (8-hour day). None if not applicable.",
    )
    crew: list[str] = Field(
        default_factory=list,
        description="Crew composition (e.g., ['mason', 'laborer'], ['foreman', 'mason', 'laborer'])",
    )
    estimated_days: float | None = Field(
        default=None,
        ge=0.0,
        description="Estimated number of days to complete this activity. Calculated from quantity / productivity_per_day if both present.",
    )
    labor_cost: float | None = Field(
        default=None,
        ge=0.0,
        description="Total labor cost for this activity in dollars. Calculated from crew rates × estimated_days if available.",
    )
    reason: str = Field(
        description="Explanation of how this labor activity was derived (e.g., 'From bid item: Parapet rebuild', 'Estimated from productivity rates')"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0-1) for this labor breakdown (1.0 = certain, 0.0 = uncertain)",
    )


from app.schemas.expanded_scope import RegionResolution


class LaborBreakdown(BaseModel):
    """Complete labor breakdown for a project (Phase 9.3A)."""

    project_id: str = Field(description="Project ID this labor breakdown applies to")
    profile_id: str = Field(
        description="Contractor profile ID used to generate this labor breakdown"
    )
    activities: list[LaborActivity] = Field(
        default_factory=list, description="List of labor activities"
    )
    total_labor_cost: float | None = Field(
        default=None,
        ge=0.0,
        description="Total labor cost across all activities in dollars. Sum of all activity labor_cost values.",
    )
    region_resolution: RegionResolution | None = Field(
        default=None, description="Region resolution metadata (Phase 9.7)"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="When this labor breakdown was generated"
    )

