"""Unit tests for pricing engine v2 (Phase 10.2)."""

import pytest

from app.services.pricing_engine_v2 import compute_pricing_v2
from app.schemas.bid_pricing_v2 import BidPricingV2, LineItemPricingV2
from app.schemas.bid_proposal import BidProposal, BidSummary, BidLineItem
from app.schemas.contractor_profile import ContractorProfile, LaborRates, CrewProductivity


def test_compute_pricing_v2_default_split() -> None:
    """Test: Default split applied when no profile provided."""
    bid_proposal = BidProposal(
        project_id="test-project",
        summary=BidSummary(
            total_cost=1000.0,
            cost_by_division={"04 Masonry": 1000.0},
        ),
        line_items=[
            BidLineItem(
                division="04 Masonry",
                description="Brick repointing",
                quantity=100.0,
                unit="SF",
                unit_cost=10.0,
                total_cost=1000.0,
                basis="From drawing",
                confidence=0.9,
            )
        ],
    )

    result = compute_pricing_v2(bid_proposal)

    assert result.project_id == "test-project"
    assert len(result.line_items) == 1
    assert result.grand_total == 1000.0

    line_item = result.line_items[0]
    assert line_item.total == 1000.0
    assert line_item.confidence == 0.60  # Default split confidence

    # Verify components sum to total
    component_total = sum(c.amount for c in line_item.components)
    assert abs(component_total - 1000.0) < 0.01

    # Verify default split percentages (approximately)
    assert any(c.type == "labor" for c in line_item.components)
    assert any(c.type == "material" for c in line_item.components)
    assert any(c.type == "equipment" for c in line_item.components)
    assert any(c.type == "overhead_profit" for c in line_item.components)

    # Verify totals_by_component
    assert result.totals_by_component["material"] > 0
    assert result.totals_by_component["labor"] > 0


def test_compute_pricing_v2_with_profile() -> None:
    """Test: Profile OHP rates applied, higher confidence."""
    bid_proposal = BidProposal(
        project_id="test-project",
        summary=BidSummary(
            total_cost=1000.0,
            cost_by_division={"04 Masonry": 1000.0},
        ),
        line_items=[
            BidLineItem(
                division="04 Masonry",
                description="Brick repointing",
                quantity=100.0,
                unit="SF",
                unit_cost=10.0,
                total_cost=1000.0,
                basis="From drawing",
                confidence=0.9,
            )
        ],
    )

    profile = ContractorProfile(
        profile_id="test-profile",
        region="NYC",
        project_type="row_house_masonry",
        labor_rates=LaborRates(),
        overhead_pct=18.0,
        profit_pct=12.0,
        contingency_pct=5.0,
        crew_productivity=CrewProductivity(),
    )

    result = compute_pricing_v2(bid_proposal, contractor_profile=profile)

    assert result.profile_id == "test-profile"
    assert len(result.line_items) == 1

    line_item = result.line_items[0]
    assert line_item.confidence == 0.85  # Profile-defined confidence

    # Verify OHP component includes profile rates
    ohp_component = next((c for c in line_item.components if c.type == "overhead_profit"), None)
    assert ohp_component is not None
    assert "18.0%" in ohp_component.basis or "18%" in ohp_component.basis
    assert "12.0%" in ohp_component.basis or "12%" in ohp_component.basis


def test_compute_pricing_v2_multiple_items() -> None:
    """Test: Multiple line items sum correctly."""
    bid_proposal = BidProposal(
        project_id="test-project",
        summary=BidSummary(
            total_cost=3000.0,
            cost_by_division={"04 Masonry": 2000.0, "03 Concrete": 1000.0},
        ),
        line_items=[
            BidLineItem(
                division="04 Masonry",
                description="Item 1",
                quantity=100.0,
                unit="SF",
                unit_cost=20.0,
                total_cost=2000.0,
                basis="Test",
                confidence=0.9,
            ),
            BidLineItem(
                division="03 Concrete",
                description="Item 2",
                quantity=50.0,
                unit="CY",
                unit_cost=20.0,
                total_cost=1000.0,
                basis="Test",
                confidence=0.9,
            ),
        ],
    )

    result = compute_pricing_v2(bid_proposal)

    assert len(result.line_items) == 2
    assert result.grand_total == 3000.0

    # Verify each item totals correctly
    for item in result.line_items:
        component_total = sum(c.amount for c in item.components)
        assert abs(component_total - item.total) < 0.01

    # Verify grand total matches sum of items
    item_total_sum = sum(item.total for item in result.line_items)
    assert abs(item_total_sum - result.grand_total) < 0.01


def test_compute_pricing_v2_totals_by_component() -> None:
    """Test: totals_by_component sums all line items correctly."""
    bid_proposal = BidProposal(
        project_id="test-project",
        summary=BidSummary(
            total_cost=2000.0,
            cost_by_division={"04 Masonry": 2000.0},
        ),
        line_items=[
            BidLineItem(
                division="04 Masonry",
                description="Item 1",
                quantity=100.0,
                unit="SF",
                unit_cost=10.0,
                total_cost=1000.0,
                basis="Test",
                confidence=0.9,
            ),
            BidLineItem(
                division="04 Masonry",
                description="Item 2",
                quantity=100.0,
                unit="SF",
                unit_cost=10.0,
                total_cost=1000.0,
                basis="Test",
                confidence=0.9,
            ),
        ],
    )

    result = compute_pricing_v2(bid_proposal)

    # Calculate expected totals from components
    expected_material = sum(
        sum(c.amount for c in item.components if c.type == "material")
        for item in result.line_items
    )
    expected_labor = sum(
        sum(c.amount for c in item.components if c.type == "labor")
        for item in result.line_items
    )

    assert abs(result.totals_by_component["material"] - expected_material) < 0.01
    assert abs(result.totals_by_component["labor"] - expected_labor) < 0.01

    # Verify totals_by_component sum matches grand_total (approximately)
    component_sum = sum(result.totals_by_component.values())
    assert abs(component_sum - result.grand_total) < 0.01

