"""Run state storage service for resumable pipeline execution.

Provides atomic writes and safe reads for pipeline run state.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.run_state import ProjectRunState, StageRunState


class RunStateStore:
    """Manages persistent storage of pipeline run state."""

    def __init__(self, settings: Settings) -> None:
        """Initialize run state store with settings."""
        self.settings = settings
        self.storage_root = Path(settings.storage_root)

    def _get_state_path(self, project_id: str) -> Path:
        """Get the path to the run state file for a project."""
        project_dir = self.storage_root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir / "run_state.json"

    def load(self, project_id: str) -> ProjectRunState:
        """
        Load run state for a project.

        Returns a default ProjectRunState if file doesn't exist or is invalid.

        Args:
            project_id: Project ID

        Returns:
            ProjectRunState (default if missing/invalid)
        """
        state_path = self._get_state_path(project_id)

        if not state_path.exists():
            logger.bind(project_id=project_id).debug("Run state file not found, returning default state")
            return ProjectRunState(project_id=project_id)

        try:
            with open(state_path, "r") as f:
                data = json.load(f)

            # Validate and parse
            state = ProjectRunState.model_validate(data)
            logger.bind(project_id=project_id).debug(f"Loaded run state: {len(state.stages)} stages")
            return state

        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.bind(project_id=project_id).warning(
                f"Failed to load run state (invalid format): {e}. Returning default state."
            )
            return ProjectRunState(project_id=project_id)

    def save(self, state: ProjectRunState) -> None:
        """
        Save run state atomically (write temp file then rename).

        Args:
            state: ProjectRunState to save
        """
        state_path = self._get_state_path(state.project_id)

        # Update last_updated timestamp
        state.last_updated = datetime.now()

        # Write to temp file first
        temp_path = state_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w") as f:
                # Use model_dump_json for proper JSON serialization
                f.write(state.model_dump_json(indent=2))

            # Atomic rename
            temp_path.replace(state_path)

            logger.bind(project_id=state.project_id).debug(
                f"Saved run state: {len(state.stages)} stages, current_stage={state.current_stage}"
            )

        except Exception as e:
            logger.bind(project_id=state.project_id).error(f"Failed to save run state: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            raise

    def get_stage_state(self, project_id: str, stage_name: str) -> StageRunState | None:
        """
        Get the state for a specific stage.

        Args:
            project_id: Project ID
            stage_name: Name of the stage

        Returns:
            StageRunState if found, None otherwise
        """
        state = self.load(project_id)
        for stage in state.stages:
            if stage.stage_name == stage_name:
                return stage
        return None

    def update_stage_state(
        self,
        project_id: str,
        stage_name: str,
        status: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        artifacts: dict[str, str] | None = None,
        error: str | None = None,
        increment_attempts: bool = False,
    ) -> None:
        """
        Update the state for a specific stage.

        Args:
            project_id: Project ID
            stage_name: Name of the stage
            status: New status (optional)
            started_at: Start timestamp (optional)
            finished_at: Finish timestamp (optional)
            artifacts: Artifact paths dict (optional, merged with existing)
            error: Error message (optional)
            increment_attempts: If True, increment attempts counter
        """
        state = self.load(project_id)

        # Find or create stage state
        stage_state: StageRunState | None = None
        for stage in state.stages:
            if stage.stage_name == stage_name:
                stage_state = stage
                break

        if stage_state is None:
            stage_state = StageRunState(stage_name=stage_name)
            state.stages.append(stage_state)

        # Update fields
        if status is not None:
            stage_state.status = status
        if started_at is not None:
            stage_state.started_at = started_at
        if finished_at is not None:
            stage_state.finished_at = finished_at
        if artifacts is not None:
            stage_state.artifacts.update(artifacts)
        if error is not None:
            stage_state.error = error
        if increment_attempts:
            stage_state.attempts += 1

        # Update current_stage
        if status == "running":
            state.current_stage = stage_name
        elif status in ["succeeded", "failed", "skipped"]:
            if state.current_stage == stage_name:
                state.current_stage = None

        # Save updated state
        self.save(state)

