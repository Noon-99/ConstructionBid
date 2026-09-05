"""Tests for quantity provenance tracking (Phase 4.7)."""

import pytest

from app.schemas.bid_proposal import BidProposal
from app.schemas.costing import CostBreakdown, CostEngineResult, CostItem, QuantitySource
from app.schemas.extraction_result import ExtractionResult
from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext
from app.schemas.validation_report import ValidationReport
from app.services.bid_proposal_generator import generate_bid_proposal


def test_heuristic_quantity_triggers_critical_clarification() -> None:
    """Test that heuristic quantities trigger critical clarification in bid_ready mode."""
    cost_items = [
        CostItem(
            item_name="Test Item with Heuristic",
            scope_item="Test Item",
            quantity=100.0,
            unit="SF",
            unit_cost=10.0,
            material_cost=500.0,
            labor_cost=500.0,
            equipment_cost=0.0,
            waste_factor=0.0,
            multipliers={},
            subtotal=1000.0,
            rule_matched="test_rule",
            evidence="Test evidence",
            notes=[],
            quantity_source="heuristic",
            quantity_confidence=0.3,
            quantity_evidence={"evidence_snippet": "Heuristic estimate"},
        ),
    ]

    breakdown_by_category = [
        CostBreakdown(category="General", items=cost_items, subtotal=1000.0),
    ]

    costing = CostEngineResult(
        project_id="test-project",
        breakdown_by_category=breakdown_by_category,
        breakdown_by_scope_item=cost_items,
        breakdown_by_building={},
        subtotals={"General": 1000.0},
        total_cost=1000.0,
        material_cost_total=500.0,
        labor_cost_total=500.0,
        equipment_cost_total=0.0,
        waste_cost_total=0.0,
        cost_justification=[],
        missing_data_warnings=[],
        rules_used=["test_rule"],
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="institutional",
                context="test",
                evidence="test",
            )
        ),
    )

    validation = ValidationReport(
        project_id="test-project",
        passed=True,
        score=1.0,
        issues=[],
        missing_critical_items=[],
        conflicts={},
        rerun_performed=False,
        rerun_notes=[],
    )

    # Test bid_ready mode
    proposal = generate_bid_proposal(
        project_id="test-project",
        extraction=extraction,
        costing=costing,
        validation=validation,
        estimate_mode="bid_ready",
    )

    assert proposal.estimate_mode == "bid_ready"
    assert proposal.bid_ready is False  # Should be False due to heuristic quantity
    
    # Check for critical clarification
    critical_clarifications = [
        c for c in proposal.clarifications if c.severity == "critical"
    ]
    assert len(critical_clarifications) >= 1
    assert "heuristic" in critical_clarifications[0].text.lower() or "unknown" in critical_clarifications[0].text.lower()

    # Test conceptual mode (should allow heuristics)
    proposal_conceptual = generate_bid_proposal(
        project_id="test-project",
        extraction=extraction,
        costing=costing,
        validation=validation,
        estimate_mode="conceptual",
    )

    assert proposal_conceptual.estimate_mode == "conceptual"
    assert proposal_conceptual.bid_ready is True  # Conceptual mode allows heuristics


def test_computed_from_dimensions_passes() -> None:
    """Test that computed_from_dimensions quantities pass bid_ready check."""
    cost_items = [
        CostItem(
            item_name="Slab on Grade",
            scope_item="Slab",
            quantity=8500.0,
            unit="SF",
            unit_cost=6.50,
            material_cost=21250.0,
            labor_cost=37400.0,
            equipment_cost=4250.0,
            waste_factor=0.10,
            multipliers={},
            subtotal=55250.0,
            rule_matched="slab_on_grade",
            evidence="From plans",
            notes=[],
            quantity_source="computed_from_dimensions",
            quantity_confidence=0.85,
            quantity_evidence={
                "page_number": 2,
                "computation_formula": "footprint_area_sf",
                "evidence_snippet": "Computed from authoritative dimensions",
            },
        ),
    ]

    breakdown_by_category = [
        CostBreakdown(category="Concrete", items=cost_items, subtotal=55250.0),
    ]

    costing = CostEngineResult(
        project_id="test-project",
        breakdown_by_category=breakdown_by_category,
        breakdown_by_scope_item=cost_items,
        breakdown_by_building={},
        subtotals={"Concrete": 55250.0},
        total_cost=55250.0,
        material_cost_total=21250.0,
        labor_cost_total=37400.0,
        equipment_cost_total=4250.0,
        waste_cost_total=0.0,
        cost_justification=[],
        missing_data_warnings=[],
        rules_used=["slab_on_grade"],
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="institutional",
                context="test",
                evidence="test",
            )
        ),
    )

    validation = ValidationReport(
        project_id="test-project",
        passed=True,
        score=1.0,
        issues=[],
        missing_critical_items=[],
        conflicts={},
        rerun_performed=False,
        rerun_notes=[],
    )

    proposal = generate_bid_proposal(
        project_id="test-project",
        extraction=extraction,
        costing=costing,
        validation=validation,
        estimate_mode="bid_ready",
    )

    assert proposal.bid_ready is True  # Should pass with computed_from_dimensions
    assert proposal.line_items[0].quantity_source == "computed_from_dimensions"
    assert proposal.line_items[0].quantity_confidence == 0.85


def test_allowance_passes() -> None:
    """Test that allowance items pass bid_ready check."""
    cost_items = [
        CostItem(
            item_name="Temporary Shoring Allowance",
            scope_item="Shoring",
            quantity=1.0,
            unit="LS",
            unit_cost=5000.0,
            material_cost=0.0,
            labor_cost=0.0,
            equipment_cost=0.0,
            waste_factor=0.0,
            multipliers={},
            subtotal=5000.0,
            rule_matched="temp_shoring_allowance",
            evidence="Allowance",
            notes=[],
            quantity_source="allowance",
            quantity_confidence=0.9,
            quantity_evidence={"evidence_snippet": "Allowance item"},
        ),
    ]

    breakdown_by_category = [
        CostBreakdown(category="General", items=cost_items, subtotal=5000.0),
    ]

    costing = CostEngineResult(
        project_id="test-project",
        breakdown_by_category=breakdown_by_category,
        breakdown_by_scope_item=cost_items,
        breakdown_by_building={},
        subtotals={"General": 5000.0},
        total_cost=5000.0,
        material_cost_total=0.0,
        labor_cost_total=0.0,
        equipment_cost_total=0.0,
        waste_cost_total=0.0,
        cost_justification=[],
        missing_data_warnings=[],
        rules_used=["temp_shoring_allowance"],
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="institutional",
                context="test",
                evidence="test",
            )
        ),
    )

    validation = ValidationReport(
        project_id="test-project",
        passed=True,
        score=1.0,
        issues=[],
        missing_critical_items=[],
        conflicts={},
        rerun_performed=False,
        rerun_notes=[],
    )

    proposal = generate_bid_proposal(
        project_id="test-project",
        extraction=extraction,
        costing=costing,
        validation=validation,
        estimate_mode="bid_ready",
    )

    assert proposal.bid_ready is True  # Allowances are always acceptable
    assert len(proposal.allowances) == 1
    assert proposal.allowances[0].amount == 5000.0






