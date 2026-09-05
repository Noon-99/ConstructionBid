"""Unit tests for trade assembly generator (Phase 9.2)."""

from pathlib import Path

import pytest

from app.schemas.bid_proposal import BidLineItem, BidProposal, BidSummary
from app.schemas.evidence_index import BidItemEvidence, EvidenceIndex, EvidenceReference
from app.schemas.trade_assemblies import TradeAssembliesResult
from app.services.trade_assembly_generator import generate_trade_assemblies
from app.core.config import Settings


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
        BidLineItem(
            division="05 Metals",
            description="Lintel replacement",
            quantity=3.0,
            unit="EA",
            unit_cost=450.00,
            total_cost=1350.00,
            basis="From schedule",
            confidence=0.95,
        ),
    ]

    return BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=7937.50, cost_by_division={"04 Masonry": 6587.50, "05 Metals": 1350.00}),
        line_items=line_items,
        allowances=[],
        clarifications=[],
        generated_at="2025-01-01T00:00:00",
        estimate_mode="conceptual",
        bid_ready=True,
    )


@pytest.fixture
def sample_evidence_index() -> EvidenceIndex:
    """Create a sample evidence index for testing."""
    from datetime import datetime
    
    return EvidenceIndex(
        project_id="test_project",
        bid_item_evidence=[
            BidItemEvidence(
                line_item_index=0,
                division="04 Masonry",
                description="Parapet repair and rebuild",
                evidence_references=[
                    EvidenceReference(
                        page_number=2,
                        evidence_snippet="Parapet detail showing rebuild",
                        location_type="elevation_notes",
                    )
                ],
                basis="From elevation drawings",
            ),
            BidItemEvidence(
                line_item_index=1,
                division="04 Masonry",
                description="Brick repointing",
                evidence_references=[
                    EvidenceReference(
                        page_number=3,
                        evidence_snippet="Repointing specification",
                        location_type="notes",
                    )
                ],
                basis="From elevation notes",
            ),
        ],
        zone_evidence=[],
        detail_evidence=[],
        generated_at=datetime.now().isoformat(),
    )


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    from app.core.config import get_settings
    return get_settings()


def test_generate_trade_assemblies_parapet_repair(
    sample_bid_proposal: BidProposal, sample_evidence_index: EvidenceIndex, settings: Settings
):
    """Test generating trade assemblies for parapet repair."""
    result = generate_trade_assemblies(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        evidence_index=sample_evidence_index,
        ruleset="row_house_repair.yml",
        settings=settings,
    )

    assert isinstance(result, TradeAssembliesResult)
    assert result.project_id == "test_project"
    assert len(result.assemblies) > 0

    # Find parapet assembly
    parapet_assembly = None
    for assembly in result.assemblies:
        if "parapet" in assembly.id.lower():
            parapet_assembly = assembly
            break

    assert parapet_assembly is not None, "Parapet assembly should be generated"
    assert parapet_assembly.quantity == 50.0
    assert parapet_assembly.unit == "LF"
    assert len(parapet_assembly.components) > 0
    assert len(parapet_assembly.labor) > 0
    assert len(parapet_assembly.evidence_refs) > 0  # Should have evidence from line item 0

    # Check component quantities are calculated
    for component in parapet_assembly.components:
        assert component.qty > 0
        assert component.total_cost >= 0


def test_generate_trade_assemblies_brick_repointing(
    sample_bid_proposal: BidProposal, sample_evidence_index: EvidenceIndex, settings: Settings
):
    """Test generating trade assemblies for brick repointing."""
    result = generate_trade_assemblies(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        evidence_index=sample_evidence_index,
        ruleset="row_house_repair.yml",
        settings=settings,
    )

    # Find repointing assembly
    repointing_assembly = None
    for assembly in result.assemblies:
        if "repoint" in assembly.id.lower() or "repoint" in assembly.title.lower():
            repointing_assembly = assembly
            break

    assert repointing_assembly is not None, "Repointing assembly should be generated"
    assert repointing_assembly.quantity == 200.0
    assert repointing_assembly.unit == "SF"
    assert len(repointing_assembly.components) > 0

    # Check mortar bags quantity (should be Q * 0.15 = 200 * 0.15 = 30)
    mortar_component = None
    for component in repointing_assembly.components:
        if "mortar" in component.name.lower():
            mortar_component = component
            break

    if mortar_component:
        # Should be approximately 200 * 0.15 = 30 bags
        assert 25 <= mortar_component.qty <= 35, f"Expected ~30 bags, got {mortar_component.qty}"


def test_generate_trade_assemblies_no_evidence_index(
    sample_bid_proposal: BidProposal, settings: Settings
):
    """Test generating trade assemblies without evidence index."""
    result = generate_trade_assemblies(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        evidence_index=None,
        ruleset="row_house_repair.yml",
        settings=settings,
    )

    assert len(result.assemblies) > 0
    # Assemblies should still be generated, just without evidence
    for assembly in result.assemblies:
        # Evidence refs may be empty, but assembly should still exist
        assert assembly.quantity > 0


def test_generate_trade_assemblies_formula_evaluation(settings: Settings):
    """Test formula evaluation with various formulas."""
    from app.services.trade_assembly_generator import _evaluate_formula

    # Test simple multiplication
    assert _evaluate_formula("Q * 1.05", 100.0) == 105.0

    # Test with ceil
    assert _evaluate_formula("ceil(Q / 4.0)", 10.0) == 3.0  # ceil(2.5) = 3

    # Test with max
    assert _evaluate_formula("max(1.0, Q / 10.0)", 5.0) == 1.0  # max(1.0, 0.5) = 1.0
    assert _evaluate_formula("max(1.0, Q / 10.0)", 20.0) == 2.0  # max(1.0, 2.0) = 2.0

    # Test division
    assert abs(_evaluate_formula("Q / 25.0 * 8.0", 50.0) - 16.0) < 0.01


def test_generate_trade_assemblies_matching_logic(settings: Settings):
    """Test bid item to assembly matching logic."""
    from app.services.trade_assembly_generator import _match_bid_item_to_assembly

    # Load rules
    from app.services.trade_assembly_generator import _load_ruleset
    rules = _load_ruleset("row_house_repair.yml", settings)
    assemblies_rules = rules.get("assemblies", {})

    # Test parapet matching
    parapet_item = {
        "description": "Parapet repair and rebuild",
        "division": "04 Masonry",
        "unit": "LF",
    }
    assert _match_bid_item_to_assembly(
        parapet_item, "parapet_repair", assemblies_rules["parapet_repair"]
    )

    # Test repointing matching
    repoint_item = {
        "description": "Brick repointing work",
        "division": "04 Masonry",
        "unit": "SF",
    }
    assert _match_bid_item_to_assembly(
        repoint_item, "brick_repointing", assemblies_rules["brick_repointing"]
    )

    # Test non-matching
    other_item = {
        "description": "Window replacement",
        "division": "08 Openings",
        "unit": "EA",
    }
    assert not _match_bid_item_to_assembly(
        other_item, "parapet_repair", assemblies_rules["parapet_repair"]
    )

