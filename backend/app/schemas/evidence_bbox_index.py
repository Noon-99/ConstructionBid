"""Schema for evidence bbox index (Phase 8.6D).

Maps evidence snippets to bounding boxes in PDF coordinate space.
"""

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceBboxEntry(BaseModel):
    """Bounding box entry for a single evidence reference."""

    evidence_id: str = Field(
        description="Unique identifier for this evidence reference (e.g., 'bid_item_0_ref_1', 'zone_parapet_ref_0')"
    )
    page_number: int = Field(description="Page number (1-indexed)")
    snippet: str = Field(description="Evidence snippet text")
    bbox: dict[str, float] | None = Field(
        default=None,
        description="Bounding box {x0, y0, x1, y1} in PDF coordinate space (normalized 0-1) or image space",
    )
    bbox_source: Literal["pdf", "image", "none"] = Field(
        default="none",
        description="Source of bounding box: 'pdf' (PDF-native text search), 'image' (OCR), or 'none'",
    )
    match_confidence: float | None = Field(
        default=None,
        description="Confidence score (0-1) for the bbox match, if available"
    )
    match_method: str | None = Field(
        default=None,
        description="Method used to find bbox: 'text_search', 'fuzzy_match', 'ocr', etc."
    )


class EvidenceBboxIndex(BaseModel):
    """Complete evidence bbox index for a project (Phase 8.6D)."""

    project_id: str = Field(description="Project ID")
    generated_at: str = Field(description="ISO timestamp when index was generated")
    entries: list[EvidenceBboxEntry] = Field(
        default_factory=list,
        description="Bbox entries for each evidence reference"
    )
    metrics: dict[str, float | int] = Field(
        default_factory=dict,
        description="Extraction metrics: bbox_match_rate, avg_match_confidence, ocr_pages_processed, etc."
    )






