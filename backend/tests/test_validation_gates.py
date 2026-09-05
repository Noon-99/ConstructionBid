"""Unit tests for validation gates."""

import pytest

from app.core.config import Settings
from app.schemas.document_analysis import BuildingContext, DocumentAnalysis, KeyDimensions
from app.schemas.extraction_result import ExtractionResult, ScopeItem
from app.schemas.geometry_for_3d import Dimensions, GeometryFor3D, SiteContext, WorkZone
from app.services.openai_client import OpenAIClient
from app.services.validation_gates import (
    _check_dimension_conflicts,
    _check_row_context_mismatch,
    _validate_critical_scope,
    _validate_geometry_contract,
)


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")


@pytest.fixture
def openai_client(settings: Settings) -> OpenAIClient:
    """Create OpenAI client."""
    return OpenAIClient(settings)


def test_validate_critical_scope_missing_items() -> None:
    """Test that missing critical scope items are detected."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.9,
        missing_fields=[],
    )

    # Missing most critical items
    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            ScopeItem(
                item="parapet repair",
                description="Parapet",
                page_number=1,
                sheet_id=None,
                evidence_snippet="Parapet",
            )
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    issues = _validate_critical_scope(analysis, extraction)

    # Should have error for missing critical scope
    error_issues = [i for i in issues if i.severity == "error"]
    assert len(error_issues) > 0
    assert any("MISSING_CRITICAL_SCOPE" in issue.code for issue in error_issues)


def test_validate_critical_scope_all_present() -> None:
    """Test that all critical scope items pass validation."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.9,
        missing_fields=[],
    )

    # All critical items present
    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            ScopeItem(item="parapet repair", description="Parapet", page_number=1, sheet_id=None, evidence_snippet="Parapet"),
            ScopeItem(item="lintel replacement", description="Lintels", page_number=1, sheet_id=None, evidence_snippet="Lintels"),
            ScopeItem(item="flashing installation", description="Flashing", page_number=1, sheet_id=None, evidence_snippet="Flashing"),
            ScopeItem(item="brick rebuild", description="Brick", page_number=1, sheet_id=None, evidence_snippet="Brick"),
            ScopeItem(item="crack repair", description="Cracks", page_number=1, sheet_id=None, evidence_snippet="Cracks"),
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    issues = _validate_critical_scope(analysis, extraction)

    # Should have no errors
    error_issues = [i for i in issues if i.severity == "error"]
    assert len(error_issues) == 0


def test_validate_geometry_contract_missing_dimensions() -> None:
    """Test that missing dimensions are detected."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.9,
        missing_fields=[],
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
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            dimensions=None,  # Missing dimensions
            work_zones=[],
            evidence_missing=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    issues = _validate_geometry_contract(analysis, extraction)

    # Should have error for missing geometry
    error_issues = [i for i in issues if i.severity == "error"]
    assert len(error_issues) > 0
    assert any("MISSING_GEOMETRY" in issue.code for issue in error_issues)


def test_check_dimension_conflicts() -> None:
    """Test that dimension conflicts are detected."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        key_dimensions=KeyDimensions(
            width=40.0,
            depth=60.0,
            height=30.0,
            evidence="Stage 1",
            confidence=0.9,
        ),
        confidence=0.9,
        missing_fields=[],
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
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            dimensions=Dimensions(
                width=50.0,  # 25% difference from 40.0 (error threshold)
                depth=60.0,
                height=30.0,
                evidence="Stage 2",
                confidence=0.9,
            ),
            work_zones=[],
            evidence_missing=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    conflicts = _check_dimension_conflicts(analysis, extraction)

    assert conflicts is not None
    assert "issues" in conflicts
    error_issues = [i for i in conflicts["issues"] if i.severity == "error"]
    assert len(error_issues) > 0
    assert any("DIMENSION_CONFLICT" in issue.code for issue in error_issues)


def test_check_row_context_mismatch() -> None:
    """Test that row context mismatches are detected."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        building_context=BuildingContext(
            building_type="row_house",
            is_row_context=True,
            building_ids=["B-1", "B-2", "B-3"],
            addresses=[],
            evidence="Row context",
        ),
        confidence=0.9,
        missing_fields=[],
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
                row_of_buildings=["B-1"],  # Only one building (mismatch)
                addresses=[],
                evidence="Test",
            ),
            work_zones=[],
            evidence_missing=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    issues = _check_row_context_mismatch(analysis, extraction)

    # Should have warning for row context mismatch
    assert len(issues) > 0
    assert any("ROW_CONTEXT_MISMATCH" in issue.code for issue in issues)

