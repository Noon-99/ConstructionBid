"""Unit tests for 3D model generator."""

import pytest

from app.generators.model_3d_generator import Model3DGenerator
from app.schemas.extraction_result import ExtractionResult
from app.schemas.geometry_for_3d import (
    Dimensions,
    GeometryFor3D,
    SiteContext,
    WorkZone,
)
from app.schemas.model_3d import Model3D


@pytest.fixture
def generator() -> Model3DGenerator:
    """Create 3D model generator."""
    return Model3DGenerator()


def test_generate_with_complete_dimensions(generator: Model3DGenerator) -> None:
    """Test generation with complete dimensions."""
    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=["B-1", "B-2"],
                subject_building_id="B-2",
                addresses=[],
                evidence="Row house context",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=30.0,
                evidence="Extracted from elevations",
                confidence=0.9,
            ),
            work_zones=[
                WorkZone(
                    zone_name="parapet_band",
                    z_min=28.0,
                    z_max=30.0,
                    facade_region=None,
                    page_number=1,
                    sheet_id="A-1",
                    evidence="Parapet zone",
                )
            ],
            evidence_missing=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    model = generator.generate(extraction)

    assert isinstance(model, Model3D)
    assert len(model.buildings) > 0
    assert any(b.is_subject for b in model.buildings)
    assert len(model.work_zones) == 1
    assert model.work_zones[0].zone_name == "parapet_band"
    assert model.work_zones[0].bounding_box is not None
    assert len(model.missing_evidence) == 0


def test_generate_with_missing_dimensions(generator: Model3DGenerator) -> None:
    """Test generation with missing dimensions."""
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
                evidence="Row house context",
            ),
            dimensions=None,
            work_zones=[],
            evidence_missing=["dimensions"],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    model = generator.generate(extraction)

    assert isinstance(model, Model3D)
    assert len(model.buildings) == 0  # No buildings without dimensions
    assert "width" in model.missing_evidence
    assert "depth" in model.missing_evidence
    assert "height" in model.missing_evidence


def test_generate_with_facade_regions_only(generator: Model3DGenerator) -> None:
    """Test generation with work zones that only have facade regions (no Z coordinates)."""
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
                evidence="Row house context",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=30.0,
                evidence="Extracted",
                confidence=0.9,
            ),
            work_zones=[
                WorkZone(
                    zone_name="lintel_band",
                    z_min=None,
                    z_max=None,
                    facade_region="lintel band",
                    page_number=1,
                    sheet_id="A-1",
                    evidence="Lintel zone",
                )
            ],
            evidence_missing=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    model = generator.generate(extraction)

    assert len(model.work_zones) == 1
    assert model.work_zones[0].bounding_box is None
    assert model.work_zones[0].facade_region == "lintel band"


def test_generate_adjacent_buildings(generator: Model3DGenerator) -> None:
    """Test generation includes adjacent buildings in row."""
    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=["B-1", "B-2", "B-3"],
                subject_building_id="B-2",
                addresses=[],
                evidence="Row of 3 buildings",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=30.0,
                evidence="Extracted",
                confidence=0.9,
            ),
            work_zones=[],
            evidence_missing=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    model = generator.generate(extraction)

    # Should have subject building + 2 adjacent buildings
    assert len(model.buildings) == 3
    subject_buildings = [b for b in model.buildings if b.is_subject]
    assert len(subject_buildings) == 1
    assert subject_buildings[0].building_id == "B-2"


def test_no_hardcoded_geometry(generator: Model3DGenerator) -> None:
    """Test that no hardcoded geometry is used when dimensions are missing."""
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
                evidence="Row house context",
            ),
            dimensions=Dimensions(
                width=None,  # Missing
                depth=40.0,
                height=30.0,
                evidence="Partial dimensions",
                confidence=0.9,
            ),
            work_zones=[],
            evidence_missing=["width"],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    model = generator.generate(extraction)

    # Should not create buildings without complete dimensions
    assert len(model.buildings) == 0
    assert "width" in model.missing_evidence


def test_material_assignments(generator: Model3DGenerator) -> None:
    """Test that materials are assigned correctly."""
    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            {
                "item": "parapet repair",
                "description": "Parapet repair work",
                "location": "front facade",
                "page_number": 1,
                "sheet_id": "A-1",
                "evidence_snippet": "Parapet repair noted",
            }
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                subject_building_id="B-1",
                addresses=[],
                evidence="Row house",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=30.0,
                evidence="Extracted",
                confidence=0.9,
            ),
            work_zones=[],
            evidence_missing=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    model = generator.generate(extraction)

    # Should assign materials
    assert "B-1" in model.materials.building_materials
    assert model.materials.building_materials["B-1"] == "brick_masonry"
    # Should assign work zone materials based on scope
    assert "parapet_band" in model.materials.work_zone_materials

