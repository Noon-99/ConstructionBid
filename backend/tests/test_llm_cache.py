"""Unit tests for LLM cache (SQLite-backed)."""

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.llm_cache import CachedResponse, LLMCache, get_llm_cache


@pytest.fixture
def temp_cache_path() -> Path:
    """Create a temporary cache database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_cache.sqlite"


@pytest.fixture
def cache(temp_cache_path: Path) -> LLMCache:
    """Create an LLM cache instance for testing."""
    return LLMCache(cache_path=temp_cache_path, enabled=True)


@pytest.fixture
def disabled_cache(temp_cache_path: Path) -> LLMCache:
    """Create a disabled LLM cache instance for testing."""
    return LLMCache(cache_path=temp_cache_path, enabled=False)


def test_cache_key_computation(cache: LLMCache) -> None:
    """Test cache key computation includes all required components."""
    model = "gpt-4o-mini"
    detail = "high"
    prompt_text = "Extract rooms from this image"
    image_bytes = b"fake_image_bytes_12345"
    
    key1 = cache.compute_cache_key(model, detail, prompt_text, image_bytes)
    key2 = cache.compute_cache_key(model, detail, prompt_text, image_bytes)
    
    # Same inputs should produce same key
    assert key1 == key2
    assert len(key1) == 64  # SHA256 hex digest length


def test_cache_key_different_prompts(cache: LLMCache) -> None:
    """Test that different prompts produce different cache keys."""
    model = "gpt-4o-mini"
    detail = "high"
    image_bytes = b"fake_image_bytes_12345"
    
    key1 = cache.compute_cache_key(model, detail, "Prompt 1", image_bytes)
    key2 = cache.compute_cache_key(model, detail, "Prompt 2", image_bytes)
    
    assert key1 != key2


def test_cache_key_different_images(cache: LLMCache) -> None:
    """Test that different images produce different cache keys."""
    model = "gpt-4o-mini"
    detail = "high"
    prompt_text = "Extract rooms"
    
    key1 = cache.compute_cache_key(model, detail, prompt_text, b"image1")
    key2 = cache.compute_cache_key(model, detail, prompt_text, b"image2")
    
    assert key1 != key2


def test_cache_key_schema_version_invalidation(cache: LLMCache) -> None:
    """Test that schema version change invalidates cache."""
    model = "gpt-4o-mini"
    detail = "high"
    prompt_text = "Extract rooms"
    image_bytes = b"image"
    
    key_v1 = cache.compute_cache_key(model, detail, prompt_text, image_bytes, schema_version="v1")
    key_v2 = cache.compute_cache_key(model, detail, prompt_text, image_bytes, schema_version="v2")
    
    # Different schema versions should produce different keys
    assert key_v1 != key_v2


def test_cache_get_miss(cache: LLMCache) -> None:
    """Test cache get returns None on miss."""
    cache_key = "nonexistent_key_12345"
    result = cache.get(cache_key)
    assert result is None


def test_cache_set_and_get(cache: LLMCache) -> None:
    """Test setting and getting from cache."""
    cache_key = cache.compute_cache_key(
        model="gpt-4o-mini",
        detail="high",
        prompt_text="Test prompt",
        image_bytes=b"test_image",
    )
    
    response_json = '{"result": "test"}'
    token_usage_json = '{"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}'
    prompt_hash = hashlib.sha256("Test prompt".encode("utf-8")).hexdigest()
    image_hash = hashlib.sha256(b"test_image").hexdigest()
    
    # Set cache
    cache.set(
        cache_key=cache_key,
        model="gpt-4o-mini",
        detail="high",
        prompt_hash=prompt_hash,
        image_hash=image_hash,
        response_json=response_json,
        token_usage_json=token_usage_json,
    )
    
    # Get from cache
    cached = cache.get(cache_key)
    
    assert cached is not None
    assert cached.response_json == response_json
    assert cached.token_usage_json == token_usage_json
    assert cached.created_at is not None


def test_cache_disabled_get(disabled_cache: LLMCache) -> None:
    """Test that disabled cache always returns None on get."""
    cache_key = "any_key"
    result = disabled_cache.get(cache_key)
    assert result is None


def test_cache_disabled_set(disabled_cache: LLMCache) -> None:
    """Test that disabled cache doesn't store values."""
    cache_key = "any_key"
    
    disabled_cache.set(
        cache_key=cache_key,
        model="gpt-4o-mini",
        detail="high",
        prompt_hash="hash1",
        image_hash="hash2",
        response_json='{"test": "data"}',
    )
    
    # Should not be retrievable
    result = disabled_cache.get(cache_key)
    assert result is None


