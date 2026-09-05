"""Tests for bid proposal generator (Phase 4.6)."""

from datetime import datetime

import pytest

from app.schemas.bid_proposal import BidProposal
from app.schemas.costing import CostBreakdown, CostEngineResult, CostItem
from app.schemas.extraction_result import ExtractionResult
from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext
from app.schemas.validation_report import ValidationIssue, ValidationReport
from app.services.bid_proposal_generator import generate_bid_proposal


def test_generate_bid_proposal_groups_costs_into_divisions() -> None:
    """Test that bid proposal groups costs into CSI divisions."""
    # Create mock costing result with multiple categories
    cost_items = [
        CostItem(
            item_name="CMU Wall Demo",
            scope_item="CMU Wall Demo",
            quantity=100.0,
            unit="SF",
            unit_cost=8.50,
            material_cost=0.0,
            labor_cost=660.0,
            equipment_cost=200.0,
            waste_factor=0.0,
            multipliers={},
            subtotal=850.0,
            rule_matched="cmu_wall_demo",
            evidence="From drawings",
            notes=[],
        ),
        CostItem(
            item_name="New 8\" CMU Wall",
            scope_item="New 8\" CMU Wall",
            quantity=200.0,
            unit="SF",
            unit_cost=18.50,
            material_cost=1700.0,
            labor_cost=1650.0,
            equipment_cost=200.0,
            waste_factor=0.05,
            multipliers={},
            subtotal=3700.0,
            rule_matched="new_cmu_wall_8in",
            evidence="From drawings",
            notes=[],
        ),
        CostItem(
            item_name="Concrete Footing",
            scope_item="Concrete Footing",
            quantity=10.0,
            unit="CY",
            unit_cost=450.0,
            material_cost=1200.0,
            labor_cost=1375.0,
            equipment_cost=500.0,
            waste_factor=0.10,
            multipliers={},
            subtotal=4500.0,
            rule_matched="concrete_footing",
            evidence="From drawings",
            notes=[],
        ),
    ]

    breakdown_by_category = [
        CostBreakdown(category="Demo", items=[cost_items[0]], subtotal=850.0),
        CostBreakdown(category="Masonry", items=[cost_items[1]], subtotal=3700.0),
        CostBreakdown(category="Concrete", items=[cost_items[2]], subtotal=4500.0),
    ]

    costing = CostEngineResult(
        project_id="test-project",
        breakdown_by_category=breakdown_by_category,
        breakdown_by_scope_item=cost_items,
        breakdown_by_building={},
        subtotals={"Demo": 850.0, "Masonry": 3700.0, "Concrete": 4500.0},
        total_cost=9050.0,
        material_cost_total=2900.0,
        labor_cost_total=3685.0,
        equipment_cost_total=900.0,
        waste_cost_total=0.0,
        cost_justification=[],
        missing_data_warnings=[],
        rules_used=["cmu_wall_demo", "new_cmu_wall_8in", "concrete_footing"],
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
    )

    assert proposal.project_id == "test-project"
    assert proposal.summary.total_cost == 9050.0
    assert len(proposal.line_items) == 3
    
    # Check divisions
    divisions = {item.division for item in proposal.line_items}
    assert "02 Existing Conditions" in divisions  # Demo
    assert "04 Masonry" in divisions  # Masonry
    assert "03 Concrete" in divisions  # Concrete
    
    # Check division totals
    assert proposal.summary.cost_by_division["02 Existing Conditions"] == 850.0
    assert proposal.summary.cost_by_division["04 Masonry"] == 3700.0
    assert proposal.summary.cost_by_division["03 Concrete"] == 4500.0


