"""Schema for bid pricing v2 (Phase 10.2).

Pricing v2 architecture for multi-component cost breakdowns (materials, labor,
equipment, subcontract, overhead/profit) instead of single unit costs.
"""

from typing import Literal

from pydantic import BaseModel, Field


class PricingComponent(BaseModel):
    """Individual pricing component for a line item."""

    type: Literal[
        "material", "labor", "equipment", "subcontract", "overhead_profit"
    ] = Field(description="Component type")
    amount: float = Field(ge=0.0, description="Amount for this component")
    basis: str = Field(
        description="Explicit basis/explanation for this component pricing"
    )
    source_id: str | None = Field(
        default=None,
        description="Source identifier (e.g., profile_id, market_data_id)",
    )


class LineItemPricingV2(BaseModel):
    """Pricing v2 for a single line item."""

    line_item_id: str = Field(
        description="Line item identifier (matches bid_proposal line item index or description)"
    )
    title: str = Field(description="Line item title/description")
    unit: str | None = Field(
        default=None, description="Unit of measurement"
    )
    quantity: float | None = Field(
        default=None, description="Quantity"
    )
    components: list[PricingComponent] = Field(
        default_factory=list,
        description="Cost components for this line item",
    )
    total: float = Field(
        ge=0.0, description="Total cost (sum of all components)"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in this pricing (higher if profile data used)",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Additional notes about this pricing",
    )


class BidPricingV2(BaseModel):
    """Complete bid pricing v2 result (Phase 10.2)."""

    project_id: str = Field(description="Project ID")
    profile_id: str | None = Field(
        default=None, description="Contractor profile ID used (if any)"
    )
    region_id: str | None = Field(
        default=None, description="Region identifier (if known)"
    )
    line_items: list[LineItemPricingV2] = Field(
        default_factory=list, description="Pricing v2 for each line item"
    )
    totals_by_component: dict[str, float] = Field(
        default_factory=dict,
        description="Total amounts by component type (material, labor, equipment, subcontract, overhead_profit)",
    )
    grand_total: float = Field(
        ge=0.0, description="Grand total (sum of all line items)"
    )






