"""Schema for building envelope elements extraction (Phase 7.2)."""

from typing import Literal

from pydantic import BaseModel, Field


class EnvelopeWall(BaseModel):
    """Exterior wall system."""

    wall_id: str | None = Field(default=None, description="Wall identifier")
    wall_type: Literal["brick_veneer", "cmu_backup", "eifs", "concrete", "metal_panel"] = Field(
        description="Type of wall system"
    )
    area_sf: float | None = Field(default=None, description="Wall area in square feet")
    height_ft: float | None = Field(default=None, description="Wall height in feet")
    length_ft: float | None = Field(default=None, description="Wall length in feet")
    material_spec: str | None = Field(
        default=None, description="Material specification (e.g., '8\" CMU', '4\" brick')"
    )
    location: str | None = Field(
        default=None, description="Location (e.g., 'North elevation', 'East facade')"
    )
    page_number: int = Field(description="Page number where wall was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Evidence snippet")


class RoofSystem(BaseModel):
    """Roof system components."""

    roof_id: str | None = Field(default=None, description="Roof identifier")
    deck_type: Literal["concrete", "steel", "wood", "composite"] | None = Field(
        default=None, description="Deck type"
    )
    insulation_type: str | None = Field(
        default=None, description="Insulation type (e.g., 'R-30 rigid', 'spray foam')"
    )
    membrane_type: Literal["epdm", "tpo", "pvc", "modified_bitumen", "built_up"] | None = Field(
        default=None, description="Roof membrane type"
    )
    area_sf: float | None = Field(default=None, description="Roof area in square feet")
    parapet_height_ft: float | None = Field(
        default=None, description="Parapet height in feet if present"
    )
    page_number: int = Field(description="Page number where roof was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Evidence snippet")


class FlashingSystem(BaseModel):
    """Flashing system component."""

    flashing_id: str | None = Field(default=None, description="Flashing identifier")
    flashing_type: Literal[
        "lintel_flashing",
        "coping",
        "drip_edge",
        "base_flashing",
        "counter_flashing",
        "through_wall",
    ] = Field(description="Type of flashing")
    length_lf: float | None = Field(default=None, description="Length in linear feet")
    material: str | None = Field(
        default=None, description="Material (e.g., 'Copper', 'Galvanized steel', 'Aluminum')"
    )
    location: str | None = Field(
        default=None, description="Location (e.g., 'Parapet coping', 'Window lintels')"
    )
    page_number: int = Field(description="Page number where flashing was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    detail_reference: str | None = Field(
        default=None, description="Detail sheet reference"
    )
    evidence_snippet: str = Field(description="Evidence snippet")


class Opening(BaseModel):
    """Window or door opening."""

    opening_id: str | None = Field(default=None, description="Opening identifier")
    opening_type: Literal["window", "door", "opening"] = Field(description="Type of opening")
    count: int | None = Field(default=None, description="Count of openings")
    type_description: str | None = Field(
        default=None, description="Type description (e.g., 'Double-hung window', 'Steel door')"
    )
    size: str | None = Field(
        default=None, description="Size (e.g., '3-0 x 6-8', '4-0 x 7-0')"
    )
    location: str | None = Field(
        default=None, description="Location (e.g., 'North elevation', 'Main entrance')"
    )
    page_number: int = Field(description="Page number where opening was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Evidence snippet")


class BuildingEnvelopeResult(BaseModel):
    """Complete building envelope extraction result."""

    walls: list[EnvelopeWall] = Field(
        default_factory=list, description="List of exterior walls"
    )
    roof_systems: list[RoofSystem] = Field(
        default_factory=list, description="List of roof systems"
    )
    flashing_systems: list[FlashingSystem] = Field(
        default_factory=list, description="List of flashing systems"
    )
    openings: list[Opening] = Field(
        default_factory=list, description="List of openings (windows/doors)"
    )
    missing_fields: list[str] = Field(
        default_factory=list, description="Fields that could not be determined"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in extraction (0.0 to 1.0)",
    )






