"""Schema for quantity normalization report (Phase 10.11A)."""

from typing import Literal

from pydantic import BaseModel, Field


class QuantityChange(BaseModel):
    """A single quantity normalization change."""

    line_item_index: int = Field(description="Index of the bid_proposal line item that was changed")
    rule_applied: str = Field(description="Normalization rule that was applied (e.g., 'flashing_lf_from_perimeter', 'repointing_sf_from_area')")
    old_value: float | None = Field(description="Original quantity value")
    new_value: float = Field(description="Normalized quantity value")
    old_unit: str = Field(description="Original unit (e.g., 'EA', 'LF', 'SF')")
    new_unit: str = Field(description="Normalized unit (e.g., 'LF', 'SF')")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the normalization (0.0 to 1.0)"
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="List of evidence references used (e.g., detail IDs, page numbers, dimension sources)",
    )
    computation_formula: str | None = Field(
        default=None, description="Formula used to compute the new value (if applicable)"
    )
    flag: Literal["unit_unknown", "insufficient_evidence", "normalized"] = Field(
        default="normalized",
        description="Flag indicating the normalization result",
    )


class QuantityNormalizationReport(BaseModel):
    """Complete quantity normalization report (Phase 10.11A)."""

    project_id: str = Field(description="Project ID")
    changes: list[QuantityChange] = Field(
        default_factory=list, description="List of all quantity changes made"
    )
    items_normalized: int = Field(
        description="Number of line items that were normalized"
    )
    items_flagged: int = Field(
        description="Number of line items flagged but not changed (insufficient evidence)"
    )
    items_unchanged: int = Field(
        description="Number of line items that were not modified"
    )





