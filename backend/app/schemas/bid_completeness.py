"""Schema for bid completeness gate (Phase 10.12A)."""

from typing import Any

from pydantic import BaseModel, Field


class BidCompletenessResult(BaseModel):
    """Bid completeness assessment result (Phase 10.12A)."""

    project_id: str = Field(description="Project ID")
    passed: bool = Field(
        description="True if bid passes completeness gate (all required sections present)"
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Completeness score (0.0 to 1.0) based on required sections present",
    )
    blockers: list[str] = Field(
        default_factory=list,
        description="Blocking issues that prevent bid from being ready",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings that don't block but should be noted",
    )
    required_sections: list[str] = Field(
        default_factory=list,
        description="List of required section keys (e.g., 'parapet', 'lintels', 'logistics')",
    )
    missing_sections: list[str] = Field(
        default_factory=list,
        description="List of required sections that are missing",
    )
    present_sections: list[str] = Field(
        default_factory=list,
        description="List of required sections that are present",
    )
    section_details: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Details about each section (line_item_count, evidence_ref_count, etc.)",
    )

