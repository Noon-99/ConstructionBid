"""Document processing service for PDF to image conversion."""

from pathlib import Path

import fitz  # PyMuPDF
from loguru import logger

from app.core.config import Settings
from app.models.schemas import DocumentBundle
from app.services.storage import StorageService
from app.utils.timing import stage_timer


class DocumentProcessor:
    """Service for processing PDF documents into images."""

    def __init__(self, settings: Settings, storage_service: StorageService) -> None:
        """Initialize document processor with settings and storage service."""
        self.settings = settings
        self.storage_service = storage_service
        self.dpi = settings.pdf_dpi
        self.zoom = self.dpi / 72.0  # PyMuPDF uses zoom factor

    def process_pdf(self, project_id: str, pdf_path: Path) -> DocumentBundle:
        """Process PDF: extract page count and convert pages to images."""
        with stage_timer(project_id, "pdf_to_images"):
            logger.bind(project_id=project_id).info(
                f"Processing PDF: {pdf_path} at {self.dpi} DPI"
            )

            # Open PDF and get page count
            doc = fitz.open(pdf_path)
            page_count = len(doc)

            logger.bind(project_id=project_id).info(
                f"PDF has {page_count} pages"
            )

            # Ensure pages directory exists
            pages_dir = self.storage_service.ensure_pages_dir(project_id)

            # Convert each page to PNG and extract text
            page_image_paths: list[Path] = []
            page_texts: list[str] = []
            for page_num in range(page_count):
                page = doc[page_num]
                mat = fitz.Matrix(self.zoom, self.zoom)
                pix = page.get_pixmap(matrix=mat)
                image_path = pages_dir / f"page_{page_num + 1}.png"
                pix.save(str(image_path))
                page_image_paths.append(image_path)
                
                # Extract text from PDF page (not OCR - direct text extraction)
                try:
                    page_text = page.get_text()
                    page_texts.append(page_text)
                    if page_text.strip():
                        logger.bind(project_id=project_id).debug(
                            f"Extracted {len(page_text)} chars from page {page_num + 1}"
                        )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(
                        f"Failed to extract text from page {page_num + 1}: {e}"
                    )
                    page_texts.append("")  # Empty text if extraction fails

                logger.bind(project_id=project_id).debug(
                    f"Converted page {page_num + 1} to {image_path}"
                )

            doc.close()

            logger.bind(project_id=project_id).info(
                f"Converted {page_count} pages to images"
            )

            return DocumentBundle(
                project_id=project_id,
                source_pdf_path=pdf_path,
                page_count=page_count,
                page_image_paths=page_image_paths,
                page_texts=page_texts,
            )

