"""Project upload and processing endpoints."""

from datetime import datetime
from typing import Any

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from loguru import logger

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.core.config import Settings, get_settings
from app.core.ids import generate_project_id
from app.models.schemas import ProjectResult, UploadResponse
from app.services.document_processor import DocumentProcessor
from app.services.job_queue import JobHandle, JobQueueService
from app.services.openai_client import OpenAIClient
from app.services.pipeline import PipelineOrchestrator
from app.services.run_state_store import RunStateStore
from app.services.storage import StorageService
from app.services.bid_readiness import compute_bid_readiness
from app.schemas.bid_readiness import BidReadinessResult
from app.utils.timing import stage_timer
from app.schemas.manual_overrides import ManualOverridesUpdate, ManualOverrides
from app.services.manual_override_service import (
    load_manual_overrides,
    save_manual_overrides,
)

router = APIRouter(prefix="/projects", tags=["projects"])

# Known artifact names (Phase 6.1, 6.4, 10.0)
ALLOWED_ARTIFACTS = {
    "document_analysis",
    "extraction_result",
    "proposal_markdown",
    "validation_report",
    "model_3d",
    "costing_result",
    "bid_proposal",
    "metrics",
    "page_index",
    "proposal_pdf",  # Phase 6.4: PDF artifact
    "evidence_index",  # Phase 6.7: Evidence index
    "bid_review",  # Phase 8.2: Bid review artifact
    "zone_cost_map",  # Phase 8.3: Zone cost map artifact
    "detail_overlay_index",  # Phase 8.4: Detail overlay index artifact
    "evidence_bbox_index",  # Phase 8.6D: Evidence bbox index
    "expanded_scope",  # Phase 9.2B: Expanded scope artifact
    "labor_breakdown",  # Phase 9.3B: Labor breakdown artifact
    "contractor_bid",  # Phase 9.4B: Contractor bid artifact
    "contractor_proposal_pdf",  # Phase 9.6: Contractor proposal PDF artifact
    "proposal_markdown",  # Phase 9.8: Proposal markdown template artifact
    "work_packages",  # Phase 9.9: Work package normalizer artifact
    "bid_pricing_v2",  # Phase 10.2: Bid pricing v2 with component breakdowns
    "calibration_pack",  # Phase 10.3: Calibration pack for contractor adjustments
    "typology_confidence_report",  # Phase 10.7: Typology confidence report
    "proposal_sections",  # Phase 10.9A: Contractor-style proposal sections
    "pricing_profile",  # Phase 10.10A: Selected pricing profile
    "bid_proposal_v2",  # Phase 10.11A: Normalized bid proposal
    "quantity_normalization_report",  # Phase 10.11A: Quantity normalization report
    "bid_completeness",  # Phase 10.12A: Bid completeness gate result
    "trade_packages",  # Phase 11.0: Trade packages / subcontractor breakdown
    "trade_assemblies",  # Phase 9.2: Trade assemblies (material + labor + equipment breakdowns)
    "general_conditions",  # Phase 10.1: General conditions (overhead, logistics, permits)
    "construction_systems",  # Phase 14.1: Construction system assemblies (grouping line items into systems)
    "work_package_map",  # Task 1: Work packages (contractor-friendly zone aggregations)
    "trust_report",  # Trust Report: One-page bid confidence summary
    "coverage_declarations",  # Coverage & Warranty declarations (contractor-declared)
    "bid_export",  # Phase 1: Excel export with sticky explanations
    "case_study",  # Phase 1: Compliance case study narrative
}


def get_storage_service(settings: Settings = Depends(get_settings)) -> StorageService:
    """Dependency: Get storage service."""
    return StorageService(settings)


def _ensure_legacy_link(preferred_out: Path, legacy_out: Path) -> None:
    """Ensure backend/out mirrors preferred out directory via symlink."""

    legacy_out.parent.mkdir(parents=True, exist_ok=True)

    try:
        if legacy_out.exists():
            try:
                if legacy_out.resolve() == preferred_out.resolve():
                    return
            except FileNotFoundError:
                legacy_out.unlink(missing_ok=True)

            if legacy_out.is_symlink():
                legacy_out.unlink()
            else:
                shutil.rmtree(legacy_out)

        legacy_out.symlink_to(preferred_out, target_is_directory=True)
    except Exception as link_error:  # pragma: no cover - defensive logging
        logger.bind(source=str(legacy_out), destination=str(preferred_out)).warning(
            f"Failed to create legacy output symlink: {link_error}"
        )


