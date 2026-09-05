"""Batch store for persisting batch manifests (Phase 3.5)."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.batch import BatchItemStatus, BatchStatusResponse


class BatchStore:
    """Manages persistent storage of batch manifests."""

    def __init__(self, settings: Settings) -> None:
        """Initialize batch store with settings."""
        self.settings = settings
        self.storage_root = Path(settings.storage_root)
        self.batches_dir = self.storage_root / "batches"
        self.batches_dir.mkdir(parents=True, exist_ok=True)

    def _get_batch_path(self, batch_id: str) -> Path:
        """Get the path to the batch manifest file."""
        return self.batches_dir / f"{batch_id}.json"

    def save(self, batch_status: BatchStatusResponse) -> None:
        """
        Save batch status atomically (write temp file then rename).

        Args:
            batch_status: BatchStatusResponse to save
        """
        batch_path = self._get_batch_path(batch_status.batch_id)

        # Write to temp file first
        temp_path = batch_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w") as f:
                # Use model_dump_json for proper JSON serialization
                f.write(batch_status.model_dump_json(indent=2))

            # Atomic rename
            temp_path.replace(batch_path)

            logger.debug(
                f"Saved batch manifest: {batch_status.batch_id} ({len(batch_status.items)} items)"
            )

        except Exception as e:
            logger.error(f"Failed to save batch manifest {batch_status.batch_id}: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            raise

    def load(self, batch_id: str) -> BatchStatusResponse | None:
        """
        Load batch status from disk.

        Args:
            batch_id: Batch ID

        Returns:
            BatchStatusResponse if found, None otherwise
        """
        batch_path = self._get_batch_path(batch_id)

        if not batch_path.exists():
            logger.debug(f"Batch manifest not found: {batch_id}")
            return None

        try:
            with open(batch_path, "r") as f:
                data = json.load(f)

            # Validate and parse
            batch_status = BatchStatusResponse.model_validate(data)
            logger.debug(f"Loaded batch manifest: {batch_id}")
            return batch_status

        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.warning(f"Failed to load batch manifest {batch_id} (invalid format): {e}")
            return None

    def update_item_status(
        self, batch_id: str, project_id: str, item_status: BatchItemStatus
    ) -> None:
        """
        Update status of a single item in a batch.

        Args:
            batch_id: Batch ID
            project_id: Project ID to update
            item_status: Updated item status
        """
        batch_status = self.load(batch_id)
        if not batch_status:
            raise ValueError(f"Batch {batch_id} not found")

        # Find and update the item
        updated = False
        for i, item in enumerate(batch_status.items):
            if item.project_id == project_id:
                batch_status.items[i] = item_status
                updated = True
                break

        if not updated:
            raise ValueError(f"Project {project_id} not found in batch {batch_id}")

        # Save updated batch
        self.save(batch_status)
        logger.debug(f"Updated item status in batch {batch_id}: {project_id} -> {item_status.status}")






