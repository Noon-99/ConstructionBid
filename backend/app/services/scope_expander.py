"""Scope expansion engine (Phase 9.2B).

Deterministically expands conceptual bids with contractor-grade items
like scaffolding, logistics, permits, and other items typically included
in contractor bids but may be omitted in conceptual bids.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal
from app.schemas.contractor_profile import ContractorProfile
from app.schemas.expanded_scope import ExpandedScope, ExpandedScopeItem, RegionResolution
from app.schemas.validation_report import ValidationReport
from app.services.contractor_profile_store import load_profile


class ScopeExpander:
    """Deterministic scope expansion engine (Phase 9.2B)."""

    def __init__(self, settings: Settings) -> None:
        """Initialize scope expander."""
        self.settings = settings

    def generate_expanded_scope(
        self,
        project_id: str,
        bid_proposal: BidProposal,
        validation_report: ValidationReport | None = None,
        profile_id: str | None = None,
        region_resolution: RegionResolution | None = None,
    ) -> ExpandedScope:
        """
        Generate expanded scope for a project (Phase 9.2B).

        Args:
            project_id: Project ID
            bid_proposal: Bid proposal to expand
            validation_report: Optional validation report
            profile_id: Optional contractor profile ID (uses default if None)

        Returns:
            ExpandedScope with added items
        """
        # Load contractor profile
        if profile_id is None:
            profile_id = self.settings.default_contractor_profile_id

        profile = load_profile(profile_id, self.settings)
        logger.bind(project_id=project_id).info(
            f"Generating expanded scope using profile: {profile_id} (region: {profile.region})"
        )

        items: list[ExpandedScopeItem] = []

        # Analyze bid proposal to determine what to add
        has_exterior_masonry = self._has_exterior_masonry(bid_proposal)
        has_parapet_work = self._has_parapet_work(bid_proposal)
        has_structural_lintel_work = self._has_structural_lintel_work(bid_proposal)
        is_nyc = profile.region == "NYC"

        # Rule 1: If bid contains exterior masonry items, add scaffolding, dumpsters, dust control
        if has_exterior_masonry:
            # Scaffolding
            scaffold_item = self._create_scaffolding_item(profile, bid_proposal)
            if scaffold_item:
                items.append(scaffold_item)

            # Debris removal / dumpsters
            dumpster_item = self._create_dumpster_item(profile, bid_proposal)
            if dumpster_item:
                items.append(dumpster_item)

            # Dust control & daily cleanup
            dust_control_item = self._create_dust_control_item(profile, bid_proposal)
            if dust_control_item:
                items.append(dust_control_item)

        # Rule 2: If parapet work exists, add temporary weather protection
        if has_parapet_work:
            weather_protection_item = self._create_weather_protection_item(profile, bid_proposal)
            if weather_protection_item:
                items.append(weather_protection_item)

        # Rule 3: If structural/lintel work exists, add special inspections
        if has_structural_lintel_work:
            inspections_item = self._create_special_inspections_item(profile, bid_proposal)
            if inspections_item:
                items.append(inspections_item)

        # Rule 4: If region is NYC, add sidewalk shed and permit filing
        if is_nyc:
            sidewalk_shed_item = self._create_sidewalk_shed_item(profile, bid_proposal)
            if sidewalk_shed_item:
                items.append(sidewalk_shed_item)

            permit_filing_item = self._create_permit_filing_item(profile, bid_proposal)
            if permit_filing_item:
                items.append(permit_filing_item)

        expanded_scope = ExpandedScope(
            project_id=project_id,
            profile_id=profile_id,
            items=items,
            region_resolution=region_resolution,
        )

        logger.bind(project_id=project_id).info(
            f"Generated expanded scope with {len(items)} items"
        )

        return expanded_scope

    def _has_exterior_masonry(self, bid_proposal: BidProposal) -> bool:
        """Check if bid contains exterior masonry items."""
        keywords = ["parapet", "brick", "repoint", "lintel", "masonry"]
        for item in bid_proposal.line_items:
            # Check division
            if item.division and ("04" in item.division or "Masonry" in item.division):
                return True
            # Check description keywords
            desc_lower = item.description.lower()
            if any(keyword in desc_lower for keyword in keywords):
                return True
        return False

    def _has_parapet_work(self, bid_proposal: BidProposal) -> bool:
        """Check if bid contains parapet work."""
        for item in bid_proposal.line_items:
            if "parapet" in item.description.lower():
                return True
        return False

    def _has_structural_lintel_work(self, bid_proposal: BidProposal) -> bool:
        """Check if bid contains structural or lintel work."""
        keywords = ["lintel", "structural", "steel", "beam", "column"]
        for item in bid_proposal.line_items:
            desc_lower = item.description.lower()
            if any(keyword in desc_lower for keyword in keywords):
                return True
        return False

    def _create_scaffolding_item(
        self, profile: ContractorProfile, bid_proposal: BidProposal
    ) -> ExpandedScopeItem | None:
        """Create scaffolding item if rate is available."""
        scaffold_rate = profile.logistics_rates.get("scaffold_weekly")
        if scaffold_rate is None:
            return ExpandedScopeItem(
                item_id="scaffold_001",
                title="Scaffolding",
                division="01",
                reason="Required for exterior masonry work above 6ft. Pricing not configured in contractor profile.",
                source="contractor_profile",
                confidence=0.9,
            )

        # Estimate duration: assume 4-8 weeks for typical row house project
        # This is a heuristic; could be improved with actual project duration calculation
        quantity = 6.0  # weeks
        total_cost = quantity * scaffold_rate

        return ExpandedScopeItem(
            item_id="scaffold_001",
            title="Scaffolding",
            division="01",
            quantity=quantity,
            unit="week",
            unit_cost=scaffold_rate,
            total_cost=total_cost,
            reason="Required for exterior masonry work above 6ft per OSHA requirements",
            source="contractor_profile",
            confidence=1.0,
            blocking=True,
        )

    def _create_dumpster_item(
        self, profile: ContractorProfile, bid_proposal: BidProposal
    ) -> ExpandedScopeItem | None:
        """Create dumpster/debris removal item."""
        dumpster_rate = profile.logistics_rates.get("dumpster_each")
        if dumpster_rate is None:
            return ExpandedScopeItem(
                item_id="dumpster_001",
                title="Debris Removal / Dumpster Rental",
                division="01",
                reason="Required for debris removal. Pricing not configured in contractor profile.",
                source="contractor_profile",
                confidence=0.9,
            )

        # Estimate: 1-2 dumpsters for typical row house project
        quantity = 2.0
        total_cost = quantity * dumpster_rate

        return ExpandedScopeItem(
            item_id="dumpster_001",
            title="Debris Removal / Dumpster Rental",
            division="01",
            quantity=quantity,
            unit="each",
            unit_cost=dumpster_rate,
            total_cost=total_cost,
            reason="Required for debris removal from masonry and demo work",
            source="contractor_profile",
            confidence=1.0,
        )

    def _create_dust_control_item(
        self, profile: ContractorProfile, bid_proposal: BidProposal
    ) -> ExpandedScopeItem | None:
        """Create dust control and daily cleanup item."""
        # Estimate project duration: assume 6-8 weeks
        quantity = 40.0  # days (5 days/week * 8 weeks)
        # Use allowance default if available, otherwise estimate $50/day
        unit_cost = profile.allowances_defaults.get("dust_control", 50.0)
        total_cost = quantity * unit_cost

        return ExpandedScopeItem(
            item_id="dust_control_001",
            title="Dust Control & Daily Cleanup",
            division="01",
            quantity=quantity,
            unit="day",
            unit_cost=unit_cost,
            total_cost=total_cost,
            reason="Required for daily cleanup and dust control during masonry work",
            source="contractor_profile",
            confidence=0.8,
        )

    def _create_weather_protection_item(
        self, profile: ContractorProfile, bid_proposal: BidProposal
    ) -> ExpandedScopeItem | None:
        """Create temporary weather protection item for parapet work."""
        return ExpandedScopeItem(
            item_id="weather_protection_001",
            title="Temporary Weather Protection",
            division="01",
            reason="Required for parapet work to protect exposed masonry during construction",
            source="rules",
            confidence=0.9,
            blocking=False,
        )

    def _create_special_inspections_item(
        self, profile: ContractorProfile, bid_proposal: BidProposal
    ) -> ExpandedScopeItem | None:
        """Create special inspections allowance for structural/lintel work."""
        # Use allowance default if available, otherwise estimate $2000
        amount = profile.allowances_defaults.get("inspections", 2000.0)

        return ExpandedScopeItem(
            item_id="special_inspections_001",
            title="Special Inspections Allowance",
            division="01",
            quantity=1.0,
            unit="LS",
            unit_cost=amount,
            total_cost=amount,
            reason="Required for structural/lintel work per building code requirements",
            source="rules",
            confidence=1.0,
            blocking=True,
        )

    def _create_sidewalk_shed_item(
        self, profile: ContractorProfile, bid_proposal: BidProposal
    ) -> ExpandedScopeItem | None:
        """Create sidewalk shed item for NYC projects."""
        shed_rate = profile.logistics_rates.get("sidewalk_shed_weekly")
        if shed_rate is None:
            return ExpandedScopeItem(
                item_id="sidewalk_shed_001",
                title="Sidewalk Shed Allowance",
                division="01",
                reason="Required for NYC projects per DOB requirements. Pricing not configured in contractor profile.",
                source="contractor_profile",
                confidence=0.9,
                blocking=True,
            )

        # Estimate duration: same as scaffolding
        quantity = 6.0  # weeks
        total_cost = quantity * shed_rate

        return ExpandedScopeItem(
            item_id="sidewalk_shed_001",
            title="Sidewalk Shed Allowance",
            division="01",
            quantity=quantity,
            unit="week",
            unit_cost=shed_rate,
            total_cost=total_cost,
            reason="Required for NYC projects per DOB requirements for work above sidewalk",
            source="contractor_profile",
            confidence=1.0,
            blocking=True,
        )

    def _create_permit_filing_item(
        self, profile: ContractorProfile, bid_proposal: BidProposal
    ) -> ExpandedScopeItem | None:
        """Create permit filing allowance for NYC projects."""
        # Use allowance default if available, otherwise estimate $2500
        amount = profile.allowances_defaults.get("permits", 2500.0)

        return ExpandedScopeItem(
            item_id="permit_filing_001",
            title="Permit Filing Allowance",
            division="01",
            quantity=1.0,
            unit="LS",
            unit_cost=amount,
            total_cost=amount,
            reason="Required for NYC projects per DOB permit filing requirements",
            source="contractor_profile",
            confidence=1.0,
            blocking=True,
        )


def generate_expanded_scope(
    project_id: str,
    output_dir: Path,
    settings: Settings,
    profile_id: str | None = None,
    region_resolution: RegionResolution | None = None,
) -> ExpandedScope:
    """
    Generate expanded scope for a project (Phase 9.2B).

    Convenience function that loads bid_proposal and validation_report from files.

    Args:
        project_id: Project ID
        output_dir: Output directory containing bid_proposal.json and validation_report.json
        settings: Application settings
        profile_id: Optional contractor profile ID (uses default if None)

    Returns:
        ExpandedScope object
    """
    # Load bid proposal
    bid_file = output_dir / "bid_proposal.json"
    if not bid_file.exists():
        raise FileNotFoundError(f"Bid proposal not found: {bid_file}")

    with open(bid_file, "r") as f:
        bid_data = json.load(f)
    bid_proposal = BidProposal.model_validate(bid_data)

    # Load validation report (optional)
    validation_report = None
    validation_file = output_dir / "validation_report.json"
    if validation_file.exists():
        with open(validation_file, "r") as f:
            validation_data = json.load(f)
        validation_report = ValidationReport.model_validate(validation_data)

    # Generate expanded scope
    expander = ScopeExpander(settings)
    return expander.generate_expanded_scope(
        project_id=project_id,
        bid_proposal=bid_proposal,
        validation_report=validation_report,
        profile_id=profile_id,
        region_resolution=region_resolution,
    )

