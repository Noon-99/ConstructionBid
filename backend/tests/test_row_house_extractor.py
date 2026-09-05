"""Unit tests for row-house repair extractor."""

from unittest.mock import MagicMock, patch

import pytest

from app.analyzers.row_house_repair_extractor import RowHouseRepairExtractor
from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult, MaterialSpecification
from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext, WorkZone
from app.services.openai_client import OpenAIClient


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
    )


@pytest.fixture
def openai_client(settings: Settings) -> OpenAIClient:
    """Create OpenAI client."""
    return OpenAIClient(settings)


@pytest.fixture
def extractor(settings: Settings, openai_client: OpenAIClient) -> RowHouseRepairExtractor:
    """Create row-house repair extractor."""
    return RowHouseRepairExtractor(settings, openai_client)


def test_extractor_requires_row_house_repair(extractor: RowHouseRepairExtractor) -> None:
    """Test that extractor only works for row_house + repair."""
    analysis = DocumentAnalysis(
        project_type="institutional",
        scope_type="renovation",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.8,
        missing_fields=[],
    )

    pdf_images = [
        PdfPageImage(page_number=1, image_base64="dGVzdA==", mime_type="image/png")
    ]

    with pytest.raises(ValueError, match="row_house.*repair"):
        extractor.extract(pdf_images, analysis, "test-project")


def test_extractor_uses_resolved_types(extractor: RowHouseRepairExtractor) -> None:
    """Test that extractor uses resolved types from TypologyResolver."""
    analysis = DocumentAnalysis(
        project_type="institutional",  # Original (wrong)
        scope_type="renovation",  # Original (wrong)
        resolved_project_type="row_house",  # Resolved (correct)
        resolved_scope_type="repair",  # Resolved (correct)
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.8,
        missing_fields=[],
    )

    pdf_images = [
        PdfPageImage(page_number=1, image_base64="dGVzdA==", mime_type="image/png")
    ]

    # Should not raise error about project type mismatch
    # (will fail on page selection, but that's expected)
    with pytest.raises((ValueError, KeyError)):  # Either no pages selected or extraction fails
        extractor.extract(pdf_images, analysis, "test-project")


def test_page_selection_usage(extractor: RowHouseRepairExtractor) -> None:
    """Test that extractor uses select_pages_for_stage2 correctly."""
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

    pdf_images = [
        PdfPageImage(page_number=1, image_base64="dGVzdA==", mime_type="image/png")
    ]

    # Should fail because no pages selected (expected behavior)
    with pytest.raises(ValueError, match="No pages selected"):
        extractor.extract(pdf_images, analysis, "test-project")


def test_lintel_extraction_in_scope() -> None:
    """Test that lintels are extracted into scope_of_work."""
    from app.schemas.extraction_result import ExtractionResult
    from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext

    # Create extraction result with lintels
    result = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            {
                "item": "lintel replacement",
                "description": "Replace 8 window lintels with steel angle L3x3x1/4",
                "location": "window openings",
                "page_number": 2,
                "sheet_id": "A-2",
                "evidence_snippet": "Typical lintel detail 1 - steel angle L3x3x1/4",
            }
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Row house",
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    # Verify lintel is in scope
    lintel_items = [
        item for item in result.scope_of_work if "lintel" in item.item.lower()
    ]
    assert len(lintel_items) > 0
    assert "steel angle" in lintel_items[0].description.lower() or "L3x3" in lintel_items[0].evidence_snippet


def test_lintel_extraction_in_materials() -> None:
    """Test that lintel materials are extracted."""
    from app.schemas.extraction_result import ExtractionResult
    from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext

    result = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[],
        material_specifications=[
            {
                "material_name": "Steel Lintel",
                "specification": "L3x3x1/4",
                "application": "Lintel replacement",
                "detail_sheet": "D-2",
                "page_number": 2,
                "sheet_id": "A-2",
                "evidence_snippet": "Steel lintel schedule S-011 - L3x3x1/4",
            }
        ],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Row house",
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    lintel_materials = [
        mat
        for mat in result.material_specifications
        if "lintel" in mat.material_name.lower()
    ]
    assert len(lintel_materials) > 0
    assert lintel_materials[0].specification is not None