def get_output_dir(project_id: str, settings: Settings = Depends(get_settings)) -> Path:
    """Get the output directory for a project, checking multiple possible locations."""
    # Pipeline writes to root/out/ (relative to project root)
    # storage_root is backend/storage, so parent.parent is project root
    project_root = settings.storage_root.parent.parent
    root_out = project_root / "out" / project_id
    legacy_out = settings.storage_root.parent / "out" / project_id

    if root_out.exists():
        root_out.mkdir(parents=True, exist_ok=True)
        _ensure_legacy_link(root_out, legacy_out)
        return root_out

    # Fallback: try relative paths
    possible_paths = [
        Path("out") / project_id,  # If API runs from root
        Path("../out") / project_id,  # If API runs from backend/
    ]

    for path in possible_paths:
        if path.exists():
            root_out.parent.mkdir(parents=True, exist_ok=True)
            if not root_out.exists():
                try:
                    shutil.copytree(path, root_out, dirs_exist_ok=True)
                    logger.bind(project_id=project_id).info(
                        "Migrated project artifacts to unified out directory",
                        source=str(path),
                        destination=str(root_out),
                    )
                except Exception as migrate_error:  # pragma: no cover
                    logger.bind(project_id=project_id).warning(
                        f"Failed to migrate artifacts from {path}: {migrate_error}"
                    )
            _ensure_legacy_link(root_out, legacy_out)
            return root_out

    # Default to root/out/ (will be created if needed)
    root_out.parent.mkdir(parents=True, exist_ok=True)
    root_out.mkdir(parents=True, exist_ok=True)
    _ensure_legacy_link(root_out, legacy_out)
    return root_out


def get_document_processor(
    settings: Settings = Depends(get_settings),
    storage_service: StorageService = Depends(get_storage_service),
) -> DocumentProcessor:
    """Dependency: Get document processor."""
    return DocumentProcessor(settings, storage_service)


def get_openai_client(settings: Settings = Depends(get_settings)) -> OpenAIClient:
    """Dependency: Get OpenAI client."""
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY must be set in environment or .env file")
    return OpenAIClient(settings)


def get_document_analyzer(
    settings: Settings = Depends(get_settings),
    openai_client: OpenAIClient = Depends(get_openai_client),
) -> DocumentAnalyzer:
    """Dependency: Get document analyzer."""
    return DocumentAnalyzer(settings, openai_client)


def get_pipeline_orchestrator(
    document_analyzer: DocumentAnalyzer = Depends(get_document_analyzer),
    settings: Settings = Depends(get_settings),
) -> PipelineOrchestrator:
    """Dependency: Get pipeline orchestrator."""
    return PipelineOrchestrator(document_analyzer=document_analyzer, settings=settings)


def get_job_queue_service(
    settings: Settings = Depends(get_settings),
) -> JobQueueService:
    """Dependency: Get job queue service."""
    return JobQueueService(settings)


def get_run_state_store(
    settings: Settings = Depends(get_settings),
) -> RunStateStore:
    """Dependency: Get run state store."""
    return RunStateStore(settings)


