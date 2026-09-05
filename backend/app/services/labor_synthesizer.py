"""Labor synthesizer (Phase 9.3B).

Deterministically generates labor breakdown from bid proposal and contractor profile,
calculating crew composition, productivity, estimated days, and labor costs.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal
from app.schemas.contractor_profile import ContractorProfile
from app.schemas.expanded_scope import RegionResolution
from app.schemas.labor_breakdown import LaborActivity, LaborBreakdown
from app.services.contractor_profile_store import load_profile


class LaborSynthesizer:
    """Deterministic labor synthesizer (Phase 9.3B)."""

    def __init__(self, settings: Settings) -> None:
        """Initialize labor synthesizer."""
        self.settings = settings

    def generate_labor_breakdown(
        self,
        project_id: str,
        bid_proposal: BidProposal,
        profile_id: str | None = None,
        region_resolution: RegionResolution | None = None,
        trade_assemblies: Any | None = None,
    ) -> LaborBreakdown:
        """
        Generate labor breakdown for a project (Phase 9.3B, 11.1).

        Phase 11.1 enhancement: Uses explicit hours from trade assemblies when available.

        Args:
            project_id: Project ID
            bid_proposal: Bid proposal to analyze
            profile_id: Optional contractor profile ID (uses default if None)
            region_resolution: Optional region resolution
            trade_assemblies: Optional TradeAssembliesResult (Phase 11.1 - preferred source)

        Returns:
            LaborBreakdown with activities and costs
        """
        # Load contractor profile
        if profile_id is None:
            profile_id = self.settings.default_contractor_profile_id

        profile = load_profile(profile_id, self.settings)
        log_ctx = logger.bind(project_id=project_id)
        log_ctx.info(f"Generating labor breakdown using profile: {profile_id}")

        activities: list[LaborActivity] = []

        # Phase 11.1: If trade assemblies exist, use explicit hours from them
        if trade_assemblies is not None:
            log_ctx.info(
                f"Using trade assemblies for explicit labor hours ({len(trade_assemblies.assemblies)} assemblies)"
            )
            activities = self._generate_from_trade_assemblies(
                trade_assemblies, bid_proposal, profile
            )
        else:
            log_ctx.info("Trade assemblies not available, using keyword-based approach")
            # Fall back to existing keyword-based approach
            for idx, line_item in enumerate(bid_proposal.line_items):
                # Skip items without quantity (allowances, etc.)
                if line_item.quantity is None or line_item.unit is None:
                    continue

            # Determine crew and productivity based on keywords
            crew, productivity_per_day = self._determine_crew_and_productivity(
                line_item, profile
            )

            # Calculate estimated days if productivity is available
            estimated_days = None
            if productivity_per_day is not None and productivity_per_day > 0:
                estimated_days = line_item.quantity / productivity_per_day

            # Calculate labor cost if we have crew rates and estimated days
            labor_cost = None
            if crew and estimated_days is not None:
                labor_cost = self._calculate_labor_cost(crew, estimated_days, profile)

            # Create activity
            activity_id = f"activity_{idx:03d}"
            related_bid_item_ids = [f"bid_item_{idx}"]

            reason_parts = [f"From bid item: {line_item.description}"]
            if productivity_per_day is None:
                reason_parts.append("Productivity rate not configured in contractor profile")
            if not crew:
                reason_parts.append("Crew composition not determined")
            if labor_cost is None:
                if estimated_days is None:
                    reason_parts.append("Cannot calculate labor cost: missing productivity or crew rates")
                else:
                    reason_parts.append("Cannot calculate labor cost: missing crew rates")

            activity = LaborActivity(
                activity_id=activity_id,
                title=line_item.description,
                related_bid_item_ids=related_bid_item_ids,
                quantity=line_item.quantity,
                unit=line_item.unit,
                productivity_per_day=productivity_per_day,
                crew=crew,
                estimated_days=estimated_days,
                labor_cost=labor_cost,
                reason=". ".join(reason_parts),
                confidence=line_item.confidence if labor_cost is not None else 0.5,
            )

            activities.append(activity)

        # Calculate total labor cost
        total_labor_cost = sum(act.labor_cost or 0.0 for act in activities)

        breakdown = LaborBreakdown(
            project_id=project_id,
            profile_id=profile_id,
            activities=activities,
            total_labor_cost=total_labor_cost if total_labor_cost > 0 else None,
            region_resolution=region_resolution,
        )

        logger.bind(project_id=project_id).info(
            f"Generated labor breakdown with {len(activities)} activities, "
            f"total labor cost: ${total_labor_cost:.2f}" if total_labor_cost > 0 else "no labor costs calculated"
        )

        return breakdown

    def _determine_crew_and_productivity(
        self, line_item: Any, profile: ContractorProfile
    ) -> tuple[list[str], float | None]:
        """
        Determine crew composition and productivity for a bid line item.

        Returns:
            Tuple of (crew list, productivity_per_day)
        """
        desc_lower = line_item.description.lower()
        unit = line_item.unit.lower() if line_item.unit else ""

        # Keyword mapping rules
        # Repointing
        if "repoint" in desc_lower and unit in ["sf", "sqft", "sq ft"]:
            productivity = profile.crew_productivity.repointing_sf_per_day
            crew = ["mason", "laborer"]
            return (crew, productivity)

        # Parapet rebuild
        if "parapet" in desc_lower and unit in ["lf", "linear ft", "linear feet"]:
            productivity = profile.crew_productivity.parapet_rebuild_lf_per_day
            crew = ["mason", "laborer"]
            return (crew, productivity)

        # Lintel replacement
        if "lintel" in desc_lower and unit in ["each", "ea"]:
            productivity = profile.crew_productivity.lintel_each_per_day
            # Use steel worker if available, otherwise mason
            if profile.labor_rates.steel is not None:
                crew = ["steel", "laborer"]
            else:
                crew = ["mason", "laborer"]
            return (crew, productivity)

        # Flashing
        if "flash" in desc_lower and unit in ["lf", "linear ft", "linear feet"]:
            productivity = profile.crew_productivity.flashing_lf_per_day
            crew = ["carpenter", "laborer"]
            return (crew, productivity)

        # Brick rebuild
        if ("brick" in desc_lower or "masonry" in desc_lower) and "rebuild" in desc_lower and unit in ["sf", "sqft", "sq ft"]:
            productivity = profile.crew_productivity.brick_rebuild_sf_per_day
            crew = ["mason", "laborer"]
            return (crew, productivity)

        # CMU wall
        if "cmu" in desc_lower or "concrete block" in desc_lower:
            if "demo" in desc_lower and unit in ["sf", "sqft", "sq ft"]:
                productivity = profile.crew_productivity.demo_cmu_sf_per_day
                crew = ["laborer"]
                return (crew, productivity)
            elif unit in ["sf", "sqft", "sq ft"]:
                productivity = profile.crew_productivity.cmu_wall_sf_per_day
                crew = ["mason", "laborer"]
                return (crew, productivity)

        # Concrete footing
        if "footing" in desc_lower or "foundation" in desc_lower:
            if unit in ["cy", "cubic yard", "cubic yards"]:
                productivity = profile.crew_productivity.concrete_footing_cy_per_day
                crew = ["concrete", "laborer"]
                return (crew, productivity)

        # Slab on grade
        if "slab" in desc_lower and unit in ["sf", "sqft", "sq ft"]:
            productivity = profile.crew_productivity.slab_on_grade_sf_per_day
            crew = ["concrete", "laborer"]
            return (crew, productivity)

        # Window replacement
        if "window" in desc_lower and unit in ["each", "ea"]:
            productivity = profile.crew_productivity.window_replacement_each_per_day
            crew = ["carpenter", "laborer"]
            return (crew, productivity)

        # Door replacement
        if "door" in desc_lower and unit in ["each", "ea"]:
            productivity = profile.crew_productivity.door_replacement_each_per_day
            crew = ["carpenter", "laborer"]
            return (crew, productivity)

        # Default: no crew/productivity determined
        return ([], None)

    def _generate_from_trade_assemblies(
        self, trade_assemblies: Any, bid_proposal: BidProposal, profile: ContractorProfile
    ) -> list[LaborActivity]:
        """
        Generate labor activities from trade assemblies with explicit hours (Phase 11.1).

        Args:
            trade_assemblies: TradeAssembliesResult with assemblies containing labor components
            bid_proposal: Bid proposal for reference
            profile: Contractor profile for rate mapping

        Returns:
            List of LaborActivity objects
        """
        from app.schemas.trade_assemblies import TradeAssembliesResult

        # Convert to object if dict
        if isinstance(trade_assemblies, dict):
            trade_assemblies = TradeAssembliesResult.model_validate(trade_assemblies)

        activities: list[LaborActivity] = []
        activity_counter = 0

        # Process each trade assembly
        for assembly in trade_assemblies.assemblies:
            # Group labor components by trade/crew for aggregation
            labor_by_trade: dict[str, dict[str, Any]] = {}

            for labor_comp in assembly.labor:
                # Create key from trade + crew composition
                crew_key = "_".join(sorted(labor_comp.crew)) if labor_comp.crew else labor_comp.trade
                trade_key = labor_comp.trade

                # Aggregate labor hours by trade
                if trade_key not in labor_by_trade:
                    labor_by_trade[trade_key] = {
                        "hours": 0.0,
                        "crew": labor_comp.crew,
                        "rate": labor_comp.rate,
                        "total_cost": 0.0,
                        "basis_parts": [],
                        "assembly_ids": [],
                    }

                labor_by_trade[trade_key]["hours"] += labor_comp.hours
                labor_by_trade[trade_key]["total_cost"] += labor_comp.total_cost
                labor_by_trade[trade_key]["basis_parts"].append(labor_comp.basis)
                labor_by_trade[trade_key]["assembly_ids"].append(assembly.id)

            # Create labor activities from aggregated labor
            for trade, labor_data in labor_by_trade.items():
                # Calculate estimated days from hours (8 hours/day)
                estimated_days = labor_data["hours"] / 8.0 if labor_data["hours"] > 0 else None

                # Get related bid item IDs from assembly
                related_bid_item_ids = assembly.related_bid_item_ids

                # Create activity title
                activity_title = f"{assembly.title} - {trade.title()}"

                # Build reason with assembly info
                reason_parts = [
                    f"From trade assembly: {assembly.id}",
                    f"Explicit hours: {labor_data['hours']:.2f} hrs",
                    f"Basis: {'; '.join(labor_data['basis_parts'][:2])}",  # Limit to first 2
                ]

                activity = LaborActivity(
                    activity_id=f"activity_ta_{activity_counter:03d}",
                    title=activity_title,
                    related_bid_item_ids=related_bid_item_ids,
                    quantity=assembly.quantity,
                    unit=assembly.unit,
                    productivity_per_day=None,  # Not needed when using explicit hours
                    crew=labor_data["crew"],
                    estimated_days=estimated_days,
                    labor_cost=labor_data["total_cost"] if labor_data["total_cost"] > 0 else None,
                    reason=". ".join(reason_parts),
                    confidence=0.95,  # High confidence when using explicit hours from assemblies
                )

                activities.append(activity)
                activity_counter += 1

        logger.info(
            f"Generated {len(activities)} labor activities from {len(trade_assemblies.assemblies)} trade assemblies"
        )

        return activities

    def _calculate_labor_cost(
        self, crew: list[str], estimated_days: float, profile: ContractorProfile
    ) -> float | None:
        """
        Calculate labor cost for a crew over estimated days.

        Args:
            crew: List of crew role names (e.g., ["mason", "laborer"])
            estimated_days: Estimated number of days
            profile: Contractor profile with labor rates

        Returns:
            Total labor cost in dollars, or None if rates are missing
        """
        hours_per_day = 8.0
        total_hours = estimated_days * hours_per_day

        # Map crew role names to labor rate fields
        rate_map = {
            "mason": profile.labor_rates.masonry,
            "laborer": profile.labor_rates.laborer,
            "foreman": profile.labor_rates.foreman,
            "concrete": profile.labor_rates.concrete,
            "steel": profile.labor_rates.steel,
            "carpenter": profile.labor_rates.carpenter,
            "electrician": profile.labor_rates.electrician,
            "plumber": profile.labor_rates.plumber,
        }

        # Calculate total hourly rate for crew
        total_hourly_rate = 0.0
        for role in crew:
            rate = rate_map.get(role)
            if rate is None:
                # Missing rate for this role
                return None
            total_hourly_rate += rate

        # Calculate total labor cost
        labor_cost = total_hours * total_hourly_rate
        return labor_cost


def generate_labor_breakdown(
    project_id: str,
    output_dir: Path,
    settings: Settings,
    profile_id: str | None = None,
    region_resolution: RegionResolution | None = None,
    trade_assemblies: Any | None = None,
) -> LaborBreakdown:
    """
    Generate labor breakdown for a project (Phase 9.3B, 11.1).

    Convenience function that loads bid_proposal from file.
    Phase 11.1: Optionally uses trade assemblies for explicit hours.

    Args:
        project_id: Project ID
        output_dir: Output directory containing bid_proposal.json
        settings: Application settings
        profile_id: Optional contractor profile ID (uses default if None)
        region_resolution: Optional region resolution
        trade_assemblies: Optional TradeAssembliesResult (Phase 11.1 - preferred source)

    Returns:
        LaborBreakdown object
    """
    # Load bid proposal
    bid_file = output_dir / "bid_proposal.json"
    if not bid_file.exists():
        raise FileNotFoundError(f"Bid proposal not found: {bid_file}")

    with open(bid_file, "r") as f:
        bid_data = json.load(f)
    bid_proposal = BidProposal.model_validate(bid_data)

    # Load trade assemblies if not provided
    if trade_assemblies is None:
        assemblies_file = output_dir / "trade_assemblies.json"
        if assemblies_file.exists():
            try:
                with open(assemblies_file, "r") as f:
                    assemblies_data = json.load(f)
                from app.schemas.trade_assemblies import TradeAssembliesResult

                trade_assemblies = TradeAssembliesResult.model_validate(assemblies_data)
                logger.bind(project_id=project_id).info(
                    f"Loaded trade assemblies from {assemblies_file}"
                )
            except Exception as e:
                logger.bind(project_id=project_id).warning(
                    f"Failed to load trade assemblies: {e}, falling back to keyword-based approach"
                )
                trade_assemblies = None

    # Generate labor breakdown
    synthesizer = LaborSynthesizer(settings)
    return synthesizer.generate_labor_breakdown(
        project_id=project_id,
        bid_proposal=bid_proposal,
        profile_id=profile_id,
        region_resolution=region_resolution,
        trade_assemblies=trade_assemblies,
    )

