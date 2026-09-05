"""Pydantic models for request/response schemas."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

# Import DocumentAnalysis from the detailed schema module
from app.schemas.document_analysis import DocumentAnalysis

if TYPE_CHECKING:
    from app.schemas.model_3d import Model3D


class DocumentBundle(BaseModel):
    """Metadata and file paths for a processed document."""

    project_id: str
    source_pdf_path: Path
    page_count: int
    page_image_paths: list[Path] = Field(default_factory=list)
    page_texts: list[str] = Field(default_factory=list)  # Extracted text from PDF pages


# Import ExtractionResult from the detailed schema module
from app.schemas.extraction_result import ExtractionResult

# Keep ExtractionResults as alias for backward compatibility
ExtractionResults = ExtractionResult


class ValidationResults(BaseModel):
    """Stage 3: Validation results (stub)."""

    missing_critical: list[str] = Field(default_factory=list)
    needs_reread_pages: list[int] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProjectResult(BaseModel):
    """Complete project processing result."""

    project_id: str
    page_count: int
    status: str
    document_bundle: DocumentBundle
    document_analysis: DocumentAnalysis
    extraction: ExtractionResults
    validation: ValidationResults
    model_3d: Any | None = Field(
        default=None, description="3D model if Stage 3 was run (Model3D)"
    )
    costing_result: Any | None = Field(
        default=None, description="Costing result if Stage 4 was run (CostEngineResult)"
    )
    validation_report: Any | None = Field(
        default=None, description="Validation report from Stage 2.5 (ValidationReport)"
    )
    bid_proposal: Any | None = Field(
        default=None, description="Bid proposal if Stage 4 was run (BidProposal, Phase 4.6)"
    )


class UploadResponse(BaseModel):
    """Response for PDF upload endpoint."""

    project_id: str
    page_count: int
    status: str

