"""Export endpoints for bulk operations (Phase 6.6)."""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from app.core.config import Settings, get_settings
from app.schemas.export import ExportProposalsRequest
from app.services.zip_exporter import export_proposals_zip

router = APIRouter(prefix="/projects/export", tags=["exports"])


@router.post("/proposals.zip")
async def export_proposals_zip_endpoint(
    request: ExportProposalsRequest,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """
    Export proposal PDFs as a ZIP file with manifest (Phase 6.6).

    Returns a ZIP containing:
    - proposals/{project_id}_{STAMP}.pdf for each project
    - manifest.json with metadata

    Args:
        request: Export request with project_ids and options
        settings: Application settings

    Returns:
        StreamingResponse with application/zip

    Raises:
        409: If fail_if_missing_pdf=True and any PDF is missing
        400: If no project_ids provided
    """
    log_ctx = logger.bind(
        endpoint="export_proposals_zip",
        project_count=len(request.project_ids),
    )
    log_ctx.info("Starting bulk proposal export")

    if not request.project_ids:
        raise HTTPException(status_code=400, detail="project_ids list cannot be empty")

    if len(request.project_ids) > 500:
        raise HTTPException(
            status_code=400, detail="Maximum 500 project_ids allowed per export"
        )

    try:
        # Generate ZIP
        zip_buffer, manifest_entries = export_proposals_zip(
            project_ids=request.project_ids,
            output_dir=Path("out"),
            include_manifest=request.include_manifest,
            fail_if_missing_pdf=request.fail_if_missing_pdf,
        )

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"proposals_export_{timestamp}.zip"

        log_ctx.info(f"Export complete: {filename}")

        # Reset buffer position for reading
        zip_buffer.seek(0)

        def generate():
            """Generator for streaming ZIP content."""
            chunk_size = 8192
            while True:
                chunk = zip_buffer.read(chunk_size)
                if not chunk:
                    break
                yield chunk
            zip_buffer.close()

        return StreamingResponse(
            generate(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/zip",
            },
        )

    except FileNotFoundError as e:
        log_ctx.error(f"Export failed: {e}")
        raise HTTPException(
            status_code=409,
            detail=f"Export failed: One or more PDFs are missing. {str(e)}",
        )
    except Exception as e:
        log_ctx.exception(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

