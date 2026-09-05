"""Unit tests for PDF bbox overlay helper (Phase 10.4)."""

import pytest

from app.services.pdf_bbox_overlay import normalize_bbox, bbox_to_pixels


def test_normalize_bbox_valid() -> None:
    """Test: Normalize valid bbox."""
    bbox = {"x0": 0.1, "y0": 0.2, "x1": 0.5, "y1": 0.6}
    result = normalize_bbox(bbox)

    assert result is not None
    assert result["x0"] == 0.1
    assert result["y0"] == 0.2
    assert result["x1"] == 0.5
    assert result["y1"] == 0.6


def test_normalize_bbox_clamps_to_bounds() -> None:
    """Test: Bbox coordinates are clamped to 0-1 range."""
    bbox = {"x0": -0.1, "y0": 0.2, "x1": 1.5, "y1": 0.6}
    result = normalize_bbox(bbox)

    assert result is not None
    assert result["x0"] == 0.0  # Clamped
    assert result["y0"] == 0.2
    assert result["x1"] == 1.0  # Clamped
    assert result["y1"] == 0.6


def test_normalize_bbox_invalid_returns_none() -> None:
    """Test: Invalid bbox (x1 <= x0 or y1 <= y0) returns None."""
    # x1 <= x0
    bbox1 = {"x0": 0.5, "y0": 0.2, "x1": 0.3, "y1": 0.6}
    assert normalize_bbox(bbox1) is None

    # y1 <= y0
    bbox2 = {"x0": 0.1, "y0": 0.6, "x1": 0.5, "y1": 0.2}
    assert normalize_bbox(bbox2) is None

    # None input
    assert normalize_bbox(None) is None


def test_bbox_to_pixels() -> None:
    """Test: Convert normalized bbox to pixel coordinates."""
    bbox = {"x0": 0.1, "y0": 0.2, "x1": 0.5, "y1": 0.6}
    page_width = 612.0  # 8.5in at 72 DPI
    page_height = 792.0  # 11in at 72 DPI

    result = bbox_to_pixels(bbox, page_width, page_height)

    assert result["x0"] == pytest.approx(61.2, rel=1e-6)
    assert result["y0"] == pytest.approx(158.4, rel=1e-6)
    assert result["x1"] == pytest.approx(306.0, rel=1e-6)
    assert result["y1"] == pytest.approx(475.2, rel=1e-6)