def get_output_dir(project_id: str, settings: Settings | None = None) -> Path:
    """Get the output directory for a project, checking multiple possible locations."""
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()
    
    # Pipeline writes to root/out/ (relative to project root)
    # API might run from backend/ or root/, so check both
    # storage_root is backend/storage, so parent is root, then out/
    root_out = settings.storage_root.parent / "out" / project_id
    if root_out.exists():
        return root_out
    
    # Fallback: try relative paths
    possible_paths = [
        Path("out") / project_id,  # If API runs from root
        Path("../out") / project_id,  # If API runs from backend/
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Default to root/out/ (will be created if needed)
    return root_out


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(..., description="PDF file to upload"),
    storage_service: StorageService = Depends(get_storage_service),
    settings: Settings = Depends(get_settings),
    job_queue: JobQueueService = Depends(get_job_queue_service),
) -> UploadResponse:
    """
    Upload a PDF file and save it to storage.
    
    This endpoint only saves the PDF. To process it, call POST /projects/{project_id}/run
    
    For large PDFs (>50 pages), automatically enqueues a page indexing job.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="File must be a PDF (.pdf extension required)"
        )

    # Generate project ID
    project_id = generate_project_id()
    logger.bind(project_id=project_id).info(f"Uploading PDF: {file.filename}")

    try:
        # Read file content
        file_content = await file.read()
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        # Save PDF to out/{project_id}/input.pdf
        with stage_timer(project_id, "save_pdf"):
            pdf_path = storage_service.save_pdf(project_id, file_content)

        logger.bind(project_id=project_id).info(
            f"PDF saved successfully to {pdf_path}"
        )

        # Get page count to determine if we should auto-enqueue page indexing
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()

        # Auto-enqueue page indexing for large PDFs (>50 pages)
        page_index_job_id = None
        if page_count > 50:
            try:
                job_handle = job_queue.enqueue_page_index_job(project_id)
                page_index_job_id = job_handle.job_id
                logger.bind(project_id=project_id).info(
                    f"Auto-enqueued page indexing job for large PDF ({page_count} pages): {page_index_job_id}"
                )
            except Exception as e:
                # Don't fail upload if job enqueue fails, just log warning
                logger.bind(project_id=project_id).warning(
                    f"Failed to auto-enqueue page indexing job: {e}"
                )

        # Auto-trigger pipeline run after upload (don't make user click "Re-run Pipeline")
        try:
            # Clear any stale lock before attempting to enqueue (same as run_project_pipeline)
            try:
                from redis import Redis
                redis_conn = Redis.from_url(job_queue.settings.redis_url)
                lock_key = f"pipeline:lock:{project_id}"
                if redis_conn.exists(lock_key):
                    redis_conn.delete(lock_key)
                    logger.bind(project_id=project_id).warning(
                        f"Cleared stale lock for project {project_id} during upload"
                    )
            except Exception as lock_error:
                logger.bind(project_id=project_id).warning(
                    f"Could not check/clear lock during upload: {lock_error}. Proceeding anyway."
                )
            
            pipeline_job_handle = job_queue.enqueue_project_run(project_id)
            logger.bind(project_id=project_id).info(
                f"Auto-enqueued pipeline job after upload: {pipeline_job_handle.job_id}"
            )
        except Exception as e:
            # Don't fail upload if job enqueue fails, but log error for debugging
            logger.bind(project_id=project_id).error(
                f"CRITICAL: Failed to auto-enqueue pipeline job after upload: {e}. Pipeline will NOT start automatically."
            )
            # Don't fail upload - user can manually trigger, but log the error

        return UploadResponse(
            project_id=project_id,
            page_count=page_count,
            status="uploaded",
            page_index_job_id=page_index_job_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.bind(project_id=project_id).exception(
            f"Error saving upload: {str(e)}"
        )
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/{project_id}/result", response_model=ProjectResult)
async def get_project_result(
    project_id: str,
    storage_service: StorageService = Depends(get_storage_service),
    document_processor: DocumentProcessor = Depends(get_document_processor),
    pipeline: PipelineOrchestrator = Depends(get_pipeline_orchestrator),
) -> ProjectResult:
    """Get the full processing result for a project (reprocesses if needed)."""
    pdf_path = storage_service.get_source_pdf_path(project_id)

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    # Reprocess to get full result
    document_bundle = document_processor.process_pdf(project_id, pdf_path)
    project_result = pipeline.run_full_pipeline(project_id, document_bundle)

    return project_result


@router.post("/{project_id}/run")
async def run_project_pipeline(
    project_id: str,
    storage_service: StorageService = Depends(get_storage_service),
    job_queue: JobQueueService = Depends(get_job_queue_service),
    run_state_store: RunStateStore = Depends(get_run_state_store),
) -> dict[str, str]:
    """
    Enqueue a background job to run the pipeline for a project.

    Resumes from the next incomplete stage using run_state.
    Clears any stale locks before enqueuing.
    """
    # Validate project exists - check for source.pdf (saved by upload endpoint)
    pdf_path = storage_service.get_source_pdf_path(project_id)
    if not pdf_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Project {project_id} not found. PDF file (source.pdf) does not exist at {pdf_path}. Please upload the PDF first using POST /projects/upload"
        )

    logger.bind(project_id=project_id).info("Enqueuing pipeline job")

    # Reset existing run state so each rerun executes all stages
    try:
        state = run_state_store.load(project_id)
        if state.stages:
            any_running = any(stage.status == "running" for stage in state.stages)
            if not any_running:
                for stage in state.stages:
                    stage.status = "pending"
                    stage.started_at = None
                    stage.finished_at = None
                    stage.error = None
                state.current_stage = None
                run_state_store.save(state)
                logger.bind(project_id=project_id).info(
                    "Reset pipeline run state to pending for rerun"
                )
            else:
                logger.bind(project_id=project_id).warning(
                    "Skipping run state reset because a stage is currently running"
                )
    except Exception as state_error:  # pragma: no cover - defensive logging
        logger.bind(project_id=project_id).warning(
            f"Failed to reset run state before rerun: {state_error}"
        )

    try:
        # Clear any stale locks before enqueuing (in case previous job crashed)
        # A lock is considered stale if:
        # 1. It exists but no job is actually running (check RQ job registry)
        # 2. The lock TTL is very high (suggests a crashed job)
        try:
            from redis import Redis
            from rq import Queue as RQQueue
            from rq.job import Job
            redis_conn = Redis.from_url(job_queue.settings.redis_url)
            rq_queue = RQQueue(job_queue.settings.rq_queue_name, connection=redis_conn)
            lock_key = f"pipeline:lock:{project_id}"
            
            # Check if lock exists
            if redis_conn.exists(lock_key):
                ttl = redis_conn.ttl(lock_key)
                # Check if there's actually a running job for this project
                has_running_job = False
                try:
                    # Check started jobs
                    started_jobs = rq_queue.started_job_registry.get_job_ids()
                    for job_id in started_jobs:
                        try:
                            job = Job.fetch(job_id, connection=redis_conn)
                            if job.meta.get("project_id") == project_id:
                                has_running_job = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
                
                # If no running job but lock exists, or TTL is suspiciously high, clear it
                if not has_running_job or ttl > 3600:
                    logger.bind(project_id=project_id).warning(
                        f"Clearing stale lock (TTL: {ttl}s, has_running_job: {has_running_job})"
                    )
                    redis_conn.delete(lock_key)
        except Exception as lock_error:
            logger.bind(project_id=project_id).warning(
                f"Could not check/clear lock: {lock_error}. Proceeding anyway."
            )

        # Enqueue job
        job_handle = job_queue.enqueue_project_run(project_id)

        return {
            "project_id": project_id,
            "job_id": job_handle.job_id,
            "status": "queued",
        }
    except Exception as e:
        # Catch Redis connection errors and other job queue failures
        error_msg = str(e)
        logger.bind(project_id=project_id).exception(f"Failed to enqueue job: {error_msg}")
        
        # Check if it's a Redis connection error
        if "redis" in error_msg.lower() or "connection" in error_msg.lower() or "ConnectionError" in str(type(e)) or "Connection refused" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="Redis unavailable. Please start Redis server: docker run -d -p 6379:6379 --name redis-construction redis (or redis-server) and ensure worker is running: python -m app.workers.worker"
            )
        
        # Other errors
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue pipeline job: {error_msg}"
        )


@router.get("/{project_id}/manual_overrides", response_model=ManualOverrides)
async def get_manual_overrides(
    project_id: str,
    settings: Settings = Depends(get_settings),
) -> ManualOverrides:
    """Return current manual overrides for a project."""

    try:
        overrides = load_manual_overrides(project_id, settings)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.bind(project_id=project_id).warning(
            f"Failed to load manual overrides: {exc}"
        )
        overrides = ManualOverrides()
    return overrides


@router.post("/{project_id}/manual_overrides")
async def update_manual_overrides(
    project_id: str,
    payload: ManualOverridesUpdate,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Update manual overrides for a project."""

    try:
        overrides = save_manual_overrides(project_id, payload, settings)
        return {
            "success": True,
            "overrides": overrides.model_dump(),
        }
    except Exception as exc:
        logger.bind(project_id=project_id).exception(
            f"Failed to save manual overrides: {exc}"
        )
        raise HTTPException(status_code=500, detail="Failed to save manual overrides")


