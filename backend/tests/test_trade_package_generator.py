"""Tests for trade package generator (Phase 11.0)."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal, BidLineItem
from app.schemas.proposal_sections import (
    ProposalSections,
    ScopeSection,
    LogisticsSection,
    PermitsInspectionsSection,
    ExecutiveSummary,
)
from app.schemas.evidence_index import EvidenceIndex, BidItemEvidence, EvidenceReference
from app.services.trade_package_generator import (
    generate_trade_packages,
    _map_line_items_to_trades,
    _generate_trade_package,
)


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings()


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create temporary output directory."""
    return tmp_path


@pytest.fixture
def sample_bid_proposal() -> BidProposal:
    """Create sample bid proposal."""
    return BidProposal(
        project_id="test_project",
        generated_at=datetime.now(),
        estimate_mode="conceptual",
        bid_ready=True,
        summary={
            "total_cost": 150000.0,
            "cost_by_division": {
                "04 Masonry": 100000.0,
                "05 Metals": 30000.0,
                "07 Thermal": 20000.0,
            },
        },
        line_items=[
            BidLineItem(
                division="04 Masonry",
                description="Parapet repair and rebuild",
                quantity=100.0,
                unit="SF",
                unit_cost=50.0,
                total_cost=5000.0,
                basis="Drawing A-1",
                confidence=0.9,
            ),
            BidLineItem(
                division="04 Masonry",
                description="Brick repointing",
                quantity=500.0,
                unit="SF",
                unit_cost=15.0,
                total_cost=7500.0,
                basis="Drawing A-2",
                confidence=0.85,
            ),
            BidLineItem(
                division="05 Metals",
                description="Steel lintel replacement",
                quantity=10.0,
                unit="EA",
                unit_cost=3000.0,
                total_cost=30000.0,
                basis="Detail S-011",
                confidence=0.9,
            ),
            BidLineItem(
                division="07 Thermal",
                description="Thru-wall flashing installation",
                quantity=200.0,
                unit="LF",
                unit_cost=100.0,
                total_cost=20000.0,
                basis="Detail S-102",
                confidence=0.85,
            ),
            BidLineItem(
                division="01 General Requirements",
                description="Scaffold rental - 4 weeks",
                quantity=4.0,
                unit="WK",
                unit_cost=2500.0,
                total_cost=10000.0,
                basis="Site logistics",
                confidence=0.8,
            ),
        ],
        allowances=[],
        clarifications=[],
    )


@pytest.fixture
def sample_evidence_index() -> EvidenceIndex:
    """Create sample evidence index."""
    return EvidenceIndex(
        project_id="test_project",
        generated_at=datetime.now().isoformat(),
        bid_item_evidence=[
            BidItemEvidence(
                line_item_index=0,
                division="04 Masonry",
                description="Parapet repair and rebuild",
                evidence_references=[
                    EvidenceReference(
                        page_number=1,
                        evidence_snippet="Parapet repair noted on elevation A-1",
                        sheet_id="A-1",
                    )
                ],
                quantity_source="from_drawing",
                basis="Drawing A-1",
            ),
            BidItemEvidence(
                line_item_index=2,
                division="05 Metals",
                description="Steel lintel replacement",
                evidence_references=[
                    EvidenceReference(
                        page_number=5,
                        evidence_snippet="Lintel schedule detail S-011",
                        sheet_id="S-011",
                    )
                ],
                quantity_source="from_schedule",
                basis="Detail S-011",
            ),
        ],
        zone_evidence=[],
    )


def test_map_line_items_to_trades_basic(sample_bid_proposal: BidProposal):
    """Test basic trade mapping."""
    mapping = _map_line_items_to_trades(sample_bid_proposal, None)

    # Check masonry trade
    assert "masonry" in mapping
    assert len(mapping["masonry"]) == 2  # Parapet and repointing
    assert 0 in mapping["masonry"]  # Parapet
    assert 1 in mapping["masonry"]  # Repointing

    # Check metals trade
    assert "metals" in mapping
    assert len(mapping["metals"]) == 1
    assert 2 in mapping["metals"]  # Lintel

    # Check waterproofing trade
    assert "waterproofing" in mapping
    assert len(mapping["waterproofing"]) == 1
    assert 3 in mapping["waterproofing"]  # Flashing

    # Check general conditions
    assert "general_conditions" in mapping
    assert len(mapping["general_conditions"]) == 1
    assert 4 in mapping["general_conditions"]  # Scaffold


