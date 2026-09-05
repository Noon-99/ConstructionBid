"""Unit tests for work package map schema (Task 1)."""

from datetime import datetime

import pytest

from app.schemas.work_package_map import WorkPackage, WorkPackageMap


def test_work_package_creation():
    """Test creating a WorkPackage."""
    package = WorkPackage(
        id="package_001",
        title="Parapet / Coping / Roof Edge",
        division="04 Masonry",
        trade="Masonry",
        estimated_cost=15000.0,
        priority="high",
        confidence=0.85,
        basis_refs=["Detail 1/2", "Spec 04 21 13"],
        member_zone_ids=["zone_1", "zone_2"],
        member_line_item_ids=["0", "1", "2"],
    )

    assert package.id == "package_001"
    assert package.title == "Parapet / Coping / Roof Edge"
    assert package.division == "04 Masonry"
    assert package.trade == "Masonry"
    assert package.estimated_cost == 15000.0
    assert package.priority == "high"
    assert package.confidence == 0.85
    assert len(package.member_zone_ids) == 2
    assert len(package.member_line_item_ids) == 3


def test_work_package_map_creation():
    """Test creating a WorkPackageMap."""
    package1 = WorkPackage(
        id="package_001",
        title="Parapet Work",
        division="04 Masonry",
        estimated_cost=10000.0,
        confidence=0.85,
        member_zone_ids=["zone_1"],
        member_line_item_ids=["0"],
    )

    package2 = WorkPackage(
        id="package_002",
        title="Lintel Replacement",
        division="05 Metals",
        estimated_cost=5000.0,
        confidence=0.8,
        member_zone_ids=["zone_2"],
        member_line_item_ids=["1"],
    )

    package_map = WorkPackageMap(
        project_id="test_project",
        packages=[package1, package2],
        zone_to_package={"zone_1": "package_001", "zone_2": "package_002"},
        line_item_to_package={"0": "package_001", "1": "package_002"},
        generated_at=datetime.now(),
        version="1.0",
    )

    assert package_map.project_id == "test_project"
    assert len(package_map.packages) == 2
    assert len(package_map.zone_to_package) == 2
    assert len(package_map.line_item_to_package) == 2
    assert package_map.version == "1.0"


def test_work_package_serialization():
    """Test that WorkPackage serializes to JSON correctly."""
    package = WorkPackage(
        id="test_package",
        title="Test Package",
        division="04 Masonry",
        trade="Masonry",
        estimated_cost=5000.0,
        priority="medium",
        confidence=0.8,
        member_zone_ids=["zone_1"],
        member_line_item_ids=["0"],
    )

    data = package.model_dump()
    assert data["id"] == "test_package"
    assert data["title"] == "Test Package"
    assert data["estimated_cost"] == 5000.0

    restored = WorkPackage.model_validate(data)
    assert restored.id == package.id
    assert restored.title == package.title


def test_work_package_map_serialization():
    """Test that WorkPackageMap serializes to JSON correctly."""
    package_map = WorkPackageMap(
        project_id="test_project",
        packages=[],
        zone_to_package={},
        line_item_to_package={},
        generated_at=datetime(2024, 1, 1, 12, 0, 0),
        version="1.0",
    )

    data = package_map.model_dump(mode="json")
    assert data["project_id"] == "test_project"
    assert data["version"] == "1.0"
    assert isinstance(data["generated_at"], str)  # datetime serializes to ISO string

    restored = WorkPackageMap.model_validate(data)
    assert restored.project_id == package_map.project_id
    assert restored.version == package_map.version