@router.get("/{project_id}/jobs/page-index/status")
async def get_page_index_job_status(
    project_id: str,
    dry_run: bool = False,
    job_queue: JobQueueService = Depends(get_job_queue_service),
) -> dict[str, Any]:
    """
    Get status of page indexing job for a project.
    
    Returns job status, progress summary, and current state.
    
    Args:
        project_id: Project ID
        dry_run: If True, compute workload prediction without executing (Batch 4)
    """
    status = job_queue.get_page_index_job_status(project_id, dry_run=dry_run)
    return status


@router.get("/{project_id}/status")
async def get_project_status(
    project_id: str,
    run_state_store: RunStateStore = Depends(get_run_state_store),
    storage_service: StorageService = Depends(get_storage_service),
) -> dict[str, Any]:
    """
    Get run state summary for a project.

    Returns stage statuses, artifact paths, last_updated timestamp, and progress details.
    """
    state = run_state_store.load(project_id)

    # Get page count from document bundle if available
    page_count = None
    try:
        pdf_path = storage_service.get_source_pdf_path(project_id)
        if pdf_path.exists():
            import fitz
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            doc.close()
    except Exception:
        pass  # Ignore errors getting page count

    # If no stages, project hasn't started
    if not state.stages:
        return {
            "project_id": project_id,
            "status": "not_started",
            "stages": [],
            "last_updated": None,
            "page_count": page_count,
        }

    # Build stage summary with duration calculations
    stages_summary = []
    for stage in state.stages:
        stage_info: dict[str, any] = {
            "stage_name": stage.stage_name,
            "status": stage.status,
            "attempts": stage.attempts,
        }
        if stage.started_at:
            stage_info["started_at"] = stage.started_at.isoformat()
        if stage.finished_at:
            stage_info["finished_at"] = stage.finished_at.isoformat()
            # Calculate duration
            if stage.started_at:
                duration_seconds = (stage.finished_at - stage.started_at).total_seconds()
                stage_info["duration_seconds"] = duration_seconds
        elif stage.started_at:
            # Stage is running - calculate elapsed time
            from datetime import datetime
            elapsed_seconds = (datetime.now() - stage.started_at).total_seconds()
            stage_info["elapsed_seconds"] = elapsed_seconds
        if stage.artifacts:
            stage_info["artifacts"] = stage.artifacts
        if stage.error:
            stage_info["error"] = stage.error
        stages_summary.append(stage_info)

    # Determine overall status
    overall_status = "running"
    if state.current_stage is None:
        # Check if all stages succeeded
        if all(s.status == "succeeded" for s in state.stages):
            overall_status = "succeeded"
        elif any(s.status == "failed" for s in state.stages):
            overall_status = "failed"
        else:
            overall_status = "completed"  # Some skipped, some succeeded

    return {
        "project_id": project_id,
        "status": overall_status,
        "current_stage": state.current_stage,
        "stages": stages_summary,
        "last_updated": state.last_updated.isoformat() if state.last_updated else None,
        "page_count": page_count,
    }


