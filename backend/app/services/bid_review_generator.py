"""Bid review generator (Phase 8.2).

Generates contractor-grade review breakdown of bid line items.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.schemas.bid_review import (
    BidLineItemReview,
    BidReview,
    EvidenceRef,
    MultiplierApplied,
    RuleRef,
)
from app.schemas.costing import CostItem


class BidReviewGenerator:
    """Generates bid review artifact from bid proposal and costing result."""

    def __init__(self) -> None:
        """Initialize bid review generator."""
        pass

    def generate(
        self,
        project_id: str,
        bid_proposal: dict[str, Any],
        costing_result: dict[str, Any],
        validation_report: dict[str, Any] | None = None,
        evidence_index: dict[str, Any] | None = None,
    ) -> BidReview:
        """
        Generate bid review artifact.

        Args:
            project_id: Project ID
            bid_proposal: Bid proposal JSON (from bid_proposal.json)
            costing_result: Costing result JSON (from costing_result.json)
            validation_report: Validation report JSON (optional, for recovery info)
            evidence_index: Evidence index JSON (optional, for evidence refs)

        Returns:
            BidReview artifact
        """
        log_ctx = logger.bind(project_id=project_id, stage="bid_review")
        log_ctx.info("Generating bid review")

        # Extract recovery info
        recovery_performed = False
        recovery_pages: list[int] = []
        if validation_report:
            recovery_performed = validation_report.get("rerun_performed", False)
            # Extract page numbers from rerun_notes
            rerun_notes = validation_report.get("rerun_notes", [])
            for note in rerun_notes:
                # Look for page numbers in notes (e.g., "Re-reading pages 5, 6")
                import re

                page_matches = re.findall(r"\b(\d+)\b", note)
                for match in page_matches:
                    try:
                        page_num = int(match)
                        if 1 <= page_num <= 1000:  # Reasonable page range
                            recovery_pages.append(page_num)
                    except ValueError:
                        pass
            recovery_pages = sorted(list(set(recovery_pages)))

        # Get line items from bid proposal
        line_items_data = bid_proposal.get("line_items", [])
        total_bid = bid_proposal.get("summary", {}).get("total_cost", 0.0)

        # Get cost items from costing result
        cost_items_by_scope: dict[str, CostItem] = {}
        for cost_item_data in costing_result.get("breakdown_by_scope_item", []):
            cost_item = CostItem.model_validate(cost_item_data)
            scope_item = cost_item.scope_item or cost_item.item_name
            cost_items_by_scope[scope_item] = cost_item

        # Generate review for each line item
        line_item_reviews: list[BidLineItemReview] = []
        for idx, line_item in enumerate(line_items_data):
            review = self._generate_line_item_review(
                project_id=project_id,
                line_item=line_item,
                line_item_index=idx,
                cost_items_by_scope=cost_items_by_scope,
                evidence_index=evidence_index,
                recovery_performed=recovery_performed,
                validation_report=validation_report,
            )
            line_item_reviews.append(review)

        compliance_costs = costing_result.get("compliance_costs", {}) or {}
        compliance_total = costing_result.get("compliance_total", 0.0)
        compliance_adjustments = costing_result.get("compliance_adjustments", []) or []

        if compliance_costs and "compliance" not in bid_proposal.get("summary", {}).get("cost_by_division", {}):
            compliance_entry = ", ".join(
                f"{key.title()} ${value:,.2f}" for key, value in compliance_costs.items()
            )
            logger.bind(project_id=project_id).info(
                f"Compliance costs included in review: {compliance_entry}"
            )

        bid_review = BidReview(
            project_id=project_id,
            total_bid=total_bid,
            line_items=line_item_reviews,
            recovery_performed=recovery_performed,
            recovery_pages=recovery_pages,
            compliance_adjustments=compliance_adjustments,
            compliance_costs=compliance_costs,
            compliance_total=compliance_total,
            generated_at=datetime.utcnow().isoformat(),
        )

        log_ctx.info(
            f"Bid review generated: {len(line_item_reviews)} line items, "
            f"recovery_performed={recovery_performed}"
        )

        return bid_review

    def _generate_line_item_review(
        self,
        project_id: str,
        line_item: dict[str, Any],
        line_item_index: int,
        cost_items_by_scope: dict[str, CostItem],
        evidence_index: dict[str, Any] | None,
        recovery_performed: bool,
        validation_report: dict[str, Any] | None = None,
    ) -> BidLineItemReview:
        """Generate review for a single line item."""
        division = line_item.get("division", "Unknown")
        description = line_item.get("description", "")
        quantity = line_item.get("quantity", 0.0)
        unit = line_item.get("unit", "EA")
        unit_cost = line_item.get("unit_cost", 0.0)
        total_cost = line_item.get("total_cost", 0.0)

        # Find matching cost item
        cost_item: CostItem | None = None
        for scope_key, cost_item_candidate in cost_items_by_scope.items():
            if scope_key.lower() in description.lower() or description.lower() in scope_key.lower():
                cost_item = cost_item_candidate
                break

        # Extract rule refs
        rule_refs: list[RuleRef] = []
        if cost_item and cost_item.rule_matched:
            rule_name = cost_item.rule_matched
            # Infer YAML file name from rule name
            yaml_file = f"{rule_name.replace(' ', '_').lower()}.yml"
            # Extract match keywords from item name and description
            match_keywords = self._extract_keywords(description)
            rule_refs.append(
                RuleRef(
                    rule_name=rule_name,
                    yaml_file=yaml_file,
                    match_keywords_used=match_keywords,
                )
            )

        # Extract multipliers
        multipliers_applied: list[MultiplierApplied] = []
        if cost_item:
            # From multipliers dict
            for mult_name, mult_factor in cost_item.multipliers.items():
                multipliers_applied.append(
                    MultiplierApplied(name=mult_name, factor=mult_factor)
                )
            # Waste factor
            if cost_item.waste_factor > 0:
                multipliers_applied.append(
                    MultiplierApplied(name="waste", factor=cost_item.waste_factor)
                )
            # Phase 10.10B: Add profile multiplier breakdown
            if hasattr(cost_item, 'multiplier_breakdown') and cost_item.multiplier_breakdown:
                for breakdown_item in cost_item.multiplier_breakdown:
                    # Parse breakdown item (e.g., "labor_rate: nyc masonry ($50/hr → $85/hr)")
                    # Extract a simplified factor if possible
                    multipliers_applied.append(
                        MultiplierApplied(name=f"profile: {breakdown_item}", factor=1.0)
                    )

                # Surface compliance-specific multipliers as explicit flags
                compliance_breakdowns = [
                    breakdown_item
                    for breakdown_item in cost_item.multiplier_breakdown
                    if any(keyword in breakdown_item.lower() for keyword in ["prevailing_wage", "union", "bond", "insurance", "compliance"])
                ]
                if compliance_breakdowns:
                    for line in compliance_breakdowns:
                        multipliers_applied.append(
                            MultiplierApplied(name=f"compliance: {line}", factor=1.0)
                        )

        # Map quantity_source
        quantity_source_map = {
            "from_drawing": "explicit_takeoff",
            "from_schedule": "explicit_takeoff",
            "computed_from_dimensions": "derived_from_dimensions",
            "heuristic": "heuristic",
            "allowance": "allowance",
            "unknown": "unknown",
        }
        quantity_source = "unknown"
        if cost_item:
            quantity_source = quantity_source_map.get(
                cost_item.quantity_source, "unknown"
            )

        # Extract evidence refs
        evidence_refs: list[EvidenceRef] = []
        if evidence_index:
            # Find evidence for this line item
            bid_item_evidence = evidence_index.get("bid_item_evidence", [])
            for evidence_data in bid_item_evidence:
                if evidence_data.get("line_item_index") == line_item_index:
                    for ref_data in evidence_data.get("evidence_references", []):
                        evidence_refs.append(
                            EvidenceRef(
                                page_number=ref_data.get("page_number", 1),
                                sheet_id=ref_data.get("sheet_id"),
                                snippet=ref_data.get("evidence_snippet"),
                            )
                        )
                    break

        # If no evidence from evidence_index, try cost_item quantity_evidence
        if not evidence_refs and cost_item and cost_item.quantity_evidence:
            qty_evidence = cost_item.quantity_evidence
            if isinstance(qty_evidence, dict):
                evidence_refs.append(
                    EvidenceRef(
                        page_number=qty_evidence.get("page_number", 1),
                        sheet_id=qty_evidence.get("sheet_id"),
                        snippet=qty_evidence.get("evidence_snippet"),
                    )
                )

        # Generate flags
        flags: list[str] = []
        if cost_item:
            # Recovered item flag - check if item was mentioned in recovery notes
            if recovery_performed:
                rerun_notes = validation_report.get("rerun_notes", [])
                description_lower = description.lower()
                for note in rerun_notes:
                    note_lower = note.lower()
                    # Check if description keywords appear in recovery notes
                    if any(
                        keyword in note_lower
                        for keyword in self._extract_keywords(description)
                    ):
                        flags.append("recovered_item")
                        break
            
            # Heuristic quantity flag
            if quantity_source == "heuristic":
                flags.append("heuristic_quantity")
            
            # Suspicious quantity flag
            if quantity_source != "allowance" and quantity <= 0.01:
                flags.append("suspicious_quantity")
            
            # Suspicious unit cost flag - check against rule base_unit_cost if available
            if unit_cost > 0 and cost_item.rule_matched:
                # Load rule to check typical unit cost range
                # For now, use simple thresholds based on unit type
                unit_lower = unit.lower()
                if unit_lower in ["sf", "sq ft", "sqft"]:
                    # SF items: suspicious if < $0.50 or > $500 per SF
                    if unit_cost < 0.5 or unit_cost > 500.0:
                        flags.append("suspicious_unit_cost")
                elif unit_lower in ["lf", "ln ft", "linear ft"]:
                    # LF items: suspicious if < $1 or > $1000 per LF
                    if unit_cost < 1.0 or unit_cost > 1000.0:
                        flags.append("suspicious_unit_cost")
                elif unit_lower in ["ea", "each"]:
                    # EA items: suspicious if < $1 or > $5000 per EA
                    if unit_cost < 1.0 or unit_cost > 5000.0:
                        flags.append("suspicious_unit_cost")
                elif unit_lower in ["cy", "cubic yard"]:
                    # CY items: suspicious if < $10 or > $2000 per CY
                    if unit_cost < 10.0 or unit_cost > 2000.0:
                        flags.append("suspicious_unit_cost")
                else:
                    # Generic: suspicious if < $1 or > $1000
                    if unit_cost < 1.0 or unit_cost > 1000.0:
                        flags.append("suspicious_unit_cost")

        # Generate line_item_id
        line_item_id = f"line_item_{line_item_index}"

        return BidLineItemReview(
            line_item_id=line_item_id,
            line_item_index=line_item_index,
            division=division,
            title=description,
            quantity=quantity,
            unit=unit,
            unit_cost=unit_cost,
            total_cost=total_cost,
            rule_refs=rule_refs,
            multipliers_applied=multipliers_applied,
            quantity_source=quantity_source,
            evidence_refs=evidence_refs,
            flags=flags,
        )

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract relevant keywords from text for rule matching."""
        text_lower = text.lower()
        keywords: list[str] = []

        # Common construction keywords
        keyword_patterns = [
            "parapet",
            "lintel",
            "repoint",
            "brick",
            "flashing",
            "crack",
            "repair",
            "rebuild",
            "replacement",
            "install",
            "demo",
            "demolition",
        ]

        for pattern in keyword_patterns:
            if pattern in text_lower:
                keywords.append(pattern)

        return keywords

