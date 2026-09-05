"""Batch processing schemas for Phase 3.5."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class BatchCreateRequest(BaseModel):
    """Request to create a batch of project runs."""

    project_ids: list[str] = Field(
        description="List of project IDs to process in batch",
        min_length=1,
        max_length=500,
    )


class BatchItemStatus(BaseModel):
    """Status of a single batch item (project)."""

    project_id: str = Field(description="Project ID")
    job_id: str | None = Field(default=None, description="RQ job ID if enqueued")
    status: Literal["queued", "running", "succeeded", "failed"] = Field(
        description="Job status"
    )
    validation_passed: bool | None = Field(
        default=None, description="Validation passed flag (None if not available yet)"
    )
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Validation score (0.0-1.0, None if not available)",
    )


class BatchSummary(BaseModel):
    """Aggregated summary statistics for a batch."""

    # Totals
    count: int = Field(description="Total number of items in batch", ge=0)
    completed: int = Field(description="Number of completed items (succeeded or failed)", ge=0)
    passed: int = Field(description="Number of items that passed validation", ge=0)
    failed: int = Field(description="Number of items that failed validation", ge=0)
    queued: int = Field(description="Number of items still queued", ge=0)
    running: int = Field(description="Number of items currently running", ge=0)

    # Averages (only computed for completed items with metrics)
    avg_tokens: float | None = Field(
        default=None, description="Average total tokens across completed items"
    )
    avg_cost_usd: float | None = Field(
        default=None, description="Average cost in USD across completed items"
    )
    avg_latency_seconds: float | None = Field(
        default=None, description="Average latency in seconds across completed items"
    )
    avg_cache_hit_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Average cache hit rate percentage across completed items",
    )

    # Failure analysis
    top_failure_reasons: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Top failure reasons with counts, e.g., [{'code': 'MISSING_CRITICAL_SCOPE', 'count': 5}]",
    )


class BatchStatusResponse(BaseModel):
    """Complete batch status response."""

    batch_id: str = Field(description="Batch ID")
    created_at: datetime = Field(description="When the batch was created")
    items: list[BatchItemStatus] = Field(
        description="Status of each item in the batch"
    )
    summary: BatchSummary = Field(description="Aggregated summary statistics")

