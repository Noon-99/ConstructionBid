"""Schema for compliance case study artifact."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComplianceCaseStudy(BaseModel):
    """Narrative artifact summarizing compliance-driven adjustments."""

    project_id: str = Field(description="Project identifier")
    project_name: str | None = Field(default=None, description="Name of the project if available")
    location: str | None = Field(default=None, description="Project address or location")
    issuing_authority: str | None = Field(default=None, description="Detected issuing authority")
    bid_submission_date: str | None = Field(default=None, description="Bid submission date (ISO string) if known")

    base_scope_cost: float | None = Field(default=None, description="Base scope cost before compliance adders")
    compliance_total: float | None = Field(default=None, description="Total compliance cost added")
    total_bid: float | None = Field(default=None, description="Final bid total including compliance")
    compliance_delta_pct: float | None = Field(
        default=None,
        description="Compliance total expressed as a percentage of base scope cost",
    )
    compliance_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Breakdown of compliance costs by category",
    )
    compliance_adjustments: list[str] = Field(
        default_factory=list, description="List of compliance adjustments applied"
    )

    prevailing_wage_applied: bool = Field(
        default=False, description="True if prevailing wage labor regime was applied"
    )
    bonds_required: bool = Field(
        default=False, description="True if payment/performance bonds were required"
    )
    insurance_applied: bool = Field(
        default=False, description="True if supplemental insurance compliance costs were applied"
    )

    procurement_indicators: list[str] = Field(
        default_factory=list,
        description="Signals indicating public-sector or compliance context",
    )
    procurement_notes: list[str] = Field(
        default_factory=list, description="Narrative notes explaining procurement detection"
    )
    evidence_references: list[Any] = Field(
        default_factory=list,
        description="Additional evidence references such as source pages or snippets",
    )

    confidence_pct: float | None = Field(
        default=None, description="Overall confidence percentage from trust report if available"
    )
    confidence_explanation: str | None = Field(
        default=None, description="Narrative explanation of confidence from trust report"
    )

    summary: str = Field(description="High-level narrative summary of compliance actions")
    recommendations: list[str] = Field(
        default_factory=list,
        description="Follow-up recommendations for reviewers or estimators",
    )
