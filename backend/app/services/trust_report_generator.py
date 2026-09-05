"""Trust Report Generator - One-page bid confidence summary."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.trust_report import (
    TrustReport,
    ConfidenceBreakdown,
    VerifiedItem,
    ReviewRecommendedItem,
    EvidenceCoverageMetrics,
    GeometryConfidence,
)


def generate_trust_report(
    project_id: str, output_dir: Path, settings: Settings
) -> TrustReport:
    """
    Generate a one-page trust report from existing artifacts.

    Args:
        project_id: Project ID
        output_dir: Output directory containing artifacts
        settings: Application settings

    Returns:
        TrustReport object
    """
    log_ctx = logger.bind(project_id=project_id, service="trust_report_generator")
    log_ctx.info("Generating trust report")

    # Load required artifacts
    bid_readiness_file = output_dir / "bid_readiness.json"
    validation_report_file = output_dir / "validation_report.json"
    bid_review_file = output_dir / "bid_review.json"
    bid_proposal_file = output_dir / "bid_proposal.json"
    document_analysis_file = output_dir / "document_analysis.json"
    model_3d_file = output_dir / "model_3d.json"
    metrics_file = output_dir / "metrics.json"

    # Load bid_readiness
    bid_readiness: dict[str, Any] = {}
    if bid_readiness_file.exists():
        with open(bid_readiness_file, "r") as f:
            bid_readiness = json.load(f)

    # Load validation_report
    validation_report: dict[str, Any] = {}
    if validation_report_file.exists():
        with open(validation_report_file, "r") as f:
            validation_report = json.load(f)

    # Load bid_review
    bid_review: dict[str, Any] = {}
    if bid_review_file.exists():
        with open(bid_review_file, "r") as f:
            bid_review = json.load(f)

    # Load bid_proposal
    bid_proposal: dict[str, Any] = {}
    if bid_proposal_file.exists():
        with open(bid_proposal_file, "r") as f:
            bid_proposal = json.load(f)

    # Load document_analysis
    document_analysis: dict[str, Any] = {}
    if document_analysis_file.exists():
        with open(document_analysis_file, "r") as f:
            document_analysis = json.load(f)

    # Load model_3d
    model_3d: dict[str, Any] = {}
    if model_3d_file.exists():
        with open(model_3d_file, "r") as f:
            model_3d = json.load(f)

    # Load metrics
    metrics: dict[str, Any] = {}
    if metrics_file.exists():
        with open(metrics_file, "r") as f:
            metrics = json.load(f)

    # Load coverage_declarations
    coverage_declarations_file = output_dir / "coverage_declarations.json"
    coverage_declarations: dict[str, Any] | None = None
    if coverage_declarations_file.exists():
        try:
            with open(coverage_declarations_file, "r") as f:
                coverage_declarations = json.load(f)
        except Exception as e:
            log_ctx.debug(f"Could not load coverage declarations: {e}")

    # Extract project metadata
    project_type = document_analysis.get("project_type", "unknown")
    resolved_project_type = document_analysis.get("resolved_project_type")
    
    # Phase 1: If government project detected, show "Government" in project type
    procurement_context = document_analysis.get("procurement_context")
    if procurement_context and procurement_context.get("is_public_project"):
        issuing_authority = document_analysis.get("issuing_authority")
        if issuing_authority:
            # Show issuing authority in project type (e.g., "Government - NYS OGS")
            project_type = f"Government - {issuing_authority}"
        else:
            project_type = "Government"
    elif resolved_project_type and resolved_project_type != "unknown":
        project_type = resolved_project_type
    
    project_name = None  # Could be extracted from document_analysis or elsewhere

    # Header: Bid Status
    bid_ready = bid_readiness.get("bid_ready", False)
    overall_confidence = (validation_report.get("score", 0.0) * 100) if validation_report else 0.0
    if bid_readiness.get("readiness_score"):
        overall_confidence = bid_readiness["readiness_score"] * 100

    confidence_explanation = (
        "This bid passed validation checks and meets minimum evidence coverage thresholds."
        if bid_ready
        else "This bid requires review before submission. Some quantities are estimated or evidence is incomplete."
    )

    # Section 1: Confidence Breakdown
    validation_score = validation_report.get("score", 0.0) if validation_report else 0.0
    dimension_confidence = (
        document_analysis.get("key_dimensions", {}).get("confidence", 0.0)
        if document_analysis
        else metrics.get("dimension_confidence", 0.0)
    )
    if not dimension_confidence and metrics:
        dimension_confidence = metrics.get("dimension_confidence", 0.0)

    # Calculate scope coverage from critical items
    critical_items = document_analysis.get("critical_expected_items", [])
    critical_found = sum(1 for item in critical_items if item.get("found", False))
    scope_coverage = (
        critical_found / len(critical_items) if critical_items else 1.0
    )

    # Calculate evidence coverage
    line_items = bid_review.get("line_items", []) or bid_proposal.get("line_items", [])
    items_with_evidence = sum(
        1
        for item in line_items
        if item.get("evidence_refs") and len(item.get("evidence_refs", [])) > 0
    )
    evidence_coverage = (
        items_with_evidence / len(line_items) if line_items else 0.0
    )

    # Calculate average quantity confidence
    quantity_confidences = [
        item.get("quantity_confidence", 0.5) for item in line_items if "quantity_confidence" in item
    ]
    avg_quantity_confidence = (
        sum(quantity_confidences) / len(quantity_confidences) if quantity_confidences else 0.5
    )

    # Determine geometry quality
    geometry_quality = "authoritative"
    if not model_3d or not model_3d.get("buildings"):
        geometry_quality = "partial"
    elif not dimension_confidence or dimension_confidence < 0.8:
        geometry_quality = "derived"

    confidence_breakdown = ConfidenceBreakdown(
        scope_coverage=scope_coverage,
        quantity_confidence=avg_quantity_confidence,
        evidence_coverage=evidence_coverage,
        geometry_quality=geometry_quality.title(),
    )

    # Section 2: Verified Items
    verified_items: list[VerifiedItem] = []
    for item in line_items:
        if item.get("evidence_refs") and len(item.get("evidence_refs", [])) > 0:
            evidence_pages = [
                ref.get("page_number")
                for ref in item.get("evidence_refs", [])
                if ref.get("page_number")
            ]
            detail_refs = item.get("detail_refs", []) or []
            if detail_refs and not isinstance(detail_refs, list):
                detail_refs = []

            verified_items.append(
                VerifiedItem(
                    item=item.get("title") or item.get("description", ""),
                    evidence_pages=sorted(set(evidence_pages)),
                    detail_refs=detail_refs,
                )
            )

    # Recovery status
    recovery_applied = (metrics.get("total_pages_sent_recovery", 0) or 0) > 0
    recovery_pages: list[int] = []  # Could be extracted from metrics if tracked

    # Section 3: Review Recommended Items
    review_recommended_items: list[ReviewRecommendedItem] = []
    for item in line_items:
        quantity_source = item.get("quantity_source", "")
        flags = item.get("flags", [])

        if quantity_source in ("heuristic", "unknown", "allowance") or any(
            "heuristic" in flag.lower() or "estimated" in flag.lower() for flag in flags
        ):
            reason = f"Quantity {quantity_source.replace('_', ' ')}"
            if quantity_source == "heuristic":
                reason = "Quantity inferred"
            elif quantity_source == "unknown":
                reason = "Quantity unknown"
            elif "EA" in (item.get("unit") or ""):
                reason = "Quantity expressed as EA (may need conversion)"

            review_recommended_items.append(
                ReviewRecommendedItem(
                    item=item.get("title") or item.get("description", ""),
                    reason=reason,
                    quantity_source=quantity_source,
                )
            )

    # Section 4: Evidence Coverage
    total_bid_value = bid_review.get("total_bid") or bid_proposal.get("summary", {}).get("total_cost", 0.0)
    items_with_evidence_value = sum(
        item.get("total_cost", 0.0)
        for item in line_items
        if item.get("evidence_refs") and len(item.get("evidence_refs", [])) > 0
    )
    bid_value_coverage_pct = (
        (items_with_evidence_value / total_bid_value * 100) if total_bid_value > 0 else 0.0
    )

    all_pages = set()
    all_detail_refs = set()
    for item in line_items:
        for ref in item.get("evidence_refs", []):
            if ref.get("page_number"):
                all_pages.add(ref.get("page_number"))
        for detail_ref in item.get("detail_refs", []):
            if detail_ref:
                all_detail_refs.add(detail_ref)

    orphan_items = sum(
        1
        for item in line_items
        if (not item.get("evidence_refs") or len(item.get("evidence_refs", [])) == 0)
        and (not item.get("detail_refs") or len(item.get("detail_refs", [])) == 0)
    )

    evidence_coverage_metrics = EvidenceCoverageMetrics(
        bid_value_coverage_pct=bid_value_coverage_pct,
        items_with_evidence_pct=evidence_coverage * 100,
        orphan_items_count=orphan_items,
        referenced_pages=sorted(all_pages),
        detail_refs=sorted(all_detail_refs),
    )

    # Section 5: Geometry & 3D
    buildings_count = len(model_3d.get("buildings", [])) if model_3d else 0
    work_zones_count = len(model_3d.get("work_zones", [])) if model_3d else 0
    geometry_type = "Dimensional + sectional" if buildings_count > 0 else "Not generated"

    geometry_confidence = GeometryConfidence(
        model_generated=buildings_count > 0,
        buildings_count=buildings_count,
        work_zones_count=work_zones_count,
        geometry_type=geometry_type,
        used_for=["Quantity derivation", "Cost attribution", "Evidence navigation"],
    )

    # Section 6: Includes/Excludes
    included_items = [
        "Line items with quantities & unit costs",
        "Drawing references per item",
        "Scope-level cost breakdown",
        "Evidence-linked audit trail",
    ]
    excluded_items = [
        "Field verification",
        "Permits & filing fees (unless specified)",
        "Contractor overhead & profit",
        "Change order contingencies",
    ]

    # Section 7: System Integrity
    validation_gates_passed = validation_report.get("passed", False) if validation_report else False
    critical_recovery_applied = (
        len(validation_report.get("missing_critical_items", [])) > 0
        if validation_report
        else False
    ) and recovery_applied
    cache_reuse_enabled = metrics.get("cache_hit_rate", 0) > 0 if metrics else True

    # Get run timestamp from metrics or bid_readiness
    run_timestamp = metrics.get("created_at") if metrics else bid_readiness.get("created_at")
    if isinstance(run_timestamp, str):
        try:
            run_timestamp = datetime.fromisoformat(run_timestamp.replace("Z", "+00:00"))
        except:
            run_timestamp = datetime.now()
    elif not isinstance(run_timestamp, datetime):
        run_timestamp = datetime.now()

    # Determine mode
    mode = "conceptual"
    if bid_proposal.get("bid_mode") == "contractor":
        mode = "contractor"

    proposal_summary = bid_proposal.get("summary", {}) if bid_proposal else {}
    trust_report = TrustReport(
        project_id=project_id,
        project_name=project_name,
        project_type=project_type.replace("_", " ").title(),
        run_id=project_id,
        generated_at=datetime.now(),
        bid_ready=bid_ready,
        overall_confidence=overall_confidence,
        confidence_explanation=confidence_explanation,
        base_scope_cost=proposal_summary.get("base_scope_cost", 0.0),
        allowances_total=proposal_summary.get("allowances_total", 0.0),
        compliance_adjustments=bid_review.get("compliance_adjustments", []),
        compliance_costs=proposal_summary.get("compliance_costs", {}),
        compliance_total=proposal_summary.get("compliance_total", 0.0),
        contingency_recommendation_pct=proposal_summary.get("contingency_recommendation_pct"),
        contingency_recommendation_amount=proposal_summary.get("contingency_recommendation_amount"),
        confidence_breakdown=confidence_breakdown,
        verified_items=verified_items[:10],  # Limit to top 10
        recovery_applied=recovery_applied,
        recovery_pages=recovery_pages,
        review_recommended_items=review_recommended_items,
        evidence_coverage=evidence_coverage_metrics,
        geometry_confidence=geometry_confidence,
        included_items=included_items,
        excluded_items=excluded_items,
        validation_gates_passed=validation_gates_passed,
        critical_recovery_applied=critical_recovery_applied,
        cache_reuse_enabled=cache_reuse_enabled,
        deterministic_run=True,  # Always true for our system
        mode=mode,
        run_timestamp=run_timestamp,
        coverage_declarations=coverage_declarations,
    )

    log_ctx.info(
        f"Trust report generated: confidence={overall_confidence:.0f}%, "
        f"evidence_coverage={bid_value_coverage_pct:.0f}%, "
        f"review_items={len(review_recommended_items)}"
    )

    return trust_report

