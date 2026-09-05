"""PDF bbox overlay helper (Phase 10.4).

Utilities for normalizing and working with bounding boxes in PDF context.
"""

from typing import Any


def normalize_bbox(bbox: dict[str, float] | None) -> dict[str, float] | None:
    """
    Normalize bbox coordinates to 0-1 range (Phase 10.4).

    Args:
        bbox: Dictionary with x0, y0, x1, y1 (may be in pixels or 0-1)

    Returns:
        Normalized bbox with coordinates in 0-1 range, or None if invalid
    """
    if not bbox:
        return None

    x0 = bbox.get("x0", 0.0)
    y0 = bbox.get("y0", 0.0)
    x1 = bbox.get("x1", 0.0)
    y1 = bbox.get("y1", 0.0)

    # Validate
    if x1 <= x0 or y1 <= y0:
        return None

    # If coordinates are > 1.0, assume they're in pixels
    # Normalize by assuming standard page dimensions (e.g., 8.5x11 inches at 72 DPI = 612x792 px)
    # For now, we assume coordinates are already normalized (0-1)
    # This function is primarily for validation and future normalization logic

    # Ensure within 0-1 bounds
    x0 = max(0.0, min(1.0, x0))
    y0 = max(0.0, min(1.0, y0))
    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))

    if x1 <= x0 or y1 <= y0:
        return None

    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def bbox_to_pixels(
    bbox: dict[str, float],
    page_width_px: float,
    page_height_px: float,
) -> dict[str, float]:
    """
    Convert normalized bbox (0-1) to pixel coordinates (Phase 10.4).

    Args:
        bbox: Normalized bbox with x0, y0, x1, y1 in 0-1 range
        page_width_px: Page width in pixels
        page_height_px: Page height in pixels

    Returns:
        Bbox in pixel coordinates
    """
    return {
        "x0": bbox["x0"] * page_width_px,
        "y0": bbox["y0"] * page_height_px,
        "x1": bbox["x1"] * page_width_px,
        "y1": bbox["y1"] * page_height_px,
    }






