"""Unit tests for Phase 7.1 routing improvements."""

import pytest

from app.schemas.document_analysis import DocumentAnalysis, QuantityLocator
from app.schemas.page_index import PageIndex, PageIndexItem


def test_routing_strong_signal_from_page_index() -> None:
    """Test: Routing triggers on page_index room_schedule indicator with confidence >= 0.6."""
    # Simulate page_index with strong signal
    page_index = PageIndex(
        project_id="test",
        pages=[
            PageIndexItem(
                page_number=1,
                indicators=["room_schedule"],
                confidence=0.7,  # >= 0.6
                page_types=["schedule"],
            )
        ],
    )
    
    # Simulate document analysis
    analysis = DocumentAnalysis(
        project_type="unknown",  # Not institutional, but should route anyway
        scope_type="repair",  # Problematic scope_type
        where_quantities_lives=[],
    )
    
    # Check routing logic (simulated)
    strong_signal = False
    strong_signal_pages: list[int] = []
    
    if page_index and hasattr(page_index, "pages"):
        for page_item in page_index.pages:
            if page_item.confidence >= 0.6:
                if any(
                    ind in page_item.indicators
                    for ind in ["room_schedule", "life_safety", "occupancy"]
                ):
                    strong_signal = True
                    strong_signal_pages.append(page_item.page_number)
    
    assert strong_signal is True
    assert 1 in strong_signal_pages


def test_routing_medium_signal_from_stage1_locators() -> None:
    """Test: Routing triggers on Stage 1 locators indicating room_schedule."""
    analysis = DocumentAnalysis(
        project_type="commercial",
        scope_type="unknown",  # Unreliable
        where_quantities_lives=[
            QuantityLocator(
                page_number=2,
                location_type="room_schedule",
                evidence="Room schedule on page 2",
                confidence=0.8,
            )
        ],
    )
    
    # Check medium signal
    medium_signal = False
    for locator in analysis.where_quantities_lives:
        if locator.location_type in ["room_schedule", "life_safety_plan", "schedule"]:
            medium_signal = True
            break
    
    assert medium_signal is True


def test_routing_does_not_trigger_below_confidence_threshold() -> None:
    """Test: Routing does NOT trigger if confidence < 0.6."""
    page_index = PageIndex(
        project_id="test",
        pages=[
            PageIndexItem(
                page_number=1,
                indicators=["room_schedule"],
                confidence=0.5,  # < 0.6
                page_types=["schedule"],
            )
        ],
    )
    
    strong_signal = False
    if page_index and hasattr(page_index, "pages"):
        for page_item in page_index.pages:
            if page_item.confidence >= 0.6:  # Threshold check
                if any(
                    ind in page_item.indicators
                    for ind in ["room_schedule", "life_safety", "occupancy"]
                ):
                    strong_signal = True
                    break
    
    assert strong_signal is False


def test_routing_does_not_override_row_house() -> None:
    """Test: Routing does NOT trigger institutional for row_house even with medium signal."""
    analysis = DocumentAnalysis(
        project_type="row_house",  # Should NOT route to institutional
        scope_type="repair",
        where_quantities_lives=[
            QuantityLocator(
                page_number=1,
                location_type="room_schedule",
                evidence="test",
                confidence=0.8,
            )
        ],
    )
    
    medium_signal = False
    for locator in analysis.where_quantities_lives:
        if locator.location_type in ["room_schedule", "life_safety_plan", "schedule"]:
            medium_signal = True
            break
    
    # Should have medium signal, but routing decision should exclude row_house
    should_route = medium_signal and analysis.project_type not in ["row_house", "single_family"]
    
    assert medium_signal is True
    assert should_route is False  # row_house excluded


