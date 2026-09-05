"""Unit tests for typology expansion (Phase 10.7)."""

import pytest

from app.schemas.document_analysis import DocumentAnalysis
from app.services.typology_resolver import resolve_typology
from app.services.typology_confidence_service import generate_typology_confidence_report


def test_small_commercial_falls_back_to_row_house() -> None:
    """Test: small_commercial falls back to row_house if row-house indicators present."""
    analysis = DocumentAnalysis(
        project_type="small_commercial",
        scope_type="renovation",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.7,
        missing_fields=[],
    )
    
    # Add row-house indicator (elevation with adjacent building mention)
    from app.schemas.document_analysis import SheetInfo, ScopeLocator
    analysis.sheets = [
        SheetInfo(sheet_id="A-1", sheet_type="elevation", page_number=1, title=None)
    ]
    analysis.where_scope_lives = [
        ScopeLocator(
            sheet_id="A-1",
            page_number=1,
            location_type="elevation_notes",
            evidence="adjacent building party wall",
            confidence=0.8,
        )
    ]
    
    resolved = resolve_typology(analysis)
    
    # Should override to row_house due to indicators
    assert resolved.resolved_project_type == "row_house"
    # Verify override occurred (resolution notes should exist)
    assert len(resolved.resolution_notes) > 0


def test_multi_family_falls_back_to_row_house() -> None:
    """Test: multi_family falls back to row_house if row-house indicators present."""
    analysis = DocumentAnalysis(
        project_type="multi_family",
        scope_type="renovation",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.7,
        missing_fields=[],
    )
    
    # Add row-house indicator
    from app.schemas.document_analysis import SheetInfo, ScopeLocator
    analysis.sheets = [
        SheetInfo(sheet_id="A-1", sheet_type="elevation", page_number=1, title="Row House Elevation")
    ]
    
    resolved = resolve_typology(analysis)
    
    # Should override to row_house
    assert resolved.resolved_project_type == "row_house"


def test_existing_row_house_stays_row_house() -> None:
    """Test: Existing row_house projects remain row_house (no breaking change)."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.8,
        missing_fields=[],
    )
    
    resolved = resolve_typology(analysis)
    
    # Should remain row_house
    assert resolved.resolved_project_type is None  # No override needed
    assert resolved.project_type == "row_house"


def test_institutional_triggers_only_with_indicators() -> None:
    """Test: Institutional routing only triggers with strong indicators."""
    # Test that institutional still requires strong signals (handled in pipeline)
    analysis = DocumentAnalysis(
        project_type="institutional",
        scope_type="renovation",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.6,
        missing_fields=[],
    )
    
    # Without life_safety_plan indicators, should not force override
    resolved = resolve_typology(analysis)
    
    # Typology resolver doesn't override institutional unless row-house indicators present
    assert resolved.resolved_project_type is None or resolved.resolved_project_type == "institutional"


def test_typology_confidence_report_generation() -> None:
    """Test: Typology confidence report generation."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.8,
        missing_fields=[],
    )
    
    report = generate_typology_confidence_report(
        project_id="test-project",
        document_analysis=analysis,
        routing_decision="row_house_path",
        routing_reason="project_type=row_house and scope_type=repair",
    )
    
    assert report.project_id == "test-project"
    assert report.final_project_type == "row_house"
    assert report.routing_decision == "row_house_path"
    assert report.overall_confidence >= 0.0
    assert report.overall_confidence <= 1.0