def test_cache_same_input_returns_cached_response(cache: LLMCache) -> None:
    """Test that same input returns cached response (simulating OpenAI call avoidance)."""
    model = "gpt-4o-mini"
    detail = "high"
    prompt_text = "Extract data"
    image_bytes = b"image_data"
    
    cache_key = cache.compute_cache_key(model, detail, prompt_text, image_bytes)
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    
    # Store response
    cache.set(
        cache_key=cache_key,
        model=model,
        detail=detail,
        prompt_hash=prompt_hash,
        image_hash=image_hash,
        response_json='{"cached": "response"}',
        token_usage_json='{"total_tokens": 100}',
    )
    
    # Get cached response (should not call OpenAI)
    cached = cache.get(cache_key)
    assert cached is not None
    assert cached.response_json == '{"cached": "response"}'


def test_cache_clear(cache: LLMCache) -> None:
    """Test clearing the cache."""
    cache_key = cache.compute_cache_key(
        model="gpt-4o-mini",
        detail="high",
        prompt_text="Test",
        image_bytes=b"image",
    )
    prompt_hash = hashlib.sha256("Test".encode("utf-8")).hexdigest()
    image_hash = hashlib.sha256(b"image").hexdigest()
    
    # Set and verify
    cache.set(
        cache_key=cache_key,
        model="gpt-4o-mini",
        detail="high",
        prompt_hash=prompt_hash,
        image_hash=image_hash,
        response_json='{"test": "data"}',
    )
    assert cache.get(cache_key) is not None
    
    # Clear and verify
    cache.clear()
    assert cache.get(cache_key) is None


def test_singleton_cache(temp_cache_path: Path) -> None:
    """Test that get_llm_cache returns a singleton instance."""
    cache1 = get_llm_cache(cache_path=temp_cache_path, enabled=True)
    cache2 = get_llm_cache(cache_path=temp_cache_path, enabled=True)
    
    # Should be the same instance
    assert cache1 is cache2


def test_cache_handles_corruption_gracefully(cache: LLMCache) -> None:
    """Test that cache handles database corruption gracefully."""
    # First, store a valid entry
    cache_key = cache.compute_cache_key(
        model="gpt-4o-mini",
        detail="high",
        prompt_text="Test",
        image_bytes=b"image",
    )
    prompt_hash = hashlib.sha256("Test".encode("utf-8")).hexdigest()
    image_hash = hashlib.sha256(b"image").hexdigest()
    
    cache.set(
        cache_key=cache_key,
        model="gpt-4o-mini",
        detail="high",
        prompt_hash=prompt_hash,
        image_hash=image_hash,
        response_json='{"test": "data"}',
    )
    
    # Verify it works before corruption
    cached = cache.get(cache_key)
    assert cached is not None
    
    # Corrupt the database file
    cache.cache_path.write_bytes(b"corrupted sqlite data")
    
    # Should handle gracefully (treat as miss)
    result = cache.get("any_key")
    assert result is None
    
    # Should also fail gracefully on write (logs warning but doesn't crash)
    cache.set(
        cache_key=cache_key,
        model="gpt-4o-mini",
        detail="high",
        prompt_hash=prompt_hash,
        image_hash=image_hash,
        response_json='{"test": "data2"}',
    )
    
    # Get should still return None (corruption persists, gracefully handled)
    cached_after_corruption = cache.get(cache_key)
    assert cached_after_corruption is None

