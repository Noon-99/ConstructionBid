"""Golden tests for institutional PDF extraction (Phase 4.4).

Ensures contractor-critical outputs remain stable when changes are made.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.analyzers.institutional_room_extractor import InstitutionalRoomExtractor
from app.analyzers.structural_notes_extractor import StructuralNotesExtractor
from app.core.config import Settings
from app.core.ids import generate_project_id
from app.core.logging import configure_logging
from app.models.schemas import DocumentBundle
from app.services.openai_client import OpenAIClient
from app.services.page_indexer import PageIndexer
from app.services.pipeline import PipelineOrchestrator
from app.services.storage import StorageService
from app.utils.pdf_images import pdf_to_images


# Golden test fixtures directory
GOLDEN_FIXTURES_DIR = Path(__file__).parent / "golden" / "fixtures"
GOLDEN_EXPECTATIONS_DIR = Path(__file__).parent / "golden" / "expectations"
OUTPUT_DIR = Path(__file__).parent.parent / "out" / "test_runs"


def load_expectations(project_name: str) -> dict[str, Any]:
    """Load expectations JSON for a project."""
    expectations_file = GOLDEN_EXPECTATIONS_DIR / f"{project_name}.expectations.json"
    if not expectations_file.exists():
        raise FileNotFoundError(
            f"Expectations file not found: {expectations_file}. "
            f"Create it based on the template in {GOLDEN_EXPECTATIONS_DIR}"
        )
    
    with open(expectations_file, "r") as f:
        return json.load(f)


def find_room_matching(
    rooms: list[dict[str, Any]], room_name_contains: str, min_area_sf: float
) -> bool:
    """Check if a room matching the criteria exists."""
    room_name_lower = room_name_contains.lower()
    for room in rooms:
        room_name = room.get("room_name", "").lower()
        area_sf = room.get("area_sf")
        
        if room_name_lower in room_name:
            if area_sf is not None and area_sf >= min_area_sf:
                return True
    return False


def get_nested_field(data: dict[str, Any], path: str) -> Any:
    """Get a nested field using dot-path notation (e.g., 'steel_specs[0].w_shapes')."""
    parts = path.split(".")
    current = data
    
    for part in parts:
        if "[" in part and "]" in part:
            # Handle array access like "steel_specs[0]"
            field_name = part[: part.index("[")]
            index_str = part[part.index("[") + 1 : part.index("]")]
            index = int(index_str)
            
            if field_name:
                current = current.get(field_name, [])
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]
        else:
            current = current.get(part)
            if current is None:
                return None
    
    return current


def check_code_compliance(
    code_compliance: list[dict[str, Any]], required_code: str
) -> bool:
    """Check if a required code is found in code_compliance."""
    required_lower = required_code.lower()
    for code_ref in code_compliance:
        code_name = code_ref.get("code_name", "").lower()
        if required_lower in code_name:
            return True
    return False


@pytest.fixture
def golden_settings() -> Settings:
    """Create settings for golden tests with cache enabled and deterministic temperature."""
    return Settings(
        openai_api_key="test-key",  # Will be overridden by actual env var
        openai_temperature=0.0,  # Deterministic
        openai_model="gpt-4o-mini",
        llm_cache_enabled=True,  # Use cache for stability
        institutional_room_count_min=15,
        institutional_largest_room_min_sf=2500.0,
        institutional_room_area_tolerance_pct=5.0,
    )


@pytest.fixture
def output_base_dir() -> Path:
    """Get output directory for test runs."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


