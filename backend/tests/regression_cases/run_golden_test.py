"""Golden test for Phase 2.6A - Acceptance Testing.

Runs full pipeline on a test PDF and asserts:
- Critical-5 coverage ≥ 4/5
- Dimension conflicts resolved
- Stage 3 and 4 run
- Validation score ≥ 0.85
- Recovery triggered appropriately
"""

import json
import sys
from pathlib import Path

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.analyzers.institutional_room_extractor import InstitutionalRoomExtractor
from app.analyzers.row_house_repair_extractor import RowHouseRepairExtractor
from app.analyzers.structural_notes_extractor import StructuralNotesExtractor
from app.core.config import Settings, get_settings
from app.core.ids import generate_project_id
from app.core.logging import configure_logging
from app.costing.cost_engine import CostEngine
from app.generators.model_3d_generator import Model3DGenerator
from app.models.schemas import DocumentBundle
from app.services.openai_client import OpenAIClient
from app.services.page_indexer import PageIndexer
from app.services.pipeline import PipelineOrchestrator
from app.utils.pdf_images import pdf_to_images


def count_critical_5_coverage(extraction) -> tuple[int, int]:
    """Count how many Critical-5 items are present in extraction."""
    scope_items_lower = [item.item.lower() for item in extraction.scope_of_work]
    
    found = {
        "parapet": any("parapet" in item for item in scope_items_lower),
        "lintel": any("lintel" in item for item in scope_items_lower),
        "flashing": any("flash" in item for item in scope_items_lower),
        "brick_or_repoint": any("brick" in item or "repoint" in item for item in scope_items_lower),
        "crack_repair": any("crack" in item or "stabil" in item or "epoxy" in item for item in scope_items_lower),
    }
    
    found_count = sum(found.values())
    return found_count, 5


