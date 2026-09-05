"""Schema for openings extraction (windows/doors) - Phase 7.3."""

from typing import Literal

from pydantic import BaseModel, Field


class OpeningDetail(BaseModel):
    """Detailed opening information extracted from schedules, elevations, or details."""

    opening_id: str = Field(description="Opening identifier (e.g., 'WIN-1', 'D-101')")
    opening_type: Literal["window", "door", "opening"] = Field(
        description="Type of opening"
    )
    level: str | None = Field(
        default=None, description="Level/floor (e.g., '1st Floor', '2nd Floor', 'Ground')"
    )
    count: int | None = Field(
        default=None, description="Count of openings of this type"
    )
    width_ft: float | None = Field(
        default=None, description="Width in feet (if stated)"
    )
    height_ft: float | None = Field(
        default=None, description="Height in feet (if stated)"
    )
    size: str | None = Field(
        default=None, description="Size designation (e.g., '3-0 x 6-8', '4-0 x 7-0')"
    )
    material: str | None = Field(
        default=None,
        description="Material (e.g., 'aluminum', 'steel', 'wood', 'storefront')",
    )
    associated_lintel_id: str | None = Field(
        default=None, description="Associated lintel identifier if applicable"
    )
    flashing_required: bool = Field(
        default=False, description="Whether flashing is required"
    )
    source: Literal["schedule", "elevation", "detail", "unknown"] = Field(
        default="unknown", description="Source of extraction"
    )
    page_number: int = Field(description="Page number where opening was found (1-indexed)")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    detail_reference: str | None = Field(
        default=None, description="Detail sheet reference (e.g., 'D-2 Detail 3')"
    )
    evidence_snippet: str = Field(
        description="Evidence snippet showing where opening was found"
    )


class OpeningsResult(BaseModel):
    """Complete openings extraction result (Phase 7.3)."""

    openings: list[OpeningDetail] = Field(
        default_factory=list, description="List of extracted openings"
    )
    missing_fields: list[str] = Field(
        default_factory=list, description="Fields that could not be determined"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in extraction (0.0 to 1.0)",
    )






