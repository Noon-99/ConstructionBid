"""RQ worker job for PDF generation (Phase 6.4)."""

from datetime import datetime
from pathlib import Path

from loguru import logger
from redis import Redis

from app.core.config import Settings
from app.services.pdf_exporter import PDFExporter
from app.services.run_state_store import RunStateStore


def run_proposal_pdf_job(project_id: str) -> dict[str, str]:
    """
    RQ job function to generate proposal PDF for a project.

    Args:
        project_id: Project ID to generate PDF for

    Returns:
        Dictionary with status and project_id

    Raises:
        Exception: If lock cannot be acquired or PDF generation fails
    """
    settings = Settings()
    redis_conn = Redis.from_url(settings.redis_url)

    # Per-project lock key
    lock_key = f"pdf:lock:{project_id}"
    lock_timeout = 600  # 10 minutes max lock time

    log_ctx = logger.bind(project_id=project_id, stage="stage_6_4_pdf_export")
    log_ctx.info("Starting PDF generation job")

    # Acquire per-project lock
    lock = redis_conn.lock(lock_key, timeout=lock_timeout)
    acquired = False

    run_state_store = RunStateStore(settings)

    try:
        # Try to acquire lock (non-blocking)
        acquired = lock.acquire(blocking=False)

        if not acquired:
            error_msg = (
                f"Project {project_id} PDF generation is already in progress. "
                "Wait for the current job to complete."
            )
            log_ctx.error(error_msg)
            raise RuntimeError(error_msg)

        log_ctx.info("Lock acquired, generating PDF")

        # Mark stage as running
        run_state_store.update_stage_state(
            project_id=project_id,
            stage_name="stage_6_4_pdf_export",
            status="running",
            started_at=datetime.now(),
        )

        # Initialize PDF exporter
        pdf_exporter = PDFExporter(settings)

        # Generate PDF
        pdf_path = pdf_exporter.generate_proposal_pdf(project_id)

        # Verify PDF was created
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file was not created: {pdf_path}")

        # Update run state with artifact (relative path from project root)
        # PDF is stored in out/{project_id}/proposal.pdf to match artifact convention
        artifact_path = f"out/{project_id}/proposal.pdf"
        run_state_store.update_stage_state(
            project_id=project_id,
            stage_name="stage_6_4_pdf_export",
            status="succeeded",
            finished_at=datetime.now(),
            artifacts={"proposal_pdf": artifact_path},
        )

        log_ctx.info(f"PDF generation completed: {pdf_path}")

        return {
            "status": "succeeded",
            "project_id": project_id,
            "pdf_path": str(pdf_path),
            "message": "PDF generated successfully",
        }

    except Exception as e:
        log_ctx.exception(f"PDF generation job failed: {e}")

        # Update run state with error
        run_state_store.update_stage_state(
            project_id=project_id,
            stage_name="stage_6_4_pdf_export",
            status="failed",
            finished_at=datetime.now(),
            error=str(e),
        )

        raise

    finally:
        # Always release lock
        if acquired:
            try:
                lock.release()
                log_ctx.info("Lock released")
            except Exception as e:
                log_ctx.error(f"Failed to release lock: {e}")


def run_contractor_proposal_pdf_job(project_id: str) -> dict[str, str]:
    """
    RQ job function to generate contractor proposal PDF for a project (Phase 9.6).

    Args:
        project_id: Project ID to generate PDF for

    Returns:
        Dictionary with status and project_id

    Raises:
        Exception: If lock cannot be acquired or PDF generation fails
    """
    settings = Settings()
    redis_conn = Redis.from_url(settings.redis_url)

    # Per-project lock key
    lock_key = f"contractor_pdf:lock:{project_id}"
    lock_timeout = 600  # 10 minutes max lock time

    log_ctx = logger.bind(project_id=project_id, stage="contractor_proposal_pdf_export")
    log_ctx.info("Starting contractor proposal PDF generation job")

    # Acquire per-project lock
    lock = redis_conn.lock(lock_key, timeout=lock_timeout)
    acquired = False

    run_state_store = RunStateStore(settings)

    try:
        # Try to acquire lock (non-blocking)
        acquired = lock.acquire(blocking=False)

        if not acquired:
            error_msg = (
                f"Project {project_id} contractor proposal PDF generation is already in progress. "
                "Wait for the current job to complete."
            )
            log_ctx.error(error_msg)
            raise RuntimeError(error_msg)

        log_ctx.info("Lock acquired, generating contractor proposal PDF")

        # Mark stage as running
        run_state_store.update_stage_state(
            project_id=project_id,
            stage_name="contractor_proposal_pdf_export",
            status="running",
            started_at=datetime.now(),
        )

        # Initialize PDF exporter
        pdf_exporter = PDFExporter(settings)

        # Generate PDF
        pdf_path = pdf_exporter.generate_contractor_proposal_pdf(project_id)

        # Verify PDF was created
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file was not created: {pdf_path}")

        # Update run state with artifact (relative path from project root)
        artifact_path = f"out/{project_id}/contractor_proposal.pdf"
        run_state_store.update_stage_state(
            project_id=project_id,
            stage_name="contractor_proposal_pdf_export",
            status="succeeded",
            finished_at=datetime.now(),
            artifacts={"contractor_proposal_pdf": artifact_path},
        )

        log_ctx.info(f"Contractor proposal PDF generation completed: {pdf_path}")

        return {
            "status": "succeeded",
            "project_id": project_id,
            "pdf_path": str(pdf_path),
            "message": "Contractor proposal PDF generated successfully",
        }

    except Exception as e:
        log_ctx.exception(f"Contractor proposal PDF generation job failed: {e}")

        # Update run state with error
        run_state_store.update_stage_state(
            project_id=project_id,
            stage_name="contractor_proposal_pdf_export",
            status="failed",
            finished_at=datetime.now(),
            error=str(e),
        )

        raise

    finally:
        # Always release lock
        if acquired:
            try:
                lock.release()
                log_ctx.info("Lock released")
            except Exception as e:
                log_ctx.error(f"Failed to release lock: {e}")

