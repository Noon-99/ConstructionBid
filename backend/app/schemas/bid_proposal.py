"""Schema for bid proposal output (Phase 4.6, 4.7)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Import QuantitySource from costing schema
try:
    from app.schemas.costing import QuantitySource
except ImportError:
    QuantitySource = Literal[
        "from_drawing",
        "from_schedule",
        "computed_from_dimensions",
        "allowance",
        "heuristic",
        "unknown",
    ]


class BidLineItem(BaseModel):
    """Individual bid line item."""

    division: str = Field(description="CSI division number/name (e.g., '03 Concrete', '04 Masonry')")
    description: str = Field(description="Item description")
    quantity: float | None = Field(default=None, description="Quantity (null for allowance items)")
    unit: str | None = Field(default=None, description="Unit of measurement (null for allowance items)")
    unit_cost: float | None = Field(default=None, description="Unit cost (null for allowance items)")
    total_cost: float = Field(description="Total cost for this line item")
    basis: str = Field(description="Basis/evidence/assumption for this item")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this line item")
    # Phase 4.7: Quantity provenance
    quantity_source: QuantitySource | None = Field(
        default=None, description="Source of the quantity (from_drawing, from_schedule, etc.)"
    )
    quantity_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Confidence in the quantity"
    )


class BidAllowance(BaseModel):
    """Allowance item (lump sum)."""

    name: str = Field(description="Allowance name")
    amount: float = Field(description="Allowance amount")
    notes: str = Field(description="Notes about what this allowance covers")


class BidAlternate(BaseModel):
    """Alternate bid item."""

    name: str = Field(description="Alternate name")
    delta_amount: float = Field(description="Delta amount (add or subtract from base)")
    notes: str = Field(description="Notes about this alternate")


class BidClarification(BaseModel):
    """Clarification or assumption note."""

    text: str = Field(description="Clarification text")
    severity: Literal["info", "warning", "critical"] = Field(
        default="info", description="Severity level"
    )


class BidSummary(BaseModel):
    """Bid proposal summary."""

    total_cost: float = Field(description="Total bid amount")
    cost_by_division: dict[str, float] = Field(
        default_factory=dict, description="Cost subtotals by CSI division"
    )
    base_scope_cost: float = Field(
        default=0.0,
        description="Base scope cost before compliance adders (materials + labor + equipment + waste)",
    )
    allowances_total: float = Field(
        default=0.0,
        description="Total of allowance items included in the proposal",
    )
    compliance_costs: dict[str, float] = Field(
        default_factory=dict,
        description="Compliance cost adders by type (e.g., {'bond': 2500.0, 'insurance': 1200.0})",
    )
    compliance_total: float = Field(
        default=0.0,
        description="Sum of all compliance adders applied to the bid",
    )
    contingency_recommendation_pct: float | None = Field(
        default=None,
        description="Recommended contingency percentage from costing stage",
    )
    contingency_recommendation_amount: float | None = Field(
        default=None,
        description="Dollar amount associated with the recommended contingency",
    )


class BidProposal(BaseModel):
    """Complete bid proposal (Phase 4.6, 4.7)."""

    project_id: str = Field(description="Project ID")
    summary: BidSummary = Field(description="Bid summary with totals")
    line_items: list[BidLineItem] = Field(
        default_factory=list, description="Line items grouped by division"
    )
    allowances: list[BidAllowance] = Field(
        default_factory=list, description="Allowance items (lump sum)"
    )
    alternates: list[BidAlternate] = Field(
        default_factory=list, description="Alternate bid items"
    )
    clarifications: list[BidClarification] = Field(
        default_factory=list, description="Clarifications and assumptions"
    )
    generated_at: datetime = Field(
        default_factory=datetime.now, description="When this proposal was generated"
    )
    # Phase 4.7: Estimate mode and bid readiness
    estimate_mode: Literal["conceptual", "bid_ready"] = Field(
        default="conceptual", description="Estimate mode: conceptual allows heuristics, bid_ready requires evidence"
    )
    bid_ready: bool = Field(
        default=True, description="True if bid is ready for submission (no heuristic quantities in bid_ready mode)"
    )
    # Phase 9.0: Bid mode guardrail (conceptual vs contractor)
    bid_mode: Literal["conceptual", "contractor"] = Field(
        default="conceptual", description="Bid mode: conceptual (default) or contractor (synthesized with contractor logic)"
    )

