"""Batch processing API routes (Phase 3.5)."""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from app.core.config import Settings, get_settings
from app.schemas.batch import BatchCreateRequest, BatchStatusResponse
from app.services.batch_service import BatchService
from app.services.batch_store import BatchStore
from app.services.job_queue import JobQueueService
from app.services.run_state_store import RunStateStore

router = APIRouter(prefix="/batches", tags=["batches"])


def get_job_queue_service(
    settings: Settings = Depends(get_settings),
) -> JobQueueService:
    """Dependency: Get job queue service."""
    return JobQueueService(settings)


def get_batch_store(settings: Settings = Depends(get_settings)) -> BatchStore:
    """Dependency: Get batch store."""
    return BatchStore(settings)


def get_run_state_store(
    settings: Settings = Depends(get_settings),
) -> RunStateStore:
    """Dependency: Get run state store."""
    return RunStateStore(settings)


def get_batch_service(
    settings: Settings = Depends(get_settings),
    job_queue: JobQueueService = Depends(get_job_queue_service),
    batch_store: BatchStore = Depends(get_batch_store),
    run_state_store: RunStateStore = Depends(get_run_state_store),
) -> BatchService:
    """Dependency: Get batch service."""
    return BatchService(settings, job_queue, batch_store, run_state_store)


@router.post("", response_model=BatchStatusResponse)
async def create_batch(
    request: BatchCreateRequest,
    batch_service: BatchService = Depends(get_batch_service),
) -> BatchStatusResponse:
    """
    Create a batch of project runs.

    Args:
        request: Batch create request with list of project IDs

    Returns:
        BatchStatusResponse with batch_id and initial status
    """
    logger.info(f"Creating batch with {len(request.project_ids)} projects")

    try:
        batch_status = batch_service.create_batch(request.project_ids)
        logger.bind(batch_id=batch_status.batch_id).info(
            f"Batch created: {batch_status.batch_id} with {len(batch_status.items)} items"
        )
        return batch_status
    except Exception as e:
        logger.error(f"Failed to create batch: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create batch: {str(e)}")


@router.get("/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status(
    batch_id: str,
    batch_service: BatchService = Depends(get_batch_service),
) -> BatchStatusResponse:
    """
    Get current status of a batch.

    Args:
        batch_id: Batch ID

    Returns:
        BatchStatusResponse with current status and summary

    Raises:
        HTTPException: If batch not found
    """
    logger.bind(batch_id=batch_id).debug("Getting batch status")

    batch_status = batch_service.get_batch_status(batch_id)
    if not batch_status:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    return batch_status






