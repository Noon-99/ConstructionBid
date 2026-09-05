"""Schema for zone cost map (Phase 8.3).

Maps 3D zones to bid line items and computes cost attribution.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence_index import EvidenceReference


class TopLineItem(BaseModel):
    """Top contributing line item for a zone."""

    line_item_index: int = Field(description="Index in bid_proposal.line_items")
    title: str = Field(description="Line item title/description")
    division: str = Field(description="Division name")
    total_cost: float = Field(description="Total cost for this line item")
    contribution_percent: float = Field(
        description="Percentage of zone total cost contributed by this item"
    )
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list, description="Evidence references from bid_review (Phase 8.6B: standardized)"
    )


class ZoneCostItem(BaseModel):
    """Cost attribution for a single zone."""

    zone_id: str = Field(description="Zone identifier (zone_name from model_3d)")
    zone_name: str = Field(description="Zone name/label")
    zone_type: str | None = Field(
        default=None, description="Zone type (work_zone, room, building_mass)"
    )
    total_cost: float = Field(description="Total cost attributed to this zone")
    division_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Cost breakdown by division (e.g., {'04 Masonry': 1000.0, '05 Metals': 500.0})",
    )
    top_line_items: list[TopLineItem] = Field(
        default_factory=list, description="Top 5 line items by cost contribution"
    )
    linked_line_item_ids: list[int] = Field(
        default_factory=list,
        description="Indices of all linked bid line items (from evidence_index or keyword match)",
    )
    attribution_method: Literal["evidence_index", "keyword_fallback", "none"] = Field(
        description="Method used to attribute costs (evidence_index explicit links, keyword fallback, or none)"
    )


class ZoneCostMap(BaseModel):
    """Complete zone cost map for a project (Phase 8.3)."""

    project_id: str = Field(description="Project ID")
    generated_at: str = Field(description="ISO timestamp when map was generated")
    zones: list[ZoneCostItem] = Field(
        default_factory=list, description="Cost attribution for each zone"
    )
    max_cost: float = Field(
        default=0.0, description="Maximum zone cost (for heatmap normalization)"
    )
    min_cost: float = Field(
        default=0.0, description="Minimum zone cost (for heatmap normalization, excluding 0)"
    )

