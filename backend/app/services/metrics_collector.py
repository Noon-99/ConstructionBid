"""Metrics collector for Phase 2.6C - Evaluation Metrics.

Tracks pages sent, tokens, costs, latency, and scores per project.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


class StageMetrics(BaseModel):
    """Metrics for a single pipeline stage."""

    stage_name: str = Field(description="Stage name (e.g., 'stage_1_document_analysis')")
    pages_sent: int = Field(default=0, description="Number of pages sent to this stage")
    tokens_prompt: int = Field(default=0, description="Prompt tokens used")
    tokens_completion: int = Field(default=0, description="Completion tokens used")
    tokens_total: int = Field(default=0, description="Total tokens used")
    latency_seconds: float = Field(default=0.0, description="Latency in seconds")
    cost_estimate_usd: float = Field(default=0.0, description="Estimated cost in USD")


class ProjectMetrics(BaseModel):
    """Complete metrics for a project run."""

    project_id: str = Field(description="Project ID")
    created_at: datetime = Field(default_factory=datetime.now, description="When metrics were collected")
    
    # Stage-level metrics
    stage_metrics: list[StageMetrics] = Field(
        default_factory=list, description="Metrics per stage"
    )
    
    # Aggregated metrics
    total_pages_sent_stage1: int = Field(default=0, description="Total pages sent to Stage 1")
    total_pages_sent_stage2: int = Field(default=0, description="Total pages sent to Stage 2")
    total_pages_sent_recovery: int = Field(default=0, description="Total pages sent during recovery")
    
    total_tokens: int = Field(default=0, description="Total tokens across all stages")
    total_cost_estimate_usd: float = Field(default=0.0, description="Total estimated cost in USD")
    
    total_latency_seconds: float = Field(default=0.0, description="Total pipeline latency")
    
    # Quality metrics
    critical_coverage_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Critical-5 coverage score (0.0-1.0)"
    )
    dimension_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Authoritative dimension confidence (0.0-1.0)"
    )
    validation_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Validation score (0.0-1.0)"
    )
    
    # Cache metrics (Phase 3.4)
    cache_hits_total: int = Field(
        default=0, description="Total cache hits"
    )
    cache_misses_total: int = Field(
        default=0, description="Total cache misses"
    )
    cache_hits_by_stage: dict[str, int] = Field(
        default_factory=dict, description="Cache hits by stage"
    )
    cache_misses_by_stage: dict[str, int] = Field(
        default_factory=dict, description="Cache misses by stage"
    )
    cache_hit_rate: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Cache hit rate percentage"
    )
    
    # Throttle metrics (Phase 3.3)
    throttle_wait_ms_total: float = Field(
        default=0.0, description="Total throttle wait time in milliseconds"
    )
    throttle_wait_ms_by_stage: dict[str, float] = Field(
        default_factory=dict, description="Throttle wait time by stage (ms)"
    )
    openai_calls_total: int = Field(
        default=0, description="Total number of OpenAI API calls"
    )
    openai_calls_by_stage: dict[str, int] = Field(
        default_factory=dict, description="OpenAI API calls by stage"
    )


class MetricsCollector:
    """Collects and aggregates metrics during pipeline execution."""

    def __init__(self, project_id: str) -> None:
        """Initialize metrics collector."""
        self.project_id = project_id
        self.metrics = ProjectMetrics(project_id=project_id)
        self.stage_start_times: dict[str, float] = {}
        self.stage_token_usage: dict[str, dict[str, int]] = {}
        self.stage_pages: dict[str, int] = {}
        self.openai_call_counts: dict[str, int] = {}  # Track OpenAI calls by stage
        
        # Cost per 1K tokens (approximate, as of 2024)
        # gpt-4o-mini: $0.15/$0.60 per 1M tokens (input/output)
        self.cost_per_1k_input = 0.00015  # $0.15 per 1M tokens
        self.cost_per_1k_output = 0.00060  # $0.60 per 1M tokens

    def start_stage(self, stage_name: str, pages_sent: int = 0) -> None:
        """Mark the start of a stage."""
        self.stage_start_times[stage_name] = time.perf_counter()
        self.stage_pages[stage_name] = pages_sent

    def record_tokens(
        self, stage_name: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        """Record token usage for a stage."""
        if stage_name not in self.stage_token_usage:
            self.stage_token_usage[stage_name] = {}
        self.stage_token_usage[stage_name] = {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        }
    
    def record_openai_call(self, stage_name: str) -> None:
        """Record an OpenAI API call for a stage."""
        if stage_name not in self.openai_call_counts:
            self.openai_call_counts[stage_name] = 0
        self.openai_call_counts[stage_name] += 1

    def end_stage(self, stage_name: str) -> None:
        """Mark the end of a stage and calculate metrics."""
        if stage_name not in self.stage_start_times:
            logger.warning(f"Stage {stage_name} ended without start time")
            return

        latency = time.perf_counter() - self.stage_start_times[stage_name]
        pages_sent = self.stage_pages.get(stage_name, 0)
        
        token_usage = self.stage_token_usage.get(stage_name, {})
        prompt_tokens = token_usage.get("prompt", 0)
        completion_tokens = token_usage.get("completion", 0)
        total_tokens = token_usage.get("total", 0)
        
        # Estimate cost
        cost = (
            (prompt_tokens / 1000) * self.cost_per_1k_input
            + (completion_tokens / 1000) * self.cost_per_1k_output
        )

        stage_metric = StageMetrics(
            stage_name=stage_name,
            pages_sent=pages_sent,
            tokens_prompt=prompt_tokens,
            tokens_completion=completion_tokens,
            tokens_total=total_tokens,
            latency_seconds=latency,
            cost_estimate_usd=cost,
        )

        self.metrics.stage_metrics.append(stage_metric)

        # Clean up
        del self.stage_start_times[stage_name]

    def set_quality_metrics(
        self,
        critical_coverage_score: float | None = None,
        dimension_confidence: float | None = None,
        validation_score: float | None = None,
    ) -> None:
        """Set quality metrics after pipeline completion."""
        if critical_coverage_score is not None:
            self.metrics.critical_coverage_score = critical_coverage_score
        if dimension_confidence is not None:
            self.metrics.dimension_confidence = dimension_confidence
        if validation_score is not None:
            self.metrics.validation_score = validation_score

    def finalize(self) -> ProjectMetrics:
        """Finalize metrics and calculate aggregates."""
        # Aggregate totals
        self.metrics.total_tokens = sum(
            stage.tokens_total for stage in self.metrics.stage_metrics
        )
        self.metrics.total_cost_estimate_usd = sum(
            stage.cost_estimate_usd for stage in self.metrics.stage_metrics
        )
        self.metrics.total_latency_seconds = sum(
            stage.latency_seconds for stage in self.metrics.stage_metrics
        )

        # Aggregate pages by stage type
        for stage in self.metrics.stage_metrics:
            if "stage_1" in stage.stage_name or "page_indexing" in stage.stage_name:
                self.metrics.total_pages_sent_stage1 += stage.pages_sent
            elif "stage_2" in stage.stage_name or "extraction" in stage.stage_name:
                self.metrics.total_pages_sent_stage2 += stage.pages_sent
            elif "recovery" in stage.stage_name or "rerun" in stage.stage_name:
                self.metrics.total_pages_sent_recovery += stage.pages_sent

        # Get throttle metrics (Phase 3.3)
        try:
            from app.services.throttle import get_throttle
            throttle = get_throttle()
            throttle_metrics = throttle.get_metrics()
            self.metrics.throttle_wait_ms_total = throttle_metrics.get("throttle_wait_ms_total", 0.0)
            self.metrics.throttle_wait_ms_by_stage = throttle_metrics.get("throttle_wait_ms_by_stage", {})
            self.metrics.openai_calls_total = throttle_metrics.get("openai_calls_total", 0)
            self.metrics.openai_calls_by_stage = throttle_metrics.get("openai_calls_by_stage", {})
        except Exception as e:
            logger.warning(f"Failed to get throttle metrics: {e}")
            # Fallback to local counts if throttle not available
            self.metrics.openai_calls_total = sum(self.openai_call_counts.values())
            self.metrics.openai_calls_by_stage = self.openai_call_counts.copy()

        # Get cache metrics (Phase 3.4) - aggregate from all OpenAI clients
        # Note: Cache stats are tracked per-client, so we need to aggregate
        # For now, we'll get stats from the document_analyzer's client if available
        try:
            # Try to get cache stats from pipeline's document_analyzer
            # This is a bit of a hack, but cache stats are per-client instance
            # In practice, all clients share the same cache, so we can get stats from any
            cache_stats = self._get_cache_stats_from_pipeline()
            if cache_stats:
                self.metrics.cache_hits_total = cache_stats.get("cache_hits_total", 0)
                self.metrics.cache_misses_total = cache_stats.get("cache_misses_total", 0)
                self.metrics.cache_hits_by_stage = cache_stats.get("cache_hits_by_stage", {})
                self.metrics.cache_misses_by_stage = cache_stats.get("cache_misses_by_stage", {})
                self.metrics.cache_hit_rate = cache_stats.get("cache_hit_rate", 0.0)
        except Exception as e:
            logger.warning(f"Failed to get cache metrics: {e}")

    def _get_cache_stats_from_pipeline(self) -> dict[str, Any] | None:
        """
        Get cache stats from pipeline's OpenAI clients.
        
        This is a workaround - cache stats are tracked per-client instance.
        In practice, we aggregate from the first available client.
        """
        # This will be called from pipeline context where clients are available
        # For now, return None and let pipeline pass stats explicitly
        return None

    def set_cache_stats(self, cache_stats: dict[str, Any]) -> None:
        """
        Set cache statistics from OpenAI client.
        
        Args:
            cache_stats: Dictionary with cache_hits_total, cache_misses_total, etc.
        """
        self.metrics.cache_hits_total = cache_stats.get("cache_hits_total", 0)
        self.metrics.cache_misses_total = cache_stats.get("cache_misses_total", 0)
        self.metrics.cache_hits_by_stage = cache_stats.get("cache_hits_by_stage", {})
        self.metrics.cache_misses_by_stage = cache_stats.get("cache_misses_by_stage", {})
        self.metrics.cache_hit_rate = cache_stats.get("cache_hit_rate", 0.0)

    def save(self, output_dir: Path) -> Path:
        """Save metrics to JSON file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics_file = output_dir / "metrics.json"
        
        with open(metrics_file, "w") as f:
            json.dump(self.metrics.model_dump(mode="json"), f, indent=2, default=str)
        
        logger.bind(project_id=self.project_id).info(f"Metrics saved to {metrics_file}")
        return metrics_file

