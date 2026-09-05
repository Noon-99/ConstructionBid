"""Tests for expanded scope schema (Phase 9.2A)."""

from datetime import datetime

import pytest

from app.schemas.evidence_index import EvidenceReference
from app.schemas.expanded_scope import ExpandedScope, ExpandedScopeItem


def test_expanded_scope_item_construction() -> None:
    """Test constructing an ExpandedScopeItem with all fields."""
    item = ExpandedScopeItem(
        item_id="scaffold_001",
        title="Scaffolding",
        division="01",
        quantity=4.0,
        unit="week",
        unit_cost=1200.0,
        total_cost=4800.0,
        reason="Required for parapet and facade work above 6ft",
        source="contractor_profile",
        confidence=1.0,
        evidence_refs=[],
        blocking=True,
    )

    assert item.item_id == "scaffold_001"
    assert item.title == "Scaffolding"
    assert item.division == "01"
    assert item.quantity == 4.0
    assert item.unit == "week"
    assert item.unit_cost == 1200.0
    assert item.total_cost == 4800.0
    assert item.reason == "Required for parapet and facade work above 6ft"
    assert item.source == "contractor_profile"
    assert item.confidence == 1.0
    assert item.blocking is True


def test_expanded_scope_item_minimal() -> None:
    """Test constructing an ExpandedScopeItem with minimal required fields."""
    item = ExpandedScopeItem(
        item_id="dumpster_001",
        title="Dumpster Rental",
        reason="Required for debris removal",
        source="rules",
        confidence=0.8,
    )

    assert item.item_id == "dumpster_001"
    assert item.title == "Dumpster Rental"
    assert item.division is None
    assert item.quantity is None
    assert item.unit is None
    assert item.unit_cost is None
    assert item.total_cost is None
    assert item.reason == "Required for debris removal"
    assert item.source == "rules"
    assert item.confidence == 0.8
    assert item.evidence_refs == []
    assert item.blocking is False  # Default


def test_expanded_scope_item_with_evidence() -> None:
    """Test ExpandedScopeItem with evidence references."""
    evidence = EvidenceReference(
        page_number=5,
        sheet_id="A-101",
        evidence_snippet="Scaffolding required for work above 6ft per OSHA",
        location_type="general_notes",
    )

    item = ExpandedScopeItem(
        item_id="scaffold_002",
        title="Scaffolding",
        reason="OSHA requirement for work above 6ft",
        source="rules",
        confidence=1.0,
        evidence_refs=[evidence],
    )

    assert len(item.evidence_refs) == 1
    assert item.evidence_refs[0].page_number == 5
    assert item.evidence_refs[0].sheet_id == "A-101"
    assert "OSHA" in item.evidence_refs[0].evidence_snippet


def test_expanded_scope_construction() -> None:
    """Test constructing an ExpandedScope with multiple items."""
    items = [
        ExpandedScopeItem(
            item_id="scaffold_001",
            title="Scaffolding",
            division="01",
            quantity=4.0,
            unit="week",
            unit_cost=1200.0,
            total_cost=4800.0,
            reason="Required for parapet work",
            source="contractor_profile",
            confidence=1.0,
        ),
        ExpandedScopeItem(
            item_id="dumpster_001",
            title="Dumpster Rental",
            division="01",
            quantity=2.0,
            unit="each",
            unit_cost=485.0,
            total_cost=970.0,
            reason="Debris removal",
            source="contractor_profile",
            confidence=0.9,
        ),
    ]

    expanded_scope = ExpandedScope(
        project_id="test_project_123",
        profile_id="nyc_row_house_masonry_v1",
        items=items,
    )

    assert expanded_scope.project_id == "test_project_123"
    assert expanded_scope.profile_id == "nyc_row_house_masonry_v1"
    assert len(expanded_scope.items) == 2
    assert expanded_scope.items[0].title == "Scaffolding"
    assert expanded_scope.items[1].title == "Dumpster Rental"
    assert isinstance(expanded_scope.created_at, datetime)


def test_expanded_scope_empty_items() -> None:
    """Test ExpandedScope with no items (empty list)."""
    expanded_scope = ExpandedScope(
        project_id="test_project_456",
        profile_id="nyc_row_house_masonry_v1",
        items=[],
    )

    assert expanded_scope.project_id == "test_project_456"
    assert expanded_scope.profile_id == "nyc_row_house_masonry_v1"
    assert len(expanded_scope.items) == 0


def test_expanded_scope_item_confidence_bounds() -> None:
    """Test that confidence must be between 0 and 1."""
    # Valid confidence values
    item1 = ExpandedScopeItem(
        item_id="test_001",
        title="Test Item",
        reason="Test",
        source="rules",
        confidence=0.0,
    )
    assert item1.confidence == 0.0

    item2 = ExpandedScopeItem(
        item_id="test_002",
        title="Test Item",
        reason="Test",
        source="rules",
        confidence=1.0,
    )
    assert item2.confidence == 1.0

    item3 = ExpandedScopeItem(
        item_id="test_003",
        title="Test Item",
        reason="Test",
        source="rules",
        confidence=0.5,
    )
    assert item3.confidence == 0.5

    # Invalid confidence values should raise validation error
    with pytest.raises(Exception):  # Pydantic validation error
        ExpandedScopeItem(
            item_id="test_004",
            title="Test Item",
            reason="Test",
            source="rules",
            confidence=1.5,  # > 1.0
        )

    with pytest.raises(Exception):  # Pydantic validation error
        ExpandedScopeItem(
            item_id="test_005",
            title="Test Item",
            reason="Test",
            source="rules",
            confidence=-0.1,  # < 0.0
        )