@pytest.mark.golden
@pytest.mark.integration
def test_golden_recreation_center(
    golden_settings: Settings, output_base_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Golden test for recreation center institutional project.
    
    Runs full pipeline (0.5 → 1 → 1.5 → 2 → 2.5) and asserts contractor-critical
    outputs match expectations.
    """
    # Load expectations
    expectations = load_expectations("recreation_center")
    project_name = expectations["project_name"]
    
    # Find fixture PDF
    fixture_pdf = GOLDEN_FIXTURES_DIR / f"{project_name}.pdf"
    if not fixture_pdf.exists():
        pytest.skip(
            f"Fixture PDF not found: {fixture_pdf}. "
            f"Place a test PDF at this location to run golden test."
        )
    
    # Configure logging
    configure_logging(golden_settings)
    
    # Generate project ID for this test run
    project_id = f"golden-{project_name}-{generate_project_id()}"
    project_output_dir = output_base_dir / project_id
    project_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Override storage root for test
    golden_settings.storage_root = project_output_dir / "storage"
    
    try:
        # Initialize services
        storage_service = StorageService(golden_settings)
        openai_client = OpenAIClient(golden_settings)
        document_analyzer = DocumentAnalyzer(golden_settings, openai_client)
        institutional_room_extractor = InstitutionalRoomExtractor(
            golden_settings, openai_client
        )
        structural_notes_extractor = StructuralNotesExtractor(
            golden_settings, openai_client
        )
        page_indexer = PageIndexer(golden_settings, openai_client)
        
        pipeline = PipelineOrchestrator(
            document_analyzer=document_analyzer,
            institutional_room_extractor=institutional_room_extractor,
            structural_notes_extractor=structural_notes_extractor,
            page_indexer=page_indexer,
            settings=golden_settings,
        )
        
        # Convert PDF to images
        pdf_images = pdf_to_images(fixture_pdf, golden_settings, project_id)
        
        # Create document bundle
        document_bundle = DocumentBundle(
            project_id=project_id,
            source_pdf_path=fixture_pdf,
            page_image_paths=[img.path for img in pdf_images],
        )
        
        # Run full pipeline (0.5 → 1 → 1.5 → 2 → 2.5)
        project_result = pipeline.run_full_pipeline(project_id, document_bundle)
        
        # Save outputs for inspection
        output_file = project_output_dir / "project_result.json"
        with open(output_file, "w") as f:
            f.write(project_result.model_dump_json(indent=2))
        
        # Extract results
        extraction = project_result.extraction
        validation_report = project_result.validation
        
        # Assertions
        
        # 1) Validation must pass
        validation_req = expectations.get("validation_requirements", {})
        if validation_req.get("must_pass", True):
            assert validation_report.passed, (
                f"Validation failed. Errors: {[i.message for i in validation_report.issues if i.severity == 'error']}"
            )
        
        max_errors = validation_req.get("max_errors", 0)
        error_count = sum(1 for i in validation_report.issues if i.severity == "error")
        assert error_count <= max_errors, (
            f"Too many validation errors: {error_count} > {max_errors}. "
            f"Issues: {[i.message for i in validation_report.issues if i.severity == 'error']}"
        )
        
        # 2) Room program assertions
        assert extraction.room_program is not None, "Room program is missing"
        room_program = extraction.room_program.model_dump()
        rooms = room_program.get("rooms", [])
        
        # Min room count
        min_room_count = expectations.get("min_room_count", 0)
        assert len(rooms) >= min_room_count, (
            f"Room count {len(rooms)} is below minimum {min_room_count}"
        )
        
        # Required rooms
        required_rooms = expectations.get("required_rooms", [])
        missing_rooms = []
        for req_room in required_rooms:
            room_name_contains = req_room["room_name_contains"]
            min_area_sf = req_room["min_area_sf"]
            
            if not find_room_matching(rooms, room_name_contains, min_area_sf):
                missing_rooms.append(
                    f"{room_name_contains} (min {min_area_sf} SF)"
                )
        
        assert len(missing_rooms) == 0, (
            f"Missing required rooms: {', '.join(missing_rooms)}"
        )
        
        # Totals validation
        totals_expectations = expectations.get("totals", {})
        if totals_expectations:
            room_totals = room_program.get("totals", {})
            
            # Check existing_gsf
            if "existing_gsf" in totals_expectations:
                existing_gsf_exp = totals_expectations["existing_gsf"]
                if existing_gsf_exp.get("value") is not None:
                    existing_gsf_actual = room_totals.get("existing_gsf")
                    tolerance_pct = existing_gsf_exp.get("tolerance_pct", 5.0)
                    
                    if existing_gsf_actual is not None:
                        diff_pct = (
                            abs(existing_gsf_actual - existing_gsf_exp["value"])
                            / existing_gsf_exp["value"]
                            * 100
                        )
                        assert diff_pct <= tolerance_pct, (
                            f"Existing GSF mismatch: {existing_gsf_actual} vs "
                            f"{existing_gsf_exp['value']} ({diff_pct:.1f}% > {tolerance_pct}%)"
                        )
            
            # Check addition_gsf
            if "addition_gsf" in totals_expectations:
                addition_gsf_exp = totals_expectations["addition_gsf"]
                if addition_gsf_exp.get("value") is not None:
                    addition_gsf_actual = room_totals.get("addition_gsf")
                    tolerance_pct = addition_gsf_exp.get("tolerance_pct", 5.0)
                    
                    if addition_gsf_actual is not None:
                        diff_pct = (
                            abs(addition_gsf_actual - addition_gsf_exp["value"])
                            / addition_gsf_exp["value"]
                            * 100
                        )
                        assert diff_pct <= tolerance_pct, (
                            f"Addition GSF mismatch: {addition_gsf_actual} vs "
                            f"{addition_gsf_exp['value']} ({diff_pct:.1f}% > {tolerance_pct}%)"
                        )
        
        # 3) Structural notes assertions
        assert extraction.structural_notes is not None, "Structural notes are missing"
        structural_notes = extraction.structural_notes.model_dump()
        
        # Required structural fields
        required_fields = expectations.get("required_structural_fields", [])
        missing_fields = []
        for field_spec in required_fields:
            path = field_spec["path"]
            value = get_nested_field(structural_notes, path)
            
            if value is None:
                missing_fields.append(f"{path} ({field_spec.get('description', '')})")
        
        assert len(missing_fields) == 0, (
            f"Missing required structural fields: {', '.join(missing_fields)}"
        )
        
        # Required codes
        required_codes = expectations.get("required_codes", [])
        code_compliance = structural_notes.get("code_compliance", [])
        missing_codes = []
        
        for code_spec in required_codes:
            code_name_contains = code_spec["code_name_contains"]
            if not check_code_compliance(code_compliance, code_name_contains):
                missing_codes.append(
                    f"{code_name_contains} ({code_spec.get('description', '')})"
                )
        
        assert len(missing_codes) == 0, (
            f"Missing required codes: {', '.join(missing_codes)}"
        )
        
        # Test passed - log success
        print(f"\n✅ Golden test passed for {project_name}")
        print(f"   Output saved to: {project_output_dir}")
        
    except Exception as e:
        # Save error output for debugging
        error_file = project_output_dir / "test_error.txt"
        with open(error_file, "w") as f:
            f.write(f"Golden test failed: {str(e)}\n")
            import traceback
            f.write(traceback.format_exc())
        
        raise






