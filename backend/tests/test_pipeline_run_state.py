"""Unit tests for pipeline run state integration."""

import json
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from app.core.config import Settings
from app.models.schemas import DocumentBundle
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.services.pipeline import PipelineOrchestrator
from app.services.run_state_store import RunStateStore


@pytest.fixture
def temp_storage() -> Path:
    """Create temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_output() -> Path:
    """Create temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def settings(temp_storage: Path) -> Settings:
    """Create settings with temp storage."""
    return Settings(storage_root=temp_storage)


@pytest.fixture
def document_bundle(temp_storage: Path) -> DocumentBundle:
    """Create a test document bundle."""
    project_id = "test_project"
    pdf_path = temp_storage / project_id / "source.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"fake pdf content")
    
    return DocumentBundle(
        project_id=project_id,
        source_pdf_path=pdf_path,
        page_count=5,
        page_image_paths=[temp_storage / project_id / "pages" / f"page_{i}.png" for i in range(1, 6)],
    )


def test_run_state_created_on_first_run(
    settings: Settings, document_bundle: DocumentBundle, temp_output: Path
) -> None:
    """Test that run state is created on first pipeline run."""
    # Mock pipeline with minimal setup (won't actually run stages)
    pipeline = PipelineOrchestrator(settings=settings)
    
    # Check that run state store is initialized
    assert pipeline.run_state_store is not None
    
    # Load state (should be empty/default)
    state = pipeline.run_state_store.load(document_bundle.project_id)
    assert state.project_id == document_bundle.project_id
    assert len(state.stages) == 0


def test_stage_skipping_when_artifacts_exist(
    settings: Settings, document_bundle: DocumentBundle, temp_output: Path
) -> None:
    """Test that stages are skipped when artifacts exist."""
    project_id = document_bundle.project_id
    output_dir = temp_output / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create fake artifact file
    artifact_file = output_dir / "page_index.json"
    artifact_file.write_text('{"project_id": "test", "pages": []}')
    
    pipeline = PipelineOrchestrator(settings=settings, page_indexer=None)
    
    # Mark stage as succeeded in run state
    pipeline.run_state_store.update_stage_state(
        project_id=project_id,
        stage_name="stage_0_5_page_indexing",
        status="succeeded",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        attempts=1,
        artifacts={"page_index": str(artifact_file)},
    )
    
    # Check if should skip
    should_skip, cached = pipeline._should_skip_stage(
        project_id, "stage_0_5_page_indexing", {"page_index": str(artifact_file)}
    )
    
    assert should_skip is True
    assert cached is not None  # Should load cached JSON


def test_stage_resumes_after_failure(
    settings: Settings, document_bundle: DocumentBundle
) -> None:
    """Test that stage resumes after simulated crash."""
    project_id = document_bundle.project_id
    pipeline = PipelineOrchestrator(settings=settings)
    
    # Simulate failed stage
    pipeline.run_state_store.update_stage_state(
        project_id=project_id,
        stage_name="stage_1_document_analysis",
        status="failed",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        attempts=1,
        error="Simulated failure",
    )
    
    # Check if should retry (attempts < max)
    should_skip, _ = pipeline._should_skip_stage(
        project_id,
        "stage_1_document_analysis",
        {"document_analysis": "out/test_project/document_analysis.json"},
    )
    
    assert should_skip is False  # Should retry


def test_stage_skips_after_max_attempts(
    settings: Settings, document_bundle: DocumentBundle
) -> None:
    """Test that stage skips after max retry attempts."""
    project_id = document_bundle.project_id
    pipeline = PipelineOrchestrator(settings=settings)
    
    # Simulate failed stage with max attempts
    pipeline.run_state_store.update_stage_state(
        project_id=project_id,
        stage_name="stage_1_document_analysis",
        status="failed",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        attempts=3,  # Max attempts
        error="Persistent failure",
    )
    
    # Check if should skip
    should_skip, _ = pipeline._should_skip_stage(
        project_id,
        "stage_1_document_analysis",
        {"document_analysis": "out/test_project/document_analysis.json"},
    )
    
    assert should_skip is True  # Should skip (max attempts reached)


def test_artifact_existence_check(settings: Settings) -> None:
    """Test artifact existence checking."""
    pipeline = PipelineOrchestrator(settings=settings)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create a file
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")
        
        # Check exists
        artifacts_exist = {"test": str(test_file)}
        assert pipeline._check_artifacts_exist(artifacts_exist) is True
        
        # Check missing
        artifacts_missing = {"test": str(tmp_path / "missing.json")}
        assert pipeline._check_artifacts_exist(artifacts_missing) is False


def test_stage_four_records_trade_and_gc_artifacts(
    settings: Settings, document_bundle: DocumentBundle
) -> None:
    """Stage 4 run state should store costing, assemblies, and GC artifacts."""

    pipeline = PipelineOrchestrator(settings=settings)
    project_id = document_bundle.project_id

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        costing_path = tmp_path / "costing_result.json"
        assemblies_path = tmp_path / "trade_assemblies.json"
        gc_path = tmp_path / "general_conditions.json"

        expected_artifacts = {
            "costing_result": str(costing_path),
            "trade_assemblies": str(assemblies_path),
            "general_conditions": str(gc_path),
        }

        def _stage_func() -> str:
            costing_path.write_text(json.dumps({"total_cost": 123.45}))
            assemblies_path.write_text(json.dumps({"assemblies": []}))
            gc_path.write_text(json.dumps({"items": []}))
            return "ok"

        result = pipeline._execute_stage_with_state(
            project_id,
            "stage_4_costing",
            _stage_func,
            expected_artifacts,
        )

        assert result == "ok"

        stage_state = pipeline.run_state_store.get_stage_state(project_id, "stage_4_costing")
        assert stage_state is not None
        assert stage_state.status == "succeeded"
        assert stage_state.artifacts == expected_artifacts


def test_stage_four_skip_uses_cached_trade_and_gc(
    settings: Settings, document_bundle: DocumentBundle
) -> None:
    """Stage 4 should skip when costing, assemblies, and GC artifacts already exist."""

    pipeline = PipelineOrchestrator(settings=settings)
    project_id = document_bundle.project_id

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        costing_path = tmp_path / "costing_result.json"
        assemblies_path = tmp_path / "trade_assemblies.json"
        gc_path = tmp_path / "general_conditions.json"

        costing_payload = {"project_id": "cached", "total_cost": 999.99}
        costing_path.write_text(json.dumps(costing_payload))
        assemblies_path.write_text(json.dumps({"assemblies": []}))
        gc_path.write_text(json.dumps({"items": []}))

        pipeline.run_state_store.update_stage_state(
            project_id=project_id,
            stage_name="stage_4_costing",
            status="succeeded",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            artifacts={
                "costing_result": str(costing_path),
                "trade_assemblies": str(assemblies_path),
                "general_conditions": str(gc_path),
            },
        )

        should_skip, cached = pipeline._should_skip_stage(
            project_id,
            "stage_4_costing",
            {
                "costing_result": str(costing_path),
                "trade_assemblies": str(assemblies_path),
                "general_conditions": str(gc_path),
            },
        )

        assert should_skip is True
        assert cached == costing_payload





