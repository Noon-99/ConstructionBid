"""Schema for structural elements extraction (Phase 7.2)."""

from typing import Literal

from pydantic import BaseModel, Field


class StructuralElementDimensions(BaseModel):
    """Dimensions for a structural element."""

    width_ft: float | None = Field(default=None, description="Width in feet")
    depth_ft: float | None = Field(default=None, description="Depth in feet")
    height_ft: float | None = Field(default=None, description="Height in feet")
    length_ft: float | None = Field(default=None, description="Length in feet (for beams, lintels)")
    section: str | None = Field(
        default=None, description="Section designation (e.g., 'W12x26', 'HSS6x6x1/4')"
    )
    diameter_in: float | None = Field(default=None, description="Diameter in inches (for columns)")
    thickness_in: float | None = Field(default=None, description="Thickness in inches (for walls)")


class MaterialSpecification(BaseModel):
    """Material specification for structural element."""

    astm: str | None = Field(default=None, description="ASTM designation (e.g., 'ASTM A36', 'ASTM A992')")
    psi: float | None = Field(default=None, description="Strength in PSI (e.g., 3000 for concrete)")
    grade: str | None = Field(default=None, description="Grade designation (e.g., 'Grade 60' for rebar)")
    unit_strength: float | None = Field(
        default=None, description="Unit strength (e.g., CMU unit strength PSI)"
    )


class StructuralElement(BaseModel):
    """A structural element extracted from drawings."""

    element_type: Literal[
        "footing",
        "slab",
        "bearing_wall",
        "column",
        "beam",
        "lintel",
        "cmu_wall",
        "shoring",
    ] = Field(description="Type of structural element")
    element_id: str | None = Field(
        default=None, description="Element identifier (e.g., 'F-1', 'C-2', 'B-3')"
    )
    dimensions: StructuralElementDimensions = Field(description="Element dimensions")
    material_spec: MaterialSpecification = Field(description="Material specification")
    quantity: float | None = Field(
        default=None, description="Quantity (units depend on element_type)"
    )
    unit: str | None = Field(
        default=None, description="Unit of measurement (e.g., 'LF', 'EA', 'SF', 'CY')"
    )
    location: str | None = Field(
        default=None, description="Location description (e.g., 'North wall', 'Grid A-B')"
    )
    page_number: int = Field(description="Page number where element was found (1-indexed)")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    detail_reference: str | None = Field(
        default=None, description="Detail sheet reference (e.g., 'S-2 Detail 3')"
    )
    evidence_snippet: str = Field(
        description="Evidence snippet showing where element was found"
    )


class StructuralElementsResult(BaseModel):
    """Complete structural elements extraction result."""

    elements: list[StructuralElement] = Field(
        default_factory=list, description="List of extracted structural elements"
    )
    missing_fields: list[str] = Field(
        default_factory=list, description="Fields that could not be determined"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in extraction (0.0 to 1.0)",
    )






