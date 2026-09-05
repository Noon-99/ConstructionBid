"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import batches, contractor_profiles, exports, health, jobs, pages, projects
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging

# Initialize settings and logging
settings = get_settings()
configure_logging(settings)

# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    debug=settings.debug,
)

# CORS middleware (allow all origins in development, specifically localhost:3000)
# MUST be registered BEFORE routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods including OPTIONS
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(projects.router, prefix=settings.api_prefix)
app.include_router(pages.router, prefix=settings.api_prefix)
app.include_router(jobs.router, prefix=settings.api_prefix)
app.include_router(batches.router, prefix=settings.api_prefix)
app.include_router(exports.router, prefix=settings.api_prefix)
app.include_router(contractor_profiles.router, prefix=settings.api_prefix)


@app.on_event("startup")
async def startup_event() -> None:
    """Application startup event."""
    from loguru import logger

    logger.info("Construction Bid AI API starting up")
    logger.info(f"Storage root: {settings.storage_root.absolute()}")
    logger.info(f"PDF DPI: {settings.pdf_dpi}")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown event."""
    from loguru import logger

    logger.info("Construction Bid AI API shutting down")

