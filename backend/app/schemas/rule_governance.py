"""Schemas for cost rule governance and draft generation."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MissingRuleCandidate(BaseModel):
    """Scope item that lacks an associated cost rule."""

    item_name: str = Field(description="Scope item name that was not matched to a cost rule")
    description: str | None = Field(
        default=None, description="Detailed description of the work item if available"
    )
    page_number: int | None = Field(
        default=None, description="Page number where this scope item was detected (1-indexed)"
    )
    sheet_id: str | None = Field(
        default=None, description="Sheet identifier for additional context"
    )
    evidence_snippet: str | None = Field(
        default=None,
        description="Supporting snippet or callout pulled from the document",
    )
    detected_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords detected in the scope item that may guide rule authoring",
    )
    probable_trade: Literal[
        "masonry",
        "roofing",
        "concrete",
        "interiors",
        "mechanical",
        "plumbing",
        "electrical",
        "site",
        "structural",
        "unknown",
    ] = Field(default="unknown", description="Heuristic guess of the governing trade")
    draft_generated: bool = Field(
        default=False,
        description="True once a draft YAML rule has been authored for this scope item",
    )
    draft_filename: str | None = Field(
        default=None,
        description="Path to the generated YAML draft relative to the project output directory",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata captured at detection time (e.g., procurement flags)",
    )


class RuleGovernanceReport(BaseModel):
    """Aggregated report of missing cost rules and draft generation state."""

    project_id: str | None = Field(
        default=None, description="Project identifier associated with this governance report"
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the governance report was generated",
    )
    missing_rules: list[MissingRuleCandidate] = Field(
        default_factory=list,
        description="List of scope items that require new cost rules",
    )
    notes: list[str] = Field(
        default_factory=list, description="Supplemental notes or warnings for reviewers"
    )
