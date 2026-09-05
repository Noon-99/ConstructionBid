"""Tests for detail overlay indexer (Phase 8.4)."""

import pytest

from app.schemas.detail_overlay_index import DetailOverlayIndex
from app.services.detail_overlay_indexer import DetailOverlayIndexer


def test_generate_detail_overlay_index_basic():
    """Test basic detail overlay index generation."""
    indexer = DetailOverlayIndexer()

    model_3d = {
        "cross_section_regions": [
            {
                "region_id": "parapet_001",
                "region_type": "parapet",
                "bounding_box": {
                    "min": {"x": 0, "y": 0, "z": 0},
                    "max": {"x": 10, "y": 10, "z": 2},
                },
                "applies_to": ["zone_1"],
                "detail_refs": ["DET-001"],
                "evidence": "Parapet region from elevation",
            }
        ]
    }

    detail_graph = {
        "details": [
            {
                "detail_id": "DET-001",
                "detail_type": "parapet",
                "sheet_id": "S-011",
                "detail_label": "Detail 4",
                "page_number": 5,
                "evidence_snippet": "Parapet detail on sheet S-011",
                "applies_to": [],
                "materials_referenced": [],
                "dimensions_referenced": [],
            }
        ]
    }

    result = indexer.generate(
        project_id="test",
        model_3d=model_3d,
        detail_graph=detail_graph,
        evidence_index=None,
    )

    assert result.project_id == "test"
    assert len(result.regions) == 1

    region = result.regions[0]
    assert region.region_id == "parapet_001"
    assert region.region_type == "parapet"
    assert "DET-001" in region.detail_ids
    assert len(region.detail_refs) == 1
    assert region.detail_refs[0]["detail_id"] == "DET-001"
    assert region.detail_refs[0]["sheet_id"] == "S-011"
    assert region.detail_refs[0]["detail_label"] == "Detail 4"
    assert 5 in region.evidence_pages
    assert len(region.snippets) > 0


def test_generate_detail_overlay_index_with_evidence():
    """Test detail overlay index with evidence_index enrichment."""
    indexer = DetailOverlayIndexer()

    model_3d = {
        "cross_section_regions": [
            {
                "region_id": "wall_assembly_001",
                "region_type": "wall_assembly",
                "bounding_box": {
                    "min": {"x": 0, "y": 0, "z": 0},
                    "max": {"x": 10, "y": 10, "z": 20},
                },
                "applies_to": ["building_1"],
                "detail_refs": ["DET-002"],
                "evidence": "Wall assembly region",
            }
        ]
    }

    detail_graph = {
        "details": [
            {
                "detail_id": "DET-002",
                "detail_type": "wall_section",
                "sheet_id": "S-012",
                "detail_label": "Typical Wall Section",
                "page_number": 6,
                "evidence_snippet": "Wall section detail",
                "applies_to": [],
                "materials_referenced": [],
                "dimensions_referenced": [],
            }
        ]
    }

    evidence_index = {
        "detail_evidence": [
            {
                "detail_id": "DET-002",
                "detail_type": "wall_section",
                "sheet_id": "S-012",
                "detail_label": "Typical Wall Section",
                "evidence_references": [
                    {
                        "page_number": 6,
                        "sheet_id": "S-012",
                        "evidence_snippet": "Wall section callout on elevation",
                        "location_type": "callout",
                    },
                    {
                        "page_number": 7,
                        "sheet_id": "S-012",
                        "evidence_snippet": "Wall section spec notes",
                        "location_type": "note",
                    },
                ],
                "linked_zones": [],
                "linked_openings": [],
                "linked_bid_items": [],
            }
        ]
    }

    result = indexer.generate(
        project_id="test",
        model_3d=model_3d,
        detail_graph=detail_graph,
        evidence_index=evidence_index,
    )

    region = result.regions[0]
    # Should have evidence from both detail_graph and evidence_index
    assert 6 in region.evidence_pages
    assert 7 in region.evidence_pages
    # Should have multiple snippets
    assert len(region.snippets) >= 2


def test_generate_detail_overlay_index_missing_data():
    """Test detail overlay index with missing detail_graph."""
    indexer = DetailOverlayIndexer()

    model_3d = {
        "cross_section_regions": [
            {
                "region_id": "roof_edge_001",
                "region_type": "roof_edge",
                "bounding_box": {
                    "min": {"x": 0, "y": 0, "z": 0},
                    "max": {"x": 10, "y": 10, "z": 1},
                },
                "applies_to": ["roof_1"],
                "detail_refs": ["DET-003"],
                "evidence": "Roof edge region",
            }
        ]
    }

    # No detail_graph
    result = indexer.generate(
        project_id="test",
        model_3d=model_3d,
        detail_graph=None,
        evidence_index=None,
    )

    region = result.regions[0]
    assert region.region_id == "roof_edge_001"
    assert len(region.detail_ids) == 1  # Still has detail_refs from region
    assert len(region.detail_refs) == 0  # But no detail info without detail_graph
    # Should fallback to region evidence
    assert len(region.snippets) > 0


def test_generate_detail_overlay_index_multiple_regions():
    """Test detail overlay index with multiple regions."""
    indexer = DetailOverlayIndexer()

    model_3d = {
        "cross_section_regions": [
            {
                "region_id": "parapet_001",
                "region_type": "parapet",
                "bounding_box": {"min": {"x": 0, "y": 0, "z": 0}, "max": {"x": 10, "y": 10, "z": 2}},
                "applies_to": [],
                "detail_refs": ["DET-001"],
                "evidence": "Parapet",
            },
            {
                "region_id": "foundation_001",
                "region_type": "foundation",
                "bounding_box": {"min": {"x": 0, "y": 0, "z": 0}, "max": {"x": 10, "y": 10, "z": 1}},
                "applies_to": [],
                "detail_refs": ["DET-002"],
                "evidence": "Foundation",
            },
        ]
    }

    detail_graph = {
        "details": [
            {
                "detail_id": "DET-001",
                "detail_type": "parapet",
                "sheet_id": "S-011",
                "detail_label": "Detail 4",
                "page_number": 5,
                "evidence_snippet": "Parapet detail",
                "applies_to": [],
                "materials_referenced": [],
                "dimensions_referenced": [],
            },
            {
                "detail_id": "DET-002",
                "detail_type": "foundation",
                "sheet_id": "S-012",
                "detail_label": "Foundation Detail",
                "page_number": 6,
                "evidence_snippet": "Foundation detail",
                "applies_to": [],
                "materials_referenced": [],
                "dimensions_referenced": [],
            },
        ]
    }

    result = indexer.generate(
        project_id="test",
        model_3d=model_3d,
        detail_graph=detail_graph,
        evidence_index=None,
    )

    assert len(result.regions) == 2
    assert result.regions[0].region_id == "parapet_001"
    assert result.regions[1].region_id == "foundation_001"






