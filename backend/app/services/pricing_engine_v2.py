"""Pricing engine v2 for multi-component cost breakdowns (Phase 10.2).

Generates bid_pricing_v2.json with materials, labor, equipment, subcontract,
and overhead/profit breakdowns instead of single unit costs.
"""

from pathlib import Path
from typing import Any

from loguru import logger

from app.schemas.bid_pricing_v2 import (
    BidPricingV2,
    LineItemPricingV2,
    PricingComponent,
)
from app.schemas.bid_proposal import BidProposal
from app.schemas.contractor_profile import ContractorProfile
from app.core.config import Settings

# Default component splits (configurable)
DEFAULT_LABOR_PCT = 55.0
DEFAULT_MATERIAL_PCT = 35.0
DEFAULT_EQUIPMENT_PCT = 5.0
DEFAULT_OHP_PCT = 5.0

# Confidence levels
CONFIDENCE_PROFILE_DEFINED = 0.85
CONFIDENCE_DEFAULT_SPLIT = 0.60


def compute_pricing_v2(
    bid_proposal: BidProposal,
    contractor_profile: ContractorProfile | None = None,
    region_resolution: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> BidPricingV2:
    """
    Compute pricing v2 with multi-component breakdowns (Phase 10.2).

    Args:
        bid_proposal: Original bid proposal with unit costs
        contractor_profile: Contractor profile (optional, for component splits)
        region_resolution: Region resolution info (optional)
        settings: Application settings (optional)

    Returns:
        BidPricingV2 with component breakdowns for each line item
    """
    log_ctx = logger.bind(service="pricing_engine_v2")
    log_ctx.info(f"Computing pricing v2 for project {bid_proposal.project_id}")

    profile_id = contractor_profile.profile_id if contractor_profile else None
    region_id = None
    if region_resolution:
        region_id = region_resolution.get("region_id")

    line_items_pricing: list[LineItemPricingV2] = []
    totals_by_component: dict[str, float] = {
        "material": 0.0,
        "labor": 0.0,
        "equipment": 0.0,
        "subcontract": 0.0,
        "overhead_profit": 0.0,
    }

    # Process each line item
    for idx, line_item in enumerate(bid_proposal.line_items):
        line_item_id = str(idx)  # Use index as ID, or could use description hash
        total_cost = line_item.total_cost

        # Determine component splits
        splits, confidence, notes = _get_component_splits(
            line_item, contractor_profile, total_cost
        )

        # Create components
        components: list[PricingComponent] = []
        for component_type, amount in splits.items():
            if amount > 0.0:
                basis = _generate_component_basis(
                    component_type, line_item, contractor_profile, amount, total_cost
                )
                source_id = profile_id if contractor_profile else None

                components.append(
                    PricingComponent(
                        type=component_type,
                        amount=amount,
                        basis=basis,
                        source_id=source_id,
                    )
                )
                totals_by_component[component_type] += amount

        # Create line item pricing
        line_items_pricing.append(
            LineItemPricingV2(
                line_item_id=line_item_id,
                title=line_item.description,
                unit=line_item.unit,
                quantity=line_item.quantity,
                components=components,
                total=total_cost,
                confidence=confidence,
                notes=notes,
            )
        )

    # Calculate grand total
    grand_total = sum(item.total for item in line_items_pricing)

    result = BidPricingV2(
        project_id=bid_proposal.project_id,
        profile_id=profile_id,
        region_id=region_id,
        line_items=line_items_pricing,
        totals_by_component=totals_by_component,
        grand_total=grand_total,
    )

    log_ctx.info(
        f"Pricing v2 computed: {len(line_items_pricing)} items, "
        f"total=${grand_total:.2f}, "
        f"profile={profile_id or 'none'}"
    )

    return result


def _get_component_splits(
    line_item: Any,
    contractor_profile: ContractorProfile | None,
    total_cost: float,
) -> tuple[dict[str, float], float, list[str]]:
    """
    Get component splits for a line item.

    Returns:
        Tuple of (splits dict, confidence, notes list)
    """
    splits: dict[str, float] = {
        "material": 0.0,
        "labor": 0.0,
        "equipment": 0.0,
        "subcontract": 0.0,
        "overhead_profit": 0.0,
    }
    notes: list[str] = []

    # Check if profile provides explicit splits for this division/task
    # For now, we use default splits (future: extend profile schema)
    # TODO: Extend contractor_profile to include division-specific splits

    # Use default splits
    labor_pct = DEFAULT_LABOR_PCT
    material_pct = DEFAULT_MATERIAL_PCT
    equipment_pct = DEFAULT_EQUIPMENT_PCT
    ohp_pct = DEFAULT_OHP_PCT

    # Apply overhead and profit from profile if available
    if contractor_profile:
        # Calculate OHP based on profile settings
        # OHP is applied after base costs
        base_total = total_cost
        overhead_rate = contractor_profile.overhead_pct / 100.0
        profit_rate = contractor_profile.profit_pct / 100.0

        # Calculate OHP: base * (overhead + profit) / (1 + overhead + profit)
        # This gives us the OHP portion of the total
        ohp_total = base_total * (overhead_rate + profit_rate) / (
            1.0 + overhead_rate + profit_rate
        )
        base_less_ohp = base_total - ohp_total

        # Split base_less_ohp according to percentages
        splits["labor"] = base_less_ohp * (labor_pct / 100.0)
        splits["material"] = base_less_ohp * (material_pct / 100.0)
        splits["equipment"] = base_less_ohp * (equipment_pct / 100.0)
        splits["overhead_profit"] = ohp_total

        confidence = CONFIDENCE_PROFILE_DEFINED
        notes.append(
            f"OH/P applied: {contractor_profile.overhead_pct}% overhead, "
            f"{contractor_profile.profit_pct}% profit"
        )
    else:
        # Simple default split
        splits["labor"] = total_cost * (labor_pct / 100.0)
        splits["material"] = total_cost * (material_pct / 100.0)
        splits["equipment"] = total_cost * (equipment_pct / 100.0)
        splits["overhead_profit"] = total_cost * (ohp_pct / 100.0)

        confidence = CONFIDENCE_DEFAULT_SPLIT
        notes.append(
            f"Default split applied: labor {labor_pct}%, material {material_pct}%, "
            f"equipment {equipment_pct}%, OHP {ohp_pct}%"
        )

    # Normalize to ensure total matches exactly (handle rounding)
    total_split = sum(splits.values())
    if total_split > 0 and abs(total_split - total_cost) > 0.01:
        # Adjust largest component to match
        diff = total_cost - total_split
        largest_component = max(splits.items(), key=lambda x: x[1])
        splits[largest_component[0]] += diff

    return splits, confidence, notes


def _generate_component_basis(
    component_type: str,
    line_item: Any,
    contractor_profile: ContractorProfile | None,
    amount: float,
    total_cost: float,
) -> str:
    """Generate explicit basis text for a component."""
    pct = (amount / total_cost * 100.0) if total_cost > 0 else 0.0

    if component_type == "material":
        if contractor_profile:
            return (
                f"Material cost: ${amount:.2f} ({pct:.1f}%) - "
                f"based on contractor profile defaults for {line_item.division}"
            )
        return (
            f"Material cost: ${amount:.2f} ({pct:.1f}%) - "
            f"default split for {line_item.division}"
        )

    elif component_type == "labor":
        if contractor_profile:
            trade = _infer_trade_from_description(line_item.description)
            rate_info = ""
            if trade and hasattr(contractor_profile.labor_rates, trade):
                rate = getattr(contractor_profile.labor_rates, trade)
                if rate:
                    rate_info = f" (rate: ${rate:.2f}/hr)"
            return (
                f"Labor cost: ${amount:.2f} ({pct:.1f}%) - "
                f"based on contractor profile{trade and rate_info or ''}"
            )
        return (
            f"Labor cost: ${amount:.2f} ({pct:.1f}%) - "
            f"default split for {line_item.division}"
        )

    elif component_type == "equipment":
        return (
            f"Equipment cost: ${amount:.2f} ({pct:.1f}%) - "
            f"default split for {line_item.division}"
        )

    elif component_type == "subcontract":
        return (
            f"Subcontract cost: ${amount:.2f} ({pct:.1f}%) - "
            f"default split for {line_item.division}"
        )

    elif component_type == "overhead_profit":
        if contractor_profile:
            return (
                f"Overhead/Profit: ${amount:.2f} ({pct:.1f}%) - "
                f"{contractor_profile.overhead_pct}% overhead, "
                f"{contractor_profile.profit_pct}% profit from profile"
            )
        return (
            f"Overhead/Profit: ${amount:.2f} ({pct:.1f}%) - "
            f"default split for {line_item.division}"
        )

    return f"{component_type}: ${amount:.2f} ({pct:.1f}%)"


def _infer_trade_from_description(description: str) -> str | None:
    """Infer trade type from line item description."""
    desc_lower = description.lower()
    if any(word in desc_lower for word in ["masonry", "brick", "mortar", "parapet"]):
        return "masonry"
    elif any(word in desc_lower for word in ["concrete", "foundation", "slab"]):
        return "concrete"
    elif any(word in desc_lower for word in ["steel", "iron", "metal"]):
        return "steel"
    elif any(word in desc_lower for word in ["carpenter", "wood", "framing"]):
        return "carpenter"
    elif any(word in desc_lower for word in ["electrical", "wiring"]):
        return "electrician"
    elif any(word in desc_lower for word in ["plumbing", "plumber"]):
        return "plumber"
    return None






