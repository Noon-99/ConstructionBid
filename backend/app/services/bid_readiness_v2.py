"""Bid readiness v2 assessment service (Phase 10.1).

Separates conceptual readiness from contractor readiness.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.schemas.bid_readiness import BidReadinessResult
from app.schemas.bid_readiness_v2 import BidReadinessV2Result
from app.services.bid_readiness import compute_bid_readiness
from app.services.contractor_profile_store import load_profile
from app.core.config import Settings


def compute_bid_readiness_v2(
    project_id: str, output_dir: Path | None = None, settings: Settings | None = None
) -> BidReadinessV2Result:
    """
    Compute bid readiness v2 separating conceptual vs contractor readiness (Phase 10.1).

    Args:
        project_id: Project ID
        output_dir: Output directory (default: Path("out") / project_id)
        settings: Application settings (required for profile loading)

    Returns:
        BidReadinessV2Result with conceptual_ready and contractor_ready flags
    """
    if output_dir is None:
        output_dir = Path("out") / project_id
    elif isinstance(output_dir, str):
        output_dir = Path(output_dir)

    log_ctx = logger.bind(project_id=project_id, service="bid_readiness_v2")
    log_ctx.info("Computing bid readiness v2")

    # Get conceptual readiness (existing logic)
    conceptual_readiness = compute_bid_readiness(project_id, output_dir)
    conceptual_ready = conceptual_readiness.bid_ready

    # Compute contractor readiness
    contractor_ready = False
    blocking_reasons_contractor: list[str] = []
    warnings_contractor: list[str] = []
    derived_from: dict[str, Any] = {
        "conceptual_ready": conceptual_ready,
        "conceptual_readiness_score": conceptual_readiness.readiness_score,
    }

    # Rule 1: Conceptual validation must pass >= 0.85
    validation_file = output_dir / "validation_report.json"
    validation_passed = False
    validation_score = 0.0
    if validation_file.exists():
        try:
            with open(validation_file, "r") as f:
                validation_data = json.load(f)
            validation_passed = validation_data.get("passed", False)
            validation_score = validation_data.get("score", 0.0)
            derived_from["validation_passed"] = validation_passed
            derived_from["validation_score"] = validation_score
        except Exception as e:
            log_ctx.warning(f"Failed to load validation report: {e}")

    if not validation_passed:
        blocking_reasons_contractor.append("Conceptual validation did not pass")
    elif validation_score < 0.85:
        blocking_reasons_contractor.append(
            f"Conceptual validation score too low: {validation_score:.2%} (required: >= 85%)"
        )

    # Rule 2: Contractor profile must be loaded
    contractor_profile = None
    profile_id = None
    
    # Phase 10.10B: Also check for pricing_profile.json
    pricing_profile_file = output_dir / "pricing_profile.json"
    if pricing_profile_file.exists():
        try:
            with open(pricing_profile_file, "r") as f:
                pricing_profile_data = json.load(f)
            profile_id = pricing_profile_data.get("profile_id")
            derived_from["pricing_profile_id"] = profile_id
        except Exception as e:
            log_ctx.warning(f"Failed to load pricing_profile: {e}")
    
    # Prepare key artifact paths
    expanded_scope_file = output_dir / "expanded_scope.json"
    contractor_bid_file = output_dir / "contractor_bid.json"

    # Try to get profile_id from expanded_scope or contractor_bid
    if not profile_id:
        if expanded_scope_file.exists():
            try:
                with open(expanded_scope_file, "r") as f:
                    expanded_scope_data = json.load(f)
                profile_id = expanded_scope_data.get("profile_id")
            except Exception as e:
                log_ctx.warning(f"Failed to load expanded_scope: {e}")

        if not profile_id and contractor_bid_file.exists():
            try:
                with open(contractor_bid_file, "r") as f:
                    contractor_bid_data = json.load(f)
                # Try to get profile_id from expanded_scope reference in contractor_bid
                # (Note: contractor_bid may not have profile_id directly)
            except Exception as e:
                log_ctx.warning(f"Failed to load contractor_bid: {e}")

    if settings and profile_id:
        try:
            contractor_profile = load_profile(profile_id, settings)
            derived_from["profile_id"] = profile_id
            derived_from["profile_loaded"] = True
        except Exception as e:
            log_ctx.warning(f"Failed to load contractor profile {profile_id}: {e}")
            blocking_reasons_contractor.append(
                f"Failed to load contractor profile: {profile_id}"
            )
    else:
        if not profile_id:
            blocking_reasons_contractor.append("Contractor profile ID not found")
        if not settings:
            blocking_reasons_contractor.append("Settings not available for profile loading")

    # Rule 3: contractor_bid must exist OR can be generated
    contractor_bid_exists = contractor_bid_file.exists()
    derived_from["contractor_bid_exists"] = contractor_bid_exists

    if not contractor_bid_exists:
        # Check if we can generate it (have required artifacts)
        bid_proposal_exists = (output_dir / "bid_proposal.json").exists()
        if not bid_proposal_exists:
            blocking_reasons_contractor.append(
                "Contractor bid does not exist and cannot be generated (missing bid_proposal.json)"
            )
        else:
            warnings_contractor.append(
                "Contractor bid not generated yet (can be generated)"
            )

    # Rule 4: expanded_scope must exist (or can be generated)
    expanded_scope_exists = expanded_scope_file.exists()
    derived_from["expanded_scope_exists"] = expanded_scope_exists

    if not expanded_scope_exists:
        # Check if we can generate it
        bid_proposal_exists = (output_dir / "bid_proposal.json").exists()
        if not bid_proposal_exists:
            blocking_reasons_contractor.append(
                "Expanded scope does not exist and cannot be generated (missing bid_proposal.json)"
            )
        else:
            warnings_contractor.append(
                "Expanded scope not generated yet (can be generated)"
            )

    # Phase 10.12A: Check bid completeness gate
    completeness_blockers: list[str] = []
    completeness_warnings: list[str] = []
    try:
        from app.services.bid_completeness import evaluate_bid_completeness
        completeness = evaluate_bid_completeness(
            project_id=project_id,
            output_dir=output_dir,
            extraction_result=None,  # Will load internally
            validation_report=None,  # Will load internally
            bid_review=None,  # Will load internally
        )
        derived_from["bid_completeness"] = {
            "passed": completeness.passed,
            "score": completeness.score,
            "blockers": completeness.blockers,
            "warnings": completeness.warnings,
        }
        if not completeness.passed:
            completeness_blockers.extend(completeness.blockers)
            completeness_warnings.extend(completeness.warnings)
            blocking_reasons_contractor.extend([f"Bid completeness: {blocker}" for blocker in completeness.blockers])
        else:
            if completeness.warnings:
                warnings_contractor.extend([f"Bid completeness: {warning}" for warning in completeness.warnings])
    except Exception as e:
        log_ctx.warning(f"Failed to evaluate bid completeness: {e}")
        # Don't block if completeness check fails, but warn
        warnings_contractor.append("Bid completeness check unavailable")

    # Contractor readiness: no blocking reasons
    contractor_ready = len(blocking_reasons_contractor) == 0

    # Note: contractor_ready does NOT require all items to be evidenced
    # (many are profile defaults), but we should note items without drawing evidence
    if contractor_bid_exists:
        try:
            with open(contractor_bid_file, "r") as f:
                contractor_bid_data = json.load(f)
            
            # Count items with "Contractor profile" or similar basis (no drawing evidence)
            items_without_evidence = 0
            total_items = 0
            
            sections = contractor_bid_data.get("sections", [])
            for section in sections:
                for item in section.get("line_items", []):
                    total_items += 1
                    basis = item.get("basis", "").lower()
                    if "contractor profile" in basis or "default" in basis:
                        items_without_evidence += 1
            
            if items_without_evidence > 0:
                warnings_contractor.append(
                    f"{items_without_evidence} of {total_items} line items have no drawing evidence "
                    "(based on contractor profile defaults)"
                )
        except Exception as e:
            log_ctx.warning(f"Failed to analyze contractor bid items: {e}")

    result = BidReadinessV2Result(
        conceptual_ready=conceptual_ready,
        contractor_ready=contractor_ready,
        blocking_reasons_contractor=blocking_reasons_contractor,
        warnings_contractor=warnings_contractor,
        derived_from=derived_from,
    )

    log_ctx.info(
        f"Bid readiness v2 computed: conceptual_ready={conceptual_ready}, "
        f"contractor_ready={contractor_ready}, "
        f"contractor_blockers={len(blocking_reasons_contractor)}, "
        f"contractor_warnings={len(warnings_contractor)}"
    )

    return result


