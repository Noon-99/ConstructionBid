"""SQLite-backed cache for OpenAI Vision API responses."""

import hashlib
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class CachedResponse:
    """Cached OpenAI response."""

    def __init__(
        self,
        response_json: str,
        token_usage_json: str | None = None,
        created_at: str | None = None,
    ) -> None:
        """Initialize cached response."""
        self.response_json = response_json
        self.token_usage_json = token_usage_json
        self.created_at = created_at


class LLMCache:
    """SQLite-backed cache for OpenAI Vision API calls."""

    SCHEMA_VERSION = "v2"  # Increment to invalidate all cache (v2: added text to extraction prompts)

    def __init__(self, cache_path: Path, enabled: bool = True) -> None:
        """
        Initialize LLM cache.

        Args:
            cache_path: Path to SQLite database file
            enabled: Whether caching is enabled
        """
        self.cache_path = cache_path
        self.enabled = enabled
        self._lock = threading.Lock()

        if not enabled:
            logger.debug("LLM cache disabled")
            return

        # Ensure cache directory exists
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        try:
            conn = sqlite3.connect(
                str(self.cache_path),
                check_same_thread=False,  # Allow multi-threaded access
                timeout=10.0,
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    model TEXT NOT NULL,
                    detail TEXT,
                    prompt_hash TEXT NOT NULL,
                    image_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    token_usage_json TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_at ON llm_cache(created_at)"
            )
            conn.commit()
            conn.close()
            logger.debug(f"LLM cache initialized at {self.cache_path}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM cache: {e}")
            self.enabled = False

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection (thread-safe)."""
        return sqlite3.connect(
            str(self.cache_path),
            check_same_thread=False,
            timeout=10.0,
        )

    def compute_cache_key(
        self,
        model: str,
        detail: str,
        prompt_text: str,
        image_bytes: bytes,
        schema_version: str | None = None,
    ) -> str:
        """
        Compute cache key from inputs.

        Args:
            model: Model name (e.g., "gpt-4o-mini")
            detail: Vision detail level ("low" or "high")
            prompt_text: Exact prompt text
            image_bytes: Image bytes
            schema_version: Schema version (defaults to SCHEMA_VERSION)

        Returns:
            SHA256 hash as hex string
        """
        schema_version = schema_version or self.SCHEMA_VERSION

        # Hash image bytes
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        # Hash prompt text
        prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

        # Combine all components
        key_components = f"{schema_version}:{model}:{detail}:{prompt_hash}:{image_hash}"

        # Hash the combined key
        cache_key = hashlib.sha256(key_components.encode("utf-8")).hexdigest()

        return cache_key

    def get(self, cache_key: str) -> CachedResponse | None:
        """
        Get cached response.

        Args:
            cache_key: Cache key

        Returns:
            CachedResponse if found, None otherwise
        """
        if not self.enabled:
            return None

        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.execute(
                    "SELECT response_json, token_usage_json, created_at FROM llm_cache WHERE cache_key = ?",
                    (cache_key,),
                )
                row = cursor.fetchone()
                conn.close()

                if row:
                    return CachedResponse(
                        response_json=row[0],
                        token_usage_json=row[1],
                        created_at=row[2],
                    )
                return None

            except Exception as e:
                logger.warning(f"Cache read error (treating as miss): {e}")
                return None

    def set(
        self,
        cache_key: str,
        model: str,
        detail: str,
        prompt_hash: str,
        image_hash: str,
        response_json: str,
        token_usage_json: str | None = None,
    ) -> None:
        """
        Store response in cache.

        Args:
            cache_key: Cache key
            model: Model name
            detail: Vision detail level
            prompt_hash: Hash of prompt text
            image_hash: Hash of image bytes
            response_json: Response content (JSON string)
            token_usage_json: Optional token usage JSON
        """
        if not self.enabled:
            return

        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO llm_cache
                    (cache_key, created_at, model, detail, prompt_hash, image_hash, response_json, token_usage_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cache_key,
                        datetime.now().isoformat(),
                        model,
                        detail,
                        prompt_hash,
                        image_hash,
                        response_json,
                        token_usage_json,
                    ),
                )
                conn.commit()
                conn.close()

            except Exception as e:
                logger.warning(f"Cache write error: {e}")

    def clear(self) -> None:
        """Clear all cache entries (useful for testing)."""
        if not self.enabled:
            return

        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute("DELETE FROM llm_cache")
                conn.commit()
                conn.close()
                logger.info("LLM cache cleared")
            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")


# Module-level singleton instance
_cache_instance: LLMCache | None = None
_cache_lock = threading.Lock()


def get_llm_cache(cache_path: Path | None = None, enabled: bool | None = None) -> LLMCache:
    """
    Get or create singleton LLM cache instance.

    Args:
        cache_path: Path to cache database (required on first call)
        enabled: Whether caching is enabled (required on first call)

    Returns:
        LLMCache instance
    """
    global _cache_instance

    if _cache_instance is None:
        if cache_path is None or enabled is None:
            # Try to get from settings
            try:
                from app.core.config import Settings
                settings = Settings()
                cache_path = cache_path or settings.llm_cache_path
                enabled = enabled if enabled is not None else settings.llm_cache_enabled
            except Exception:
                raise ValueError("cache_path and enabled required for first cache initialization")

        with _cache_lock:
            if _cache_instance is None:
                _cache_instance = LLMCache(cache_path, enabled)

    return _cache_instance
