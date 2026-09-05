"""Typology confidence report generator (Phase 10.7).

Generates report explaining typology classification and routing decisions.
"""

from loguru import logger

from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.typology_confidence_report import (
    TypologyConfidenceReport,
    TypologyIndicator,
)


def generate_typology_confidence_report(
    project_id: str,
    document_analysis: DocumentAnalysis,
    routing_decision: str,
    routing_reason: str,
) -> TypologyConfidenceReport:
    """
    Generate typology confidence report (Phase 10.7).

    Args:
        project_id: Project ID
        document_analysis: Document analysis with resolved typology
        routing_decision: Routing decision ("row_house_path", "institutional_path", "fallback_row_house")
        routing_reason: Explanation for routing decision

    Returns:
        TypologyConfidenceReport with indicators and confidence
    """
    log_ctx = logger.bind(project_id=project_id, service="typology_confidence")
    log_ctx.info("Generating typology confidence report")

    indicators: list[TypologyIndicator] = []
    overall_confidence = 0.5  # Base confidence

    # Get final resolved type
    final_project_type = (
        document_analysis.resolved_project_type or document_analysis.project_type
    )
    original_project_type = document_analysis.project_type
    was_overridden = (
        document_analysis.resolved_project_type is not None
        and document_analysis.resolved_project_type != document_analysis.project_type
    )

    # Collect indicators from document analysis
    # 1. Sheet types
    if document_analysis.sheets:
        elevation_count = sum(1 for s in document_analysis.sheets if s.sheet_type == "elevation")
        plan_count = sum(1 for s in document_analysis.sheets if s.sheet_type == "plan")
        schedule_count = sum(1 for s in document_analysis.sheets if s.sheet_type == "schedule")

        if elevation_count > 0:
            strength = "strong" if elevation_count >= 2 else "moderate"
            confidence_contrib = 0.15 if elevation_count >= 2 else 0.10
            indicators.append(
                TypologyIndicator(
                    indicator_type="sheet_type",
                    indicator_value=f"{elevation_count} elevation sheet(s)",
                    strength=strength,
                    confidence_contribution=confidence_contrib,
                )
            )
            overall_confidence += confidence_contrib

        if plan_count > 0:
            indicators.append(
                TypologyIndicator(
                    indicator_type="sheet_type",
                    indicator_value=f"{plan_count} plan sheet(s)",
                    strength="moderate",
                    confidence_contribution=0.08,
                )
            )
            overall_confidence += 0.08

        if schedule_count > 0:
            strength = "strong" if schedule_count >= 2 else "moderate"
            confidence_contrib = 0.12 if schedule_count >= 2 else 0.08
            indicators.append(
                TypologyIndicator(
                    indicator_type="sheet_type",
                    indicator_value=f"{schedule_count} schedule sheet(s)",
                    strength=strength,
                    confidence_contribution=confidence_contrib,
                )
            )
            overall_confidence += confidence_contrib

    # 2. Location types (where quantities/scope live)
    if document_analysis.where_quantities_live:
        has_life_safety = any(
            loc.location_type == "life_safety_plan" for loc in document_analysis.where_quantities_live
        )
        has_room_schedule = any(
            loc.location_type == "room_schedule" for loc in document_analysis.where_quantities_live
        )

        if has_life_safety:
            indicators.append(
                TypologyIndicator(
                    indicator_type="location_type",
                    indicator_value="life_safety_plan",
                    strength="strong",
                    confidence_contribution=0.20,
                )
            )
            overall_confidence += 0.20

        if has_room_schedule:
            indicators.append(
                TypologyIndicator(
                    indicator_type="location_type",
                    indicator_value="room_schedule",
                    strength="strong",
                    confidence_contribution=0.18,
                )
            )
            overall_confidence += 0.18

    # 3. Building context
    if document_analysis.building_context:
        if document_analysis.building_context.is_row_context:
            indicators.append(
                TypologyIndicator(
                    indicator_type="building_context",
                    indicator_value="row_context=True",
                    strength="strong",
                    confidence_contribution=0.15,
                )
            )
            overall_confidence += 0.15

        if document_analysis.building_context.building_ids:
            indicators.append(
                TypologyIndicator(
                    indicator_type="building_context",
                    indicator_value=f"Multiple building IDs: {len(document_analysis.building_context.building_ids)}",
                    strength="moderate",
                    confidence_contribution=0.10,
                )
            )
            overall_confidence += 0.10

    # 4. Resolution notes (if typology was overridden)
    if was_overridden and document_analysis.resolution_notes:
        for note in document_analysis.resolution_notes:
            if "row-house indicators" in note.lower():
                indicators.append(
                    TypologyIndicator(
                        indicator_type="keyword_match",
                        indicator_value=f"Row-house override: {note}",
                        strength="strong",
                        confidence_contribution=0.12,
                    )
                )
                overall_confidence += 0.12

    # 5. Default fallback indicator (if low confidence)
    if overall_confidence < 0.4:
        indicators.append(
            TypologyIndicator(
                indicator_type="default_fallback",
                indicator_value="Low confidence - using conservative routing",
                strength="weak",
                confidence_contribution=-0.05,  # Reduces confidence
            )
        )
        overall_confidence = max(0.3, overall_confidence - 0.05)

    # Clamp confidence to 0.0-1.0
    overall_confidence = max(0.0, min(1.0, overall_confidence))

    report = TypologyConfidenceReport(
        project_id=project_id,
        final_project_type=final_project_type,
        original_project_type=original_project_type,
        overall_confidence=overall_confidence,
        indicators=indicators,
        routing_decision=routing_decision,
        routing_reason=routing_reason,
        was_overridden=was_overridden,
        override_reasons=document_analysis.resolution_notes if was_overridden else [],
    )

    log_ctx.info(
        f"Typology confidence report: {final_project_type} (confidence: {overall_confidence:.2%}, "
        f"routing: {routing_decision})"
    )

    return report






