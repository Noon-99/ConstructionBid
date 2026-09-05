"""Schema for bid readiness v2 assessment (Phase 10.1).

Separates conceptual readiness from contractor readiness.
"""

from typing import Any

from pydantic import BaseModel, Field


class BidReadinessV2Result(BaseModel):
    """Result of bid readiness v2 assessment (Phase 10.1)."""

    conceptual_ready: bool = Field(
        description="True if conceptual bid is ready (existing logic)"
    )
    contractor_ready: bool = Field(
        description="True if contractor bid is ready (new logic)"
    )
    blocking_reasons_contractor: list[str] = Field(
        default_factory=list,
        description="Reasons why contractor bid is not ready",
    )
    warnings_contractor: list[str] = Field(
        default_factory=list,
        description="Warnings for contractor bid that don't block",
    )
    # Include original readiness for backward compatibility
    derived_from: dict[str, Any] = Field(
        default_factory=dict,
        description="Source data used for assessment",
    )






