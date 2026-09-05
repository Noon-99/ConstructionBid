"""Schema for trade assemblies (Phase 9.1).

Trade assemblies break down bid line items into material components,
labor requirements, equipment needs, and specifications.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence_index import EvidenceReference


class TradeComponent(BaseModel):
    """A material or accessory component within a trade assembly."""

    name: str = Field(description="Component name (e.g., 'Aluminum Coping', 'Mortar Mix Type N')")
    unit: str = Field(description="Unit of measurement (e.g., 'LF', 'SF', 'EA', 'Bag', 'CY')")
    qty: float = Field(ge=0.0, description="Quantity needed for this component")
    unit_cost: float | None = Field(
        default=None, ge=0.0, description="Unit cost in dollars. None if cost_source is 'derived'."
    )
    total_cost: float = Field(ge=0.0, description="Total cost for this component (qty × unit_cost)")
    cost_source: Literal["ruleset", "bid_item", "derived"] = Field(
        description="Source of cost: 'ruleset' = from YAML rules, 'bid_item' = inherited from bid, 'derived' = calculated"
    )
    notes: str | None = Field(
        default=None, description="Additional notes about this component (e.g., waste factor applied)"
    )


class LaborComponent(BaseModel):
    """A labor requirement within a trade assembly."""

    trade: str = Field(description="Trade name (e.g., 'mason', 'laborer', 'carpenter', 'foreman')")
    crew: list[str] = Field(
        default_factory=list,
        description="Crew composition (e.g., ['mason', 'laborer']). Empty if single trade.",
    )
    hours: float = Field(ge=0.0, description="Total labor hours required")
    rate: float | None = Field(
        default=None, ge=0.0, description="Hourly rate in dollars. None if rate not yet determined."
    )
    total_cost: float = Field(ge=0.0, description="Total labor cost (hours × rate)")
    basis: str = Field(
        description="Basis for labor hours calculation (e.g., 'Q * 0.5 hours per LF', 'Productivity: 50 SF/day')"
    )


class EquipmentComponent(BaseModel):
    """An equipment requirement within a trade assembly."""

    name: str = Field(description="Equipment name (e.g., 'Scaffold', 'Forklift', 'Concrete Mixer')")
    unit: str = Field(description="Unit of measurement (e.g., 'Week', 'Day', 'EA', 'Hour')")
    qty: float = Field(ge=0.0, description="Quantity needed")
    unit_cost: float | None = Field(
        default=None, ge=0.0, description="Unit cost in dollars. None if cost_source is 'derived'."
    )
    total_cost: float = Field(ge=0.0, description="Total cost (qty × unit_cost)")
    basis: str = Field(
        description="Basis for equipment requirement (e.g., 'Scaffolding required for exterior masonry work')"
    )


class TradeAssembly(BaseModel):
    """A trade assembly breaking down a bid line item into components."""

    id: str = Field(description="Unique identifier for this assembly (e.g., 'parapet_repair_001')")
    title: str = Field(description="Assembly title (e.g., 'Parapet Repair and Rebuild')")
    division: str = Field(description="CSI division (e.g., '04 Masonry', '07 56 00 Flashing')")
    unit: str = Field(description="Unit of measurement for the assembly (e.g., 'LF', 'SF', 'EA')")
    quantity: float = Field(ge=0.0, description="Quantity of the assembly (from bid line item)")
    related_bid_item_ids: list[str] = Field(
        default_factory=list,
        description="List of bid item IDs this assembly relates to (string indices from bid_proposal)",
    )
    components: list[TradeComponent] = Field(
        default_factory=list, description="Material and accessory components"
    )
    labor: list[LaborComponent] = Field(default_factory=list, description="Labor requirements")
    equipment: list[EquipmentComponent] = Field(
        default_factory=list, description="Equipment requirements"
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions for this assembly (e.g., 'Access via existing stair', 'Weather permitting')",
    )
    spec_refs: list[str] = Field(
        default_factory=list,
        description="Specification references (e.g., '04 21 13', 'Section 7.6.2')",
    )
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list, description="Linked evidence references from drawings"
    )
    ruleset_used: str | None = Field(
        default=None,
        description="Ruleset file used to generate this assembly (e.g., 'row_house_repair.yml')",
    )


class TradeAssembliesResult(BaseModel):
    """Complete trade assemblies result (Phase 9.1)."""

    project_id: str = Field(description="Project ID this result applies to")
    assemblies: list[TradeAssembly] = Field(
        default_factory=list, description="List of trade assemblies"
    )
    generated_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp when assemblies were generated"
    )
    version: str = Field(default="1.0", description="Schema version for forward compatibility")





