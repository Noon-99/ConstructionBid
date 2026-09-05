"""Schema for validation report and issues."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    """Individual validation issue."""

    code: str = Field(
        description="Issue code (e.g., 'MISSING_CRITICAL_SCOPE', 'DIMENSION_CONFLICT', 'MISSING_GEOMETRY')"
    )
    severity: Literal["error", "warning"] = Field(description="Severity level")
    message: str = Field(description="Human-readable message")
    affected_fields: list[str] = Field(
        default_factory=list, description="List of affected field names"
    )
    recommended_action: str | None = Field(
        default=None, description="Recommended action to resolve the issue"
    )


class ValidationReport(BaseModel):
    """Complete validation report."""

    project_id: str = Field(description="Project ID")
    passed: bool = Field(description="Whether validation passed (no errors)")
    score: float = Field(
        ge=0.0, le=1.0, description="Validation score (0.0 to 1.0)"
    )
    issues: list[ValidationIssue] = Field(
        default_factory=list, description="List of validation issues"
    )
    missing_critical_items: list[str] = Field(
        default_factory=list, description="List of missing critical items"
    )
    conflicts: dict[str, Any] = Field(
        default_factory=dict, description="Detected conflicts (e.g., dimension mismatches)"
    )
    rerun_performed: bool = Field(
        default=False, description="Whether a targeted re-read was performed"
    )
    rerun_notes: list[str] = Field(
        default_factory=list, description="Notes about the re-read process"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="When the validation was performed"
    )






