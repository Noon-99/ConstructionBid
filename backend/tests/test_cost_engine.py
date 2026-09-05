"""Unit tests for cost engine."""

import pytest
from pathlib import Path

from app.costing.cost_engine import CostEngine
from app.schemas.extraction_result import ExtractionResult
from app.schemas.geometry_for_3d import Dimensions, GeometryFor3D, SiteContext


@pytest.fixture
def cost_engine() -> CostEngine:
    """Create cost engine with default rules directory."""
    return CostEngine()


def test_cost_engine_loads_rules(cost_engine: CostEngine) -> None:
    """Test that cost engine loads YAML rules."""
    assert len(cost_engine.rules) > 0
    assert "parapet_rebuild" in cost_engine.rules
    assert "lintel_replacement" in cost_engine.rules


def test_match_scope_item_to_rule(cost_engine: CostEngine) -> None:
    """Test matching scope items to cost rules."""
    scope_item = {"item": "parapet repair", "description": "Parapet work"}
    rule = cost_engine._match_scope_item_to_rule(scope_item)
    assert rule is not None
    assert rule.get("name") == "parapet_rebuild"

    scope_item = {"item": "lintel replacement", "description": "Lintel work"}
    rule = cost_engine._match_scope_item_to_rule(scope_item)
    assert rule is not None
    assert rule.get("name") == "lintel_replacement"


def test_calculate_quantity(cost_engine: CostEngine) -> None:
    """Test quantity calculation."""
    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=30.0,
                evidence="Test",
                confidence=0.9,
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    scope_item = {"item": "parapet repair", "description": "Parapet work"}
    quantity, unit = cost_engine._calculate_quantity(scope_item, extraction)
    assert quantity > 0
    assert unit == "LF"  # Parapet is linear feet


def test_apply_multipliers(cost_engine: CostEngine) -> None:
    """Test multiplier application."""
    rule = {
        "height_multiplier": {
            "0-20": 1.0,
            "20-30": 1.15,
            "30-40": 1.30,
        },
        "material_multiplier": 1.2,
        "equipment_multiplier": 1.0,
    }

    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=25.0,  # Should trigger 20-30 multiplier
                evidence="Test",
                confidence=0.9,
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    base_cost = 100.0
    final_cost, multipliers = cost_engine._apply_multipliers(base_cost, rule, extraction)

    assert final_cost > base_cost
    assert "height" in multipliers
    assert multipliers["height"] == 1.15
    assert "material" in multipliers
    assert multipliers["material"] == 1.2


def test_compute_cost_basic(cost_engine: CostEngine) -> None:
    """Test basic cost computation."""
    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            {
                "item": "parapet repair",
                "description": "Parapet repair work",
                "location": "front facade",
                "page_number": 1,
                "sheet_id": "A-1",
                "evidence_snippet": "Parapet repair",
            },
            {
                "item": "lintel replacement",
                "description": "Replace 8 lintels",
                "location": "window openings",
                "page_number": 1,
                "sheet_id": "A-1",
                "evidence_snippet": "Replace lintel",
            },
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=30.0,
                evidence="Test",
                confidence=0.9,
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    result = cost_engine.compute_cost(extraction)

    assert result.total_cost > 0
    assert len(result.breakdown_by_category) > 0
    assert len(result.breakdown_by_scope_item) == 2
    assert result.material_cost_total > 0
    assert result.labor_cost_total > 0


def test_compute_cost_compliance_and_contingency(cost_engine: CostEngine) -> None:
    """Cost engine should surface compliance adders and contingency recommendation."""

    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            {
                "item": "parapet repair",
                "description": "Parapet repair work",
                "location": "front facade",
                "page_number": 1,
                "sheet_id": "A-1",
                "evidence_snippet": "Parapet repair",
            }
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=30.0,
                evidence="Test",
                confidence=0.9,
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    result = cost_engine.compute_cost(
        extraction,
        pricing_profile=None,
        labor_regime="prevailing_wage",
        prevailing_wage_multiplier=1.5,
        union_multiplier=1.2,
        requires_prevailing_wage=True,
        requires_bonds=True,
        requires_insurance=True,
        bond_rate_pct=2.5,
        insurance_rate_pct=1.2,
    )

    assert result.base_scope_cost > 0
    assert result.compliance_costs.get("bond") is not None
    assert result.compliance_costs.get("insurance") is not None
    assert result.compliance_total == pytest.approx(
        sum(result.compliance_costs.values()), rel=1e-6
    )
    assert result.total_cost == pytest.approx(
        result.base_scope_cost + result.compliance_total, rel=1e-6
    )
    assert result.contingency_recommendation_pct is not None
    assert result.contingency_recommendation_amount is not None


def test_compute_cost_with_regional_pricing(cost_engine: CostEngine) -> None:
    """Regional pricing profile should increase costs for high-cost markets."""

    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            {
                "item": "parapet repair",
                "description": "Parapet repair work",
                "location": "front facade",
                "page_number": 1,
                "sheet_id": "A-1",
                "evidence_snippet": "Parapet repair",
            }
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=30.0,
                evidence="Test",
                confidence=0.9,
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    from app.core.config import Settings
    from app.services.pricing_profile_service import load_profiles

    profiles = load_profiles(Settings())
    default_profile = profiles["default_national"]
    nyc_profile = profiles["nyc_2025q1"]

    default_result = cost_engine.compute_cost(
        extraction,
        pricing_profile=default_profile,
        labor_regime="standard",
    )

    nyc_result = cost_engine.compute_cost(
        extraction,
        pricing_profile=nyc_profile,
        labor_regime="standard",
    )

    assert nyc_result.total_cost > default_result.total_cost
    assert nyc_result.labor_cost_total > default_result.labor_cost_total
    assert nyc_result.profile_id == nyc_profile.profile_id


def test_compute_cost_with_waste_factor(cost_engine: CostEngine) -> None:
    """Test that waste factors are applied correctly."""
    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            {
                "item": "brick rebuild",
                "description": "Brick rebuild work",
                "location": "front facade",
                "page_number": 1,
                "sheet_id": "A-1",
                "evidence_snippet": "Brick rebuild",
            }
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            dimensions=Dimensions(
                width=20.0,
                depth=40.0,
                height=30.0,
                evidence="Test",
                confidence=0.9,
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    result = cost_engine.compute_cost(extraction)

    # Check that waste is applied
    brick_item = next(
        (item for item in result.breakdown_by_scope_item if "brick" in item.item_name.lower()),
        None,
    )
    assert brick_item is not None
    assert brick_item.waste_factor > 0


def test_missing_rule_warning(cost_engine: CostEngine) -> None:
    """Test that missing rules generate warnings."""
    extraction = ExtractionResult(
        project_type="row_house",
        scope_type="repair",
        scope_of_work=[
            {
                "item": "unknown work type",
                "description": "Unknown work",
                "location": "unknown",
                "page_number": 1,
                "sheet_id": "A-1",
                "evidence_snippet": "Unknown",
            }
        ],
        material_specifications=[],
        quantity_takeoff=[],
        geometry_for_3d=GeometryFor3D(
            site_context=SiteContext(
                building_type="row_house",
                row_of_buildings=[],
                addresses=[],
                evidence="Test",
            ),
            work_zones=[],
        ),
        validation_metadata={},
        evidence_missing=[],
    )

    result = cost_engine.compute_cost(extraction)

    assert len(result.missing_data_warnings) > 0
    assert any("unknown work type" in warning.lower() for warning in result.missing_data_warnings)






