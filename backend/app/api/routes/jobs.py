"""Job status endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from app.core.config import Settings, get_settings
from app.services.job_queue import JobQueueService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_queue_service(
    settings: Settings = Depends(get_settings),
) -> JobQueueService:
    """Dependency: Get job queue service."""
    return JobQueueService(settings)


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    job_queue: JobQueueService = Depends(get_job_queue_service),
) -> dict[str, Any]:
    """
    Get status of a job.

    Returns job status, project_id, timestamps, and error if failed.
    """
    logger.bind(job_id=job_id).debug("Getting job status")

    status = job_queue.get_job_status(job_id)

    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return status

