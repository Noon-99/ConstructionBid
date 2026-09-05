"""Bid proposal generator (Phase 4.6, 4.7).

Converts costing results into structured bid proposal JSON.
"""

from datetime import datetime
from typing import Literal

from loguru import logger

from app.schemas.bid_proposal import (
    BidAlternate,
    BidAllowance,
    BidClarification,
    BidLineItem,
    BidProposal,
    BidSummary,
)
from app.schemas.costing import CostEngineResult, CostItem
from app.schemas.extraction_result import ExtractionResult
from app.schemas.validation_report import ValidationReport


# CSI Division mapping
DIVISION_MAP: dict[str, str] = {
    "General": "01 General Requirements",
    "Masonry": "04 Masonry",
    "Concrete": "03 Concrete",
    "Structural": "05 Metals",
    "Waterproofing": "07 Thermal and Moisture Protection",
    "Repairs": "01 General Requirements",
    "Demo": "02 Existing Conditions",
    "Metals": "05 Metals",
    "Finishes": "09 Finishes",
    "Openings": "08 Openings",
}


def _map_category_to_division(category: str) -> str:
    """Map cost category to CSI division."""
    return DIVISION_MAP.get(category, "01 General Requirements")


def _cost_item_to_line_item(cost_item: CostItem, division: str) -> BidLineItem:
    """Convert CostItem to BidLineItem with quantity provenance (Phase 4.7)."""
    # Build basis with quantity provenance
    basis_parts = [cost_item.evidence or f"Matched rule: {cost_item.rule_matched}"]
    
    # Add quantity source information
    if cost_item.quantity_source and cost_item.quantity_source != "unknown":
        source_desc = {
            "from_drawing": "Quantity from drawing",
            "from_schedule": "Quantity from schedule",
            "computed_from_dimensions": "Quantity computed from dimensions",
            "allowance": "Allowance item",
            "heuristic": "Quantity estimated (heuristic)",
        }.get(cost_item.quantity_source, cost_item.quantity_source)
        basis_parts.append(f"Qty source: {source_desc}")
        
        if cost_item.quantity_evidence:
            if "page_number" in cost_item.quantity_evidence:
                basis_parts.append(f"Page {cost_item.quantity_evidence['page_number']}")
            if "computation_formula" in cost_item.quantity_evidence:
                basis_parts.append(f"Formula: {cost_item.quantity_evidence['computation_formula']}")
    
    # Phase 7.4: Include detail references in basis
    if cost_item.detail_refs:
        detail_refs_text = ", ".join(cost_item.detail_refs)
        basis_parts.append(f"Detail refs: {detail_refs_text}")

    # Phase 12.x: Surface compliance-driven multipliers in the bid narrative
    if cost_item.multiplier_breakdown:
        compliance_notes = [
            note
            for note in cost_item.multiplier_breakdown
            if any(keyword in note.lower() for keyword in ["prevailing_wage", "union", "bond", "insurance", "compliance"])
        ]
        if compliance_notes:
            basis_parts.append("Compliance adjustments: " + "; ".join(compliance_notes))

    basis = ". ".join(basis_parts)

    return BidLineItem(
        division=division,
        description=cost_item.item_name,
        quantity=cost_item.quantity,
        unit=cost_item.unit,
        unit_cost=cost_item.unit_cost,
        total_cost=cost_item.subtotal,
        basis=basis,
        confidence=0.8 if cost_item.rule_matched else 0.5,
        quantity_source=cost_item.quantity_source,
        quantity_confidence=cost_item.quantity_confidence,
    )


