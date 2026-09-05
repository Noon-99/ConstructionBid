"""Storage service for managing project files."""

from pathlib import Path

from loguru import logger

from app.core.config import Settings


class StorageService:
    """Service for managing file storage operations."""

    def __init__(self, settings: Settings) -> None:
        """Initialize storage service with settings."""
        self.settings = settings
        self.storage_root = settings.storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def get_project_dir(self, project_id: str) -> Path:
        """Get the storage directory for a project."""
        return self.storage_root / project_id

    def get_source_pdf_path(self, project_id: str) -> Path:
        """Get the path for the source PDF file."""
        return self.get_project_dir(project_id) / "source.pdf"

    def get_pages_dir(self, project_id: str) -> Path:
        """Get the directory for page images."""
        return self.get_project_dir(project_id) / "pages"

    def save_pdf(self, project_id: str, file_content: bytes) -> Path:
        """Save uploaded PDF to disk."""
        project_dir = self.get_project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = self.get_source_pdf_path(project_id)
        pdf_path.write_bytes(file_content)

        logger.bind(project_id=project_id).info(
            f"Saved PDF to {pdf_path} ({len(file_content)} bytes)"
        )

        return pdf_path

    def ensure_pages_dir(self, project_id: str) -> Path:
        """Ensure pages directory exists and return its path."""
        pages_dir = self.get_pages_dir(project_id)
        pages_dir.mkdir(parents=True, exist_ok=True)
        return pages_dir

