"""Health check endpoint."""

from fastapi import APIRouter
from app.core.config import get_settings
from app.services.job_queue import JobQueueService

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@router.get("/health/redis")
async def health_check_redis() -> dict[str, str]:
    """Check Redis connectivity."""
    try:
        settings = get_settings()
        job_queue = JobQueueService(settings)
        # Try to access redis_conn property (will connect and ping)
        job_queue.redis_conn.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "redis": "disconnected", "error": str(e)}

