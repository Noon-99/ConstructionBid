"""Calibration pack generator (Phase 10.3).

Generates calibration pack JSON for contractor review and adjustment.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.schemas.bid_proposal import BidProposal
from app.schemas.bid_pricing_v2 import BidPricingV2
from app.schemas.calibration_pack import (
    CalibrationPack,
    LineItemCalibration,
    SuggestedAdjustments,
)
from app.schemas.contractor_profile import ContractorProfile
from app.core.config import Settings


def generate_calibration_pack(
    project_id: str,
    output_dir: Path,
    contractor_profile: ContractorProfile | None = None,
    region_id: str | None = None,
    settings: Settings | None = None,
) -> CalibrationPack:
    """
    Generate calibration pack for a project (Phase 10.3).

    Args:
        project_id: Project ID
        output_dir: Output directory containing artifacts
        contractor_profile: Contractor profile used (optional)
        region_id: Region identifier (optional)
        settings: Application settings (optional)

    Returns:
        CalibrationPack with key assumptions and suggested adjustments
    """
    log_ctx = logger.bind(project_id=project_id, service="calibration_pack_generator")
    log_ctx.info("Generating calibration pack")

    # Load bid_proposal
    bid_proposal_file = output_dir / "bid_proposal.json"
    if not bid_proposal_file.exists():
        raise FileNotFoundError(f"bid_proposal.json not found for project {project_id}")

    with open(bid_proposal_file, "r") as f:
        bid_proposal_data = json.load(f)
    bid_proposal = BidProposal.model_validate(bid_proposal_data)

    # Load pricing_v2 if available
    pricing_v2: BidPricingV2 | None = None
    pricing_v2_file = output_dir / "bid_pricing_v2.json"
    if pricing_v2_file.exists():
        try:
            with open(pricing_v2_file, "r") as f:
                pricing_v2_data = json.load(f)
            from app.schemas.bid_pricing_v2 import BidPricingV2

            pricing_v2 = BidPricingV2.model_validate(pricing_v2_data)
        except Exception as e:
            log_ctx.warning(f"Failed to load pricing_v2: {e}")

    # Extract profile_id
    profile_id = contractor_profile.profile_id if contractor_profile else None
    if not profile_id and pricing_v2:
        profile_id = pricing_v2.profile_id

    # Extract region_id
    if not region_id and pricing_v2:
        region_id = pricing_v2.region_id
    if not region_id and contractor_profile:
        region_id = contractor_profile.region

    # Process line items
    line_items_with_flags: list[tuple[int, Any, dict[str, bool]]] = []
    for idx, line_item in enumerate(bid_proposal.line_items):
        flags: dict[str, bool] = {}

        # Flag heuristic quantity
        if line_item.quantity_source == "heuristic":
            flags["heuristic_quantity"] = True

        # Flag suspicious unit cost (low confidence or unusual values)
        if line_item.confidence < 0.7:
            flags["suspicious_unit_cost"] = True
        elif line_item.unit_cost is not None:
            # Flag if unit_cost seems unusually high or low (heuristic thresholds)
            if line_item.unit:
                if line_item.unit.lower() in ["sf", "sq ft", "square feet"]:
                    if line_item.unit_cost > 500.0 or line_item.unit_cost < 1.0:
                        flags["suspicious_unit_cost"] = True
                elif line_item.unit.lower() in ["lf", "linear feet", "lin ft"]:
                    if line_item.unit_cost > 200.0 or line_item.unit_cost < 0.5:
                        flags["suspicious_unit_cost"] = True
                elif line_item.unit.lower() in ["each", "ea", "eaches"]:
                    if line_item.unit_cost > 10000.0 or line_item.unit_cost < 1.0:
                        flags["suspicious_unit_cost"] = True

        line_items_with_flags.append((idx, line_item, flags))

    # Get top 10 by cost
    top_items = sorted(
        line_items_with_flags, key=lambda x: x[1].total_cost, reverse=True
    )[:10]

    # Get flagged items
    flagged_items = [
        (idx, item, flags)
        for idx, item, flags in line_items_with_flags
        if flags.get("heuristic_quantity") or flags.get("suspicious_unit_cost")
    ]

    # Build LineItemCalibration objects
    def build_line_item_calibration(
        idx: int, line_item: Any, flags: dict[str, bool]
    ) -> LineItemCalibration:
        # Get component splits from pricing_v2 if available
        component_splits: dict[str, float] | None = None
        if pricing_v2:
            # Find matching pricing v2 line item
            pricing_item = next(
                (
                    pi
                    for pi in pricing_v2.line_items
                    if pi.line_item_id == str(idx)
                    or pi.title == line_item.description
                ),
                None,
            )
            if pricing_item:
                component_splits = {
                    comp.type: comp.amount for comp in pricing_item.components
                }

        return LineItemCalibration(
            line_item_id=str(idx),
            title=line_item.description,
            division=line_item.division,
            quantity=line_item.quantity,
            unit=line_item.unit,
            unit_cost=line_item.unit_cost,
            total_cost=line_item.total_cost,
            quantity_source=line_item.quantity_source,
            confidence=line_item.confidence,
            flags=[k for k, v in flags.items() if v],
            component_splits=component_splits,
        )

    top_line_items = [
        build_line_item_calibration(idx, item, flags) for idx, item, flags in top_items
    ]
    flagged_line_items = [
        build_line_item_calibration(idx, item, flags)
        for idx, item, flags in flagged_items
    ]

    # Build suggested adjustments
    suggested = _build_suggested_adjustments(
        bid_proposal, pricing_v2, contractor_profile, line_items_with_flags
    )

    pack = CalibrationPack(
        project_id=project_id,
        profile_id=profile_id,
        region_id=region_id,
        top_line_items=top_line_items,
        flagged_line_items=flagged_line_items,
        suggested_adjustments=suggested,
    )

    log_ctx.info(
        f"Calibration pack generated: {len(top_line_items)} top items, "
        f"{len(flagged_line_items)} flagged items"
    )

    return pack


def _build_suggested_adjustments(
    bid_proposal: BidProposal,
    pricing_v2: BidPricingV2 | None,
    contractor_profile: ContractorProfile | None,
    line_items_with_flags: list[tuple[int, Any, dict[str, bool]]],
) -> SuggestedAdjustments:
    """Build suggested adjustments based on bid data."""
    suggestions = SuggestedAdjustments()
    notes: list[str] = []

    # If profile exists, suggest current values as baseline
    if contractor_profile:
        # Suggest current labor rates
        if contractor_profile.labor_rates.masonry:
            suggestions.labor_rates["masonry"] = contractor_profile.labor_rates.masonry
        if contractor_profile.labor_rates.laborer:
            suggestions.labor_rates["laborer"] = contractor_profile.labor_rates.laborer

        # Suggest current logistics rates
        if "scaffold_weekly" in contractor_profile.logistics_rates:
            suggestions.scaffold_weekly_cost = contractor_profile.logistics_rates[
                "scaffold_weekly"
            ]
        if "dumpster_each" in contractor_profile.logistics_rates:
            suggestions.dumpster_cost = contractor_profile.logistics_rates[
                "dumpster_each"
            ]

        # Suggest current OHP
        suggestions.overhead_pct = contractor_profile.overhead_pct
        suggestions.profit_pct = contractor_profile.profit_pct
        notes.append("Current profile values shown as baseline for adjustment")
    else:
        notes.append("No profile loaded - using defaults as suggestions")

    # Analyze flagged items for adjustments
    heuristic_count = sum(
        1
        for _, _, flags in line_items_with_flags
        if flags.get("heuristic_quantity")
    )
    suspicious_count = sum(
        1
        for _, _, flags in line_items_with_flags
        if flags.get("suspicious_unit_cost")
    )

    if heuristic_count > 0:
        notes.append(
            f"{heuristic_count} line item(s) have heuristic quantities - consider adjusting"
        )
    if suspicious_count > 0:
        notes.append(
            f"{suspicious_count} line item(s) have suspicious unit costs - review and adjust"
        )

    suggestions.notes = notes
    return suggestions






