"""Schema for high-level project context summaries exposed to the UI."""

from typing import Any

from pydantic import BaseModel, Field


class SummaryScopeItem(BaseModel):
    description: str = Field(
        description="Short scope description (e.g., 'Roof membrane replacement')"
    )
    evidence_page: int | None = Field(
        default=None, description="Page number where evidence was found"
    )
    evidence_sheet: str | None = Field(
        default=None, description="Sheet identifier, if available"
    )


class SummaryMaterial(BaseModel):
    name: str = Field(description="Material name (e.g., 'TPO roof membrane')")
    application: str | None = Field(
        default=None, description="How the material is used"
    )
    evidence_page: int | None = Field(default=None, description="Evidence page")


class SummaryQuantity(BaseModel):
    item: str = Field(description="Quantity label (e.g., 'Roof area')")
    quantity: float = Field(description="Numeric quantity")
    unit: str = Field(description="Unit for the quantity")
    confidence: float | None = Field(
        default=None, description="0-1 confidence score if available"
    )
    source: str | None = Field(
        default=None, description="Quantity provenance (e.g., 'from_schedule')"
    )
    evidence_page: int | None = Field(default=None, description="Page number for evidence")


class SummaryWarning(BaseModel):
    message: str = Field(description="Warning or clarification text")
    severity: str = Field(description="Severity label (e.g., 'warning', 'info', 'critical')")


class ProjectContextSummary(BaseModel):
    project_id: str = Field(description="Project identifier")
    project_type: str | None = Field(
        default=None, description="High-level project typology"
    )
    scope_type: str | None = Field(
        default=None, description="Work classification (e.g., repair, replacement)"
    )
    primary_trade: str | None = Field(
        default=None, description="Dominant trade (e.g., 'roofing', 'windows')"
    )
    primary_division: str | None = Field(
        default=None, description="CSI division code if present"
    )
    location_summary: str | None = Field(
        default=None, description="Address or site context snippet"
    )
    scope_overview: list[SummaryScopeItem] = Field(
        default_factory=list, description="Key scope items"
    )
    materials: list[SummaryMaterial] = Field(
        default_factory=list, description="Key material specs"
    )
    quantities: list[SummaryQuantity] = Field(
        default_factory=list, description="High-confidence quantities"
    )
    warnings: list[SummaryWarning] = Field(
        default_factory=list, description="Warnings or clarifications"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Extra derived metadata for UI use"
    )
