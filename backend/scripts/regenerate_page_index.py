#!/usr/bin/env python3
"""Utility to regenerate Stage 0.5 page_index.json for a project.

This bypasses the PipelineOrchestrator skip logic so that we can
force-write the page index artifact even when the run state claims it
already exists.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from loguru import logger

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.models.schemas import DocumentBundle
from app.services.openai_client import OpenAIClient
from app.services.page_indexer import PageIndexer
from app.services.storage import StorageService
from app.utils.pdf_images import load_page_images_from_paths


def _collect_page_image_paths(pages_dir: Path) -> Sequence[Path]:
    if not pages_dir.exists():
        raise FileNotFoundError(f"Pages directory not found: {pages_dir}")

    image_paths = sorted(pages_dir.glob("page_*.png"))
    if not image_paths:
        raise FileNotFoundError(
            f"No page_* PNGs found in pages directory: {pages_dir}"
        )
    return image_paths


def regenerate_page_index(project_id: str, force_reindex: bool = True) -> Path:
    settings = get_settings()
    configure_logging(settings)

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY must be configured to run Stage 0.5")

    storage_service = StorageService(settings)
    pages_dir = storage_service.get_pages_dir(project_id)
    image_paths = _collect_page_image_paths(pages_dir)

    document_bundle = DocumentBundle(
        project_id=project_id,
        source_pdf_path=storage_service.get_source_pdf_path(project_id),
        page_count=len(image_paths),
        page_image_paths=list(image_paths),
    )

    logger.info(
        "Loaded document bundle for %s: %d pages", project_id, document_bundle.page_count
    )

    page_images = load_page_images_from_paths(document_bundle.page_image_paths)

    openai_client = OpenAIClient(settings)
    page_indexer = PageIndexer(settings, openai_client)

    # Ensure PageIndexer writes cache + artifacts into the repo-level out/ directory
    project_root = settings.storage_root.parent.parent
    desired_out_root = project_root / "out"
    desired_out_root.mkdir(parents=True, exist_ok=True)

    original_cwd = Path.cwd()
    try:
        os.chdir(project_root)
        page_index = page_indexer.index_pages(
            project_id,
            page_images,
            force_reindex=force_reindex,
        )
    finally:
        os.chdir(original_cwd)

    if hasattr(page_index, "model_dump_json"):
        output_dir = desired_out_root / project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "page_index.json"
        output_path.write_text(page_index.model_dump_json(indent=2))
        logger.success("Saved page index to %s", output_path)
        return output_path

    raise RuntimeError("Unexpected page index payload returned from PageIndexer")


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate page_index.json for a project")
    parser.add_argument("project_id", help="Target project ID (matches storage/out folders)")
    parser.add_argument(
        "--allow-cache",
        action="store_true",
        help="Allow reuse of cached per-page results instead of forcing reindex",
    )
    args = parser.parse_args()

    force = not args.allow_cache
    output_path = regenerate_page_index(args.project_id, force_reindex=force)
    print(f"Saved page index to {output_path}")


if __name__ == "__main__":
    main()
