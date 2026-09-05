"""Schema for detail overlay index (Phase 8.4).

Maps cross-section regions to detail references and evidence for section view navigation.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence_index import EvidenceReference


class EvidenceSnippet(BaseModel):
    """Evidence snippet with page reference (Phase 8.6B: aligned with EvidenceReference)."""

    page_number: int = Field(description="Page number (1-indexed)")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    snippet: str = Field(description="Evidence snippet text")
    location_type: str | None = Field(
        default=None, description="Location type (e.g., 'detail', 'note', 'callout')"
    )
    bbox: dict[str, float] | None = Field(
        default=None,
        description="Bounding box {x0, y0, x1, y1} normalized 0..1 OR absolute px (Phase 8.6A)",
    )
    bbox_source: Literal["none", "vision_box", "heuristic"] | None = Field(
        default="none",
        description="Source of bounding box (Phase 8.6A). 'none' if bbox is null.",
    )


class DetailOverlayRef(BaseModel):
    """Detail overlay reference for a cross-section region."""

    region_id: str = Field(description="Region ID from cross_section_regions")
    region_type: Literal[
        "wall_assembly", "parapet", "roof_edge", "floor_to_floor", "foundation"
    ] = Field(description="Type of cross-section region")
    detail_ids: list[str] = Field(
        default_factory=list,
        description="List of detail IDs linked to this region (from detail_graph)",
    )
    detail_refs: list[dict] = Field(
        default_factory=list,
        description="Detail references with sheet_id, detail_label, page_number",
    )
    evidence_pages: list[int] = Field(
        default_factory=list,
        description="List of page numbers with evidence (deduplicated)",
    )
    snippets: list[EvidenceSnippet] = Field(
        default_factory=list, description="Evidence snippets with page references"
    )


class DetailOverlayIndex(BaseModel):
    """Complete detail overlay index for a project (Phase 8.4)."""

    project_id: str = Field(description="Project ID")
    generated_at: str = Field(description="ISO timestamp when index was generated")
    regions: list[DetailOverlayRef] = Field(
        default_factory=list, description="Detail overlay references for each region"
    )

