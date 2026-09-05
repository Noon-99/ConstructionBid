"""Schema for lintel and header extraction - Phase 7.3."""

from typing import Literal

from pydantic import BaseModel, Field


class LintelDetail(BaseModel):
    """Lintel or header detail extracted from schedules or details."""

    lintel_id: str = Field(description="Lintel identifier (e.g., 'L-1', 'LINT-101')")
    lintel_type: Literal[
        "steel_lintel", "cmu_lintel", "precast_lintel", "bond_beam", "header"
    ] = Field(description="Type of lintel")
    section: str | None = Field(
        default=None,
        description="Section designation (e.g., 'L3x3x1/4', 'C8x11.5', '8x16 CMU')",
    )
    material_spec: str | None = Field(
        default=None,
        description="Material specification (e.g., 'ASTM A36', 'ASTM A992', 'Galvanized')",
    )
    span_ft: float | None = Field(
        default=None, description="Span in feet"
    )
    quantity: int | None = Field(
        default=None, description="Quantity of lintels"
    )
    associated_openings: list[str] = Field(
        default_factory=list,
        description="List of opening IDs associated with this lintel",
    )
    flashing_required: bool = Field(
        default=False, description="Whether flashing is required"
    )
    drip_edge_required: bool = Field(
        default=False, description="Whether drip edge is required"
    )
    source: Literal["schedule", "detail", "elevation", "unknown"] = Field(
        default="unknown", description="Source of extraction"
    )
    page_number: int = Field(description="Page number where lintel was found (1-indexed)")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    detail_reference: str | None = Field(
        default=None, description="Detail sheet reference (e.g., 'S-2 Detail 5')"
    )
    evidence_snippet: str = Field(
        description="Evidence snippet showing where lintel was found"
    )


class LintelsResult(BaseModel):
    """Complete lintels extraction result (Phase 7.3)."""

    lintels: list[LintelDetail] = Field(
        default_factory=list, description="List of extracted lintels"
    )
    missing_fields: list[str] = Field(
        default_factory=list, description="Fields that could not be determined"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in extraction (0.0 to 1.0)",
    )






