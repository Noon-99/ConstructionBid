"""Utility for converting PDF pages to images in memory.

Uses PyMuPDF (fitz) for rendering - fast, local, no external dependencies.
PyMuPDF is already in the project dependencies.
"""

import base64
import io
from pathlib import Path

import fitz  # PyMuPDF
from loguru import logger

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage


def pdf_to_images(
    pdf_path: Path, settings: Settings, project_id: str | None = None
) -> list[PdfPageImage]:
    """
    Convert PDF pages to in-memory images (base64 encoded).

    Args:
        pdf_path: Path to PDF file
        settings: Application settings (for DPI)
        project_id: Optional project ID for logging

    Returns:
        List of PdfPageImage objects with base64-encoded PNG data

    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If PDF cannot be opened
    """
    log_ctx = logger.bind(project_id=project_id or "unknown")

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    log_ctx.info(f"Converting PDF to images: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        dpi = settings.pdf_dpi
        zoom = dpi / 72.0  # PyMuPDF uses zoom factor

        log_ctx.info(f"PDF has {page_count} pages, rendering at {dpi} DPI")

        pdf_images: list[PdfPageImage] = []

        for page_num in range(page_count):
            page = doc[page_num]
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PNG bytes in memory
            img_bytes = pix.tobytes("png")

            # Base64 encode
            base64_data = base64.b64encode(img_bytes).decode("utf-8")

            pdf_images.append(
                PdfPageImage(
                    page_number=page_num + 1,
                    image_base64=base64_data,
                    mime_type="image/png",
                )
            )

            log_ctx.debug(f"Converted page {page_num + 1} to base64 image")

        doc.close()

        log_ctx.info(f"Converted {page_count} pages to images in memory")
        return pdf_images

    except Exception as e:
        log_ctx.error(f"Error converting PDF to images: {e}")
        raise ValueError(f"Failed to convert PDF to images: {str(e)}") from e


def load_page_images_from_paths(page_image_paths: list[Path]) -> list[PdfPageImage]:
    """
    Load page images from file paths.

    Args:
        page_image_paths: List of paths to page image files

    Returns:
        List of PdfPageImage objects
    """
    images = []
    for path in page_image_paths:
        image_data = path.read_bytes()
        base64_data = base64.b64encode(image_data).decode("utf-8")
        images.append(
            PdfPageImage(
                page_number=int(path.stem.split("_")[-1]),
                image_base64=base64_data,
                mime_type="image/png",
            )
        )
    return images

