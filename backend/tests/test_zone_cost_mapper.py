"""Tests for zone cost mapper (Phase 8.3)."""

import pytest

from app.schemas.zone_cost_map import ZoneCostMap
from app.services.zone_cost_mapper import ZoneCostMapper


def test_generate_zone_cost_map_evidence_index():
    """Test zone cost mapping using evidence_index explicit links."""
    mapper = ZoneCostMapper()

    model_3d = {
        "work_zones": [
            {
                "zone_name": "parapet_band",
                "zone_type": "work_zone",
                "bounding_box": None,
                "facade_region": "parapet",
                "page_number": 1,
                "evidence": "Parapet zone",
            }
        ]
    }

    bid_review = {
        "line_items": [
            {
                "line_item_id": "line_item_0",
                "line_item_index": 0,
                "division": "04 Masonry",
                "title": "Parapet repair",
                "quantity": 20.0,
                "unit": "LF",
                "unit_cost": 50.0,
                "total_cost": 1000.0,
                "rule_refs": [],
                "multipliers_applied": [],
                "quantity_source": "explicit_takeoff",
                "evidence_refs": [],
                "flags": [],
            }
        ]
    }

    evidence_index = {
        "zone_evidence": [
            {
                "zone_id": "parapet_band",
                "zone_type": "work_zone",
                "label": "Parapet Band",
                "evidence_references": [],
                "linked_bid_items": [0],  # Explicit link to line item 0
            }
        ]
    }

    result = mapper.generate(
        project_id="test",
        model_3d=model_3d,
        bid_review=bid_review,
        evidence_index=evidence_index,
    )

    assert result.project_id == "test"
    assert len(result.zones) == 1

    zone = result.zones[0]
    assert zone.zone_id == "parapet_band"
    assert zone.zone_name == "parapet_band"
    assert zone.total_cost == 1000.0
    assert zone.attribution_method == "evidence_index"
    assert zone.linked_line_item_ids == [0]
    assert "04 Masonry" in zone.division_breakdown
    assert zone.division_breakdown["04 Masonry"] == 1000.0
    assert len(zone.top_line_items) == 1
    assert zone.top_line_items[0].line_item_index == 0
    assert zone.top_line_items[0].contribution_percent == 100.0


def test_generate_zone_cost_map_keyword_fallback():
    """Test zone cost mapping using keyword fallback."""
    mapper = ZoneCostMapper()

    model_3d = {
        "work_zones": [
            {
                "zone_name": "parapet_band",
                "zone_type": "work_zone",
                "bounding_box": None,
                "facade_region": "parapet",
                "page_number": 1,
                "evidence": "Parapet zone",
            }
        ]
    }

    bid_review = {
        "line_items": [
            {
                "line_item_id": "line_item_0",
                "line_item_index": 0,
                "division": "04 Masonry",
                "title": "Parapet band repair and rebuild",
                "quantity": 20.0,
                "unit": "LF",
                "unit_cost": 50.0,
                "total_cost": 1000.0,
                "rule_refs": [],
                "multipliers_applied": [],
                "quantity_source": "explicit_takeoff",
                "evidence_refs": [],
                "flags": [],
            }
        ]
    }

    # No evidence_index, should use keyword fallback
    result = mapper.generate(
        project_id="test",
        model_3d=model_3d,
        bid_review=bid_review,
        evidence_index=None,
    )

    assert len(result.zones) == 1
    zone = result.zones[0]
    # Should match via keyword (parapet and band appear in both)
    assert zone.attribution_method == "keyword_fallback"
    assert len(zone.linked_line_item_ids) > 0


def test_generate_zone_cost_map_none():
    """Test zone cost mapping with no attribution."""
    mapper = ZoneCostMapper()

    model_3d = {
        "work_zones": [
            {
                "zone_name": "unknown_zone",
                "zone_type": "work_zone",
                "bounding_box": None,
                "facade_region": None,
                "page_number": 1,
                "evidence": "Unknown zone",
            }
        ]
    }

    bid_review = {
        "line_items": [
            {
                "line_item_id": "line_item_0",
                "line_item_index": 0,
                "division": "04 Masonry",
                "title": "Completely unrelated item",
                "quantity": 20.0,
                "unit": "LF",
                "unit_cost": 50.0,
                "total_cost": 1000.0,
                "rule_refs": [],
                "multipliers_applied": [],
                "quantity_source": "explicit_takeoff",
                "evidence_refs": [],
                "flags": [],
            }
        ]
    }

    result = mapper.generate(
        project_id="test",
        model_3d=model_3d,
        bid_review=bid_review,
        evidence_index=None,
    )

    assert len(result.zones) == 1
    zone = result.zones[0]
    assert zone.attribution_method == "none"
    assert zone.total_cost == 0.0
    assert len(zone.linked_line_item_ids) == 0


