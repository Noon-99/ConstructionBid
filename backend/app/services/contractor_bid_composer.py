"""Contractor bid composer (Phase 9.4B).

Composes a contractor-grade bid from conceptual bid, expanded scope, labor breakdown,
and contractor profile.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal
from app.schemas.contractor_bid import (
    ContractorBid,
    ContractorBidLineItem,
    ContractorBidSection,
)
from app.schemas.contractor_profile import ContractorProfile
from app.schemas.costing import CostEngineResult
from app.schemas.expanded_scope import ExpandedScope, RegionResolution
from app.schemas.labor_breakdown import LaborBreakdown
from app.services.contractor_profile_store import load_profile


class ContractorBidComposer:
    """Composes contractor-grade bids (Phase 9.4B)."""

    def __init__(self, settings: Settings) -> None:
        """Initialize contractor bid composer."""
        self.settings = settings

    def compose_contractor_bid(
        self,
        project_id: str,
        bid_proposal: BidProposal,
        expanded_scope: ExpandedScope | None = None,
        labor_breakdown: LaborBreakdown | None = None,
        costing_result: CostEngineResult | None = None,
        profile_id: str | None = None,
        region_resolution: RegionResolution | None = None,
    ) -> ContractorBid:
        """
        Compose a contractor-grade bid (Phase 9.4B).

        Args:
            project_id: Project ID
            bid_proposal: Conceptual bid proposal
            expanded_scope: Optional expanded scope
            labor_breakdown: Optional labor breakdown
            profile_id: Optional contractor profile ID (uses default if None)

        Returns:
            ContractorBid object
        """
        # Load contractor profile
        if profile_id is None:
            profile_id = self.settings.default_contractor_profile_id

        profile = load_profile(profile_id, self.settings)
        logger.bind(project_id=project_id).info(
            f"Composing contractor bid using profile: {profile_id}"
        )

        # Start with conceptual line items (Base Scope)
        base_scope_items: list[ContractorBidLineItem] = []
        base_scope_total = 0.0

        for line_item in bid_proposal.line_items:
            bid_item = ContractorBidLineItem(
                item_id=f"bid_item_{len(base_scope_items):03d}",
                title=line_item.description,
                division=line_item.division,
                quantity=line_item.quantity,
                unit=line_item.unit,
                unit_cost=line_item.unit_cost,
                total_cost=line_item.total_cost,
                basis=line_item.basis,
            )
            base_scope_items.append(bid_item)
            base_scope_total += line_item.total_cost

        # Create Base Scope section
        base_scope_section = ContractorBidSection(
            section_id="base_scope",
            title="Base Scope (from drawings)",
            division=None,
            line_items=base_scope_items,
            subtotal=base_scope_total,
        )

        sections: list[ContractorBidSection] = [base_scope_section]

        # Add expanded scope items
        logistics_items: list[ContractorBidLineItem] = []
        permits_items: list[ContractorBidLineItem] = []
        logistics_total = 0.0
        permits_total = 0.0

        if expanded_scope:
            for item in expanded_scope.items:
                # Skip items without total_cost
                if item.total_cost is None:
                    continue

                contractor_item = ContractorBidLineItem(
                    item_id=item.item_id,
                    title=item.title,
                    division=item.division,
                    quantity=item.quantity,
                    unit=item.unit,
                    unit_cost=item.unit_cost,
                    total_cost=item.total_cost or 0.0,
                    basis=item.reason,
                )

                # Categorize: permits/inspections vs logistics
                title_lower = item.title.lower()
                if any(
                    keyword in title_lower
                    for keyword in ["permit", "inspection", "filing", "allowance"]
                ):
                    permits_items.append(contractor_item)
                    permits_total += item.total_cost or 0.0
                else:
                    logistics_items.append(contractor_item)
                    logistics_total += item.total_cost or 0.0

        # Create Logistics section
        if logistics_items:
            logistics_section = ContractorBidSection(
                section_id="logistics",
                title="Logistics & Protection",
                division="01",
                line_items=logistics_items,
                subtotal=logistics_total,
            )
            sections.append(logistics_section)

        # Permits and inspections are stored separately (not in sections)
        # They're already in permits_items list

        # Add labor breakdown (if available)
        labor_total = 0.0
        labor_items: list[ContractorBidLineItem] = []

        if labor_breakdown and labor_breakdown.total_labor_cost:
            labor_total = labor_breakdown.total_labor_cost

            # Create labor line items from activities
            for activity in labor_breakdown.activities:
                if activity.labor_cost is None:
                    continue

                labor_item = ContractorBidLineItem(
                    item_id=activity.activity_id,
                    title=f"Labor: {activity.title}",
                    division=None,
                    quantity=activity.estimated_days,
                    unit="days",
                    unit_cost=None,  # Labor cost is total, not per day
                    total_cost=activity.labor_cost,
                    basis=activity.reason,
                )
                labor_items.append(labor_item)

            if labor_items:
                labor_section = ContractorBidSection(
                    section_id="labor",
                    title="Labor (derived)",
                    division=None,
                    line_items=labor_items,
                    subtotal=labor_total,
                )
                sections.append(labor_section)
        elif costing_result and costing_result.labor_cost_total > 0:
            # Fallback: Extract labor from costing_result if labor_breakdown doesn't exist
            labor_total = costing_result.labor_cost_total
            labor_item = ContractorBidLineItem(
                item_id="labor_embedded",
                title="Labor (from base scope items)",
                division=None,
                quantity=None,
                unit=None,
                unit_cost=None,
                total_cost=labor_total,
                basis="Labor costs embedded in base scope unit costs",
            )
            labor_items.append(labor_item)
            labor_section = ContractorBidSection(
                section_id="labor",
                title="Labor (extracted from base scope)",
                division=None,
                line_items=labor_items,
                subtotal=labor_total,
            )
            sections.append(labor_section)

        # Calculate subtotal before overhead/profit/contingency
        subtotal_before_ohp = (
            base_scope_total + logistics_total + permits_total + labor_total
        )

        # Apply overhead and profit
        overhead_pct = profile.overhead_pct
        profit_pct = profile.profit_pct
        contingency_pct = profile.contingency_pct

        overhead_amount = subtotal_before_ohp * (overhead_pct / 100.0)
        profit_amount = subtotal_before_ohp * (profit_pct / 100.0)
        contingency_amount = subtotal_before_ohp * (contingency_pct / 100.0)

        # Create Overhead & Profit section
        ohp_items: list[ContractorBidLineItem] = [
            ContractorBidLineItem(
                item_id="overhead",
                title="Overhead",
                division="01",
                quantity=None,
                unit=None,
                unit_cost=None,
                total_cost=overhead_amount,
                basis=f"Overhead at {overhead_pct}%",
            ),
            ContractorBidLineItem(
                item_id="profit",
                title="Profit",
                division="01",
                quantity=None,
                unit=None,
                unit_cost=None,
                total_cost=profit_amount,
                basis=f"Profit at {profit_pct}%",
            ),
        ]

        ohp_section = ContractorBidSection(
            section_id="overhead_profit",
            title="Overhead & Profit",
            division="01",
            line_items=ohp_items,
            subtotal=overhead_amount + profit_amount,
        )
        sections.append(ohp_section)

        # Create Contingency section (prioritize costing recommendation if available)
        contingency_item_basis = f"Contingency at {contingency_pct}%"
        if costing_result and costing_result.contingency_recommendation_pct is not None:
            contingency_pct = costing_result.contingency_recommendation_pct
            contingency_amount = costing_result.contingency_recommendation_amount or contingency_amount
            contingency_item_basis = (
                "Contingency per costing recommendation "
                f"({contingency_pct:.2f}% of base + compliance)"
            )

        contingency_item = ContractorBidLineItem(
            item_id="contingency",
            title="Contingency",
            division="01",
            quantity=None,
            unit=None,
            unit_cost=None,
            total_cost=contingency_amount,
            basis=contingency_item_basis,
        )

        contingency_section = ContractorBidSection(
            section_id="contingency",
            title="Contingency",
            division="01",
            line_items=[contingency_item],
            subtotal=contingency_amount,
        )
        sections.append(contingency_section)

        # Compliance cost section
        compliance_items: list[ContractorBidLineItem] = []
        compliance_total = 0.0
        if costing_result and costing_result.compliance_costs:
            for key, value in costing_result.compliance_costs.items():
                compliance_items.append(
                    ContractorBidLineItem(
                        item_id=f"compliance_{key}",
                        title=f"Compliance: {key.title()}",
                        division="01",
                        quantity=None,
                        unit=None,
                        unit_cost=None,
                        total_cost=value,
                        basis="Derived from compliance settings in cost engine",
                    )
                )
                compliance_total += value

        if compliance_items:
            compliance_section = ContractorBidSection(
                section_id="compliance",
                title="Compliance Costs",
                division="01",
                line_items=compliance_items,
                subtotal=compliance_total,
            )
            sections.append(compliance_section)

        # Calculate total bid
        total_bid = (
            subtotal_before_ohp + overhead_amount + profit_amount + contingency_amount + compliance_total
        )

        # Build subtotals dict
        subtotals = {
            "base_scope": base_scope_total,
            "logistics": logistics_total,
            "permits": permits_total,
            "labor": labor_total,
            "overhead": overhead_amount,
            "profit": profit_amount,
            "contingency": contingency_amount,
            "compliance": compliance_total,
        }

        # Build exclusions and assumptions
        exclusions = self._build_exclusions(profile)
        assumptions = self._build_assumptions(bid_proposal, profile)

        contractor_bid = ContractorBid(
            project_id=project_id,
            bid_mode="contractor",
            total_bid=total_bid,
            subtotals=subtotals,
            sections=sections,
            schedule=None,  # Can be added later
            payment_schedule=None,  # Can be added later
            permits_and_inspections=permits_items,
            logistics=logistics_items,
            exclusions=exclusions,
            assumptions=assumptions,
            region_resolution=region_resolution,
        )

        logger.bind(project_id=project_id).info(
            f"Composed contractor bid: total=${total_bid:.2f}, "
            f"base_scope=${base_scope_total:.2f}, "
            f"extras=${logistics_total + permits_total + labor_total:.2f}"
        )

        return contractor_bid

    def _build_exclusions(self, profile: ContractorProfile) -> list[str]:
        """Build default exclusions list."""
        exclusions = [
            "Site work not shown on drawings",
            "Interior finishes not specified",
            "Mechanical, electrical, and plumbing work (unless specified)",
            "Hazardous materials abatement",
            "Permits and fees beyond those listed",
            "Owner-furnished materials",
        ]

        # Add region-specific exclusions
        if profile.region == "NYC":
            exclusions.append("DOB violations and penalties")
            exclusions.append("Sidewalk repair beyond scope shown")

        return exclusions

    def _build_assumptions(
        self, bid_proposal: BidProposal, profile: ContractorProfile
    ) -> list[str]:
        """Build assumptions list from bid clarifications and defaults."""
        assumptions = [
            "Access to site is available during normal working hours",
            "No hazardous materials are present",
            "Existing conditions are as shown on drawings",
            "Weather conditions permit normal construction activities",
        ]

        # Add region-specific assumptions
        if profile.region == "NYC":
            assumptions.append("DOB permits will be obtained in timely manner")
            assumptions.append("Sidewalk protection per DOB requirements")

        # Add clarifications from bid proposal
        for clarification in bid_proposal.clarifications:
            assumptions.append(clarification.text)

        return assumptions


def compose_contractor_bid(
    project_id: str,
    output_dir: Path,
    settings: Settings,
    profile_id: str | None = None,
    region_resolution: RegionResolution | None = None,
) -> ContractorBid:
    """
    Compose contractor bid for a project (Phase 9.4B).

    Convenience function that loads all required artifacts from files.

    Args:
        project_id: Project ID
        output_dir: Output directory containing artifacts
        settings: Application settings
        profile_id: Optional contractor profile ID (uses default if None)

    Returns:
        ContractorBid object
    """
    # Load bid proposal
    bid_file = output_dir / "bid_proposal.json"
    if not bid_file.exists():
        raise FileNotFoundError(f"Bid proposal not found: {bid_file}")

    with open(bid_file, "r") as f:
        bid_data = json.load(f)
    bid_proposal = BidProposal.model_validate(bid_data)

    # Load expanded scope (optional)
    expanded_scope = None
    expanded_scope_file = output_dir / "expanded_scope.json"
    if expanded_scope_file.exists():
        with open(expanded_scope_file, "r") as f:
            expanded_scope_data = json.load(f)
        expanded_scope = ExpandedScope.model_validate(expanded_scope_data)

    # Load labor breakdown (optional)
    labor_breakdown = None
    labor_file = output_dir / "labor_breakdown.json"
    if labor_file.exists():
        with open(labor_file, "r") as f:
            labor_data = json.load(f)
        labor_breakdown = LaborBreakdown.model_validate(labor_data)

    # Load costing result (optional - used to extract labor if labor_breakdown doesn't exist)
    costing_result = None
    costing_file = output_dir / "costing_result.json"
    if costing_file.exists():
        with open(costing_file, "r") as f:
            costing_data = json.load(f)
        costing_result = CostEngineResult.model_validate(costing_data)

    # Compose contractor bid
    composer = ContractorBidComposer(settings)
    return composer.compose_contractor_bid(
        project_id=project_id,
        bid_proposal=bid_proposal,
        expanded_scope=expanded_scope,
        labor_breakdown=labor_breakdown,
        costing_result=costing_result,
        profile_id=profile_id,
        region_resolution=region_resolution,
    )

