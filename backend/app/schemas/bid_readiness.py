"""Schema for bid readiness assessment (Phase 6.5)."""

from typing import Any

from pydantic import BaseModel, Field


class BidReadinessResult(BaseModel):
    """Result of bid readiness assessment."""

    bid_ready: bool = Field(description="True if bid is ready for submission")
    readiness_score: float = Field(
        ge=0.0, le=1.0, description="Readiness score (0.0 to 1.0)"
    )
    reasons_blocking: list[str] = Field(
        default_factory=list, description="Reasons why bid is not ready (if bid_ready=False)"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Warnings that don't block but should be reviewed"
    )
    derived_from: dict[str, Any] = Field(
        default_factory=dict,
        description="Source data used for assessment (validation_score, validation_passed, geometry_quality, etc.)",
    )
    readiness_stamp_text: str = Field(
        description="Text for proposal stamp (e.g., 'BID READY' or 'PRELIMINARY — REVIEW REQUIRED')"
    )

