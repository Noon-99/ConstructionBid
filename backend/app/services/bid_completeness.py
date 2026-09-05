"""Bid completeness gate service (Phase 10.12A).

Deterministic evaluation of bid completeness for contractor-ready packages.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.schemas.bid_completeness import BidCompletenessResult
from app.schemas.proposal_sections import ProposalSections
from app.schemas.extraction_result import ExtractionResult


def evaluate_bid_completeness(
    project_id: str,
    output_dir: Path,
    proposal_sections: ProposalSections | None = None,
    extraction_result: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
    bid_review: dict[str, Any] | None = None,
) -> BidCompletenessResult:
    """
    Evaluate bid completeness gate (Phase 10.12A).

    Required sections for row_house+repair:
    - parapet section: present and has >=1 line item + >=1 evidence ref
    - lintels section: present if lintel scope exists
    - brick/repoint section: present if brick/repoint scope exists
    - logistics section: present (template allowed)
    - permits/inspections section: present (template allowed)
    - exclusions: non-empty
    - assumptions: non-empty
    - clarifications: can be empty list

    Args:
        project_id: Project ID
        output_dir: Output directory for project artifacts
        proposal_sections: Proposal sections artifact (optional, will load if not provided)
        extraction_result: Extraction result artifact (optional, will load if not provided)
        validation_report: Validation report artifact (optional)
        bid_review: Bid review artifact (optional)

    Returns:
        BidCompletenessResult
    """
    log_ctx = logger.bind(project_id=project_id, service="bid_completeness")
    log_ctx.info("Evaluating bid completeness")

    # Load artifacts if not provided
    if proposal_sections is None:
        try:
            with open(output_dir / "proposal_sections.json", "r") as f:
                proposal_sections = ProposalSections.model_validate(json.load(f))
        except FileNotFoundError:
            log_ctx.warning("proposal_sections.json not found, cannot evaluate completeness")
            return BidCompletenessResult(
                project_id=project_id,
                passed=False,
                score=0.0,
                blockers=["proposal_sections.json not found"],
                warnings=[],
                required_sections=[],
                missing_sections=[],
            )
        except Exception as e:
            log_ctx.error(f"Failed to load proposal_sections.json: {e}")
            return BidCompletenessResult(
                project_id=project_id,
                passed=False,
                score=0.0,
                blockers=[f"Failed to load proposal_sections.json: {str(e)}"],
                warnings=[],
                required_sections=[],
                missing_sections=[],
            )

    if extraction_result is None:
        try:
            with open(output_dir / "extraction_result.json", "r") as f:
                extraction_result = json.load(f)
        except FileNotFoundError:
            log_ctx.debug("extraction_result.json not found")
        except Exception as e:
            log_ctx.warning(f"Failed to load extraction_result.json: {e}")

    # Determine project type (default to row_house+repair)
    project_type = "row_house"
    scope_type = "repair"
    if extraction_result:
        project_type = extraction_result.get("project_type", "row_house")
        scope_type = extraction_result.get("scope_type", "repair")

    # Required sections for row_house+repair
    required_sections: list[str] = []
    required_sections_conditional: list[str] = []

    if project_type == "row_house" and scope_type == "repair":
        # Always required
        required_sections = ["parapet", "logistics", "permits"]
        # Conditionally required based on scope
        required_sections_conditional = ["lintels", "veneer", "repointing"]

    blockers: list[str] = []
    warnings: list[str] = []
    missing_sections: list[str] = []
    present_sections: list[str] = []
    section_details: dict[str, dict[str, Any]] = {}

    # Check each required section
    for section_key in required_sections:
        section = _find_section(proposal_sections, section_key)
        if section:
            present_sections.append(section_key)
            details = _evaluate_section(section, section_key)
            section_details[section_key] = details

            # Special check for parapet: must have >=1 line item + >=1 evidence ref
            if section_key == "parapet":
                if details["line_item_count"] == 0:
                    blockers.append("Parapet section must have at least 1 line item")
                if details["evidence_ref_count"] == 0:
                    blockers.append("Parapet section must have at least 1 evidence reference")
        else:
            missing_sections.append(section_key)
            blockers.append(f"Required section missing: {section_key}")

    # Check conditional sections
    if extraction_result:
        scope_items = extraction_result.get("scope_of_work", [])
        scope_text_lower = " ".join(
            [item.get("item", "") or item.get("description", "") for item in scope_items]
        ).lower()

        # Check for lintels
        if "lintel" in scope_text_lower:
            lintels_section = _find_section(proposal_sections, "lintels")
            if not lintels_section:
                missing_sections.append("lintels")
                blockers.append("Lintels section required (lintel scope detected)")

        # Check for brick/veneer
        if "brick" in scope_text_lower or "veneer" in scope_text_lower:
            veneer_section = _find_section(proposal_sections, "veneer")
            if not veneer_section:
                missing_sections.append("veneer")
                blockers.append("Veneer section required (brick/veneer scope detected)")

        # Check for repointing
        if "repoint" in scope_text_lower or "tuckpoint" in scope_text_lower or "mortar" in scope_text_lower:
            repointing_section = _find_section(proposal_sections, "repointing")
            if not repointing_section:
                missing_sections.append("repointing")
                warnings.append("Repointing section recommended (repointing scope detected)")

    # Check logistics section (template allowed but warn)
    logistics_section = proposal_sections.logistics_section
    if not logistics_section or len(logistics_section.line_item_ids) == 0:
        warnings.append("Logistics section has no line items (template-only)")

    # Check permits/inspections section (template allowed but warn)
    permits_section = proposal_sections.permits_inspections_section
    if not permits_section or len(permits_section.line_item_ids) == 0:
        warnings.append("Permits & Inspections section has no line items (template-only)")

    # Check exclusions (must be non-empty)
    if not proposal_sections.exclusions or len(proposal_sections.exclusions) == 0:
        blockers.append("Exclusions list must be non-empty")

    # Check assumptions (must be non-empty)
    if not proposal_sections.assumptions or len(proposal_sections.assumptions) == 0:
        blockers.append("Assumptions list must be non-empty")

    # Clarifications can be empty (no check needed)

    # Calculate score
    total_required = len(required_sections) + len([s for s in required_sections_conditional if s not in missing_sections])
    total_present = len(present_sections)
    score = total_present / total_required if total_required > 0 else 0.0

    # Pass if no blockers
    passed = len(blockers) == 0

    result = BidCompletenessResult(
        project_id=project_id,
        passed=passed,
        score=score,
        blockers=blockers,
        warnings=warnings,
        required_sections=required_sections + required_sections_conditional,
        missing_sections=missing_sections,
        present_sections=present_sections,
        section_details=section_details,
    )

    log_ctx.info(
        f"Bid completeness: passed={passed}, score={score:.2f}, "
        f"blockers={len(blockers)}, warnings={len(warnings)}"
    )

    return result


def _find_section(proposal_sections: ProposalSections, section_key: str) -> Any | None:
    """Find a scope section by key."""
    for section in proposal_sections.scope_sections:
        if section.section_key == section_key:
            return section
    return None


def _evaluate_section(section: Any, section_key: str) -> dict[str, Any]:
    """Evaluate a section's details."""
    return {
        "section_key": section_key,
        "title": section.title if hasattr(section, "title") else "",
        "line_item_count": len(section.line_item_ids) if hasattr(section, "line_item_ids") else 0,
        "evidence_ref_count": len(section.evidence_refs) if hasattr(section, "evidence_refs") else 0,
        "detail_ref_count": len(section.detail_refs) if hasattr(section, "detail_refs") else 0,
        "flags": section.flags if hasattr(section, "flags") else [],
    }





