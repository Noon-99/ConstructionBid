"""Compliance case study generator for pipeline artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings, get_settings
from app.schemas.case_study import ComplianceCaseStudy


def generate_compliance_case_study(
    project_id: str,
    output_dir: Path,
    settings: Settings | None = None,
) -> ComplianceCaseStudy:
    """Build compliance-focused case study artifact using saved pipeline outputs."""

    if settings is None:
        settings = get_settings()

    bid_proposal = _load_json(output_dir / "bid_proposal.json", "bid proposal")
    costing_result = _load_json(output_dir / "costing_result.json", "costing result")
    document_analysis = _load_json(
        output_dir / "document_analysis.json", "document analysis", required=False
    )
    trust_report = _load_json(output_dir / "trust_report.json", "trust report", required=False)
    bid_review = _load_json(output_dir / "bid_review.json", "bid review", required=False)

    project_name = None
    if trust_report and trust_report.get("project_name"):
        project_name = trust_report["project_name"]
    elif document_analysis:
        project_name = document_analysis.get("project_address")

    location = None
    if document_analysis:
        location = (
            document_analysis.get("project_location")
            or document_analysis.get("project_address")
            or (document_analysis.get("site_context") or {}).get("street_front")
        )

    issuing_authority = None
    procurement_context = None
    if document_analysis:
        procurement_context = document_analysis.get("procurement_context")
        if procurement_context:
            issuing_authority = (
                procurement_context.get("issuing_authority")
                or document_analysis.get("issuing_authority")
            )

    summary = bid_proposal.get("summary", {}) if bid_proposal else {}
    base_scope_cost = summary.get("base_scope_cost")
    compliance_total = summary.get("compliance_total")
    total_bid = summary.get("total_cost")
    compliance_breakdown = summary.get("compliance_costs", {})
    compliance_adjustments = costing_result.get("compliance_adjustments", []) if costing_result else []

    compliance_delta_pct = None
    if base_scope_cost and base_scope_cost > 0 and compliance_total is not None:
        compliance_delta_pct = round((compliance_total / base_scope_cost) * 100, 2)

    labor_regime = None
    bonds_required = False
    if document_analysis:
        labor_regime = document_analysis.get("labor_regime")
        bonds_required = bool(document_analysis.get("requires_bonds"))
    prevailing_wage_applied = labor_regime == "prevailing_wage"
    insurance_applied = bool(compliance_breakdown.get("insurance"))

    procurement_indicators: list[str] = []
    procurement_notes: list[str] = []
    evidence_references: list[Any] = []
    if procurement_context:
        procurement_indicators = procurement_context.get("indicators", []) or []
        procurement_notes = procurement_context.get("notes", []) or []
        candidate_pages = procurement_context.get("source_pages", []) or []
        if candidate_pages:
            evidence_references.append(
                {
                    "type": "procurement_pages",
                    "pages": candidate_pages,
                    "description": "Pages flagged for procurement indicators",
                }
            )

    validation_report = _load_json(
        output_dir / "validation_report.json",
        "validation report",
        required=False,
    )
    if validation_report:
        rerun_notes = validation_report.get("rerun_notes", [])
        if rerun_notes:
            evidence_references.append(
                {
                    "type": "validation_rerun_notes",
                    "notes": rerun_notes,
                }
            )

    if bid_review:
        recovery_notes = []
        if bid_review.get("recovery_performed"):
            recovery_notes.append("Recovery rerun performed for missing scope items")
        if bid_review.get("recovery_pages"):
            recovery_notes.append(
                "Recovery pages revisited: "
                + ", ".join(str(page) for page in bid_review.get("recovery_pages", []))
            )
        if recovery_notes:
            evidence_references.append(
                {
                    "type": "recovery",
                    "details": recovery_notes,
                }
            )

    confidence_pct = None
    confidence_explanation = None
    if trust_report:
        confidence_pct = trust_report.get("overall_confidence")
        confidence_explanation = trust_report.get("confidence_explanation")

    summary_text = _compose_summary(
        project_name=project_name,
        location=location,
        base_scope_cost=base_scope_cost,
        compliance_total=compliance_total,
        total_bid=total_bid,
        compliance_delta_pct=compliance_delta_pct,
        prevailing_wage_applied=prevailing_wage_applied,
        bonds_required=bonds_required,
        insurance_applied=insurance_applied,
        procurement_indicators=procurement_indicators,
    )

    recommendations = _compose_recommendations(
        compliance_breakdown=compliance_breakdown,
        prevailing_wage_applied=prevailing_wage_applied,
        bonds_required=bonds_required,
        procurement_notes=procurement_notes,
        compliance_adjustments=compliance_adjustments,
    )

    case_study = ComplianceCaseStudy(
        project_id=project_id,
        project_name=project_name,
        location=location,
        issuing_authority=issuing_authority,
        bid_submission_date=_extract_bid_date(document_analysis),
        base_scope_cost=base_scope_cost,
        compliance_total=compliance_total,
        total_bid=total_bid,
        compliance_delta_pct=compliance_delta_pct,
        compliance_breakdown=compliance_breakdown,
        compliance_adjustments=compliance_adjustments,
        prevailing_wage_applied=prevailing_wage_applied,
        bonds_required=bonds_required,
        insurance_applied=insurance_applied,
        procurement_indicators=procurement_indicators,
        procurement_notes=procurement_notes,
        evidence_references=evidence_references,
        confidence_pct=confidence_pct,
        confidence_explanation=confidence_explanation,
        summary=summary_text,
        recommendations=recommendations,
    )

    artifact_path = output_dir / "case_study.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(case_study.model_dump_json(indent=2))
    logger.bind(project_id=project_id).info(
        "Compliance case study generated",
        path=str(artifact_path),
    )

    return case_study


def _load_json(path: Path, label: str, required: bool = True) -> dict[str, Any] | None:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing {label} artifact at {path}")
        logger.debug(f"{label.title()} artifact missing at {path}, continuing without it")
        return None

    with open(path, "r") as f:
        return json.load(f)


def _extract_bid_date(document_analysis: dict[str, Any] | None) -> str | None:
    if not document_analysis:
        return None

    schedule = document_analysis.get("project_schedule")
    if isinstance(schedule, dict):
        bid_date = schedule.get("bid_submission_date")
        if bid_date:
            return bid_date

    metadata_date = document_analysis.get("bid_submission_date")
    if metadata_date:
        return metadata_date

    generated_at = document_analysis.get("generated_at")
    if generated_at:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            return generated_at
        except Exception:
            return None

    return None


def _compose_summary(
    project_name: str | None,
    location: str | None,
    base_scope_cost: float | None,
    compliance_total: float | None,
    total_bid: float | None,
    compliance_delta_pct: float | None,
    prevailing_wage_applied: bool,
    bonds_required: bool,
    insurance_applied: bool,
    procurement_indicators: list[str],
) -> str:
    parts: list[str] = []

    descriptor = project_name or "This project"
    if location:
        descriptor += f" in {location}"

    if base_scope_cost is not None and total_bid is not None:
        parts.append(
            f"{descriptor} moved from a base scope of ${base_scope_cost:,.0f} to a compliance-aware total of ${total_bid:,.0f}."
        )
    elif base_scope_cost is not None and compliance_total is not None:
        parts.append(
            f"{descriptor} added ${compliance_total:,.0f} in compliance safeguards on top of a ${base_scope_cost:,.0f} base scope."
        )
    else:
        parts.append(f"{descriptor} required compliance-focused adjustments.")

    if compliance_total and compliance_total > 0 and compliance_delta_pct is not None:
        parts.append(f"Compliance uplift represented {compliance_delta_pct:.1f}% of the base scope.")

    if prevailing_wage_applied:
        parts.append("Prevailing wage labor rates were applied based on detected procurement signals.")
    if bonds_required:
        parts.append("Bond requirements were included to satisfy public agency standards.")
    if insurance_applied and not bonds_required:
        parts.append("Supplemental insurance was added to align with public project expectations.")

    if procurement_indicators:
        cues = ", ".join(procurement_indicators[:5])
        if len(procurement_indicators) > 5:
            cues += ", ..."
        parts.append("Key compliance cues included: " + cues)

    return " ".join(parts)


def _compose_recommendations(
    compliance_breakdown: dict[str, float],
    prevailing_wage_applied: bool,
    bonds_required: bool,
    procurement_notes: list[str],
    compliance_adjustments: list[str],
) -> list[str]:
    recommendations: list[str] = []

    adjustments_text = "".join(compliance_adjustments).lower()

    if prevailing_wage_applied and "prevailing" not in adjustments_text:
        recommendations.append(
            "Confirm prevailing wage schedules with the agency to validate multiplier assumptions."
        )
    if bonds_required and "bond" not in adjustments_text:
        recommendations.append(
            "Coordinate with surety providers to lock bond pricing against the detected requirements."
        )
    if compliance_breakdown.get("insurance") and "insurance" not in adjustments_text:
        recommendations.append(
            "Review insurance riders to ensure coverage aligns with public procurement thresholds."
        )
    if procurement_notes:
        recommendations.append("Review procurement notes for additional submission obligations.")

    if not recommendations:
        recommendations.append("No outstanding compliance follow-ups identified.")

    return recommendations
