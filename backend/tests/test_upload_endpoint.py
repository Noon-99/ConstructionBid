"""Tests for upload endpoint."""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_upload_pdf_success(client, tmp_path, monkeypatch):
    """Test successful PDF upload."""
    # Mock storage root
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    
    # Create a fake PDF content
    pdf_content = b"%PDF-1.4\nfake pdf content"
    
    # Upload
    response = client.post(
        "/v1/projects/upload",
        files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "project_id" in data
    assert data["status"] == "uploaded"
    
    # Verify PDF was saved
    project_id = data["project_id"]
    pdf_path = tmp_path / project_id / "source.pdf"
    assert pdf_path.exists()
    assert pdf_path.read_bytes() == pdf_content


def test_upload_non_pdf_fails(client):
    """Test that non-PDF files are rejected."""
    response = client.post(
        "/v1/projects/upload",
        files={"file": ("test.txt", io.BytesIO(b"not a pdf"), "text/plain")},
    )
    
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_upload_empty_file_fails(client):
    """Test that empty files are rejected."""
    response = client.post(
        "/v1/projects/upload",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_run_without_upload_fails(client, tmp_path, monkeypatch):
    """Test that running pipeline without upload fails."""
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    
    fake_project_id = "test_project_123"
    response = client.post(f"/v1/projects/{fake_project_id}/run")
    
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()
    assert "upload" in response.json()["detail"].lower()






