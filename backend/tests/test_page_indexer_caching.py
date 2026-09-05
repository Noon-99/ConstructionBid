"""Tests for PageIndexer caching and resumability features."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.pdf_page_image import PdfPageImage
from app.schemas.page_index import PageIndex, PageIndexItem
from app.services.page_indexer import PageIndexer


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
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
def sample_page_images():
    """Create sample page images for testing."""
    return [
        PdfPageImage(
            page_number=1,
            image_base64="base64data1",
            mime_type="image/png",
        ),
        PdfPageImage(
            page_number=2,
            image_base64="base64data2",
            mime_type="image/png",
        ),
        PdfPageImage(
            page_number=3,
            image_base64="base64data3",
            mime_type="image/png",
        ),
    ]


def test_first_run_indexes_pages_and_writes_cache(
    page_indexer, sample_page_images, tmp_path, monkeypatch
):
    """Test that first run indexes pages and writes per-page cache."""
    project_id = "test_project_001"

    # Mock the output directory
    def mock_get_cache_dir(project_id: str) -> Path:
        cache_dir = tmp_path / "out" / project_id / "page_index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    page_indexer._get_cache_dir = mock_get_cache_dir

    # Run indexing
    result = page_indexer.index_pages(project_id, sample_page_images)

    # Verify result
    assert isinstance(result, PageIndex)
    assert result.project_id == project_id
    assert len(result.pages) == 3
    assert result.total_pages == 3
    assert result.indexed_pages == 3
    assert result.cached_pages == 0  # First run, no cache
    assert result.started_at is not None
    assert result.finished_at is not None

    # Verify pages are ordered correctly
    for i, page_item in enumerate(result.pages, start=1):
        assert page_item.page_number == i
        assert page_item.page_types == ["plan"]
        assert page_item.indicators == ["dimensions"]

    # Verify cache files were created
    cache_dir = tmp_path / "out" / project_id / "page_index_cache"
    assert cache_dir.exists()
    assert (cache_dir / "page_1.json").exists()
    assert (cache_dir / "page_2.json").exists()
    assert (cache_dir / "page_3.json").exists()

    # Verify cache file contents
    with open(cache_dir / "page_1.json", "r") as f:
        cached_data = json.load(f)
        assert cached_data["page_number"] == 1
        assert cached_data["page_types"] == ["plan"]

    # Verify API was called for each page
    assert page_indexer.openai_client.call_vision.call_count == 3


def test_second_run_reuses_cache_and_skips_api_calls(
    page_indexer, sample_page_images, tmp_path, monkeypatch
):
    """Test that second run reuses cache and does not call API."""
    project_id = "test_project_002"

    # Mock the output directory
    cache_dir = tmp_path / "out" / project_id / "page_index_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def mock_get_cache_dir(project_id: str) -> Path:
        return cache_dir

    def mock_get_cached_page_path(project_id: str, page_number: int) -> Path:
        return cache_dir / f"page_{page_number}.json"

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._get_cached_page_path = mock_get_cached_page_path

    # Create cached entries for pages 1 and 2
    cached_item_1 = PageIndexItem(
        page_number=1,
        sheet_id="A-1",
        sheet_title="Cached Page 1",
        page_types=["elevation"],
        indicators=["lintel"],
        confidence=0.85,
    )
    cached_item_2 = PageIndexItem(
        page_number=2,
        sheet_id="A-2",
        sheet_title="Cached Page 2",
        page_types=["detail"],
        indicators=["flashing"],
        confidence=0.90,
    )

    with open(cache_dir / "page_1.json", "w") as f:
        f.write(cached_item_1.model_dump_json(indent=2))
    with open(cache_dir / "page_2.json", "w") as f:
        f.write(cached_item_2.model_dump_json(indent=2))

    # Reset call count
    page_indexer.openai_client.call_vision.reset_mock()

    # Run indexing (should load pages 1 and 2 from cache, index page 3)
    result = page_indexer.index_pages(project_id, sample_page_images)

    # Verify result
    assert isinstance(result, PageIndex)
    assert len(result.pages) == 3
    assert result.total_pages == 3
    assert result.indexed_pages == 3
    assert result.cached_pages == 2  # Pages 1 and 2 from cache

    # Verify cached pages are loaded correctly
    assert result.pages[0].page_number == 1
    assert result.pages[0].sheet_title == "Cached Page 1"
    assert result.pages[0].page_types == ["elevation"]
    assert result.pages[1].page_number == 2
    assert result.pages[1].sheet_title == "Cached Page 2"
    assert result.pages[1].page_types == ["detail"]

    # Verify API was only called once (for page 3)
    assert page_indexer.openai_client.call_vision.call_count == 1

    # Verify page 3 cache was created
    assert (cache_dir / "page_3.json").exists()


def test_force_reindex_bypasses_cache(
    page_indexer, sample_page_images, tmp_path, monkeypatch
):
    """Test that force_reindex=True bypasses cache and re-indexes all pages."""
    project_id = "test_project_003"

    # Mock the output directory
    cache_dir = tmp_path / "out" / project_id / "page_index_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def mock_get_cache_dir(project_id: str) -> Path:
        return cache_dir

    def mock_get_cached_page_path(project_id: str, page_number: int) -> Path:
        return cache_dir / f"page_{page_number}.json"

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._get_cached_page_path = mock_get_cached_page_path

    # Create cached entries
    cached_item = PageIndexItem(
        page_number=1,
        sheet_id="OLD",
        sheet_title="Old Cached",
        page_types=["notes"],  # Valid page type
        indicators=[],
        confidence=0.5,
    )
    with open(cache_dir / "page_1.json", "w") as f:
        f.write(cached_item.model_dump_json(indent=2))

    # Reset call count
    page_indexer.openai_client.call_vision.reset_mock()

    # Run indexing with force_reindex=True
    result = page_indexer.index_pages(
        project_id, sample_page_images, force_reindex=True
    )

    # Verify result
    assert isinstance(result, PageIndex)
    assert len(result.pages) == 3
    assert result.cached_pages == 0  # All re-indexed, no cache used

    # Verify all pages were re-indexed (API called 3 times)
    assert page_indexer.openai_client.call_vision.call_count == 3

    # Verify page 1 was updated in cache (not using old cached value)
    with open(cache_dir / "page_1.json", "r") as f:
        updated_data = json.load(f)
        assert updated_data["sheet_title"] == "Test Page"  # New value (not "Old Cached")
        assert updated_data["page_types"] == ["plan"]  # New value (not ["notes"])


def test_partial_cache_resume_after_interruption(
    page_indexer, sample_page_images, tmp_path, monkeypatch
):
    """Test that indexing can resume after interruption using partial cache."""
    project_id = "test_project_004"

    # Mock the output directory
    cache_dir = tmp_path / "out" / project_id / "page_index_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def mock_get_cache_dir(project_id: str) -> Path:
        return cache_dir

    def mock_get_cached_page_path(project_id: str, page_number: int) -> Path:
        return cache_dir / f"page_{page_number}.json"

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._get_cached_page_path = mock_get_cached_page_path

    # Simulate partial indexing (only page 1 was indexed before interruption)
    cached_item_1 = PageIndexItem(
        page_number=1,
        sheet_id="A-1",
        sheet_title="Resumed Page 1",
        page_types=["plan"],
        indicators=["dimensions"],
        confidence=0.9,
    )
    with open(cache_dir / "page_1.json", "w") as f:
        f.write(cached_item_1.model_dump_json(indent=2))

    # Reset call count
    page_indexer.openai_client.call_vision.reset_mock()

    # Resume indexing (should load page 1, index pages 2 and 3)
    result = page_indexer.index_pages(project_id, sample_page_images)

    # Verify result
    assert isinstance(result, PageIndex)
    assert len(result.pages) == 3
    assert result.total_pages == 3
    assert result.cached_pages == 1  # Only page 1 from cache
    assert result.indexed_pages == 3  # All pages indexed

    # Verify page 1 is from cache
    assert result.pages[0].page_number == 1
    assert result.pages[0].sheet_title == "Resumed Page 1"

    # Verify API was only called for pages 2 and 3
    assert page_indexer.openai_client.call_vision.call_count == 2

    # Verify all pages are in cache now
    assert (cache_dir / "page_1.json").exists()
    assert (cache_dir / "page_2.json").exists()
    assert (cache_dir / "page_3.json").exists()


def test_cache_handles_corrupted_cache_files(
    page_indexer, sample_page_images, tmp_path, monkeypatch
):
    """Test that corrupted cache files are handled gracefully."""
    project_id = "test_project_005"

    # Mock the output directory
    cache_dir = tmp_path / "out" / project_id / "page_index_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def mock_get_cache_dir(project_id: str) -> Path:
        return cache_dir

    def mock_get_cached_page_path(project_id: str, page_number: int) -> Path:
        return cache_dir / f"page_{page_number}.json"

    page_indexer._get_cache_dir = mock_get_cache_dir
    page_indexer._get_cached_page_path = mock_get_cached_page_path

    # Create corrupted cache file
    with open(cache_dir / "page_1.json", "w") as f:
        f.write("invalid json content {")

    # Reset call count
    page_indexer.openai_client.call_vision.reset_mock()

    # Run indexing (should skip corrupted cache and re-index page 1)
    result = page_indexer.index_pages(project_id, sample_page_images)

    # Verify result
    assert isinstance(result, PageIndex)
    assert len(result.pages) == 3
    # Corrupted cache should be ignored, so page 1 is re-indexed
    assert result.cached_pages == 0

    # Verify API was called for all pages (including page 1 due to corrupted cache)
    assert page_indexer.openai_client.call_vision.call_count == 3

    # Verify page 1 cache was fixed/overwritten
    assert (cache_dir / "page_1.json").exists()
    with open(cache_dir / "page_1.json", "r") as f:
        data = json.load(f)
        assert data["page_number"] == 1


def test_output_remains_compatible_with_existing_stages(
    page_indexer, sample_page_images, tmp_path, monkeypatch
):
    """Test that output format remains compatible with existing pipeline stages."""
    project_id = "test_project_006"

    # Mock the output directory
    def mock_get_cache_dir(project_id: str) -> Path:
        cache_dir = tmp_path / "out" / project_id / "page_index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    page_indexer._get_cache_dir = mock_get_cache_dir

    # Run indexing
    result = page_indexer.index_pages(project_id, sample_page_images)

    # Verify required fields exist (for backward compatibility)
    assert hasattr(result, "project_id")
    assert hasattr(result, "pages")
    assert hasattr(result, "created_at")

    # Verify pages list is non-empty and ordered
    assert len(result.pages) > 0
    for i, page_item in enumerate(result.pages, start=1):
        assert page_item.page_number == i

    # Verify PageIndexItem structure (what downstream stages expect)
    for page_item in result.pages:
        assert hasattr(page_item, "page_number")
        assert hasattr(page_item, "page_types")
        assert hasattr(page_item, "indicators")
        assert hasattr(page_item, "confidence")

    # Verify it can be serialized to JSON (what pipeline expects)
    json_str = result.model_dump_json(indent=2)
    assert json_str
    parsed = json.loads(json_str)
    assert "pages" in parsed
    assert "project_id" in parsed

