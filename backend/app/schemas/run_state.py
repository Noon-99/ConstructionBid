"""Run state schemas for resumable pipeline execution."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StageRunState(BaseModel):
    """State for a single pipeline stage execution."""

    stage_name: str = Field(description="Name of the stage (e.g., 'stage_1_document_analysis')")
    status: Literal["pending", "running", "succeeded", "failed", "skipped"] = Field(
        default="pending", description="Current status of the stage"
    )
    started_at: datetime | None = Field(
        default=None, description="When the stage started execution"
    )
    finished_at: datetime | None = Field(
        default=None, description="When the stage finished execution"
    )
    attempts: int = Field(
        default=0, ge=0, description="Number of execution attempts for this stage"
    )
    artifacts: dict[str, str] = Field(
        default_factory=dict,
        description="Dictionary of artifact names to file paths produced by this stage",
    )
    error: str | None = Field(
        default=None, description="Error message if stage failed (traceback summary)"
    )


class ProjectRunState(BaseModel):
    """Complete run state for a project pipeline execution."""

    project_id: str = Field(description="Project ID")
    current_stage: str | None = Field(
        default=None, description="Name of the currently running stage (if any)"
    )
    stages: list[StageRunState] = Field(
        default_factory=list, description="List of stage states"
    )
    last_updated: datetime = Field(
        default_factory=datetime.now, description="Last time the run state was updated"
    )






