"""Schema for page indexing results."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PageIndexItem(BaseModel):
    """Index entry for a single page."""

    page_number: int = Field(description="1-indexed page number")
    sheet_id: str | None = Field(
        default=None, description="Sheet ID if visible (e.g., 'A-1', 'S-2')"
    )
    sheet_title: str | None = Field(
        default=None, description="Sheet title if visible (e.g., 'Front Elevation')"
    )
    page_types: list[
        Literal[
            "plan",
            "elevation",
            "detail",
            "schedule",
            "notes",
            "compliance",
            "cover",
            "index",
            "unknown",
        ]
    ] = Field(
        default_factory=list,
        description="Classification of page types (can be multiple)",
    )
    indicators: list[str] = Field(
        default_factory=list,
        description="Key construction indicators found (e.g., 'dimensions', 'lintel', 'parapet', 'room_schedule', 'compliance')",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the classification (0.0 to 1.0)",
    )


class PageIndex(BaseModel):
    """Complete page index for a document."""

    project_id: str = Field(description="Project ID")
    pages: list[PageIndexItem] = Field(
        default_factory=list, description="Index entries for each page"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="When the index was created"
    )
    # Metadata fields (non-breaking additions for large PDF support)
    total_pages: int | None = Field(
        default=None, description="Total number of pages in the document"
    )
    indexed_pages: int | None = Field(
        default=None, description="Number of pages successfully indexed"
    )
    cached_pages: int | None = Field(
        default=None, description="Number of pages loaded from cache"
    )
    started_at: datetime | None = Field(
        default=None, description="When indexing started"
    )
    finished_at: datetime | None = Field(
        default=None, description="When indexing finished (None if incomplete)"
    )
    # Batch 4: Metrics for cost control and observability
    metrics: dict[str, Any] | None = Field(
        default=None,
        description="Metrics: indexed_pages_count, cache_hit_rate, retries_count, failed_pages_count",
    )


