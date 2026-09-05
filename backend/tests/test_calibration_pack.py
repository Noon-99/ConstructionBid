"""Unit tests for calibration pack generator (Phase 10.3)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.services.calibration_pack_generator import generate_calibration_pack
from app.schemas.bid_proposal import BidProposal, BidSummary, BidLineItem
from app.schemas.contractor_profile import ContractorProfile, LaborRates, CrewProductivity


def test_generate_calibration_pack_basic() -> None:
    """Test: Basic calibration pack generation."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        # Create bid_proposal
        bid_proposal = BidProposal(
            project_id="test-project",
            summary=BidSummary(
                total_cost=10000.0,
                cost_by_division={"04 Masonry": 10000.0},
            ),
            line_items=[
                BidLineItem(
                    division="04 Masonry",
                    description="Brick repointing",
                    quantity=100.0,
                    unit="SF",
                    unit_cost=100.0,
                    total_cost=10000.0,
                    basis="From drawing",
                    confidence=0.9,
                    quantity_source="from_drawing",
                )
            ],
        )

        bid_file = output_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            f.write(bid_proposal.model_dump_json(indent=2))

        pack = generate_calibration_pack(
            project_id="test-project",
            output_dir=output_dir,
        )

        assert pack.project_id == "test-project"
        assert len(pack.top_line_items) == 1
        assert len(pack.flagged_line_items) == 0
        assert pack.top_line_items[0].total_cost == 10000.0


def test_generate_calibration_pack_flags_heuristic() -> None:
    """Test: Flags heuristic quantities."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        bid_proposal = BidProposal(
            project_id="test-project",
            summary=BidSummary(total_cost=5000.0, cost_by_division={}),
            line_items=[
                BidLineItem(
                    division="04 Masonry",
                    description="Item with heuristic quantity",
                    quantity=50.0,
                    unit="SF",
                    unit_cost=100.0,
                    total_cost=5000.0,
                    basis="Estimated",
                    confidence=0.6,
                    quantity_source="heuristic",
                )
            ],
        )

        bid_file = output_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            f.write(bid_proposal.model_dump_json(indent=2))

        pack = generate_calibration_pack(
            project_id="test-project",
            output_dir=output_dir,
        )

        assert len(pack.flagged_line_items) == 1
        assert "heuristic_quantity" in pack.flagged_line_items[0].flags


def test_generate_calibration_pack_top_10() -> None:
    """Test: Returns top 10 items by cost."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        # Create 15 items
        line_items = [
            BidLineItem(
                division="04 Masonry",
                description=f"Item {i}",
                quantity=10.0,
                unit="SF",
                unit_cost=float(i * 100),
                total_cost=float(i * 1000),
                basis="Test",
                confidence=0.9,
            )
            for i in range(1, 16)
        ]

        bid_proposal = BidProposal(
            project_id="test-project",
            summary=BidSummary(total_cost=sum(item.total_cost for item in line_items), cost_by_division={}),
            line_items=line_items,
        )

        bid_file = output_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            f.write(bid_proposal.model_dump_json(indent=2))

        pack = generate_calibration_pack(
            project_id="test-project",
            output_dir=output_dir,
        )

        assert len(pack.top_line_items) == 10
        # Should be sorted descending by cost
        assert pack.top_line_items[0].total_cost == 15000.0
        assert pack.top_line_items[-1].total_cost == 6000.0


def test_generate_calibration_pack_with_pricing_v2() -> None:
    """Test: Includes component splits from pricing_v2 if available."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        bid_proposal = BidProposal(
            project_id="test-project",
            summary=BidSummary(total_cost=1000.0, cost_by_division={}),
            line_items=[
                BidLineItem(
                    division="04 Masonry",
                    description="Test item",
                    quantity=100.0,
                    unit="SF",
                    unit_cost=10.0,
                    total_cost=1000.0,
                    basis="Test",
                    confidence=0.9,
                )
            ],
        )

        bid_file = output_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            f.write(bid_proposal.model_dump_json(indent=2))

        # Create pricing_v2
        from app.schemas.bid_pricing_v2 import BidPricingV2, LineItemPricingV2, PricingComponent

        pricing_v2 = BidPricingV2(
            project_id="test-project",
            line_items=[
                LineItemPricingV2(
                    line_item_id="0",
                    title="Test item",
                    quantity=100.0,
                    unit="SF",
                    components=[
                        PricingComponent(type="material", amount=350.0, basis="Material cost"),
                        PricingComponent(type="labor", amount=550.0, basis="Labor cost"),
                    ],
                    total=1000.0,
                    confidence=0.85,
                )
            ],
            grand_total=1000.0,
        )

        pricing_file = output_dir / "bid_pricing_v2.json"
        with open(pricing_file, "w") as f:
            f.write(pricing_v2.model_dump_json(indent=2))

        pack = generate_calibration_pack(
            project_id="test-project",
            output_dir=output_dir,
        )

        assert len(pack.top_line_items) == 1
        assert pack.top_line_items[0].component_splits is not None
        assert pack.top_line_items[0].component_splits["material"] == 350.0
        assert pack.top_line_items[0].component_splits["labor"] == 550.0






