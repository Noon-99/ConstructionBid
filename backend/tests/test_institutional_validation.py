"""Tests for institutional validation (Phase 4.3)."""

import pytest

from app.core.config import Settings
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.schemas.institutional_rooms import (
    InstitutionalRoomProgramResult,
    RoomItem,
    RoomProgramTotals,
)
from app.schemas.structural_notes import (
    ConcreteSpec,
    DesignLoads,
    InstitutionalStructuralNotesResult,
    SteelSpec,
    SubmittalRequirement,
)
from app.services.institutional_validation import validate_institutional


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        institutional_room_count_min=15,
        institutional_largest_room_min_sf=2500.0,
        institutional_room_area_tolerance_pct=5.0,
    )


@pytest.fixture
def analysis() -> DocumentAnalysis:
    """Create test document analysis."""
    return DocumentAnalysis(
        project_type="institutional",
        scope_type="new_construction",
        confidence=0.9,
        missing_fields=[],
    )


def test_missing_room_program_fails(settings: Settings, analysis: DocumentAnalysis) -> None:
    """Test that missing room program fails validation."""
    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        room_program=None,
        structural_notes=None,
    )

    issues = validate_institutional(extraction, analysis, settings)

    assert len(issues) > 0
    assert any(i.code == "MISSING_ROOM_PROGRAM" and i.severity == "error" for i in issues)


def test_missing_structural_notes_fails(settings: Settings, analysis: DocumentAnalysis) -> None:
    """Test that missing structural notes fails validation."""
    room_program = InstitutionalRoomProgramResult(
        rooms=[RoomItem(room_name=f"Room {i}", area_sf=1000.0, page_number=1, evidence_snippet=f"Room {i}") for i in range(20)],
        totals=RoomProgramTotals(),
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        room_program=room_program,
        structural_notes=None,
    )

    issues = validate_institutional(extraction, analysis, settings)

    assert len(issues) > 0
    assert any(i.code == "MISSING_STRUCTURAL_NOTES" and i.severity == "error" for i in issues)


def test_insufficient_room_count_fails(settings: Settings, analysis: DocumentAnalysis) -> None:
    """Test that room count below minimum fails."""
    room_program = InstitutionalRoomProgramResult(
        rooms=[RoomItem(room_name=f"Room {i}", area_sf=1000.0, page_number=1, evidence_snippet=f"Room {i}") for i in range(10)],
        totals=RoomProgramTotals(),
        confidence=0.9,
    )

    structural_notes = InstitutionalStructuralNotesResult(
        concrete_specs=[ConcreteSpec(strength_psi=4000.0, page_number=1, evidence_snippet="4000 PSI")],
        design_loads=DesignLoads(roof_live_psf=50.0, page_number=1, evidence_snippet="50 psf"),
        submittals=[SubmittalRequirement(item="Mix designs", page_number=1, evidence_snippet="Mix designs")],
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        room_program=room_program,
        structural_notes=structural_notes,
    )

    issues = validate_institutional(extraction, analysis, settings)

    assert len(issues) > 0
    assert any(i.code == "INSUFFICIENT_ROOM_COUNT" and i.severity == "error" for i in issues)


def test_totals_mismatch_over_5_percent_fails(settings: Settings, analysis: DocumentAnalysis) -> None:
    """Test that totals mismatch > 5% fails."""
    # Create rooms that sum to 10000 SF, but totals say 12000 SF (20% difference)
    rooms = [
        RoomItem(room_name=f"Room {i}", area_sf=500.0, page_number=1, evidence_snippet=f"Room {i}")
        for i in range(20)
    ]  # Sum = 10000 SF

    room_program = InstitutionalRoomProgramResult(
        rooms=rooms,
        totals=RoomProgramTotals(existing_gsf=12000.0),  # 20% difference
        confidence=0.9,
    )

    structural_notes = InstitutionalStructuralNotesResult(
        concrete_specs=[ConcreteSpec(strength_psi=4000.0, page_number=1, evidence_snippet="4000 PSI")],
        design_loads=DesignLoads(roof_live_psf=50.0, page_number=1, evidence_snippet="50 psf"),
        submittals=[SubmittalRequirement(item="Mix designs", page_number=1, evidence_snippet="Mix designs")],
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        room_program=room_program,
        structural_notes=structural_notes,
    )

    issues = validate_institutional(extraction, analysis, settings)

    assert len(issues) > 0
    assert any(i.code == "ROOM_SUM_MISMATCH" and i.severity == "error" for i in issues)


