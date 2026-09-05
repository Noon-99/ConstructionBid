"""Unit tests for general conditions estimator (Phase 10.1)."""

import pytest

from app.schemas.bid_proposal import BidLineItem, BidProposal, BidSummary
from app.services.general_conditions_estimator import estimate_general_conditions


@pytest.fixture
def sample_bid_proposal() -> BidProposal:
    """Create a sample bid proposal for testing."""
    line_items = [
        BidLineItem(
            division="04 Masonry",
            description="Parapet repair and rebuild",
            quantity=50.0,
            unit="LF",
            unit_cost=97.75,
            total_cost=4887.50,
            basis="From elevation drawings",
            confidence=0.9,
        ),
        BidLineItem(
            division="04 Masonry",
            description="Brick repointing",
            quantity=200.0,
            unit="SF",
            unit_cost=8.50,
            total_cost=1700.00,
            basis="From elevation notes",
            confidence=0.85,
        ),
    ]

    return BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=6587.50, cost_by_division={"04 Masonry": 6587.50}),
        line_items=line_items,
        allowances=[],
        clarifications=[],
        generated_at="2025-01-01T00:00:00",
        estimate_mode="conceptual",
        bid_ready=True,
    )


def test_estimate_general_conditions_row_house(sample_bid_proposal: BidProposal):
    """Test estimating GC for a row house project."""
    gc = estimate_general_conditions(
        project_id="test_project",
        building_type="row_house",
        bid_proposal=sample_bid_proposal,
        region_resolution={"region_id": "NYC", "confidence": 0.9, "evidence": []},
    )

    assert gc.project_id == "test_project"
    assert gc.building_type == "row_house"
    assert gc.region_id == "NYC"
    assert len(gc.items) > 0
    assert gc.total_cost > 0
    assert gc.estimated_duration_weeks > 0

    # Should have management item
    management_items = [item for item in gc.items if item.category == "management"]
    assert len(management_items) > 0

    # Should have site protection (exterior masonry work)
    protection_items = [item for item in gc.items if item.category == "site_protection"]
    assert len(protection_items) > 0  # Should have protection for exterior work


def test_estimate_general_conditions_institutional(sample_bid_proposal: BidProposal):
    """Test estimating GC for an institutional project."""
    gc = estimate_general_conditions(
        project_id="test_project",
        building_type="institutional",
        bid_proposal=sample_bid_proposal,
        region_resolution={"region_id": "US_DEFAULT", "confidence": 0.8, "evidence": []},
    )

    assert gc.building_type == "institutional"
    assert gc.estimated_duration_weeks >= 10.0  # Institutional projects are longer

    # Should have temporary facilities for institutional
    facilities_items = [item for item in gc.items if item.category == "temporary_facilities"]
    assert len(facilities_items) > 0

    # Should have security for institutional
    security_items = [item for item in gc.items if item.category == "security"]
    assert len(security_items) > 0


def test_estimate_general_conditions_regional_multiplier(sample_bid_proposal: BidProposal):
    """Test that regional multipliers are applied."""
    gc_nyc = estimate_general_conditions(
        project_id="test_project",
        building_type="row_house",
        bid_proposal=sample_bid_proposal,
        region_resolution={"region_id": "NYC", "confidence": 0.9, "evidence": []},
    )

    gc_default = estimate_general_conditions(
        project_id="test_project",
        building_type="row_house",
        bid_proposal=sample_bid_proposal,
        region_resolution={"region_id": "US_DEFAULT", "confidence": 0.8, "evidence": []},
    )

    # NYC should be more expensive than default
    assert gc_nyc.total_cost > gc_default.total_cost


def test_estimate_general_conditions_permits(sample_bid_proposal: BidProposal):
    """Test that permits are included."""
    gc = estimate_general_conditions(
        project_id="test_project",
        building_type="row_house",
        bid_proposal=sample_bid_proposal,
        region_resolution={"region_id": "NYC", "confidence": 0.9, "evidence": []},
    )

    permit_items = [item for item in gc.items if item.category == "permits"]
    assert len(permit_items) > 0
    assert permit_items[0].total_cost > 0


def test_estimate_general_conditions_inspections(sample_bid_proposal: BidProposal):
    """Test that inspections are included for masonry work."""
    gc = estimate_general_conditions(
        project_id="test_project",
        building_type="row_house",
        bid_proposal=sample_bid_proposal,
        region_resolution={"region_id": "US_DEFAULT", "confidence": 0.8, "evidence": []},
    )

    # Should have inspections due to masonry work
    inspection_items = [item for item in gc.items if item.category == "inspections"]
    assert len(inspection_items) > 0