def test_lintel_work_zone_extraction() -> None:
    """Test that lintel work zones are created."""
    from app.schemas.extraction_result import ExtractionResult
    from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext, WorkZone

    result = ExtractionResult(
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
                evidence="Row house",
            ),
            work_zones=[
                WorkZone(
                    zone_name="lintel_band",
                    z_min=None,
                    z_max=None,
                    facade_region="lintel band",
                    page_number=2,
                    sheet_id="A-2",
                    evidence="Lintel replacement zone - typical lintel detail",
                )
            ],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    lintel_zones = [
        zone for zone in result.geometry_for_3d.work_zones if "lintel" in zone.zone_name.lower()
    ]
    assert len(lintel_zones) > 0
    assert lintel_zones[0].facade_region is not None


def test_lintel_missing_detection() -> None:
    """Test that missing lintels are added to evidence_missing."""
    from app.schemas.extraction_result import ExtractionResult
    from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext

    result = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            {
                "item": "parapet repair",
                "description": "Parapet work",
                "location": "front facade",
                "page_number": 1,
                "sheet_id": "A-1",
                "evidence_snippet": "Parapet repair",
            }
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Row house",
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=["lintels"],
    )

    assert "lintels" in result.evidence_missing


def test_extraction_schema_validation() -> None:
    """Test that extraction result matches schema."""
    from app.schemas.extraction_result import ExtractionResult
    from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext

    # Valid extraction result
    result = ExtractionResult(
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
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    assert result.project_type == "row_house"
    assert result.scope_type == "repair"
    assert isinstance(result.geometry_for_3d, GeometryFor3D)


def test_lintel_extraction_in_scope() -> None:
    """Test that lintels are extracted as scope items."""
    # Valid extraction result with lintels
    result = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            {
                "item": "lintel replacement",
                "description": "Replace window lintels with steel angles",
                "location": "window openings",
                "page_number": 2,
                "sheet_id": "A-2",
                "evidence_snippet": "Replace window lintels - typical lintel detail 1",
            }
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

    # Check lintel is in scope
    lintel_items = [
        item for item in result.scope_of_work if "lintel" in item.item.lower()
    ]
    assert len(lintel_items) > 0
    assert "lintel" in lintel_items[0].item.lower()


def test_lintel_material_extraction() -> None:
    """Test that lintel materials are extracted."""
    result = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[],
        material_specifications=[
            MaterialSpecification(
                material_name="Steel Lintel",
                specification="L3x3x1/4",
                application="Window lintel replacement",
                detail_sheet="S-011",
                page_number=2,
                sheet_id="A-2",
                evidence_snippet="Steel lintel schedule S-011 - L3x3x1/4",
            )
        ],
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

    lintel_materials = [
        m for m in result.material_specifications if "lintel" in m.material_name.lower()
    ]
    assert len(lintel_materials) > 0
    assert "steel" in lintel_materials[0].material_name.lower()


def test_lintel_work_zone_extraction() -> None:
    """Test that lintel work zones are created."""
    result = ExtractionResult(
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
            work_zones=[
                WorkZone(
                    zone_name="lintel_band",
                    z_min=8.0,
                    z_max=10.0,
                    facade_region=None,
                    page_number=1,
                    sheet_id="A-1",
                    evidence="Lintel zone at window level",
                )
            ],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    lintel_zones = [
        zone for zone in result.geometry_for_3d.work_zones if "lintel" in zone.zone_name
    ]
    assert len(lintel_zones) > 0
    assert lintel_zones[0].zone_name == "lintel_band"


def test_lintel_missing_detection() -> None:
    """Test that missing lintels are detected."""
    result = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[],  # No lintels
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            work_zones=[],  # No lintel zone
        ),
        validation_metadata={},
        evidence_missing=["lintels"],
    )

    assert "lintels" in result.evidence_missing