@router.get("/{project_id}/artifacts")
async def list_artifacts(
    project_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, list[dict[str, str]]]:
    """
    List available artifacts for a project (Phase 6.1).
    
    Returns list of artifact names with their URLs.
    """
    # Output directory (matches pipeline convention)
    output_dir = get_output_dir(project_id, settings)
    
    artifacts: list[dict[str, str]] = []
    
    for artifact_name in ALLOWED_ARTIFACTS:
        artifact_file = output_dir / f"{artifact_name}.json"
        if artifact_file.exists():
            artifacts.append({
                "name": artifact_name,
                "url": f"/v1/projects/{project_id}/artifacts/{artifact_name}",
            })
    
    return {"artifacts": artifacts}


@router.get("/{project_id}/artifacts/{artifact_name}")
async def get_artifact(
    project_id: str,
    artifact_name: str,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """
    Get a specific artifact file (Phase 6.1, 10.0).
    
    Supports JSON files and markdown files (proposal_markdown.md).
    Only allows known artifact names for security.
    """
    # Normalize artifact name: replace spaces with underscores (handles URL encoding issues)
    # This allows both "construction_systems" and "construction systems" to work
    normalized_name = artifact_name.replace(" ", "_")
    
    # Security: only allow known artifact names
    if normalized_name not in ALLOWED_ARTIFACTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown artifact name: {artifact_name}. Allowed: {', '.join(sorted(ALLOWED_ARTIFACTS))}",
        )
    
    # Use normalized name for all operations
    artifact_name = normalized_name
    
    # Output directory (matches pipeline convention)
    output_dir = get_output_dir(project_id, settings)
    
    # Try different file extensions based on artifact type
    artifact_file: Path | None = None
    media_type = "application/json"
    
    # Excel files (Phase 1: bid_export.xlsx)
    if artifact_name == "bid_export":
        artifact_file = output_dir / "bid_export.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    # JSON files (default)
    elif artifact_name == "proposal_markdown":
        # Try JSON first, then markdown
        artifact_file = output_dir / "proposal_markdown.json"
        if not artifact_file.exists():
            artifact_file = output_dir / "proposal_markdown.md"
            media_type = "text/markdown"
    else:
        # Default: JSON
        artifact_file = output_dir / f"{artifact_name}.json"
    
    if not artifact_file or not artifact_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact not found: {artifact_name}",
        )
    
    return FileResponse(
        path=str(artifact_file),
        media_type=media_type,
        filename=artifact_file.name,
    )