def test_map_line_items_to_trades_with_proposal_sections(
    sample_bid_proposal: BidProposal,
):
    """Test trade mapping with proposal sections."""
    proposal_sections = ProposalSections(
        project_id="test_project",
        generated_at=datetime.now(),
        executive_summary=ExecutiveSummary(
            project_overview="Test project",
            total_bid_amount=150000.0,
            scope_summary="Test scope",
            key_highlights=[],
        ),
        scope_sections=[
            ScopeSection(
                section_key="parapet",
                title="Parapet Repair",
                narrative="Parapet repair work",
                line_item_ids=["0"],
                evidence_refs=[],
                detail_refs=[],
                flags=[],
            ),
            ScopeSection(
                section_key="lintels",
                title="Lintel Replacement",
                narrative="Lintel replacement work",
                line_item_ids=["2"],
                evidence_refs=[],
                detail_refs=[],
                flags=[],
            ),
        ],
        logistics_section=LogisticsSection(
            title="Logistics",
            narrative="Site logistics",
            line_item_ids=["4"],
            evidence_refs=[],
        ),
        permits_inspections_section=PermitsInspectionsSection(
            title="Permits",
            narrative="Permits work",
            line_item_ids=[],
            evidence_refs=[],
        ),
        exclusions=[],
        assumptions=[],
        payment_schedule={},
        schedule={"start_conditions": [], "critical_path_items": []},
        notes=[],
    )

    mapping = _map_line_items_to_trades(sample_bid_proposal, proposal_sections)

    # Verify mapping uses proposal sections
    assert 0 in mapping["masonry"]  # From section_key="parapet"
    assert 2 in mapping["metals"]  # From section_key="lintels"
    assert 4 in mapping["general_conditions"]  # From logistics_section


def test_generate_trade_package_masonry(
    sample_bid_proposal: BidProposal,
    sample_evidence_index: EvidenceIndex,
):
    """Test generating masonry trade package."""
    package = _generate_trade_package(
        trade_id="masonry",
        line_item_indices=[0, 1],
        bid_proposal=sample_bid_proposal,
        proposal_sections=None,
        evidence_index=sample_evidence_index,
        detail_graph=None,
    )

    assert package.trade_id == "masonry"
    assert package.trade_name == "Masonry"
    assert len(package.line_items) == 2
    assert package.total_cost == 12500.0  # 5000 + 7500
    assert "04 Masonry" in package.divisions

    # Check evidence references
    assert len(package.evidence_refs) > 0

    # Check inclusions/exclusions
    assert len(package.inclusions) > 0
    assert len(package.exclusions) > 0
    assert len(package.assumptions) > 0


def test_generate_trade_packages_end_to_end(
    sample_bid_proposal: BidProposal,
    sample_evidence_index: EvidenceIndex,
    output_dir: Path,
    settings: Settings,
):
    """Test end-to-end trade package generation."""
    # Save artifacts
    (output_dir / "bid_proposal.json").write_text(sample_bid_proposal.model_dump_json(indent=2))
    (output_dir / "evidence_index.json").write_text(sample_evidence_index.model_dump_json(indent=2))

    # Generate packages
    export = generate_trade_packages(
        project_id="test_project",
        output_dir=output_dir,
        settings=settings,
        bid_proposal=sample_bid_proposal,
        proposal_sections=None,
        evidence_index=sample_evidence_index,
        detail_graph=None,
        pricing_profile=None,
    )

    assert export.project_id == "test_project"
    assert len(export.packages) > 0

    # Check that all line items are assigned
    all_indices = set()
    for pkg in export.packages:
        for item in pkg.line_items:
            all_indices.add(item.line_item_index)

    # Should have masonry, metals, waterproofing, general_conditions
    assert len(all_indices) == 5  # All 5 line items should be assigned

    # Check no duplication
    trade_indices: dict[str, set[int]] = {}
    for pkg in export.packages:
        trade_indices[pkg.trade_id] = {item.line_item_index for item in pkg.line_items}

    # Verify no overlap between trades (except "other" which shouldn't exist here)
    for trade1, indices1 in trade_indices.items():
        for trade2, indices2 in trade_indices.items():
            if trade1 != trade2 and trade1 != "other" and trade2 != "other":
                assert indices1.isdisjoint(indices2), f"Trades {trade1} and {trade2} overlap"

    # Check totals match (sum of all line items)
    expected_total = sum(item.total_cost for item in sample_bid_proposal.line_items)
    total_from_packages = sum(pkg.total_cost for pkg in export.packages)
    # Allow for packages that might include allowances or other items
    # In this case, all line items should be assigned to packages
    assert abs(total_from_packages - expected_total) < 0.01, f"Package total {total_from_packages} != expected {expected_total}"


def test_generate_trade_packages_deterministic_ordering(
    sample_bid_proposal: BidProposal,
    output_dir: Path,
    settings: Settings,
):
    """Test that packages are sorted by total cost (descending)."""
    export = generate_trade_packages(
        project_id="test_project",
        output_dir=output_dir,
        settings=settings,
        bid_proposal=sample_bid_proposal,
        proposal_sections=None,
        evidence_index=None,
        detail_graph=None,
        pricing_profile=None,
    )

    # Check sorting (descending by total_cost)
    costs = [pkg.total_cost for pkg in export.packages]
    assert costs == sorted(costs, reverse=True)


def test_trade_package_no_duplication(sample_bid_proposal: BidProposal):
    """Test that no line item appears in multiple trades."""
    mapping = _map_line_items_to_trades(sample_bid_proposal, None)

    # Collect all indices
    all_indices = []
    for trade_id, indices in mapping.items():
        all_indices.extend(indices)

    # Check for duplicates
    assert len(all_indices) == len(set(all_indices)), "Line items duplicated across trades"

