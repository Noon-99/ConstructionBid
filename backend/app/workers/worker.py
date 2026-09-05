"""RQ worker for processing pipeline jobs."""

import multiprocessing

# Fix for macOS fork() crashes - use 'spawn' start method
if __name__ == '__main__' or multiprocessing.get_start_method(allow_none=True) is None:
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        # Already set, ignore
        pass

from loguru import logger
from redis import Redis
from rq import Worker, Queue

from app.core.config import Settings
from app.services.document_processor import DocumentProcessor
from app.services.pipeline import PipelineOrchestrator
from app.services.run_state_store import RunStateStore
from app.services.storage import StorageService


def run_pipeline_job(project_id: str) -> dict[str, str]:
    """
    RQ job function to run pipeline for a project.

    Args:
        project_id: Project ID to process

    Returns:
        Dictionary with status and project_id

    Raises:
        Exception: If lock cannot be acquired or pipeline fails
    """
    settings = Settings()
    redis_conn = Redis.from_url(settings.redis_url)

    # Per-project lock key
    lock_key = f"pipeline:lock:{project_id}"
    lock_timeout = 3600  # 1 hour max lock time

    logger.bind(project_id=project_id).info("Starting pipeline job")

    # Acquire per-project lock
    lock = redis_conn.lock(lock_key, timeout=lock_timeout)
    acquired = False

    try:
        # Try to acquire lock (non-blocking)
        acquired = lock.acquire(blocking=False)

        if not acquired:
            # Check if the lock is actually stale (no active job)
            from rq import Queue as RQQueue
            from rq.job import Job
            rq_queue = RQQueue(settings.rq_queue_name, connection=redis_conn)
            has_active_job = False
            try:
                # Check all job registries for this project
                for registry in [rq_queue.started_job_registry, rq_queue, rq_queue.failed_job_registry]:
                    try:
                        job_ids = list(registry.get_job_ids())
                        for job_id in job_ids:
                            try:
                                job = Job.fetch(job_id, connection=redis_conn)
                                if job.meta.get("project_id") == project_id:
                                    status = job.get_status()
                                    # Only consider it active if it's queued or started (not failed/finished)
                                    if status in ["queued", "started"]:
                                        has_active_job = True
                                        break
                            except Exception:
                                continue
                        if has_active_job:
                            break
                    except Exception:
                        continue
            except Exception as e:
                logger.bind(project_id=project_id).warning(f"Error checking job status: {e}")
            
            if not has_active_job:
                # Lock exists but no active job - it's stale, force clear and acquire
                logger.bind(project_id=project_id).warning(
                    "Lock exists but no active job found - clearing stale lock and proceeding"
                )
                try:
                    # Delete the lock key directly
                    redis_conn.delete(lock_key)
                    # Try to acquire again
                    acquired = lock.acquire(blocking=False)
                    if acquired:
                        logger.bind(project_id=project_id).info("Successfully acquired lock after clearing stale lock")
                except Exception as e:
                    logger.bind(project_id=project_id).error(f"Failed to clear stale lock: {e}")
            
            if not acquired:
                error_msg = (
                    f"Project {project_id} is already being processed by another job. "
                    "Wait for the current job to complete or clear the lock manually."
                )
                logger.bind(project_id=project_id).error(error_msg)
                raise RuntimeError(error_msg)

        logger.bind(project_id=project_id).info("Lock acquired, running pipeline")

        # Initialize services
        storage_service = StorageService(settings)
        run_state_store = RunStateStore(settings)

        # Check if project exists
        pdf_path = storage_service.get_source_pdf_path(project_id)
        if not pdf_path.exists():
            raise FileNotFoundError(f"Project {project_id} not found: {pdf_path}")

        # Initialize pipeline services
        from app.services.openai_client import OpenAIClient
        from app.analyzers.document_analyzer import DocumentAnalyzer
        from app.analyzers.row_house_repair_extractor import RowHouseRepairExtractor
        from app.analyzers.institutional_room_extractor import InstitutionalRoomExtractor
        from app.analyzers.structural_notes_extractor import StructuralNotesExtractor
        from app.generators.model_3d_generator import Model3DGenerator
        from app.costing.cost_engine import CostEngine
        from app.services.page_indexer import PageIndexer

        openai_client = OpenAIClient(settings)
        document_analyzer = DocumentAnalyzer(settings, openai_client)
        row_house_extractor = RowHouseRepairExtractor(settings, openai_client)
        institutional_room_extractor = InstitutionalRoomExtractor(settings, openai_client)
        structural_notes_extractor = StructuralNotesExtractor(settings, openai_client)
        model_3d_generator = Model3DGenerator()
        cost_engine = CostEngine()
        page_indexer = PageIndexer(settings, openai_client)

        pipeline = PipelineOrchestrator(
            document_analyzer=document_analyzer,
            row_house_extractor=row_house_extractor,
            institutional_room_extractor=institutional_room_extractor,
            structural_notes_extractor=structural_notes_extractor,
            model_3d_generator=model_3d_generator,
            cost_engine=cost_engine,
            page_indexer=page_indexer,
            settings=settings,
        )

        # Process PDF to images
        doc_processor = DocumentProcessor(settings, storage_service)
        document_bundle = doc_processor.process_pdf(project_id, pdf_path)

        # Run pipeline (uses run_state internally to resume)
        logger.bind(project_id=project_id).info("Running full pipeline")
        result = pipeline.run_full_pipeline(project_id, document_bundle)

        logger.bind(project_id=project_id).info(
            f"Pipeline completed: status={result.status}"
        )

        return {
            "status": "succeeded",
            "project_id": project_id,
            "message": "Pipeline completed successfully",
        }

    except Exception as e:
        logger.bind(project_id=project_id).exception(f"Pipeline job failed: {e}")
        raise

    finally:
        # Always release lock
        if acquired:
            try:
                lock.release()
                logger.bind(project_id=project_id).info("Lock released")
            except Exception as e:
                logger.bind(project_id=project_id).error(f"Failed to release lock: {e}")


