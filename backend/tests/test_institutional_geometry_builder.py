"""Tests for institutional geometry builder (Phase 4.5)."""

import pytest

from app.core.config import Settings
from app.schemas.document_analysis import DocumentAnalysis, KeyDimensions
from app.schemas.extraction_result import ExtractionResult
from app.schemas.geometry_for_3d import Dimensions, GeometryFor3D, SiteContext
from app.schemas.institutional_geometry_for_3d import InstitutionalGeometryFor3D
from app.schemas.institutional_rooms import (
    InstitutionalRoomProgramResult,
    RoomItem,
    RoomProgramTotals,
)
from app.services.dimension_authority import AuthoritativeDimensions
from app.services.institutional_geometry_builder import build_institutional_geometry


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings()


@pytest.fixture
def analysis() -> DocumentAnalysis:
    """Create test document analysis."""
    return DocumentAnalysis(
        project_type="institutional",
        scope_type="new_construction",
        key_dimensions=KeyDimensions(
            width=100.0, depth=80.0, height=20.0, confidence=0.9, evidence="From plans"
        ),
        confidence=0.9,
        missing_fields=[],
    )


def test_build_geometry_with_authoritative_dims_and_20_rooms(
    settings: Settings, analysis: DocumentAnalysis
) -> None:
    """Test geometry builder with authoritative dims + 20 rooms produces envelope + zones."""
    # Create room program with 20 rooms
    rooms = [
        RoomItem(
            room_name=f"Room {i}",
            area_sf=500.0 + i * 50.0,  # Varying areas
            page_number=1,
            evidence_snippet=f"Room {i}",
        )
        for i in range(20)
    ]
    # Make first room (Gymnasium) the largest
    rooms[0].room_name = "Gymnasium"
    rooms[0].area_sf = 7140.0

    room_program = InstitutionalRoomProgramResult(
        rooms=rooms,
        totals=RoomProgramTotals(existing_gsf=15465.0, existing_gsf_evidence="Total 15,465 GSF"),
        confidence=0.9,
    )

    # Create extraction with authoritative dimensions
    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(building_type="institutional", evidence="Institutional"),
            dimensions=Dimensions(width=100.0, depth=80.0, height=20.0, evidence="From plans"),
        ),
        room_program=room_program,
        authoritative_dimensions=AuthoritativeDimensions(
            width=100.0, depth=80.0, height=20.0, confidence=0.95
        ),
    )

    geometry = build_institutional_geometry(analysis, extraction, settings)

    # Assertions
    assert isinstance(geometry, InstitutionalGeometryFor3D)
    assert geometry.existing_building.area_gsf > 0
    assert geometry.existing_building.dimensions["width_ft"] == 100.0
    assert geometry.existing_building.dimensions["depth_ft"] == 80.0
    assert len(geometry.room_zones) == 20

    # Check that Gymnasium (largest room) has largest bbox footprint
    gym_zone = next((z for z in geometry.room_zones if z.room_name == "Gymnasium"), None)
    assert gym_zone is not None
    gym_footprint = (
        (gym_zone.bbox["max"]["x"] - gym_zone.bbox["min"]["x"])
        * (gym_zone.bbox["max"]["y"] - gym_zone.bbox["min"]["y"])
    )

    for zone in geometry.room_zones:
        if zone.room_name != "Gymnasium":
            zone_footprint = (
                (zone.bbox["max"]["x"] - zone.bbox["min"]["x"])
                * (zone.bbox["max"]["y"] - zone.bbox["min"]["y"])
            )
            assert gym_footprint >= zone_footprint, "Gymnasium should have largest footprint"

    assert geometry.geometry_quality in ["authoritative", "partial"]


def test_build_geometry_without_dims_but_with_totals(
    settings: Settings, analysis: DocumentAnalysis
) -> None:
    """Test geometry builder without dims but with totals produces derived_from_area masses."""
    room_program = InstitutionalRoomProgramResult(
        rooms=[],
        totals=RoomProgramTotals(existing_gsf=15465.0, existing_gsf_evidence="Total 15,465 GSF"),
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(building_type="institutional", evidence="Institutional"),
            dimensions=None,
        ),
        room_program=room_program,
        authoritative_dimensions=None,
    )

    geometry = build_institutional_geometry(analysis, extraction, settings)

    # Should derive dimensions from area
    assert geometry.existing_building.area_gsf == 15465.0
    assert geometry.existing_building.dimensions["width_ft"] is not None
    assert geometry.existing_building.dimensions["depth_ft"] is not None
    assert geometry.geometry_quality == "derived_from_area"
    assert "footprint_dimensions_derived_from_area" in geometry.missing_evidence


def test_build_geometry_with_addition(
    settings: Settings, analysis: DocumentAnalysis
) -> None:
    """Test geometry builder creates addition mass when addition GSF exists."""
    room_program = InstitutionalRoomProgramResult(
        rooms=[],
        totals=RoomProgramTotals(
            existing_gsf=15465.0,
            addition_gsf=1142.0,
            existing_gsf_evidence="Total 15,465 GSF",
            addition_gsf_evidence="Addition 1,142 GSF",
        ),
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="addition",
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(building_type="institutional", evidence="Institutional"),
            dimensions=Dimensions(width=100.0, depth=80.0, height=20.0, evidence="From plans"),
        ),
        room_program=room_program,
        authoritative_dimensions=AuthoritativeDimensions(
            width=100.0, depth=80.0, height=20.0, confidence=0.95
        ),
    )

    geometry = build_institutional_geometry(analysis, extraction, settings)

    assert geometry.addition_building is not None
    assert geometry.addition_building.area_gsf == 1142.0
    assert geometry.addition_building.label == "addition"
    assert geometry.addition_building.placement["relation"] == "adjacent_unknown"


def test_largest_room_is_largest_bbox_footprint(
    settings: Settings, analysis: DocumentAnalysis
) -> None:
    """Test that largest room by area has largest bbox footprint."""
    rooms = [
        RoomItem(room_name="Small Room", area_sf=500.0, page_number=1, evidence_snippet="Small"),
        RoomItem(room_name="Medium Room", area_sf=1000.0, page_number=1, evidence_snippet="Medium"),
        RoomItem(room_name="Gymnasium", area_sf=7140.0, page_number=1, evidence_snippet="Gymnasium"),
    ]

    room_program = InstitutionalRoomProgramResult(
        rooms=rooms,
        totals=RoomProgramTotals(existing_gsf=8640.0),
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(building_type="institutional", evidence="Institutional"),
            dimensions=Dimensions(width=100.0, depth=80.0, height=20.0, evidence="From plans"),
        ),
        room_program=room_program,
        authoritative_dimensions=AuthoritativeDimensions(
            width=100.0, depth=80.0, height=20.0, confidence=0.95
        ),
    )

    geometry = build_institutional_geometry(analysis, extraction, settings)

    # Find largest room by area
    largest_room = max(geometry.room_zones, key=lambda z: z.area_sf)
    assert largest_room.room_name == "Gymnasium"

    # Check footprint
    largest_footprint = (
        (largest_room.bbox["max"]["x"] - largest_room.bbox["min"]["x"])
        * (largest_room.bbox["max"]["y"] - largest_room.bbox["min"]["y"])
    )

    for zone in geometry.room_zones:
        if zone.room_name != "Gymnasium":
            zone_footprint = (
                (zone.bbox["max"]["x"] - zone.bbox["min"]["x"])
                * (zone.bbox["max"]["y"] - zone.bbox["min"]["y"])
            )
            assert largest_footprint >= zone_footprint

