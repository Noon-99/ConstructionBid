"""CLI script to run Stage 1 -> 1.5 -> Stage 2 extraction on a PDF."""

import argparse
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
from app.services.openai_client import OpenAIClient
from app.services.page_indexer import PageIndexer
from app.services.pipeline import PipelineOrchestrator
from app.services.storage import StorageService
from app.utils.pdf_images import pdf_to_images


def main() -> None:
    """CLI entry point for Stage 2 extraction."""
    parser = argparse.ArgumentParser(
        description="Run Stage 1 -> 1.5 -> Stage 2 extraction on a PDF file"
    )
    parser.add_argument(
        "input_path",
        type=str,
        nargs="?",
        help="Path to PDF file to analyze",
    )
    parser.add_argument(
        "--pdf",
        type=str,
        help="[Deprecated] Use positional argument instead",
    )
    parser.add_argument(
        "--project-id",
        type=str,
        default=None,
        help="Optional project ID (generated if not provided)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./out",
        help="Output directory for results (default: ./out)",
    )

    args = parser.parse_args()

    # Initialize settings and logging
    settings = get_settings()
    configure_logging(settings)

    if not settings.openai_api_key:
        print("Error: OPENAI_API_KEY must be set in environment or .env file", file=sys.stderr)
        sys.exit(1)

    # Support both positional argument and --pdf flag
    input_path_str = args.input_path or args.pdf
    if not input_path_str:
        parser.print_help()
        print("\nError: Must provide PDF file path", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(input_path_str)
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    if pdf_path.suffix.lower() != ".pdf":
        print(f"Error: File must be a PDF: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    project_id = args.project_id or generate_project_id()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    project_output_dir = output_dir / project_id
    project_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        print(f"\n{'='*80}")
        print(f"Processing: {pdf_path.name}")
        print(f"{'='*80}")

        # Initialize services
        storage_service = StorageService(settings)
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

        # Convert PDF to images
        print("Converting PDF to images...")
        pdf_images = pdf_to_images(pdf_path, settings, project_id)

        # Create document bundle
        from app.models.schemas import DocumentBundle

        document_bundle = DocumentBundle(
            project_id=project_id,
            source_pdf_path=pdf_path,
            page_count=len(pdf_images),
            page_image_paths=[],  # Not needed for pipeline
        )

        # Run full pipeline (Stage 1 -> 1.5 -> Stage 2)
        print("Running pipeline: Stage 1 -> 1.5 -> Stage 2...")
        project_result = pipeline.run_full_pipeline(project_id, document_bundle)

        # Save results
        analysis_file = project_output_dir / "document_analysis.json"
        with open(analysis_file, "w") as f:
            f.write(project_result.document_analysis.model_dump_json(indent=2))

        extraction_file = project_output_dir / "extraction_result.json"
        with open(extraction_file, "w") as f:
            f.write(project_result.extraction.model_dump_json(indent=2))

        # Save 3D model if generated
        if project_result.model_3d:
            model_3d_file = project_output_dir / "model_3d.json"
            with open(model_3d_file, "w") as f:
                f.write(project_result.model_3d.model_dump_json(indent=2))

        # Save costing result if generated
        if project_result.costing_result:
            costing_file = project_output_dir / "costing_result.json"
            with open(costing_file, "w") as f:
                f.write(project_result.costing_result.model_dump_json(indent=2))

        # Print summary
        print("\n" + "=" * 80)
        print("Pipeline Complete (Stage 1 -> 1.5 -> 2 -> 3 -> 4)")
        print("=" * 80)
        print(f"Project ID: {project_id}")
        print(f"Project Type: {project_result.document_analysis.resolved_project_type or project_result.document_analysis.project_type}")
        print(f"Scope Type: {project_result.document_analysis.resolved_scope_type or project_result.document_analysis.scope_type}")
        print(f"\nExtraction:")
        print(f"  Scope Items: {len(project_result.extraction.scope_of_work)}")
        print(f"  Materials: {len(project_result.extraction.material_specifications)}")
        print(f"  Quantities: {len(project_result.extraction.quantity_takeoff)}")
        print(f"  Work Zones: {len(project_result.extraction.geometry_for_3d.work_zones)}")
        if project_result.model_3d:
            print(f"\n3D Model:")
            print(f"  Buildings: {len(project_result.model_3d.buildings)}")
            print(f"  Work Zone Volumes: {len(project_result.model_3d.work_zones)}")
            print(f"  Windows: {len(project_result.model_3d.windows)}")
        if project_result.costing_result:
            print(f"\nCosting:")
            print(f"  Total Cost: ${project_result.costing_result.total_cost:,.2f}")
            print(f"  Material: ${project_result.costing_result.material_cost_total:,.2f}")
            print(f"  Labor: ${project_result.costing_result.labor_cost_total:,.2f}")
            print(f"  Items: {len(project_result.costing_result.breakdown_by_scope_item)}")
        print(f"\n✓ Analysis saved to: {analysis_file}")
        print(f"✓ Extraction saved to: {extraction_file}")
        if project_result.model_3d:
            print(f"✓ 3D Model saved to: {model_3d_file}")
        if project_result.costing_result:
            print(f"✓ Costing saved to: {costing_file}")

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