def run_page_index_job(project_id: str) -> dict[str, str]:
    """
    RQ job function to run page indexing (Stage 0.5) for a project.

    Args:
        project_id: Project ID to process

    Returns:
        Dictionary with status and project_id

    Raises:
        Exception: If lock cannot be acquired or page indexing fails
    """
    settings = Settings()
    redis_conn = Redis.from_url(settings.redis_url)

    # Per-project lock key for page indexing
    lock_key = f"page_index:lock:{project_id}"
    lock_timeout = 7200  # 2 hour max lock time (for large PDFs)

    logger.bind(project_id=project_id).info("Starting page indexing job")

    # Acquire per-project lock
    lock = redis_conn.lock(lock_key, timeout=lock_timeout)
    acquired = False

    try:
        # Try to acquire lock (non-blocking)
        acquired = lock.acquire(blocking=False)

        if not acquired:
            error_msg = (
                f"Page indexing for project {project_id} is already running. "
                "Wait for the current job to complete."
            )
            logger.bind(project_id=project_id).error(error_msg)
            raise RuntimeError(error_msg)

        logger.bind(project_id=project_id).info("Lock acquired, running page indexing")

        # Initialize services
        storage_service = StorageService(settings)

        # Check if project exists
        pdf_path = storage_service.get_source_pdf_path(project_id)
        if not pdf_path.exists():
            raise FileNotFoundError(f"Project {project_id} not found: {pdf_path}")

        # Process PDF to images
        doc_processor = DocumentProcessor(settings, storage_service)
        document_bundle = doc_processor.process_pdf(project_id, pdf_path)

        # Initialize page indexer
        from app.services.openai_client import OpenAIClient
        from app.services.page_indexer import PageIndexer

        openai_client = OpenAIClient(settings)
        page_indexer = PageIndexer(settings, openai_client)

        # Load page images
        from app.utils.pdf_images import load_page_images_from_paths

        page_images = load_page_images_from_paths(document_bundle.page_image_paths)

        # Index pages (this writes progress.json automatically)
        logger.bind(project_id=project_id).info(
            f"Indexing {len(page_images)} pages"
        )
        page_index = page_indexer.index_pages(project_id, page_images)

        # Save page index to output directory
        from pathlib import Path
        output_dir = Path("out") / project_id
        index_file = output_dir / "page_index.json"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        with open(index_file, "w") as f:
            f.write(page_index.model_dump_json(indent=2))

        logger.bind(project_id=project_id).info(
            f"Page indexing completed: {len(page_index.pages)} pages indexed, "
            f"file saved to {index_file}"
        )

        return {
            "status": "succeeded",
            "project_id": project_id,
            "message": f"Page indexing completed: {len(page_index.pages)} pages indexed",
            "pages_indexed": len(page_index.pages),
        }

    except Exception as e:
        logger.bind(project_id=project_id).exception(f"Page indexing job failed: {e}")
        raise

    finally:
        # Always release lock
        if acquired:
            try:
                lock.release()
                logger.bind(project_id=project_id).info("Lock released")
            except Exception as e:
                logger.bind(project_id=project_id).error(f"Failed to release lock: {e}")


def main() -> None:
    """Main entry point for RQ worker."""
    import sys
    
    settings = Settings()
    redis_conn = Redis.from_url(settings.redis_url)
    queue = Queue(settings.rq_queue_name, connection=redis_conn)

    # Use SimpleWorker on macOS to avoid fork() crashes
    # SimpleWorker runs jobs in-process (no fork), completely avoiding macOS fork safety issues
    # SpawnWorker still uses fork() internally, so it doesn't help
    if sys.platform == "darwin":  # macOS
        try:
            from rq.worker import SimpleWorker
            logger.info(f"Starting RQ SimpleWorker (in-process, no fork) for queue: {settings.rq_queue_name} on macOS")
            worker = SimpleWorker([queue], connection=redis_conn)
        except ImportError:
            # Fallback to SimpleWorker if SpawnWorker not available (older RQ versions)
            from rq.worker import SimpleWorker
            logger.warning(f"SpawnWorker not available, using SimpleWorker (may still have fork issues)")
            worker = SimpleWorker([queue], connection=redis_conn)
    else:
        logger.info(f"Starting RQ worker (forking) for queue: {settings.rq_queue_name} on {sys.platform}")
        worker = Worker([queue], connection=redis_conn)
    
    worker.work()


if __name__ == "__main__":
    main()


