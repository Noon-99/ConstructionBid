"""Tests for work package normalizer (Phase 9.9)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.core.config import Settings
from app.schemas.bid_proposal import BidLineItem, BidProposal, BidSummary
from app.schemas.contractor_bid import ContractorBid, ContractorBidLineItem, ContractorBidSection
from app.services.work_package_normalizer import (
    generate_work_packages,
    normalize_work_packages,
)


@pytest.fixture
def settings():
    """Test settings."""
    return Settings()


def test_normalize_work_packages_contractor_bid_items():
    """Test normalizing contractor bid items into work packages."""
    items = [
        ContractorBidLineItem(
            item_id="item-1",
            title="Parapet rebuild",
            division="04",
            quantity=50.0,
            unit="LF",
            unit_cost=150.0,
            total_cost=7500.0,
            basis="From drawings",
            notes=None,
        ),
        ContractorBidLineItem(
            item_id="item-2",
            title="Brick repointing",
            division="04",
            quantity=500.0,
            unit="SF",
            unit_cost=8.0,
            total_cost=4000.0,
            basis="From drawings",
            notes=None,
        ),
        ContractorBidLineItem(
            item_id="item-3",
            title="Steel lintel replacement",
            division="04",
            quantity=5.0,
            unit="EA",
            unit_cost=800.0,
            total_cost=4000.0,
            basis="From drawings",
            notes=None,
        ),
        ContractorBidLineItem(
            item_id="item-4",
            title="Scaffolding",
            division=None,
            quantity=4.0,
            unit="week",
            unit_cost=1200.0,
            total_cost=4800.0,
            basis="Contractor profile",
            notes=None,
        ),
    ]

    packages = normalize_work_packages(items)

    assert len(packages) > 0

    # Check that parapet package exists
    parapet_pkg = next((p for p in packages if "Parapet" in p.title), None)
    assert parapet_pkg is not None
    assert "item-1" in parapet_pkg.line_item_ids
    assert parapet_pkg.subtotal == 7500.0
    assert len(parapet_pkg.keywords_matched) > 0

    # Check that repointing package exists
    repointing_pkg = next((p for p in packages if "Repointing" in p.title), None)
    assert repointing_pkg is not None
    assert "item-2" in repointing_pkg.line_item_ids
    assert repointing_pkg.subtotal == 4000.0

    # Check that lintels package exists
    lintels_pkg = next((p for p in packages if "Lintels" in p.title), None)
    assert lintels_pkg is not None
    assert "item-3" in lintels_pkg.line_item_ids

    # Check that logistics package exists
    logistics_pkg = next((p for p in packages if "Logistics" in p.title), None)
    assert logistics_pkg is not None
    assert "item-4" in logistics_pkg.line_item_ids

    # Verify total cost matches
    total_cost = sum(p.subtotal for p in packages)
    expected_total = sum(item.total_cost for item in items)
    assert abs(total_cost - expected_total) < 0.01


def test_normalize_work_packages_bid_proposal_items():
    """Test normalizing bid proposal items into work packages."""
    items = [
        BidLineItem(
            division="04 Masonry",
            description="Parapet reconstruction",
            quantity=50.0,
            unit="LF",
            unit_cost=150.0,
            total_cost=7500.0,
            basis="From drawings",
            confidence=0.9,
        ),
        BidLineItem(
            division="04 Masonry",
            description="Mortar joint repointing",
            quantity=500.0,
            unit="SF",
            unit_cost=8.0,
            total_cost=4000.0,
            basis="From drawings",
            confidence=0.9,
        ),
        BidLineItem(
            division="04 Masonry",
            description="Flashing replacement",
            quantity=100.0,
            unit="LF",
            unit_cost=25.0,
            total_cost=2500.0,
            basis="From drawings",
            confidence=0.9,
        ),
    ]

    packages = normalize_work_packages(items)

    assert len(packages) > 0

    # Verify total cost matches
    total_cost = sum(p.subtotal for p in packages)
    expected_total = sum(item.total_cost for item in items)
    assert abs(total_cost - expected_total) < 0.01


def test_normalize_work_packages_unassigned_items():
    """Test that unassigned items go into 'Other Work' package."""
    items = [
        ContractorBidLineItem(
            item_id="item-1",
            title="Custom work item",
            division="99",
            quantity=1.0,
            unit="LS",
            unit_cost=1000.0,
            total_cost=1000.0,
            basis="Unknown",
            notes=None,
        ),
    ]

    packages = normalize_work_packages(items)

    # Should have at least one package (Other Work)
    assert len(packages) > 0

    other_pkg = next((p for p in packages if p.package_id == "pkg_other"), None)
    assert other_pkg is not None
    assert other_pkg.title == "Other Work"
    assert "item-1" in other_pkg.line_item_ids
    assert other_pkg.subtotal == 1000.0
    assert other_pkg.confidence == 0.3  # Lower confidence for unassigned


def test_generate_work_packages_from_contractor_bid(settings):
    """Test generating work packages from contractor_bid.json."""
    sample_bid = ContractorBid(
        project_id="test-project",
        bid_mode="contractor",
        total_bid=25000.0,
        subtotals={"base_scope": 20000.0, "logistics": 5000.0},
        sections=[
            ContractorBidSection(
                section_id="base_scope",
                title="Base Scope",
                division=None,
                line_items=[
                    ContractorBidLineItem(
                        item_id="item-1",
                        title="Parapet rebuild",
                        division="04",
                        quantity=50.0,
                        unit="LF",
                        unit_cost=150.0,
                        total_cost=7500.0,
                        basis="From drawings",
                        notes=None,
                    ),
                ],
                subtotal=7500.0,
            ),
        ],
        permits_and_inspections=[],
        logistics=[
            ContractorBidLineItem(
                item_id="log-1",
                title="Scaffolding",
                division=None,
                quantity=4.0,
                unit="week",
                unit_cost=1200.0,
                total_cost=4800.0,
                basis="Contractor profile",
                notes=None,
            ),
        ],
        exclusions=[],
        assumptions=[],
        payment_schedule=None,
        schedule=None,
    )

    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Save contractor_bid.json
        contractor_bid_file = output_dir / "contractor_bid.json"
        with open(contractor_bid_file, "w") as f:
            f.write(sample_bid.model_dump_json(indent=2))

        # Generate work packages
        work_packages_file = generate_work_packages(
            project_id="test-project",
            output_dir=output_dir,
            settings=settings,
        )

        assert work_packages_file.exists()

        # Load and verify
        with open(work_packages_file, "r") as f:
            packages_data = json.load(f)

        assert isinstance(packages_data, list)
        assert len(packages_data) > 0

        # Verify packages contain expected items
        all_item_ids = [item_id for pkg in packages_data for item_id in pkg["line_item_ids"]]
        assert "item-1" in all_item_ids
        assert "log-1" in all_item_ids


def test_generate_work_packages_from_bid_proposal(settings):
    """Test generating work packages from bid_proposal.json (fallback)."""
    sample_proposal = BidProposal(
        project_id="test-project",
        summary=BidSummary(
            total_cost=15000.0,
            cost_by_division={"04 Masonry": 15000.0},
        ),
        line_items=[
            BidLineItem(
                division="04 Masonry",
                description="Parapet reconstruction",
                quantity=50.0,
                unit="LF",
                unit_cost=150.0,
                total_cost=7500.0,
                basis="From drawings",
                confidence=0.9,
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
            ),
        ],
        allowances=[],
        clarifications=[],
        generated_at="2025-01-01T00:00:00Z",
        estimate_mode="conceptual",
        bid_ready=False,
    )

    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Save bid_proposal.json (no contractor_bid.json)
        bid_file = output_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            f.write(sample_proposal.model_dump_json(indent=2))

        # Generate work packages
        work_packages_file = generate_work_packages(
            project_id="test-project",
            output_dir=output_dir,
            settings=settings,
        )

        assert work_packages_file.exists()

        # Load and verify
        with open(work_packages_file, "r") as f:
            packages_data = json.load(f)

        assert isinstance(packages_data, list)
        assert len(packages_data) > 0


def test_generate_work_packages_missing_files(settings):
    """Test that generating work packages raises FileNotFoundError when no bid files exist."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        with pytest.raises(FileNotFoundError):
            generate_work_packages(
                project_id="test-project",
                output_dir=output_dir,
                settings=settings,
            )






