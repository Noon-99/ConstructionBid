"""Schemas for cost engine and costing results."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.rule_governance import RuleGovernanceReport


QuantitySource = Literal[
    "from_drawing",
    "from_schedule",
    "computed_from_dimensions",
    "allowance",
    "heuristic",
    "unknown",
]


class CostItem(BaseModel):
    """Individual cost item with breakdown."""

    item_name: str = Field(description="Name of the cost item (e.g., 'Parapet Rebuild')")
    scope_item: str | None = Field(
        default=None, description="Associated scope item from extraction"
    )
    quantity: float = Field(description="Quantity for this cost item")
    unit: str = Field(description="Unit type (EA, LF, SF, CY)")
    unit_cost: float = Field(description="Cost per unit")
    material_cost: float = Field(default=0.0, description="Material cost component")
    labor_cost: float = Field(default=0.0, description="Labor cost component")
    equipment_cost: float = Field(default=0.0, description="Equipment cost component")
    waste_factor: float = Field(default=0.0, description="Waste factor applied")
    multipliers: dict[str, float] = Field(
        default_factory=dict, description="Applied multipliers (height, accessibility, etc.)"
    )
    subtotal: float = Field(description="Subtotal for this item (quantity * unit_cost * multipliers)")
    rule_matched: str | None = Field(
        default=None, description="Name of the cost rule that matched"
    )
    evidence: str = Field(description="Evidence or justification for this cost")
    notes: list[str] = Field(default_factory=list, description="Additional notes")
    # Phase 4.7: Quantity provenance
    quantity_source: QuantitySource = Field(
        default="unknown", description="Source of the quantity (from_drawing, from_schedule, computed_from_dimensions, allowance, heuristic, unknown)"
    )
    quantity_confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence in the quantity (0.0 to 1.0)"
    )
    quantity_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Evidence for quantity (page_number, sheet_id, evidence_snippet, computation_formula, etc.)",
    )
    detail_refs: list[str] = Field(
        default_factory=list,
        description="List of detail IDs that govern this cost item (Phase 7.4)",
    )
    # Phase 10.10B: Pricing profile traceability
    profile_id: str | None = Field(
        default=None, description="Pricing profile ID used for this item (Phase 10.10B)"
    )
    multiplier_breakdown: list[str] = Field(
        default_factory=list,
        description="List of profile multipliers applied (e.g., ['labor_rate: nyc', 'material_multiplier: +12%']) (Phase 10.10B)",
    )
    override_source: Literal["manual_override", "extracted", "computed", "unknown"] = Field(
        default="unknown",
        description="Indicates whether this cost used manual overrides or extracted values",
    )


class CostBreakdown(BaseModel):
    """Cost breakdown by category."""

    category: str = Field(description="Category name (e.g., 'Masonry', 'Structural')")
    items: list[CostItem] = Field(default_factory=list, description="Cost items in this category")
    subtotal: float = Field(description="Subtotal for this category")


class CostEngineResult(BaseModel):
    """Complete cost engine result."""

    project_id: str = Field(description="Project ID")
    breakdown_by_category: list[CostBreakdown] = Field(
        default_factory=list, description="Cost breakdown by category"
    )
    breakdown_by_scope_item: list[CostItem] = Field(
        default_factory=list, description="Cost items grouped by scope item"
    )
    breakdown_by_building: dict[str, list[CostItem]] = Field(
        default_factory=dict, description="Cost items grouped by building ID"
    )
    subtotals: dict[str, float] = Field(
        default_factory=dict,
        description="Subtotals by category (e.g., {'Masonry': 15000.0, 'Structural': 5000.0})",
    )
    total_cost: float = Field(description="Total project cost")
    material_cost_total: float = Field(default=0.0, description="Total material cost")
    labor_cost_total: float = Field(default=0.0, description="Total labor cost")
    equipment_cost_total: float = Field(default=0.0, description="Total equipment cost")
    waste_cost_total: float = Field(default=0.0, description="Total waste cost")
    cost_justification: list[str] = Field(
        default_factory=list, description="Justification notes for cost calculations"
    )
    missing_data_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about missing data that affected cost accuracy",
    )
    rules_used: list[str] = Field(
        default_factory=list, description="List of cost rule files that were applied"
    )
    # Phase 10.10B: Pricing profile traceability
    profile_id: str | None = Field(
        default=None, description="Pricing profile ID used for this costing result (Phase 10.10B)"
    )
    compliance_adjustments: list[str] = Field(
        default_factory=list,
        description="Compliance-driven adjustments applied to this costing run (e.g., prevailing wage, union multipliers, bonds)",
    )
    compliance_costs: dict[str, float] = Field(
        default_factory=dict,
        description="Breakdown of compliance cost adders by type (e.g., {'bond': 2500.0, 'insurance': 1200.0})",
    )
    compliance_total: float = Field(
        default=0.0,
        description="Total compliance cost added to the project (sum of compliance_costs)",
    )
    base_scope_cost: float = Field(
        default=0.0,
        description="Total cost prior to compliance adders (materials + labor + equipment + waste)",
    )
    contingency_recommendation_pct: float | None = Field(
        default=None,
        description="Recommended contingency percentage based on project context and risk",
    )
    contingency_recommendation_amount: float | None = Field(
        default=None,
        description="Dollar amount associated with the recommended contingency",
    )
    rule_governance: RuleGovernanceReport | None = Field(
        default=None,
        description="Governance report capturing scope items that lack cost rules and draft generation status",
    )
