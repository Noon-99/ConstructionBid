"""Application configuration using pydantic-settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get backend directory (where this file is located: backend/app/core/config.py -> backend/)
# Use a function to compute the path to avoid evaluation issues
def _get_backend_dir() -> Path:
    """Get the backend directory path."""
    return Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_get_backend_dir() / ".env"),  # Load .env from backend directory
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API settings
    api_title: str = "Construction Bid AI API"
    api_version: str = "v1"
    api_prefix: str = "/v1"
    debug: bool = Field(default=False, description="Enable debug mode")

    # Storage settings
    # Compute default storage path (backend/storage) - use absolute path to avoid issues
    # Note: Must compute at class definition time, not module load time
    storage_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent / "storage",
        description="Root directory for storing uploaded files",
    )

    # Document processing settings
    pdf_dpi: int = Field(
        default=200,
        ge=72,
        le=600,
        description="DPI for PDF to image conversion",
    )

    # Logging settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    log_format: Literal["json", "text"] = Field(
        default="json",
        description="Log format (json or text)",
    )

    # Evidence bbox extraction settings (Phase 8.6D)
    enable_ocr_bbox_extraction: bool = Field(
        default=False,
        description="Enable OCR fallback for bbox extraction (slower, only for scanned PDFs)",
    )

    # OpenAI settings
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key (required for AI features)",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model to use for vision tasks",
    )
    openai_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="OpenAI temperature for deterministic output",
    )
    openai_max_tokens: int = Field(
        default=4096,
        ge=1,
        le=100000,
        description="Maximum tokens for OpenAI API calls",
    )
    
    # Task 6: Prevailing wage multiplier (configurable, not hard-coded)
    prevailing_wage_multiplier: float = Field(
        default=1.5,
        ge=1.0,
        le=3.0,
        description="Labor rate multiplier for prevailing wage projects (DOT/public work). Range: 1.35-1.70 typical, default 1.5",
    )
    
    # Task 7: Roofing production rate for duration estimation
    roofing_production_rate_sf_per_day: float = Field(
        default=1000.0,
        ge=100.0,
        le=5000.0,
        description="Roofing production rate in square feet per day for duration estimation. Default: 1000 SF/day (typical for roof replacement crews)",
    )
    
    openai_timeout: float = Field(
        default=60.0,
        ge=10.0,
        le=300.0,
        description="Request timeout in seconds",
    )
    openai_max_concurrency_per_worker: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum concurrent OpenAI API calls per worker",
    )

    # Page indexing settings (Batch 2: batching + concurrency, Batch 4: guardrails)
    page_index_batch_size: int = Field(
        default=15,
        ge=1,
        le=100,
        description="Number of pages to process per batch in Stage 0.5",
    )
    page_index_concurrency: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Maximum concurrent page indexing operations per batch",
    )
    page_index_max_retries: int = Field(
        default=6,
        ge=1,
        le=10,
        description="Maximum retry attempts for failed page indexing operations",
    )
    max_page_index_pages: int = Field(
        default=500,
        ge=1,
        le=10000,
        description="Hard cap on number of pages that can be indexed (Batch 4: cost control)",
    )
    page_index_smart_mode_threshold: int = Field(
        default=120,
        ge=1,
        le=1000,
        description="Page count threshold above which smart index mode (caching + concurrency) is used",
    )
    
    # Large PDF page selection (fix empty extraction)
    large_pdf_threshold: int = Field(
        default=120,
        ge=1,
        description="Page count threshold for using index-driven page selection in Stages 1 and 2. PDFs >= this use wider sampling.",
    )
    stage1_max_pages_large: int = Field(
        default=12,
        ge=4,
        le=50,
        description="Maximum pages to analyze in Stage 1 for large PDFs (index-driven selection).",
    )
    stage2_max_pages_large: int = Field(
        default=8,
        ge=4,
        le=30,
        description="Maximum pages to extract in Stage 2 for large PDFs (index-driven selection).",
    )
    rescue_stage2_max_pages: int = Field(
        default=12,
        ge=4,
        le=30,
        description="Maximum pages for rescue rerun of Stage 2 when extraction returns 0 items.",
    )
    
    # Fast page indexing for large PDFs (TASK 2)
    page_index_fast_mode_threshold: int = Field(
        default=120,
        ge=1,
        description="Page count threshold for fast indexing mode (sampling instead of full scan).",
    )
    page_index_fast_max_pages: int = Field(
        default=80,
        ge=20,
        le=200,
        description="Maximum pages to index in fast mode (sampling + expansion around hot pages).",
    )
    page_index_stride: int = Field(
        default=10,
        ge=5,
        le=50,
        description="Stride for fast mode sampling (index every Nth page).",
    )
    page_index_expand_radius: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Radius for expanding around hot pages (±N pages) in fast mode.",
    )

    # Redis/RQ settings
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for job queue",
    )
    rq_queue_name: str = Field(
        default="pipeline",
        description="RQ queue name for pipeline jobs",
    )

    # PDF Export settings (Phase 6.4)
    frontend_base_url: str = Field(
        default="http://localhost:3000",
        description="Base URL for frontend (used for PDF generation)",
    )

    # LLM Cache settings (Phase 3.4)
    llm_cache_enabled: bool = Field(
        default=True,
        description="Enable SQLite-backed caching for OpenAI responses",
    )
    llm_cache_path: Path = Field(
        default=Path("./storage/cache/llm_cache.sqlite"),
        description="Path to SQLite cache database",
    )

    # Rule governance / authoring
    rule_authoring_auto_generate: bool = Field(
        default=False,
        description="Automatically generate draft YAML rules when governance detects missing coverage",
    )

    # Institutional extractor validation settings (Phase 4.1, 4.3)
    institutional_room_count_min: int = Field(
        default=15,
        ge=1,
        description="Minimum number of rooms required for institutional room program",
    )
    institutional_room_area_tolerance_pct: float = Field(
        default=5.0,
        ge=0.0,
        le=100.0,
        description="Tolerance percentage for room area sum vs totals (±%)",
    )
    institutional_largest_room_min_sf: float = Field(
        default=2500.0,
        ge=0.0,
        description="Minimum area for largest room (sanity check for institutional projects)",
    )

    # Procurement / compliance detection settings (Stage 1 enhancements)
    procurement_public_keywords: list[str] = Field(
        default_factory=lambda: [
            "department of transportation",
            "office of general services",
            "request for proposal",
            "public works",
            "state of",
            "county of",
            "city of",
            "town of",
            "school district",
            "federal project",
        ],
        description="Keyword indicators suggesting government/public procurement context",
    )
    procurement_prevailing_wage_keywords: list[str] = Field(
        default_factory=lambda: [
            "prevailing wage",
            "davis-bacon",
            "section 220",
            "wage schedule",
            "labor law",
        ],
        description="Keyword indicators suggesting prevailing wage requirements",
    )
    procurement_bond_keywords: list[str] = Field(
        default_factory=lambda: [
            "performance bond",
            "payment bond",
            "bid bond",
            "surety",
            "bonding requirements",
        ],
        description="Keyword indicators suggesting bond/insurance requirements",
    )
    procurement_public_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence threshold to mark project as public from heuristics",
    )
    procurement_default_prevailing_wage: bool = Field(
        default=True,
        description="Assume prevailing wage when project is detected as public and signals are weak",
    )
    procurement_default_bonds: bool = Field(
        default=True,
        description="Assume bond requirements when project is detected as public and signals are weak",
    )
    procurement_enable_gpt: bool = Field(
        default=True,
        description="Enable GPT assist for procurement detection when heuristics are inconclusive",
    )
    procurement_max_pages_to_review: int = Field(
        default=4,
        ge=1,
        le=12,
        description="Maximum number of pages to include when calling GPT for procurement detection",
    )

    # Stage 4: Compliance cost adjustments (prevailing wage, bond, insurance)
    compliance_prevailing_wage_multiplier: float = Field(
        default=1.5,
        ge=1.0,
        le=3.0,
        description="Labor rate multiplier applied when prevailing wage is required",
    )
    compliance_union_multiplier: float = Field(
        default=1.3,
        ge=1.0,
        le=3.0,
        description="Labor rate multiplier applied when union labor regime is detected",
    )
    compliance_bond_rate_pct: float = Field(
        default=2.5,
        ge=0.0,
        le=10.0,
        description="Percentage of subtotal used to estimate payment/performance bond costs",
    )
    compliance_insurance_rate_pct: float = Field(
        default=1.2,
        ge=0.0,
        le=10.0,
        description="Percentage of subtotal used to estimate supplemental insurance costs",
    )

    # Contractor profile settings (Phase 9.1A)
    default_contractor_profile_id: str = Field(
        default="nyc_row_house_masonry_v1",
        description="Default contractor profile ID for bid synthesis",
    )

    def model_post_init(self, __context: object) -> None:
        """Ensure storage directory exists."""
        self.storage_root.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Get application settings (dependency injection)."""
    return Settings()

