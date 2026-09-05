"""Tests for Phase 1 compliance enhancements.

Verifies:
1. Enhanced procurement analyzer GPT prompt
2. Compliance costs as explicit line items
3. Enhanced compliance adjustment explanations
"""

import pytest

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal
from app.schemas.costing import CostBreakdown, CostEngineResult, CostItem
from app.schemas.extraction_result import ExtractionResult
from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext
from app.schemas.validation_report import ValidationReport
from app.services.bid_proposal_generator import generate_bid_proposal
from app.services.procurement_analyzer import ProcurementSignalAnalyzer


def test_procurement_analyzer_enhanced_prompt() -> None:
    """Test that procurement analyzer has enhanced GPT prompt."""
    settings = Settings()
    from app.services.openai_client import OpenAIClient
    
    analyzer = ProcurementSignalAnalyzer(settings, OpenAIClient(settings))
    prompt = analyzer._build_prompt()
    
    # Verify enhanced prompt includes pattern recognition language
    assert "pattern recognition" in prompt.lower() or "semantic understanding" in prompt.lower()
    assert "generalize" in prompt.lower() or "variations" in prompt.lower()
    assert "government" in prompt.lower() or "public" in prompt.lower()
    
    # Verify it asks for intelligent detection, not just keywords
    assert "intelligently" in prompt.lower() or "semantic" in prompt.lower()


def test_compliance_costs_as_line_items() -> None:
    """Test that compliance costs (bonds, insurance) appear as explicit line items."""
    # Create mock costing result with compliance costs
    cost_items = [
        CostItem(
            item_name="Roof Replacement",
            scope_item="Roof Replacement",
            quantity=8000.0,
            unit="SF",
            unit_cost=25.0,
            material_cost=120000.0,
            labor_cost=80000.0,
            equipment_cost=0.0,
            waste_factor=0.0,
            multipliers={},
            subtotal=200000.0,
            rule_matched="roof_replacement",
            evidence="From drawings",
            notes=[],
        ),
    ]
    
    breakdown_by_category = [
        CostBreakdown(category="Waterproofing", items=cost_items, subtotal=200000.0),
    ]
    
    costing = CostEngineResult(
        project_id="test-project",
        breakdown_by_category=breakdown_by_category,
        breakdown_by_scope_item=cost_items,
        breakdown_by_building={},
        subtotals={"Waterproofing": 200000.0},
        total_cost=223500.0,  # Includes compliance costs
        material_cost_total=120000.0,
        labor_cost_total=80000.0,
        equipment_cost_total=0.0,
        waste_cost_total=0.0,
        cost_justification=[],
        missing_data_warnings=[],
        rules_used=["roof_replacement"],
        compliance_costs={"bond": 5000.0, "insurance": 2000.0},  # $7k total
        compliance_total=7000.0,
        base_scope_cost=200000.0,
        compliance_adjustments=[
            "Performance & Payment Bonds: +2.50% of base scope ($5,000.00) (Government/public project detected). Required for public/government contracts to protect the owner.",
            "Supplemental Insurance: +1.00% of base scope ($2,000.00) (Government/public project detected). Additional coverage required for public/government projects.",
        ],
    )
    
    extraction = ExtractionResult(
        project_type="commercial",
        scope_type="renovation",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="commercial",
                context="test",
                evidence="Test evidence",
            ),
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
    
    # Verify compliance costs appear as line items
    line_item_descriptions = [item.description for item in proposal.line_items]
    
    # Should have bonds and insurance as explicit line items
    assert any("bond" in desc.lower() for desc in line_item_descriptions), \
        "Bonds should appear as explicit line item"
    assert any("insurance" in desc.lower() for desc in line_item_descriptions), \
        "Insurance should appear as explicit line item"
    
    # Verify compliance costs are in summary
    assert proposal.summary.compliance_costs == {"bond": 5000.0, "insurance": 2000.0}
    assert proposal.summary.compliance_total == 7000.0


def test_enhanced_compliance_adjustment_explanations() -> None:
    """Test that compliance adjustments include enhanced explanations."""
    # Create mock costing with compliance adjustments
    cost_items = [
        CostItem(
            item_name="Roof Replacement",
            scope_item="Roof Replacement",
            quantity=8000.0,
            unit="SF",
            unit_cost=25.0,
            material_cost=120000.0,
            labor_cost=80000.0,
            equipment_cost=0.0,
            waste_factor=0.0,
            multipliers={},
            subtotal=200000.0,
            rule_matched="roof_replacement",
            evidence="From drawings",
            notes=[],
        ),
    ]
    
    breakdown_by_category = [
        CostBreakdown(category="Waterproofing", items=cost_items, subtotal=200000.0),
    ]
    
    # Test with enhanced compliance adjustments
    compliance_adjustments = [
        "Prevailing wage multiplier applied: +50% to labor rates (NYS OGS project detected). Required for public/government projects per Davis-Bacon or state prevailing wage laws.",
        "Performance & Payment Bonds: +2.50% of base scope ($5,000.00) (Government/public project detected). Required for public/government contracts to protect the owner.",
    ]
    
    costing = CostEngineResult(
        project_id="test-project",
        breakdown_by_category=breakdown_by_category,
        breakdown_by_scope_item=cost_items,
        breakdown_by_building={},
        subtotals={"Waterproofing": 200000.0},
        total_cost=205000.0,
        material_cost_total=120000.0,
        labor_cost_total=80000.0,
        equipment_cost_total=0.0,
        waste_cost_total=0.0,
        cost_justification=[],
        missing_data_warnings=[],
        rules_used=["roof_replacement"],
        compliance_adjustments=compliance_adjustments,
    )
    
    extraction = ExtractionResult(
        project_type="commercial",
        scope_type="renovation",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="commercial",
                context="test",
                evidence="Test evidence",
            ),
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
    
    # Verify enhanced explanations appear in clarifications
    clarification_texts = [c.text for c in proposal.clarifications]
    
    # Should have compliance adjustment clarifications with enhanced explanations
    compliance_clarifications = [
        c for c in proposal.clarifications
        if "compliance" in c.text.lower() or "adjustment" in c.text.lower()
    ]
    
    assert len(compliance_clarifications) > 0, "Should have compliance adjustment clarifications"
    
    # Verify explanations include context (e.g., "NYS OGS", "Government/public project")
    all_clarification_text = " ".join(clarification_texts).lower()
    assert "government" in all_clarification_text or "public" in all_clarification_text, \
        "Compliance adjustments should mention government/public project context"