def test_generate_bid_proposal_includes_allowances() -> None:
    """Test that allowance items are included as allowances."""
    cost_items = [
        CostItem(
            item_name="Temporary Shoring Allowance",
            scope_item="Temporary Shoring Allowance",
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
            evidence="Allowance for temporary shoring",
            notes=[],
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
    )

    assert len(proposal.allowances) == 1
    assert proposal.allowances[0].name == "Temporary Shoring Allowance"
    assert proposal.allowances[0].amount == 5000.0
    assert proposal.summary.total_cost == 5000.0


def test_generate_bid_proposal_includes_clarifications_from_validation() -> None:
    """Test that validation issues are converted to clarifications."""
    cost_items = [
        CostItem(
            item_name="Test Item",
            scope_item="Test Item",
            quantity=10.0,
            unit="SF",
            unit_cost=10.0,
            material_cost=50.0,
            labor_cost=50.0,
            equipment_cost=0.0,
            waste_factor=0.0,
            multipliers={},
            subtotal=100.0,
            rule_matched="test_rule",
            evidence="Test evidence",
            notes=[],
        ),
    ]

    breakdown_by_category = [
        CostBreakdown(category="General", items=cost_items, subtotal=100.0),
    ]

    costing = CostEngineResult(
        project_id="test-project",
        breakdown_by_category=breakdown_by_category,
        breakdown_by_scope_item=cost_items,
        breakdown_by_building={},
        subtotals={"General": 100.0},
        total_cost=100.0,
        material_cost_total=50.0,
        labor_cost_total=50.0,
        equipment_cost_total=0.0,
        waste_cost_total=0.0,
        cost_justification=[],
        missing_data_warnings=["No cost rule found for scope item: Unknown"],
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
        passed=False,
        score=0.7,
        issues=[
            ValidationIssue(
                code="MISSING_DATA",
                severity="warning",
                message="Some data is missing",
                affected_fields=["scope_of_work"],
                recommended_action="Re-read pages",
            ),
            ValidationIssue(
                code="CRITICAL_ERROR",
                severity="error",
                message="Critical error occurred",
                affected_fields=["extraction"],
                recommended_action="Fix extraction",
            ),
        ],
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
    )

    # Should have clarifications from validation issues and missing data warnings
    assert len(proposal.clarifications) >= 3  # At least 2 from validation + 1 from missing data
    
    # Check severity mapping
    warning_clarifications = [c for c in proposal.clarifications if c.severity == "warning"]
    critical_clarifications = [c for c in proposal.clarifications if c.severity == "critical"]
    assert len(warning_clarifications) >= 1
    assert len(critical_clarifications) >= 1


def test_generate_bid_proposal_totals_match() -> None:
    """Test that bid proposal totals match costing totals."""
    cost_items = [
        CostItem(
            item_name="Item 1",
            scope_item="Item 1",
            quantity=10.0,
            unit="SF",
            unit_cost=10.0,
            material_cost=50.0,
            labor_cost=50.0,
            equipment_cost=0.0,
            waste_factor=0.0,
            multipliers={},
            subtotal=100.0,
            rule_matched="test_rule",
            evidence="Test",
            notes=[],
        ),
        CostItem(
            item_name="Item 2",
            scope_item="Item 2",
            quantity=20.0,
            unit="SF",
            unit_cost=15.0,
            material_cost=100.0,
            labor_cost=200.0,
            equipment_cost=0.0,
            waste_factor=0.0,
            multipliers={},
            subtotal=300.0,
            rule_matched="test_rule",
            evidence="Test",
            notes=[],
        ),
    ]

    breakdown_by_category = [
        CostBreakdown(category="General", items=cost_items, subtotal=400.0),
    ]

    costing = CostEngineResult(
        project_id="test-project",
        breakdown_by_category=breakdown_by_category,
        breakdown_by_scope_item=cost_items,
        breakdown_by_building={},
        subtotals={"General": 400.0},
        total_cost=400.0,
        material_cost_total=150.0,
        labor_cost_total=250.0,
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

    proposal = generate_bid_proposal(
        project_id="test-project",
        extraction=extraction,
        costing=costing,
        validation=validation,
    )

    # Total should match
    line_items_total = sum(item.total_cost for item in proposal.line_items)
    allowances_total = sum(allowance.amount for allowance in proposal.allowances)
    calculated_total = line_items_total + allowances_total
    
    assert proposal.summary.total_cost == calculated_total
    assert proposal.summary.total_cost == 400.0


def test_bid_proposal_defaults_to_conceptual_mode() -> None:
    """Test that bid_mode defaults to 'conceptual' (Phase 9.0)."""
    cost_items = [
        CostItem(
            item_name="Test Item",
            scope_item="Test Item",
            quantity=10.0,
            unit="SF",
            unit_cost=10.0,
            material_cost=50.0,
            labor_cost=50.0,
            equipment_cost=0.0,
            waste_factor=0.0,
            multipliers={},
            subtotal=100.0,
            rule_matched="test_rule",
            evidence="Test",
            notes=[],
        ),
    ]

    breakdown_by_category = [
        CostBreakdown(category="General", items=cost_items, subtotal=100.0),
    ]

    costing = CostEngineResult(
        project_id="test-project",
        breakdown_by_category=breakdown_by_category,
        breakdown_by_scope_item=cost_items,
        breakdown_by_building={},
        subtotals={"General": 100.0},
        total_cost=100.0,
        material_cost_total=50.0,
        labor_cost_total=50.0,
        equipment_cost_total=0.0,
        waste_cost_total=0.0,
        cost_justification=[],
        missing_data_warnings=[],
        rules_used=["test_rule"],
    )

    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
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
    )

    # Phase 9.0: bid_mode should default to "conceptual"
    assert proposal.bid_mode == "conceptual"