@router.get("/{project_id}/summary")
async def get_project_summary(
    project_id: str,
    settings: Settings = Depends(get_settings),
    run_state_store: RunStateStore = Depends(get_run_state_store),
) -> dict[str, Any]:
    """
    Get lightweight project summary (Phase 6.1).
    
    Returns status, validation score, total cost, bid_ready flag, etc.
    """
    # Output directory (matches pipeline convention)
    output_dir = get_output_dir(project_id, settings)
    
    # Get run state
    state = run_state_store.load(project_id)
    
    # Determine overall status
    # If no run_state exists or no stages, project is just uploaded (not processed yet)
    if not state.stages:
        overall_status = "uploaded"  # PDF uploaded but pipeline hasn't run
    elif state.current_stage is not None:
        overall_status = "running"  # Pipeline is currently running
    elif all(s.status == "succeeded" for s in state.stages):
        overall_status = "succeeded"
    elif any(s.status == "failed" for s in state.stages):
        overall_status = "failed"
    else:
        overall_status = "completed"  # Some stages succeeded, some skipped
    
    summary: dict[str, Any] = {
        "project_id": project_id,
        "status": overall_status,
        "last_updated": state.last_updated.isoformat() if state.last_updated else None,
    }
    
    # Try to load validation report
    validation_file = output_dir / "validation_report.json"
    if validation_file.exists():
        try:
            import json
            with open(validation_file, "r") as f:
                validation_data = json.load(f)
            summary["validation_score"] = validation_data.get("score", 0.0)
            summary["validation_passed"] = validation_data.get("passed", False)
        except Exception as e:
            logger.warning(f"Failed to load validation report: {e}")
    
    # Try to load costing result
    costing_file = output_dir / "costing_result.json"
    if costing_file.exists():
        try:
            import json
            with open(costing_file, "r") as f:
                costing_data = json.load(f)
            summary["total_cost"] = costing_data.get("total_cost")
        except Exception as e:
            logger.warning(f"Failed to load costing result: {e}")
    
    # Try to load bid proposal
    bid_file = output_dir / "bid_proposal.json"
    if bid_file.exists():
        try:
            import json
            with open(bid_file, "r") as f:
                bid_data = json.load(f)
            summary["bid_ready"] = bid_data.get("bid_ready", True)
            summary["estimate_mode"] = bid_data.get("estimate_mode", "conceptual")
            summary["bid_mode"] = bid_data.get("bid_mode", "conceptual")  # Phase 9.0: Bid mode guardrail
        except Exception as e:
            logger.warning(f"Failed to load bid proposal: {e}")
    
    # Determine pricing mode (Phase 10.2)
    pricing_v2_file = output_dir / "bid_pricing_v2.json"
    if pricing_v2_file.exists():
        summary["pricing_mode"] = "pricing_v2"
    else:
        summary["pricing_mode"] = "unit_cost_v1"
    
    # Try to load institutional geometry
    extraction_file = output_dir / "extraction_result.json"
    if extraction_file.exists():
        try:
            import json
            with open(extraction_file, "r") as f:
                extraction_data = json.load(f)
            inst_geometry = extraction_data.get("institutional_geometry_for_3d")
            if inst_geometry:
                summary["geometry_quality"] = inst_geometry.get("geometry_quality")
        except Exception as e:
            logger.warning(f"Failed to load extraction result: {e}")
    
    # Compute bid readiness (Phase 6.5)
    try:
        readiness = compute_bid_readiness(project_id, output_dir)
        summary["bid_ready"] = readiness.bid_ready
        summary["readiness_score"] = readiness.readiness_score
        summary["readiness_stamp_text"] = readiness.readiness_stamp_text
        summary["readiness_reasons_blocking"] = readiness.reasons_blocking
        summary["readiness_warnings"] = readiness.warnings
    except Exception as e:
        logger.warning(f"Failed to compute bid readiness: {e}")
        # Don't fail summary if readiness computation fails
    
    return summary


@router.get("/{project_id}/bid_readiness", response_model=BidReadinessResult)
async def get_bid_readiness(
    project_id: str,
    settings: Settings = Depends(get_settings),
) -> BidReadinessResult:
    """
    Get bid readiness assessment for a project (Phase 6.5).
    
    Returns deterministic assessment based on validation, geometry quality, and artifacts.
    """
    output_dir = get_output_dir(project_id, settings)
    
    if not output_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    
    return compute_bid_readiness(project_id, output_dir)


@router.get("/{project_id}/bid_readiness_v2")
async def get_bid_readiness_v2(
    project_id: str,
    settings: Settings = Depends(get_settings),
):
    """
    Get bid readiness v2 assessment separating conceptual vs contractor readiness (Phase 10.1).
    
    Returns deterministic assessment with conceptual_ready and contractor_ready flags.
    """
    from app.services.bid_readiness_v2 import compute_bid_readiness_v2
    
    output_dir = get_output_dir(project_id, settings)
    
    if not output_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    
    return compute_bid_readiness_v2(project_id, output_dir, settings)


