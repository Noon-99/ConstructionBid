"""Unit tests for typology resolver."""

import pytest

from app.schemas.document_analysis import (
    BuildingContext,
    DocumentAnalysis,
    QuantityLocator,
    ScopeLocator,
    SheetInfo,
)
from app.services.typology_resolver import resolve_typology


def test_row_house_renovation_becomes_repair() -> None:
    """Test that row-house renovation is changed to repair."""
    analysis = DocumentAnalysis(
        project_type="institutional",  # Misclassified
        scope_type="renovation",
        sheets=[
            SheetInfo(
                sheet_id="A-1",
                page_number=1,
                sheet_type="elevation",
                title="Row House Elevation",
            ),
        ],
        where_scope_lives=[
            ScopeLocator(
                sheet_id="A-1",
                page_number=1,
                location_type="elevation_notes",
                evidence="Row of attached buildings with party walls",
                confidence=0.9,
            ),
        ],
        where_quantities_live=[],
        where_materials_live=[],
        building_context=BuildingContext(
            building_type="institutional",
            is_row_context=False,
            building_ids=[],
            addresses=["123 Main St", "125 Main St", "127 Main St"],
            evidence="Multiple adjacent addresses",
        ),
        confidence=0.85,
        missing_fields=[],
    )

    resolved = resolve_typology(analysis)

    assert resolved.resolved_project_type == "row_house"
    assert resolved.resolved_scope_type == "repair"
    assert len(resolved.resolution_notes) > 0
    assert "row-house indicators detected" in " ".join(resolved.resolution_notes).lower()
    assert "renovation" in " ".join(resolved.resolution_notes).lower()
    assert "repair" in " ".join(resolved.resolution_notes).lower()


def test_institutional_no_override() -> None:
    """Test that institutional buildings without row-house indicators are not overridden."""
    analysis = DocumentAnalysis(
        project_type="institutional",
        scope_type="renovation",
        sheets=[
            SheetInfo(
                sheet_id="LS-1",
                page_number=1,
                sheet_type="plan",
                title="Life Safety Plan",
            ),
        ],
        where_scope_lives=[],
        where_quantities_live=[
            QuantityLocator(
                sheet_id="LS-1",
                page_number=1,
                location_type="life_safety_plan",
                evidence="Occupant load analysis",
                confidence=0.9,
            ),
        ],
        where_materials_live=[],
        building_context=BuildingContext(
            building_type="institutional",
            is_row_context=False,
            building_ids=[],
            addresses=["815 N MACON PARK DR, MACON, GA 31210"],
            evidence="Single institutional building",
        ),
        confidence=0.9,
        missing_fields=[],
    )

    resolved = resolve_typology(analysis)

    # No override should occur
    assert resolved.resolved_project_type is None
    assert resolved.resolved_scope_type is None
    assert len(resolved.resolution_notes) == 0


def test_elevation_dominates_life_safety_plan() -> None:
    """Test that elevation sheets dominate Life Safety Plans for typology."""
    analysis = DocumentAnalysis(
        project_type="institutional",  # Misclassified
        scope_type="renovation",
        sheets=[
            SheetInfo(
                sheet_id="A-1",
                page_number=1,
                sheet_type="elevation",
                title="Front Elevation - Row Houses",
            ),
            SheetInfo(
                sheet_id="LS-1",
                page_number=2,
                sheet_type="plan",
                title="Life Safety Plan",
            ),
        ],
        where_scope_lives=[
            ScopeLocator(
                sheet_id="A-1",
                page_number=1,
                location_type="elevation_notes",
                evidence="Adjacent buildings with shared walls",
                confidence=0.9,
            ),
        ],
        where_quantities_live=[
            QuantityLocator(
                sheet_id="LS-1",
                page_number=2,
                location_type="life_safety_plan",
                evidence="Occupant load",
                confidence=0.8,
            ),
        ],
        where_materials_live=[],
        building_context=BuildingContext(
            building_type="institutional",
            is_row_context=False,
            building_ids=[],
            addresses=[],
            evidence="Building context",
        ),
        confidence=0.85,
        missing_fields=[],
    )

    resolved = resolve_typology(analysis)

    assert resolved.resolved_project_type == "row_house"
    assert any(
        "elevation" in note.lower() and "dominate" in note.lower()
        for note in resolved.resolution_notes
    )


def test_townhouse_keyword_detection() -> None:
    """Test detection of townhouse keywords in sheet titles."""
    analysis = DocumentAnalysis(
        project_type="commercial",
        scope_type="renovation",
        sheets=[
            SheetInfo(
                sheet_id="A-1",
                page_number=1,
                sheet_type="elevation",
                title="Townhouse Elevation",
            ),
        ],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        building_context=None,
        confidence=0.8,
        missing_fields=[],
    )

    resolved = resolve_typology(analysis)

    assert resolved.resolved_project_type == "row_house"
    assert any("townhouse" in note.lower() for note in resolved.resolution_notes)


def test_multiple_addresses_detection() -> None:
    """Test detection of multiple addresses as row-house indicator."""
    analysis = DocumentAnalysis(
        project_type="institutional",
        scope_type="renovation",
        sheets=[],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        building_context=BuildingContext(
            building_type="institutional",
            is_row_context=False,
            building_ids=["B-1", "B-2", "B-3"],
            addresses=["123 Main St", "125 Main St", "127 Main St"],
            evidence="Multiple buildings",
        ),
        confidence=0.85,
        missing_fields=[],
    )

    resolved = resolve_typology(analysis)

    assert resolved.resolved_project_type == "row_house"
    assert any("multiple" in note.lower() for note in resolved.resolution_notes)


def test_no_changes_when_correct() -> None:
    """Test that correct classifications are not changed."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        sheets=[
            SheetInfo(
                sheet_id="A-1",
                page_number=1,
                sheet_type="elevation",
                title="Row House Elevation",
            ),
        ],
        where_scope_lives=[],
        where_quantities_live=[],
        where_materials_live=[],
        building_context=BuildingContext(
            building_type="row_house",
            is_row_context=True,
            building_ids=[],
            addresses=[],
            evidence="Row house",
        ),
        confidence=0.9,
        missing_fields=[],
    )

    resolved = resolve_typology(analysis)

    # Should not add resolution fields if no changes needed
    # (though it might still add notes for logging)
    # The key is that resolved_project_type and resolved_scope_type should match original
    if resolved.resolved_project_type is not None:
        assert resolved.resolved_project_type == "row_house"
    if resolved.resolved_scope_type is not None:
        assert resolved.resolved_scope_type == "repair"

