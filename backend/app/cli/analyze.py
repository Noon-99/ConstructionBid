"""CLI tool for document analysis."""

import json
import sys
from pathlib import Path

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.core.config import Settings
from app.core.ids import generate_project_id
from app.core.logging import configure_logging
from app.services.document_processor import DocumentProcessor
from app.services.openai_client import OpenAIClient
from app.services.storage import StorageService


def main() -> None:
    """CLI entry point for document analysis."""
    if len(sys.argv) < 2:
        print("Usage: python -m app.cli.analyze <path/to/file.pdf>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    # Initialize settings and logging
    settings = Settings()
    configure_logging(settings)

    if not settings.openai_api_key:
        print("Error: OPENAI_API_KEY must be set in environment or .env file")
        sys.exit(1)

    # Generate project ID
    project_id = generate_project_id()

    try:
        # Initialize services
        storage_service = StorageService(settings)
        document_processor = DocumentProcessor(settings, storage_service)
        openai_client = OpenAIClient(settings)
        document_analyzer = DocumentAnalyzer(settings, openai_client)

        # Process PDF to images
        print(f"Processing PDF: {pdf_path}")
        document_bundle = document_processor.process_pdf(project_id, pdf_path)

        # Analyze document
        print(f"Analyzing document with OpenAI Vision...")
        analysis = document_analyzer.analyze_from_paths(
            image_paths=document_bundle.page_image_paths,
            project_id=project_id,
        )

        # Output JSON
        output = analysis.model_dump_json(indent=2)
        print("\n" + "=" * 80)
        print("Document Analysis Result:")
        print("=" * 80)
        print(output)

        # Save to file
        output_path = pdf_path.parent / "document_analysis.json"
        with open(output_path, "w") as f:
            f.write(output)
        print(f"\nSaved to: {output_path}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

