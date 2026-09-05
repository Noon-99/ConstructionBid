"""Page image endpoints (Phase 8.6A)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from loguru import logger

from app.core.config import Settings, get_settings
from app.services.storage import StorageService
from app.services.document_processor import DocumentProcessor

def get_storage_service(settings: Settings = Depends(get_settings)) -> StorageService:
    """Dependency: Get storage service."""
    return StorageService(settings)

def get_document_processor(
    settings: Settings = Depends(get_settings),
    storage_service: StorageService = Depends(get_storage_service),
) -> DocumentProcessor:
    """Dependency: Get document processor."""
    from app.services.document_processor import DocumentProcessor
    return DocumentProcessor(settings, storage_service)

router = APIRouter(prefix="/projects", tags=["pages"])


@router.get("/{project_id}/pages")
async def list_pages(
    project_id: str,
    storage_service: StorageService = Depends(get_storage_service),
    document_processor: DocumentProcessor = Depends(get_document_processor),
) -> dict:
    """
    List all pages for a project.

    Returns:
        {
            "project_id": "abc123",
            "page_count": 9,
            "pages": [
                {"page_number": 1, "url": "/v1/projects/abc123/pages/1.png"},
                ...
            ]
        }
    """
    pages_dir = storage_service.get_pages_dir(project_id)
    pdf_path = storage_service.get_source_pdf_path(project_id)
    
    # Check if project exists
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Project '{project_id}' not found"
        )

    # Count PNG files matching page_{n}.png pattern
    page_files = sorted(pages_dir.glob("page_*.png")) if pages_dir.exists() else []
    page_count = len(page_files)

    # If no page images exist, generate them from the PDF
    if page_count == 0:
        logger.bind(project_id=project_id).info(
            "No page images found, generating on-demand from PDF"
        )
        try:
            document_bundle = document_processor.process_pdf(project_id, pdf_path)
            page_count = document_bundle.page_count
            # Refresh page files list
            page_files = sorted(pages_dir.glob("page_*.png"))
        except Exception as e:
            logger.bind(project_id=project_id).exception(
                f"Failed to generate page images: {e}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate page images: {str(e)}"
            )

    # Build page list
    pages = []
    for page_file in page_files:
        # Extract page number from filename (page_{n}.png)
        try:
            page_num_str = page_file.stem.split("_")[1]  # "page_1" -> "1"
            page_number = int(page_num_str)
        except (ValueError, IndexError):
            logger.warning(f"Invalid page filename: {page_file.name}, skipping")
            continue

        pages.append(
            {
                "page_number": page_number,
                "url": f"/v1/projects/{project_id}/pages/{page_number}.png",
            }
        )

    # Sort by page number
    pages.sort(key=lambda p: p["page_number"])

    return {
        "project_id": project_id,
        "page_count": page_count,
        "pages": pages,
    }


@router.get("/{project_id}/pages/{page_number}.png")
async def get_page_image(
    project_id: str,
    page_number: int,
    storage_service: StorageService = Depends(get_storage_service),
    document_processor: DocumentProcessor = Depends(get_document_processor),
) -> Response:
    """
    Stream a page image as PNG.
    
    If page images don't exist, generates them on-demand from the source PDF.

    Args:
        project_id: Project ID
        page_number: 1-indexed page number

    Returns:
        PNG image file response
    """
    # Validate page number
    if page_number < 1:
        raise HTTPException(status_code=400, detail="Page number must be >= 1")

    # Get page count first to validate range
    pages_dir = storage_service.get_pages_dir(project_id)
    pdf_path = storage_service.get_source_pdf_path(project_id)
    
    # Check if project exists
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Project '{project_id}' not found"
        )

    # Check if page images exist, if not generate them on-demand
    page_files = sorted(pages_dir.glob("page_*.png")) if pages_dir.exists() else []
    page_count = len(page_files)

    # If no page images exist, generate them from the PDF
    if page_count == 0:
        logger.bind(project_id=project_id).info(
            "No page images found, generating on-demand from PDF"
        )
        try:
            document_bundle = document_processor.process_pdf(project_id, pdf_path)
            page_count = document_bundle.page_count
            # Refresh page files list
            page_files = sorted(pages_dir.glob("page_*.png"))
        except Exception as e:
            logger.bind(project_id=project_id).exception(
                f"Failed to generate page images: {e}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate page images: {str(e)}"
            )

    if page_number > page_count:
        raise HTTPException(
            status_code=400,
            detail=f"Page number {page_number} out of range (max: {page_count})",
        )

    # Construct file path (deterministic: page_{n}.png)
    page_path = pages_dir / f"page_{page_number}.png"

    if not page_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Page {page_number} image not found for project '{project_id}'",
        )

    # Return file response
    return FileResponse(
        path=str(page_path),
        media_type="image/png",
        filename=f"page_{page_number}.png",
    )

