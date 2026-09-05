"""Tests for 3D model generator institutional branch (Phase 4.5)."""

import pytest

from app.generators.model_3d_generator import Model3DGenerator
from app.schemas.extraction_result import ExtractionResult
from app.schemas.geometry_for_3d import Dimensions, GeometryFor3D, SiteContext
from app.schemas.institutional_geometry_for_3d import (
    BuildingMass,
    InstitutionalGeometryFor3D,
    RoomZoneVolume,
)
from app.schemas.model_3d import Model3D


@pytest.fixture
def generator() -> Model3DGenerator:
    """Create model 3D generator."""
    return Model3DGenerator()


def test_institutional_generator_emits_building_masses_and_room_zones(
    generator: Model3DGenerator,
) -> None:
    """Test that institutional generator emits building masses + room zones."""
    # Create institutional geometry
    existing_building = BuildingMass(
        mass_id="existing_001",
        label="existing",
        dimensions={"width_ft": 100.0, "depth_ft": 80.0, "height_ft": 20.0},
        area_gsf=8000.0,
        bbox={
            "min": {"x": 0.0, "y": 0.0, "z": 0.0},
            "max": {"x": 100.0, "y": 80.0, "z": 20.0},
        },
        placement={"x_offset_ft": 0.0, "y_offset_ft": 0.0, "relation": "adjacent_unknown"},
        evidence={"page_number": 1, "evidence_snippet": "Existing building"},
    )

    addition_building = BuildingMass(
        mass_id="addition_001",
        label="addition",
        dimensions={"width_ft": 30.0, "depth_ft": 40.0, "height_ft": 20.0},
        area_gsf=1200.0,
        bbox={
            "min": {"x": 100.0, "y": 0.0, "z": 0.0},
            "max": {"x": 130.0, "y": 40.0, "z": 20.0},
        },
        placement={"x_offset_ft": 100.0, "y_offset_ft": 0.0, "relation": "adjacent_unknown"},
        evidence={"page_number": 1, "evidence_snippet": "Addition building"},
    )

    room_zones = [
        RoomZoneVolume(
            room_number="127",
            room_name="Gymnasium",
            area_sf=7140.0,
            floor=None,
            zone_id="room_127",
            bbox={
                "min": {"x": 0.0, "y": 0.0, "z": 0.0},
                "max": {"x": 70.0, "y": 102.0, "z": 20.0},
            },
            assignment_confidence=0.9,
            evidence={"page_number": 2, "evidence_snippet": "Gymnasium 7,140 SF"},
            notes="layout unknown, packed by area for visualization",
        ),
        RoomZoneVolume(
            room_number="101",
            room_name="Meeting Room",
            area_sf=500.0,
            floor=None,
            zone_id="room_101",
            bbox={
                "min": {"x": 70.0, "y": 0.0, "z": 0.0},
                "max": {"x": 100.0, "y": 7.14, "z": 20.0},
            },
            assignment_confidence=0.8,
            evidence={"page_number": 2, "evidence_snippet": "Meeting Room 500 SF"},
            notes="layout unknown, packed by area for visualization",
        ),
    ]

    inst_geometry = InstitutionalGeometryFor3D(
        existing_building=existing_building,
        addition_building=addition_building,
        room_zones=room_zones,
        geometry_quality="authoritative",
        missing_evidence=[],
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="addition",
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(building_type="institutional", evidence="Institutional"),
            dimensions=Dimensions(width=100.0, depth=80.0, height=20.0, evidence="From plans"),
        ),
        institutional_geometry_for_3d=inst_geometry,
    )

    model = generator.generate(extraction)

    # Assertions
    assert isinstance(model, Model3D)
    assert len(model.buildings) == 2  # Existing + addition
    assert len(model.work_zones) == 2  # Room zones

    # Check building types
    building_types = [b.building_type for b in model.buildings]
    assert "institutional" in building_types

    # Check room zones have zone_type="room"
    room_zones_in_model = [z for z in model.work_zones if z.zone_type == "room"]
    assert len(room_zones_in_model) == 2

    # Check Gymnasium is present
    gym_zone = next((z for z in model.work_zones if "Gymnasium" in z.zone_name), None)
    assert gym_zone is not None
    assert gym_zone.zone_type == "room"
    assert gym_zone.bounding_box is not None

    # Check evidence is preserved
    assert gym_zone.evidence == "Room: Gymnasium" or "Gymnasium" in gym_zone.evidence
    assert gym_zone.page_number == 2


def test_institutional_generator_without_geometry_falls_back(
    generator: Model3DGenerator,
) -> None:
    """Test that generator falls back to row-house path if no institutional geometry."""
    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(building_type="institutional", evidence="Institutional"),
            dimensions=Dimensions(width=100.0, depth=80.0, height=20.0, evidence="From plans"),
        ),
        institutional_geometry_for_3d=None,  # No institutional geometry
    )

    # Should use row-house path (will have missing evidence but should not crash)
    model = generator.generate(extraction)
    assert isinstance(model, Model3D)






