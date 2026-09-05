"""Tests for artifact endpoints (Phase 6.1)."""

import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app


def test_artifact_name_allowlist() -> None:
    """Test that only allowed artifact names are accepted."""
    client = TestClient(app)
    
    # Try to access a disallowed artifact name
    response = client.get("/v1/projects/test-project/artifacts/invalid_artifact")
    
    assert response.status_code == 400
    assert "Unknown artifact name" in response.json()["detail"]
    assert "invalid_artifact" in response.json()["detail"]


def test_list_artifacts_includes_trade_assemblies(tmp_path) -> None:
    """Endpoint should list trade_assemblies when artifact file exists."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "trade_assemblies.json").write_text('{"project_id": "test", "assemblies": []}')

    import app.api.routes.projects as projects_module

    projects_module_get_output_dir = getattr(projects_module, "get_output_dir")
    projects_module.ALLOWED_ARTIFACTS.add("trade_assemblies")
    projects_module_get_output_dir_orig = projects_module_get_output_dir

    try:
        projects_module.get_output_dir = lambda project_id, settings=None: project_dir  # type: ignore[assignment]
        client = TestClient(app)
        response = client.get("/v1/projects/test-project/artifacts")
    finally:
        projects_module.get_output_dir = projects_module_get_output_dir_orig  # type: ignore[assignment]

    assert response.status_code == 200
    artifact_names = {artifact["name"] for artifact in response.json().get("artifacts", [])}
    assert "trade_assemblies" in artifact_names


def test_get_artifact_unknown_name() -> None:
    """Test that unknown artifact names are rejected."""
    client = TestClient(app)
    
    response = client.get("/v1/projects/test-project/artifacts/../../etc/passwd")
    
    assert response.status_code == 400
    assert "Unknown artifact name" in response.json()["detail"]


def test_get_trade_assemblies_artifact(tmp_path) -> None:
    """Trade assemblies artifact should be downloadable as JSON."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "trade_assemblies.json").write_text('{"project_id": "sample", "assemblies": []}')

    import app.api.routes.projects as projects_module

    projects_module_get_output_dir = getattr(projects_module, "get_output_dir")
    projects_module.ALLOWED_ARTIFACTS.add("trade_assemblies")
    projects_module_get_output_dir_orig = projects_module_get_output_dir

    try:
        projects_module.get_output_dir = lambda project_id, settings=None: project_dir  # type: ignore[assignment]
        client = TestClient(app)
        response = client.get("/v1/projects/test-project/artifacts/trade_assemblies")
    finally:
        projects_module.get_output_dir = projects_module_get_output_dir_orig  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["project_id"] == "sample"






