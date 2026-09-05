#!/usr/bin/env python3
"""Force-generate Stage 0.5 page index for a project.

This bypasses the pipeline CLI/run state skip logic and writes out/PROJECT/page_index.json.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.openai_client import OpenAIClient
from app.services.page_indexer import PageIndexer
from app.services.storage import StorageService
from app.utils.pdf_images import load_page_images_from_paths


def _resolve_output_dir(settings, project_id: str) -> Path:
    """Mirror PipelineOrchestrator output directory resolution."""
    project_root = settings.storage_root.parent.parent
    output_dir = project_root / "out" / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def generate_page_index(project_id: str, force: bool = False) -> Path:
    """Generate page_index.json for the given project and return its path."""
    settings = get_settings()
    configure_logging(settings)

    storage_service = StorageService(settings)
    pdf_path = storage_service.get_source_pdf_path(project_id)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Source PDF not found for project {project_id}: {pdf_path}")

    pages_dir = storage_service.get_pages_dir(project_id)
    page_image_paths = sorted(
        pages_dir.glob("page_*.png"), key=lambda p: int(p.stem.split("_")[-1])
    )
    if not page_image_paths:
        raise FileNotFoundError(
            f"No page images found in {pages_dir}. Run Stage 0 first (pdf_to_images)."
        )

    logger.info(
        "Loading %d page images from %s", len(page_image_paths), pages_dir
    )
    page_images = load_page_images_from_paths(page_image_paths)

    openai_client = OpenAIClient(settings)
    page_indexer = PageIndexer(settings, openai_client)

    logger.info(
        "Indexing pages for project %s (force_reindex=%s)", project_id, force
    )
    page_index = page_indexer.index_pages(
        project_id, page_images, force_reindex=force
    )

    # Ensure we have a PageIndex instance (indexer can return dict when skipping)
    if not hasattr(page_index, "model_dump_json"):
        from app.schemas.page_index import PageIndex as PageIndexModel

        page_index = PageIndexModel.model_validate(page_index)

    output_dir = _resolve_output_dir(settings, project_id)
    output_path = output_dir / "page_index.json"
    output_path.write_text(page_index.model_dump_json(indent=2))

    logger.success("Wrote page index to %s", output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Force-generate Stage 0.5 page_index.json for a project"
    )
    parser.add_argument("project_id", help="Target project ID (e.g. 6558be4e)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-index every page even if cache exists",
    )
    args = parser.parse_args()

    try:
        output_path = generate_page_index(args.project_id, force=args.force)
        logger.info("Done. page_index.json ready at %s", output_path)
    except Exception as exc:  # pragma: no cover - diagnostic script
        logger.error("Failed to generate page index: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
