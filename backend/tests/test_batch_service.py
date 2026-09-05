"""Unit tests for batch service (Phase 3.5)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.schemas.batch import BatchItemStatus, BatchStatusResponse
from app.services.batch_service import BatchService
from app.services.batch_store import BatchStore
from app.services.job_queue import JobHandle, JobQueueService
from app.services.run_state_store import RunStateStore


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        storage_root=Path("./test_storage"),
        redis_url="redis://localhost:6379/0",
    )


@pytest.fixture
def temp_storage_dir() -> Path:
    """Create a temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_job_queue() -> MagicMock:
    """Create a mock job queue service."""
    queue = MagicMock(spec=JobQueueService)
    return queue


@pytest.fixture
def batch_store(settings: Settings, temp_storage_dir: Path) -> BatchStore:
    """Create a batch store with temporary storage."""
    settings.storage_root = temp_storage_dir
    return BatchStore(settings)


@pytest.fixture
def run_state_store(settings: Settings, temp_storage_dir: Path) -> RunStateStore:
    """Create a run state store with temporary storage."""
    settings.storage_root = temp_storage_dir
    return RunStateStore(settings)


@pytest.fixture
def batch_service(
    settings: Settings,
    mock_job_queue: MagicMock,
    batch_store: BatchStore,
    run_state_store: RunStateStore,
) -> BatchService:
    """Create a batch service with mocked dependencies."""
    return BatchService(settings, mock_job_queue, batch_store, run_state_store)


def test_create_batch_enqueues_jobs(
    batch_service: BatchService,
    mock_job_queue: MagicMock,
    batch_store: BatchStore,
) -> None:
    """Test that create_batch enqueues all projects and stores manifest."""
    project_ids = ["proj1", "proj2", "proj3"]
    
    # Mock job queue to return handles
    def mock_enqueue(project_id: str) -> JobHandle:
        return JobHandle(job_id=f"job_{project_id}", project_id=project_id)
    
    mock_job_queue.enqueue_project_run.side_effect = mock_enqueue
    
    # Create batch
    batch_status = batch_service.create_batch(project_ids)
    
    # Verify all jobs were enqueued
    assert mock_job_queue.enqueue_project_run.call_count == 3
    assert len(batch_status.items) == 3
    assert batch_status.summary.count == 3
    assert batch_status.summary.queued == 3
    
    # Verify items have correct status
    for item in batch_status.items:
        assert item.status == "queued"
        assert item.project_id in project_ids
        assert item.job_id is not None
    
    # Verify batch was stored
    loaded = batch_store.load(batch_status.batch_id)
    assert loaded is not None
    assert loaded.batch_id == batch_status.batch_id
    assert len(loaded.items) == 3


def test_create_batch_handles_enqueue_failure(
    batch_service: BatchService,
    mock_job_queue: MagicMock,
) -> None:
    """Test that create_batch handles job enqueue failures gracefully."""
    project_ids = ["proj1", "proj2"]
    
    # First job succeeds, second fails
    def mock_enqueue(project_id: str) -> JobHandle:
        if project_id == "proj1":
            return JobHandle(job_id="job_proj1", project_id="proj1")
        raise Exception("Queue connection failed")
    
    mock_job_queue.enqueue_project_run.side_effect = mock_enqueue
    
    # Create batch
    batch_status = batch_service.create_batch(project_ids)
    
    # Verify both items are in the batch, one queued, one failed
    assert len(batch_status.items) == 2
    assert batch_status.items[0].status == "queued"
    assert batch_status.items[1].status == "failed"
    assert batch_status.items[1].job_id is None


def test_get_batch_status_updates_from_job_queue(
    batch_service: BatchService,
    mock_job_queue: MagicMock,
    batch_store: BatchStore,
) -> None:
    """Test that get_batch_status updates item statuses from job queue."""
    project_ids = ["proj1", "proj2"]
    
    # Create a batch first
    def mock_enqueue(project_id: str) -> JobHandle:
        return JobHandle(job_id=f"job_{project_id}", project_id=project_id)
    
    mock_job_queue.enqueue_project_run.side_effect = mock_enqueue
    batch_status = batch_service.create_batch(project_ids)
    batch_id = batch_status.batch_id
    
    # Mock job status responses
    def mock_get_status(job_id: str) -> dict:
        if job_id == "job_proj1":
            return {"job_id": job_id, "status": "finished", "project_id": "proj1"}
        elif job_id == "job_proj2":
            return {"job_id": job_id, "status": "started", "project_id": "proj2"}
        return {"job_id": job_id, "status": "queued", "project_id": "unknown"}
    
    mock_job_queue.get_job_status.side_effect = mock_get_status
    
    # Get batch status
    updated_status = batch_service.get_batch_status(batch_id)
    
    assert updated_status is not None
    assert updated_status.batch_id == batch_id
    assert len(updated_status.items) == 2
    
    # Check statuses are updated
    proj1_item = next(item for item in updated_status.items if item.project_id == "proj1")
    proj2_item = next(item for item in updated_status.items if item.project_id == "proj2")
    
    assert proj1_item.status == "succeeded"
    assert proj2_item.status == "running"