def assert_golden_test(pdf_path: Path, output_dir: Path) -> dict:
    """Run golden test and return results."""
    print(f"\n{'='*80}")
    print(f"GOLDEN TEST: {pdf_path.name}")
    print(f"{'='*80}\n")
    
    # Initialize
    settings = get_settings()
    configure_logging(settings)
    
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY must be set")
    
    project_id = generate_project_id()
    project_output_dir = output_dir / project_id
    project_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize services
    openai_client = OpenAIClient(settings)
    document_analyzer = DocumentAnalyzer(settings, openai_client)
    row_house_extractor = RowHouseRepairExtractor(settings, openai_client)
    institutional_room_extractor = InstitutionalRoomExtractor(settings, openai_client)
    structural_notes_extractor = StructuralNotesExtractor(settings, openai_client)
    model_3d_generator = Model3DGenerator()
    cost_engine = CostEngine()
    page_indexer = PageIndexer(settings, openai_client)
    
    pipeline = PipelineOrchestrator(
        document_analyzer=document_analyzer,
        row_house_extractor=row_house_extractor,
        institutional_room_extractor=institutional_room_extractor,
        structural_notes_extractor=structural_notes_extractor,
        model_3d_generator=model_3d_generator,
        cost_engine=cost_engine,
        page_indexer=page_indexer,
        settings=settings,
    )
    
    # Create document bundle (this handles PDF to images conversion)
    from app.services.document_processor import DocumentProcessor
    from app.services.storage import StorageService
    
    storage_service = StorageService(settings)
    doc_processor = DocumentProcessor(settings, storage_service)
    document_bundle = doc_processor.process_pdf(project_id, pdf_path)
    
    # Run full pipeline
    print("Running full pipeline...")
    result = pipeline.run_full_pipeline(project_id, document_bundle)
    
    # Load validation report
    validation_report_path = project_output_dir / "validation_report.json"
    if not validation_report_path.exists():
        raise AssertionError(f"validation_report.json not found at {validation_report_path}")
    
    with open(validation_report_path, "r") as f:
        validation_report = json.load(f)
    
    # Assertions
    assertions = {
        "passed": False,
        "errors": [],
        "warnings": [],
        "metrics": {},
    }
    
    # 1. Critical-5 coverage ≥ 4/5
    found_count, total = count_critical_5_coverage(result.extraction)
    coverage_ratio = found_count / total
    assertions["metrics"]["critical_5_coverage"] = f"{found_count}/{total}"
    assertions["metrics"]["critical_5_ratio"] = coverage_ratio
    
    if coverage_ratio < 0.8:  # 4/5 = 0.8
        assertions["errors"].append(
            f"Critical-5 coverage too low: {found_count}/{total} ({coverage_ratio:.2%}) < 80%"
        )
    else:
        print(f"✅ Critical-5 coverage: {found_count}/{total} ({coverage_ratio:.2%})")
    
    # 2. Dimension conflicts resolved
    if result.extraction.authoritative_dimensions:
        auth_dims = result.extraction.authoritative_dimensions
        has_conflicts = len(auth_dims.conflicts) > 0
        has_dimensions = (
            auth_dims.width is not None
            and auth_dims.depth is not None
            and auth_dims.height is not None
        )
        
        assertions["metrics"]["authoritative_dimensions"] = {
            "width": auth_dims.width,
            "depth": auth_dims.depth,
            "height": auth_dims.height,
            "confidence": auth_dims.confidence,
            "conflicts_resolved": len(auth_dims.conflicts),
        }
        
        if not has_dimensions:
            assertions["errors"].append("Authoritative dimensions missing (width/depth/height)")
        else:
            print(f"✅ Authoritative dimensions resolved: width={auth_dims.width}, depth={auth_dims.depth}, height={auth_dims.height}")
            if has_conflicts:
                print(f"   (Resolved {len(auth_dims.conflicts)} conflicts)")
    else:
        assertions["warnings"].append("No authoritative dimensions found")
    
    # 3. Stage 3 and 4 ran
    assertions["metrics"]["stage_3_ran"] = result.model_3d is not None
    assertions["metrics"]["stage_4_ran"] = result.costing_result is not None
    
    if not result.model_3d:
        assertions["errors"].append("Stage 3 (3D model generation) did not run")
    else:
        print(f"✅ Stage 3 ran: {len(result.model_3d.buildings)} buildings, {len(result.model_3d.work_zones)} work zones")
    
    if not result.costing_result:
        assertions["errors"].append("Stage 4 (costing) did not run")
    else:
        print(f"✅ Stage 4 ran: Total cost = ${result.costing_result.total_cost:,.2f}")
    
    # 4. Validation score ≥ 0.85
    validation_score = validation_report.get("score", 0.0)
    assertions["metrics"]["validation_score"] = validation_score
    
    if validation_score < 0.85:
        assertions["errors"].append(
            f"Validation score too low: {validation_score:.2f} < 0.85"
        )
    else:
        print(f"✅ Validation score: {validation_score:.2f}")
    
    # 5. Recovery triggered appropriately
    rerun_performed = validation_report.get("rerun_performed", False)
    rerun_notes = validation_report.get("rerun_notes", [])
    
    assertions["metrics"]["rerun_performed"] = rerun_performed
    assertions["metrics"]["rerun_notes"] = rerun_notes
    
    if rerun_performed:
        # Check that recovery was reasonable (max 4 pages mentioned)
        pages_mentioned = False
        for note in rerun_notes:
            if "pages" in note.lower():
                pages_mentioned = True
                # Extract page count if mentioned
                import re
                page_matches = re.findall(r'(\d+)\s*pages?', note.lower())
                if page_matches:
                    page_count = int(page_matches[0])
                    if page_count > 4:
                        assertions["warnings"].append(
                            f"Recovery used {page_count} pages (expected ≤4)"
                        )
        
        print(f"✅ Recovery triggered: {len(rerun_notes)} note(s)")
        for note in rerun_notes:
            print(f"   - {note}")
    else:
        print("✅ No recovery needed (all items found on first pass)")
    
    # 6. Validation passed
    validation_passed = validation_report.get("passed", False)
    assertions["metrics"]["validation_passed"] = validation_passed
    
    if not validation_passed:
        error_count = len([i for i in validation_report.get("issues", []) if i.get("severity") == "error"])
        assertions["errors"].append(
            f"Validation failed with {error_count} error(s)"
        )
    else:
        print(f"✅ Validation passed")
    
    # Final result
    assertions["passed"] = len(assertions["errors"]) == 0
    
    # Save results
    results_path = project_output_dir / "golden_test_results.json"
    with open(results_path, "w") as f:
        json.dump(assertions, f, indent=2)
    
    print(f"\n{'='*80}")
    if assertions["passed"]:
        print("✅ GOLDEN TEST PASSED")
    else:
        print("❌ GOLDEN TEST FAILED")
        print(f"Errors: {len(assertions['errors'])}")
        for error in assertions["errors"]:
            print(f"  - {error}")
    if assertions["warnings"]:
        print(f"Warnings: {len(assertions['warnings'])}")
        for warning in assertions["warnings"]:
            print(f"  - {warning}")
    print(f"{'='*80}\n")
    
    return assertions


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_golden_test.py <path_to_pdf> [output_dir]")
        sys.exit(1)
    
    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)
    
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("./out")
    
    try:
        results = assert_golden_test(pdf_path, output_dir)
        sys.exit(0 if results["passed"] else 1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

