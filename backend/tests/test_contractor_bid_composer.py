"""Tests for contractor bid composer (Phase 9.4B)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.core.config import Settings
from app.schemas.bid_proposal import BidAllowance, BidClarification, BidLineItem, BidProposal, BidSummary
from app.schemas.contractor_bid import ContractorBid
from app.schemas.expanded_scope import ExpandedScope, ExpandedScopeItem
from app.schemas.labor_breakdown import LaborActivity, LaborBreakdown
from app.services.contractor_bid_composer import ContractorBidComposer, compose_contractor_bid


@pytest.fixture
def settings():
    """Test settings."""
    return Settings()


@pytest.fixture
def bid_proposal_conceptual():
    """Create a conceptual bid proposal."""
    line_items = [
        BidLineItem(
            division="04 Masonry",
            description="Parapet rebuild",
            quantity=50.0,
            unit="LF",
            unit_cost=150.0,
            total_cost=7500.0,
            basis="From drawings",
            confidence=0.9,
            quantity_source="from_drawing",
        ),
        BidLineItem(
            division="04 Masonry",
            description="Brick repointing",
            quantity=500.0,
            unit="SF",
            unit_cost=8.0,
            total_cost=4000.0,
            basis="From drawings",
            confidence=0.9,
            quantity_source="from_drawing",
        ),
    ]

    return BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=11500.0, cost_by_division={"04": 11500.0}),
        line_items=line_items,
        allowances=[],
        alternates=[],
        clarifications=[
            BidClarification(text="Assumes access to site during normal hours", severity="info"),
        ],
    )


@pytest.fixture
def expanded_scope_sample():
    """Create sample expanded scope."""
    items = [
        ExpandedScopeItem(
            item_id="scaffold_001",
            title="Scaffolding",
            division="01",
            quantity=6.0,
            unit="week",
            unit_cost=1200.0,
            total_cost=7200.0,
            reason="Required for exterior work",
            source="contractor_profile",
            confidence=1.0,
        ),
        ExpandedScopeItem(
            item_id="permit_001",
            title="Permit Filing",
            division="01",
            quantity=None,
            unit=None,
            unit_cost=None,
            total_cost=2500.0,
            reason="NYC DOB requirements",
            source="contractor_profile",
            confidence=1.0,
        ),
    ]

    return ExpandedScope(
        project_id="test_project",
        profile_id="nyc_row_house_masonry_v1",
        items=items,
    )


@pytest.fixture
def labor_breakdown_sample():
    """Create sample labor breakdown."""
    activities = [
        LaborActivity(
            activity_id="activity_001",
            title="Parapet rebuild",
            related_bid_item_ids=["bid_item_0"],
            quantity=50.0,
            unit="LF",
            productivity_per_day=10.0,
            crew=["mason", "laborer"],
            estimated_days=5.0,
            labor_cost=6000.0,
            reason="From bid item: Parapet rebuild",
            confidence=0.9,
        ),
    ]

    return LaborBreakdown(
        project_id="test_project",
        profile_id="nyc_row_house_masonry_v1",
        activities=activities,
        total_labor_cost=6000.0,
    )


def test_contractor_bid_composer_basic(settings, bid_proposal_conceptual):
    """Test basic contractor bid composition with only conceptual bid."""
    composer = ContractorBidComposer(settings)
    contractor_bid = composer.compose_contractor_bid(
        project_id="test_project",
        bid_proposal=bid_proposal_conceptual,
    )

    assert contractor_bid.project_id == "test_project"
    assert contractor_bid.bid_mode == "contractor"
    assert contractor_bid.total_bid > bid_proposal_conceptual.summary.total_cost  # Should include overhead/profit/contingency
    assert len(contractor_bid.sections) >= 3  # Base scope + overhead/profit + contingency

    # Check base scope section
    base_scope_section = next(
        (s for s in contractor_bid.sections if s.section_id == "base_scope"), None
    )
    assert base_scope_section is not None
    assert base_scope_section.subtotal == 11500.0  # Sum of line items


def test_contractor_bid_composer_with_extras(
    settings, bid_proposal_conceptual, expanded_scope_sample, labor_breakdown_sample
):
    """Test contractor bid composition with expanded scope and labor breakdown."""
    composer = ContractorBidComposer(settings)
    contractor_bid = composer.compose_contractor_bid(
        project_id="test_project",
        bid_proposal=bid_proposal_conceptual,
        expanded_scope=expanded_scope_sample,
        labor_breakdown=labor_breakdown_sample,
    )

    # Total should be >= conceptual total when extras are present
    conceptual_total = bid_proposal_conceptual.summary.total_cost
    assert contractor_bid.total_bid >= conceptual_total

    # Check that expanded scope items are included
    assert len(contractor_bid.logistics) > 0  # Scaffolding should be in logistics
    assert len(contractor_bid.permits_and_inspections) > 0  # Permit should be in permits

    # Check that labor section exists
    labor_section = next(
        (s for s in contractor_bid.sections if s.section_id == "labor"), None
    )
    assert labor_section is not None
    assert labor_section.subtotal == 6000.0

    # Check subtotals
    assert contractor_bid.subtotals["base_scope"] == 11500.0
    assert contractor_bid.subtotals["logistics"] == 7200.0
    assert contractor_bid.subtotals["permits"] == 2500.0
    assert contractor_bid.subtotals["labor"] == 6000.0


def test_contractor_bid_composer_overhead_profit_contingency(
    settings, bid_proposal_conceptual
):
    """Test that overhead, profit, and contingency are applied correctly."""
    composer = ContractorBidComposer(settings)
    contractor_bid = composer.compose_contractor_bid(
        project_id="test_project",
        bid_proposal=bid_proposal_conceptual,
    )

    # Check overhead & profit section
    ohp_section = next(
        (s for s in contractor_bid.sections if s.section_id == "overhead_profit"), None
    )
    assert ohp_section is not None
    assert len(ohp_section.line_items) == 2  # Overhead and profit

    # Check contingency section
    contingency_section = next(
        (s for s in contractor_bid.sections if s.section_id == "contingency"), None
    )
    assert contingency_section is not None
    assert len(contingency_section.line_items) == 1

    # Verify percentages are applied (18% overhead, 12% profit, 5% contingency)
    base_total = contractor_bid.subtotals["base_scope"]
    expected_overhead = base_total * 0.18
    expected_profit = base_total * 0.12
    expected_contingency = base_total * 0.05

    assert contractor_bid.subtotals["overhead"] == pytest.approx(expected_overhead, abs=0.01)
    assert contractor_bid.subtotals["profit"] == pytest.approx(expected_profit, abs=0.01)
    assert contractor_bid.subtotals["contingency"] == pytest.approx(expected_contingency, abs=0.01)


def test_contractor_bid_composer_exclusions_assumptions(
    settings, bid_proposal_conceptual
):
    """Test that exclusions and assumptions are populated."""
    composer = ContractorBidComposer(settings)
    contractor_bid = composer.compose_contractor_bid(
        project_id="test_project",
        bid_proposal=bid_proposal_conceptual,
    )

    assert len(contractor_bid.exclusions) > 0
    assert len(contractor_bid.assumptions) > 0

    # Assumptions should include clarifications from bid proposal
    assert any("access to site" in a.lower() for a in contractor_bid.assumptions)


def test_compose_contractor_bid_from_files(
    settings, bid_proposal_conceptual, expanded_scope_sample, labor_breakdown_sample
):
    """Test compose_contractor_bid convenience function that loads from files."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Save artifacts
        bid_file = output_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            f.write(bid_proposal_conceptual.model_dump_json(indent=2))

        expanded_scope_file = output_dir / "expanded_scope.json"
        with open(expanded_scope_file, "w") as f:
            f.write(expanded_scope_sample.model_dump_json(indent=2))

        labor_file = output_dir / "labor_breakdown.json"
        with open(labor_file, "w") as f:
            f.write(labor_breakdown_sample.model_dump_json(indent=2))

        # Compose contractor bid
        contractor_bid = compose_contractor_bid(
            project_id="test_project",
            output_dir=output_dir,
            settings=settings,
        )

        assert contractor_bid.project_id == "test_project"
        assert contractor_bid.total_bid >= bid_proposal_conceptual.summary.total_cost

        # Note: compose_contractor_bid doesn't save the file - that's the endpoint's responsibility


