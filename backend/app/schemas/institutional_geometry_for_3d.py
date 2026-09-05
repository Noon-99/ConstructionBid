"""Schema for institutional geometry-for-3D (Phase 4.5)."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class CoordinateSystem(BaseModel):
    """Coordinate system definition."""

    unit: Literal["feet"] = Field(default="feet", description="Unit of measurement")
    origin: dict[str, float] = Field(
        default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0},
        description="Origin point coordinates",
    )


class BuildingMass(BaseModel):
    """Building mass (existing or addition)."""

    mass_id: str = Field(description="Unique identifier for this mass")
    label: Literal["existing", "addition"] = Field(description="Mass type label")
    dimensions: dict[str, float | None] = Field(
        description="Dimensions: width_ft, depth_ft, height_ft (nullable)"
    )
    area_gsf: float = Field(description="Gross square feet (required if known)")
    bbox: dict[str, dict[str, float]] | None = Field(
        default=None,
        description="Bounding box: {min: {x, y, z}, max: {x, y, z}} if dimensions known",
    )
    placement: dict[str, Any] = Field(
        default_factory=lambda: {
            "x_offset_ft": 0.0,
            "y_offset_ft": 0.0,
            "relation": "adjacent_unknown",
        },
        description="Placement relative to existing building",
    )
    evidence: dict[str, Any] = Field(
        description="Evidence: {page_number, sheet_id?, evidence_snippet}"
    )


class RoomZoneVolume(BaseModel):
    """Room zone as a 3D volume."""

    room_number: str | None = Field(
        default=None, description="Room number/identifier if available"
    )
    room_name: str = Field(description="Room name")
    area_sf: float = Field(description="Room area in square feet")
    floor: str | None = Field(default=None, description="Floor level if known")
    zone_id: str = Field(description="Unique zone identifier")
    bbox: dict[str, dict[str, float]] = Field(
        description="Bounding box: {min: {x, y, z}, max: {x, y, z}}"
    )
    assignment_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in room assignment (0.0 to 1.0)",
    )
    evidence: dict[str, Any] = Field(
        description="Evidence: {page_number, evidence_snippet}"
    )
    notes: str | None = Field(
        default=None,
        description="Optional notes (e.g., 'stacked approximation', 'layout unknown')",
    )


class RoofVolume(BaseModel):
    """Roof volume for 3D representation (Phase 7.2)."""

    roof_id: str = Field(description="Roof identifier")
    bbox: dict[str, dict[str, float]] = Field(
        description="Bounding box: {min: {x, y, z}, max: {x, y, z}}"
    )
    parapet_height_ft: float | None = Field(
        default=None, description="Parapet height in feet if present"
    )
    evidence: dict[str, Any] = Field(
        description="Evidence: {page_number, evidence_snippet}"
    )


class StructuralZone(BaseModel):
    """Structural zone (columns, bearing walls) for 3D representation (Phase 7.2)."""

    zone_id: str = Field(description="Zone identifier")
    element_type: Literal["column", "bearing_wall", "footing", "beam"] = Field(
        description="Type of structural element"
    )
    bbox: dict[str, dict[str, float]] = Field(
        description="Bounding box: {min: {x, y, z}, max: {x, y, z}}"
    )
    evidence: dict[str, Any] = Field(
        description="Evidence: {page_number, evidence_snippet}"
    )


class EnvelopeLayer(BaseModel):
    """Envelope layer (coarse volume) for 3D representation (Phase 7.2)."""

    layer_id: str = Field(description="Layer identifier")
    layer_type: Literal["exterior_wall", "roof", "parapet"] = Field(
        description="Type of envelope layer"
    )
    bbox: dict[str, dict[str, float]] = Field(
        description="Bounding box: {min: {x, y, z}, max: {x, y, z}}"
    )
    evidence: dict[str, Any] = Field(
        description="Evidence: {page_number, evidence_snippet}"
    )


class OpeningCutout(BaseModel):
    """Window/door cutout in facade geometry (Phase 7.3)."""

    opening_id: str = Field(description="Opening identifier")
    bbox: dict[str, dict[str, float]] = Field(
        description="Bounding box: {min: {x, y, z}, max: {x, y, z}}"
    )
    opening_type: Literal["window", "door", "opening"] = Field(
        description="Type of opening"
    )
    evidence: dict[str, Any] = Field(
        description="Evidence: {page_number, evidence_snippet}"
    )


class LintelBand(BaseModel):
    """Lintel band above openings (Phase 7.3)."""

    lintel_id: str = Field(description="Lintel identifier")
    bbox: dict[str, dict[str, float]] = Field(
        description="Bounding box: {min: {x, y, z}, max: {x, y, z}}"
    )
    associated_openings: list[str] = Field(
        default_factory=list, description="List of opening IDs"
    )
    evidence: dict[str, Any] = Field(
        description="Evidence: {page_number, evidence_snippet}"
    )


class FlashingBand(BaseModel):
    """Flashing band at openings (Phase 7.3)."""

    flashing_id: str = Field(description="Flashing identifier")
    bbox: dict[str, dict[str, float]] = Field(
        description="Bounding box: {min: {x, y, z}, max: {x, y, z}}"
    )
    associated_openings: list[str] = Field(
        default_factory=list, description="List of opening IDs"
    )
    evidence: dict[str, Any] = Field(
        description="Evidence: {page_number, evidence_snippet}"
    )


class InstitutionalGeometryFor3D(BaseModel):
    """Institutional geometry for 3D model generation (Phase 4.5, 7.2)."""

    coordinate_system: CoordinateSystem = Field(
        default_factory=CoordinateSystem, description="Coordinate system definition"
    )
    existing_building: BuildingMass = Field(description="Existing building mass")
    addition_building: BuildingMass | None = Field(
        default=None, description="Addition building mass if present"
    )
    room_zones: list[RoomZoneVolume] = Field(
        default_factory=list, description="List of room zone volumes"
    )
    roof_volumes: list[RoofVolume] = Field(
        default_factory=list, description="Roof volumes (Phase 7.2)"
    )
    structural_zones: list[StructuralZone] = Field(
        default_factory=list, description="Structural zones (Phase 7.2)"
    )
    envelope_layers: list[EnvelopeLayer] = Field(
        default_factory=list, description="Envelope layers (Phase 7.2)"
    )
    opening_cutouts: list[OpeningCutout] = Field(
        default_factory=list, description="Window/door cutouts (Phase 7.3)"
    )
    lintel_bands: list[LintelBand] = Field(
        default_factory=list, description="Lintel bands (Phase 7.3)"
    )
    flashing_bands: list[FlashingBand] = Field(
        default_factory=list, description="Flashing bands (Phase 7.3)"
    )
    geometry_quality: Literal[
        "authoritative", "derived_from_area", "partial", "missing"
    ] = Field(
        description="Quality indicator for geometry data"
    )
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="List of missing evidence fields (e.g., 'height', 'addition_placement')",
    )

