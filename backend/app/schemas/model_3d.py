"""Schema for 3D model generation output."""

from typing import Literal

from pydantic import BaseModel, Field


class Vector3D(BaseModel):
    """3D vector/point."""

    x: float = Field(description="X coordinate in feet")
    y: float = Field(description="Y coordinate in feet")
    z: float = Field(description="Z coordinate in feet")


class BoundingBox(BaseModel):
    """Bounding box for a 3D object."""

    min: Vector3D = Field(description="Minimum corner")
    max: Vector3D = Field(description="Maximum corner")


class BuildingVolume(BaseModel):
    """Building volume definition."""

    building_id: str | None = Field(default=None, description="Building identifier")
    building_type: Literal["row_house", "garage", "adjacent", "institutional"] = Field(
        description="Type of building"
    )
    bounding_box: BoundingBox = Field(description="Bounding box of the building")
    is_subject: bool = Field(
        default=False, description="True if this is the subject building being repaired"
    )
    evidence: str = Field(description="Evidence for this building volume")
    material_tags: list[str] = Field(
        default_factory=list,
        description="Material tags for this building (e.g., ['brick_veneer', 'cmu', 'steel']) (Phase 10.5)",
    )
    material_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in material tags (0.0 to 1.0) (Phase 10.5)",
    )


class WorkZoneVolume(BaseModel):
    """Work zone volume for highlighting repair areas or room zones (Phase 4.5)."""

    zone_name: str = Field(description="Zone identifier (e.g., 'parapet_band', 'lintel_band', 'Gymnasium')")
    bounding_box: BoundingBox | None = Field(
        default=None, description="Bounding box if Z coordinates available"
    )
    facade_region: str | None = Field(
        default=None, description="Facade region if Z coordinates unavailable"
    )
    page_number: int = Field(description="Page where zone is defined")
    evidence: str = Field(description="Evidence for work zone")
    zone_type: Literal["work_zone", "room", "building_mass"] | None = Field(
        default=None, description="Zone type (Phase 4.5: 'room' for institutional, 'work_zone' for row-house)"
    )
    material_tags: list[str] = Field(
        default_factory=list,
        description="Material tags for this zone (e.g., ['brick_veneer', 'flashing', 'mortar']) (Phase 10.5)",
    )
    material_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in material tags (0.0 to 1.0) (Phase 10.5)",
    )


class WindowOpening(BaseModel):
    """Window opening definition."""

    window_id: str = Field(description="Window identifier")
    bounding_box: BoundingBox = Field(description="Window opening bounding box")
    floor_level: int | None = Field(default=None, description="Floor level if known")
    evidence: str = Field(description="Evidence for window location")


class CrossSectionRegion(BaseModel):
    """Cross-section region for semantic navigation (Phase 7.4).

    These are regions, not drawings. Used for navigation, not visualization accuracy.
    """

    region_id: str = Field(description="Region identifier")
    region_type: Literal[
        "wall_assembly", "parapet", "roof_edge", "floor_to_floor", "foundation"
    ] = Field(description="Type of cross-section region")
    bounding_box: BoundingBox = Field(description="Bounding box of the region")
    applies_to: list[str] = Field(
        default_factory=list,
        description="List of element IDs this region applies to (zones, buildings)",
    )
    detail_refs: list[str] = Field(
        default_factory=list,
        description="List of detail IDs that govern this region",
    )
    evidence: str = Field(description="Evidence for region definition")


class GroundPlane(BaseModel):
    """Ground plane definition for 3D visualization (Task 4)."""

    size: float = Field(
        default=100.0, description="Size of ground plane in feet (square)"
    )
    center: Vector3D = Field(
        default=Vector3D(x=0.0, y=0.0, z=0.0), description="Center point of ground plane"
    )


class AxisLabel(BaseModel):
    """Axis label for 3D visualization (Task 4)."""

    direction: Literal["street_front", "rear_yard", "left", "right"] = Field(
        description="Direction label"
    )
    vector: Vector3D = Field(description="Direction vector")
    label: str = Field(description="Label text (e.g., 'Street Front')")


class GhostNeighbor(BaseModel):
    """Ghost neighbor building for row context visualization (Task 4)."""

    building_id: str = Field(description="Neighbor building ID (e.g., 'adjacent_left', 'adjacent_right')")
    bounding_box: BoundingBox = Field(description="Bounding box of ghost neighbor")
    opacity: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Opacity (0.0-1.0), typically 0.15-0.25 for ghost buildings",
    )
    label: str = Field(
        default="Adjacent (approx)",
        description="Label indicating this is approximate, not evidence-based",
    )


class DimensionHUD(BaseModel):
    """Dimension HUD for 3D viewer (Task 5)."""

    width_ft: float | None = Field(default=None, description="Width in feet")
    depth_ft: float | None = Field(default=None, description="Depth in feet")
    height_ft: float | None = Field(default=None, description="Height in feet")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in dimensions (0.0-1.0)",
    )
    provenance: str = Field(
        default="unknown",
        description="Provenance of dimensions (e.g., 'explicit_callout', 'computed', 'unknown')",
    )


class Geometry3D(BaseModel):
    """3D geometry information."""

    site_origin: Vector3D = Field(
        default=Vector3D(x=0.0, y=0.0, z=0.0), description="Site origin point"
    )
    units: Literal["feet"] = Field(default="feet", description="Unit of measurement")
    coordinate_system: str = Field(
        default="right_handed_y_up", description="Coordinate system convention"
    )
    ground_plane: GroundPlane | None = Field(
        default=None, description="Ground plane for visualization (Task 4)"
    )
    axis_labels: list[AxisLabel] = Field(
        default_factory=list, description="Axis labels for street/rear yard (Task 4)"
    )
    ghost_neighbors: list[GhostNeighbor] = Field(
        default_factory=list, description="Ghost neighbor buildings for row context (Task 4)"
    )
    dimension_hud: DimensionHUD | None = Field(
        default=None, description="Dimension HUD for 3D viewer (Task 5)"
    )


class Materials3D(BaseModel):
    """Material assignments for 3D model."""

    building_materials: dict[str, str] = Field(
        default_factory=dict,
        description="Material assignments by building ID (e.g., {'B-1': 'brick_masonry'})",
    )
    work_zone_materials: dict[str, str] = Field(
        default_factory=dict,
        description="Material assignments by work zone (e.g., {'parapet_band': 'repair_zone'})",
    )


class Model3D(BaseModel):
    """Complete 3D model output."""

    buildings: list[BuildingVolume] = Field(
        default_factory=list, description="Building volumes in the model"
    )
    geometry: Geometry3D = Field(description="3D geometry metadata")
    work_zones: list[WorkZoneVolume] = Field(
        default_factory=list, description="Work zone volumes for highlighting"
    )
    windows: list[WindowOpening] = Field(
        default_factory=list, description="Window openings if geometry available"
    )
    cross_section_regions: list[CrossSectionRegion] = Field(
        default_factory=list,
        description="Cross-section regions for semantic navigation (Phase 7.4)",
    )
    materials: Materials3D = Field(description="Material assignments")
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="Missing geometry information that prevented full model generation",
    )
    geometry_quality: Literal["authoritative", "partial", "ok", "missing"] | None = Field(
        default=None,
        description="Quality of geometry data (Phase 9: 'ok' if zones >= 8 and >= 2 have evidence, 'partial' if zones < 8, 'authoritative' if all zones have evidence)",
    )

