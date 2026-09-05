"""Pydantic models for document analysis results."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.site_context import SiteContext


class SheetInfo(BaseModel):
    """Information about a drawing sheet."""

    sheet_id: str = Field(description="Sheet identifier (e.g., 'A-1', 'S-2')")
    page_number: int = Field(description="1-indexed page number")
    sheet_type: str = Field(
        description="Type: elevation, plan, section, detail, schedule, notes, unknown"
    )
    title: str | None = Field(default=None, description="Sheet title if visible")


class ScopeLocator(BaseModel):
    """Location where scope information is found."""

    sheet_id: str | None = Field(default=None, description="Sheet identifier")
    page_number: int = Field(description="1-indexed page number")
    location_type: Literal[
        "elevation_notes",
        "general_notes",
        "schedule",
        "detail_callouts",
        "specification_reference",
        "unknown",
    ] = Field(description="Type of location where scope is found")
    evidence: str = Field(
        description="Short evidence snippet (e.g., 'Parapet repair noted on elevation A-1')"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence that scope is at this location"
    )


class QuantityLocator(BaseModel):
    """Location where quantity information is found."""

    sheet_id: str | None = Field(default=None, description="Sheet identifier")
    page_number: int = Field(description="1-indexed page number")
    location_type: Literal[
        "life_safety_plan",
        "room_schedule",
        "schedule",  # Alias for room_schedule (LLM sometimes returns this)
        "elevation_dimensions",
        "area_calculations",
        "specification_table",
        "unknown",
    ] = Field(description="Type of location where quantities are found")
    evidence: str = Field(
        description="Short evidence snippet (e.g., 'Room schedule on sheet A-3')"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence that quantities are at this location"
    )


class MaterialLocator(BaseModel):
    """Location where material information is found."""

    sheet_id: str | None = Field(default=None, description="Sheet identifier")
    page_number: int = Field(description="1-indexed page number")
    location_type: Literal[
        "specification_section",
        "detail_callouts",
        "schedule",
        "general_notes",
        "unknown",
    ] = Field(description="Type of location where materials are found")
    evidence: str = Field(description="Short evidence snippet")
    confidence: float = Field(ge=0.0, le=1.0)


class GeometryLocator(BaseModel):
    """Location where geometry/3D information is found."""

    sheet_id: str | None = Field(default=None, description="Sheet identifier")
    page_number: int = Field(description="1-indexed page number")
    geometry_type: Literal[
        "floor_plan",
        "elevation",
        "section",
        "3d_view",
        "site_plan",
        "unknown",
    ] = Field(description="Type of geometry")
    evidence: str = Field(description="Short evidence snippet")
    confidence: float = Field(ge=0.0, le=1.0)


class BuildingContext(BaseModel):
    """Building context information (row-house, multi-building, etc.)."""

    building_type: Literal[
        "row_house",
        "commercial",
        "institutional",
        "mixed",
        "single_family",
        "unknown",
    ] = Field(description="Type of building")
    is_row_context: bool = Field(
        default=False, description="True if this is a row of attached buildings"
    )
    building_ids: list[str] = Field(
        default_factory=list, description="Building identifiers if present"
    )
    addresses: list[str] = Field(
        default_factory=list, description="Addresses if visible"
    )
    evidence: str = Field(description="Evidence for building context")


class KeyDimensions(BaseModel):
    """Key dimensions found in the document."""

    width: float | None = Field(default=None, description="Width in feet")
    depth: float | None = Field(default=None, description="Depth in feet")
    height: float | None = Field(default=None, description="Height in feet")
    area: float | None = Field(default=None, description="Area in square feet")
    evidence: str = Field(description="Where dimensions were found")
    confidence: float = Field(ge=0.0, le=1.0)


class CriticalExpectedItem(BaseModel):
    """Critical item that should exist for this project type."""

    item: str = Field(description="Item name (e.g., 'parapet', 'lintels', 'flashing')")
    expected_for: str = Field(
        description="Project type this is expected for (e.g., 'row_house_repair')"
    )
    found: bool = Field(description="Whether this item was found in the document")
    evidence: str | None = Field(
        default=None, description="Evidence if found, or why missing"
    )
    confidence: float = Field(ge=0.0, le=1.0)


class ProcurementContext(BaseModel):
    """Signals about procurement and compliance requirements detected in documents."""

    is_public_project: bool = Field(
        default=False,
        description="True if documents indicate a public-sector or government-issued project",
    )
    detection_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0) for procurement signal detection",
    )
    indicators: list[str] = Field(
        default_factory=list,
        description="Highlighted indicators or phrases supporting the detection",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Additional context or caveats returned by the analyzer",
    )
    source_pages: list[int] = Field(
        default_factory=list,
        description="Page numbers (1-indexed) used to determine procurement context",
    )


class DocumentAnalysis(BaseModel):
    """Complete document analysis result."""

    project_type: Literal[
        "row_house",
        "commercial",
        "small_commercial",
        "multi_family",
        "institutional",
        "mixed",
        "single_family",
        "unknown",
    ] = Field(description="Project type (Phase 10.7: expanded typologies)")
    scope_type: Literal[
        "repair",
        "renovation",
        "new_construction",
        "mixed",
        "unknown",
    ] = Field(description="Type of scope")
    sheets: list[SheetInfo] = Field(
        default_factory=list, description="List of identified sheets"
    )
    where_scope_lives: list[ScopeLocator] = Field(
        default_factory=list, description="Locations where scope information is found"
    )
    where_quantities_live: list[QuantityLocator] = Field(
        default_factory=list,
        description="Locations where quantity information is found",
    )
    where_materials_live: list[MaterialLocator] = Field(
        default_factory=list,
        description="Locations where material information is found",
    )
    building_context: BuildingContext | None = Field(
        default=None, description="Building context information"
    )
    site_context: SiteContext | None = Field(
        default=None,
        description="Site/row context with explicit provenance tracking (Task 3)",
    )
    key_dimensions: KeyDimensions | None = Field(
        default=None, description="Key dimensions if found"
    )
    critical_expected_items: list[CriticalExpectedItem] = Field(
        default_factory=list,
        description="Critical items expected for this project type",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in the analysis",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="List of fields that could not be determined",
    )
    # Typology resolution fields (set by TypologyResolver)
    resolved_project_type: Literal[
        "row_house",
        "commercial",
        "small_commercial",
        "multi_family",
        "institutional",
        "mixed",
        "single_family",
        "unknown",
    ] | None = Field(
        default=None,
        description="Resolved project type after typology correction (if override occurred) (Phase 10.7)",
    )
    resolved_scope_type: Literal[
        "repair",
        "renovation",
        "new_construction",
        "mixed",
        "unknown",
    ] | None = Field(
        default=None,
        description="Resolved scope type after typology correction (if override occurred)",
    )
    resolution_notes: list[str] = Field(
        default_factory=list,
        description="Explanations for any typology overrides applied",
    )
    # Primary trade detection fields (set by TradeDominanceDetector)
    primary_division: str | None = Field(
        default=None,
        description="Primary division (e.g., '07' for Roofing, '04' for Masonry) - detected before typology resolution",
    )
    primary_trade: str | None = Field(
        default=None,
        description="Primary trade name (e.g., 'roofing', 'masonry') - detected before typology resolution",
    )
    trade_detection_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in primary trade detection (0.0-1.0)",
    )
    # Task 6: Labor regime detection (for public work / DOT projects)
    labor_regime: Literal["standard", "prevailing_wage", "union", "unknown"] = Field(
        default="standard",
        description="Labor regime: standard, prevailing_wage (DOT/public work), union, or unknown",
    )
    labor_regime_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in labor regime detection (0.0-1.0)",
    )
    labor_regime_evidence: str | None = Field(
        default=None,
        description="Evidence for labor regime detection (e.g., 'DOT project', 'prevailing wage required')",
    )
    procurement_context: ProcurementContext | None = Field(
        default=None,
        description="Detected procurement/compliance context with supporting metadata",
    )
    requires_prevailing_wage: bool | None = Field(
        default=None,
        description="Whether prevailing-wage labor adjustments are likely required",
    )
    requires_bonds: bool | None = Field(
        default=None,
        description="Whether payment/performance bonds appear to be required",
    )
    issuing_authority: str | None = Field(
        default=None,
        description="Detected issuing agency or authority for the project, if any",
    )

