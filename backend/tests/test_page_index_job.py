"""Tests for page indexing background job (Batch 3)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_get_page_index_job_status_endpoint_not_started(client, tmp_path, monkeypatch):
    """Test status endpoint returns 'not_started' when no progress file exists."""
    project_id = "test_status_001"
    
    # Create project directory but no progress/index files
    output_dir = Path("out") / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        response = client.get(f"/v1/projects/{project_id}/jobs/page-index/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_started"
        assert data["project_id"] == project_id
    finally:
        # Cleanup
        if output_dir.exists():
            import shutil
            shutil.rmtree(output_dir)


def test_get_page_index_job_status_endpoint_running(client, tmp_path):
    """Test status endpoint returns 'running' when progress file shows incomplete."""
    project_id = "test_status_002"
    
    # Create progress file with incomplete status
    output_dir = Path("out") / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_file = output_dir / "page_index_progress.json"
    progress_data = {
        "total_pages": 100,
        "completed_pages": 42,
        "cached_pages": 10,
        "failed_pages": 0,
        "updated_at": "2024-01-01T00:00:00",
    }
    with open(progress_file, "w") as f:
        json.dump(progress_data, f)
    
    try:
        response = client.get(f"/v1/projects/{project_id}/jobs/page-index/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["project_id"] == project_id
        assert data["progress"] is not None
        assert data["progress"]["completed_pages"] == 42
        assert data["progress"]["total_pages"] == 100
    finally:
        # Cleanup
        if output_dir.exists():
            import shutil
            shutil.rmtree(output_dir)


def test_get_page_index_job_status_endpoint_succeeded(client):
    """Test status endpoint returns 'succeeded' when page_index.json exists."""
    project_id = "test_status_003"
    
    # Create page_index.json (completed)
    output_dir = Path("out") / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    index_file = output_dir / "page_index.json"
    index_data = {
        "project_id": project_id,
        "pages": [{"page_number": i, "page_types": ["plan"], "indicators": [], "confidence": 0.9} for i in range(1, 11)],
        "total_pages": 10,
        "indexed_pages": 10,
        "cached_pages": 0,
    }
    with open(index_file, "w") as f:
        json.dump(index_data, f)
    
    try:
        response = client.get(f"/v1/projects/{project_id}/jobs/page-index/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "succeeded"
        assert data["project_id"] == project_id
    finally:
        # Cleanup
        if output_dir.exists():
            import shutil
            shutil.rmtree(output_dir)

