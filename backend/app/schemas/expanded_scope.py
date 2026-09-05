"""Schema for expanded scope (Phase 9.2A).

Expanded scope represents contractor-grade additions to the conceptual bid,
such as scaffolding, logistics, permits, and other items that contractors
typically include but conceptual bids may omit.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence_index import EvidenceReference


class ExpandedScopeItem(BaseModel):
    """A single item added to the expanded scope."""

    item_id: str = Field(description="Unique identifier for this expanded item")
    title: str = Field(description="Item title (e.g., 'Scaffolding', 'Dumpster Rental')")
    division: str | None = Field(
        default=None, description="CSI division if known (e.g., '01', '03', '13')"
    )
    quantity: float | None = Field(
        default=None, description="Quantity for this item (if applicable)"
    )
    unit: str | None = Field(
        default=None, description="Unit of measure (e.g., 'week', 'each', 'SF', 'LF')"
    )
    unit_cost: float | None = Field(
        default=None, description="Unit cost in dollars (if applicable)"
    )
    total_cost: float | None = Field(
        default=None, description="Total cost for this item (quantity * unit_cost if both present)"
    )
    reason: str = Field(
        description="Explanation of why this item was added to the scope"
    )
    source: Literal["contractor_profile", "rules", "user"] = Field(
        description="Source of this expanded item (contractor profile defaults, cost rules, or user input)"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0-1) for this expansion (1.0 = certain, 0.0 = uncertain)",
    )
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list,
        description="Optional evidence references linking this item to PDF pages/snippets",
    )
    blocking: bool = Field(
        default=False,
        description="True if this item is blocking (must be included for bid to be valid)",
    )


class RegionResolution(BaseModel):
    """Region resolution metadata (Phase 9.7)."""

    region_id: str = Field(description="Resolved region ID (e.g., 'NYC', 'NJ', 'TX', 'US_DEFAULT')")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score (0-1) for region resolution"
    )
    evidence: list[str] = Field(
        default_factory=list, description="Evidence strings explaining why this region was selected"
    )


class ExpandedScope(BaseModel):
    """Complete expanded scope for a project (Phase 9.2A)."""

    project_id: str = Field(description="Project ID this expanded scope applies to")
    profile_id: str = Field(
        description="Contractor profile ID used to generate this expanded scope"
    )
    items: list[ExpandedScopeItem] = Field(
        default_factory=list, description="List of expanded scope items"
    )
    region_resolution: RegionResolution | None = Field(
        default=None, description="Region resolution metadata (Phase 9.7)"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="When this expanded scope was generated"
    )

