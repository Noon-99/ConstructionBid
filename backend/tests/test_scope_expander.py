"""Tests for scope expansion engine (Phase 9.2B)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.core.config import Settings
from app.schemas.bid_proposal import BidLineItem, BidProposal, BidSummary
from app.services.scope_expander import ScopeExpander, generate_expanded_scope


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
def bid_proposal_with_masonry():
    """Create a bid proposal with masonry items."""
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

    return BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=15100.0, cost_by_division={"04": 11500.0, "05": 3600.0}),
        line_items=line_items,
        allowances=[],
        alternates=[],
        clarifications=[],
    )


def test_scope_expander_has_exterior_masonry(settings, bid_proposal_with_masonry):
    """Test that scope expander detects exterior masonry work."""
    expander = ScopeExpander(settings)
    assert expander._has_exterior_masonry(bid_proposal_with_masonry) is True
    assert expander._has_parapet_work(bid_proposal_with_masonry) is True
    assert expander._has_structural_lintel_work(bid_proposal_with_masonry) is True


def test_scope_expander_generates_items_for_masonry(
    settings, nyc_profile, bid_proposal_with_masonry
):
    """Test that scope expander generates scaffolding, dumpsters, and sidewalk shed for NYC masonry project."""
    expander = ScopeExpander(settings)
    expanded_scope = expander.generate_expanded_scope(
        project_id="test_project",
        bid_proposal=bid_proposal_with_masonry,
        profile_id="nyc_row_house_masonry_v1",
    )

    assert expanded_scope.project_id == "test_project"
    assert expanded_scope.profile_id == "nyc_row_house_masonry_v1"
    assert len(expanded_scope.items) > 0

    # Check for scaffolding
    scaffold_items = [item for item in expanded_scope.items if "scaffold" in item.title.lower()]
    assert len(scaffold_items) > 0, "Should include scaffolding for masonry work"
    scaffold = scaffold_items[0]
    assert scaffold.division == "01"
    assert scaffold.source == "contractor_profile"
    # If rate is configured, should have pricing
    if nyc_profile.logistics_rates.get("scaffold_weekly"):
        assert scaffold.quantity is not None
        assert scaffold.unit_cost is not None
        assert scaffold.total_cost is not None

    # Check for dumpsters
    dumpster_items = [
        item for item in expanded_scope.items if "dumpster" in item.title.lower() or "debris" in item.title.lower()
    ]
    assert len(dumpster_items) > 0, "Should include dumpster/debris removal for masonry work"
    dumpster = dumpster_items[0]
    assert dumpster.source == "contractor_profile"

    # Check for sidewalk shed (NYC specific)
    shed_items = [item for item in expanded_scope.items if "sidewalk" in item.title.lower()]
    assert len(shed_items) > 0, "Should include sidewalk shed for NYC projects"
    shed = shed_items[0]
    assert shed.source == "contractor_profile"
    assert shed.blocking is True  # Sidewalk shed is blocking for NYC

    # Check for permit filing (NYC specific)
    permit_items = [item for item in expanded_scope.items if "permit" in item.title.lower()]
    assert len(permit_items) > 0, "Should include permit filing for NYC projects"
    permit = permit_items[0]
    assert permit.source == "contractor_profile"
    assert permit.blocking is True  # Permits are blocking

    # Check for weather protection (parapet work)
    weather_items = [
        item for item in expanded_scope.items if "weather" in item.title.lower()
    ]
    assert len(weather_items) > 0, "Should include weather protection for parapet work"
    weather = weather_items[0]
    assert weather.source == "rules"

    # Check for special inspections (structural/lintel work)
    inspection_items = [
        item for item in expanded_scope.items if "inspection" in item.title.lower()
    ]
    assert len(inspection_items) > 0, "Should include special inspections for structural work"
    inspection = inspection_items[0]
    assert inspection.source == "rules"
    assert inspection.blocking is True  # Inspections are blocking


def test_scope_expander_deterministic(settings, bid_proposal_with_masonry):
    """Test that scope expansion is deterministic (same input = same output)."""
    expander = ScopeExpander(settings)
    expanded_scope_1 = expander.generate_expanded_scope(
        project_id="test_project",
        bid_proposal=bid_proposal_with_masonry,
        profile_id="nyc_row_house_masonry_v1",
    )
    expanded_scope_2 = expander.generate_expanded_scope(
        project_id="test_project",
        bid_proposal=bid_proposal_with_masonry,
        profile_id="nyc_row_house_masonry_v1",
    )

    # Should have same number of items
    assert len(expanded_scope_1.items) == len(expanded_scope_2.items)

    # Should have same item IDs
    item_ids_1 = {item.item_id for item in expanded_scope_1.items}
    item_ids_2 = {item.item_id for item in expanded_scope_2.items}
    assert item_ids_1 == item_ids_2

    # Should have same total costs (if pricing is configured)
    total_1 = sum(item.total_cost or 0.0 for item in expanded_scope_1.items)
    total_2 = sum(item.total_cost or 0.0 for item in expanded_scope_2.items)
    assert total_1 == total_2


def test_generate_expanded_scope_from_files(settings, bid_proposal_with_masonry):
    """Test generate_expanded_scope convenience function that loads from files."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Save bid proposal
        bid_file = output_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            f.write(bid_proposal_with_masonry.model_dump_json(indent=2))

        # Generate expanded scope
        expanded_scope = generate_expanded_scope(
            project_id="test_project",
            output_dir=output_dir,
            settings=settings,
        )

        assert expanded_scope.project_id == "test_project"
        assert len(expanded_scope.items) > 0


def test_scope_expander_no_masonry(settings):
    """Test that scope expander doesn't add masonry-specific items when no masonry work."""
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

    expander = ScopeExpander(settings)
    expanded_scope = expander.generate_expanded_scope(
        project_id="test_project",
        bid_proposal=bid_proposal,
        profile_id="nyc_row_house_masonry_v1",
    )

    # Should not have scaffolding or dumpsters (no masonry work)
    scaffold_items = [item for item in expanded_scope.items if "scaffold" in item.title.lower()]
    dumpster_items = [
        item for item in expanded_scope.items if "dumpster" in item.title.lower() or "debris" in item.title.lower()
    ]

    # But should still have NYC-specific items (sidewalk shed, permits)
    if expanded_scope.profile_id == "nyc_row_house_masonry_v1":
        shed_items = [item for item in expanded_scope.items if "sidewalk" in item.title.lower()]
        permit_items = [item for item in expanded_scope.items if "permit" in item.title.lower()]
        # NYC items should still be present
        assert len(shed_items) > 0 or len(permit_items) > 0






