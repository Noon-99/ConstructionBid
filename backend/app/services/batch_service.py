"""Batch service for managing batch runs (Phase 3.5)."""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.core.ids import generate_project_id
from app.schemas.batch import (
    BatchItemStatus,
    BatchStatusResponse,
    BatchSummary,
)
from app.schemas.validation_report import ValidationReport
from app.services.metrics_collector import ProjectMetrics
from app.services.batch_store import BatchStore
from app.services.job_queue import JobQueueService
from app.services.run_state_store import RunStateStore


class BatchService:
    """Service for creating and managing batch runs."""

    def __init__(
        self,
        settings: Settings,
        job_queue: JobQueueService,
        batch_store: BatchStore,
        run_state_store: RunStateStore,
    ) -> None:
        """Initialize batch service."""
        self.settings = settings
        self.job_queue = job_queue
        self.batch_store = batch_store
        self.run_state_store = run_state_store

    def create_batch(self, project_ids: list[str]) -> BatchStatusResponse:
        """
        Create a batch and enqueue all projects.

        Args:
            project_ids: List of project IDs to process

        Returns:
            BatchStatusResponse with initial status
        """
        batch_id = generate_project_id()
        logger.bind(batch_id=batch_id).info(f"Creating batch with {len(project_ids)} projects")

        # Enqueue all projects
        items: list[BatchItemStatus] = []
        for project_id in project_ids:
            try:
                job_handle = self.job_queue.enqueue_project_run(project_id)
                items.append(
                    BatchItemStatus(
                        project_id=project_id,
                        job_id=job_handle.job_id,
                        status="queued",
                    )
                )
            except Exception as e:
                logger.error(f"Failed to enqueue project {project_id}: {e}")
                items.append(
                    BatchItemStatus(
                        project_id=project_id,
                        job_id=None,
                        status="failed",
                    )
                )

        # Create initial summary
        summary = BatchSummary(
            count=len(project_ids),
            completed=0,
            passed=0,
            failed=0,
            queued=sum(1 for item in items if item.status == "queued"),
            running=0,
        )

        # Create batch status
        batch_status = BatchStatusResponse(
            batch_id=batch_id,
            created_at=datetime.now(),
            items=items,
            summary=summary,
        )

        # Save batch manifest
        self.batch_store.save(batch_status)

        logger.bind(batch_id=batch_id).info(f"Batch created: {len(items)} items enqueued")
        return batch_status

    def get_batch_status(self, batch_id: str) -> BatchStatusResponse | None:
        """
        Get current batch status with aggregated summary.

        Args:
            batch_id: Batch ID

        Returns:
            BatchStatusResponse with updated status, None if batch not found
        """
        batch_status = self.batch_store.load(batch_id)
        if not batch_status:
            return None

        logger.bind(batch_id=batch_id).debug(f"Getting batch status for {len(batch_status.items)} items")

        # Update each item status from job queue and run state
        updated_items: list[BatchItemStatus] = []
        metrics_data: list[ProjectMetrics] = []
        validation_data: list[ValidationReport] = []

        for item in batch_status.items:
            updated_item = self._update_item_status(item)
            updated_items.append(updated_item)

            # Try to load metrics and validation report if job completed
            if updated_item.status in ["succeeded", "failed"]:
                metrics = self._load_metrics(updated_item.project_id)
                if metrics:
                    metrics_data.append(metrics)

                validation = self._load_validation_report(updated_item.project_id)
                if validation:
                    validation_data.append(validation)

        # Compute summary
        summary = self._compute_summary(updated_items, metrics_data, validation_data)

        # Create updated batch status
        updated_batch_status = BatchStatusResponse(
            batch_id=batch_id,
            created_at=batch_status.created_at,
            items=updated_items,
            summary=summary,
        )

        # Save updated batch (optional - can be done lazily)
        # self.batch_store.save(updated_batch_status)

        return updated_batch_status

    def _update_item_status(self, item: BatchItemStatus) -> BatchItemStatus:
        """Update status of a single item from job queue and run state."""
        # Get job status if we have a job_id
        job_status = None
        if item.job_id:
            try:
                job_status = self.job_queue.get_job_status(item.job_id)
                status_str = job_status.get("status", "unknown")
                # Map RQ status to our status
                if status_str == "finished":
                    item_status = "succeeded"
                elif status_str == "failed":
                    item_status = "failed"
                elif status_str == "started":
                    item_status = "running"
                else:
                    item_status = "queued"
            except Exception as e:
                logger.warning(f"Failed to get job status for {item.job_id}: {e}")
                item_status = item.status  # Keep current status
        else:
            item_status = item.status

        # Load validation report if available to get validation_passed and score
        validation_passed = None
        score = None
        if item_status in ["succeeded", "failed"]:
            validation = self._load_validation_report(item.project_id)
            if validation:
                validation_passed = validation.passed
                score = validation.score

        return BatchItemStatus(
            project_id=item.project_id,
            job_id=item.job_id,
            status=item_status,
            validation_passed=validation_passed,
            score=score,
        )

    def _load_metrics(self, project_id: str) -> ProjectMetrics | None:
        """Load metrics.json for a project."""
        output_dir = Path("out") / project_id
        metrics_file = output_dir / "metrics.json"

        if not metrics_file.exists():
            return None

        try:
            with open(metrics_file, "r") as f:
                data = json.load(f)
            return ProjectMetrics.model_validate(data)
        except Exception as e:
            logger.debug(f"Failed to load metrics for {project_id}: {e}")
            return None

    def _load_validation_report(self, project_id: str) -> ValidationReport | None:
        """Load validation_report.json for a project."""
        output_dir = Path("out") / project_id
        report_file = output_dir / "validation_report.json"

        if not report_file.exists():
            return None

        try:
            with open(report_file, "r") as f:
                data = json.load(f)
            return ValidationReport.model_validate(data)
        except Exception as e:
            logger.debug(f"Failed to load validation report for {project_id}: {e}")
            return None

    def _compute_summary(
        self,
        items: list[BatchItemStatus],
        metrics_data: list[ProjectMetrics],
        validation_data: list[ValidationReport],
    ) -> BatchSummary:
        """Compute aggregated summary statistics."""
        # Counts
        count = len(items)
        completed = sum(1 for item in items if item.status in ["succeeded", "failed"])
        queued = sum(1 for item in items if item.status == "queued")
        running = sum(1 for item in items if item.status == "running")

        # Passed/failed based on validation_passed
        passed = sum(1 for item in items if item.validation_passed is True)
        failed = sum(1 for item in items if item.validation_passed is False)

        # Averages from metrics
        avg_tokens = None
        avg_cost_usd = None
        avg_latency_seconds = None
        avg_cache_hit_rate = None

        if metrics_data:
            total_tokens = sum(m.total_tokens for m in metrics_data if m.total_tokens)
            total_cost = sum(m.total_cost_estimate_usd for m in metrics_data if m.total_cost_estimate_usd)
            total_latency = sum(m.total_latency_seconds for m in metrics_data if m.total_latency_seconds)
            cache_hit_rates = [m.cache_hit_rate for m in metrics_data if m.cache_hit_rate > 0]

            if total_tokens:
                avg_tokens = total_tokens / len(metrics_data)
            if total_cost:
                avg_cost_usd = total_cost / len(metrics_data)
            if total_latency:
                avg_latency_seconds = total_latency / len(metrics_data)
            if cache_hit_rates:
                avg_cache_hit_rate = sum(cache_hit_rates) / len(cache_hit_rates)

        # Top failure reasons from validation reports
        top_failure_reasons: list[dict[str, Any]] = []
        failure_codes = Counter()
        for validation in validation_data:
            if not validation.passed:
                for issue in validation.issues:
                    if issue.severity == "error":
                        failure_codes[issue.code] += 1

        # Get top 5 failure codes
        for code, count in failure_codes.most_common(5):
            top_failure_reasons.append({"code": code, "count": count})

        return BatchSummary(
            count=count,
            completed=completed,
            passed=passed,
            failed=failed,
            queued=queued,
            running=running,
            avg_tokens=avg_tokens,
            avg_cost_usd=avg_cost_usd,
            avg_latency_seconds=avg_latency_seconds,
            avg_cache_hit_rate=avg_cache_hit_rate,
            top_failure_reasons=top_failure_reasons,
        )

