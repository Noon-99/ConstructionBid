"""OpenAI API client wrapper with retries and error handling."""

import json
import time
from typing import Any

from loguru import logger
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import base64
import hashlib

from app.core.config import Settings
from app.services.llm_cache import get_llm_cache
from app.services.throttle import get_throttle


class OpenAIError(Exception):
    """Base exception for OpenAI client errors."""


class OpenAIRetryableError(OpenAIError):
    """Retryable OpenAI errors (429, 5xx, timeouts)."""


class OpenAINonRetryableError(OpenAIError):
    """Non-retryable OpenAI errors (4xx except 429, invalid requests)."""


class OpenAIClient:
    """Wrapper around OpenAI API with retries and structured logging."""

    def __init__(self, settings: Settings) -> None:
        """Initialize OpenAI client with settings."""
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout,
        )
        self.default_model = getattr(settings, "openai_model", "gpt-4o-mini")
        self.default_temperature = getattr(settings, "openai_temperature", 0.1)
        self.default_max_tokens = getattr(settings, "openai_max_tokens", 1500)
        self.timeout = getattr(settings, "openai_timeout", 60.0)
        self.last_usage: dict[str, int] | None = None  # Store last token usage
        
        # Initialize throttle singleton
        self.throttle = get_throttle(settings.openai_max_concurrency_per_worker)
        
        # Initialize LLM cache singleton
        self.llm_cache = get_llm_cache(
            cache_path=settings.llm_cache_path,
            enabled=settings.llm_cache_enabled,
        )
        
        # Track cache hits/misses for metrics
        self._cache_hits: dict[str, int] = {}
        self._cache_misses: dict[str, int] = {}

    def _extract_cache_data_from_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str, str, bytes]:
        """
        Extract prompt text, detail level, and combined image bytes from messages.

        Args:
            messages: OpenAI messages format

        Returns:
            Tuple of (prompt_text, detail, combined_image_bytes)
        """
        prompt_parts: list[str] = []
        detail = "low"  # Default
        image_bytes_list: list[bytes] = []

        for message in messages:
            if message.get("role") == "user" and "content" in message:
                for content_item in message["content"]:
                    if content_item.get("type") == "text":
                        prompt_parts.append(content_item.get("text", ""))
                    elif content_item.get("type") == "image_url":
                        image_url = content_item.get("image_url", {})
                        url = image_url.get("url", "")
                        detail = image_url.get("detail", "low")

                        # Extract base64 data from data URL
                        if url.startswith("data:"):
                            # Format: data:image/png;base64,{base64_data}
                            parts = url.split(",", 1)
                            if len(parts) == 2:
                                try:
                                    img_bytes = base64.b64decode(parts[1])
                                    image_bytes_list.append(img_bytes)
                                except Exception as e:
                                    logger.warning(f"Failed to decode image for cache: {e}")

        prompt_text = " ".join(prompt_parts)
        
        # Combine all image bytes for hashing
        combined_image_bytes = b"".join(image_bytes_list)

        return prompt_text, detail, combined_image_bytes

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if error is retryable."""
        # Check for OpenAI SDK specific error types
        from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

        if isinstance(error, RateLimitError):
            return True
        if isinstance(error, APITimeoutError):
            return True
        if isinstance(error, APIConnectionError):
            # Connection errors (network, SSL) should be retryable
            return True
        if isinstance(error, APIError):
            # Check status code for retryable errors
            if hasattr(error, "status_code"):
                status = error.status_code
                if status == 429:  # Rate limit
                    return True
                if status >= 500:  # Server errors
                    return True

        # Fallback to string matching for other exceptions
        error_str = str(error).lower()
        if "429" in error_str or "rate limit" in error_str:
            return True
        if "500" in error_str or "502" in error_str or "503" in error_str:
            return True
        if "timeout" in error_str or "timed out" in error_str:
            return True
        if "connection" in error_str or "ssl" in error_str or "network" in error_str:
            return True
        return False

    @retry(
        retry=retry_if_exception_type(OpenAIRetryableError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def call_vision(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        request_id: str | None = None,
        stage_name: str = "unknown",
        project_id: str | None = None,
    ) -> str:
        """
        Call OpenAI Vision API with retries and throttling.

        Args:
            messages: List of message dicts (must support image inputs)
            model: Model name (defaults to gpt-4o-mini)
            temperature: Temperature (defaults to 0.1)
            max_tokens: Max tokens (defaults to 4000)
            request_id: Optional request ID for logging
            stage_name: Stage name for throttling and metrics (defaults to "unknown")
            project_id: Optional project ID for throttling logs

        Returns:
            Raw text output from the model

        Raises:
            OpenAIRetryableError: For retryable errors (429, 5xx, timeouts)
            OpenAINonRetryableError: For non-retryable errors
        """
        model = model or self.default_model
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens

        log_ctx = logger.bind(
            request_id=request_id or "unknown",
            model=model,
            stage="openai_vision",
        )

        log_ctx.info(f"Calling OpenAI Vision API: {model}")

        try:
            start_time = time.perf_counter()

            # Extract cache data from messages
            prompt_text, detail, combined_image_bytes = self._extract_cache_data_from_messages(
                messages
            )

            # Compute cache key
            cache_key = self.llm_cache.compute_cache_key(
                model=model,
                detail=detail,
                prompt_text=prompt_text,
                image_bytes=combined_image_bytes,
            )

            # Check cache before API call
            cached_response = self.llm_cache.get(cache_key)
            if cached_response:
                log_ctx.debug(f"Cache HIT for stage {stage_name}")
                # Track cache hit
                if stage_name not in self._cache_hits:
                    self._cache_hits[stage_name] = 0
                self._cache_hits[stage_name] += 1

                # Parse token usage if available
                if cached_response.token_usage_json:
                    try:
                        import json
                        usage_data = json.loads(cached_response.token_usage_json)
                        self.last_usage = {
                            "prompt_tokens": usage_data.get("prompt_tokens", 0),
                            "completion_tokens": usage_data.get("completion_tokens", 0),
                            "total_tokens": usage_data.get("total_tokens", 0),
                        }
                    except Exception:
                        self.last_usage = None

                return cached_response.response_json

            # Cache miss - make API call
            log_ctx.debug(f"Cache MISS for stage {stage_name}")
            if stage_name not in self._cache_misses:
                self._cache_misses[stage_name] = 0
            self._cache_misses[stage_name] += 1

            # Acquire throttle lock (may block if at max concurrency)
            with self.throttle.acquire(stage_name=stage_name, project_id=project_id):
                # Try to use response_format for JSON-only output (gpt-4o-mini supports this)
                # If not available, fall back to regular call (prompt will enforce JSON)
                call_kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }

                # Use response_format for JSON mode if model supports it
                # Note: gpt-4o-mini supports response_format with type="json_object"
                # but we need to ensure the prompt explicitly requests JSON
                # For now, we rely on strict prompt + retry mechanism
                # response_format={"type": "json_object"} can be added if needed

                # Timeout is set in client initialization, not in create() call
                response = self.client.chat.completions.create(**call_kwargs)

            elapsed = time.perf_counter() - start_time
            content = response.choices[0].message.content or ""

            if not content:
                log_ctx.warning("OpenAI returned empty content")

            # Log token usage if available
            usage = response.usage
            token_usage_json = None
            if usage:
                self.last_usage = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                }
                import json
                token_usage_json = json.dumps(self.last_usage)
                log_ctx.info(
                    f"OpenAI call completed in {elapsed:.3f}s | "
                    f"tokens: {usage.prompt_tokens} prompt + "
                    f"{usage.completion_tokens} completion = "
                    f"{usage.total_tokens} total"
                )
            else:
                self.last_usage = None
                log_ctx.info(f"OpenAI call completed in {elapsed:.3f}s")

            # Store in cache
            prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
            image_hash = hashlib.sha256(combined_image_bytes).hexdigest()
            self.llm_cache.set(
                cache_key=cache_key,
                model=model,
                detail=detail,
                prompt_hash=prompt_hash,
                image_hash=image_hash,
                response_json=content,
                token_usage_json=token_usage_json,
            )

            return content

        except Exception as e:
            error_msg = str(e)
            log_ctx.error(f"OpenAI API error: {error_msg}")

            # Clear usage on error
            self.last_usage = None
            
            if self._is_retryable_error(e):
                raise OpenAIRetryableError(f"Retryable error: {error_msg}") from e
            else:
                raise OpenAINonRetryableError(f"Non-retryable error: {error_msg}") from e

    def get_last_usage(self) -> dict[str, int] | None:
        """Get the last token usage from the most recent API call."""
        return self.last_usage

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache hit/miss statistics.

        Returns:
            Dictionary with cache stats by stage
        """
        total_hits = sum(self._cache_hits.values())
        total_misses = sum(self._cache_misses.values())
        total_requests = total_hits + total_misses
        hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "cache_hits_total": total_hits,
            "cache_misses_total": total_misses,
            "cache_hits_by_stage": self._cache_hits.copy(),
            "cache_misses_by_stage": self._cache_misses.copy(),
            "cache_hit_rate": round(hit_rate, 2),
        }

    @retry(
        retry=retry_if_exception_type(OpenAIRetryableError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def call_chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        *,
        request_id: str | None = None,
        stage_name: str = "openai_chat",
        project_id: str | None = None,
    ) -> str:
        """Call OpenAI chat completions API for text-only prompts with caching and retries."""

        model = model or self.default_model
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens

        log_ctx = logger.bind(
            request_id=request_id or "unknown",
            model=model,
            stage=stage_name,
        )
        log_ctx.info(f"Calling OpenAI Chat API: {model}")

        try:
            start_time = time.perf_counter()

            prompt_text, _detail, _images = self._extract_cache_data_from_messages(messages)
            detail = "text"
            cache_key = self.llm_cache.compute_cache_key(
                model=model,
                detail=detail,
                prompt_text=prompt_text,
                image_bytes=b"",
            )

            cached_response = self.llm_cache.get(cache_key)
            if cached_response:
                log_ctx.debug(f"Cache HIT for stage {stage_name}")
                self._cache_hits[stage_name] = self._cache_hits.get(stage_name, 0) + 1

                if cached_response.token_usage_json:
                    try:
                        usage_data = json.loads(cached_response.token_usage_json)
                        self.last_usage = {
                            "prompt_tokens": usage_data.get("prompt_tokens", 0),
                            "completion_tokens": usage_data.get("completion_tokens", 0),
                            "total_tokens": usage_data.get("total_tokens", 0),
                        }
                    except Exception:
                        self.last_usage = None

                return cached_response.response_json

            log_ctx.debug(f"Cache MISS for stage {stage_name}")
            self._cache_misses[stage_name] = self._cache_misses.get(stage_name, 0) + 1

            with self.throttle.acquire(stage_name=stage_name, project_id=project_id):
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            elapsed = time.perf_counter() - start_time
            content = response.choices[0].message.content or ""

            usage = response.usage
            token_usage_json = None
            if usage:
                self.last_usage = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                }
                token_usage_json = json.dumps(self.last_usage)
                log_ctx.info(
                    f"OpenAI chat call completed in {elapsed:.3f}s | "
                    f"tokens: {usage.prompt_tokens} prompt + "
                    f"{usage.completion_tokens} completion = "
                    f"{usage.total_tokens} total"
                )
            else:
                self.last_usage = None
                log_ctx.info(f"OpenAI chat call completed in {elapsed:.3f}s")

            prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
            self.llm_cache.set(
                cache_key=cache_key,
                model=model,
                detail=detail,
                prompt_hash=prompt_hash,
                image_hash=hashlib.sha256(b"").hexdigest(),
                response_json=content,
                token_usage_json=token_usage_json,
            )

            return content

        except Exception as e:  # pragma: no cover - defensive logging
            error_msg = str(e)
            log_ctx.error(f"OpenAI chat API error: {error_msg}")
            self.last_usage = None

            if self._is_retryable_error(e):
                raise OpenAIRetryableError(f"Retryable error: {error_msg}") from e
            raise OpenAINonRetryableError(f"Non-retryable error: {error_msg}") from e