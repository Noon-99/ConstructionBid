"""Schema for contractor bid (Phase 9.4A).

Contractor bid represents a contractor-grade proposal that combines the conceptual bid
with expanded scope, labor breakdown, and contractor-specific adjustments.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.expanded_scope import RegionResolution


class ContractorBidLineItem(BaseModel):
    """A line item in a contractor bid section."""

    item_id: str = Field(description="Unique identifier for this line item")
    title: str = Field(description="Item title/description")
    division: str | None = Field(
        default=None, description="CSI division (e.g., '01', '04', '05')"
    )
    quantity: float | None = Field(
        default=None, description="Quantity (null for lump sum items)"
    )
    unit: str | None = Field(
        default=None, description="Unit of measure (null for lump sum items)"
    )
    unit_cost: float | None = Field(
        default=None, description="Unit cost (null for lump sum items)"
    )
    total_cost: float = Field(description="Total cost for this line item")
    basis: str = Field(description="Basis/evidence/assumption for this item")
    notes: str | None = Field(
        default=None, description="Additional notes or clarifications"
    )


class ContractorBidSection(BaseModel):
    """A section of the contractor bid."""

    section_id: str = Field(description="Unique identifier for this section")
    title: str = Field(description="Section title (e.g., 'Masonry Work', 'General Requirements')")
    division: str | None = Field(
        default=None, description="CSI division if applicable"
    )
    line_items: list[ContractorBidLineItem] = Field(
        default_factory=list, description="Line items in this section"
    )
    subtotal: float = Field(
        ge=0.0, description="Subtotal for this section (sum of line items)"
    )


class ContractorSchedule(BaseModel):
    """Project schedule information."""

    estimated_start_date: str | None = Field(
        default=None, description="Estimated project start date (ISO format)"
    )
    estimated_duration_days: int | None = Field(
        default=None, ge=0, description="Estimated project duration in days"
    )
    estimated_completion_date: str | None = Field(
        default=None, description="Estimated project completion date (ISO format)"
    )
    phases: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Project phases with durations and dependencies (optional)",
    )


class PaymentMilestone(BaseModel):
    """A payment milestone in the payment schedule."""

    milestone_id: str = Field(description="Unique identifier for this milestone")
    title: str = Field(description="Milestone title (e.g., 'Mobilization', '50% Complete')")
    percentage: float = Field(
        ge=0.0, le=100.0, description="Percentage of total bid amount for this milestone"
    )
    amount: float = Field(ge=0.0, description="Payment amount in dollars")
    trigger: str = Field(
        description="Trigger condition (e.g., 'Upon mobilization', 'Upon completion of masonry work')"
    )


class ContractorBid(BaseModel):
    """Complete contractor-grade bid proposal (Phase 9.4A)."""

    project_id: str = Field(description="Project ID this bid applies to")
    bid_mode: Literal["contractor"] = Field(
        default="contractor", description="Bid mode (always 'contractor' for this schema)"
    )
    total_bid: float = Field(
        ge=0.0, description="Total bid amount in dollars (sum of all sections + permits + logistics)"
    )
    subtotals: dict[str, float] = Field(
        default_factory=dict,
        description="Subtotals by section or category (e.g., {'scope': 50000.0, 'permits': 2500.0, 'logistics': 10000.0})",
    )
    sections: list[ContractorBidSection] = Field(
        default_factory=list, description="Main bid sections (scope of work)"
    )
    schedule: ContractorSchedule | None = Field(
        default=None, description="Project schedule information"
    )
    payment_schedule: list[PaymentMilestone] | None = Field(
        default=None, description="Payment milestones and schedule"
    )
    permits_and_inspections: list[ContractorBidLineItem] = Field(
        default_factory=list,
        description="Permits and inspections line items (from expanded scope or allowances)",
    )
    logistics: list[ContractorBidLineItem] = Field(
        default_factory=list,
        description="Logistics line items (scaffolding, dumpsters, etc. from expanded scope)",
    )
    exclusions: list[str] = Field(
        default_factory=list,
        description="List of items explicitly excluded from this bid",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="List of assumptions made in preparing this bid",
    )
    region_resolution: RegionResolution | None = Field(
        default=None, description="Region resolution metadata (Phase 9.7)"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="When this contractor bid was generated"
    )

