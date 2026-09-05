"""Tests for labor synthesizer (Phase 9.3B)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.core.config import Settings
from app.schemas.bid_proposal import BidLineItem, BidProposal, BidSummary
from app.services.labor_synthesizer import LaborSynthesizer, generate_labor_breakdown


@pytest.fixture
def settings():
    """Test settings."""
    return Settings()


@pytest.fixture
def nyc_profile(settings):
    """Load NYC contractor profile."""
    from app.services.contractor_profile_store import load_profile

    return load_profile("nyc_row_house_masonry_v1", settings)


@pytest.fixture
def bid_proposal_with_repointing():
    """Create a bid proposal with repointing work."""
    line_items = [
        BidLineItem(
            division="04 Masonry",
            description="Brick repointing",
            quantity=600.0,
            unit="SF",
            unit_cost=8.0,
            total_cost=4800.0,
            basis="From drawings",
            confidence=0.9,
            quantity_source="from_drawing",
        ),
    ]

    return BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=4800.0, cost_by_division={"04": 4800.0}),
        line_items=line_items,
        allowances=[],
        alternates=[],
        clarifications=[],
    )


def test_labor_synthesizer_repointing_calculation(settings, nyc_profile, bid_proposal_with_repointing):
    """Test that repointing 600 SF with 120 SF/day productivity yields ~5 days."""
    synthesizer = LaborSynthesizer(settings)
    breakdown = synthesizer.generate_labor_breakdown(
        project_id="test_project",
        bid_proposal=bid_proposal_with_repointing,
        profile_id="nyc_row_house_masonry_v1",
    )

    assert breakdown.project_id == "test_project"
    assert breakdown.profile_id == "nyc_row_house_masonry_v1"
    assert len(breakdown.activities) == 1

    activity = breakdown.activities[0]
    assert activity.title == "Brick repointing"
    assert activity.quantity == 600.0
    assert activity.unit == "SF"
    assert activity.productivity_per_day == 120.0  # From profile
    assert activity.estimated_days == pytest.approx(5.0, abs=0.1)  # 600 / 120 = 5.0
    assert activity.crew == ["mason", "laborer"]

    # Calculate expected labor cost: 5 days * 8 hours * (85 + 65) = 5 * 8 * 150 = 6000
    expected_labor_cost = 5.0 * 8.0 * (85.0 + 65.0)  # days * hours * (mason + laborer rates)
    assert activity.labor_cost == pytest.approx(expected_labor_cost, abs=1.0)


def test_labor_synthesizer_parapet_calculation(settings):
    """Test parapet rebuild labor calculation."""
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
    ]

    bid_proposal = BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=7500.0, cost_by_division={"04": 7500.0}),
        line_items=line_items,
        allowances=[],
        alternates=[],
        clarifications=[],
    )

    synthesizer = LaborSynthesizer(settings)
    breakdown = synthesizer.generate_labor_breakdown(
        project_id="test_project",
        bid_proposal=bid_proposal,
        profile_id="nyc_row_house_masonry_v1",
    )

    assert len(breakdown.activities) == 1
    activity = breakdown.activities[0]
    assert activity.productivity_per_day == 10.0  # parapet_rebuild_lf_per_day
    assert activity.estimated_days == pytest.approx(5.0, abs=0.1)  # 50 / 10 = 5.0
    assert activity.crew == ["mason", "laborer"]


def test_labor_synthesizer_lintel_calculation(settings):
    """Test lintel replacement labor calculation."""
    line_items = [
        BidLineItem(
            division="05 Metals",
            description="Steel lintel replacement",
            quantity=3.0,
            unit="each",
            unit_cost=1200.0,
            total_cost=3600.0,
            basis="From drawings",
            confidence=0.9,
            quantity_source="from_drawing",
        ),
    ]

    bid_proposal = BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=3600.0, cost_by_division={"05": 3600.0}),
        line_items=line_items,
        allowances=[],
        alternates=[],
        clarifications=[],
    )

    synthesizer = LaborSynthesizer(settings)
    breakdown = synthesizer.generate_labor_breakdown(
        project_id="test_project",
        bid_proposal=bid_proposal,
        profile_id="nyc_row_house_masonry_v1",
    )

    assert len(breakdown.activities) == 1
    activity = breakdown.activities[0]
    assert activity.productivity_per_day == 2.0  # lintel_each_per_day
    assert activity.estimated_days == pytest.approx(1.5, abs=0.1)  # 3 / 2 = 1.5
    assert "steel" in activity.crew or "mason" in activity.crew  # Should use steel if available


def test_labor_synthesizer_deterministic(settings, bid_proposal_with_repointing):
    """Test that labor synthesis is deterministic (same input = same output)."""
    synthesizer = LaborSynthesizer(settings)
    breakdown_1 = synthesizer.generate_labor_breakdown(
        project_id="test_project",
        bid_proposal=bid_proposal_with_repointing,
        profile_id="nyc_row_house_masonry_v1",
    )
    breakdown_2 = synthesizer.generate_labor_breakdown(
        project_id="test_project",
        bid_proposal=bid_proposal_with_repointing,
        profile_id="nyc_row_house_masonry_v1",
    )

    # Should have same number of activities
    assert len(breakdown_1.activities) == len(breakdown_2.activities)

    # Should have same estimated days and labor costs
    for act1, act2 in zip(breakdown_1.activities, breakdown_2.activities):
        assert act1.estimated_days == act2.estimated_days
        assert act1.labor_cost == act2.labor_cost


def test_labor_synthesizer_missing_productivity(settings):
    """Test handling of missing productivity rates."""
    line_items = [
        BidLineItem(
            division="09 Finishes",
            description="Paint walls",
            quantity=1000.0,
            unit="SF",
            unit_cost=2.0,
            total_cost=2000.0,
            basis="From drawings",
            confidence=0.9,
            quantity_source="from_drawing",
        ),
    ]

    bid_proposal = BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=2000.0, cost_by_division={"09": 2000.0}),
        line_items=line_items,
        allowances=[],
        alternates=[],
        clarifications=[],
    )

    synthesizer = LaborSynthesizer(settings)
    breakdown = synthesizer.generate_labor_breakdown(
        project_id="test_project",
        bid_proposal=bid_proposal,
        profile_id="nyc_row_house_masonry_v1",
    )

    assert len(breakdown.activities) == 1
    activity = breakdown.activities[0]
    assert activity.productivity_per_day is None
    assert activity.estimated_days is None
    assert activity.labor_cost is None
    assert "Productivity rate not configured" in activity.reason


def test_generate_labor_breakdown_from_files(settings, bid_proposal_with_repointing):
    """Test generate_labor_breakdown convenience function that loads from files."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Save bid proposal
        bid_file = output_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            f.write(bid_proposal_with_repointing.model_dump_json(indent=2))

        # Generate labor breakdown
        breakdown = generate_labor_breakdown(
            project_id="test_project",
            output_dir=output_dir,
            settings=settings,
        )

        assert breakdown.project_id == "test_project"
        assert len(breakdown.activities) == 1
        assert breakdown.activities[0].estimated_days == pytest.approx(5.0, abs=0.1)


def test_labor_synthesizer_skips_allowances(settings):
    """Test that items without quantity (allowances) are skipped."""
    line_items = [
        BidLineItem(
            division="01 General Requirements",
            description="Permit allowance",
            quantity=None,  # Allowance item
            unit=None,
            unit_cost=None,
            total_cost=2500.0,
            basis="Allowance",
            confidence=1.0,
            quantity_source=None,
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

    bid_proposal = BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=6500.0, cost_by_division={"01": 2500.0, "04": 4000.0}),
        line_items=line_items,
        allowances=[],
        alternates=[],
        clarifications=[],
    )

    synthesizer = LaborSynthesizer(settings)
    breakdown = synthesizer.generate_labor_breakdown(
        project_id="test_project",
        bid_proposal=bid_proposal,
        profile_id="nyc_row_house_masonry_v1",
    )

    # Should only have one activity (the repointing, not the allowance)
    assert len(breakdown.activities) == 1
    assert breakdown.activities[0].title == "Brick repointing"






