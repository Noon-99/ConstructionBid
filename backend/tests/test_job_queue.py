"""Unit tests for job queue service."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.services.job_queue import JobHandle, JobQueueService


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(redis_url="redis://localhost:6379/1")


@pytest.fixture
def mock_redis() -> MagicMock:
    """Mock Redis connection."""
    return MagicMock()


@pytest.fixture
def mock_queue(mock_redis: MagicMock) -> MagicMock:
    """Mock RQ Queue."""
    queue = MagicMock()
    queue.connection = mock_redis
    return queue


@pytest.fixture
def job_queue_service(settings: Settings, mock_queue: MagicMock) -> JobQueueService:
    """Create job queue service with mocked dependencies."""
    with patch("app.services.job_queue.Redis") as mock_redis_class, patch(
        "app.services.job_queue.Queue"
    ) as mock_queue_class:
        mock_redis_class.from_url.return_value = mock_queue.connection
        mock_queue_class.return_value = mock_queue

        service = JobQueueService(settings)
        service.queue = mock_queue
        service.redis_conn = mock_queue.connection

        return service


def test_enqueue_project_run(job_queue_service: JobQueueService, mock_queue: MagicMock) -> None:
    """Test enqueuing a project run job."""
    # Mock job
    mock_job = MagicMock()
    mock_job.id = "test-job-123"
    mock_queue.enqueue.return_value = mock_job

    # Enqueue
    handle = job_queue_service.enqueue_project_run("test-project")

    # Verify
    assert isinstance(handle, JobHandle)
    assert handle.job_id == "test-job-123"
    assert handle.project_id == "test-project"

    # Verify enqueue was called with correct args
    mock_queue.enqueue.assert_called_once()
    call_args = mock_queue.enqueue.call_args
    assert call_args[0][0].__name__ == "run_pipeline_job"  # Function name
    assert call_args[0][1] == "test-project"  # project_id arg
    assert call_args[1]["meta"]["project_id"] == "test-project"


def test_get_job_status_success(
    job_queue_service: JobQueueService, mock_queue: MagicMock
) -> None:
    """Test getting job status for existing job."""
    # Mock job
    mock_job = MagicMock()
    mock_job.id = "test-job-123"
    mock_job.get_status.return_value = "finished"
    mock_job.is_failed = False
    mock_job.meta = {"project_id": "test-project", "enqueued_at": "2025-01-01T00:00:00"}
    mock_job.enqueued_at = datetime(2025, 1, 1, 0, 0, 0)
    mock_job.started_at = datetime(2025, 1, 1, 0, 1, 0)
    mock_job.ended_at = datetime(2025, 1, 1, 0, 2, 0)
    mock_job.exc_info = None

    with patch("app.services.job_queue.Job") as mock_job_class:
        mock_job_class.fetch.return_value = mock_job

        status = job_queue_service.get_job_status("test-job-123")

        assert status["job_id"] == "test-job-123"
        assert status["status"] == "finished"
        assert status["project_id"] == "test-project"
        assert "enqueued_at" in status
        assert "started_at" in status
        assert "ended_at" in status
        assert "error" not in status


def test_get_job_status_failed(
    job_queue_service: JobQueueService, mock_queue: MagicMock
) -> None:
    """Test getting job status for failed job."""
    # Mock failed job
    mock_job = MagicMock()
    mock_job.id = "test-job-123"
    mock_job.get_status.return_value = "failed"
    mock_job.is_failed = True
    mock_job.meta = {"project_id": "test-project"}
    mock_job.exc_info = "Traceback: Error occurred"

    with patch("app.services.job_queue.Job") as mock_job_class:
        mock_job_class.fetch.return_value = mock_job

        status = job_queue_service.get_job_status("test-job-123")

        assert status["status"] == "failed"
        assert "error" in status
        assert status["error"] == "Traceback: Error occurred"


def test_get_job_status_not_found(job_queue_service: JobQueueService) -> None:
    """Test getting job status for non-existent job."""
    with patch("app.services.job_queue.Job") as mock_job_class:
        mock_job_class.fetch.side_effect = Exception("Job not found")

        status = job_queue_service.get_job_status("non-existent-job")

        assert status["status"] == "not_found"
        assert "error" in status