def generate_bid_proposal(
    project_id: str,
    extraction: ExtractionResult,
    costing: CostEngineResult,
    validation: ValidationReport,
    estimate_mode: Literal["conceptual", "bid_ready"] = "conceptual",
) -> BidProposal:
    """
    Generate bid proposal from extraction, costing, and validation results.

    Args:
        project_id: Project ID
        extraction: Extraction result from Stage 2
        costing: Cost engine result from Stage 4
        validation: Validation report from Stage 2.5
        estimate_mode: "conceptual" (allows heuristics) or "bid_ready" (requires evidence)

    Returns:
        BidProposal object
    """
    log_ctx = logger.bind(project_id=project_id, stage="bid_proposal_generator")
    log_ctx.info("Generating bid proposal")

    line_items: list[BidLineItem] = []
    allowances: list[BidAllowance] = []
    clarifications: list[BidClarification] = []
    cost_by_division: dict[str, float] = {}

    # Convert cost items to line items, grouped by division
    for breakdown in costing.breakdown_by_category:
        division = _map_category_to_division(breakdown.category)
        
        # Initialize division total
        if division not in cost_by_division:
            cost_by_division[division] = 0.0

        for cost_item in breakdown.items:
            line_item = _cost_item_to_line_item(cost_item, division)
            line_items.append(line_item)
            cost_by_division[division] += line_item.total_cost

    # Check for allowance-type items in cost items
    # (Allowances are identified by rule_matched containing "allowance" or unit_cost is None)
    for cost_item in costing.breakdown_by_scope_item:
        if "allowance" in (cost_item.rule_matched or "").lower():
            allowances.append(
                BidAllowance(
                    name=cost_item.item_name,
                    amount=cost_item.subtotal,
                    notes=cost_item.evidence or f"Allowance for {cost_item.item_name}",
                )
            )
            # Remove from line items if it was added
            line_items = [li for li in line_items if li.description != cost_item.item_name]

    # Add compliance costs as explicit line items (Phase 1: Compliance Cost Composer)
    compliance_costs = getattr(costing, "compliance_costs", {}) or {}
    if compliance_costs:
        compliance_division = "01 General Requirements"
        for cost_type, cost_amount in compliance_costs.items():
            if cost_amount > 0:
                # Create descriptive names based on cost type
                description_map = {
                    "bond": "Performance & Payment Bonds",
                    "insurance": "Supplemental Insurance",
                    "contingency": "Contingency",
                }
                description = description_map.get(cost_type, cost_type.title())
                
                # Create basis with explanation
                basis_parts = []
                if cost_type == "bond":
                    basis_parts.append("Required for public/government project")
                elif cost_type == "insurance":
                    basis_parts.append("Additional insurance requirements for public project")
                elif cost_type == "contingency":
                    basis_parts.append("Recommended contingency for project unknowns")
                
                compliance_item = BidLineItem(
                    division=compliance_division,
                    description=description,
                    quantity=1.0,
                    unit="lump",
                    unit_cost=cost_amount,
                    total_cost=cost_amount,
                    basis=". ".join(basis_parts) if basis_parts else f"{cost_type.title()} requirement",
                    confidence=0.9,
                    quantity_source="allowance",
                    quantity_confidence=0.9,
                )
                line_items.append(compliance_item)
                cost_by_division[compliance_division] = cost_by_division.get(compliance_division, 0.0) + cost_amount

    # Add clarifications from validation issues
    for issue in validation.issues:
        severity = "info"
        if issue.severity == "error":
            severity = "critical"
        elif issue.severity == "warning":
            severity = "warning"

        clarifications.append(
            BidClarification(
                text=f"{issue.message}. {issue.recommended_action}",
                severity=severity,
            )
        )

    # Add clarifications from missing data warnings
    for warning in costing.missing_data_warnings:
        clarifications.append(
            BidClarification(
                text=f"Cost data missing: {warning}. Estimate may be incomplete.",
                severity="warning",
            )
        )

    # Surface compliance adjustments from costing
    for adjustment in getattr(costing, "compliance_adjustments", []) or []:
        clarifications.append(
            BidClarification(
                text=f"Compliance adjustment applied: {adjustment}",
                severity="info",
            )
        )

    # Add clarifications for institutional projects if room program incomplete
    if extraction.project_type == "institutional":
        if extraction.room_program:
            room_count = len(extraction.room_program.rooms) if extraction.room_program.rooms else 0
            if room_count < 15:
                clarifications.append(
                    BidClarification(
                        text=f"Room program incomplete: only {room_count} rooms identified (expected >=15). "
                        "Some scope may be missing from estimate.",
                        severity="warning",
                    )
                )

        if not extraction.structural_notes:
            clarifications.append(
                BidClarification(
                    text="Structural notes not fully extracted. Structural costs may be incomplete.",
                    severity="warning",
                )
            )

    # Calculate totals (before adding compliance items)
    line_items_total_before_compliance = sum(item.total_cost for item in line_items)
    allowances_total = sum(allowance.amount for allowance in allowances)

    compliance_costs = getattr(costing, "compliance_costs", {}) or {}
    compliance_total = getattr(costing, "compliance_total", None)
    if compliance_total is None:
        compliance_total = round(sum(compliance_costs.values()), 2) if compliance_costs else 0.0

    base_scope_cost = getattr(costing, "base_scope_cost", None)
    if not base_scope_cost:
        base_scope_cost = line_items_total_before_compliance + allowances_total

    contingency_pct = getattr(costing, "contingency_recommendation_pct", None)
    contingency_amount = getattr(costing, "contingency_recommendation_amount", None)
    
    # Add contingency as explicit line item if recommended (Phase 1: Compliance Cost Composer)
    if contingency_amount and contingency_amount > 0:
        contingency_division = "01 General Requirements"
        contingency_item = BidLineItem(
            division=contingency_division,
            description="Contingency",
            quantity=1.0,
            unit="lump",
            unit_cost=contingency_amount,
            total_cost=contingency_amount,
            basis=f"Recommended {contingency_pct:.2f}% contingency for project unknowns and risk factors",
            confidence=0.8,
            quantity_source="allowance",
            quantity_confidence=0.8,
        )
        line_items.append(contingency_item)
        cost_by_division[contingency_division] = cost_by_division.get(contingency_division, 0.0) + contingency_amount

    # Recalculate totals after adding compliance items and contingency
    line_items_total = sum(item.total_cost for item in line_items)
    
    # Use cost engine's total_cost if available (it already includes compliance), otherwise calculate
    total_cost = getattr(costing, "total_cost", None)
    if total_cost is None or total_cost == 0:
        # Compliance items are now in line_items, so don't double-add compliance_total
        # But we need to account for contingency if it wasn't in the original total
        total_cost = line_items_total + allowances_total

    if compliance_total > 0:
        clarifications.append(
            BidClarification(
                text=(
                    "Compliance cost adders included in total: "
                    + ", ".join(
                        f"{key.title()} ${value:,.2f}" for key, value in compliance_costs.items()
                    )
                ),
                severity="info",
            )
        )

    if contingency_pct is not None and contingency_amount is not None:
        clarifications.append(
            BidClarification(
                text=(
                    f"Recommended contingency: {contingency_pct:.2f}% "
                    f"(~${contingency_amount:,.2f}) applied to base + compliance."
                ),
                severity="info",
            )
        )

    # Phase 4.7: Check bid readiness based on estimate_mode
    bid_ready = True
    if estimate_mode == "bid_ready":
        # Check for heuristic or unknown quantities in non-allowance items
        heuristic_items: list[str] = []
        for line_item in line_items:
            if line_item.quantity_source in ["heuristic", "unknown"]:
                heuristic_items.append(line_item.description)
        
        if heuristic_items:
            bid_ready = False
            clarifications.append(
                BidClarification(
                    text=(
                        f"CRITICAL: Bid not ready for submission. "
                        f"The following items use heuristic or unknown quantities: {', '.join(heuristic_items)}. "
                        f"These quantities must be verified from drawings or schedules before bid submission."
                    ),
                    severity="critical",
                )
            )
            log_ctx.warning(
                f"Bid not ready: {len(heuristic_items)} items with heuristic/unknown quantities"
            )

    summary = BidSummary(
        total_cost=total_cost,
        cost_by_division=cost_by_division,
        base_scope_cost=base_scope_cost,
        allowances_total=allowances_total,
        compliance_costs=compliance_costs,
        compliance_total=compliance_total,
        contingency_recommendation_pct=contingency_pct,
        contingency_recommendation_amount=contingency_amount,
    )

    proposal = BidProposal(
        project_id=project_id,
        summary=summary,
        line_items=line_items,
        allowances=allowances,
        alternates=[],  # Alternates not yet implemented
        clarifications=clarifications,
        generated_at=datetime.now(),
        estimate_mode=estimate_mode,
        bid_ready=bid_ready,
        bid_mode="conceptual",  # Phase 9.0: Default to conceptual mode
    )

    log_ctx.info(
        f"Bid proposal generated: ${total_cost:,.2f} total, "
        f"{len(line_items)} line items, {len(allowances)} allowances, "
        f"{len(clarifications)} clarifications"
    )

    return proposal

