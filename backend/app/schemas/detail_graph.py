"""Schema for detail graph extraction (Phase 7.4).

Detail graph represents what details exist, where they apply, and what construction elements they govern.
"""

from typing import Literal

from pydantic import BaseModel, Field


class DetailNode(BaseModel):
    """A construction detail node in the detail graph (Phase 7.4)."""

    detail_id: str = Field(description="Unique detail identifier (e.g., 'DET-001', 'S-011-D4')")
    detail_type: Literal[
        "parapet",
        "wall_section",
        "window",
        "lintel",
        "roof",
        "roof_edge",
        "foundation",
        "footing",
        "mechanical",
        "plumbing",
        "electrical",
        "site",
        "compliance",
        "other",
    ] = Field(description="Type of construction detail")
    sheet_id: str = Field(description="Sheet ID where detail is located (e.g., 'S-011')")
    detail_label: str = Field(
        description="Detail label/callout (e.g., 'Detail 4', 'Typical Parapet Detail')"
    )
    applies_to: list[str] = Field(
        default_factory=list,
        description="List of element IDs this detail applies to (zones, openings, structural elements)",
    )
    materials_referenced: list[str] = Field(
        default_factory=list,
        description="Materials referenced in detail (e.g., '8\" CMU', 'Steel lintel L3x3x1/4')",
    )
    dimensions_referenced: list[str] = Field(
        default_factory=list,
        description="Dimensions referenced in detail (e.g., '12\" parapet height', '6\" flashing')",
    )
    compliance_references: list[str] = Field(
        default_factory=list,
        description="Compliance or procurement references tied to this detail (e.g., prevailing wage schedules, bond requirements)",
    )
    notes: str | None = Field(
        default=None, description="Notes or special requirements from detail"
    )
    page_number: int = Field(description="Page number where detail is found (1-indexed)")
    evidence_snippet: str = Field(
        description="Evidence snippet showing where detail was found"
    )
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence score for this detail extraction (0.0-1.0)",
    )


class DetailGraph(BaseModel):
    """Complete detail graph for a project (Phase 7.4)."""

    details: list[DetailNode] = Field(
        default_factory=list, description="List of extracted detail nodes"
    )
    missing_fields: list[str] = Field(
        default_factory=list, description="Fields that could not be determined"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in extraction (0.0 to 1.0)",
    )






