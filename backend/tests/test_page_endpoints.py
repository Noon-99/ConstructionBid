"""Tests for page image endpoints (Phase 8.6A)."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import shutil

from app.main import app
from app.core.config import Settings


@pytest.fixture
def client():
    """Test client."""
    return TestClient(app)


@pytest.fixture
def test_project_id():
    """Test project ID."""
    return "test_pages_123"


@pytest.fixture
def test_pages_dir(test_project_id, tmp_path, monkeypatch):
    """Create test pages directory with sample images."""
    # Mock storage root
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    
    # Create project pages directory
    pages_dir = storage_root / test_project_id / "pages"
    pages_dir.mkdir(parents=True)
    
    # Create dummy PNG files (we'll use small valid PNGs or skip actual image validation)
    # For testing, we can create empty files or use a test image
    for page_num in range(1, 4):  # 3 pages
        page_file = pages_dir / f"page_{page_num}.png"
        # Create a minimal valid PNG (1x1 transparent pixel)
        # PNG header: 89 50 4E 47 0D 0A 1A 0A
        minimal_png = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D,  # IHDR chunk length
            0x49, 0x48, 0x44, 0x52,  # IHDR
            0x00, 0x00, 0x00, 0x01,  # width = 1
            0x00, 0x00, 0x00, 0x01,  # height = 1
            0x08, 0x06, 0x00, 0x00, 0x00,  # bit depth, color type, etc.
            0x1F, 0x15, 0xC4, 0x89,  # CRC
            0x00, 0x00, 0x00, 0x0A,  # IDAT chunk length
            0x49, 0x44, 0x41, 0x54,  # IDAT
            0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00, 0x05, 0x00, 0x01,  # compressed data
            0x0D, 0x0A, 0x2D, 0xB4,  # CRC
            0x00, 0x00, 0x00, 0x00,  # IEND chunk length
            0x49, 0x45, 0x4E, 0x44,  # IEND
            0xAE, 0x42, 0x60, 0x82,  # CRC
        ])
        page_file.write_bytes(minimal_png)
    
    # Patch settings to use test storage root
    def get_test_settings():
        settings = Settings()
        settings.storage_root = storage_root
        return settings
    
    monkeypatch.setattr("app.api.routes.pages.get_settings", get_test_settings)
    monkeypatch.setattr("app.services.storage.get_settings", get_test_settings)
    
    return pages_dir


def test_pages_list_ok(client, test_project_id, test_pages_dir):
    """Test listing pages for existing project."""
    response = client.get(f"/v1/projects/{test_project_id}/pages")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["project_id"] == test_project_id
    assert data["page_count"] == 3
    assert len(data["pages"]) == 3
    
    # Check page structure
    for page in data["pages"]:
        assert "page_number" in page
        assert "url" in page
        assert page["page_number"] >= 1
        assert f"/v1/projects/{test_project_id}/pages/{page['page_number']}.png" in page["url"]
    
    # Check pages are sorted
    page_numbers = [p["page_number"] for p in data["pages"]]
    assert page_numbers == sorted(page_numbers)


def test_pages_list_404_project(client):
    """Test listing pages for non-existent project."""
    response = client.get("/v1/projects/nonexistent_project/pages")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_page_png_ok(client, test_project_id, test_pages_dir):
    """Test getting a valid page image."""
    response = client.get(f"/v1/projects/{test_project_id}/pages/1.png")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0  # Should have PNG data


def test_page_png_out_of_range_400(client, test_project_id, test_pages_dir):
    """Test getting page image with out-of-range page number."""
    response = client.get(f"/v1/projects/{test_project_id}/pages/999.png")
    
    assert response.status_code == 400
    assert "out of range" in response.json()["detail"].lower()


def test_page_png_non_int_400(client, test_project_id):
    """Test getting page image with invalid page number."""
    # FastAPI will handle this as 422 (validation error) or 404
    response = client.get(f"/v1/projects/{test_project_id}/pages/invalid.png")
    
    # Should be 422 (validation error) or 404
    assert response.status_code in [400, 404, 422]


def test_page_png_negative_400(client, test_project_id, test_pages_dir):
    """Test getting page image with negative page number."""
    response = client.get(f"/v1/projects/{test_project_id}/pages/0.png")
    
    assert response.status_code == 400
    assert "must be >= 1" in response.json()["detail"].lower()


def test_page_png_404_missing_file(client, test_project_id, tmp_path, monkeypatch):
    """Test getting page image when file doesn't exist."""
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    pages_dir = storage_root / test_project_id / "pages"
    pages_dir.mkdir(parents=True)
    # Don't create any page files
    
    def get_test_settings():
        settings = Settings()
        settings.storage_root = storage_root
        return settings
    
    monkeypatch.setattr("app.api.routes.pages.get_settings", get_test_settings)
    monkeypatch.setattr("app.services.storage.get_settings", get_test_settings)
    
    response = client.get(f"/v1/projects/{test_project_id}/pages/1.png")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()






