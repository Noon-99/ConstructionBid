"""Schema for evidence index linking bid items and geometry to PDF pages (Phase 6.7)."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceReference(BaseModel):
    """Reference to evidence in PDF."""

    page_number: int = Field(description="1-indexed page number")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Text snippet or description of evidence")
    location_type: str | None = Field(
        default=None, description="Type of location (e.g., 'elevation_notes', 'schedule')"
    )
    bbox: dict[str, float] | None = Field(
        default=None,
        description="Bounding box {x0, y0, x1, y1} normalized 0..1 OR absolute px (Phase 8.6A)",
    )
    bbox_source: Literal["none", "vision_box", "heuristic"] | None = Field(
        default="none",
        description="Source of bounding box (Phase 8.6A). 'none' if bbox is null.",
    )


class BidItemEvidence(BaseModel):
    """Evidence links for a bid line item."""

    line_item_index: int = Field(description="Index in bid_proposal.line_items")
    division: str = Field(description="Division name")
    description: str = Field(description="Line item description")
    evidence_references: list[EvidenceReference] = Field(
        default_factory=list, description="Linked evidence references"
    )
    quantity_source: str | None = Field(
        default=None, description="Source of quantity (from_drawing, from_schedule, etc.)"
    )
    basis: str = Field(description="Basis/evidence text from line item")


class ZoneEvidence(BaseModel):
    """Evidence links for a 3D zone."""

    zone_id: str = Field(description="Zone ID from model_3d")
    zone_type: str = Field(description="Zone type (room, work_zone, building_mass)")
    label: str | None = Field(default=None, description="Zone label/name")
    evidence_references: list[EvidenceReference] = Field(
        default_factory=list, description="Linked evidence references"
    )
    linked_bid_items: list[int] = Field(
        default_factory=list,
        description="Indices of linked bid line items (by keyword match or exact match)",
    )


class DetailEvidence(BaseModel):
    """Evidence links for a construction detail (Phase 7.4)."""

    detail_id: str = Field(description="Detail ID from detail graph")
    detail_type: str = Field(description="Type of detail")
    sheet_id: str = Field(description="Sheet ID")
    detail_label: str = Field(description="Detail label")
    evidence_references: list[EvidenceReference] = Field(
        default_factory=list, description="Linked evidence references"
    )
    linked_zones: list[str] = Field(
        default_factory=list, description="List of zone IDs this detail applies to"
    )
    linked_openings: list[str] = Field(
        default_factory=list, description="List of opening IDs this detail applies to"
    )
    linked_bid_items: list[int] = Field(
        default_factory=list,
        description="Indices of linked bid line items",
    )


class EvidenceIndex(BaseModel):
    """Complete evidence index for a project."""

    project_id: str = Field(description="Project ID")
    bid_item_evidence: list[BidItemEvidence] = Field(
        default_factory=list, description="Evidence for each bid line item"
    )
    zone_evidence: list[ZoneEvidence] = Field(
        default_factory=list, description="Evidence for each 3D zone"
    )
    detail_evidence: list[DetailEvidence] = Field(
        default_factory=list, description="Evidence for each construction detail (Phase 7.4)"
    )
    generated_at: str = Field(description="ISO timestamp when index was generated")

