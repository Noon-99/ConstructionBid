"""Schema for export requests (Phase 6.6)."""

from pydantic import BaseModel, Field


class ExportProposalsRequest(BaseModel):
    """Request to export proposal PDFs as ZIP."""

    project_ids: list[str] = Field(
        description="List of project IDs to export (1-500 allowed)",
        min_length=1,
        max_length=500,
    )
    include_manifest: bool = Field(
        default=True, description="Include manifest.json in ZIP"
    )
    fail_if_missing_pdf: bool = Field(
        default=False,
        description="If True, return 409 error if any PDF is missing. If False, skip missing PDFs.",
    )