def test_generate_zone_cost_map_multiple_items():
    """Test zone cost mapping with multiple line items."""
    mapper = ZoneCostMapper()

    model_3d = {
        "work_zones": [
            {
                "zone_name": "parapet_band",
                "zone_type": "work_zone",
                "bounding_box": None,
                "facade_region": "parapet",
                "page_number": 1,
                "evidence": "Parapet zone",
            }
        ]
    }

    bid_review = {
        "line_items": [
            {
                "line_item_id": "line_item_0",
                "line_item_index": 0,
                "division": "04 Masonry",
                "title": "Parapet repair",
                "quantity": 20.0,
                "unit": "LF",
                "unit_cost": 50.0,
                "total_cost": 1000.0,
                "rule_refs": [],
                "multipliers_applied": [],
                "quantity_source": "explicit_takeoff",
                "evidence_refs": [],
                "flags": [],
            },
            {
                "line_item_id": "line_item_1",
                "line_item_index": 1,
                "division": "05 Metals",
                "title": "Parapet flashing",
                "quantity": 20.0,
                "unit": "LF",
                "unit_cost": 25.0,
                "total_cost": 500.0,
                "rule_refs": [],
                "multipliers_applied": [],
                "quantity_source": "explicit_takeoff",
                "evidence_refs": [],
                "flags": [],
            },
        ]
    }

    evidence_index = {
        "zone_evidence": [
            {
                "zone_id": "parapet_band",
                "zone_type": "work_zone",
                "label": "Parapet Band",
                "evidence_references": [],
                "linked_bid_items": [0, 1],  # Both items linked
            }
        ]
    }

    result = mapper.generate(
        project_id="test",
        model_3d=model_3d,
        bid_review=bid_review,
        evidence_index=evidence_index,
    )

    zone = result.zones[0]
    assert zone.total_cost == 1500.0  # 1000 + 500
    assert zone.division_breakdown["04 Masonry"] == 1000.0
    assert zone.division_breakdown["05 Metals"] == 500.0
    assert len(zone.top_line_items) == 2
    # Top item should be the one with higher cost
    assert zone.top_line_items[0].line_item_index == 0
    assert zone.top_line_items[0].total_cost == 1000.0
    assert zone.top_line_items[0].contribution_percent == pytest.approx(66.67, abs=0.1)


def test_min_max_cost_computation():
    """Test min/max cost computation for heatmap normalization."""
    mapper = ZoneCostMapper()

    model_3d = {
        "work_zones": [
            {
                "zone_name": "zone_1",
                "zone_type": "work_zone",
                "bounding_box": None,
                "facade_region": None,
                "page_number": 1,
                "evidence": "Zone 1",
            },
            {
                "zone_name": "zone_2",
                "zone_type": "work_zone",
                "bounding_box": None,
                "facade_region": None,
                "page_number": 1,
                "evidence": "Zone 2",
            },
            {
                "zone_name": "zone_3",
                "zone_type": "work_zone",
                "bounding_box": None,
                "facade_region": None,
                "page_number": 1,
                "evidence": "Zone 3",
            },
        ]
    }

    bid_review = {
        "line_items": [
            {
                "line_item_id": "line_item_0",
                "line_item_index": 0,
                "division": "04 Masonry",
                "title": "Item 1",
                "quantity": 10.0,
                "unit": "LF",
                "unit_cost": 10.0,
                "total_cost": 100.0,
                "rule_refs": [],
                "multipliers_applied": [],
                "quantity_source": "explicit_takeoff",
                "evidence_refs": [],
                "flags": [],
            },
            {
                "line_item_id": "line_item_1",
                "line_item_index": 1,
                "division": "04 Masonry",
                "title": "Item 2",
                "quantity": 20.0,
                "unit": "LF",
                "unit_cost": 20.0,
                "total_cost": 400.0,
                "rule_refs": [],
                "multipliers_applied": [],
                "quantity_source": "explicit_takeoff",
                "evidence_refs": [],
                "flags": [],
            },
        ]
    }

    evidence_index = {
        "zone_evidence": [
            {
                "zone_id": "zone_1",
                "zone_type": "work_zone",
                "label": "Zone 1",
                "evidence_references": [],
                "linked_bid_items": [0],  # 100.0
            },
            {
                "zone_id": "zone_2",
                "zone_type": "work_zone",
                "label": "Zone 2",
                "evidence_references": [],
                "linked_bid_items": [1],  # 400.0
            },
            # zone_3 has no links (0.0)
        ]
    }

    result = mapper.generate(
        project_id="test",
        model_3d=model_3d,
        bid_review=bid_review,
        evidence_index=evidence_index,
    )

    assert result.max_cost == 400.0
    assert result.min_cost == 100.0  # Excludes 0.0

