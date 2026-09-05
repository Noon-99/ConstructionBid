#!/usr/bin/env python3
"""CLI script to run institutional room extraction (Phase 7.1 proof runner).

Dev-only tool to test Phase 7.1 institutional extraction path.
Supports forcing institutional extractor for testing.
"""

import argparse
import json
import sys
from pathlib import Path

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.analyzers.institutional_room_extractor import InstitutionalRoomExtractor
from app.analyzers.row_house_repair_extractor import RowHouseRepairExtractor
from app.analyzers.structural_notes_extractor import StructuralNotesExtractor
from app.analyzers.structural_elements_extractor import StructuralElementsExtractor
from app.analyzers.building_envelope_extractor import BuildingEnvelopeExtractor
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
    """CLI entry point for institutional room extraction."""
    parser = argparse.ArgumentParser(
        description="Run institutional room extraction (Phase 7.1 proof runner)"
    )
    parser.add_argument(
        "pdf_path",
        type=str,
        help="Path to PDF file to analyze",
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
    parser.add_argument(
        "--force-project-type",
        type=str,
        choices=["institutional", "commercial"],
        default=None,
        help="Force project type for testing (dev-only)",
    )
    parser.add_argument(
        "--force-use-institutional-extractor",
        action="store_true",
        help="Force use of institutional extractor regardless of routing (dev-only)",
    )

    args = parser.parse_args()

    # Initialize settings and logging
    settings = get_settings()
    configure_logging(settings)

    if not settings.openai_api_key:
        print("Error: OPENAI_API_KEY must be set in environment or .env file", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(args.pdf_path)
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
        print(f"Institutional Room Extraction Test (Phase 7.1)")
        print(f"{'='*80}")
        print(f"PDF: {pdf_path.name}")
        print(f"Project ID: {project_id}")
        if args.force_project_type:
            print(f"⚠️  FORCED project type: {args.force_project_type}")
        if args.force_use_institutional_extractor:
            print(f"⚠️  FORCED institutional extractor (dev-only)")
        print(f"{'='*80}\n")

        # Initialize services
        storage_service = StorageService(settings)
        openai_client = OpenAIClient(settings)
        document_analyzer = DocumentAnalyzer(settings, openai_client)
        row_house_extractor = RowHouseRepairExtractor(settings, openai_client)
        institutional_room_extractor = InstitutionalRoomExtractor(settings, openai_client)
        structural_notes_extractor = StructuralNotesExtractor(settings, openai_client)
        structural_elements_extractor = StructuralElementsExtractor(settings, openai_client)
        building_envelope_extractor = BuildingEnvelopeExtractor(settings, openai_client)
        model_3d_generator = Model3DGenerator()
        cost_engine = CostEngine()
        page_indexer = PageIndexer(settings, openai_client)
        pipeline = PipelineOrchestrator(
            document_analyzer=document_analyzer,
            row_house_extractor=row_house_extractor,
            institutional_room_extractor=institutional_room_extractor,
            structural_notes_extractor=structural_notes_extractor,
            structural_elements_extractor=structural_elements_extractor,
            building_envelope_extractor=building_envelope_extractor,
            model_3d_generator=model_3d_generator,
            cost_engine=cost_engine,
            page_indexer=page_indexer,
            settings=settings,
        )

        # Process PDF
        print("Processing PDF...")
        from app.services.document_processor import DocumentProcessor
        document_processor = DocumentProcessor(settings, storage_service)
        document_bundle = document_processor.process_pdf(project_id, pdf_path)

        # Run pipeline stages
        print("\nRunning pipeline stages...")
        project_result = pipeline.run_full_pipeline(project_id, document_bundle)

        # If forcing, override extraction result
        if args.force_use_institutional_extractor or args.force_project_type:
            print("\n⚠️  Forcing institutional extraction path...")
            from app.models.schemas import DocumentBundle
            from app.schemas.document_analysis import DocumentAnalysis

            # Load document analysis
            analysis_file = project_output_dir / "document_analysis.json"
            if analysis_file.exists():
                with open(analysis_file, "r") as f:
                    analysis_data = json.load(f)
                    document_analysis = DocumentAnalysis.model_validate(analysis_data)
            else:
                print("Error: document_analysis.json not found", file=sys.stderr)
                sys.exit(1)

            # Override project type if forced
            if args.force_project_type:
                document_analysis.project_type = args.force_project_type
                document_analysis.resolved_project_type = args.force_project_type
                if document_analysis.scope_type not in ["renovation", "addition", "new_construction"]:
                    document_analysis.scope_type = "new_construction"
                    document_analysis.resolved_scope_type = "new_construction"

            # Load page index
            page_index_file = project_output_dir / "page_index.json"
            page_index = None
            if page_index_file.exists():
                with open(page_index_file, "r") as f:
                    page_index_data = json.load(f)
                    from app.schemas.page_index import PageIndex
                    page_index = PageIndex.model_validate(page_index_data)

            # Force institutional extraction
            pdf_images = pdf_to_images(pdf_path, settings, project_id)

            print("Extracting room schedule...")
            # Use extract_room_schedule method (Phase 7.1)
            room_schedule = institutional_room_extractor.extract_room_schedule(
                pdf_images=pdf_images,
                analysis=document_analysis,
                page_index=page_index,
                project_id=project_id,
            )

            # Save room schedule
            room_schedule_file = project_output_dir / "room_schedule.json"
            with open(room_schedule_file, "w") as f:
                f.write(room_schedule.model_dump_json(indent=2))
            print(f"✅ Room schedule saved to {room_schedule_file}")

        # Load and print summary
        print(f"\n{'='*80}")
        print("EXTRACTION SUMMARY")
        print(f"{'='*80}\n")

        # Load extraction result
        extraction_file = project_output_dir / "extraction_result.json"
        if extraction_file.exists():
            with open(extraction_file, "r") as f:
                extraction_data = json.load(f)
                extraction = extraction_data

            # Check for room_schedule
            room_schedule_data = extraction.get("room_schedule")
            if not room_schedule_data:
                # Try loading from separate file
                room_schedule_file = project_output_dir / "room_schedule.json"
                if room_schedule_file.exists():
                    with open(room_schedule_file, "r") as f:
                        room_schedule_data = json.load(f)

            if room_schedule_data and room_schedule_data.get("rooms"):
                rooms = room_schedule_data["rooms"]
                room_count = len(rooms)
                total_area = sum(r.get("area_sf", 0) for r in rooms)
                total_gsf = room_schedule_data.get("total_gsf")

                print(f"Room Count: {room_count}")
                print(f"Total Room Area: {total_area:,.0f} SF")
                if total_gsf:
                    print(f"Declared GSF: {total_gsf:,.0f} SF")
                    coverage_pct = (total_area / total_gsf * 100) if total_gsf > 0 else 0
                    print(f"Coverage: {coverage_pct:.1f}%")

                # Top 5 rooms by area
                sorted_rooms = sorted(rooms, key=lambda r: r.get("area_sf", 0), reverse=True)
                print(f"\nTop 5 Rooms by Area:")
                for i, room in enumerate(sorted_rooms[:5], 1):
                    area = room.get("area_sf", 0)
                    name = room.get("room_name", "Unknown")
                    print(f"  {i}. {name}: {area:,.0f} SF")

            else:
                print("⚠️  No room schedule extracted")

            # Check validation
            validation_file = project_output_dir / "validation_report.json"
            if validation_file.exists():
                with open(validation_file, "r") as f:
                    validation_data = json.load(f)
                    score = validation_data.get("score", 0.0)
                    passed = validation_data.get("passed", False)
                    print(f"\nValidation Score: {score:.2f}")
                    print(f"Validation Passed: {'✅' if passed else '❌'}")

            # Check bid readiness
            from app.services.bid_readiness import compute_bid_readiness
            try:
                readiness = compute_bid_readiness(project_id, project_output_dir)
                print(f"\nBid Ready: {'✅' if readiness.bid_ready else '❌'}")
                print(f"Readiness Score: {readiness.readiness_score:.2f}")
            except Exception as e:
                print(f"\n⚠️  Could not compute bid readiness: {e}")

        else:
            print("⚠️  Extraction result not found")

        print(f"\n{'='*80}")
        print(f"Output directory: {project_output_dir}")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