def test_get_batch_status_computes_summary_with_metrics(
    batch_service: BatchService,
    mock_job_queue: MagicMock,
    batch_store: BatchStore,
    temp_storage_dir: Path,
) -> None:
    """Test that get_batch_status computes summary from metrics and validation reports."""
    project_ids = ["proj1"]
    
    # Create batch
    def mock_enqueue(project_id: str) -> JobHandle:
        return JobHandle(job_id=f"job_{project_id}", project_id=project_id)
    
    mock_job_queue.enqueue_project_run.side_effect = mock_enqueue
    batch_status = batch_service.create_batch(project_ids)
    batch_id = batch_status.batch_id
    
    # Create output directory and mock metrics/validation files
    output_dir = Path("out") / "proj1"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Mock metrics.json
    metrics_data = {
        "project_id": "proj1",
        "total_tokens": 1000,
        "total_cost_estimate_usd": 0.50,
        "total_latency_seconds": 10.5,
        "cache_hit_rate": 75.0,
    }
    with open(output_dir / "metrics.json", "w") as f:
        json.dump(metrics_data, f)
    
    # Mock validation_report.json
    validation_data = {
        "project_id": "proj1",
        "passed": True,
        "score": 0.95,
        "issues": [],
    }
    with open(output_dir / "validation_report.json", "w") as f:
        json.dump(validation_data, f)
    
    # Mock job status
    mock_job_queue.get_job_status.return_value = {
        "job_id": "job_proj1",
        "status": "finished",
        "project_id": "proj1",
    }
    
    # Get batch status
    updated_status = batch_service.get_batch_status(batch_id)
    
    assert updated_status is not None
    assert updated_status.summary.completed == 1
    assert updated_status.summary.passed == 1
    assert updated_status.summary.avg_tokens == 1000.0
    assert updated_status.summary.avg_cost_usd == 0.50
    assert updated_status.summary.avg_latency_seconds == 10.5
    assert updated_status.summary.avg_cache_hit_rate == 75.0


def test_get_batch_status_computes_top_failure_reasons(
    batch_service: BatchService,
    mock_job_queue: MagicMock,
    batch_store: BatchStore,
) -> None:
    """Test that get_batch_status computes top failure reasons from validation reports."""
    project_ids = ["proj1", "proj2", "proj3"]
    
    # Create batch
    def mock_enqueue(project_id: str) -> JobHandle:
        return JobHandle(job_id=f"job_{project_id}", project_id=project_id)
    
    mock_job_queue.enqueue_project_run.side_effect = mock_enqueue
    batch_status = batch_service.create_batch(project_ids)
    batch_id = batch_status.batch_id
    
    # Create validation reports with different failure reasons
    validation_reports = [
        {
            "project_id": "proj1",
            "passed": False,
            "score": 0.5,
            "issues": [
                {"code": "MISSING_CRITICAL_SCOPE", "severity": "error", "message": "Missing scope"},
                {"code": "MISSING_CRITICAL_SCOPE", "severity": "error", "message": "Missing scope"},
            ],
        },
        {
            "project_id": "proj2",
            "passed": False,
            "score": 0.6,
            "issues": [
                {"code": "MISSING_CRITICAL_SCOPE", "severity": "error", "message": "Missing scope"},
                {"code": "DIMENSION_CONFLICT", "severity": "error", "message": "Conflict"},
            ],
        },
        {
            "project_id": "proj3",
            "passed": True,
            "score": 0.9,
            "issues": [],
        },
    ]
    
    for i, report_data in enumerate(validation_reports):
        output_dir = Path("out") / project_ids[i]
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "validation_report.json", "w") as f:
            json.dump(report_data, f)
    
    # Mock job statuses
    def mock_get_status(job_id: str) -> dict:
        return {"job_id": job_id, "status": "finished", "project_id": job_id.replace("job_", "")}
    
    mock_job_queue.get_job_status.side_effect = mock_get_status
    
    # Get batch status
    updated_status = batch_service.get_batch_status(batch_id)
    
    assert updated_status is not None
    assert len(updated_status.summary.top_failure_reasons) > 0
    
    # MISSING_CRITICAL_SCOPE should be the top failure reason (3 occurrences)
    top_reason = updated_status.summary.top_failure_reasons[0]
    assert top_reason["code"] == "MISSING_CRITICAL_SCOPE"
    assert top_reason["count"] == 3


def test_get_batch_status_returns_none_for_missing_batch(
    batch_service: BatchService,
) -> None:
    """Test that get_batch_status returns None for non-existent batch."""
    result = batch_service.get_batch_status("nonexistent_batch_id")
    assert result is None






