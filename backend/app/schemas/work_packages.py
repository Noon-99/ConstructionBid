"""Schema for work packages (Phase 9.9).

Work packages group bid items into contractor-friendly sections based on keyword matching.
"""

from pydantic import BaseModel, Field


class WorkPackage(BaseModel):
    """A work package grouping related bid items."""

    package_id: str = Field(description="Unique identifier for this work package")
    title: str = Field(description="Work package title (e.g., 'Parapet Reconstruction')")
    line_item_ids: list[str] = Field(
        default_factory=list,
        description="List of line item IDs included in this package",
    )
    subtotal: float = Field(
        description="Total cost for all line items in this package"
    )
    keywords_matched: list[str] = Field(
        default_factory=list,
        description="Keywords that matched to create this package",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for this package grouping (0.0 to 1.0)",
    )