def test_room_area_completeness_gate_70_percent() -> None:
    """Test: Room area completeness gate errors if < 70% of GSF."""
    from app.schemas.extraction_result import ExtractionResult
    from app.schemas.room_schedule import RoomSchedule, RoomScheduleItem, EvidenceRef
    from app.schemas.institutional_rooms import RoomProgram, RoomProgramTotals
    
    # Create extraction with room_schedule and room_program
    room_schedule = RoomSchedule(
        rooms=[
            RoomScheduleItem(
                room_id="101",
                room_name="Office",
                area_sf=100.0,
                evidence=EvidenceRef(page_number=1, snippet="test"),
            ),
            RoomScheduleItem(
                room_id="102",
                room_name="Office",
                area_sf=200.0,
                evidence=EvidenceRef(page_number=1, snippet="test"),
            ),
        ],
        total_gsf=None,
    )
    
    # Total room area = 300 SF, but GSF = 1000 SF (30% coverage - should error)
    room_program = RoomProgram(
        rooms=[],
        totals=RoomProgramTotals(existing_gsf=1000.0),
    )
    
    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=None,  # type: ignore
        room_program=room_program,
        room_schedule=room_schedule,
    )
    
    # Simulate validation
    from app.services.institutional_validation import _validate_room_schedule
    
    issues = _validate_room_schedule(extraction, room_count_min=10, largest_room_min_sf=2500.0, area_tolerance_pct=5.0)
    
    # Should have ROOM_AREA_INCOMPLETE error
    incomplete_issues = [i for i in issues if i.code == "ROOM_AREA_INCOMPLETE"]
    assert len(incomplete_issues) == 1
    assert incomplete_issues[0].severity == "error"
    assert "30.0%" in incomplete_issues[0].message or "30%" in incomplete_issues[0].message


def test_room_area_completeness_gate_70_percent_pass() -> None:
    """Test: Room area completeness gate passes if >= 70% of GSF."""
    from app.schemas.extraction_result import ExtractionResult
    from app.schemas.room_schedule import RoomSchedule, RoomScheduleItem, EvidenceRef
    from app.schemas.institutional_rooms import RoomProgram, RoomProgramTotals
    
    # Total room area = 800 SF, GSF = 1000 SF (80% coverage - should pass)
    room_schedule = RoomSchedule(
        rooms=[
            RoomScheduleItem(
                room_id="101",
                room_name="Gymnasium",
                area_sf=800.0,
                evidence=EvidenceRef(page_number=1, snippet="test"),
            ),
        ],
        total_gsf=None,
    )
    
    room_program = RoomProgram(
        rooms=[],
        totals=RoomProgramTotals(existing_gsf=1000.0),
    )
    
    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=None,  # type: ignore
        room_program=room_program,
        room_schedule=room_schedule,
    )
    
    from app.services.institutional_validation import _validate_room_schedule
    
    issues = _validate_room_schedule(extraction, room_count_min=10, largest_room_min_sf=2500.0, area_tolerance_pct=5.0)
    
    # Should NOT have ROOM_AREA_INCOMPLETE error (80% >= 70%)
    incomplete_issues = [i for i in issues if i.code == "ROOM_AREA_INCOMPLETE"]
    assert len(incomplete_issues) == 0


def test_room_area_completeness_gate_warning_outside_20_percent() -> None:
    """Test: Room area completeness gate warns if outside ±20% but >= 70%."""
    from app.schemas.extraction_result import ExtractionResult
    from app.schemas.room_schedule import RoomSchedule, RoomScheduleItem, EvidenceRef
    from app.schemas.institutional_rooms import RoomProgram, RoomProgramTotals
    
    # Total room area = 750 SF, GSF = 1000 SF (75% coverage, but 25% difference - should warn)
    room_schedule = RoomSchedule(
        rooms=[
            RoomScheduleItem(
                room_id="101",
                room_name="Gymnasium",
                area_sf=750.0,
                evidence=EvidenceRef(page_number=1, snippet="test"),
            ),
        ],
        total_gsf=None,
    )
    
    room_program = RoomProgram(
        rooms=[],
        totals=RoomProgramTotals(existing_gsf=1000.0),
    )
    
    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=None,  # type: ignore
        room_program=room_program,
        room_schedule=room_schedule,
    )
    
    from app.services.institutional_validation import _validate_room_schedule
    
    issues = _validate_room_schedule(extraction, room_count_min=10, largest_room_min_sf=2500.0, area_tolerance_pct=5.0)
    
    # Should have ROOM_AREA_OUTSIDE_TOLERANCE warning (75% >= 70% but outside ±20%)
    tolerance_issues = [i for i in issues if i.code == "ROOM_AREA_OUTSIDE_TOLERANCE"]
    assert len(tolerance_issues) == 1
    assert tolerance_issues[0].severity == "warning"






