"""Unit tests for construction system assembly schema (Phase 14.1)."""

from datetime import datetime

import pytest

from app.schemas.construction_system_assembly import (
    ConstructionSystemAssembly,
    ConstructionSystemsResult,
    CostSummary,
    QuantitySummary,
    SystemSubcomponent,
)
from app.schemas.evidence_index import EvidenceReference


def test_quantity_summary_creation():
    """Test creating a QuantitySummary."""
    qty = QuantitySummary(
        primary_quantity=120.0,
        primary_unit="LF",
        secondary_quantities={"SF": 240.0, "EA": 8},
    )
    assert qty.primary_quantity == 120.0
    assert qty.primary_unit == "LF"
    assert qty.secondary_quantities == {"SF": 240.0, "EA": 8}


def test_cost_summary_creation():
    """Test creating a CostSummary."""
    cost = CostSummary(
        material_cost=5000.0, labor_cost=3000.0, equipment_cost=500.0, total_cost=8500.0
    )
    assert cost.material_cost == 5000.0
    assert cost.labor_cost == 3000.0
    assert cost.equipment_cost == 500.0
    assert cost.total_cost == 8500.0


def test_system_subcomponent_creation():
    """Test creating a SystemSubcomponent."""
    sub = SystemSubcomponent(
        category="demolition",
        description="Remove existing parapet",
        line_item_ids=["0", "1"],
    )
    assert sub.category == "demolition"
    assert sub.description == "Remove existing parapet"
    assert sub.line_item_ids == ["0", "1"]


def test_construction_system_assembly_creation():
    """Test creating a ConstructionSystemAssembly."""
    evidence_ref = EvidenceReference(
        page_number=1, sheet_id="A-1", evidence_snippet="Parapet detail", bbox=None
    )

    system = ConstructionSystemAssembly(
        id="parapet_reconstruction_001",
        system_type="parapet_reconstruction",
        description="Parapet reconstruction and repair",
        zones=["zone_1", "zone_2"],
        source_divisions=["04 Masonry"],
        base_scope_items=["0", "1", "2"],
        subcomponents=[
            SystemSubcomponent(
                category="demolition",
                description="Remove existing parapet",
                line_item_ids=["0"],
            ),
            SystemSubcomponent(
                category="structure",
                description="Rebuild parapet structure",
                line_item_ids=["1", "2"],
            ),
        ],
        quantities=QuantitySummary(primary_quantity=120.0, primary_unit="LF"),
        cost_summary=CostSummary(
            material_cost=5000.0,
            labor_cost=3000.0,
            equipment_cost=500.0,
            total_cost=8500.0,
        ),
        evidence_refs=[evidence_ref],
        confidence=0.85,
    )

    assert system.id == "parapet_reconstruction_001"
    assert system.system_type == "parapet_reconstruction"
    assert len(system.zones) == 2
    assert len(system.base_scope_items) == 3
    assert len(system.subcomponents) == 2
    assert system.confidence == 0.85


def test_construction_systems_result_creation():
    """Test creating a ConstructionSystemsResult."""
    system1 = ConstructionSystemAssembly(
        id="system_001",
        system_type="parapet_reconstruction",
        description="Parapet work",
        zones=[],
        source_divisions=[],
        base_scope_items=[],
        subcomponents=[],
        quantities=QuantitySummary(primary_quantity=100.0, primary_unit="LF"),
        cost_summary=CostSummary(
            material_cost=1000.0, labor_cost=500.0, equipment_cost=0.0, total_cost=1500.0
        ),
        evidence_refs=[],
        confidence=0.9,
    )

    result = ConstructionSystemsResult(
        project_id="test_project",
        systems=[system1],
        generated_at=datetime.now(),
        version="1.0",
    )

    assert result.project_id == "test_project"
    assert len(result.systems) == 1
    assert result.version == "1.0"


def test_construction_system_assembly_serialization():
    """Test that ConstructionSystemAssembly serializes to JSON correctly."""
    system = ConstructionSystemAssembly(
        id="test_system",
        system_type="lintel_replacement",
        description="Lintel replacement work",
        zones=["zone_1"],
        source_divisions=["05 Metals"],
        base_scope_items=["3"],
        subcomponents=[],
        quantities=QuantitySummary(primary_quantity=8.0, primary_unit="EA"),
        cost_summary=CostSummary(
            material_cost=2000.0, labor_cost=1500.0, equipment_cost=0.0, total_cost=3500.0
        ),
        evidence_refs=[],
        confidence=0.8,
    )

    # Serialize to dict (Pydantic handles JSON via model_dump)
    data = system.model_dump()
    assert data["id"] == "test_system"
    assert data["system_type"] == "lintel_replacement"
    assert data["confidence"] == 0.8

    # Deserialize from dict
    restored = ConstructionSystemAssembly.model_validate(data)
    assert restored.id == system.id
    assert restored.system_type == system.system_type
    assert restored.confidence == system.confidence


def test_construction_systems_result_serialization():
    """Test that ConstructionSystemsResult serializes to JSON correctly."""
    result = ConstructionSystemsResult(
        project_id="test_project",
        systems=[],
        generated_at=datetime(2024, 1, 1, 12, 0, 0),
        version="1.0",
    )

    data = result.model_dump(mode="json")
    assert data["project_id"] == "test_project"
    assert data["version"] == "1.0"
    assert isinstance(data["generated_at"], str)  # datetime serializes to ISO string in json mode

    # Deserialize
    restored = ConstructionSystemsResult.model_validate(data)
    assert restored.project_id == result.project_id
    assert restored.version == result.version

