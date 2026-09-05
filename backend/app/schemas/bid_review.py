"""Schema for bid review artifact (Phase 8.2).

Bid review provides contractor-grade breakdown of each line item for review.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class RuleRef(BaseModel):
    """Reference to cost rule used."""

    rule_name: str = Field(description="Name of the cost rule (e.g., 'parapet_rebuild')")
    yaml_file: str = Field(description="YAML file name (e.g., 'parapet_rebuild.yml')")
    match_keywords_used: list[str] = Field(
        default_factory=list,
        description="Keywords that matched this rule (e.g., ['parapet', 'rebuild'])",
    )


class MultiplierApplied(BaseModel):
    """Applied multiplier with factor."""

    name: str = Field(description="Multiplier name (e.g., 'height', 'material', 'equipment', 'waste')")
    factor: float = Field(description="Multiplier factor applied")


class EvidenceRef(BaseModel):
    """Evidence reference for a line item."""

    page_number: int = Field(description="Page number (1-indexed)")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    snippet: str | None = Field(default=None, description="Evidence snippet")
    bbox: dict[str, float] | None = Field(
        default=None,
        description="Bounding box {x0, y0, x1, y1} normalized 0..1 OR absolute px (Phase 8.6A)",
    )
    bbox_source: Literal["none", "vision_box", "heuristic"] | None = Field(
        default="none",
        description="Source of bounding box (Phase 8.6A). 'none' if bbox is null.",
    )


class BidLineItemReview(BaseModel):
    """Review breakdown for a single bid line item."""

    line_item_id: str = Field(description="Unique identifier for this line item")
    line_item_index: int = Field(description="Index in bid_proposal.line_items")
    division: str = Field(description="Division name (e.g., '04 Masonry')")
    title: str = Field(description="Line item description/title")
    quantity: float = Field(description="Quantity")
    unit: str = Field(description="Unit (EA, LF, SF, CY, etc.)")
    unit_cost: float = Field(description="Unit cost")
    total_cost: float = Field(description="Total cost (quantity * unit_cost * multipliers)")
    rule_refs: list[RuleRef] = Field(
        default_factory=list, description="Cost rules that matched this item"
    )
    multipliers_applied: list[MultiplierApplied] = Field(
        default_factory=list, description="Multipliers applied (height, material, equipment, waste)"
    )
    quantity_source: Literal[
        "explicit_takeoff",
        "derived_from_dimensions",
        "heuristic",
        "recovered",
        "allowance",
        "unknown",
    ] = Field(description="Source of quantity")
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list, description="Evidence references (pages, sheets, snippets)"
    )
    flags: list[str] = Field(
        default_factory=list,
        description="Flags: suspicious_unit_cost, suspicious_quantity, recovered_item, heuristic_quantity",
    )


class BidReview(BaseModel):
    """Complete bid review artifact (Phase 8.2)."""

    project_id: str = Field(description="Project ID")
    total_bid: float = Field(description="Total bid amount")
    line_items: list[BidLineItemReview] = Field(
        default_factory=list, description="Review breakdown for each line item"
    )
    recovery_performed: bool = Field(
        default=False, description="Whether recovery/re-read was performed"
    )
    recovery_pages: list[int] = Field(
        default_factory=list, description="Pages that were re-read during recovery"
    )
    compliance_adjustments: list[str] = Field(
        default_factory=list,
        description="Compliance adjustments pulled from costing (e.g., prevailing wage, union, bonds)",
    )
    compliance_costs: dict[str, float] = Field(
        default_factory=dict,
        description="Compliance cost breakdown from costing stage",
    )
    compliance_total: float = Field(
        default=0.0,
        description="Total compliance cost applied to the bid",
    )
    generated_at: str = Field(description="ISO timestamp when review was generated")