def test_largest_room_too_small_fails(settings: Settings, analysis: DocumentAnalysis) -> None:
    """Test that largest room below minimum fails."""
    rooms = [
        RoomItem(room_name=f"Room {i}", area_sf=1000.0, page_number=1, evidence_snippet=f"Room {i}")
        for i in range(20)
    ]  # All rooms 1000 SF, max is 1000 < 2500

    room_program = InstitutionalRoomProgramResult(
        rooms=rooms,
        totals=RoomProgramTotals(),
        confidence=0.9,
    )

    structural_notes = InstitutionalStructuralNotesResult(
        concrete_specs=[ConcreteSpec(strength_psi=4000.0, page_number=1, evidence_snippet="4000 PSI")],
        design_loads=DesignLoads(roof_live_psf=50.0, page_number=1, evidence_snippet="50 psf"),
        submittals=[SubmittalRequirement(item="Mix designs", page_number=1, evidence_snippet="Mix designs")],
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        room_program=room_program,
        structural_notes=structural_notes,
    )

    issues = validate_institutional(extraction, analysis, settings)

    assert len(issues) > 0
    assert any(i.code == "LARGEST_ROOM_TOO_SMALL" and i.severity == "error" for i in issues)


def test_passing_case_no_issues(settings: Settings, analysis: DocumentAnalysis) -> None:
    """Test that a passing case produces no errors."""
    # Create valid room program: 20 rooms, largest >= 2500 SF, totals match
    rooms = [
        RoomItem(room_name=f"Room {i}", area_sf=1000.0, page_number=1, evidence_snippet=f"Room {i}")
        for i in range(19)
    ]
    rooms.append(
        RoomItem(room_name="Gymnasium", area_sf=3000.0, page_number=1, evidence_snippet="Gymnasium 3000 SF")
    )  # Largest room >= 2500

    room_program = InstitutionalRoomProgramResult(
        rooms=rooms,
        totals=RoomProgramTotals(existing_gsf=22000.0),  # Sum = 22000, matches
        confidence=0.9,
    )

    structural_notes = InstitutionalStructuralNotesResult(
        concrete_specs=[ConcreteSpec(strength_psi=4000.0, page_number=1, evidence_snippet="4000 PSI")],
        design_loads=DesignLoads(roof_live_psf=50.0, page_number=1, evidence_snippet="50 psf"),
        submittals=[SubmittalRequirement(item="Mix designs", page_number=1, evidence_snippet="Mix designs")],
        inspections=[],
        code_compliance=[],
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        room_program=room_program,
        structural_notes=structural_notes,
    )

    issues = validate_institutional(extraction, analysis, settings)

    # Should only have warnings (evidence integrity), no errors
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 0


def test_missing_major_structural_spec_fails(settings: Settings, analysis: DocumentAnalysis) -> None:
    """Test that missing major structural spec fails."""
    room_program = InstitutionalRoomProgramResult(
        rooms=[RoomItem(room_name=f"Room {i}", area_sf=1000.0, page_number=1, evidence_snippet=f"Room {i}") for i in range(20)],
        totals=RoomProgramTotals(),
        confidence=0.9,
    )

    # No concrete, steel, or CMU specs
    structural_notes = InstitutionalStructuralNotesResult(
        concrete_specs=[],
        steel_specs=[],
        cmu_specs=[],
        design_loads=DesignLoads(roof_live_psf=50.0, page_number=1, evidence_snippet="50 psf"),
        submittals=[SubmittalRequirement(item="Mix designs", page_number=1, evidence_snippet="Mix designs")],
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        room_program=room_program,
        structural_notes=structural_notes,
    )

    issues = validate_institutional(extraction, analysis, settings)

    assert len(issues) > 0
    assert any(i.code == "MISSING_MAJOR_STRUCTURAL_SPEC" and i.severity == "error" for i in issues)


def test_incomplete_contractor_readiness_fails(settings: Settings, analysis: DocumentAnalysis) -> None:
    """Test that incomplete contractor readiness fails."""
    room_program = InstitutionalRoomProgramResult(
        rooms=[RoomItem(room_name=f"Room {i}", area_sf=1000.0, page_number=1, evidence_snippet=f"Room {i}") for i in range(20)],
        totals=RoomProgramTotals(),
        confidence=0.9,
    )

    # Only has loads, missing submittals/inspections/codes (only 1/4)
    structural_notes = InstitutionalStructuralNotesResult(
        concrete_specs=[ConcreteSpec(strength_psi=4000.0, page_number=1, evidence_snippet="4000 PSI")],
        design_loads=DesignLoads(roof_live_psf=50.0, page_number=1, evidence_snippet="50 psf"),
        submittals=[],
        inspections=[],
        code_compliance=[],
        confidence=0.9,
    )

    extraction = ExtractionResult(
        project_type="institutional",
        scope_type="new_construction",
        room_program=room_program,
        structural_notes=structural_notes,
    )

    issues = validate_institutional(extraction, analysis, settings)

    assert len(issues) > 0
    assert any(i.code == "INCOMPLETE_CONTRACTOR_READINESS" and i.severity == "error" for i in issues)






