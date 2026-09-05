"""Timing utilities for pipeline stages."""

import time
from contextlib import contextmanager
from typing import Generator

from loguru import logger


@contextmanager
def stage_timer(project_id: str, stage_name: str) -> Generator[None, None, None]:
    """Context manager to time a pipeline stage with logging."""
    start_time = time.perf_counter()
    logger.bind(project_id=project_id, stage=stage_name).info(
        f"Stage '{stage_name}' started"
    )
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start_time
        logger.bind(project_id=project_id, stage=stage_name).info(
            f"Stage '{stage_name}' completed in {elapsed:.3f}s"
        )

