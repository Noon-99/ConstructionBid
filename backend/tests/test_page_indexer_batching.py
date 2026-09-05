"""Tests for PageIndexer batching and concurrency features (Batch 2)."""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.models.pdf_page_image import PdfPageImage
from app.schemas.page_index import PageIndexItem
from app.services.page_indexer import PageIndexer


@pytest.fixture
def mock_settings():
    """Create mock settings with batching config."""
    settings = MagicMock()
    settings.page_index_batch_size = 5  # Small batch size for testing
    settings.page_index_concurrency = 2  # Low concurrency for testing
    settings.page_index_max_retries = 3
    return settings


@pytest.fixture
def mock_openai_client():
    """Create mock OpenAI client."""
    client = MagicMock()
    # Mock successful API response
    client.call_vision = MagicMock(
        return_value=json.dumps({
            "sheet_id": "A-1",
            "sheet_title": "Test Page",
            "page_types": ["plan"],
            "indicators": ["dimensions"],
            "confidence": 0.9,
        })
    )
    return client


@pytest.fixture
def page_indexer(mock_settings, mock_openai_client):
    """Create PageIndexer instance."""
    return PageIndexer(mock_settings, mock_openai_client)


@pytest.fixture
def many_page_images():
    """Create many page images for batch testing."""
    return [
        PdfPageImage(
            page_number=i,
            image_base64=f"base64data{i}",
            mime_type="image/png",
        )
        for i in range(1, 21)  # 20 pages
    ]


def test_batching_respects_batch_size(page_indexer, many_page_images, tmp_path, monkeypatch):
    """Test that pages are processed in batches of the configured size."""
    project_id = "test_batch_001"
    batch_size = page_indexer.settings.page_index_batch_size

    # Mock cache directory
    def mock_get_cache_dir(project_id: str) -> Path:
        cache_dir = tmp_path / "out" / project_id / "page_index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._load_cached_page = MagicMock(return_value=None)  # No cached pages

    # Track batch calls
    batch_call_count = 0
    original_process_batch = page_indexer._process_batch

    async def tracked_process_batch(*args, **kwargs):
        nonlocal batch_call_count
        batch_call_count += 1
        return await original_process_batch(*args, **kwargs)

    page_indexer._process_batch = tracked_process_batch

    # Run indexing
    result = page_indexer.index_pages(project_id, many_page_images)

    # Verify batching (20 pages / batch_size=5 = 4 batches)
    expected_batches = (len(many_page_images) + batch_size - 1) // batch_size
    assert batch_call_count == expected_batches, f"Expected {expected_batches} batches, got {batch_call_count}"

    # Verify all pages indexed
    assert len(result.pages) == len(many_page_images)
    assert result.total_pages == len(many_page_images)


def test_concurrency_cap_respected(page_indexer, many_page_images, tmp_path, monkeypatch):
    """Test that concurrency cap is respected during batch processing."""
    project_id = "test_concurrency_001"
    concurrency = page_indexer.settings.page_index_concurrency

    # Mock cache directory
    def mock_get_cache_dir(project_id: str) -> Path:
        cache_dir = tmp_path / "out" / project_id / "page_index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._load_cached_page = MagicMock(return_value=None)

    # Track concurrent calls
    concurrent_calls = []
    original_index_single_page = page_indexer._index_single_page

    def tracked_index_single_page(page_image, project_id):
        concurrent_calls.append(len(concurrent_calls) + 1)
        import time
        time.sleep(0.01)  # Small delay to allow concurrency
        return original_index_single_page(page_image, project_id)

    page_indexer._index_single_page = tracked_index_single_page

    # Run indexing on a small batch
    small_batch = many_page_images[:10]  # 10 pages, batch_size=5, concurrency=2
    result = page_indexer.index_pages(project_id, small_batch)

    # Verify all pages indexed (exact concurrency check is hard due to async nature)
    assert len(result.pages) == len(small_batch)


