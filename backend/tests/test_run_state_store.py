"""Unit tests for run state store."""

import json
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from app.core.config import Settings
from app.schemas.run_state import ProjectRunState, StageRunState
from app.services.run_state_store import RunStateStore


@pytest.fixture
def temp_storage() -> Path:
    """Create temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def settings(temp_storage: Path) -> Settings:
    """Create settings with temp storage."""
    return Settings(storage_root=temp_storage)


@pytest.fixture
def store(settings: Settings) -> RunStateStore:
    """Create run state store."""
    return RunStateStore(settings)


def test_load_missing_state(store: RunStateStore) -> None:
    """Test loading state when file doesn't exist."""
    state = store.load("test_project")
    assert state.project_id == "test_project"
    assert len(state.stages) == 0
    assert state.current_stage is None


def test_save_and_load_state(store: RunStateStore) -> None:
    """Test saving and loading state."""
    project_id = "test_project"
    
    # Create initial state
    state = ProjectRunState(project_id=project_id)
    state.stages.append(
        StageRunState(
            stage_name="stage_1",
            status="succeeded",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            attempts=1,
            artifacts={"result": "out/test_project/result.json"},
        )
    )
    
    # Save
    store.save(state)
    
    # Load
    loaded = store.load(project_id)
    assert loaded.project_id == project_id
    assert len(loaded.stages) == 1
    assert loaded.stages[0].stage_name == "stage_1"
    assert loaded.stages[0].status == "succeeded"


def test_get_stage_state(store: RunStateStore) -> None:
    """Test getting specific stage state."""
    project_id = "test_project"
    
    # Save state with stages
    state = ProjectRunState(project_id=project_id)
    state.stages.append(
        StageRunState(stage_name="stage_1", status="succeeded", attempts=1)
    )
    state.stages.append(
        StageRunState(stage_name="stage_2", status="running", attempts=1)
    )
    store.save(state)
    
    # Get stage state
    stage1 = store.get_stage_state(project_id, "stage_1")
    assert stage1 is not None
    assert stage1.stage_name == "stage_1"
    assert stage1.status == "succeeded"
    
    stage2 = store.get_stage_state(project_id, "stage_2")
    assert stage2 is not None
    assert stage2.status == "running"
    
    # Non-existent stage
    stage3 = store.get_stage_state(project_id, "stage_3")
    assert stage3 is None


def test_update_stage_state(store: RunStateStore) -> None:
    """Test updating stage state."""
    project_id = "test_project"
    
    # Update non-existent stage (creates it)
    store.update_stage_state(
        project_id=project_id,
        stage_name="stage_1",
        status="running",
        started_at=datetime.now(),
        increment_attempts=True,
    )
    
    state = store.load(project_id)
    assert len(state.stages) == 1
    assert state.stages[0].stage_name == "stage_1"
    assert state.stages[0].status == "running"
    assert state.stages[0].attempts == 1
    assert state.current_stage == "stage_1"
    
    # Update to succeeded
    store.update_stage_state(
        project_id=project_id,
        stage_name="stage_1",
        status="succeeded",
        finished_at=datetime.now(),
        artifacts={"result": "out/test_project/result.json"},
    )
    
    state = store.load(project_id)
    assert state.stages[0].status == "succeeded"
    assert len(state.stages[0].artifacts) == 1
    assert state.current_stage is None


def test_atomic_write(store: RunStateStore, temp_storage: Path) -> None:
    """Test that writes are atomic (temp file then rename)."""
    project_id = "test_project"
    state = ProjectRunState(project_id=project_id)
    
    # Save should create final file, not temp file
    store.save(state)
    
    state_path = temp_storage / project_id / "run_state.json"
    assert state_path.exists()
    
    # Temp file should not exist
    temp_path = state_path.with_suffix(".tmp")
    assert not temp_path.exists()


def test_invalid_json_handling(store: RunStateStore, temp_storage: Path) -> None:
    """Test handling of invalid JSON in state file."""
    project_id = "test_project"
    state_path = temp_storage / project_id / "run_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write invalid JSON
    state_path.write_text("invalid json {")
    
    # Load should return default state
    state = store.load(project_id)
    assert state.project_id == project_id
    assert len(state.stages) == 0






