"""Job queue service for enqueuing and tracking pipeline jobs."""

from datetime import datetime
from typing import Any

from loguru import logger
from rq import Queue
from rq.job import Job
from redis import Redis

from app.core.config import Settings


class JobHandle:
    """Handle for an enqueued job."""

    def __init__(self, job_id: str, project_id: str) -> None:
        """Initialize job handle."""
        self.job_id = job_id
        self.project_id = project_id


class JobQueueService:
    """Service for managing pipeline jobs via Redis RQ."""

    def __init__(self, settings: Settings) -> None:
        """Initialize job queue service."""
        self.settings = settings
        # Don't connect to Redis at init time - connect lazily to avoid startup crashes
        self._redis_conn = None
        self._queue = None
    
    @property
    def redis_conn(self) -> Redis:
        """Get Redis connection (lazy initialization)."""
        if self._redis_conn is None:
            try:
                self._redis_conn = Redis.from_url(self.settings.redis_url)
                # Test connection
                self._redis_conn.ping()
            except Exception as e:
                logger.error(f"Failed to connect to Redis at {self.settings.redis_url}: {e}")
                raise
        return self._redis_conn
    
    @property
    def queue(self) -> Queue:
        """Get RQ queue (lazy initialization)."""
        if self._queue is None:
            self._queue = Queue(self.settings.rq_queue_name, connection=self.redis_conn)
        return self._queue

    def enqueue_project_run(self, project_id: str) -> JobHandle:
        """
        Enqueue a pipeline run job for a project.

        Args:
            project_id: Project ID to run pipeline for

        Returns:
            JobHandle with job_id and project_id
        """
        logger.bind(project_id=project_id).info("Enqueuing pipeline job")

        # Import here to avoid circular imports
        from app.workers.worker import run_pipeline_job

        # Enqueue job with project_id in meta
        job = self.queue.enqueue(
            run_pipeline_job,
            project_id,
            job_id=None,  # Let RQ generate ID
            meta={"project_id": project_id, "enqueued_at": datetime.now().isoformat()},
        )

        logger.bind(project_id=project_id, job_id=job.id).info(
            f"Job enqueued: {job.id}"
        )

        return JobHandle(job_id=job.id, project_id=project_id)

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """
        Get status of a job.

        Args:
            job_id: RQ job ID

        Returns:
            Dictionary with job status, project_id, timestamps, error if any
        """
        try:
            job = Job.fetch(job_id, connection=self.redis_conn)
        except Exception as e:
            logger.warning(f"Job {job_id} not found: {e}")
            return {
                "job_id": job_id,
                "status": "not_found",
                "error": str(e),
            }

        # Extract project_id from meta
        project_id = job.meta.get("project_id", "unknown")

        result: dict[str, Any] = {
            "job_id": job_id,
            "status": job.get_status(),
            "project_id": project_id,
        }

        # Add timestamps if available
        if hasattr(job, "enqueued_at") and job.enqueued_at:
            result["enqueued_at"] = job.enqueued_at.isoformat()
        elif "enqueued_at" in job.meta:
            result["enqueued_at"] = job.meta["enqueued_at"]

        if hasattr(job, "started_at") and job.started_at:
            result["started_at"] = job.started_at.isoformat()

        if hasattr(job, "ended_at") and job.ended_at:
            result["ended_at"] = job.ended_at.isoformat()

        # Add error if failed
        if job.is_failed:
            result["error"] = str(job.exc_info) if job.exc_info else "Job failed"

        logger.bind(job_id=job_id, project_id=project_id).debug(
            f"Job status: {result['status']}"
        )

        return result

    def enqueue_page_index_job(self, project_id: str) -> JobHandle:
        """
        Enqueue a page indexing job for a project.

        Args:
            project_id: Project ID to index pages for

        Returns:
            JobHandle with job_id and project_id
        """
        logger.bind(project_id=project_id).info("Enqueuing page indexing job")

        # Import here to avoid circular imports
        from app.workers.worker import run_page_index_job

        # Enqueue job with project_id in meta
        job = self.queue.enqueue(
            run_page_index_job,
            project_id,
            job_id=None,  # Let RQ generate ID
            meta={"project_id": project_id, "job_type": "page_index", "enqueued_at": datetime.now().isoformat()},
        )

        logger.bind(project_id=project_id, job_id=job.id).info(
            f"Page indexing job enqueued: {job.id}"
        )

        return JobHandle(job_id=job.id, project_id=project_id)

    def get_page_index_job_status(self, project_id: str, dry_run: bool = False) -> dict[str, Any]:
        """
        Get status of the most recent page indexing job for a project.

        Args:
            project_id: Project ID
            dry_run: If True, compute workload prediction without executing

        Returns:
            Dictionary with job status, progress summary, error if any, or dry_run workload
        """
        try:
            # Batch 4: Dry run mode - compute workload prediction
            if dry_run:
                from pathlib import Path as PathLib
                from app.services.page_indexer import PageIndexer
                from app.services.openai_client import OpenAIClient
                from app.core.config import Settings
                from app.utils.pdf_images import load_page_images_from_paths
                
                settings = Settings()
                output_dir = PathLib("out") / project_id
                pdf_path = output_dir / "input.pdf"
                
                if not pdf_path.exists():
                    return {
                        "status": "error",
                        "project_id": project_id,
                        "error": f"PDF not found at {pdf_path}",
                    }
                
                # Load page images (just count, don't process)
                try:
                    from app.services.document_processor import DocumentProcessor
                    from app.services.storage import StorageService
                    
                    storage_service = StorageService(settings)
                    doc_processor = DocumentProcessor(settings, storage_service)
                    document_bundle = doc_processor.process_pdf(project_id, pdf_path)
                    page_images = load_page_images_from_paths(document_bundle.page_image_paths)
                    
                    openai_client = OpenAIClient(settings)
                    page_indexer = PageIndexer(settings, openai_client)
                    workload = page_indexer.index_pages(project_id, page_images, dry_run=True)
                    
                    return {
                        "status": "dry_run",
                        "project_id": project_id,
                        **workload,
                    }
                except Exception as e:
                    return {
                        "status": "error",
                        "project_id": project_id,
                        "error": str(e),
                    }
            # Get all jobs for this project (we'll find the most recent page_index job)
            # RQ doesn't have a direct way to find jobs by project_id, so we'll check
            # the progress file and try to find the job via Redis
            
            from pathlib import Path as PathLib
            progress_file = PathLib("out") / project_id / "page_index_progress.json"
            
            progress_summary = None
            if progress_file.exists():
                try:
                    import json
                    with open(progress_file, "r") as f:
                        progress_summary = json.load(f)
                except Exception as e:
                    logger.bind(project_id=project_id).warning(
                        f"Failed to load progress file: {e}"
                    )
            
            # Try to find the job in the queue
            # This is a limitation - we'd need to store job_id somewhere
            # For now, return status based on progress file and artifact existence
            index_file = PathLib("out") / project_id / "page_index.json"
            
            if index_file.exists():
                return {
                    "status": "succeeded",
                    "project_id": project_id,
                    "progress": progress_summary,
                    "message": "Page indexing completed",
                }
            elif progress_summary:
                # Job is in progress
                completed = progress_summary.get("completed_pages", 0)
                total = progress_summary.get("total_pages", 0)
                if completed < total:
                    return {
                        "status": "running",
                        "project_id": project_id,
                        "progress": progress_summary,
                        "message": f"Indexing pages: {completed}/{total}",
                    }
            
            # No progress file and no index file - check if there's a job running
            # We can't easily find it without storing job_id, so return "not_started"
            return {
                "status": "not_started",
                "project_id": project_id,
                "progress": None,
                "message": "Page indexing has not started",
            }
            
        except Exception as e:
            logger.bind(project_id=project_id).warning(
                f"Failed to get page index job status: {e}"
            )
            return {
                "status": "unknown",
                "project_id": project_id,
                "progress": None,
                "error": str(e),
            }

