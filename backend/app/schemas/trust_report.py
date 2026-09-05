"""Schema for Trust Report (one-page bid confidence summary)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConfidenceBreakdown(BaseModel):
    """Confidence score breakdown."""

    scope_coverage: float = Field(ge=0.0, le=1.0, description="Scope coverage score")
    quantity_confidence: float = Field(ge=0.0, le=1.0, description="Average quantity confidence")
    evidence_coverage: float = Field(ge=0.0, le=1.0, description="Evidence coverage score")
    geometry_quality: str = Field(description="Geometry quality level (authoritative/derived/partial)")


class VerifiedItem(BaseModel):
    """Item automatically verified from drawings."""

    item: str = Field(description="Item name")
    evidence_pages: list[int] = Field(default_factory=list, description="Page numbers where verified")
    detail_refs: list[str] = Field(default_factory=list, description="Detail references")


class ReviewRecommendedItem(BaseModel):
    """Item that requires human review."""

    item: str = Field(description="Item name")
    reason: str = Field(description="Reason review is recommended")
    quantity_source: str | None = Field(default=None, description="Quantity source type")


class EvidenceCoverageMetrics(BaseModel):
    """Evidence coverage statistics."""

    bid_value_coverage_pct: float = Field(ge=0.0, le=100.0, description="% of bid value with evidence")
    items_with_evidence_pct: float = Field(ge=0.0, le=100.0, description="% of items with evidence")
    orphan_items_count: int = Field(ge=0, description="Items with no evidence")
    referenced_pages: list[int] = Field(default_factory=list, description="Unique page numbers referenced")
    detail_refs: list[str] = Field(default_factory=list, description="Unique detail references")


class GeometryConfidence(BaseModel):
    """3D geometry confidence information."""

    model_generated: bool = Field(description="Whether 3D model was generated")
    buildings_count: int = Field(default=0, description="Number of buildings")
    work_zones_count: int = Field(default=0, description="Number of work zones")
    geometry_type: str = Field(description="Geometry type description")
    used_for: list[str] = Field(default_factory=list, description="What 3D is used for")


class TrustReport(BaseModel):
    """One-page trust report for bid confidence assessment."""

    project_id: str = Field(description="Project ID")
    project_name: str | None = Field(default=None, description="Project name or address")
    project_type: str = Field(description="Project type")
    run_id: str = Field(description="Run/project ID (same as project_id)")
    generated_at: datetime = Field(default_factory=datetime.now, description="Report generation timestamp")

    # Header - Bid Status
    bid_ready: bool = Field(description="Whether bid is ready")
    overall_confidence: float = Field(ge=0.0, le=100.0, description="Overall confidence percentage")
    confidence_explanation: str = Field(description="Explanation of confidence score")
    base_scope_cost: float = Field(
        default=0.0,
        description="Base scope cost prior to compliance adders",
    )
    allowances_total: float = Field(
        default=0.0,
        description="Total allowances included in bid",
    )
    compliance_adjustments: list[str] = Field(
        default_factory=list,
        description="Narrative compliance adjustments applied (e.g., prevailing wage, union, bonds)",
    )
    compliance_costs: dict[str, float] = Field(
        default_factory=dict,
        description="Compliance cost adders by type",
    )
    compliance_total: float = Field(
        default=0.0,
        description="Sum of compliance cost adders",
    )
    contingency_recommendation_pct: float | None = Field(
        default=None,
        description="Recommended contingency percentage from costing",
    )
    contingency_recommendation_amount: float | None = Field(
        default=None,
        description="Recommended contingency dollar amount",
    )

    # Section 1: Confidence Breakdown
    confidence_breakdown: ConfidenceBreakdown = Field(description="Detailed confidence breakdown")

    # Section 2: Verified Items
    verified_items: list[VerifiedItem] = Field(default_factory=list, description="Items verified from drawings")
    recovery_applied: bool = Field(description="Whether recovery was applied")
    recovery_pages: list[int] = Field(default_factory=list, description="Pages used for recovery")

    # Section 3: Review Recommended
    review_recommended_items: list[ReviewRecommendedItem] = Field(
        default_factory=list, description="Items requiring human review"
    )

    # Section 4: Evidence Coverage
    evidence_coverage: EvidenceCoverageMetrics = Field(description="Evidence coverage statistics")

    # Section 5: Geometry & 3D
    geometry_confidence: GeometryConfidence = Field(description="3D geometry confidence")

    # Section 6: Includes/Excludes
    included_items: list[str] = Field(default_factory=list, description="What this bid includes")
    excluded_items: list[str] = Field(default_factory=list, description="What this bid excludes")

    # Section 7: System Integrity
    validation_gates_passed: bool = Field(description="Whether validation gates passed")
    critical_recovery_applied: bool = Field(description="Whether critical recovery was applied")
    cache_reuse_enabled: bool = Field(default=True, description="Whether cache reuse was enabled")
    deterministic_run: bool = Field(default=True, description="Whether run was deterministic")
    mode: str = Field(default="conceptual", description="Bid mode (conceptual/contractor)")
    run_timestamp: datetime = Field(description="When the pipeline run completed")

    # Section 8: Coverage & Warranty (Contractor Declared)
    coverage_declarations: dict[str, Any] | None = Field(
        default=None, description="Coverage & Warranty declarations (contractor-declared, not evidence-backed)"
    )

