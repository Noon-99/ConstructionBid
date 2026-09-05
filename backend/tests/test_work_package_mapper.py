"""Unit tests for work package mapper (Task 1)."""

from datetime import datetime

import pytest

from app.schemas.bid_proposal import BidLineItem, BidProposal, BidSummary
from app.schemas.evidence_index import EvidenceIndex, ZoneEvidence
from app.schemas.model_3d import Model3D, WorkZoneVolume
from app.schemas.work_package_map import WorkPackageMap
from app.services.work_package_mapper import map_work_packages


@pytest.fixture
def sample_bid_proposal():
    """Create a sample bid proposal for testing."""
    line_items = [
        BidLineItem(
            division="04 Masonry",
            description="Parapet repair and rebuild",
            quantity=120.0,
            unit="LF",
            unit_cost=50.0,
            total_cost=6000.0,
            basis="Elevation notes",
            confidence=0.9,
        ),
        BidLineItem(
            division="04 Masonry",
            description="Roof edge flashing installation",
            quantity=120.0,
            unit="LF",
            unit_cost=25.0,
            total_cost=3000.0,
            basis="Detail 1/2",
            confidence=0.85,
        ),
        BidLineItem(
            division="05 Metals",
            description="Lintel replacement - steel angle",
            quantity=8.0,
            unit="EA",
            unit_cost=500.0,
            total_cost=4000.0,
            basis="Schedule S-011",
            confidence=0.9,
        ),
        BidLineItem(
            division="04 Masonry",
            description="Brick repointing",
            quantity=500.0,
            unit="SF",
            unit_cost=15.0,
            total_cost=7500.0,
            basis="Facade elevation",
            confidence=0.8,
        ),
        BidLineItem(
            division="04 Masonry",
            description="Crack repair and epoxy injection",
            quantity=50.0,
            unit="LF",
            unit_cost=30.0,
            total_cost=1500.0,
            basis="Elevation notes",
            confidence=0.75,
        ),
    ]

    return BidProposal(
        project_id="test_project",
        summary=BidSummary(total_cost=22000.0),
        line_items=line_items,
        allowances=[],
        alternates=[],
        clarifications=[],
    )


@pytest.fixture
def sample_model_3d():
    """Create a sample 3D model for testing."""
    from app.schemas.model_3d import Geometry3D, Materials3D, Vector3D

    zones = [
        WorkZoneVolume(
            zone_name="parapet_band",
            bounding_box=None,
            facade_region="parapet band",
            page_number=1,
            evidence="Elevation shows parapet",
            zone_type="work_zone",
        ),
        WorkZoneVolume(
            zone_name="roof_edge_zone",
            bounding_box=None,
            facade_region="roof edge",
            page_number=1,
            evidence="Detail shows roof edge",
            zone_type="work_zone",
        ),
        WorkZoneVolume(
            zone_name="lintel_band",
            bounding_box=None,
            facade_region="lintel band",
            page_number=2,
            evidence="Elevation shows lintel locations",
            zone_type="work_zone",
        ),
        WorkZoneVolume(
            zone_name="facade_zone_1",
            bounding_box=None,
            facade_region="front facade",
            page_number=1,
            evidence="Front elevation",
            zone_type="work_zone",
        ),
    ]

    geometry = Geometry3D(
        site_origin=Vector3D(x=0.0, y=0.0, z=0.0),
        units="feet",
        coordinate_system="right_handed_y_up",
    )

    materials = Materials3D(
        building_materials={},
        work_zone_materials={},
    )

    return Model3D(
        buildings=[],
        geometry=geometry,
        work_zones=zones,
        windows=[],
        materials=materials,
        missing_evidence=[],
        geometry_quality="ok",
    )


@pytest.fixture
def sample_evidence_index():
    """Create a sample evidence index for testing."""
    zone_evidence = [
        ZoneEvidence(
            zone_id="parapet_band",
            zone_type="work_zone",
            label="Parapet Band",
            evidence_references=[],
            linked_bid_items=[0],  # Links to parapet repair line item
        ),
        ZoneEvidence(
            zone_id="lintel_band",
            zone_type="work_zone",
            label="Lintel Band",
            evidence_references=[],
            linked_bid_items=[2],  # Links to lintel replacement line item
        ),
    ]

    return EvidenceIndex(
        project_id="test_project",
        bid_item_evidence=[],
        zone_evidence=zone_evidence,
        detail_evidence=[],
        generated_at=datetime.now().isoformat(),
    )


def test_map_work_packages_creates_packages(sample_bid_proposal, sample_model_3d):
    """Test that work packages are created from bid proposal."""
    result = map_work_packages(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        model_3d=sample_model_3d,
    )

    assert isinstance(result, WorkPackageMap)
    assert result.project_id == "test_project"
    assert len(result.packages) > 0
    assert len(result.packages) <= 10  # Should produce 5-10 packages for Queens rowhouse

    # Check that packages have required fields
    for package in result.packages:
        assert package.id
        assert package.title
        assert package.division
        assert package.estimated_cost >= 0
        assert package.confidence >= 0.0 and package.confidence <= 1.0


def test_map_work_packages_groups_by_scope_term(sample_bid_proposal, sample_model_3d):
    """Test that line items are grouped by root scope term."""
    result = map_work_packages(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        model_3d=sample_model_3d,
    )

    # Should have packages for: parapet, flashing, lintel, repointing, crack
    package_titles = [p.title.lower() for p in result.packages]

    assert any("parapet" in title or "coping" in title for title in package_titles)
    assert any("lintel" in title for title in package_titles)
    assert any("repoint" in title for title in package_titles)
    assert any("crack" in title for title in package_titles)


def test_map_work_packages_assigns_zones(sample_bid_proposal, sample_model_3d, sample_evidence_index):
    """Test that zones are assigned to packages using evidence_index."""
    result = map_work_packages(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        model_3d=sample_model_3d,
        evidence_index=sample_evidence_index,
    )

    # Find parapet package
    parapet_package = next(
        (p for p in result.packages if "parapet" in p.title.lower() or "coping" in p.title.lower()), None
    )
    assert parapet_package is not None
    assert "parapet_band" in parapet_package.member_zone_ids

    # Check zone_to_package mapping
    assert result.zone_to_package.get("parapet_band") == parapet_package.id


def test_map_work_packages_creates_line_item_mapping(sample_bid_proposal, sample_model_3d):
    """Test that line_item_to_package mapping is created."""
    result = map_work_packages(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        model_3d=sample_model_3d,
    )

    assert len(result.line_item_to_package) == len(sample_bid_proposal.line_items)

    # Each line item should map to a package
    for idx in range(len(sample_bid_proposal.line_items)):
        assert str(idx) in result.line_item_to_package


def test_map_work_packages_aggregates_costs(sample_bid_proposal, sample_model_3d):
    """Test that package costs are aggregated from line items."""
    result = map_work_packages(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        model_3d=sample_model_3d,
    )

    total_package_cost = sum(p.estimated_cost for p in result.packages)
    total_bid_cost = sample_bid_proposal.summary.total_cost

    # Package costs should sum to bid total (within rounding)
    assert abs(total_package_cost - total_bid_cost) < 1.0


def test_map_work_packages_handles_missing_data(sample_bid_proposal):
    """Test that mapper handles missing model_3d gracefully."""
    result = map_work_packages(
        project_id="test_project",
        bid_proposal=sample_bid_proposal,
        model_3d=None,
    )

    assert isinstance(result, WorkPackageMap)
    assert len(result.packages) > 0
    # Packages should still be created even without zones
    for package in result.packages:
        assert len(package.member_line_item_ids) > 0

