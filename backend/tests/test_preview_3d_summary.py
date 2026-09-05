"""Tests for 3D preview summary script (Phase 4.5A)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.schemas.model_3d import (
    BoundingBox,
    BuildingVolume,
    Geometry3D,
    Materials3D,
    Model3D,
    Vector3D,
    WorkZoneVolume,
)
from app.scripts.preview_3d_summary import (
    calculate_footprint_area,
    preview_3d_summary,
)


def test_calculate_footprint_area() -> None:
    """Test footprint area calculation."""
    # Valid bbox
    bbox = {
        "min": {"x": 0.0, "y": 0.0, "z": 0.0},
        "max": {"x": 100.0, "y": 80.0, "z": 20.0},
    }
    assert calculate_footprint_area(bbox) == 8000.0

    # None bbox
    assert calculate_footprint_area(None) == 0.0

    # Zero area
    bbox_zero = {
        "min": {"x": 0.0, "y": 0.0, "z": 0.0},
        "max": {"x": 0.0, "y": 0.0, "z": 20.0},
    }
    assert calculate_footprint_area(bbox_zero) == 0.0


def test_preview_3d_summary_with_institutional_model() -> None:
    """Test preview summary with institutional 3D model."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        project_id = "test-project"
        project_dir = output_dir / project_id
        project_dir.mkdir(parents=True)

        # Create model_3d.json
        model = Model3D(
            buildings=[
                BuildingVolume(
                    building_id="existing_001",
                    building_type="institutional",
                    bounding_box=BoundingBox(
                        min=Vector3D(x=0.0, y=0.0, z=0.0),
                        max=Vector3D(x=100.0, y=80.0, z=20.0),
                    ),
                    is_subject=True,
                    evidence="Existing building from plans",
                ),
                BuildingVolume(
                    building_id="addition_001",
                    building_type="institutional",
                    bounding_box=BoundingBox(
                        min=Vector3D(x=100.0, y=0.0, z=0.0),
                        max=Vector3D(x=130.0, y=40.0, z=20.0),
                    ),
                    is_subject=False,
                    evidence="Addition building",
                ),
            ],
            work_zones=[
                WorkZoneVolume(
                    zone_name="Gymnasium",
                    bounding_box=BoundingBox(
                        min=Vector3D(x=0.0, y=0.0, z=0.0),
                        max=Vector3D(x=70.0, y=102.0, z=20.0),
                    ),
                    facade_region=None,
                    page_number=2,
                    evidence="Gymnasium 7,140 SF",
                    zone_type="room",
                ),
                WorkZoneVolume(
                    zone_name="Meeting Room",
                    bounding_box=BoundingBox(
                        min=Vector3D(x=70.0, y=0.0, z=0.0),
                        max=Vector3D(x=100.0, y=7.14, z=20.0),
                    ),
                    facade_region=None,
                    page_number=2,
                    evidence="Meeting Room 500 SF",
                    zone_type="room",
                ),
            ],
            geometry=Geometry3D(),
            materials=Materials3D(),
            missing_evidence=[],
        )

        model_file = project_dir / "model_3d.json"
        with open(model_file, "w") as f:
            f.write(model.model_dump_json(indent=2))

        # Create extraction_result.json with institutional geometry
        extraction_data = {
            "institutional_geometry_for_3d": {
                "geometry_quality": "authoritative",
                "missing_evidence": [],
            }
        }
        extraction_file = project_dir / "extraction_result.json"
        with open(extraction_file, "w") as f:
            json.dump(extraction_data, f, indent=2)

        # Run preview
        exit_code = preview_3d_summary(project_id, output_dir)

        assert exit_code == 0


def test_preview_3d_summary_warnings() -> None:
    """Test that preview shows warnings for issues."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        project_id = "test-project"
        project_dir = output_dir / project_id
        project_dir.mkdir(parents=True)

        # Create model with invalid dimensions
        model = Model3D(
            buildings=[
                BuildingVolume(
                    building_id="existing_001",
                    building_type="institutional",
                    bounding_box=BoundingBox(
                        min=Vector3D(x=0.0, y=0.0, z=0.0),
                        max=Vector3D(x=0.0, y=0.0, z=20.0),  # Zero footprint
                    ),
                    is_subject=True,
                    evidence="Existing building",
                ),
            ],
            work_zones=[
                WorkZoneVolume(
                    zone_name="Room 1",
                    bounding_box=BoundingBox(
                        min=Vector3D(x=0.0, y=0.0, z=0.0),
                        max=Vector3D(x=10.0, y=10.0, z=0.0),  # Zero height
                    ),
                    facade_region=None,
                    page_number=1,
                    evidence="Room 1",
                    zone_type="room",
                ),
            ],
            geometry=Geometry3D(),
            materials=Materials3D(),
            missing_evidence=["height", "width"],
        )

        model_file = project_dir / "model_3d.json"
        with open(model_file, "w") as f:
            f.write(model.model_dump_json(indent=2))

        # Run preview
        exit_code = preview_3d_summary(project_id, output_dir)

        # Should succeed but show warnings
        assert exit_code == 0


def test_preview_3d_summary_missing_file() -> None:
    """Test that preview handles missing file gracefully."""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        project_id = "nonexistent-project"

        exit_code = preview_3d_summary(project_id, output_dir)

        assert exit_code == 1