def test_contractor_bid_total_includes_all_components(
    settings, bid_proposal_conceptual, expanded_scope_sample, labor_breakdown_sample
):
    """Test that contractor bid total includes all components correctly."""
    composer = ContractorBidComposer(settings)
    contractor_bid = composer.compose_contractor_bid(
        project_id="test_project",
        bid_proposal=bid_proposal_conceptual,
        expanded_scope=expanded_scope_sample,
        labor_breakdown=labor_breakdown_sample,
    )

    # Calculate expected total
    base_scope = contractor_bid.subtotals["base_scope"]
    logistics = contractor_bid.subtotals["logistics"]
    permits = contractor_bid.subtotals["permits"]
    labor = contractor_bid.subtotals["labor"]
    overhead = contractor_bid.subtotals["overhead"]
    profit = contractor_bid.subtotals["profit"]
    contingency = contractor_bid.subtotals["contingency"]

    # Overhead, profit, and contingency are calculated on subtotal before OH&P
    subtotal_before_ohp = base_scope + logistics + permits + labor
    expected_overhead = subtotal_before_ohp * 0.18
    expected_profit = subtotal_before_ohp * 0.12
    expected_contingency = subtotal_before_ohp * 0.05

    expected_total = (
        subtotal_before_ohp + expected_overhead + expected_profit + expected_contingency
    )

    assert contractor_bid.total_bid == pytest.approx(expected_total, abs=0.01)

