"""Unit tests for trade assemblies schema (Phase 9.1)."""

from datetime import datetime

import pytest

from app.schemas.trade_assemblies import (
    EquipmentComponent,
    LaborComponent,
    TradeAssembly,
    TradeAssembliesResult,
    TradeComponent,
)


class TestTradeComponent:
    """Test TradeComponent schema."""

    def test_trade_component_creation(self):
        """Test creating a TradeComponent with all fields."""
        component = TradeComponent(
            name="Aluminum Coping",
            unit="LF",
            qty=50.0,
            unit_cost=45.00,
            total_cost=2250.00,
            cost_source="ruleset",
            notes="5% waste applied",
        )
        assert component.name == "Aluminum Coping"
        assert component.qty == 50.0
        assert component.total_cost == 2250.00
        assert component.cost_source == "ruleset"

    def test_trade_component_serialization(self):
        """Test TradeComponent JSON serialization."""
        component = TradeComponent(
            name="Mortar Mix",
            unit="Bag",
            qty=12.5,
            unit_cost=8.00,
            total_cost=100.00,
            cost_source="ruleset",
        )
        data = component.model_dump()
        assert data["name"] == "Mortar Mix"
        assert data["qty"] == 12.5
        assert data["total_cost"] == 100.00

    def test_trade_component_optional_fields(self):
        """Test TradeComponent with optional fields."""
        component = TradeComponent(
            name="Component",
            unit="EA",
            qty=1.0,
            total_cost=100.00,
            cost_source="derived",
            notes=None,
        )
        assert component.notes is None
        assert component.unit_cost is None


class TestLaborComponent:
    """Test LaborComponent schema."""

    def test_labor_component_creation(self):
        """Test creating a LaborComponent."""
        labor = LaborComponent(
            trade="mason",
            crew=["mason", "laborer"],
            hours=16.0,
            rate=65.00,
            total_cost=1040.00,
            basis="Q / 25.0 * 8.0 hours",
        )
        assert labor.trade == "mason"
        assert len(labor.crew) == 2
        assert labor.hours == 16.0
        assert labor.total_cost == 1040.00

    def test_labor_component_serialization(self):
        """Test LaborComponent JSON serialization."""
        labor = LaborComponent(
            trade="carpenter",
            crew=[],
            hours=8.0,
            rate=60.00,
            total_cost=480.00,
            basis="8 hours per day",
        )
        data = labor.model_dump()
        assert data["trade"] == "carpenter"
        assert data["hours"] == 8.0


class TestEquipmentComponent:
    """Test EquipmentComponent schema."""

    def test_equipment_component_creation(self):
        """Test creating an EquipmentComponent."""
        equipment = EquipmentComponent(
            name="Scaffolding",
            unit="Week",
            qty=2.0,
            unit_cost=450.00,
            total_cost=900.00,
            basis="Required for exterior masonry work",
        )
        assert equipment.name == "Scaffolding"
        assert equipment.unit == "Week"
        assert equipment.total_cost == 900.00


class TestTradeAssembly:
    """Test TradeAssembly schema."""

    def test_trade_assembly_creation(self):
        """Test creating a TradeAssembly with all components."""
        components = [
            TradeComponent(
                name="Component 1",
                unit="LF",
                qty=50.0,
                unit_cost=10.00,
                total_cost=500.00,
                cost_source="ruleset",
            )
        ]
        labor = [
            LaborComponent(
                trade="mason",
                crew=["mason"],
                hours=8.0,
                rate=65.00,
                total_cost=520.00,
                basis="8 hours",
            )
        ]
        equipment = [
            EquipmentComponent(
                name="Scaffold",
                unit="Week",
                qty=1.0,
                unit_cost=450.00,
                total_cost=450.00,
                basis="Required",
            )
        ]

        assembly = TradeAssembly(
            id="parapet_001",
            title="Parapet Repair",
            division="04 Masonry",
            unit="LF",
            quantity=50.0,
            related_bid_item_ids=["0"],
            components=components,
            labor=labor,
            equipment=equipment,
            assumptions=["Weather permitting"],
            spec_refs=["04 21 13"],
            evidence_refs=[],
            ruleset_used="row_house_repair.yml",
        )

        assert assembly.id == "parapet_001"
        assert len(assembly.components) == 1
        assert len(assembly.labor) == 1
        assert len(assembly.equipment) == 1

    def test_trade_assembly_serialization(self):
        """Test TradeAssembly JSON serialization."""
        assembly = TradeAssembly(
            id="test_001",
            title="Test Assembly",
            division="04 Masonry",
            unit="SF",
            quantity=100.0,
        )
        data = assembly.model_dump()
        assert data["id"] == "test_001"
        assert data["quantity"] == 100.0
        assert isinstance(data["components"], list)
        assert isinstance(data["labor"], list)


class TestTradeAssembliesResult:
    """Test TradeAssembliesResult schema."""

    def test_trade_assemblies_result_creation(self):
        """Test creating a TradeAssembliesResult."""
        assemblies = [
            TradeAssembly(
                id="assembly_001",
                title="Assembly 1",
                division="04 Masonry",
                unit="LF",
                quantity=50.0,
            )
        ]

        result = TradeAssembliesResult(
            project_id="test_project",
            assemblies=assemblies,
            version="1.0",
        )

        assert result.project_id == "test_project"
        assert len(result.assemblies) == 1
        assert result.version == "1.0"
        assert isinstance(result.generated_at, datetime)

    def test_trade_assemblies_result_serialization(self):
        """Test TradeAssembliesResult JSON serialization."""
        result = TradeAssembliesResult(
            project_id="test_project",
            assemblies=[],
        )
        data = result.model_dump(mode="json")
        assert data["project_id"] == "test_project"
        assert isinstance(data["assemblies"], list)
        assert "generated_at" in data
        assert data["version"] == "1.0"





