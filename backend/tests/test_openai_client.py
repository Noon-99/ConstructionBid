"""Unit tests for OpenAI client (mocked, no network calls)."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openai import APIError, APITimeoutError, RateLimitError

from app.core.config import Settings
from app.services.openai_client import (
    OpenAIClient,
    OpenAINonRetryableError,
    OpenAIRetryableError,
)


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        openai_api_key="test-key-12345",
        openai_model="gpt-4o-mini",
        openai_temperature=0.1,
        openai_max_tokens=1500,
        openai_timeout=60.0,
        llm_cache_enabled=False,  # Disable cache for most tests
    )


@pytest.fixture
def mock_openai_response() -> MagicMock:
    """Create a mock OpenAI response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = '{"test": "response"}'
    response.usage = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    response.usage.total_tokens = 150
    return response


def test_call_vision_success(settings: Settings, mock_openai_response: MagicMock) -> None:
    """Test successful OpenAI Vision API call."""
    with patch("app.services.openai_client.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_openai_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(settings)
        messages = [{"role": "user", "content": [{"type": "text", "text": "test"}]}]

        result = client.call_vision(messages, request_id="test-123")

        assert result == '{"test": "response"}'
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["max_tokens"] == 1500
        # Note: timeout is set in client initialization, not in create() call


def test_call_vision_rate_limit_error(settings: Settings) -> None:
    """Test that rate limit errors are retryable."""
    with patch("app.services.openai_client.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(),
            body=MagicMock(),
        )
        mock_client.chat.completions.create.side_effect = rate_limit_error
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(settings)
        messages = [{"role": "user", "content": [{"type": "text", "text": "test"}]}]

        with pytest.raises(OpenAIRetryableError):
            client.call_vision(messages, request_id="test-123")


def test_call_vision_timeout_error(settings: Settings) -> None:
    """Test that timeout errors are retryable."""
    with patch("app.services.openai_client.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        # Use actual APITimeoutError if available, otherwise create a mock
        try:
            timeout_error = APITimeoutError(request=MagicMock(), message="Request timed out")
        except TypeError:
            # Fallback: create exception that will be detected by string matching
            timeout_error = Exception("Request timed out")
        mock_client.chat.completions.create.side_effect = timeout_error
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(settings)
        messages = [{"role": "user", "content": [{"type": "text", "text": "test"}]}]

        with pytest.raises(OpenAIRetryableError):
            client.call_vision(messages, request_id="test-123")


def test_call_vision_server_error(settings: Settings) -> None:
    """Test that 5xx server errors are retryable."""
    with patch("app.services.openai_client.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        # Create an exception that will be detected by string matching fallback
        # The _is_retryable_error method checks for "500" in error string
        server_error = Exception("500 Internal server error")
        mock_client.chat.completions.create.side_effect = server_error
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(settings)
        messages = [{"role": "user", "content": [{"type": "text", "text": "test"}]}]

        with pytest.raises(OpenAIRetryableError):
            client.call_vision(messages, request_id="test-123")


def test_call_vision_client_error(settings: Settings) -> None:
    """Test that 4xx client errors (except 429) are non-retryable."""
    with patch("app.services.openai_client.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        # Create a mock APIError with status_code attribute
        try:
            response = MagicMock()
            response.status_code = 400
            client_error = APIError(message="Bad request", request=MagicMock(), body=None, response=response)
        except TypeError:
            # Fallback: create exception with status_code attribute
            client_error = Exception("Bad request")
            client_error.status_code = 400
        mock_client.chat.completions.create.side_effect = client_error
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(settings)
        messages = [{"role": "user", "content": [{"type": "text", "text": "test"}]}]

        with pytest.raises(OpenAINonRetryableError):
            client.call_vision(messages, request_id="test-123")


def test_call_vision_empty_content(settings: Settings) -> None:
    """Test handling of empty content response."""
    with patch("app.services.openai_client.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = ""
        response.usage = None
        mock_client.chat.completions.create.return_value = response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(settings)
        messages = [{"role": "user", "content": [{"type": "text", "text": "test"}]}]

        result = client.call_vision(messages, request_id="test-123")
        assert result == ""


def test_cache_hit_avoids_openai_call(settings: Settings) -> None:
    """Test that cache hit returns cached response without calling OpenAI."""
    import tempfile
    from pathlib import Path
    from app.services.llm_cache import _cache_instance, _cache_lock, get_llm_cache
    
    # Create temp cache path
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test_cache.sqlite"
        
        # Reset singleton cache instance before creating client
        with _cache_lock:
            import app.services.llm_cache
            app.services.llm_cache._cache_instance = None
        
        # Update settings
        settings.llm_cache_enabled = True
        settings.llm_cache_path = cache_path
        
        with patch("app.services.openai_client.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            
            # Force cache reinitialization
            with _cache_lock:
                app.services.llm_cache._cache_instance = None
            
            client = OpenAIClient(settings)
            
            # Create messages with image
            import base64
            test_image_bytes = b"fake_image_data"
            test_image_b64 = base64.b64encode(test_image_bytes).decode("utf-8")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract data"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{test_image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ]
            
            # First call - should call OpenAI and cache
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '{"cached": "response"}'
            mock_response.usage = MagicMock()
            mock_response.usage.prompt_tokens = 100
            mock_response.usage.completion_tokens = 50
            mock_response.usage.total_tokens = 150
            mock_client.chat.completions.create.return_value = mock_response
            
            result1 = client.call_vision(messages, request_id="test-1", stage_name="test_stage")
            assert result1 == '{"cached": "response"}'
            assert mock_client.chat.completions.create.call_count == 1
            
            # Second call with same input - should use cache, no OpenAI call
            result2 = client.call_vision(messages, request_id="test-2", stage_name="test_stage")
            assert result2 == '{"cached": "response"}'
            assert mock_client.chat.completions.create.call_count == 1  # Still 1, no new call
            
            # Check cache stats
            stats = client.get_cache_stats()
            assert stats["cache_hits_total"] == 1
            assert stats["cache_misses_total"] == 1
            assert stats["cache_hit_rate"] == 50.0


def test_cache_miss_different_prompt(settings: Settings) -> None:
    """Test that different prompt creates cache miss."""
    import tempfile
    from pathlib import Path
    from app.services.llm_cache import _cache_instance, _cache_lock
    
    # Reset singleton cache instance
    with _cache_lock:
        global _cache_instance
        _cache_instance = None
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test_cache.sqlite"
        settings.llm_cache_enabled = True
        settings.llm_cache_path = cache_path
        
        with patch("app.services.openai_client.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            
            client = OpenAIClient(settings)
            
            import base64
            test_image_bytes = b"fake_image_data"
            test_image_b64 = base64.b64encode(test_image_bytes).decode("utf-8")
            
            # First call
            messages1 = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Prompt 1"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{test_image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ]
            
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '{"result": "1"}'
            mock_response.usage = MagicMock()
            mock_response.usage.prompt_tokens = 100
            mock_response.usage.completion_tokens = 50
            mock_response.usage.total_tokens = 150
            mock_client.chat.completions.create.return_value = mock_response
            
            client.call_vision(messages1, stage_name="test_stage")
            
            # Second call with different prompt - should be a miss
            messages2 = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Prompt 2"},  # Different prompt
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{test_image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ]
            
            client.call_vision(messages2, stage_name="test_stage")
            
            # Should have made 2 API calls (both misses)
            assert mock_client.chat.completions.create.call_count == 2
            
            stats = client.get_cache_stats()
            assert stats["cache_hits_total"] == 0
            assert stats["cache_misses_total"] == 2


def test_cache_disabled(settings: Settings) -> None:
    """Test that cache disabled doesn't interfere with normal operation."""
    settings.llm_cache_enabled = False
    
    with patch("app.services.openai_client.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"test": "response"}'
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        client = OpenAIClient(settings)
        messages = [{"role": "user", "content": [{"type": "text", "text": "test"}]}]
        
        # Should work normally
        result = client.call_vision(messages, request_id="test-123")
        assert result == '{"test": "response"}'
        
        # Second call should still call OpenAI (no cache)
        client.call_vision(messages, request_id="test-456")
        assert mock_client.chat.completions.create.call_count == 2