@router.get("/{project_id}/contractor_bid")
async def get_contractor_bid(
    project_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Get contractor bid for a project (Phase 9.4B).
    
    Returns 404 if contractor bid has not been generated yet.
    """
    output_dir = get_output_dir(project_id, settings)
    contractor_bid_file = output_dir / "contractor_bid.json"
    
    if not contractor_bid_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Contractor bid not found for project {project_id}. Generate it first using POST /v1/projects/{project_id}/contractor_bid",
        )
    
    import json
    with open(contractor_bid_file, "r") as f:
        return json.load(f)


@router.post("/{project_id}/contractor_bid")
async def generate_contractor_bid(
    project_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Generate and save contractor bid for a project (Phase 9.4B).
    
    Composes contractor bid from bid_proposal, expanded_scope, labor_breakdown, and contractor profile.
    """
    output_dir = get_output_dir(project_id, settings)
    
    try:
        from app.services.contractor_bid_composer import compose_contractor_bid
        from app.services.region_resolver import resolve_region, select_profile_id
        from app.schemas.expanded_scope import RegionResolution
        import json
        
        # Resolve region (Phase 9.7)
        region_resolution = None
        profile_id = None
        try:
            # Load document_analysis and extraction_result for region resolution
            document_analysis_dict = None
            extraction_result_dict = None
            
            analysis_file = output_dir / "document_analysis.json"
            if analysis_file.exists():
                with open(analysis_file, "r") as f:
                    document_analysis_dict = json.load(f)
            
            extraction_file = output_dir / "extraction_result.json"
            if extraction_file.exists():
                with open(extraction_file, "r") as f:
                    extraction_result_dict = json.load(f)
            
            # Resolve region
            region_result = resolve_region(document_analysis_dict, extraction_result_dict)
            region_id = region_result["region_id"]
            profile_id = select_profile_id(region_id, "row_house_masonry")
            
            # Create RegionResolution object
            region_resolution = RegionResolution(
                region_id=region_id,
                confidence=region_result["confidence"],
                evidence=region_result["evidence"],
            )
        except Exception as e:
            logger.bind(project_id=project_id).warning(f"Failed to resolve region, using default: {e}")
        
        contractor_bid = compose_contractor_bid(
            project_id=project_id,
            output_dir=output_dir,
            settings=settings,
            profile_id=profile_id,
            region_resolution=region_resolution,
        )
        
        # Save contractor bid
        contractor_bid_file = output_dir / "contractor_bid.json"
        contractor_bid_file.parent.mkdir(parents=True, exist_ok=True)
        with open(contractor_bid_file, "w") as f:
            f.write(contractor_bid.model_dump_json(indent=2))
        
        logger.bind(project_id=project_id).info(
            f"Contractor bid saved to {contractor_bid_file} (total: ${contractor_bid.total_bid:.2f})"
        )
        
        return contractor_bid.model_dump(mode="json")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Required artifact not found: {str(e)}",
        ) from e
    except Exception as e:
        logger.bind(project_id=project_id).exception(f"Failed to generate contractor bid: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate contractor bid: {str(e)}",
        ) from e


@router.post("/{project_id}/proposal.pdf")
async def generate_proposal_pdf(
    project_id: str,
    job_queue: JobQueueService = Depends(get_job_queue_service),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """
    Enqueue a job to generate proposal PDF (Phase 6.4).

    Returns:
        Dictionary with job_id
    """
    log_ctx = logger.bind(project_id=project_id, endpoint="generate_proposal_pdf")

    # Check if project exists (use out/ directory to match artifact convention)
    output_dir = get_output_dir(project_id, settings)
    if not output_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Check if bid_proposal exists
    bid_proposal_file = output_dir / "bid_proposal.json"
    if not bid_proposal_file.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Bid proposal not found for project {project_id}. Please run the pipeline first.",
        )

    # Import PDF worker function
    from app.workers.pdf_worker import run_proposal_pdf_job

    # Enqueue PDF generation job
    log_ctx.info("Enqueuing PDF generation job")
    job = job_queue.queue.enqueue(
        run_proposal_pdf_job,
        project_id,
        job_id=None,  # Let RQ generate ID
        meta={"project_id": project_id, "enqueued_at": datetime.now().isoformat()},
    )

    log_ctx.info(f"PDF generation job enqueued: {job.id}")

    return {"job_id": job.id, "project_id": project_id, "status": "queued"}


