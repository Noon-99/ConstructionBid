"""Bid readiness assessment service (Phase 6.5)."""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.schemas.bid_readiness import BidReadinessResult
from app.schemas.bid_proposal import BidProposal
from app.schemas.validation_report import ValidationReport


def compute_bid_readiness(project_id: str, output_dir: Path | None = None) -> BidReadinessResult:
    """
    Compute bid readiness based on validation, geometry quality, and artifacts.

    Args:
        project_id: Project ID
        output_dir: Output directory (default: Path("out") / project_id)

    Returns:
        BidReadinessResult with bid_ready flag, score, reasons, and warnings
    """
    if output_dir is None:
        output_dir = Path("out") / project_id

    log_ctx = logger.bind(project_id=project_id, service="bid_readiness")
    log_ctx.info("Computing bid readiness")

    reasons_blocking: list[str] = []
    warnings: list[str] = []
    derived_from: dict[str, Any] = {}

    # Load validation report
    validation_report: ValidationReport | None = None
    validation_file = output_dir / "validation_report.json"
    if validation_file.exists():
        try:
            with open(validation_file, "r") as f:
                validation_data = json.load(f)
            validation_report = ValidationReport.model_validate(validation_data)
            derived_from["validation_passed"] = validation_report.passed
            derived_from["validation_score"] = validation_report.score
            derived_from["rerun_performed"] = validation_report.rerun_performed
        except Exception as e:
            log_ctx.warning(f"Failed to load validation report: {e}")
            reasons_blocking.append("Validation report missing or invalid")
    else:
        reasons_blocking.append("Validation report not found")

    # Load bid proposal
    bid_proposal: BidProposal | None = None
    bid_file = output_dir / "bid_proposal.json"
    if bid_file.exists():
        try:
            with open(bid_file, "r") as f:
                bid_data = json.load(f)
            bid_proposal = BidProposal.model_validate(bid_data)
            derived_from["bid_proposal_bid_ready"] = bid_proposal.bid_ready
            derived_from["estimate_mode"] = bid_proposal.estimate_mode
        except Exception as e:
            log_ctx.warning(f"Failed to load bid proposal: {e}")
            reasons_blocking.append("Bid proposal missing or invalid")
    else:
        reasons_blocking.append("Bid proposal not found")

    # Load costing result (check if exists)
    costing_file = output_dir / "costing_result.json"
    if not costing_file.exists():
        reasons_blocking.append("Costing result not found")

    # Load extraction result for geometry quality
    geometry_quality: str | None = None
    extraction_file = output_dir / "extraction_result.json"
    if extraction_file.exists():
        try:
            with open(extraction_file, "r") as f:
                extraction_data = json.load(f)
            inst_geometry = extraction_data.get("institutional_geometry_for_3d")
            if inst_geometry:
                geometry_quality = inst_geometry.get("geometry_quality")
                derived_from["geometry_quality"] = geometry_quality
        except Exception as e:
            log_ctx.warning(f"Failed to load extraction result for geometry quality: {e}")

    # Load metrics (optional, for cache hit rate warning)
    cache_hit_rate: float | None = None
    metrics_file = output_dir / "metrics.json"
    if metrics_file.exists():
        try:
            with open(metrics_file, "r") as f:
                metrics_data = json.load(f)
            cache_hit_rate = metrics_data.get("cache_hit_rate")
            if cache_hit_rate is not None:
                derived_from["cache_hit_rate"] = cache_hit_rate
        except Exception as e:
            log_ctx.debug(f"Failed to load metrics: {e}")

    # Apply rules: Hard blockers
    if validation_report:
        if not validation_report.passed:
            reasons_blocking.append("Validation did not pass")
        if validation_report.score < 0.85:
            reasons_blocking.append(f"Validation score too low: {validation_report.score:.2%} (required: >= 85%)")
    else:
        # Already added to reasons_blocking above
        pass

    if geometry_quality == "partial":
        reasons_blocking.append("Geometry quality is 'partial' (incomplete geometry data)")

    # Warnings (don't block)
    if validation_report and validation_report.rerun_performed:
        warnings.append("Auto-recovery was performed (targeted re-read occurred)")

    if cache_hit_rate is not None and cache_hit_rate < 0.5:
        warnings.append(f"Low cache hit rate: {cache_hit_rate:.1%} (may indicate data quality issues)")

    if bid_proposal and bid_proposal.clarifications:
        warnings.append(f"{len(bid_proposal.clarifications)} clarification(s) present (review assumptions)")

    # Compute readiness score
    readiness_score = 1.0
    if reasons_blocking:
        readiness_score = 0.0
    elif validation_report:
        # Base score on validation score, but penalize for warnings
        readiness_score = validation_report.score
        if warnings:
            # Small penalty for warnings
            readiness_score = max(0.0, readiness_score - 0.1)

    # Determine bid_ready
    bid_ready = len(reasons_blocking) == 0

    # Generate stamp text
    if bid_ready:
        readiness_stamp_text = "BID READY"
    else:
        readiness_stamp_text = "PRELIMINARY — REVIEW REQUIRED"

    result = BidReadinessResult(
        bid_ready=bid_ready,
        readiness_score=readiness_score,
        reasons_blocking=reasons_blocking,
        warnings=warnings,
        derived_from=derived_from,
        readiness_stamp_text=readiness_stamp_text,
    )

    log_ctx.info(
        f"Bid readiness computed: ready={bid_ready}, score={readiness_score:.2%}, "
        f"blockers={len(reasons_blocking)}, warnings={len(warnings)}"
    )

    return result






