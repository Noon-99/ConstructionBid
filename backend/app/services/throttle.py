"""Synchronous throttling for OpenAI API calls using threading.BoundedSemaphore."""

import threading
import time
from contextlib import contextmanager
from typing import Any

from loguru import logger


class Throttle:
    """Thread-safe throttling for limiting concurrent OpenAI API calls."""

    def __init__(self, max_concurrency: int) -> None:
        """
        Initialize throttle with max concurrency.

        Args:
            max_concurrency: Maximum number of concurrent calls allowed
        """
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self.max_concurrency = max_concurrency
        self.semaphore = threading.BoundedSemaphore(max_concurrency)
        self._wait_times: dict[str, list[float]] = {}  # stage_name -> list of wait times (ms)
        self._total_wait_ms: float = 0.0
        self._call_counts: dict[str, int] = {}  # stage_name -> call count
        self._total_calls: int = 0
        self._lock = threading.Lock()  # Protects metrics

    @contextmanager
    def acquire(self, stage_name: str, project_id: str | None = None) -> Any:
        """
        Context manager to acquire throttle lock.

        Measures wait time and logs if > 250ms.

        Args:
            stage_name: Name of the stage making the call
            project_id: Optional project ID for logging

        Yields:
            None (context manager)
        """
        wait_start = time.monotonic()

        # Acquire semaphore (may block)
        self.semaphore.acquire()

        wait_end = time.monotonic()
        wait_time_ms = (wait_end - wait_start) * 1000.0

        # Record metrics
        with self._lock:
            self._total_wait_ms += wait_time_ms
            if stage_name not in self._wait_times:
                self._wait_times[stage_name] = []
            self._wait_times[stage_name].append(wait_time_ms)
            
            # Track call counts
            if stage_name not in self._call_counts:
                self._call_counts[stage_name] = 0
            self._call_counts[stage_name] += 1
            self._total_calls += 1

        # Log if wait was significant
        if wait_time_ms > 250:
            log_ctx = logger.bind(
                stage_name=stage_name,
                wait_time_ms=round(wait_time_ms, 2),
            )
            if project_id:
                log_ctx = log_ctx.bind(project_id=project_id)
            log_ctx.warning(
                f"Throttle wait: {wait_time_ms:.0f}ms for stage {stage_name}"
            )

        try:
            yield
        finally:
            # Always release
            self.semaphore.release()

    def get_metrics(self) -> dict[str, Any]:
        """
        Get throttle metrics.

        Returns:
            Dictionary with throttle statistics
        """
        with self._lock:
            # Calculate wait time by stage
            wait_by_stage: dict[str, float] = {}
            for stage_name, wait_times in self._wait_times.items():
                wait_by_stage[stage_name] = sum(wait_times)

            return {
                "throttle_wait_ms_total": round(self._total_wait_ms, 2),
                "throttle_wait_ms_by_stage": {
                    stage: round(total_ms, 2) for stage, total_ms in wait_by_stage.items()
                },
                "throttle_max_concurrency": self.max_concurrency,
                "openai_calls_total": self._total_calls,
                "openai_calls_by_stage": self._call_counts.copy(),
            }

    def reset_metrics(self) -> None:
        """Reset throttle metrics (useful for testing)."""
        with self._lock:
            self._wait_times.clear()
            self._total_wait_ms = 0.0
            self._call_counts.clear()
            self._total_calls = 0


# Module-level singleton instance (will be initialized by dependency injection)
_throttle_instance: Throttle | None = None
_throttle_lock = threading.Lock()


def get_throttle(max_concurrency: int | None = None) -> Throttle:
    """
    Get or create singleton throttle instance.

    Args:
        max_concurrency: Max concurrency (required on first call)

    Returns:
        Throttle instance
    """
    global _throttle_instance

    if _throttle_instance is None:
        if max_concurrency is None:
            raise ValueError("max_concurrency required for first throttle initialization")
        with _throttle_lock:
            if _throttle_instance is None:
                _throttle_instance = Throttle(max_concurrency)

    return _throttle_instance