@router.post("/{project_id}/trade-packages/{trade_id}/pdf")
async def generate_trade_package_pdf(
    project_id: str,
    trade_id: str,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """
    Generate PDF for a specific trade package (Phase 11.0).
    
    Returns the generated PDF file.
    """
    from app.services.pdf_exporter import PDFExporter
    
    output_dir = get_output_dir(project_id, settings)
    if not output_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    
    # Check if trade packages exist
    packages_file = output_dir / "trade_packages.json"
    if not packages_file.exists():
        raise HTTPException(status_code=404, detail="Trade packages not found for this project")
    
    # Verify trade_id exists
    import json
    with open(packages_file, "r") as f:
        packages_data = json.load(f)
    
    trade_ids = [pkg["trade_id"] for pkg in packages_data.get("packages", [])]
    if trade_id not in trade_ids:
        raise HTTPException(status_code=404, detail=f"Trade package '{trade_id}' not found")
    
    # Generate PDF
    exporter = PDFExporter(settings)
    try:
        pdf_path = exporter.generate_trade_package_pdf(project_id, trade_id)
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            filename=f"trade_package_{trade_id}_{project_id}.pdf",
        )
    except Exception as e:
        logger.exception(f"Failed to generate trade package PDF: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.get("/{project_id}/proposal.pdf")
@router.head("/{project_id}/proposal.pdf")
async def download_proposal_pdf(
    project_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """
    Download the generated proposal PDF (Phase 6.4).

    Returns:
        PDF file stream

    Raises:
        404: If PDF not generated yet
    """
    # Use out/ directory to match artifact convention
    output_dir = get_output_dir(project_id, settings)
    pdf_path = output_dir / "proposal.pdf"

    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF not generated yet for project {project_id}. Call POST /v1/projects/{project_id}/proposal.pdf to generate.",
        )

    # Security: Ensure path is within out/ directory
    try:
        pdf_path.resolve().relative_to(Path("out").resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid PDF path")

    # For HEAD requests, return empty response with headers only
    if request.method == "HEAD":
        return Response(
            status_code=200,
            headers={
                "Content-Type": "application/pdf",
                "Content-Length": str(pdf_path.stat().st_size),
            }
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"proposal_{project_id}.pdf",
    )


@router.get("/{project_id}/source.pdf")
async def get_source_pdf(
    project_id: str,
    storage_service: StorageService = Depends(get_storage_service),
) -> FileResponse:
    """
    Get the source PDF file for a project (Phase 8.6C).
    
    Returns:
        PDF file stream
    
    Raises:
        404: If PDF not found
    """
    pdf_path = storage_service.get_source_pdf_path(project_id)
    
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source PDF not found for project {project_id}",
        )
    
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{project_id}_source.pdf",
    )


@router.get("/{project_id}/trust_report")
async def get_trust_report(
    project_id: str,
    settings: Settings = Depends(get_settings),
):
    """
    Get trust report for a project (one-page bid confidence summary).
    
    Generates trust report on-demand from existing artifacts.
    """
    from app.services.trust_report_generator import generate_trust_report
    
    output_dir = get_output_dir(project_id, settings)
    
    if not output_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    
    try:
        trust_report = generate_trust_report(project_id, output_dir, settings)
        
        # Save to file for caching
        trust_report_file = output_dir / "trust_report.json"
        with open(trust_report_file, "w") as f:
            import json
            f.write(trust_report.model_dump_json(indent=2))
        
        return trust_report.model_dump(mode="json")
    except Exception as e:
        logger.exception(f"Failed to generate trust report for {project_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate trust report: {str(e)}"
        )


@router.get("/{project_id}/calibration_pack")
async def get_calibration_pack(
    project_id: str,
    settings: Settings = Depends(get_settings),
):
    """
    Get calibration pack for a project (Phase 10.3).
    
    Returns calibration pack with key assumptions and suggested adjustments.
    """
    from app.services.calibration_pack_generator import generate_calibration_pack
    from app.services.contractor_profile_store import load_profile
    
    output_dir = get_output_dir(project_id, settings)
    
    if not output_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    
    # Try to load contractor profile and region info
    contractor_profile = None
    region_id = None
    
    # Try to get from expanded_scope
    expanded_scope_file = output_dir / "expanded_scope.json"
    if expanded_scope_file.exists():
        try:
            import json
            with open(expanded_scope_file, "r") as f:
                expanded_scope_data = json.load(f)
            profile_id = expanded_scope_data.get("profile_id")
            region_resolution = expanded_scope_data.get("region_resolution")
            if region_resolution:
                region_id = region_resolution.get("region_id")
            
            if profile_id:
                try:
                    contractor_profile = load_profile(profile_id, settings)
                except Exception as e:
                    logger.warning(f"Failed to load profile {profile_id}: {e}")
        except Exception as e:
            logger.warning(f"Failed to load expanded_scope: {e}")
    
    # Try to get from pricing_v2
    if not region_id:
        pricing_v2_file = output_dir / "bid_pricing_v2.json"
        if pricing_v2_file.exists():
            try:
                import json
                with open(pricing_v2_file, "r") as f:
                    pricing_v2_data = json.load(f)
                region_id = pricing_v2_data.get("region_id")
            except Exception:
                pass
    
    pack = generate_calibration_pack(
        project_id=project_id,
        output_dir=output_dir,
        contractor_profile=contractor_profile,
        region_id=region_id,
        settings=settings,
    )
    
    # Save calibration pack
    pack_file = output_dir / "calibration_pack.json"
    pack_file.parent.mkdir(parents=True, exist_ok=True)
    with open(pack_file, "w") as f:
        f.write(pack.model_dump_json(indent=2))
    
    return pack.model_dump(mode="json")