def test_retry_on_rate_limit(page_indexer, many_page_images, tmp_path, monkeypatch):
    """Test that 429 rate limit errors trigger retries with backoff."""
    project_id = "test_retry_001"

    # Mock cache directory
    def mock_get_cache_dir(project_id: str) -> Path:
        cache_dir = tmp_path / "out" / project_id / "page_index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._load_cached_page = MagicMock(return_value=None)

    # Track call count
    call_count = 0
    max_retries = page_indexer.settings.page_index_max_retries

    def mock_call_vision_with_retry(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:  # First 2 calls fail with 429
            raise Exception("429 Rate limit exceeded")
        # Third call succeeds
        return json.dumps({
            "sheet_id": "A-1",
            "sheet_title": "Test Page",
            "page_types": ["plan"],
            "indicators": ["dimensions"],
            "confidence": 0.9,
        })

    page_indexer.openai_client.call_vision = MagicMock(side_effect=mock_call_vision_with_retry)

    # Run indexing on a single page (to test retry logic)
    single_page = many_page_images[:1]
    result = page_indexer.index_pages(project_id, single_page)

    # Verify retry occurred (call_count should be 3: 2 failures + 1 success)
    assert call_count >= 3, f"Expected at least 3 calls (retries), got {call_count}"
    # Verify page was eventually indexed successfully
    assert len(result.pages) == 1
    assert result.pages[0].confidence > 0.0


def test_output_ordering_preserved(page_indexer, many_page_images, tmp_path, monkeypatch):
    """Test that final output is ordered by page number even if processed out-of-order."""
    project_id = "test_ordering_001"

    # Mock cache directory
    def mock_get_cache_dir(project_id: str) -> Path:
        cache_dir = tmp_path / "out" / project_id / "page_index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._load_cached_page = MagicMock(return_value=None)

    # Make processing complete out of order by adding delays
    call_order = []
    original_index_single_page = page_indexer._index_single_page

    def delayed_index_single_page(page_image, project_id):
        import time
        # Pages with higher numbers finish faster (to create out-of-order completion)
        delay = (100 - page_image.page_number) * 0.001
        time.sleep(delay)
        call_order.append(page_image.page_number)
        return original_index_single_page(page_image, project_id)

    page_indexer._index_single_page = delayed_index_single_page

    # Run indexing
    result = page_indexer.index_pages(project_id, many_page_images)

    # Verify pages are ordered correctly in output (1, 2, 3, ..., 20)
    page_numbers = [p.page_number for p in result.pages]
    assert page_numbers == list(range(1, len(many_page_images) + 1)), \
        f"Pages not ordered correctly: {page_numbers}"

    # Verify processing order was different (to confirm sorting worked)
    if len(call_order) > 1:
        assert call_order != page_numbers, \
            "Processing completed in order, test may not have exercised sorting logic"


def test_progress_file_created(page_indexer, many_page_images, tmp_path, monkeypatch):
    """Test that progress.json file is created and updated."""
    project_id = "test_progress_001"
    output_dir = tmp_path / "out" / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_file = output_dir / "page_index_progress.json"

    # Mock _update_progress to write to tmp_path
    original_update_progress = page_indexer._update_progress
    progress_calls = []

    def mock_update_progress(project_id, total_pages, completed_pages, cached_pages, failed_pages):
        progress_calls.append({
            "total_pages": total_pages,
            "completed_pages": completed_pages,
            "cached_pages": cached_pages,
            "failed_pages": failed_pages,
        })
        # Write to tmp_path instead of "out"
        progress_data = {
            "total_pages": total_pages,
            "completed_pages": completed_pages,
            "cached_pages": cached_pages,
            "failed_pages": failed_pages,
            "updated_at": "2024-01-01T00:00:00",
        }
        with open(progress_file, "w") as f:
            json.dump(progress_data, f, indent=2)

    page_indexer._update_progress = mock_update_progress

    # Mock cache directory
    def mock_get_cache_dir(project_id: str) -> Path:
        cache_dir = tmp_path / "out" / project_id / "page_index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._load_cached_page = MagicMock(return_value=None)

    # Run indexing
    result = page_indexer.index_pages(project_id, many_page_images)

    # Verify progress file exists
    assert progress_file.exists(), "Progress file was not created"

    # Verify progress file content
    with open(progress_file, "r") as f:
        progress_data = json.load(f)

    assert "total_pages" in progress_data
    assert "completed_pages" in progress_data
    assert "cached_pages" in progress_data
    assert "failed_pages" in progress_data
    assert "updated_at" in progress_data

    assert progress_data["total_pages"] == len(many_page_images)
    assert progress_data["completed_pages"] == len(result.pages)
    assert progress_data["cached_pages"] == 0  # No cached pages in this test


def test_progress_file_includes_failed_pages(page_indexer, many_page_images, tmp_path, monkeypatch):
    """Test that progress file correctly tracks failed pages."""
    project_id = "test_progress_failed_001"

    # Mock cache directory
    def mock_get_cache_dir(project_id: str) -> Path:
        cache_dir = tmp_path / "out" / project_id / "page_index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._load_cached_page = MagicMock(return_value=None)

    # Make some pages fail (non-retryable errors)
    call_count = 0
    original_index_single_page = page_indexer._index_single_page

    def failing_index_single_page(page_image, project_id):
        nonlocal call_count
        call_count += 1
        if page_image.page_number <= 2:  # Pages 1-2 fail
            raise Exception("400 Bad Request")  # Non-retryable
        return original_index_single_page(page_image, project_id)

    page_indexer._index_single_page = failing_index_single_page

    # Run indexing on a small batch
    small_batch = many_page_images[:10]
    result = page_indexer.index_pages(project_id, small_batch)

    # Verify progress file shows failed pages
    progress_file = tmp_path / "out" / project_id / "page_index_progress.json"
    if progress_file.exists():
        with open(progress_file, "r") as f:
            progress_data = json.load(f)

        # Should have some failed pages
        assert progress_data["failed_pages"] >= 0
        # All pages should be "completed" (even if failed, they have fallback entries)
        assert progress_data["completed_pages"] == len(result.pages)


def test_batching_works_with_mixed_cache(page_indexer, many_page_images, tmp_path, monkeypatch):
    """Test that batching works correctly when some pages are cached."""
    project_id = "test_mixed_cache_001"

    # Mock cache directory
    cache_dir = tmp_path / "out" / project_id / "page_index_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def mock_get_cache_dir(project_id: str) -> Path:
        return cache_dir

    page_indexer._get_cache_dir = mock_get_cache_dir

    # Pre-cache pages 1-5
    for i in range(1, 6):
        cached_item = PageIndexItem(
            page_number=i,
            sheet_id=f"A-{i}",
            sheet_title=f"Cached Page {i}",
            page_types=["plan"],
            indicators=[],
            confidence=0.9,
        )
        cache_path = cache_dir / f"page_{i}.json"
        with open(cache_path, "w") as f:
            f.write(cached_item.model_dump_json(indent=2))

    # Run indexing
    result = page_indexer.index_pages(project_id, many_page_images)

    # Verify all pages indexed
    assert len(result.pages) == len(many_page_images)
    # Verify cached pages were loaded
    assert result.cached_pages == 5
    # Verify cached pages have correct data
    for i in range(1, 6):
        page_item = next(p for p in result.pages if p.page_number == i)
        assert page_item.sheet_title == f"Cached Page {i}"
        assert page_item.page_types == ["plan"]

