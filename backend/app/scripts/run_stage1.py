"""CLI script to run Stage 1 document analysis on a PDF."""

import argparse
import json
import sys
from pathlib import Path

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.core.config import Settings, get_settings
from app.core.ids import generate_project_id
from app.core.logging import configure_logging
from app.services.openai_client import OpenAIClient
from app.utils.pdf_images import pdf_to_images


def main() -> None:
    """CLI entry point for Stage 1 document analysis."""
    parser = argparse.ArgumentParser(
        description="Run Stage 1 document analysis on a PDF file"
    )
    parser.add_argument(
        "input_path",
        type=str,
        nargs="?",
        help="Path to PDF file or folder of PDFs to analyze",
    )
    parser.add_argument(
        "--pdf",
        type=str,
        help="[Deprecated] Use positional argument instead. Path to PDF file to analyze",
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

    # Support both positional argument and --pdf flag (for backward compatibility)
    input_path_str = args.input_path or args.pdf
    if not input_path_str:
        parser.print_help()
        print("\nError: Must provide PDF file or folder path", file=sys.stderr)
        sys.exit(1)

    input_path = Path(input_path_str)
    if not input_path.exists():
        print(f"Error: Path not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Collect PDF files
    pdf_files: list[Path] = []
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            print(f"Error: File must be a PDF: {input_path}", file=sys.stderr)
            sys.exit(1)
        pdf_files = [input_path]
    elif input_path.is_dir():
        pdf_files = sorted(input_path.glob("*.pdf"))
        if not pdf_files:
            print(f"Error: No PDF files found in directory: {input_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(pdf_files)} PDF file(s) in directory")
    else:
        print(f"Error: Invalid path: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize services once
    openai_client = OpenAIClient(settings)
    document_analyzer = DocumentAnalyzer(settings, openai_client)

    # Process each PDF
    for pdf_path in pdf_files:
        project_id = args.project_id or generate_project_id()

        try:
            # Convert PDF to images in memory
            print(f"\n{'='*80}")
            print(f"Processing: {pdf_path.name}")
            print(f"{'='*80}")
            print(f"Converting PDF to images...")
            pdf_images = pdf_to_images(pdf_path, settings, project_id)

            print(f"Analyzing {len(pdf_images)} pages with OpenAI Vision...")

            # Run analysis
            analysis = document_analyzer.analyze(pdf_images, project_id)

            # Convert to JSON
            analysis_json = analysis.model_dump_json(indent=2)

            # Print to console
            print("\n" + "=" * 80)
            print("Document Analysis Result:")
            print("=" * 80)
            print(analysis_json)

            # Save to file
            project_output_dir = output_dir / project_id
            project_output_dir.mkdir(parents=True, exist_ok=True)
            output_file = project_output_dir / "document_analysis.json"
            with open(output_file, "w") as f:
                f.write(analysis_json)

            print(f"\n✓ Analysis saved to: {output_file}")
            print(f"  Project ID: {project_id}")
            print(f"  Project Type: {analysis.project_type}")
            print(f"  Scope Type: {analysis.scope_type}")
            print(f"  Confidence: {analysis.confidence:.2f}")
            print(f"  Pages: {len(pdf_images)}")
            print(f"  Sheets Identified: {len(analysis.sheets)}")

            # Generate new project_id for next PDF if processing multiple
            if len(pdf_files) > 1:
                project_id = None  # Will be regenerated

        except Exception as e:
            print(f"\n✗ Error processing {pdf_path.name}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            if len(pdf_files) == 1:
                sys.exit(1)
            # Continue with next PDF if processing multiple


if __name__ == "__main__":
    main()

