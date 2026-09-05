"""Schema for contractor-style proposal sections (Phase 10.9A).

This is a deterministic rendering layer that organizes bid proposal data
into contractor-style sections without changing the underlying bid_proposal.json schema.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence_index import EvidenceReference


class ExecutiveSummary(BaseModel):
    """Executive summary section."""

    project_overview: str = Field(description="Brief project overview")
    total_bid_amount: float = Field(description="Total bid amount")
    scope_summary: str = Field(description="Scope summary")
    key_highlights: list[str] = Field(
        default_factory=list, description="Key highlights or important notes"
    )


class ScopeSection(BaseModel):
    """A scope section in the proposal."""

    section_key: Literal[
        "parapet",
        "lintels",
        "veneer",
        "repointing",
        "crack_repair",
        "flashing",
        "protection",
        "permits",
    ] = Field(description="Section key identifier")
    title: str = Field(description="Section title (e.g., 'Parapet Repair and Rebuild')")
    narrative: str = Field(
        description="Narrative description of the work in this section"
    )
    line_item_ids: list[str] = Field(
        default_factory=list,
        description="References to line item IDs from bid_proposal (as string indices)",
    )
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list, description="Linked evidence references"
    )
    detail_refs: list[str] = Field(
        default_factory=list,
        description="Detail IDs from detail_graph if available",
    )
    flags: list[str] = Field(
        default_factory=list,
        description="Flags (e.g., 'estimated', 'heuristic_quantity', 'recovered_item')",
    )


class LogisticsSection(BaseModel):
    """Logistics and site protection section."""

    title: str = Field(default="Logistics & Site Protection", description="Section title")
    narrative: str = Field(
        description="Description of logistics, scaffolding, protection, site access, etc."
    )
    line_item_ids: list[str] = Field(
        default_factory=list,
        description="References to line item IDs related to logistics",
    )
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list, description="Linked evidence references"
    )


class PermitsInspectionsSection(BaseModel):
    """Permits and inspections section."""

    title: str = Field(
        default="Permits & Inspections", description="Section title"
    )
    narrative: str = Field(
        description="Description of permits, inspections, and regulatory requirements"
    )
    line_item_ids: list[str] = Field(
        default_factory=list,
        description="References to line item IDs related to permits/inspections",
    )
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list, description="Linked evidence references"
    )


class PaymentSchedule(BaseModel):
    """Payment schedule section."""

    milestone_1: str | None = Field(
        default=None, description="Milestone 1 description and percentage"
    )
    milestone_2: str | None = Field(
        default=None, description="Milestone 2 description and percentage"
    )
    milestone_3: str | None = Field(
        default=None, description="Milestone 3 description and percentage"
    )
    final_payment: str | None = Field(
        default=None, description="Final payment description and percentage"
    )


class ProjectSchedule(BaseModel):
    """Project schedule section."""

    estimated_duration_weeks: int | None = Field(
        default=None, description="Estimated project duration in weeks"
    )
    start_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions required before work can start",
    )
    critical_path_items: list[str] = Field(
        default_factory=list,
        description="Critical path items or milestones",
    )


class ProposalSections(BaseModel):
    """Complete contractor-style proposal sections (Phase 10.9A)."""

    project_id: str = Field(description="Project ID")
    generated_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp of generation"
    )
    executive_summary: ExecutiveSummary = Field(description="Executive summary section")
    scope_sections: list[ScopeSection] = Field(
        default_factory=list, description="Scope sections ordered deterministically"
    )
    logistics_section: LogisticsSection = Field(description="Logistics section")
    permits_inspections_section: PermitsInspectionsSection = Field(
        description="Permits and inspections section"
    )
    exclusions: list[str] = Field(
        default_factory=list, description="List of exclusions"
    )
    assumptions: list[str] = Field(
        default_factory=list, description="List of assumptions"
    )
    payment_schedule: PaymentSchedule = Field(description="Payment schedule")
    schedule: ProjectSchedule = Field(description="Project schedule")
    notes: list[str] = Field(default_factory=list, description="Additional notes")





