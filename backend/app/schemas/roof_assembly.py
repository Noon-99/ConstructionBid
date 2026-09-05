"""Roof assembly schema for Task 2: Assembly-level roof pricing."""

from typing import Literal

from pydantic import BaseModel, Field


class RoofAssembly(BaseModel):
    """
    Minimal roof assembly model used only when primary_trade == 'roofing'.
    
    Task 2: This represents the primary roof system assembly that dominates
    roof replacement pricing.
    """

    roof_area_sf: float = Field(
        gt=0.0,
        description="Roof area in square feet (required for pricing)",
    )
    system_type: Literal[
        "TPO",
        "EPDM",
        "PVC",
        "Modified bitumen",
        "Built-up roof",
        "BUR",
        "Metal",
        "Single-ply",
        "Unknown",
    ] = Field(
        default="Unknown",
        description="Roof membrane system type",
    )
    insulation_thickness_in: float | None = Field(
        default=None,
        ge=0.0,
        description="Insulation thickness in inches (optional)",
    )
    tearoff_included: bool = Field(
        default=True,
        description="Whether tear-off of existing roof is included in this assembly",
    )
    # Task 4: Tear-off & disposal fields
    tearoff_scope: Literal["full", "partial", "none", "unknown"] = Field(
        default="unknown",
        description="Tear-off scope: full (entire roof), partial (specific areas), none (overlay), or unknown",
    )
    disposal_requirement: str | None = Field(
        default=None,
        description="Disposal requirements if specified (e.g., 'dumpster required', 'off-site disposal', 'recycling required')",
    )
    # Task 5: Perimeter and edge metal fields
    perimeter_length_lf: float | None = Field(
        default=None,
        ge=0.0,
        description="Roof perimeter length in linear feet (from roof plan or building dimensions)",
    )
    edge_metal_lf: float | None = Field(
        default=None,
        ge=0.0,
        description="Edge metal/coping linear feet if specified",
    )
    base_flashing_lf: float | None = Field(
        default=None,
        ge=0.0,
        description="Base flashing linear feet if specified",
    )
    perimeter_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in perimeter length (0.0-1.0). Lower if inferred from dimensions.",
    )
    evidence: str = Field(
        description="Evidence for roof assembly extraction (page numbers, spec references, etc.)",
    )

