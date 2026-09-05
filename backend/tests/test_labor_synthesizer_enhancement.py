"""Unit tests for labor breakdown enhancement with trade assemblies (Phase 11.1)."""

import pytest

from app.schemas.bid_proposal import BidLineItem, BidProposal, BidSummary
from app.schemas.trade_assemblies import (
    LaborComponent,
    TradeAssembly,
    TradeAssembliesResult,
    TradeComponent,
)
from app.schemas.contractor_profile import ContractorProfile
from app.core.config import Settings
from app.services.labor_synthesizer import LaborSynthesizer


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
    ]

    return BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=4887.50, cost_by_division={"04 Masonry": 4887.50}),
        line_items=line_items,
        allowances=[],
        clarifications=[],
        generated_at="2025-01-01T00:00:00",
        estimate_mode="conceptual",
        bid_ready=True,
    )


@pytest.fixture
def sample_trade_assemblies() -> TradeAssembliesResult:
    """Create sample trade assemblies with explicit labor hours."""
    labor_components = [
        LaborComponent(
            trade="mason",
            crew=["mason", "laborer"],
            hours=16.0,
            rate=65.00,
            total_cost=1040.00,
            basis="Q / 25.0 * 8.0 hours",
        ),
        LaborComponent(
            trade="foreman",
            crew=["foreman"],
            hours=4.0,
            rate=85.00,
            total_cost=340.00,
            basis="Supervision: 2 hours/day",
        ),
    ]

    components = [
        TradeComponent(
            name="Aluminum Coping",
            unit="LF",
            qty=52.5,
            unit_cost=45.00,
            total_cost=2362.50,
            cost_source="ruleset",
        ),
    ]

    assembly = TradeAssembly(
        id="parapet_repair_001",
        title="Parapet Repair and Rebuild",
        division="04 Masonry",
        unit="LF",
        quantity=50.0,
        related_bid_item_ids=["0"],
        components=components,
        labor=labor_components,
        equipment=[],
        assumptions=[],
        spec_refs=[],
        evidence_refs=[],
        ruleset_used="row_house_repair.yml",
    )

    return TradeAssembliesResult(
        project_id="test_project",
        assemblies=[assembly],
        version="1.0",
    )


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    from app.core.config import get_settings
    return get_settings()


def test_labor_breakdown_from_trade_assemblies(
    sample_bid_proposal: BidProposal,
    sample_trade_assemblies: TradeAssembliesResult,
    settings: Settings,
):
    """Test that labor breakdown uses explicit hours from trade assemblies."""
    synthesizer = LaborSynthesizer(settings)
    
    breakdown = synthesizer.generate_labor_breakdown(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        profile_id=settings.default_contractor_profile_id,  # Use default profile
        trade_assemblies=sample_trade_assemblies,
    )

    assert breakdown.project_id == "test_project"
    assert len(breakdown.activities) > 0

    # Should have activities based on trade assemblies
    # Should aggregate labor by trade (mason + foreman)
    assert any("mason" in act.title.lower() for act in breakdown.activities)
    
    # Total labor cost should match sum from assemblies
    expected_total = 1040.00 + 340.00  # mason + foreman
    if breakdown.total_labor_cost:
        assert abs(breakdown.total_labor_cost - expected_total) < 0.01

    # Activities should have explicit hours/days
    for activity in breakdown.activities:
        assert activity.estimated_days is not None or activity.labor_cost is not None
        assert activity.confidence >= 0.9  # High confidence when using explicit hours


def test_labor_breakdown_fallback_to_keyword_based(
    sample_bid_proposal: BidProposal,
    settings: Settings,
):
    """Test that labor breakdown falls back to keyword-based when trade assemblies unavailable."""
    synthesizer = LaborSynthesizer(settings)
    
    breakdown = synthesizer.generate_labor_breakdown(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        trade_assemblies=None,  # No trade assemblies
    )

    # Should still generate activities using keyword-based approach
    assert len(breakdown.activities) > 0
    # Confidence might be lower without explicit hours
    assert any(act.confidence <= 0.9 for act in breakdown.activities if act.labor_cost is not None)

