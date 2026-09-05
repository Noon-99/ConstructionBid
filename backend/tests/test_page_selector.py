"""Unit tests for page selector service."""

import pytest

from app.schemas.document_analysis import (
    BuildingContext,
    DocumentAnalysis,
    MaterialLocator,
    QuantityLocator,
    ScopeLocator,
    SheetInfo,
)
from app.services.page_selector import select_pages_for_stage1, select_pages_for_stage2


def test_select_pages_for_stage1_small_document() -> None:
    """Test page selection for small documents (<=4 pages)."""
    # All pages should be selected
    assert select_pages_for_stage1(1) == [0]
    assert select_pages_for_stage1(2) == [0, 1]
    assert select_pages_for_stage1(3) == [0, 1, 2]
    assert select_pages_for_stage1(4) == [0, 1, 2, 3]


def test_select_pages_for_stage1_large_document() -> None:
    """Test page selection for large documents (>4 pages)."""
    selected = select_pages_for_stage1(9)
    # Should have max 4 pages
    assert len(selected) <= 4
    # Should always include first page
    assert 0 in selected
    # Should always include last page
    assert 8 in selected
    # All indices should be valid
    assert all(0 <= i < 9 for i in selected)
    # Should be sorted
    assert selected == sorted(selected)


def test_select_pages_for_stage1_very_large_document() -> None:
    """Test page selection for very large documents."""
    selected = select_pages_for_stage1(50)
    assert len(selected) <= 4
    assert 0 in selected  # First page
    assert 49 in selected  # Last page
    assert all(0 <= i < 50 for i in selected)
    assert selected == sorted(selected)


def test_select_pages_for_stage1_empty() -> None:
    """Test page selection for empty document."""
    assert select_pages_for_stage1(0) == []


def test_select_pages_for_stage2_with_scope_locators() -> None:
    """Test Stage 2 page selection based on scope locators."""
    analysis = DocumentAnalysis(
        project_type="institutional",
        scope_type="renovation",
        sheets=[],
        where_scope_lives=[
            ScopeLocator(
                sheet_id="A-1",
                page_number=1,
                location_type="elevation_notes",
                evidence="Scope on page 1",
                confidence=0.9,
            ),
            ScopeLocator(
                sheet_id="A-2",
                page_number=3,
                location_type="general_notes",
                evidence="Scope on page 3",
                confidence=0.8,
            ),
        ],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.85,
        missing_fields=[],
    )

    result = select_pages_for_stage2(analysis)
    assert result["scope_pages"] == [0, 2]  # 1-indexed to 0-indexed
    assert result["quantity_pages"] == []
    assert result["materials_pages"] == []
    assert result["geometry_pages"] == []


def test_select_pages_for_stage2_with_all_locators() -> None:
    """Test Stage 2 page selection with all locator types."""
    analysis = DocumentAnalysis(
        project_type="commercial",
        scope_type="new_construction",
        sheets=[
            SheetInfo(
                sheet_id="A-1",
                page_number=2,
                sheet_type="plan",
                title="Floor Plan",
            ),
            SheetInfo(
                sheet_id="A-2",
                page_number=5,
                sheet_type="elevation",
                title="Front Elevation",
            ),
        ],
        where_scope_lives=[
            ScopeLocator(
                sheet_id="A-1",
                page_number=1,
                location_type="general_notes",
                evidence="Scope",
                confidence=0.9,
            ),
        ],
        where_quantities_live=[
            QuantityLocator(
                sheet_id="LS-1",
                page_number=2,
                location_type="life_safety_plan",
                evidence="Quantities",
                confidence=0.8,
            ),
        ],
        where_materials_live=[
            MaterialLocator(
                sheet_id="SO-1",
                page_number=3,
                location_type="specification_section",
                evidence="Materials",
                confidence=0.85,
            ),
        ],
        confidence=0.9,
        missing_fields=[],
    )

    result = select_pages_for_stage2(analysis)
    assert result["scope_pages"] == [0]  # page 1 -> index 0
    assert result["quantity_pages"] == [1]  # page 2 -> index 1
    assert result["materials_pages"] == [2]  # page 3 -> index 2
    # Geometry pages from sheets (page 2 and 5 -> indices 1 and 4)
    assert set(result["geometry_pages"]) == {1, 4}


def test_select_pages_for_stage2_deduplication() -> None:
    """Test that Stage 2 selection deduplicates pages."""
    analysis = DocumentAnalysis(
        project_type="row_house",
        scope_type="repair",
        sheets=[],
        where_scope_lives=[
            ScopeLocator(
                sheet_id="A-1",
                page_number=2,
                location_type="elevation_notes",
                evidence="Scope",
                confidence=0.9,
            ),
            ScopeLocator(
                sheet_id="A-2",
                page_number=2,  # Duplicate page
                location_type="general_notes",
                evidence="More scope",
                confidence=0.8,
            ),
        ],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.85,
        missing_fields=[],
    )

    result = select_pages_for_stage2(analysis)
    # Should only have page 2 once (index 1)
    assert result["scope_pages"] == [1]
    assert len(result["scope_pages"]) == 1


def test_select_pages_for_stage2_sorted() -> None:
    """Test that Stage 2 selection returns sorted pages."""
    analysis = DocumentAnalysis(
        project_type="institutional",
        scope_type="renovation",
        sheets=[],
        where_scope_lives=[
            ScopeLocator(
                sheet_id="A-3",
                page_number=5,
                location_type="general_notes",
                evidence="Scope",
                confidence=0.9,
            ),
            ScopeLocator(
                sheet_id="A-1",
                page_number=1,
                location_type="elevation_notes",
                evidence="Scope",
                confidence=0.9,
            ),
            ScopeLocator(
                sheet_id="A-2",
                page_number=3,
                location_type="schedule",
                evidence="Scope",
                confidence=0.9,
            ),
        ],
        where_quantities_live=[],
        where_materials_live=[],
        confidence=0.85,
        missing_fields=[],
    )

    result = select_pages_for_stage2(analysis)
    # Should be sorted: pages 1, 3, 5 -> indices 0, 2, 4
    assert result["scope_pages"] == [0, 2, 4]
    assert result["scope_pages"] == sorted(result["scope_pages"])

