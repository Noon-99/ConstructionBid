"""CLI script to preview 3D model geometry summary (Phase 4.5A).

Reads model_3d.json and prints a human-readable summary for verification.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.schemas.model_3d import Model3D


def calculate_footprint_area(bbox: dict[str, dict[str, float]] | None) -> float:
    """Calculate footprint area from bounding box."""
    if not bbox:
        return 0.0
    width = bbox["max"]["x"] - bbox["min"]["x"]
    depth = bbox["max"]["y"] - bbox["min"]["y"]
    return width * depth


def preview_3d_summary(project_id: str, output_dir: Path | None = None) -> int:
    """
    Preview 3D model geometry summary.

    Args:
        project_id: Project ID
        output_dir: Output directory (default: ./out)

    Returns:
        Exit code (0 = success, 1 = error)
    """
    if output_dir is None:
        output_dir = Path("./out")

    project_dir = output_dir / project_id
    model_3d_file = project_dir / "model_3d.json"

    if not model_3d_file.exists():
        print(f"Error: model_3d.json not found at {model_3d_file}", file=sys.stderr)
        return 1

    try:
        with open(model_3d_file, "r") as f:
            model_data = json.load(f)

        model = Model3D.model_validate(model_data)

        print(f"\n{'='*80}")
        print(f"3D Model Geometry Summary: {project_id}")
        print(f"{'='*80}\n")

        # A) Building masses
        print("BUILDING MASSES:")
        print(f"  Total buildings: {len(model.buildings)}")
        
        existing_buildings = [b for b in model.buildings if b.is_subject]
        addition_buildings = [b for b in model.buildings if not b.is_subject and (b.building_type == "institutional" or "addition" in (b.building_id or "").lower())]
        
        if existing_buildings:
            existing = existing_buildings[0]
            bbox = existing.bounding_box
            width = bbox.max.x - bbox.min.x
            depth = bbox.max.y - bbox.min.y
            height = bbox.max.z - bbox.min.z
            print(f"  ✓ Existing building:")
            print(f"    - Dimensions: {width:.1f}' × {depth:.1f}' × {height:.1f}'")
            print(f"    - Footprint: {width * depth:.0f} SF")
            print(f"    - Evidence: {existing.evidence[:60]}...")
        else:
            print("  ✗ No existing building found")

        if addition_buildings:
            addition = addition_buildings[0]
            bbox = addition.bounding_box
            width = bbox.max.x - bbox.min.x
            depth = bbox.max.y - bbox.min.y
            height = bbox.max.z - bbox.min.z
            print(f"  ✓ Addition building:")
            print(f"    - Dimensions: {width:.1f}' × {depth:.1f}' × {height:.1f}'")
            print(f"    - Footprint: {width * depth:.0f} SF")
            print(f"    - Evidence: {addition.evidence[:60]}...")
        else:
            print("  - No addition building")

        # B) Room zones
        print(f"\nROOM ZONES:")
        room_zones = [z for z in model.work_zones if z.zone_type == "room"]
        work_zones = [z for z in model.work_zones if z.zone_type == "work_zone" or z.zone_type is None]
        
        print(f"  Room zones: {len(room_zones)}")
        print(f"  Work zones: {len(work_zones)}")
        print(f"  Total zones: {len(model.work_zones)}")

        if len(room_zones) < 10:
            print(f"  ⚠ WARNING: Only {len(room_zones)} room zones (expected >= 10 for institutional)")

        # Top 5 largest room zones by footprint
        if room_zones:
            print(f"\n  TOP 5 LARGEST ROOM ZONES (by footprint):")
            room_footprints = [
                (
                    zone,
                    calculate_footprint_area(
                        zone.bounding_box.model_dump() if zone.bounding_box else None
                    ),
                )
                for zone in room_zones
            ]
            room_footprints.sort(key=lambda x: x[1], reverse=True)
            
            for i, (zone, footprint) in enumerate(room_footprints[:5], 1):
                bbox = zone.bounding_box
                if bbox:
                    width = bbox.max.x - bbox.min.x
                    depth = bbox.max.y - bbox.min.y
                    print(f"    {i}. {zone.zone_name}: {footprint:.0f} SF ({width:.1f}' × {depth:.1f}')")
                else:
                    print(f"    {i}. {zone.zone_name}: {footprint:.0f} SF (no bbox)")

        # C) Geometry quality check
        print(f"\nGEOMETRY QUALITY:")
        extraction_file = project_dir / "extraction_result.json"
        if extraction_file.exists():
            try:
                with open(extraction_file, "r") as f:
                    extraction_data = json.load(f)
                
                inst_geometry = extraction_data.get("institutional_geometry_for_3d")
                if inst_geometry:
                    quality = inst_geometry.get("geometry_quality", "unknown")
                    print(f"  Quality: {quality}")
                    
                    if quality == "derived_from_area":
                        print("  ⚠ WARNING: Geometry derived from area (layout approximated)")
                    elif quality == "partial":
                        print("  ⚠ WARNING: Partial geometry (some data missing)")
                    elif quality == "missing":
                        print("  ✗ ERROR: Missing geometry")
                    else:
                        print("  ✓ Authoritative geometry")
                    
                    missing = inst_geometry.get("missing_evidence", [])
                    if missing:
                        print(f"  Missing evidence: {', '.join(missing)}")
                else:
                    print("  - No institutional geometry data")
            except Exception as e:
                print(f"  ⚠ Could not read extraction_result.json: {e}")
        else:
            print("  - extraction_result.json not found")

        # D) Warnings
        warnings: list[str] = []
        
        # Check for zero/negative dimensions
        for building in model.buildings:
            bbox = building.bounding_box
            width = bbox.max.x - bbox.min.x
            depth = bbox.max.y - bbox.min.y
            height = bbox.max.z - bbox.min.z
            
            if width <= 0 or depth <= 0:
                warnings.append(f"Building {building.building_id} has invalid footprint: {width:.1f}' × {depth:.1f}'")
            if height <= 0:
                warnings.append(f"Building {building.building_id} has invalid height: {height:.1f}'")
        
        for zone in model.work_zones:
            if zone.bounding_box:
                bbox = zone.bounding_box
                width = bbox.max.x - bbox.min.x
                depth = bbox.max.y - bbox.min.y
                height = bbox.max.z - bbox.min.z
                
                if width <= 0 or depth <= 0:
                    warnings.append(f"Zone '{zone.zone_name}' has invalid footprint: {width:.1f}' × {depth:.1f}'")
                if height <= 0:
                    warnings.append(f"Zone '{zone.zone_name}' has invalid height: {height:.1f}'")

        # Check missing evidence
        if model.missing_evidence:
            warnings.append(f"Missing evidence: {', '.join(model.missing_evidence)}")

        if warnings:
            print(f"\n⚠ WARNINGS:")
            for warning in warnings:
                print(f"  - {warning}")
        else:
            print(f"\n✓ No warnings")

        print(f"\n{'='*80}\n")

        return 0

    except Exception as e:
        print(f"Error reading model_3d.json: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Preview 3D model geometry summary (Phase 4.5A)"
    )
    parser.add_argument(
        "project_id",
        type=str,
        help="Project ID to preview",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./out",
        help="Output directory (default: ./out)",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    exit_code = preview_3d_summary(args.project_id, output_dir)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

