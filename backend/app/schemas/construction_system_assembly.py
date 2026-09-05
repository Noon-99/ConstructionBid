"""Schema for construction system assemblies (Phase 14.1).

Construction system assemblies represent contractor-grade construction systems
that group related line items into logical construction systems (e.g., 
parapet_reconstruction, lintel_replacement).

This is different from trade_assemblies which break down line items into
material/labor components. System assemblies group items into systems.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence_index import EvidenceReference


class SystemSubcomponent(BaseModel):
    """A subcomponent category within a construction system."""

    category: Literal[
        "demolition",
        "structure",
        "waterproofing",
        "finish",
        "qa",
        "access",
        "other",
    ] = Field(description="Subcomponent category")
    description: str = Field(description="Description of work in this category")
    line_item_ids: list[str] = Field(
        default_factory=list, description="Bid line item IDs in this subcomponent"
    )


class QuantitySummary(BaseModel):
    """Summary of quantities for a construction system."""

    primary_quantity: float = Field(ge=0.0, description="Primary quantity value")
    primary_unit: str = Field(description="Primary unit (e.g., 'LF', 'SF', 'EA')")
    secondary_quantities: dict[str, float] = Field(
        default_factory=dict,
        description="Additional quantities with their units (e.g., {'SF': 120.0, 'EA': 8})",
    )


class CostSummary(BaseModel):
    """Summary of costs for a construction system."""

    material_cost: float = Field(ge=0.0, description="Total material cost")
    labor_cost: float = Field(ge=0.0, description="Total labor cost")
    equipment_cost: float = Field(ge=0.0, description="Total equipment cost")
    total_cost: float = Field(ge=0.0, description="Total system cost")


class ConstructionSystemAssembly(BaseModel):
    """A construction system assembly grouping related line items."""

    id: str = Field(
        description="Unique identifier (e.g., 'parapet_reconstruction_001', 'lintel_replacement_002')"
    )
    system_type: str = Field(
        description="System type (e.g., 'parapet_reconstruction', 'lintel_replacement', 'flashing_installation')"
    )
    description: str = Field(description="Human-readable description of the system")
    zones: list[str] = Field(
        default_factory=list,
        description="List of zone IDs from model_3d where this system applies",
    )
    source_divisions: list[str] = Field(
        default_factory=list,
        description="CSI divisions involved (e.g., ['04 Masonry', '07 56 00 Flashing'])",
    )
    base_scope_items: list[str] = Field(
        default_factory=list,
        description="List of bid line item IDs (string indices) included in this system",
    )
    subcomponents: list[SystemSubcomponent] = Field(
        default_factory=list,
        description="System subcomponents (demolition, structure, waterproofing, finish, QA, etc.)",
    )
    quantities: QuantitySummary = Field(description="Quantity summary for the system")
    cost_summary: CostSummary = Field(description="Cost breakdown for the system")
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list, description="Evidence references from drawings"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (minimum of included line item confidences)",
    )


class ConstructionSystemsResult(BaseModel):
    """Complete construction systems result (Phase 14.1)."""

    project_id: str = Field(description="Project ID this result applies to")
    systems: list[ConstructionSystemAssembly] = Field(
        default_factory=list, description="List of construction system assemblies"
    )
    generated_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp when systems were generated"
    )
    version: str = Field(
        default="1.0", description="Schema version for forward compatibility"
    )





