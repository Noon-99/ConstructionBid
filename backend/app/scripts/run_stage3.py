"""CLI script to run Stage 3 (3D model generation) from extraction result."""

import argparse
import json
import sys
from pathlib import Path

from app.generators.model_3d_generator import Model3DGenerator
from app.schemas.extraction_result import ExtractionResult


def main() -> None:
    """CLI entry point for Stage 3 3D model generation."""
    parser = argparse.ArgumentParser(
        description="Generate 3D model from Stage 2 extraction result"
    )
    parser.add_argument(
        "extraction_file",
        type=str,
        help="Path to extraction_result.json file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: same directory as input, named model_3d.json)",
    )

    args = parser.parse_args()

    extraction_path = Path(args.extraction_file)
    if not extraction_path.exists():
        print(f"Error: Extraction file not found: {extraction_path}", file=sys.stderr)
        sys.exit(1)

    try:
        # Load extraction result
        print(f"Loading extraction result: {extraction_path}")
        with open(extraction_path, "r") as f:
            extraction_data = json.load(f)

        extraction_result = ExtractionResult.model_validate(extraction_data)

        # Generate 3D model
        print("Generating 3D model...")
        generator = Model3DGenerator()
        model_3d = generator.generate(extraction_result)

        # Save output
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = extraction_path.parent / "model_3d.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(model_3d.model_dump_json(indent=2))

        # Print summary
        print("\n" + "=" * 80)
        print("3D Model Generation Complete")
        print("=" * 80)
        print(f"Buildings: {len(model_3d.buildings)}")
        print(f"Work Zones: {len(model_3d.work_zones)}")
        print(f"Windows: {len(model_3d.windows)}")
        if model_3d.missing_evidence:
            print(f"Missing Evidence: {', '.join(model_3d.missing_evidence)}")
        print(f"\n✓ Model saved to: {output_path}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

