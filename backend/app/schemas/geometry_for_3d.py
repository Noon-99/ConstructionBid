"""Schema for 3D geometry extraction results."""

from typing import Literal

from pydantic import BaseModel, Field


class SiteContext(BaseModel):
    """Site context for construction projects."""

    building_type: Literal["row_house", "institutional", "commercial", "mixed", "single_family", "unknown"] = Field(description="Building type")
    row_of_buildings: list[str] = Field(
        default_factory=list,
        description="Building IDs in the row (e.g., ['B-1', 'B-2', 'B-3'])",
    )
    subject_building_id: str | None = Field(
        default=None, description="ID of the subject building being repaired"
    )
    addresses: list[str] = Field(
        default_factory=list, description="Addresses of buildings in the row"
    )
    evidence: str = Field(description="Evidence for site context")


class Dimensions(BaseModel):
    """Building dimensions with evidence."""

    width: float | None = Field(default=None, description="Width in feet")
    depth: float | None = Field(default=None, description="Depth in feet")
    height: float | None = Field(default=None, description="Height in feet")
    evidence: str = Field(description="Where dimensions were found or how computed")
    computation_formula: str | None = Field(
        default=None, description="Formula if computed (e.g., 'sum(elevation_dimensions)')"
    )
    input_pages: list[int] = Field(
        default_factory=list, description="Page numbers used for computation"
    )


class WorkZone(BaseModel):
    """Work zone definition for 3D representation."""

    zone_name: str = Field(
        description="Zone identifier (e.g., 'parapet_band', 'lintel_band', 'facade_repair')"
    )
    z_min: float | None = Field(
        default=None, description="Minimum Z coordinate in feet (if height info exists)"
    )
    z_max: float | None = Field(
        default=None, description="Maximum Z coordinate in feet (if height info exists)"
    )
    facade_region: str | None = Field(
        default=None,
        description="Facade region if height unavailable (e.g., 'parapet band', 'lintel band')",
    )
    page_number: int = Field(description="Page where zone is defined")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence: str = Field(description="Evidence for work zone")


class GeometryFor3D(BaseModel):
    """Complete geometry information for 3D reconstruction."""

    site_context: SiteContext = Field(description="Site and building context")
    dimensions: Dimensions | None = Field(
        default=None, description="Building dimensions if available"
    )
    work_zones: list[WorkZone] = Field(
        default_factory=list, description="Work zones with Z ranges or facade regions"
    )
    evidence_missing: list[str] = Field(
        default_factory=list,
        description="List of missing geometry information (e.g., 'height', 'work_zone_z_ranges')",
    )

