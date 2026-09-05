#!/usr/bin/env python3
"""Run full pipeline on a PDF file to generate bid proposal."""

import sys
from pathlib import Path

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.analyzers.institutional_room_extractor import InstitutionalRoomExtractor
from app.analyzers.row_house_repair_extractor import RowHouseRepairExtractor
from app.analyzers.structural_notes_extractor import StructuralNotesExtractor
from app.analyzers.structural_elements_extractor import StructuralElementsExtractor
from app.analyzers.building_envelope_extractor import BuildingEnvelopeExtractor
from app.analyzers.openings_extractor import OpeningsExtractor
from app.analyzers.lintels_extractor import LintelsExtractor
from app.analyzers.detail_extractor import DetailExtractor
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
    """Run full pipeline on PDF."""
    if len(sys.argv) < 2:
        print("Usage: python run_full_pipeline.py <pdf_path> [project_id]")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    project_id = sys.argv[2] if len(sys.argv) > 2 else generate_project_id()

    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Initialize settings
    settings = get_settings()
    configure_logging(settings)

    if not settings.openai_api_key:
        print("Error: OPENAI_API_KEY must be set", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*80}")
    print(f"Running Full Pipeline on: {pdf_path.name}")
    print(f"Project ID: {project_id}")
    print(f"{'='*80}\n")

    try:
        # Initialize services
        storage_service = StorageService(settings)
        from app.services.document_processor import DocumentProcessor
        document_processor = DocumentProcessor(settings, storage_service)
        openai_client = OpenAIClient(settings)
        document_analyzer = DocumentAnalyzer(settings, openai_client)
        row_house_extractor = RowHouseRepairExtractor(settings, openai_client)
        institutional_room_extractor = InstitutionalRoomExtractor(settings, openai_client)
        structural_notes_extractor = StructuralNotesExtractor(settings, openai_client)
        structural_elements_extractor = StructuralElementsExtractor(settings, openai_client)
        building_envelope_extractor = BuildingEnvelopeExtractor(settings, openai_client)
        openings_extractor = OpeningsExtractor(settings, openai_client)
        lintels_extractor = LintelsExtractor(settings, openai_client)
        detail_extractor = DetailExtractor(settings, openai_client)
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
            openings_extractor=openings_extractor,
            lintels_extractor=lintels_extractor,
            detail_extractor=detail_extractor,
            model_3d_generator=model_3d_generator,
            cost_engine=cost_engine,
            page_indexer=page_indexer,
            settings=settings,
        )

        # Process PDF using document processor (handles image conversion and storage)
        print("Processing PDF...")
        document_bundle = document_processor.process_pdf(project_id, pdf_path)

        # Run full pipeline
        print("\nRunning full pipeline (Stages 0.5 → 1 → 2 → 2.5 → 3 → 4)...")
        project_result = pipeline.run_full_pipeline(project_id, document_bundle)

        # Print summary
        print(f"\n{'='*80}")
        print("PIPELINE COMPLETE")
        print(f"{'='*80}")
        print(f"Status: {project_result.status}")
        print(f"Project ID: {project_id}")
        
        if project_result.costing_result:
            print(f"\nCosting Result:")
            print(f"  Total Cost: ${project_result.costing_result.total_cost:,.2f}")
            print(f"  Items: {len(project_result.costing_result.breakdown_by_scope_item)}")
        
        if project_result.bid_proposal:
            print(f"\nBid Proposal Generated:")
            print(f"  Total Bid: ${project_result.bid_proposal.summary.total_cost:,.2f}")
            print(f"  Line Items: {len(project_result.bid_proposal.line_items)}")
            print(f"  Allowances: {len(project_result.bid_proposal.allowances)}")
            print(f"  Clarifications: {len(project_result.bid_proposal.clarifications)}")

            # Show output file location using orchestrator output dir helper
            output_dir = pipeline._get_output_dir(project_id)
            bid_file = output_dir / "bid_proposal.json"
            print(f"\n  Bid proposal saved to: {bid_file}")

        print(f"\nOutput directory: {pipeline._get_output_dir(project_id)}")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

