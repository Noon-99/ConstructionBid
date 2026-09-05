"""Tests for contractor proposal PDF endpoints (Phase 9.6)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_project_dir(tmp_path, monkeypatch):
    """Create a mock project directory with contractor_bid.json."""
    project_id = "test-project-123"
    project_dir = tmp_path / "out" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # Create contractor_bid.json
    contractor_bid = {
        "project_id": project_id,
        "bid_mode": "contractor",
        "total_bid": 100000.0,
        "subtotals": {"scope": 80000.0, "permits": 5000.0, "logistics": 15000.0},
        "sections": [
            {
                "section_id": "section-1",
                "title": "Base Scope",
                "division": "04",
                "line_items": [
                    {
                        "item_id": "item-1",
                        "title": "Masonry Repointing",
                        "division": "04",
                        "quantity": 500.0,
                        "unit": "SF",
                        "unit_cost": 15.0,
                        "total_cost": 7500.0,
                        "basis": "From drawings",
                        "notes": None,
                    }
                ],
                "subtotal": 7500.0,
            }
        ],
        "permits_and_inspections": [
            {
                "item_id": "perm-1",
                "title": "Building Permit",
                "division": None,
                "quantity": None,
                "unit": None,
                "unit_cost": None,
                "total_cost": 2500.0,
                "basis": "NYC permit fees",
                "notes": None,
            }
        ],
        "logistics": [
            {
                "item_id": "log-1",
                "title": "Scaffolding",
                "division": None,
                "quantity": 4.0,
                "unit": "week",
                "unit_cost": 1200.0,
                "total_cost": 4800.0,
                "basis": "Contractor profile",
                "notes": None,
            }
        ],
        "exclusions": ["Site work", "Landscaping"],
        "assumptions": ["Access available", "Weather delays not included"],
        "payment_schedule": None,
        "schedule": None,
        "created_at": "2025-01-01T00:00:00Z",
    }

    contractor_bid_file = project_dir / "contractor_bid.json"
    with open(contractor_bid_file, "w") as f:
        json.dump(contractor_bid, f)

    # Monkeypatch Path to use tmp_path
    original_path = Path

    def mock_path(*args):
        if len(args) == 1 and str(args[0]).startswith("out/"):
            # Convert "out/project_id" to tmp_path/out/project_id
            parts = str(args[0]).split("/")
            if len(parts) >= 2 and parts[0] == "out":
                return tmp_path / "/".join(parts)
        return original_path(*args)

    monkeypatch.setattr("app.api.routes.projects.Path", mock_path)

    return project_dir, project_id


def test_generate_contractor_proposal_pdf_missing_contractor_bid(client, tmp_path, monkeypatch):
    """Test that POST /contractor_proposal.pdf returns 409 if contractor_bid.json is missing."""
    project_id = "test-project-456"
    project_dir = tmp_path / "out" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch Path
    original_path = Path

    def mock_path(*args):
        if len(args) == 1 and str(args[0]).startswith("out/"):
            parts = str(args[0]).split("/")
            if len(parts) >= 2 and parts[0] == "out":
                return tmp_path / "/".join(parts)
        return original_path(*args)

    monkeypatch.setattr("app.api.routes.projects.Path", mock_path)

    response = client.post(f"/v1/projects/{project_id}/contractor_proposal.pdf")

    assert response.status_code == 409
    assert "Generate contractor bid first" in response.json()["detail"]


def test_generate_contractor_proposal_pdf_success(client, mock_project_dir, monkeypatch):
    """Test that POST /contractor_proposal.pdf enqueues job when contractor_bid.json exists."""
    project_dir, project_id = mock_project_dir

    # Mock job queue to avoid Redis dependency
    from unittest.mock import MagicMock

    mock_job = MagicMock()
    mock_job.id = "job-123"

    mock_queue = MagicMock()
    mock_queue.enqueue.return_value = mock_job

    mock_job_queue_service = MagicMock()
    mock_job_queue_service.queue = mock_queue

    # Monkeypatch the dependency
    def get_mock_job_queue():
        return mock_job_queue_service

    monkeypatch.setattr("app.api.routes.projects.get_job_queue_service", get_mock_job_queue)

    response = client.post(f"/v1/projects/{project_id}/contractor_proposal.pdf")

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["project_id"] == project_id
    assert data["status"] == "queued"

    # Verify job was enqueued
    assert mock_queue.enqueue.called


def test_download_contractor_proposal_pdf_not_found(client, tmp_path, monkeypatch):
    """Test that GET /contractor_proposal.pdf returns 404 if PDF doesn't exist."""
    project_id = "test-project-789"
    project_dir = tmp_path / "out" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch Path
    original_path = Path

    def mock_path(*args):
        if len(args) == 1 and str(args[0]).startswith("out/"):
            parts = str(args[0]).split("/")
            if len(parts) >= 2 and parts[0] == "out":
                return tmp_path / "/".join(parts)
        return original_path(*args)

    monkeypatch.setattr("app.api.routes.projects.Path", mock_path)

    response = client.get(f"/v1/projects/{project_id}/contractor_proposal.pdf")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_contractor_proposal_pdf_in_artifacts_allowlist():
    """Test that contractor_proposal_pdf is in ALLOWED_ARTIFACTS."""
    from app.api.routes.projects import ALLOWED_ARTIFACTS

    assert "contractor_proposal_pdf" in ALLOWED_ARTIFACTS






