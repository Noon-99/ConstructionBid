"""Pipeline orchestrator for document processing stages."""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.analyzers.institutional_room_extractor import InstitutionalRoomExtractor
from app.analyzers.row_house_repair_extractor import RowHouseRepairExtractor
from app.analyzers.structural_notes_extractor import StructuralNotesExtractor
from app.analyzers.structural_elements_extractor import StructuralElementsExtractor
from app.analyzers.building_envelope_extractor import BuildingEnvelopeExtractor
from app.analyzers.openings_extractor import OpeningsExtractor
from app.analyzers.lintels_extractor import LintelsExtractor
from app.analyzers.detail_extractor import DetailExtractor
from app.costing.cost_engine import CostEngine
from app.generators.model_3d_generator import Model3DGenerator
from app.models.schemas import (
    DocumentBundle,
    ExtractionResults,
    ProjectResult,
    ValidationResults,
)
from app.schemas.coverage_score import CoverageScoreReport
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.schemas.page_index import PageIndex
from app.schemas.trade_coverage import TradeCoverageResult
from app.core.config import Settings
from app.services.metrics_collector import MetricsCollector
from app.services.page_indexer import PageIndexer
from app.services.run_state_store import RunStateStore
from app.services.coverage_evaluator import evaluate_coverage_score
from app.services.trade_dominance_detector import detect_primary_trade
from app.services.trade_coverage_analyzer import analyze_trade_coverage
from app.services.rule_authoring_helper import RuleAuthoringHelper
from app.services.excel_exporter import create_bid_excel_export
from app.services.case_study_generator import generate_compliance_case_study
from app.services.typology_resolver import resolve_typology
from app.services.validation_gates import validate_and_maybe_rerun
from app.utils.timing import stage_timer


def _persist_extraction_with_merge(
    extraction_file: Path, extraction: ExtractionResult, project_id: str
) -> None:
    """Persist extraction to JSON while preserving existing metadata."""

    try:
        existing_data: dict[str, Any] = {}
        if extraction_file.exists():
            with open(extraction_file, "r") as f:
                existing_data = json.load(f)

        merged = _merge_extraction_dict(existing_data, extraction.model_dump(mode="json"))

        extraction_file.parent.mkdir(parents=True, exist_ok=True)
        extraction_file.write_text(json.dumps(merged, indent=2))
        logger.bind(project_id=project_id).debug(
            "Extraction result persisted with metadata merge",
            path=str(extraction_file),
        )
    except Exception as persist_error:  # pragma: no cover - defensive logging
        logger.bind(project_id=project_id).warning(
            f"Failed to persist extraction result with merge: {persist_error}"
        )


def _merge_extraction_dict(existing: dict[str, Any], new_data: dict[str, Any]) -> dict[str, Any]:
    """Merge new extraction data with existing metadata."""

    if not existing:
        return new_data

    merged = existing.copy()
    merged.update(new_data)

    if "validation_metadata" in existing:
        if "validation_metadata" not in merged or not isinstance(merged["validation_metadata"], dict):
            merged["validation_metadata"] = existing["validation_metadata"]
        else:
            merged_validation = existing.get("validation_metadata", {}).copy()
            merged_validation.update(new_data.get("validation_metadata", {}) or {})
            merged["validation_metadata"] = merged_validation

    if "authoritative_dimensions" in existing and new_data.get("authoritative_dimensions"):
        merged["authoritative_dimensions"] = {
            **existing.get("authoritative_dimensions", {}),
            **new_data.get("authoritative_dimensions", {}),
        }

    if "fallback_dimensions" in existing or new_data.get("fallback_dimensions"):
        existing_fallbacks = existing.get("fallback_dimensions", {}) or {}
        new_fallbacks = new_data.get("fallback_dimensions", {}) or {}
        if isinstance(existing_fallbacks, dict) and isinstance(new_fallbacks, dict):
            merged["fallback_dimensions"] = {**existing_fallbacks, **new_fallbacks}
        else:
            merged["fallback_dimensions"] = new_fallbacks or existing_fallbacks

    return merged


_PERSISTED_ARTIFACTS = {
    "pipeline_artifacts": [
        "extraction_result.json",
        "validation_report.json",
        "costing_breakdown.json",
    ],
    "run_state": "run_state.json",
}


_COVERAGE_SIGNAL_FEATURES: dict[str, set[str]] = {
    "roofing_plan": {"plan", "scope"},
    "roofing_detail": {"detail", "materials"},
    "roofing_quantity": {"quantity"},
    "window_schedule": {"quantity", "materials"},
    "window_elevation": {"scope"},
    "window_detail": {"detail", "materials"},
    "paving_plan": {"plan", "scope"},
    "paving_quantity": {"quantity"},
    "masonry_elevation": {"scope"},
    "masonry_detail": {"detail", "materials"},
    "structure_plan": {"plan", "scope"},
    "structure_detail": {"detail", "scope"},
    "interiors_schedule": {"materials", "quantity"},
    "interiors_plan": {"scope"},
}

if TYPE_CHECKING:
    from app.schemas.model_3d import Model3D


class PipelineOrchestrator:
    """Orchestrates the document processing pipeline stages."""

    def __init__(
        self,
        document_analyzer: DocumentAnalyzer | None = None,
        row_house_extractor: RowHouseRepairExtractor | None = None,
        institutional_room_extractor: InstitutionalRoomExtractor | None = None,
        structural_notes_extractor: StructuralNotesExtractor | None = None,
        structural_elements_extractor: StructuralElementsExtractor | None = None,
        building_envelope_extractor: BuildingEnvelopeExtractor | None = None,
        openings_extractor: OpeningsExtractor | None = None,
        lintels_extractor: LintelsExtractor | None = None,
        detail_extractor: DetailExtractor | None = None,
        model_3d_generator: Model3DGenerator | None = None,
        cost_engine: CostEngine | None = None,
        page_indexer: PageIndexer | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize pipeline orchestrator."""
        self.document_analyzer = document_analyzer
        self.row_house_extractor = row_house_extractor
        self.institutional_room_extractor = institutional_room_extractor
        self.structural_notes_extractor = structural_notes_extractor
        self.structural_elements_extractor = structural_elements_extractor
        self.building_envelope_extractor = building_envelope_extractor
        self.openings_extractor = openings_extractor
        self.lintels_extractor = lintels_extractor
        self.detail_extractor = detail_extractor
        self.model_3d_generator = model_3d_generator
        self.cost_engine = cost_engine
        self.page_indexer = page_indexer
        self._rule_authoring_helper: RuleAuthoringHelper | None = None
        
        # Store settings or get from document_analyzer if available
        if settings:
            self.settings = settings
        elif document_analyzer and hasattr(document_analyzer, "settings"):
            self.settings = document_analyzer.settings
        else:
            # Fallback: get from config
            from app.core.config import get_settings
            self.settings = get_settings()
        
        # Ensure settings is always set (defensive check)
        if not hasattr(self, 'settings') or self.settings is None:
            from app.core.config import get_settings
            self.settings = get_settings()
        
        # Initialize run state store
        self.run_state_store = RunStateStore(self.settings)

    def _check_artifacts_exist(self, artifacts: dict[str, str]) -> bool:
        """
        Check if all artifact files exist.

        Args:
            artifacts: Dictionary of artifact names to file paths

        Returns:
            True if all artifacts exist, False otherwise.
            If artifacts dict is empty, returns True (for in-memory stages).
        """
        if not artifacts:
            # Empty artifacts means in-memory transformation stage
            # Return True to allow skipping based on status only
            return True

        from pathlib import Path

        for artifact_name, artifact_path in artifacts.items():
            path = Path(artifact_path)
            if not path.exists():
                logger.debug(f"Artifact missing: {artifact_name} at {artifact_path}")
                return False

        return True

    def _get_output_dir(self, project_id: str) -> Path:
        """Get the output directory for a project."""

        project_root = self.settings.storage_root.parent.parent
        preferred_out = project_root / "out" / project_id
        if preferred_out.exists():
            preferred_out.mkdir(parents=True, exist_ok=True)
            return preferred_out

        legacy_candidates = [
            self.settings.storage_root.parent / "out" / project_id,
            Path("out") / project_id,
            Path("../out") / project_id,
        ]

        for candidate in legacy_candidates:
            if candidate.exists():
                preferred_out.parent.mkdir(parents=True, exist_ok=True)
                if not preferred_out.exists():
                    preferred_out.mkdir(parents=True, exist_ok=True)
                    try:
                        import shutil

                        shutil.copytree(candidate, preferred_out, dirs_exist_ok=True)
                        logger.bind(project_id=project_id).info(
                            "Migrated project artifacts to unified out directory",
                            source=str(candidate),
                            destination=str(preferred_out),
                        )
                    except Exception as migrate_error:  # pragma: no cover
                        logger.bind(project_id=project_id).warning(
                            f"Failed to migrate legacy artifacts from {candidate}: {migrate_error}"
                        )
                return preferred_out

        preferred_out.parent.mkdir(parents=True, exist_ok=True)
        preferred_out.mkdir(parents=True, exist_ok=True)
        return preferred_out

    def _should_skip_stage(
        self, project_id: str, stage_name: str, expected_artifacts: dict[str, str]
    ) -> tuple[bool, Any | None]:
        """
        Check if a stage should be skipped based on run state.

        Args:
            project_id: Project ID
            stage_name: Name of the stage
            expected_artifacts: Dictionary of expected artifact names to paths

        Returns:
            Tuple of (should_skip, cached_result)
            cached_result is the loaded artifact if skip=True, None otherwise
        """
        if not self.run_state_store:
            return False, None

        stage_state = self.run_state_store.get_stage_state(project_id, stage_name)

        if not stage_state:
            return False, None

        # If stage succeeded and artifacts exist, skip
        if stage_state.status == "succeeded":
            # For stages with no artifacts (in-memory transformations), don't skip
            # They need to re-run to apply any code changes
            if not expected_artifacts:
                logger.bind(project_id=project_id).info(
                    f"Stage {stage_name} has no artifacts, re-running (in-memory transformation)"
                )
                return False, None
            elif self._check_artifacts_exist(stage_state.artifacts):
                logger.bind(project_id=project_id).info(
                    f"Stage {stage_name} already succeeded, skipping (artifacts exist)"
                )
                # Try to load cached result if it's a JSON artifact
                cached_result = self._load_cached_artifact(stage_state.artifacts)
                return True, cached_result
            else:
                logger.bind(project_id=project_id).warning(
                    f"Stage {stage_name} marked succeeded but artifacts missing, re-running"
                )

        # If stage failed, check retry limit
        if stage_state.status == "failed":
            max_attempts = 3
            if stage_state.attempts >= max_attempts:
                logger.bind(project_id=project_id).warning(
                    f"Stage {stage_name} failed {stage_state.attempts} times, skipping retry"
                )
                return True, None  # Skip (don't retry)
            else:
                logger.bind(project_id=project_id).info(
                    f"Stage {stage_name} failed previously, retrying (attempt {stage_state.attempts + 1}/{max_attempts})"
                )

        return False, None

    def _load_cached_artifact(self, artifacts: dict[str, str]) -> Any | None:
        """
        Load a cached artifact from disk (for skipping stages).

        Currently only supports JSON files. Returns None if not loadable.

        Args:
            artifacts: Dictionary of artifact names to paths

        Returns:
            Loaded artifact (dict/object) or None
        """
        import json
        from pathlib import Path

        # Try to load the first JSON artifact
        for artifact_name, artifact_path in artifacts.items():
            if artifact_path.endswith(".json"):
                path = Path(artifact_path)
                if path.exists():
                    try:
                        with open(path, "r") as f:
                            return json.load(f)
                    except Exception as e:
                        logger.warning(f"Failed to load cached artifact {artifact_name}: {e}")

        return None

    def _execute_stage_with_state(
        self,
        project_id: str,
        stage_name: str,
        stage_func,
        expected_artifacts: dict[str, str],
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute a stage with run state tracking.

        Args:
            project_id: Project ID
            stage_name: Name of the stage
            stage_func: Function to execute for the stage
            expected_artifacts: Dictionary of artifact names to paths that this stage produces
            *args, **kwargs: Arguments to pass to stage_func

        Returns:
            Result from stage_func

        Raises:
            Exception: If stage execution fails
        """
        from datetime import datetime
        import traceback

        if not self.run_state_store:
            # No run state store, execute normally
            return stage_func(*args, **kwargs)

        # Check if should skip
        should_skip, cached_result = self._should_skip_stage(
            project_id, stage_name, expected_artifacts
        )
        if should_skip:
            if cached_result is not None:
                # Return cached result (will need to convert back to proper type)
                return cached_result
            return None  # Skipped

        # Mark stage as running
        self.run_state_store.update_stage_state(
            project_id=project_id,
            stage_name=stage_name,
            status="running",
            started_at=datetime.now(),
            increment_attempts=True,
        )

        try:
            # Execute stage
            result = stage_func(*args, **kwargs)

            # Mark as succeeded and save artifacts
            self.run_state_store.update_stage_state(
                project_id=project_id,
                stage_name=stage_name,
                status="succeeded",
                finished_at=datetime.now(),
                artifacts=expected_artifacts,
            )

            logger.bind(project_id=project_id).info(
                f"Stage {stage_name} completed successfully"
            )

            return result

        except Exception as e:
            # Mark as failed and store error
            error_summary = f"{type(e).__name__}: {str(e)}"
            # Truncate traceback to last 500 chars
            tb_summary = traceback.format_exc()[-500:] if traceback.format_exc() else None
            error_msg = error_summary + ("\n" + tb_summary if tb_summary else "")

            self.run_state_store.update_stage_state(
                project_id=project_id,
                stage_name=stage_name,
                status="failed",
                finished_at=datetime.now(),
                error=error_msg,
            )

            logger.bind(project_id=project_id).error(
                f"Stage {stage_name} failed: {error_summary}"
            )

            raise

    def run_stage_0_pdf_to_images(
        self, project_id: str, document_bundle: DocumentBundle
    ) -> DocumentBundle:
        """Stage 0: PDF to images (already done by DocumentProcessor)."""
        with stage_timer(project_id, "stage_0_pdf_to_images"):
            logger.bind(project_id=project_id).info(
                "Stage 0: PDF to images completed"
            )
            return document_bundle

    def run_stage_0_5_page_indexing(
        self, project_id: str, document_bundle: DocumentBundle
    ) -> Any | None:
        """Stage 0.5: Page indexing - classify all pages."""
        output_dir = self._get_output_dir(project_id)
        index_file = output_dir / "page_index.json"
        expected_artifacts = {"page_index": str(index_file)}

        def _execute() -> Any | None:
            with stage_timer(project_id, "stage_0_5_page_indexing"):
                # Check if page_index.json already exists (from background job)
                if index_file.exists():
                    logger.bind(project_id=project_id).info(
                        "Page index already exists, loading from file"
                    )
                    try:
                        import json
                        with open(index_file, "r") as f:
                            index_data = json.load(f)
                        from app.schemas.page_index import PageIndex
                        return PageIndex.model_validate(index_data)
                    except Exception as e:
                        logger.bind(project_id=project_id).warning(
                            f"Failed to load existing page_index.json: {e}, will regenerate"
                        )
                
                # Check if page indexing is in progress (progress file exists)
                progress_file = output_dir / "page_index_progress.json"
                if progress_file.exists():
                    try:
                        import json
                        with open(progress_file, "r") as f:
                            progress = json.load(f)
                        completed = progress.get("completed_pages", 0)
                        total = progress.get("total_pages", 0)
                        if completed < total:
                            # Page indexing is still in progress
                            error_msg = (
                                f"Page indexing is still in progress ({completed}/{total} pages). "
                                "Please wait for the background job to complete, or check status at "
                                f"/v1/projects/{project_id}/jobs/page-index/status"
                            )
                            logger.bind(project_id=project_id).warning(error_msg)
                            raise RuntimeError(error_msg)
                    except RuntimeError:
                        raise
                    except Exception as e:
                        logger.bind(project_id=project_id).debug(
                            f"Could not read progress file: {e}, proceeding with indexing"
                        )
                
                if self.page_indexer is None:
                    logger.bind(project_id=project_id).warning(
                        "PageIndexer not provided - skipping page indexing"
                    )
                    return None

                logger.bind(project_id=project_id).info("Stage 0.5: Indexing all pages")

                # Load page images
                from app.utils.pdf_images import load_page_images_from_paths

                page_images = load_page_images_from_paths(document_bundle.page_image_paths)

                # Index pages
                page_index = self.page_indexer.index_pages(project_id, page_images)

                logger.bind(project_id=project_id).info(
                    f"Page indexing complete: {len(page_index.pages)} pages indexed"
                )

                # Save page index to output directory
                index_file.parent.mkdir(parents=True, exist_ok=True)
                with open(index_file, "w") as f:
                    f.write(page_index.model_dump_json(indent=2))
                logger.bind(project_id=project_id).info(f"Page index saved to {index_file}")

                return page_index

        result = self._execute_stage_with_state(
            project_id, "stage_0_5_page_indexing", _execute, expected_artifacts
        )
        
        # If skipped and we have cached result, convert it back to PageIndex
        if result and isinstance(result, dict):
            from app.schemas.page_index import PageIndex
            return PageIndex.model_validate(result)
        
        return result

    def run_stage_1_document_analysis(
        self,
        project_id: str,
        document_bundle: DocumentBundle,
        page_index: Any | None = None,
    ) -> DocumentAnalysis:
        """Stage 1: Document analysis using OpenAI Vision."""
        output_dir = self._get_output_dir(project_id)
        analysis_file = output_dir / "document_analysis.json"
        expected_artifacts = {"document_analysis": str(analysis_file)}

        def _execute() -> DocumentAnalysis:
            with stage_timer(project_id, "stage_1_document_analysis"):
                if self.document_analyzer is None:
                    logger.bind(project_id=project_id).error(
                        "DocumentAnalyzer not provided to PipelineOrchestrator"
                    )
                    raise ValueError(
                        "DocumentAnalyzer must be provided to run Stage 1 analysis"
                    )

                logger.bind(project_id=project_id).info(
                    "Stage 1: Document analysis with OpenAI Vision"
                )

                # Analyze using the document analyzer
                page_texts = getattr(document_bundle, 'page_texts', None)
                logger.bind(project_id=project_id).error(
                    f"PHASE1 TEXT CHECK: page_texts type={type(page_texts)}, "
                    f"is_none={page_texts is None}, "
                    f"hasattr={hasattr(document_bundle, 'page_texts')}, "
                    f"bundle_keys={list(document_bundle.model_dump().keys()) if hasattr(document_bundle, 'model_dump') else 'N/A'}"
                )
                if page_texts:
                    total_chars = sum(len(t) for t in page_texts if t)
                    logger.bind(project_id=project_id).error(
                        f"PHASE1: Passing {len(page_texts)} pages of extracted text ({total_chars} total chars) to document analyzer"
                    )
                else:
                    logger.bind(project_id=project_id).error(
                        "PHASE1: No page_texts in document_bundle - text extraction may have failed or bundle was created before text extraction was added"
                    )
                
                analysis = self.document_analyzer.analyze_from_paths(
                    image_paths=document_bundle.page_image_paths,
                    project_id=project_id,
                    page_index=page_index,
                    page_texts=page_texts,  # Pass extracted text
                )

                # CRITICAL: Apply text-based trade override if page_texts is available
                # This ensures override works even if Stage 1 was cached
                if page_texts:
                    from app.analyzers.document_analyzer import DocumentAnalyzer
                    from app.core.config import Settings
                    from app.services.openai_client import OpenAIClient
                    
                    settings = Settings()
                    openai_client = OpenAIClient(settings)
                    analyzer = DocumentAnalyzer(settings, openai_client)
                    text_result = analyzer._detect_primary_trade_from_text(page_texts, project_id)
                    
                    if text_result:
                        logger.bind(project_id=project_id).error(
                            f"✅✅✅ PIPELINE OVERRIDE: Text-based detection found {text_result['primary_trade']} "
                            f"(Division {text_result['primary_division']}) - FORCING OVERRIDE on analysis object"
                        )
                        # Force override on analysis object
                        analysis = analysis.model_copy(update={
                            "primary_division": text_result["primary_division"],
                            "primary_trade": text_result["primary_trade"],
                            "trade_detection_confidence": text_result["confidence"],
                        })
                        logger.bind(project_id=project_id).error(
                            f"✅✅✅ OVERRIDE APPLIED: analysis now has {analysis.primary_division}/{analysis.primary_trade}"
                        )

                # Save document analysis
                analysis_file.parent.mkdir(parents=True, exist_ok=True)
                with open(analysis_file, "w") as f:
                    f.write(analysis.model_dump_json(indent=2))
                logger.bind(project_id=project_id).info(f"Document analysis saved to {analysis_file}")

                return analysis

        result = self._execute_stage_with_state(
            project_id, "stage_1_document_analysis", _execute, expected_artifacts
        )
        
        # If skipped and we have cached result, convert it back to DocumentAnalysis
        if result and isinstance(result, dict):
            analysis = DocumentAnalysis.model_validate(result)
            
            # CRITICAL: Apply text-based override even when Stage 1 is cached
            # This ensures override works even if document_analysis.json was loaded from cache
            # If page_texts not in bundle, extract it from PDF now
            page_texts = getattr(document_bundle, 'page_texts', None)
            if not page_texts and document_bundle.source_pdf_path and document_bundle.source_pdf_path.exists():
                logger.bind(project_id=project_id).error(
                    "PHASE1 CACHE OVERRIDE: page_texts missing from bundle - extracting from PDF now"
                )
                from app.services.document_processor import DocumentProcessor
                processor = DocumentProcessor(self.settings, None)
                temp_bundle = processor.process_pdf(project_id, document_bundle.source_pdf_path)
                page_texts = temp_bundle.page_texts
                if page_texts:
                    logger.bind(project_id=project_id).error(
                        f"PHASE1 CACHE OVERRIDE: Extracted {len(page_texts)} pages of text from PDF"
                    )
            
            if page_texts:
                from app.analyzers.document_analyzer import DocumentAnalyzer
                from app.core.config import Settings
                from app.services.openai_client import OpenAIClient
                
                settings = Settings()
                openai_client = OpenAIClient(settings)
                analyzer = DocumentAnalyzer(settings, openai_client)
                text_result = analyzer._detect_primary_trade_from_text(page_texts, project_id)
                
                if text_result:
                    logger.bind(project_id=project_id).error(
                        f"✅✅✅ CACHE OVERRIDE: Text-based detection found {text_result['primary_trade']} "
                        f"(Division {text_result['primary_division']}) - FORCING OVERRIDE on cached analysis"
                    )
                    # Force override on cached analysis
                    analysis = analysis.model_copy(update={
                        "primary_division": text_result["primary_division"],
                        "primary_trade": text_result["primary_trade"],
                        "trade_detection_confidence": text_result["confidence"],
                    })
                    logger.bind(project_id=project_id).error(
                        f"✅✅✅ CACHE OVERRIDE APPLIED: analysis now has {analysis.primary_division}/{analysis.primary_trade}"
                    )
                    # Save updated analysis
                    analysis_file = self._get_output_dir(project_id) / "document_analysis.json"
                    analysis_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(analysis_file, "w") as f:
                        f.write(analysis.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).error(f"Cached analysis updated with override: {analysis_file}")
            
            return analysis
        
        return result

    def run_stage_1_5_typology_resolution(
        self, project_id: str, analysis: DocumentAnalysis, page_texts: list[str] | None = None
    ) -> DocumentAnalysis:
        """Stage 1.5: Typology resolution (deterministic rule-based correction)."""
        # This stage doesn't produce artifacts (in-memory transformation)
        # Use empty artifacts dict - skip based on status only
        expected_artifacts = {}

        def _execute() -> DocumentAnalysis:
            with stage_timer(project_id, "stage_1_5_typology_resolution"):
                logger.bind(project_id=project_id).info(
                    "Stage 1.5: Typology resolution (deterministic rules)"
                )

                resolved = resolve_typology(analysis, page_texts=page_texts)

                if resolved.resolution_notes:
                    logger.bind(project_id=project_id).info(
                        f"Typology resolution applied: {len(resolved.resolution_notes)} overrides"
                    )
                else:
                    logger.bind(project_id=project_id).info(
                        "No typology resolution needed - Stage 1 classification is correct"
                    )

                return resolved

        result = self._execute_stage_with_state(
            project_id, "stage_1_5_typology_resolution", _execute, expected_artifacts
        )
        
        # If skipped, return original analysis (typology resolution is idempotent)
        if result is None:
            return analysis
        
        return result

    def _perform_extraction_with_routing(
        self,
        project_id: str,
        document_bundle: DocumentBundle,
        document_analysis: DocumentAnalysis,
        page_index: Any | None = None,
        output_dir: Path | None = None,
    ) -> ExtractionResult:
        """
        Core extraction logic with routing to appropriate extractors.
        
        This is extracted from run_stage_2_adaptive_extraction so it can be reused
        for rescue reruns with modified analysis.
        
        Args:
            project_id: Project ID
            document_bundle: Document bundle with PDF path and page images
            document_analysis: Document analysis (can be modified for rescue reruns)
            page_index: Optional page index
            output_dir: Optional output directory (will be computed if None)
            
        Returns:
            ExtractionResult
        """
        if output_dir is None:
            output_dir = self._get_output_dir(project_id)
        extraction_file = output_dir / "extraction_result.json"

        with stage_timer(project_id, "stage_2_adaptive_extraction"):
            # Get resolved types (use resolved if available, else original)
            project_type = (
                document_analysis.resolved_project_type or document_analysis.project_type
            )
            scope_type = document_analysis.resolved_scope_type or document_analysis.scope_type

            logger.bind(project_id=project_id).info(
                f"Stage 2: Adaptive extraction for {project_type} + {scope_type}"
            )

            # Generate typology confidence report (Phase 10.7)
            from app.services.typology_confidence_service import generate_typology_confidence_report

            # Determine routing decision
            routing_decision = "fallback_row_house"
            routing_reason = "No matching extractor - using fallback"

            # Route to row-house repair extractor
            if project_type == "row_house" and scope_type == "repair":
                routing_decision = "row_house_path"
                routing_reason = "project_type=row_house and scope_type=repair"
                if self.row_house_extractor is None:
                    raise ValueError(
                        "RowHouseRepairExtractor must be provided for row_house + repair projects"
                    )

                from app.utils.pdf_images import pdf_to_images

                pdf_images = pdf_to_images(
                    document_bundle.source_pdf_path,
                    self.row_house_extractor.settings,
                    project_id,
                )

                # CRITICAL: Pass page_texts to extractor (Stage 2 needs text like Stage 1 had)
                page_texts = document_bundle.page_texts if hasattr(document_bundle, 'page_texts') else None
                
                extraction = self.row_house_extractor.extract(
                    pdf_images=pdf_images,
                    analysis=document_analysis,
                    project_id=project_id,
                    page_texts=page_texts,
                )

                _persist_extraction_with_merge(extraction_file, extraction, project_id)

                confidence_report = generate_typology_confidence_report(
                    project_id=project_id,
                    document_analysis=document_analysis,
                    routing_decision=routing_decision,
                    routing_reason=routing_reason,
                )
                report_file = output_dir / "typology_confidence_report.json"
                report_file.parent.mkdir(parents=True, exist_ok=True)
                with open(report_file, "w") as f:
                    f.write(confidence_report.model_dump_json(indent=2))
                logger.bind(project_id=project_id).info(f"Typology confidence report saved to {report_file}")

                return extraction

            # Phase 10.7: Conservative fallback for new/uncertain typologies
            # small_commercial, multi_family, unknown, or other uncertain cases fall back to row_house
            # Also handle scope_type="unknown" by defaulting to "repair"
            if project_type in ["small_commercial", "multi_family", "unknown"] or routing_decision == "fallback_row_house" or scope_type == "unknown":
                routing_decision = "fallback_row_house"
                routing_reason = f"Uncertain typology ({project_type}+{scope_type}) - falling back to row_house extractor"
                logger.bind(project_id=project_id).warning(
                    f"No specific extractor for {project_type}+{scope_type} - "
                    "using row_house extractor as conservative fallback"
                )
                
                # Use row_house extractor as fallback
                if self.row_house_extractor is None:
                    raise ValueError(
                        f"RowHouseRepairExtractor required for fallback routing of {project_type} + {scope_type} projects"
                    )
                
                from app.utils.pdf_images import pdf_to_images
                pdf_images = pdf_to_images(
                    document_bundle.source_pdf_path,
                    self.row_house_extractor.settings,
                    project_id,
                )
                
                # CRITICAL: Pass page_texts to extractor (Stage 2 needs text like Stage 1 had)
                page_texts = document_bundle.page_texts if hasattr(document_bundle, 'page_texts') else None
                
                extraction = self.row_house_extractor.extract(
                    pdf_images=pdf_images,
                    analysis=document_analysis,
                    project_id=project_id,
                    page_texts=page_texts,
                )
                
                _persist_extraction_with_merge(extraction_file, extraction, project_id)
                logger.bind(project_id=project_id).info(
                    f"Extraction result saved to {extraction_file}"
                )
                
                # Generate and save typology confidence report
                confidence_report = generate_typology_confidence_report(
                    project_id=project_id,
                    document_analysis=document_analysis,
                    routing_decision=routing_decision,
                    routing_reason=routing_reason,
                )
                report_file = output_dir / "typology_confidence_report.json"
                report_file.parent.mkdir(parents=True, exist_ok=True)
                with open(report_file, "w") as f:
                    f.write(confidence_report.model_dump_json(indent=2))
                logger.bind(project_id=project_id).info(f"Typology confidence report saved to {report_file}")
                
                return extraction
                
            # Other project types not implemented yet
            raise ValueError(
                f"Extractor not implemented for {project_type} + {scope_type} projects"
            )

        result = self._execute_stage_with_state(
            project_id, "stage_2_adaptive_extraction", _execute, expected_artifacts
        )

        if result is None:
            if extraction_file.exists():
                try:
                    import json

                    with open(extraction_file, "r") as f:
                        cached = json.load(f)
                    return ExtractionResult.model_validate(cached)
                except Exception as load_error:  # pragma: no cover - defensive logging
                    logger.bind(project_id=project_id).debug(
                        f"Failed to load cached extraction_result.json: {load_error}"
                    )
            return None

        if isinstance(result, dict):
            return ExtractionResult.model_validate(result)

        return result

    def _select_rescue_pages_from_coverage(
        self,
        coverage_report: CoverageScoreReport,
        trade_coverage: TradeCoverageResult,
        *,
        page_index: PageIndex | None,
        document_analysis: DocumentAnalysis,
    ) -> set[int]:
        """Identify additional pages to include for a coverage rescue rerun.

        Pages are selected based on missing trades in the coverage score and the
        evidence recorded during the initial trade coverage scan.
        """

        if page_index is None:
            return set()

        pages: set[int] = set()

        dominant_trades = coverage_report.dominant_trades[:3]
        missing_trades = {entry.trade for entry in coverage_report.missing_trades}

        for entry in trade_coverage.trades:
            if entry.trade not in dominant_trades and entry.trade not in missing_trades:
                continue

            for evidence in entry.evidence:
                if evidence.page_number is None:
                    continue
                index = evidence.page_number - 1
                if 0 <= index < page_index.total_pages:
                    pages.add(index)

        if not pages and document_analysis.where_scope_lives:
            for locator in document_analysis.where_scope_lives:
                if locator.page_number:
                    pages.add(locator.page_number - 1)

        logger.bind(project_id=coverage_report.project_id).debug(
            "Coverage rescue pages selected",
            pages=sorted(pages),
        )

        return pages

    def _maybe_reroute_after_extraction(
        self,
        *,
        project_id: str,
        analysis: DocumentAnalysis,
        extraction: ExtractionResult,
        document_bundle: DocumentBundle,
        page_index: PageIndex | None,
        output_dir: Path,
        trade_coverage: TradeCoverageResult,
    ) -> tuple[ExtractionResult, DocumentAnalysis, str | None]:
        """Placeholder hook for typology reroute assistance after extraction.

        Until richer routing is implemented, keep the original artifacts so the
        caller can invoke this helper safely without additional branching.
        """

        logger.bind(project_id=project_id).debug(
            "Post-extraction reroute hook not implemented; returning original artifacts"
        )
        return extraction, analysis, None

    def run_stage_2_5a_dimension_authority(
        self,
        project_id: str,
        analysis: DocumentAnalysis,
        extraction: ExtractionResult,
    ) -> ExtractionResult:
        """Stage 2.5A: Dimension authority resolution."""
        # This stage doesn't produce artifacts (in-memory transformation)
        # Use empty artifacts dict - skip based on status only
        expected_artifacts = {}

        def _execute() -> ExtractionResult:
            with stage_timer(project_id, "stage_2_5a_dimension_authority"):
                logger.bind(project_id=project_id).info("Stage 2.5A: Resolving dimension authority")

                from app.services.dimension_authority import resolve_dimension_authority

                authoritative_dims = resolve_dimension_authority(analysis, extraction)

                # Update extraction with authoritative dimensions
                extraction.authoritative_dimensions = authoritative_dims

                # Update geometry_for_3d with authoritative dimensions if missing
                if extraction.geometry_for_3d and extraction.geometry_for_3d.dimensions:
                    if authoritative_dims.width:
                        extraction.geometry_for_3d.dimensions.width = authoritative_dims.width
                    if authoritative_dims.depth:
                        extraction.geometry_for_3d.dimensions.depth = authoritative_dims.depth
                    if authoritative_dims.height:
                        extraction.geometry_for_3d.dimensions.height = authoritative_dims.height

                logger.bind(project_id=project_id).info(
                    f"Dimension authority resolved: width={authoritative_dims.width}, "
                    f"depth={authoritative_dims.depth}, height={authoritative_dims.height}"
                )

                try:
                    output_dir = self._get_output_dir(project_id)
                    extraction_file = output_dir / "extraction_result.json"
                    _persist_extraction_with_merge(extraction_file, extraction, project_id)
                except Exception as e:
                    logger.bind(project_id=project_id).error(
                        f"Failed to save extraction result with authoritative dimensions: {e}",
                        exc_info=True
                    )

                return extraction

        result = self._execute_stage_with_state(
            project_id, "stage_2_5a_dimension_authority", _execute, expected_artifacts
        )
        
        # If skipped, return original extraction
        if result is None:
            return extraction
        
        return result

    def run_stage_2_5_validation_gates(
        self,
        project_id: str,
        analysis: DocumentAnalysis,
        extraction: ExtractionResult,
        page_index: Any | None,
        document_bundle: DocumentBundle | None = None,
    ) -> tuple[ExtractionResult, Any]:
        """Stage 2.5: Validation gates and auto re-read."""
        output_dir = self._get_output_dir(project_id)
        report_file = output_dir / "validation_report.json"
        expected_artifacts = {"validation_report": str(report_file)}

        def _execute() -> tuple[ExtractionResult, Any]:
            nonlocal extraction  # Capture extraction from outer scope
            with stage_timer(project_id, "stage_2_5_validation_gates"):
                logger.bind(project_id=project_id).info("Stage 2.5: Validation gates")

                # Get settings and openai_client from document_analyzer
                if self.document_analyzer is None:
                    raise ValueError("DocumentAnalyzer required for validation gates")

                settings = self.document_analyzer.settings
                openai_client = self.document_analyzer.openai_client

                manual_override_payload: dict[str, Any] = {}
                try:
                    from app.services.manual_override_service import load_manual_overrides

                    overrides_model = load_manual_overrides(project_id, settings)
                    manual_override_payload = overrides_model.sanitized()
                    if manual_override_payload:
                        if extraction.validation_metadata is None:
                            extraction.validation_metadata = {}
                        existing_overrides = (
                            extraction.validation_metadata.get("manual_overrides", {})
                        )
                        extraction.validation_metadata["manual_overrides"] = {
                            **existing_overrides,
                            **manual_override_payload,
                        }
                        logger.bind(project_id=project_id).debug(
                            "Manual overrides attached to extraction for validation",
                            overrides=manual_override_payload,
                        )
                except Exception as override_error:  # pragma: no cover - defensive logging
                    logger.bind(project_id=project_id).debug(
                        f"Could not load manual overrides before validation: {override_error}"
                    )

                extraction, validation_report = validate_and_maybe_rerun(
                    project_id=project_id,
                    analysis=analysis,
                    extraction=extraction,
                    page_index=page_index,
                    settings=settings,
                    openai_client=openai_client,
                    document_bundle=document_bundle,
                )

                report_file.parent.mkdir(parents=True, exist_ok=True)
                with open(report_file, "w") as f:
                    f.write(validation_report.model_dump_json(indent=2))
                logger.bind(project_id=project_id).info(f"Validation report saved to {report_file}")

                try:
                    extraction_file = output_dir / "extraction_result.json"
                    _persist_extraction_with_merge(extraction_file, extraction, project_id)
                except Exception as save_error:  # pragma: no cover - defensive logging
                    logger.bind(project_id=project_id).debug(
                        f"Failed to persist extraction metadata after validation: {save_error}"
                    )

                # Log validation result
                if not validation_report.passed:
                    logger.bind(project_id=project_id).warning(
                        f"Validation failed: {len([i for i in validation_report.issues if i.severity == 'error'])} errors"
                    )

                return extraction, validation_report

        result = self._execute_stage_with_state(
            project_id, "stage_2_5_validation_gates", _execute, expected_artifacts
        )
        
        # If skipped and we have cached result, convert it back
        if result and isinstance(result, tuple):
            # Already a tuple, return as-is
            return result
        elif result and isinstance(result, dict):
            # Cached result is a dict, need to load validation_report from file
            from app.schemas.validation_report import ValidationReport
            if report_file.exists():
                with open(report_file, "r") as f:
                    import json
                    validation_data = json.load(f)
                    validation_report = ValidationReport.model_validate(validation_data)
                    return extraction, validation_report
            # Fallback if file doesn't exist
            return extraction, None
        
        # If result is None or something else, return extraction and None
        return extraction, None

    def run_stage_3_validation(
        self,
        project_id: str,
        document_bundle: DocumentBundle,
        document_analysis: DocumentAnalysis,
        extraction: ExtractionResult,
    ) -> ValidationResults:
        """Stage 3: Validation (stub)."""
        with stage_timer(project_id, "stage_3_validation"):
            logger.bind(project_id=project_id).info("Stage 3: Validation (stub)")
            # Stub: Return placeholder structure
            return ValidationResults(
                missing_critical=[],
                needs_reread_pages=[],
                notes=["All required information extracted successfully"],
            )

    def run_stage_3_model_generation(
        self, project_id: str, extraction: ExtractionResult
    ) -> Any | None:
        """Stage 3: 3D model generation from extraction results."""
        output_dir = self._get_output_dir(project_id)
        model_file = output_dir / "model_3d.json"
        expected_artifacts = {"model_3d": str(model_file)}

        def _execute() -> Any | None:
            with stage_timer(project_id, "stage_3_model_generation"):
                if self.model_3d_generator is None:
                    logger.bind(project_id=project_id).warning(
                        "Model3DGenerator not provided - skipping 3D model generation"
                    )
                    return None

                logger.bind(project_id=project_id).info("Stage 3: Generating 3D model")

                # Load document_analysis for site_context and dimension authority (Tasks 4 & 5)
                document_analysis = None
                analysis_file = output_dir / "document_analysis.json"
                if analysis_file.exists():
                    import json
                    with open(analysis_file, "r") as f:
                        analysis_dict = json.load(f)
                        from app.schemas.document_analysis import DocumentAnalysis
                        document_analysis = DocumentAnalysis.model_validate(analysis_dict)

                model = self.model_3d_generator.generate(extraction, document_analysis)

                logger.bind(project_id=project_id).info(
                    f"3D model generated: {len(model.buildings)} buildings, "
                    f"{len(model.work_zones)} work zones"
                )

                # Save 3D model
                model_file.parent.mkdir(parents=True, exist_ok=True)
                with open(model_file, "w") as f:
                    f.write(model.model_dump_json(indent=2))
                logger.bind(project_id=project_id).info(f"3D model saved to {model_file}")

                return model

        result = self._execute_stage_with_state(
            project_id, "stage_3_model_generation", _execute, expected_artifacts
        )
        
        # If skipped and we have cached result, convert it back
        if result and isinstance(result, dict):
            from app.schemas.model_3d import Model3D
            return Model3D.model_validate(result)
        
        return result

    def run_stage_4_costing(
        self,
        project_id: str,
        extraction: ExtractionResult,
        model_3d: Any | None,
        pricing_profile: Any | None = None,
    ) -> Any | None:
        """Stage 4: Cost computation from extraction and geometry."""
        output_dir = self._get_output_dir(project_id)
        costing_file = output_dir / "costing_result.json"
        trade_assemblies_file = output_dir / "trade_assemblies.json"
        general_conditions_file = output_dir / "general_conditions.json"
        expected_artifacts = {
            "costing_result": str(costing_file),
            "trade_assemblies": str(trade_assemblies_file),
            "general_conditions": str(general_conditions_file),
        }

        def _execute() -> Any | None:
            with stage_timer(project_id, "stage_4_costing"):
                if self.cost_engine is None:
                    logger.bind(project_id=project_id).warning(
                        "CostEngine not provided - skipping cost computation"
                    )
                    return None

                logger.bind(project_id=project_id).info("Stage 4: Computing costs")
                
                # Phase 10.10B: Load pricing profile if not provided
                # Initialize pricing_profile variable in local scope
                local_pricing_profile = pricing_profile
                if local_pricing_profile is None:
                    try:
                        from app.services.pricing_profile_service import select_profile
                        # json is already imported at top of file
                        
                        # Try to load saved profile first
                        profile_file = output_dir / "pricing_profile.json"
                        if profile_file.exists():
                            with open(profile_file, "r") as f:
                                profile_data = json.load(f)
                            from app.schemas.pricing_profile import PricingProfile
                            local_pricing_profile = PricingProfile.model_validate(profile_data)
                            logger.bind(project_id=project_id).info(f"Loaded saved pricing profile: {local_pricing_profile.profile_id}")
                        else:
                            # Fallback: try to select profile from artifacts
                            analysis_file = output_dir / "document_analysis.json"
                            extraction_file = output_dir / "extraction_result.json"
                            document_analysis_dict = None
                            extraction_result_dict = None
                            
                            if analysis_file.exists():
                                with open(analysis_file, "r") as f:
                                    document_analysis_dict = json.load(f)
                            if extraction_file.exists():
                                with open(extraction_file, "r") as f:
                                    extraction_result_dict = json.load(f)
                            
                            local_pricing_profile = select_profile(
                                document_analysis=document_analysis_dict,
                                extraction_result=extraction_result_dict,
                                settings=self.settings,
                            )
                    except Exception as e:
                        logger.bind(project_id=project_id).warning(f"Failed to load pricing profile for costing: {e}")
                        local_pricing_profile = None

                # Task 6: Load document_analysis to get labor_regime and compliance flags
                # CRITICAL: analysis_file must be defined here (it's used in the try block above)
                analysis_file = output_dir / "document_analysis.json"
                
                logger.bind(project_id=project_id).error(
                    f"PHASE1: Attempting to load document_analysis.json from {analysis_file}, exists={analysis_file.exists()}"
                )
                
                labor_regime = "standard"
                labor_regime_confidence = 0.5
                analysis_data: dict[str, Any] | None = None
                try:
                    if analysis_file.exists():
                        with open(analysis_file, "r") as f:
                            analysis_data = json.load(f)
                            logger.bind(project_id=project_id).error(
                                f"PHASE1: Successfully loaded document_analysis.json, keys={list(analysis_data.keys())[:5]}"
                            )
                            labor_regime = analysis_data.get("labor_regime", "standard")
                            labor_regime_confidence = analysis_data.get("labor_regime_confidence", 0.5)
                            if labor_regime == "prevailing_wage":
                                logger.bind(project_id=project_id).info(
                                    f"Prevailing wage detected (confidence: {labor_regime_confidence:.2f}): {analysis_data.get('labor_regime_evidence', 'DOT/public work')}"
                                )
                    else:
                        logger.bind(project_id=project_id).error(f"PHASE1: document_analysis.json does NOT exist at {analysis_file}")
                except Exception as e:
                    logger.bind(project_id=project_id).error(f"PHASE1: Exception loading document_analysis.json: {e}", exc_info=True)

                # Derive compliance context
                requires_prevailing_wage = False
                requires_bonds = False
                procurement_context: dict[str, Any] | None = None
                if analysis_data:
                    logger.bind(project_id=project_id).error(
                        f"PHASE1: analysis_data is NOT None - requires_prevailing_wage={analysis_data.get('requires_prevailing_wage')}, "
                        f"requires_bonds={analysis_data.get('requires_bonds')}, "
                        f"procurement_context={bool(analysis_data.get('procurement_context'))}"
                    )
                    # Phase 1: Read procurement flags from document analysis
                    requires_prevailing_wage = bool(analysis_data.get("requires_prevailing_wage") or False)
                    requires_bonds = bool(analysis_data.get("requires_bonds") or False)
                    procurement_context = analysis_data.get("procurement_context")
                    logger.bind(project_id=project_id).error(
                        f"PHASE1: After reading flags - requires_prevailing_wage={requires_prevailing_wage}, requires_bonds={requires_bonds}"
                    )
                else:
                    logger.bind(project_id=project_id).error("PHASE1: analysis_data is None - compliance flags will be False!")
                    
                    # Log what we found
                    if procurement_context:
                        is_public = bool(procurement_context.get("is_public_project", False))
                        if is_public:
                            logger.bind(project_id=project_id).info(
                                f"Government project detected (confidence: {procurement_context.get('detection_confidence', 0.0):.2f})",
                                issuing_authority=procurement_context.get("issuing_authority"),
                                requires_prevailing_wage=requires_prevailing_wage,
                                requires_bonds=requires_bonds
                            )

                if labor_regime == "standard" and requires_prevailing_wage:
                    logger.bind(project_id=project_id).info(
                        "Stage 1 flagged prevailing wage; applying prevailing wage labor regime for costing"
                    )
                    labor_regime = "prevailing_wage"

                is_union_project = labor_regime == "union"
                requires_insurance = bool(requires_bonds)
                if procurement_context:
                    is_public = bool(procurement_context.get("is_public_project"))
                    requires_insurance = requires_insurance or is_public
                else:
                    is_public = False

                if requires_bonds:
                    logger.bind(project_id=project_id).info("Bond requirements detected; adding compliance cost adders")
                if requires_insurance and not requires_bonds and is_public:
                    logger.bind(project_id=project_id).info("Public procurement detected; adding insurance compliance adders")

                # Get compliance multipliers from settings
                # Phase 1: Use settings directly (they have proper defaults: bond=2.5%, insurance=1.2%, prevailing_wage=1.5x)
                prevailing_wage_multiplier = self.settings.compliance_prevailing_wage_multiplier
                union_multiplier = getattr(self.settings, "compliance_union_multiplier", 1.0)
                # CRITICAL: These defaults are in Settings class (2.5% bonds, 1.2% insurance) - NOT zero!
                bond_rate_pct = self.settings.compliance_bond_rate_pct
                insurance_rate_pct = self.settings.compliance_insurance_rate_pct
                
                # Log the rates being used for debugging
                logger.bind(project_id=project_id).info(
                    "Compliance cost rates",
                    bond_rate_pct=bond_rate_pct,
                    insurance_rate_pct=insurance_rate_pct,
                    prevailing_wage_multiplier=prevailing_wage_multiplier,
                    requires_bonds=requires_bonds,
                    requires_insurance=requires_insurance,
                )

                manual_overrides = None
                try:
                    from app.services.manual_override_service import load_manual_overrides

                    manual_overrides = load_manual_overrides(project_id, self.settings)
                    if manual_overrides:
                        sanitized = manual_overrides.sanitized()
                        if sanitized:
                            if extraction.validation_metadata is None:
                                extraction.validation_metadata = {}
                            existing_overrides = extraction.validation_metadata.get("manual_overrides", {})
                            extraction.validation_metadata["manual_overrides"] = {
                                **existing_overrides,
                                **sanitized,
                            }
                            logger.bind(project_id=project_id).debug(
                                "Manual overrides attached to extraction for costing",
                                overrides=sanitized,
                            )
                except Exception as override_error:  # pragma: no cover - defensive logging
                    logger.bind(project_id=project_id).debug(
                        f"Could not load manual overrides: {override_error}"
                    )

                costing_result = self.cost_engine.compute_cost(
                    extraction,
                    model_3d,
                    local_pricing_profile,
                    labor_regime=labor_regime,
                    labor_regime_confidence=labor_regime_confidence,
                    prevailing_wage_multiplier=prevailing_wage_multiplier,
                    union_multiplier=union_multiplier,
                    requires_prevailing_wage=requires_prevailing_wage,
                    requires_bonds=requires_bonds,
                    requires_insurance=requires_insurance,
                    bond_rate_pct=bond_rate_pct,
                    insurance_rate_pct=insurance_rate_pct,
                    procurement_context=procurement_context,
                    project_id=project_id,
                    manual_overrides=manual_overrides,
                )

                logger.bind(project_id=project_id).info(
                    f"Cost computation complete: ${costing_result.total_cost:,.2f} total"
                )

                rule_governance = costing_result.rule_governance
                if rule_governance and rule_governance.missing_rules:
                    governance_file = output_dir / "rules_governance.json"
                    governance_file.parent.mkdir(parents=True, exist_ok=True)
                    if self.settings.rule_authoring_auto_generate:
                        if self._rule_authoring_helper is None:
                            self._rule_authoring_helper = RuleAuthoringHelper(settings=self.settings)
                        logger.bind(project_id=project_id).info(
                            "Generating draft cost rules for %d missing items",
                            len(rule_governance.missing_rules),
                        )
                        updated_report = self._rule_authoring_helper.generate_drafts(
                            rule_governance, output_dir
                        )
                        costing_result.rule_governance = updated_report
                        governance_file.write_text(updated_report.model_dump_json(indent=2))
                    else:
                        governance_file.write_text(rule_governance.model_dump_json(indent=2))
                        logger.bind(project_id=project_id).warning(
                            "Missing cost rules detected (%d items). Governance report saved to %s",
                            len(rule_governance.missing_rules),
                            governance_file,
                        )

                # Save costing result
                costing_file.parent.mkdir(parents=True, exist_ok=True)
                with open(costing_file, "w") as f:
                    f.write(costing_result.model_dump_json(indent=2))
                logger.bind(project_id=project_id).info(f"Costing result saved to {costing_file}")

                return costing_result

        result = self._execute_stage_with_state(
            project_id, "stage_4_costing", _execute, expected_artifacts
        )
        
        # If skipped and we have cached result, convert it back
        if result and isinstance(result, dict):
            from app.schemas.costing import CostEngineResult
            return CostEngineResult.model_validate(result)
        
        return result

    def run_full_pipeline(
        self, project_id: str, document_bundle: DocumentBundle
    ) -> ProjectResult:
        """Run the complete processing pipeline."""
        logger.bind(project_id=project_id).info("Starting full pipeline")

        # Initialize metrics collector (Phase 2.6C)
        from pathlib import Path
        output_dir = Path("out") / project_id
        metrics_collector = MetricsCollector(project_id)

        # Stage 0: PDF to images (already done)
        bundle = self.run_stage_0_pdf_to_images(project_id, document_bundle)

        # Stage 0.5: Page indexing
        metrics_collector.start_stage("stage_0_5_page_indexing", pages_sent=bundle.page_count)
        page_index = self.run_stage_0_5_page_indexing(project_id, bundle)

        # Trade coverage scan (Task 1)
        try:
            trade_coverage = analyze_trade_coverage(
                project_id=project_id,
                page_index=page_index,
                settings=self.settings,
            )
            coverage_file = output_dir / "trade_coverage.json"
            coverage_file.parent.mkdir(parents=True, exist_ok=True)
            coverage_file.write_text(trade_coverage.model_dump_json(indent=2))
            logger.bind(project_id=project_id).info(
                f"Trade coverage saved to {coverage_file} ({len(trade_coverage.trades)} trades)"
            )
        except Exception as coverage_error:
            logger.bind(project_id=project_id).warning(
                f"Failed to generate trade coverage: {coverage_error}"
            )
            trade_coverage = None
        # Record tokens if available
        if self.page_indexer and self.page_indexer.openai_client:
            usage = self.page_indexer.openai_client.get_last_usage()
            if usage:
                metrics_collector.record_tokens(
                    "stage_0_5_page_indexing",
                    usage["prompt_tokens"],
                    usage["completion_tokens"],
                )
        metrics_collector.end_stage("stage_0_5_page_indexing")

        # Stage 1: Document analysis
        # Count pages sent (from page selector)
        from app.services.page_selector import select_pages_for_stage1
        stage1_selected_indices = select_pages_for_stage1(
            bundle.page_count, page_index=page_index, settings=self.settings
        )
        stage1_pages = len(stage1_selected_indices)
        metrics_collector.start_stage("stage_1_document_analysis", pages_sent=stage1_pages)
        analysis = self.run_stage_1_document_analysis(project_id, bundle, page_index)
        # Record tokens
        if self.document_analyzer and self.document_analyzer.openai_client:
            usage = self.document_analyzer.openai_client.get_last_usage()
            if usage:
                metrics_collector.record_tokens(
                    "stage_1_document_analysis",
                    usage["prompt_tokens"],
                    usage["completion_tokens"],
                )
        metrics_collector.end_stage("stage_1_document_analysis")

        # Stage 1.5: Typology resolution (deterministic rule-based correction)
        # CRITICAL: Attach page_texts to analysis for typology resolver text-based detection
        # This MUST happen before typology resolver runs
        logger.bind(project_id=project_id).error(
            f"=== PHASE1 TYPOLOGY PREP: project_id={project_id}, bundle_type={type(bundle).__name__} ==="
        )
        logger.bind(project_id=project_id).error(
            f"PHASE1 TYPOLOGY: Checking bundle for page_texts - hasattr={hasattr(bundle, 'page_texts')}, "
            f"value={getattr(bundle, 'page_texts', None) is not None if hasattr(bundle, 'page_texts') else 'N/A'}"
        )
        if hasattr(bundle, 'page_texts') and bundle.page_texts:
            # Store page_texts temporarily on analysis object for typology resolver
            analysis._document_bundle_page_texts = bundle.page_texts
            logger.bind(project_id=project_id).error(
                f"PHASE1 TYPOLOGY: ✅ Attached {len(bundle.page_texts)} pages of text to analysis for typology resolver"
            )
            logger.bind(project_id=project_id).error(
                f"PHASE1 TYPOLOGY: Total chars in page_texts: {sum(len(t) for t in bundle.page_texts if t)}"
            )
        else:
            logger.bind(project_id=project_id).error(
                f"PHASE1 TYPOLOGY: ❌ Cannot attach page_texts - hasattr={hasattr(bundle, 'page_texts')}, "
                f"page_texts={bundle.page_texts if hasattr(bundle, 'page_texts') else 'N/A'}"
            )
        
        metrics_collector.start_stage("stage_1_5_typology_resolution", pages_sent=0)
        # CRITICAL: Pass page_texts to typology resolver for final text-based override
        page_texts_for_resolver = bundle.page_texts if hasattr(bundle, 'page_texts') and bundle.page_texts else None
        logger.bind(project_id=project_id).error(
            f"PHASE1 TYPOLOGY: Passing page_texts to resolver - has_texts={page_texts_for_resolver is not None}, "
            f"length={len(page_texts_for_resolver) if page_texts_for_resolver else 0}"
        )
        analysis = self.run_stage_1_5_typology_resolution(project_id, analysis, page_texts=page_texts_for_resolver)
        
        # Clean up temporary attribute
        if hasattr(analysis, '_document_bundle_page_texts'):
            delattr(analysis, '_document_bundle_page_texts')
        # Save updated analysis with site_context (Task 3)
        if analysis:
            analysis_file = output_dir / "document_analysis.json"
            analysis_file.parent.mkdir(parents=True, exist_ok=True)
            with open(analysis_file, "w") as f:
                f.write(analysis.model_dump_json(indent=2))
            logger.bind(project_id=project_id).info(f"Document analysis updated with site_context: {analysis_file}")
        metrics_collector.end_stage("stage_1_5_typology_resolution")

        # Stage 2: Adaptive extraction
        # Count pages sent (from page selector)
        from app.services.page_selector import select_pages_for_stage2
        stage2_pages_dict = select_pages_for_stage2(
            analysis,
            project_id=project_id,
            page_index=page_index,
            total_pages=bundle.page_count,
            settings=self.settings,
            trade_coverage=trade_coverage,
        )
        stage2_pages = len(set(
            stage2_pages_dict["scope_pages"]
            + stage2_pages_dict["quantity_pages"]
            + stage2_pages_dict["materials_pages"]
            + stage2_pages_dict["geometry_pages"]
        ))
        metrics_collector.start_stage("stage_2_adaptive_extraction", pages_sent=stage2_pages)
        
        # Stage 2: Adaptive extraction using routing
        output_dir = self._get_output_dir(project_id)
        extraction_file = output_dir / "extraction_result.json"
        expected_artifacts = {"extraction_result": str(extraction_file)}

        def _execute() -> ExtractionResult:
            return self._perform_extraction_with_routing(
                project_id=project_id,
                document_bundle=bundle,
                document_analysis=analysis,
                page_index=page_index,
                output_dir=output_dir,
            )

        extraction = self._execute_stage_with_state(
            project_id, "stage_2_adaptive_extraction", _execute, expected_artifacts
        )
        
        # If skipped and we have cached result, convert it back to ExtractionResult
        if extraction and isinstance(extraction, dict):
            extraction = ExtractionResult.model_validate(extraction)
        
        # D) Rescue rerun if extraction returned 0 items (generalized for all extractors)
        rescue_performed = False
        rescue_index_pages: list[int] = []
        rescue_notes = []
        if (
            len(extraction.scope_of_work) == 0
            and len(extraction.quantity_takeoff) == 0
            and len(extraction.material_specifications) == 0
        ):
            logger.bind(project_id=project_id).warning(
                "Empty extraction detected - triggering rescue rerun with expanded page selection"
            )
            # Use more aggressive selection: take top pages from index directly
            from app.services.page_selector import _select_index_pages_for_stage2
            if page_index:
                rescue_index_pages = _select_index_pages_for_stage2(
                    page_index, bundle.page_count, self.settings.rescue_stage2_max_pages
                )
                logger.bind(project_id=project_id).info(
                    f"Rescue rerun: selected {len(rescue_index_pages)} pages from index: {rescue_index_pages[:10]}..."
                )
                
                # Create a temporary analysis with rescue pages as where_scope_lives
                # This allows the extractor to use those pages (works for all extractor types)
                from app.schemas.document_analysis import ScopeLocator, QuantityLocator, MaterialLocator
                rescue_analysis = analysis.model_copy(deep=True)
                rescue_analysis.where_scope_lives = [
                    ScopeLocator(
                        page_number=p + 1,
                        location_type="unknown",
                        evidence="Rescue rerun from page_index",
                        confidence=0.8,
                    )
                    for p in rescue_index_pages
                ]
                rescue_analysis.where_quantities_live = [
                    QuantityLocator(
                        page_number=p + 1,
                        location_type="unknown",
                        evidence="Rescue rerun from page_index",
                        confidence=0.8,
                    )
                    for p in rescue_index_pages
                ]
                rescue_analysis.where_materials_live = [
                    MaterialLocator(
                        page_number=p + 1,
                        location_type="unknown",
                        evidence="Rescue rerun from page_index",
                        confidence=0.8,
                    )
                    for p in rescue_index_pages
                ]
                
                # Rerun extraction using the same routing mechanism (works for all extractors)
                try:
                    rescue_extraction = self._perform_extraction_with_routing(
                        project_id=project_id,
                        document_bundle=bundle,
                        document_analysis=rescue_analysis,
                        page_index=page_index,
                        output_dir=output_dir,
                    )
                    rescue_performed = True
                    rescue_notes.append(f"Rescue rerun used {len(rescue_index_pages)} pages from page_index")
                    
                    # Only use rescue result if it found items
                    if (
                        len(rescue_extraction.scope_of_work) > 0
                        or len(rescue_extraction.quantity_takeoff) > 0
                        or len(rescue_extraction.material_specifications) > 0
                    ):
                        logger.bind(project_id=project_id).info(
                            f"Rescue rerun succeeded: found {len(rescue_extraction.scope_of_work)} scope items, "
                            f"{len(rescue_extraction.quantity_takeoff)} quantities, "
                            f"{len(rescue_extraction.material_specifications)} materials"
                        )
                        extraction = rescue_extraction
                        rescue_notes.append(
                            f"Rescue rerun succeeded: {len(rescue_extraction.scope_of_work)} scope items, "
                            f"{len(rescue_extraction.quantity_takeoff)} quantities"
                        )
                        # Save updated extraction (already saved by _perform_extraction_with_routing)
                    else:
                        logger.bind(project_id=project_id).warning(
                            "Rescue rerun also returned empty - proceeding with original empty result"
                        )
                        rescue_notes.append("Rescue rerun also returned empty")
                except Exception as e:
                    logger.bind(project_id=project_id).error(
                        f"Rescue rerun failed with exception: {e}",
                        exc_info=True
                    )
                    rescue_notes.append(f"Rescue rerun failed: {str(e)}")
        
        # Post-extraction typology reroute based on coverage hints (Task 3)
        reroute_note = None
        coverage_report: CoverageScoreReport | None = None
        if trade_coverage:
            extraction, analysis, reroute_note = self._maybe_reroute_after_extraction(
                project_id=project_id,
                analysis=analysis,
                extraction=extraction,
                document_bundle=bundle,
                page_index=page_index,
                output_dir=output_dir,
                trade_coverage=trade_coverage,
            )
            if reroute_note:
                rescue_notes.append(reroute_note)
                analysis_file.write_text(analysis.model_dump_json(indent=2))

            try:
                coverage_report = evaluate_coverage_score(project_id, extraction, trade_coverage)
                coverage_file = output_dir / "coverage_score.json"
                coverage_file.write_text(coverage_report.model_dump_json(indent=2))
            except Exception as coverage_error:
                logger.bind(project_id=project_id).warning(
                    f"Failed to compute coverage score: {coverage_error}"
                )

            if coverage_report and coverage_report.coverage_score < 0.5:
                logger.bind(project_id=project_id).warning(
                    "Coverage score below threshold; triggering rescue sweep",
                    score=coverage_report.coverage_score,
                    missing=[m.trade for m in coverage_report.missing_trades],
                )
                additional_pages = self._select_rescue_pages_from_coverage(
                    coverage_report,
                    trade_coverage,
                    page_index=page_index,
                    document_analysis=analysis,
                )
                if additional_pages:
                    rescue_notes.append(
                        f"Coverage rescue added pages {sorted(additional_pages)}"
                    )
                    rescue_analysis = analysis.model_copy(deep=True)
                    from app.schemas.document_analysis import ScopeLocator

                    rescue_analysis.where_scope_lives.extend(
                        ScopeLocator(
                            sheet_id=None,
                            page_number=p + 1,
                            location_type="unknown",
                            evidence="Coverage rescue trade gap",
                            confidence=0.7,
                        )
                        for p in additional_pages
                    )
                    try:
                        extraction = self._perform_extraction_with_routing(
                            project_id=project_id,
                            document_bundle=bundle,
                            document_analysis=rescue_analysis,
                            page_index=page_index,
                            output_dir=output_dir,
                        )
                        analysis = rescue_analysis
                        reroute_note = (
                            reroute_note
                            or "post-coverage rescue rerun executed"
                        )
                    except Exception as rescue_exc:
                        logger.bind(project_id=project_id).warning(
                            f"Coverage rescue rerun failed: {rescue_exc}"
                        )

        # Add rescue metadata to extraction if rescue was performed or reroute happened
        if reroute_note and hasattr(extraction, "validation_metadata"):
            if extraction.validation_metadata is None:
                extraction.validation_metadata = {}
            extraction.validation_metadata.setdefault("post_extraction_notes", []).append(reroute_note)
            extraction_file = output_dir / "extraction_result.json"
            _persist_extraction_with_merge(extraction_file, extraction, project_id)

        if rescue_performed and hasattr(extraction, "validation_metadata"):
            if extraction.validation_metadata is None:
                extraction.validation_metadata = {}
            extraction.validation_metadata["rescue_performed"] = rescue_performed
            extraction.validation_metadata["rescue_notes"] = rescue_notes
            # Save updated extraction with rescue metadata
            extraction_file = output_dir / "extraction_result.json"
            _persist_extraction_with_merge(extraction_file, extraction, project_id)
        # Persist selected pages debug artifact
        try:
            import json

            selected_pages_debug = {
                "total_pages": bundle.page_count,
                "stage05_indexed_pages_count": len(page_index.pages) if getattr(page_index, "pages", None) else 0,
                "stage1_selected_pages": [],
                "stage2_selected_pages": [],
                "rescue_stage2_selected_pages": [],
            }

            page_index_lookup: dict[int, dict[str, list[str] | float]] = {}
            if page_index and hasattr(page_index, "pages"):
                for item in page_index.pages:
                    page_index_lookup[item.page_number] = {
                        "page_types": list(item.page_types),
                        "indicators": list(item.indicators),
                        "confidence": item.confidence,
                    }

            def _get_page_index_labels(page_number: int):
                info = page_index_lookup.get(page_number)
                if not info:
                    return None
                return {
                    "page_types": info.get("page_types", []),
                    "indicators": info.get("indicators", []),
                    "confidence": info.get("confidence"),
                }

            for idx in stage1_selected_indices:
                page_number = idx + 1
                info = page_index_lookup.get(page_number, {})
                page_types = info.get("page_types") or []
                indicators = info.get("indicators") or []
                reason_parts = []
                if page_types:
                    reason_parts.append(f"types: {', '.join(page_types[:3])}")
                if indicators:
                    reason_parts.append(f"indicators: {', '.join(indicators[:3])}")
                if reason_parts:
                    reason = "index: " + "; ".join(reason_parts)
                else:
                    reason = "heuristic: stratified"
                selected_pages_debug["stage1_selected_pages"].append(
                    {
                        "page_number": page_number,
                        "page_index_labels": _get_page_index_labels(page_number),
                        "reason": reason,
                    }
                )

            stage2_reason_map: dict[int, set[str]] = {}
            for key, label in (
                ("scope_pages", "scope"),
                ("quantity_pages", "quantities"),
                ("materials_pages", "materials"),
                ("geometry_pages", "geometry"),
            ):
                for idx in stage2_pages_dict.get(key, []):
                    page_number = idx + 1
                    stage2_reason_map.setdefault(page_number, set()).add(label)

            for page_number in sorted(stage2_reason_map.keys()):
                info = page_index_lookup.get(page_number, {})
                label_map = {
                    "scope": "stage1: where_scope_lives",
                    "quantities": "stage1: where_quantities_live",
                    "materials": "stage1: where_materials_live",
                    "geometry": "stage1: sheets",
                }
                reason_labels = [label_map.get(tag, tag) for tag in sorted(stage2_reason_map[page_number])]
                reason = "stage2: " + ", ".join(reason_labels)
                selected_pages_debug["stage2_selected_pages"].append(
                    {
                        "page_number": page_number,
                        "page_index_labels": _get_page_index_labels(page_number),
                        "reason": reason,
                    }
                )

            if rescue_index_pages:
                for idx in rescue_index_pages:
                    page_number = idx + 1
                    selected_pages_debug["rescue_stage2_selected_pages"].append(
                        {
                            "page_number": page_number,
                            "page_index_labels": _get_page_index_labels(page_number),
                            "reason": "rescue: high-signal page_index",
                        }
                    )

            debug_file = output_dir / "selected_pages_debug.json"
            debug_file.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_file, "w") as f:
                json.dump(selected_pages_debug, f, indent=2)
            logger.bind(project_id=project_id).info(
                f"Selected pages debug artifact saved to {debug_file}"
            )
        except Exception as e:
            logger.bind(project_id=project_id).warning(
                f"Failed to write selected_pages_debug.json: {e}"
            )

        # Record tokens (from extractor)
        if self.row_house_extractor and self.row_house_extractor.openai_client:
            usage = self.row_house_extractor.openai_client.get_last_usage()
            if usage:
                metrics_collector.record_tokens(
                    "stage_2_adaptive_extraction",
                    usage["prompt_tokens"],
                    usage["completion_tokens"],
                )
        metrics_collector.end_stage("stage_2_adaptive_extraction")

        # Stage 2.5A: Dimension authority resolution
        metrics_collector.start_stage("stage_2_5a_dimension_authority", pages_sent=0)
        extraction = self.run_stage_2_5a_dimension_authority(
            project_id, analysis, extraction
        )
        metrics_collector.end_stage("stage_2_5a_dimension_authority")

        # Stage 2.5: Validation gates + auto re-read
        metrics_collector.start_stage("stage_2_5_validation_gates", pages_sent=0)
        validation_result = self.run_stage_2_5_validation_gates(
            project_id, analysis, extraction, page_index, bundle
        )
        # Handle tuple or single value return
        if isinstance(validation_result, tuple) and len(validation_result) == 2:
            extraction, validation_report = validation_result
        elif isinstance(validation_result, tuple):
            # Unexpected tuple length
            extraction = validation_result[0] if len(validation_result) > 0 else extraction
            validation_report = validation_result[1] if len(validation_result) > 1 else None
        else:
            extraction = validation_result if validation_result is not None else extraction
            validation_report = None
        # Check if recovery was performed and count pages
        if validation_report and validation_report.rerun_performed:
            # Estimate recovery pages from rerun_notes
            import re
            recovery_pages = 0
            for note in validation_report.rerun_notes:
                page_matches = re.findall(r'(\d+)\s*pages?', note.lower())
                if page_matches:
                    recovery_pages = max(recovery_pages, int(page_matches[0]))
            if recovery_pages > 0:
                metrics_collector.start_stage("stage_2_5_recovery", pages_sent=recovery_pages)
                # Record tokens if available (from recovery)
                if self.row_house_extractor and self.row_house_extractor.openai_client:
                    usage = self.row_house_extractor.openai_client.get_last_usage()
                    if usage:
                        metrics_collector.record_tokens(
                            "stage_2_5_recovery",
                            usage["prompt_tokens"],
                            usage["completion_tokens"],
                        )
                metrics_collector.end_stage("stage_2_5_recovery")
        metrics_collector.end_stage("stage_2_5_validation_gates")

        # Save extraction result after validation gates to ensure authoritative dimensions persist
        # (validation gates might modify extraction, so we save after it completes)
        try:
            extraction_file = output_dir / "extraction_result.json"
            _persist_extraction_with_merge(extraction_file, extraction, project_id)
        except Exception as e:
            logger.bind(project_id=project_id).error(
                f"Failed to save extraction result after validation gates: {e}",
                exc_info=True
            )

        # Stage 3: Validation (legacy stub)
        metrics_collector.start_stage("stage_3_validation", pages_sent=0)
        validation = self.run_stage_3_validation(
            project_id, bundle, analysis, extraction
        )
        metrics_collector.end_stage("stage_3_validation")

        # Stage 3: 3D Model Generation (always run, validation errors are warnings only)
        model_3d = None
        metrics_collector.start_stage("stage_3_model_generation", pages_sent=0)
        model_3d = self.run_stage_3_model_generation(project_id, extraction)
        metrics_collector.end_stage("stage_3_model_generation")

        # Stage 4: Costing (always run, validation errors are warnings only)
        costing_result = None
        bid_proposal = None
        # Always run costing stage regardless of validation status
        if True:
            metrics_collector.start_stage("stage_4_costing", pages_sent=0)
            # Load pricing profile before costing (Phase 10.10B)
            pricing_profile_obj = None
            try:
                pricing_profile_file = output_dir / "pricing_profile.json"
                if pricing_profile_file.exists():
                    import json
                    with open(pricing_profile_file, "r") as f:
                        profile_data = json.load(f)
                    from app.schemas.pricing_profile import PricingProfile
                    pricing_profile_obj = PricingProfile.model_validate(profile_data)
            except Exception as e:
                logger.bind(project_id=project_id).debug(f"Could not load pricing profile for costing: {e}")
            
            costing_result = self.run_stage_4_costing(project_id, extraction, model_3d, pricing_profile_obj)
            metrics_collector.end_stage("stage_4_costing")
            
            # Generate bid proposal after costing (Phase 4.6)
            if costing_result:
                from app.services.bid_proposal_generator import generate_bid_proposal
                
                bid_proposal = generate_bid_proposal(
                    project_id=project_id,
                    extraction=extraction,
                    costing=costing_result,
                    validation=validation_report,
                    estimate_mode="conceptual",  # Default to conceptual, can be made configurable
                )
                
                # Save bid proposal
                bid_file = output_dir / "bid_proposal.json"
                bid_file.parent.mkdir(parents=True, exist_ok=True)
                with open(bid_file, "w") as f:
                    f.write(bid_proposal.model_dump_json(indent=2))
                logger.bind(project_id=project_id).info(f"Bid proposal saved to {bid_file}")
                
                # Generate evidence index (Phase 6.7)
                evidence_index = None
                try:
                    from app.services.evidence_indexer import generate_evidence_index, save_evidence_index
                    evidence_index = generate_evidence_index(project_id, output_dir)
                    save_evidence_index(project_id, evidence_index, output_dir)
                    logger.bind(project_id=project_id).info("Evidence index generated and saved")
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate evidence index: {e}")

                # Generate trade assemblies (Phase 9.2) - after bid_proposal and evidence_index
                trade_assemblies = None
                try:
                    from app.services.trade_assembly_generator import generate_trade_assemblies
                    from app.schemas.evidence_index import EvidenceIndex
                    import json

                    # Determine ruleset based on project type
                    # Use 'analysis' variable which is in scope (from Stage 1)
                    project_type = (
                        analysis.resolved_project_type or analysis.project_type
                        if analysis
                        else "row_house"
                    )
                    ruleset = "row_house_repair.yml"  # Default for now
                    # TODO: Add more rulesets as they're created (e.g., "institutional_repair.yml")
                    
                    # Load evidence_index if not already in memory
                    evidence_index_obj = evidence_index
                    if evidence_index_obj is None:
                        evidence_index_file = output_dir / "evidence_index.json"
                        if evidence_index_file.exists():
                            try:
                                with open(evidence_index_file, "r") as f:
                                    evidence_index_dict = json.load(f)
                                from app.schemas.evidence_index import EvidenceIndex
                                evidence_index_obj = EvidenceIndex.model_validate(evidence_index_dict)
                            except Exception as e:
                                logger.bind(project_id=project_id).debug(
                                    f"Could not load evidence_index.json: {e}, continuing without it"
                                )
                                evidence_index_obj = None
                    
                    # Reuse existing trade assemblies if present and valid
                    trade_assemblies_file = output_dir / "trade_assemblies.json"
                    if trade_assemblies_file.exists():
                        try:
                            with open(trade_assemblies_file, "r") as f:
                                trade_assemblies_data = json.load(f)
                            from app.schemas.trade_assemblies import TradeAssembliesResult

                            trade_assemblies = TradeAssembliesResult.model_validate(trade_assemblies_data)
                            logger.bind(
                                project_id=project_id,
                                assemblies=len(trade_assemblies.assemblies),
                            ).info("Reusing existing trade assemblies artifact")
                        except Exception as e:
                            logger.bind(project_id=project_id).warning(
                                f"Existing trade_assemblies.json invalid; regenerating: {e}"
                            )
                            trade_assemblies = None

                    if trade_assemblies is None:
                        # Generate trade assemblies (can work without evidence_index - just won't have evidence refs)
                        trade_assemblies = generate_trade_assemblies(
                            project_id=project_id,
                            bid_proposal=bid_proposal,
                            evidence_index=evidence_index_obj,  # Can work without evidence_index - generator handles it
                            ruleset=ruleset,
                            settings=self.settings,
                        )

                        # Save trade assemblies artifact
                        trade_assemblies_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(trade_assemblies_file, "w") as f:
                            f.write(trade_assemblies.model_dump_json(indent=2))
                        logger.bind(project_id=project_id).info(
                            f"Trade assemblies saved to {trade_assemblies_file} "
                            f"({len(trade_assemblies.assemblies)} assemblies)"
                        )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate trade assemblies: {e}")

                # Generate general conditions (Phase 10.1) - after bid_proposal, model_3d, and region resolution
                try:
                    from app.services.general_conditions_estimator import estimate_general_conditions
                    import json

                    # Determine building type
                    # Use 'analysis' variable which is in scope (from Stage 1)
                    building_type = (
                        analysis.resolved_project_type or analysis.project_type
                        if analysis
                        else "row_house"
                    )
                    
                    # Load model_3d if not already in memory
                    model_3d_obj = model_3d
                    if model_3d_obj is None:
                        model_3d_file = output_dir / "model_3d.json"
                        if model_3d_file.exists():
                            with open(model_3d_file, "r") as f:
                                model_3d_dict = json.load(f)
                            from app.schemas.model_3d import Model3D
                            model_3d_obj = Model3D.model_validate(model_3d_dict)
                    
                    # Get region resolution (from expanded_scope if available, else resolve)
                    region_resolution = None
                    try:
                        expanded_scope_file = output_dir / "expanded_scope.json"
                        if expanded_scope_file.exists():
                            with open(expanded_scope_file, "r") as f:
                                expanded_scope_data = json.load(f)
                            region_resolution = expanded_scope_data.get("region_resolution")
                    except Exception:
                        pass
                    
                    # If no region resolution, resolve it
                    if region_resolution is None:
                        from app.services.region_resolver import resolve_region
                        document_analysis_dict = (
                            analysis.model_dump() if hasattr(analysis, "model_dump") else None
                        )
                        extraction_result_dict = None
                        extraction_file = output_dir / "extraction_result.json"
                        if extraction_file.exists():
                            with open(extraction_file, "r") as f:
                                extraction_result_dict = json.load(f)
                        region_resolution = resolve_region(document_analysis_dict, extraction_result_dict)
                    
                    # Generate general conditions (Task 7: duration-based for roofing projects)
                    # Load extraction_result for roof area if available
                    extraction_result_for_gc = None
                    try:
                        extraction_file = output_dir / "extraction_result.json"
                        if extraction_file.exists():
                            import json
                            with open(extraction_file, "r") as f:
                                extraction_result_for_gc = json.load(f)
                    except Exception as e:
                        logger.bind(project_id=project_id).debug(f"Could not load extraction_result for GC duration estimation: {e}")
                    
                    general_conditions = None
                    if general_conditions_file.exists():
                        try:
                            with open(general_conditions_file, "r") as f:
                                general_conditions_data = json.load(f)
                            from app.schemas.general_conditions import GeneralConditions as GeneralConditionsSchema

                            general_conditions = GeneralConditionsSchema.model_validate(general_conditions_data)
                            logger.bind(
                                project_id=project_id,
                                items=len(general_conditions.items),
                                total_cost=general_conditions.total_cost,
                            ).info("Reusing existing general_conditions artifact")
                        except Exception as e:
                            logger.bind(project_id=project_id).warning(
                                f"Existing general_conditions.json invalid; regenerating: {e}"
                            )
                            general_conditions = None

                    if general_conditions is None:
                        general_conditions = estimate_general_conditions(
                            project_id=project_id,
                            building_type=building_type,
                            bid_proposal=bid_proposal,
                            model_3d=model_3d_obj,
                            document_analysis=analysis.model_dump() if hasattr(analysis, "model_dump") else None,
                            extraction_result=extraction_result_for_gc,
                            region_resolution=region_resolution,
                            settings=self.settings,
                        )

                        # Save general conditions artifact
                        general_conditions_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(general_conditions_file, "w") as f:
                            f.write(general_conditions.model_dump_json(indent=2))
                        logger.bind(project_id=project_id).info(
                            f"General conditions saved to {general_conditions_file} "
                            f"(${general_conditions.total_cost:,.2f} total, {len(general_conditions.items)} items)"
                        )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate general conditions: {e}")

                # Generate construction systems (Phase 14.1) - after bid_proposal, model_3d, and evidence_index
                try:
                    from app.services.assembly_builder import build_construction_systems
                    import json

                    # Load model_3d if not already in memory
                    model_3d_obj = model_3d
                    if model_3d_obj is None:
                        model_3d_file = output_dir / "model_3d.json"
                        if model_3d_file.exists():
                            with open(model_3d_file, "r") as f:
                                model_3d_dict = json.load(f)
                            from app.schemas.model_3d import Model3D
                            model_3d_obj = Model3D.model_validate(model_3d_dict)

                    # Load evidence_index if not already in memory
                    evidence_index_obj = evidence_index
                    if evidence_index_obj is None:
                        evidence_index_file = output_dir / "evidence_index.json"
                        if evidence_index_file.exists():
                            try:
                                with open(evidence_index_file, "r") as f:
                                    evidence_index_dict = json.load(f)
                                from app.schemas.evidence_index import EvidenceIndex
                                evidence_index_obj = EvidenceIndex.model_validate(evidence_index_dict)
                            except Exception as e:
                                logger.bind(project_id=project_id).debug(
                                    f"Could not load evidence_index for construction systems: {e}, continuing without it"
                                )
                                evidence_index_obj = None

                    # Build construction systems
                    construction_systems = build_construction_systems(
                        project_id=project_id,
                        bid_proposal=bid_proposal,
                        model_3d=model_3d_obj,
                        evidence_index=evidence_index_obj,
                        settings=self.settings,
                    )

                    # Save construction systems artifact
                    systems_file = output_dir / "construction_systems.json"
                    systems_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(systems_file, "w") as f:
                        f.write(construction_systems.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).info(
                        f"Construction systems saved to {systems_file} "
                        f"({len(construction_systems.systems)} systems)"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate construction systems: {e}")

                # Generate labor breakdown (Phase 9.3B, 11.1) - after trade assemblies, before proposal sections
                # Phase 11.1: Enhanced with trade assemblies for explicit hours
                labor_breakdown_obj = None
                try:
                    from app.services.labor_synthesizer import generate_labor_breakdown
                    
                    # Load trade assemblies if available (Phase 11.1 - for explicit hours)
                    trade_assemblies_obj = None
                    try:
                        assemblies_file = output_dir / "trade_assemblies.json"
                        if assemblies_file.exists():
                            import json
                            with open(assemblies_file, "r") as f:
                                trade_assemblies_dict = json.load(f)
                            from app.schemas.trade_assemblies import TradeAssembliesResult
                            trade_assemblies_obj = TradeAssembliesResult.model_validate(trade_assemblies_dict)
                    except Exception:
                        pass  # Fall back to keyword-based approach
                    
                    # Get profile_id and region_resolution if available
                    profile_id_for_lb = profile_id
                    region_resolution_for_lb = region_resolution
                    
                    labor_breakdown_obj = generate_labor_breakdown(
                        project_id=project_id,
                        output_dir=output_dir,
                        settings=self.settings,
                        profile_id=profile_id_for_lb,
                        region_resolution=region_resolution_for_lb,
                        trade_assemblies=trade_assemblies_obj,  # Phase 11.1: Pass trade assemblies for explicit hours
                    )
                    # Save labor breakdown
                    labor_file = output_dir / "labor_breakdown.json"
                    labor_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(labor_file, "w") as f:
                        f.write(labor_breakdown_obj.model_dump_json(indent=2))
                    total_cost_str = (
                        f"total labor cost: ${labor_breakdown_obj.total_labor_cost:.2f}"
                        if labor_breakdown_obj.total_labor_cost
                        else "no labor costs calculated"
                    )
                    logger.bind(project_id=project_id).info(
                        f"Labor breakdown saved to {labor_file} "
                        f"({len(labor_breakdown_obj.activities)} activities, {total_cost_str})"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate labor breakdown: {e}")

                # Generate proposal sections (Phase 10.9A, 12.1) - after trade assemblies, general conditions, and labor breakdown
                try:
                    from app.services.proposal_sections_generator import generate_proposal_sections
                    proposal_sections = generate_proposal_sections(
                        project_id=project_id,
                        output_dir=output_dir,
                        settings=self.settings,
                    )
                    sections_file = output_dir / "proposal_sections.json"
                    sections_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(sections_file, "w") as f:
                        f.write(proposal_sections.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).info(
                        f"Proposal sections saved to {sections_file} "
                        f"({len(proposal_sections.scope_sections)} scope sections)"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate proposal sections: {e}")

                # Evaluate bid completeness (Phase 10.12A) - after proposal_sections
                try:
                    from app.services.bid_completeness import evaluate_bid_completeness
                    completeness = evaluate_bid_completeness(
                        project_id=project_id,
                        output_dir=output_dir,
                        proposal_sections=proposal_sections,
                        extraction_result=None,  # Will load internally
                        validation_report=validation_report,
                        bid_review=None,  # Will load later
                    )
                    # Save completeness artifact
                    completeness_file = output_dir / "bid_completeness.json"
                    completeness_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(completeness_file, "w") as f:
                        f.write(completeness.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).info(
                        f"Bid completeness evaluated: passed={completeness.passed}, "
                        f"score={completeness.score:.2f}, blockers={len(completeness.blockers)}"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to evaluate bid completeness: {e}")

                # Generate trade packages (Phase 11.0) - after proposal_sections
                try:
                    from app.services.trade_package_generator import generate_trade_packages
                    
                    # Load pricing profile for profile_id
                    pricing_profile_dict = None
                    try:
                        pricing_profile_file = output_dir / "pricing_profile.json"
                        if pricing_profile_file.exists():
                            import json
                            with open(pricing_profile_file, "r") as f:
                                pricing_profile_dict = json.load(f)
                    except Exception:
                        pass
                    
                    trade_packages = generate_trade_packages(
                        project_id=project_id,
                        output_dir=output_dir,
                        settings=self.settings,
                        bid_proposal=bid_proposal,
                        proposal_sections=proposal_sections,
                        evidence_index=None,  # Will load internally
                        detail_graph=None,  # Will load internally
                        pricing_profile=pricing_profile_dict,
                    )
                    # Save trade packages
                    packages_file = output_dir / "trade_packages.json"
                    packages_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(packages_file, "w") as f:
                        f.write(trade_packages.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).info(
                        f"Trade packages saved to {packages_file} "
                        f"({len(trade_packages.packages)} packages)"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate trade packages: {e}")

                # Generate trust report (Phase 10.13) - after all artifacts
                try:
                    from app.services.trust_report_generator import generate_trust_report
                    trust_report = generate_trust_report(
                        project_id=project_id,
                        output_dir=output_dir,
                        settings=self.settings,
                    )
                    # Save trust report
                    trust_file = output_dir / "trust_report.json"
                    trust_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(trust_file, "w") as f:
                        f.write(trust_report.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).info(
                        f"Trust report saved to {trust_file} "
                        f"(confidence: {trust_report.overall_confidence:.1f}%)"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate trust report: {e}")

                # Generate compliance case study (Ogdensburg narrative artifact)
                try:
                    case_study = generate_compliance_case_study(
                        project_id=project_id,
                        output_dir=output_dir,
                        settings=self.settings,
                    )
                    logger.bind(project_id=project_id).info(
                        "Compliance case study saved",
                        path=str((output_dir / "case_study.json")),
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(
                        f"Failed to generate compliance case study: {e}"
                    )

                # Resolve region (Phase 9.7)
                region_resolution = None
                document_analysis_dict = None
                extraction_result_dict = None
                try:
                    from app.services.region_resolver import resolve_region, select_profile_id
                    from app.schemas.expanded_scope import RegionResolution
                    
                    # Load document_analysis and extraction_result for region resolution
                    analysis_file = output_dir / "document_analysis.json"
                    if analysis_file.exists():
                        import json
                        with open(analysis_file, "r") as f:
                            document_analysis_dict = json.load(f)
                    
                    extraction_file = output_dir / "extraction_result.json"
                    if extraction_file.exists():
                        import json
                        with open(extraction_file, "r") as f:
                            extraction_result_dict = json.load(f)
                    
                    # Resolve region
                    region_result = resolve_region(document_analysis_dict, extraction_result_dict)
                    region_id = region_result["region_id"]
                    profile_id = select_profile_id(region_id, "row_house_masonry")
                    
                    # Create RegionResolution object
                    region_resolution = RegionResolution(
                        region_id=region_id,
                        confidence=region_result["confidence"],
                        evidence=region_result["evidence"],
                    )
                    
                    logger.bind(project_id=project_id).info(
                        f"Resolved region: {region_id} (confidence: {region_result['confidence']:.2f}), "
                        f"selected profile: {profile_id}"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to resolve region, using default: {e}")
                    profile_id = None  # Will use default from settings
                    region_result = None

                # Select and save pricing profile (Phase 10.10A)
                try:
                    from app.services.pricing_profile_service import select_profile, save_profile
                    pricing_profile = select_profile(
                        document_analysis=document_analysis_dict,
                        extraction_result=extraction_result_dict,
                        settings=self.settings,
                    )
                    save_profile(project_id, pricing_profile, output_dir)
                    logger.bind(project_id=project_id).info(
                        f"Selected pricing profile: {pricing_profile.profile_id} "
                        f"for region: {pricing_profile.region}"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to select/save pricing profile: {e}")

                # Generate pricing v2 (Phase 10.2) - after region resolution
                try:
                    from app.services.pricing_engine_v2 import compute_pricing_v2
                    from app.services.contractor_profile_store import load_profile
                    
                    # Try to load contractor profile if available
                    contractor_profile = None
                    if profile_id and settings:
                        try:
                            contractor_profile = load_profile(profile_id, settings)
                        except Exception as e:
                            logger.bind(project_id=project_id).debug(f"Profile {profile_id} not loaded for pricing v2: {e}")
                    
                    # Build region_resolution dict if available
                    region_resolution_dict = None
                    if region_result:
                        region_resolution_dict = region_result
                    elif region_resolution:
                        region_resolution_dict = {
                            "region_id": region_resolution.region_id,
                            "confidence": region_resolution.confidence,
                            "evidence": region_resolution.evidence,
                        }
                    
                    pricing_v2 = compute_pricing_v2(
                        bid_proposal=bid_proposal,
                        contractor_profile=contractor_profile,
                        region_resolution=region_resolution_dict,
                        settings=self.settings,
                    )
                    
                    # Save pricing v2
                    pricing_file = output_dir / "bid_pricing_v2.json"
                    pricing_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(pricing_file, "w") as f:
                        f.write(pricing_v2.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).info(
                        f"Pricing v2 saved to {pricing_file} "
                        f"({len(pricing_v2.line_items)} items, total=${pricing_v2.grand_total:.2f})"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate pricing v2: {e}")

                # Generate expanded scope (Phase 9.2B)
                try:
                    from app.services.scope_expander import generate_expanded_scope
                    expanded_scope = generate_expanded_scope(
                        project_id=project_id,
                        output_dir=output_dir,
                        settings=self.settings,
                        profile_id=profile_id,
                        region_resolution=region_resolution,
                    )
                    # Save expanded scope
                    expanded_scope_file = output_dir / "expanded_scope.json"
                    expanded_scope_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(expanded_scope_file, "w") as f:
                        f.write(expanded_scope.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).info(
                        f"Expanded scope saved to {expanded_scope_file} ({len(expanded_scope.items)} items)"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate expanded scope: {e}")

                # Generate proposal markdown (Phase 9.8)
                try:
                    from app.services.proposal_template_engine import render_contractor_proposal_markdown
                    proposal_markdown = render_contractor_proposal_markdown(
                        project_id=project_id,
                        output_dir=output_dir,
                        settings=self.settings,
                    )
                    # Save proposal markdown
                    markdown_file = output_dir / "proposal_markdown.md"
                    markdown_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(markdown_file, "w") as f:
                        f.write(proposal_markdown)
                    logger.bind(project_id=project_id).info(
                        f"Proposal markdown saved to {markdown_file} ({len(proposal_markdown)} characters)"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate proposal markdown: {e}")

                # Generate coverage declarations (Coverage & Warranty)
                try:
                    from app.services.coverage_declarations_generator import generate_coverage_declarations
                    import json

                    # Check if existing declarations exist
                    existing_declarations = None
                    declarations_file = output_dir / "coverage_declarations.json"
                    if declarations_file.exists():
                        try:
                            with open(declarations_file, "r") as f:
                                existing_declarations = json.load(f)
                        except Exception as e:
                            logger.bind(project_id=project_id).debug(
                                f"Could not load existing coverage declarations: {e}"
                            )

                    coverage_declarations = generate_coverage_declarations(
                        project_id=project_id, existing=existing_declarations
                    )

                    # Save coverage declarations
                    declarations_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(declarations_file, "w") as f:
                        f.write(coverage_declarations.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).info(
                        f"Coverage declarations saved to {declarations_file}"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate coverage declarations: {e}")

                # Generate work packages (Phase 9.9)
                try:
                    from app.services.work_package_normalizer import generate_work_packages
                    work_packages_file = generate_work_packages(
                        project_id=project_id,
                        output_dir=output_dir,
                        settings=self.settings,
                    )
                    logger.bind(project_id=project_id).info(
                        f"Work packages saved to {work_packages_file}"
                    )
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate work packages: {e}")

                # Generate evidence bbox index (Phase 8.6D)
                if evidence_index:
                    try:
                        from app.services.evidence_bbox_extractor import EvidenceBboxExtractor
                        import json
                        
                        bbox_extractor = EvidenceBboxExtractor(settings, storage_service)
                        bbox_index = bbox_extractor.generate(project_id, evidence_index)
                        
                        # Save bbox index
                        bbox_file = output_dir / "evidence_bbox_index.json"
                        bbox_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(bbox_file, "w") as f:
                            f.write(bbox_index.model_dump_json(indent=2))
                        logger.bind(project_id=project_id).info(
                            f"Evidence bbox index saved to {bbox_file} "
                            f"(match rate: {bbox_index.metrics.get('bbox_match_rate', 0):.1f}%)"
                        )
                    except Exception as e:
                        logger.bind(project_id=project_id).warning(f"Failed to generate evidence bbox index: {e}")

                # Generate detail overlay index (Phase 8.4)
                try:
                    from app.services.detail_overlay_indexer import DetailOverlayIndexer
                    import json
                    
                    # Load model_3d
                    model_3d_file = output_dir / "model_3d.json"
                    if model_3d_file.exists():
                        with open(model_3d_file, "r") as f:
                            model_3d_dict = json.load(f)
                        
                        # Load detail_graph from extraction_result
                        extraction_file = output_dir / "extraction_result.json"
                        detail_graph_dict = None
                        if extraction_file.exists():
                            with open(extraction_file, "r") as f:
                                extraction_dict = json.load(f)
                                detail_graph_dict = extraction_dict.get("detail_graph")
                        
                        # Load evidence_index
                        evidence_index_dict = None
                        if evidence_index:
                            evidence_index_dict = json.loads(evidence_index.model_dump_json())
                        
                        indexer = DetailOverlayIndexer()
                        overlay_index = indexer.generate(
                            project_id=project_id,
                            model_3d=model_3d_dict,
                            detail_graph=detail_graph_dict,
                            evidence_index=evidence_index_dict,
                        )
                        
                        # Save detail overlay index
                        overlay_file = output_dir / "detail_overlay_index.json"
                        overlay_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(overlay_file, "w") as f:
                            f.write(overlay_index.model_dump_json(indent=2))
                        logger.bind(project_id=project_id).info(f"Detail overlay index saved to {overlay_file}")
                    else:
                        logger.bind(project_id=project_id).warning("model_3d.json not found, skipping detail overlay index generation")
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate detail overlay index: {e}")

                # Generate bid review (Phase 8.2)
                try:
                    from app.services.bid_review_generator import BidReviewGenerator
                    import json
                    
                    # Load artifacts needed for review
                    bid_proposal_dict = json.loads(bid_proposal.model_dump_json())
                    costing_result_dict = json.loads(costing_result.model_dump_json())
                    validation_report_dict = None
                    if validation_report:
                        validation_report_dict = json.loads(validation_report.model_dump_json())
                    evidence_index_dict = None
                    if evidence_index:
                        evidence_index_dict = json.loads(evidence_index.model_dump_json())
                    
                    review_generator = BidReviewGenerator()
                    bid_review = review_generator.generate(
                        project_id=project_id,
                        bid_proposal=bid_proposal_dict,
                        costing_result=costing_result_dict,
                        validation_report=validation_report_dict,
                        evidence_index=evidence_index_dict,
                    )
                    
                    # Save bid review
                    review_file = output_dir / "bid_review.json"
                    review_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(review_file, "w") as f:
                        f.write(bid_review.model_dump_json(indent=2))
                    logger.bind(project_id=project_id).info(f"Bid review saved to {review_file}")

                    try:
                        export_path = create_bid_excel_export(
                            project_id=project_id,
                            output_dir=output_dir,
                            settings=self.settings,
                        )
                        logger.bind(project_id=project_id).info(
                            f"Bid Excel export generated at {export_path}"
                        )
                    except Exception as export_error:
                        logger.bind(project_id=project_id).warning(
                            f"Failed to generate bid Excel export: {export_error}"
                        )

                    # Generate zone cost map (Phase 8.3)
                    try:
                        from app.services.zone_cost_mapper import ZoneCostMapper
                        import json
                        
                        # Load model_3d
                        model_3d_file = output_dir / "model_3d.json"
                        if model_3d_file.exists():
                            with open(model_3d_file, "r") as f:
                                model_3d_dict = json.load(f)
                            
                            mapper = ZoneCostMapper()
                            zone_cost_map = mapper.generate(
                                project_id=project_id,
                                model_3d=model_3d_dict,
                                bid_review=json.loads(bid_review.model_dump_json()),
                                evidence_index=evidence_index_dict,
                            )
                            
                            # Save zone cost map
                            zone_map_file = output_dir / "zone_cost_map.json"
                            zone_map_file.parent.mkdir(parents=True, exist_ok=True)
                            with open(zone_map_file, "w") as f:
                                f.write(zone_cost_map.model_dump_json(indent=2))
                            logger.bind(project_id=project_id).info(f"Zone cost map saved to {zone_map_file}")
                        else:
                            logger.bind(project_id=project_id).warning("model_3d.json not found, skipping zone cost map generation")
                    except Exception as e:
                        logger.bind(project_id=project_id).warning(f"Failed to generate zone cost map: {e}")

                    # Generate work package map (Task 1) - after zone_cost_map
                    try:
                        from app.services.work_package_mapper import map_work_packages
                        import json

                        # Load bid_proposal if needed
                        bid_proposal_dict = None
                        bid_proposal_file = output_dir / "bid_proposal.json"
                        if bid_proposal_file.exists():
                            with open(bid_proposal_file, "r") as f:
                                bid_proposal_dict = json.load(f)

                        # Load model_3d (always load from file for consistency)
                        model_3d_dict_for_packages = None
                        model_3d_file = output_dir / "model_3d.json"
                        if model_3d_file.exists():
                            with open(model_3d_file, "r") as f:
                                model_3d_dict_for_packages = json.load(f)

                        # Load zone_cost_map if it exists (from file)
                        zone_cost_map_dict = None
                        zone_cost_map_file = output_dir / "zone_cost_map.json"
                        if zone_cost_map_file.exists():
                            try:
                                with open(zone_cost_map_file, "r") as f:
                                    zone_cost_map_dict = json.load(f)
                            except Exception as e:
                                logger.bind(project_id=project_id).debug(
                                    f"Could not load zone_cost_map for work packages: {e}"
                                )

                        # Load evidence_index if not already loaded
                        evidence_index_dict_for_packages = evidence_index_dict if "evidence_index_dict" in locals() else None
                        if not evidence_index_dict_for_packages:
                            evidence_index_file = output_dir / "evidence_index.json"
                            if evidence_index_file.exists():
                                try:
                                    with open(evidence_index_file, "r") as f:
                                        evidence_index_dict_for_packages = json.load(f)
                                except Exception as e:
                                    logger.bind(project_id=project_id).debug(
                                        f"Could not load evidence_index for work packages: {e}"
                                    )

                        if bid_proposal_dict and model_3d_dict_for_packages:
                            # Allow empty zone_cost_map and evidence_index
                            work_package_map = map_work_packages(
                                project_id=project_id,
                                bid_proposal=bid_proposal_dict,
                                model_3d=model_3d_dict_for_packages,
                                zone_cost_map=zone_cost_map_dict or {},
                                evidence_index=evidence_index_dict_for_packages or {},
                                settings=self.settings,
                            )

                            # Save work package map
                            packages_file = output_dir / "work_package_map.json"
                            packages_file.parent.mkdir(parents=True, exist_ok=True)
                            with open(packages_file, "w") as f:
                                f.write(work_package_map.model_dump_json(indent=2))
                            logger.bind(project_id=project_id).info(
                                f"Work package map saved to {packages_file} "
                                f"({len(work_package_map.packages)} packages)"
                            )
                        else:
                            logger.bind(project_id=project_id).warning(
                                f"Missing prerequisites for work packages: "
                                f"bid_proposal={bid_proposal_dict is not None}, "
                                f"model_3d={model_3d_dict_for_packages is not None}"
                            )
                    except Exception as e:
                        logger.bind(project_id=project_id).warning(f"Failed to generate work package map: {e}")
                        import traceback
                        logger.bind(project_id=project_id).debug(traceback.format_exc())
                except Exception as e:
                    logger.bind(project_id=project_id).warning(f"Failed to generate bid review: {e}")
        # Costing stage always runs (removed skip logic)

        # Calculate quality metrics
        # Critical coverage score
        scope_items_lower = [item.item.lower() for item in extraction.scope_of_work]
        found = {
            "parapet": any("parapet" in item for item in scope_items_lower),
            "lintel": any("lintel" in item for item in scope_items_lower),
            "flashing": any("flash" in item for item in scope_items_lower),
            "brick_or_repoint": any("brick" in item or "repoint" in item for item in scope_items_lower),
            "crack_repair": any("crack" in item or "stabil" in item or "epoxy" in item for item in scope_items_lower),
        }
        found_count = sum(found.values())
        total = 5
        critical_coverage_score = found_count / total if total > 0 else 0.0

        # Dimension confidence
        dimension_confidence = 0.0
        if extraction.authoritative_dimensions:
            dimension_confidence = extraction.authoritative_dimensions.confidence

        # Validation score
        validation_score = validation_report.score if validation_report else 0.0

        metrics_collector.set_quality_metrics(
            critical_coverage_score=critical_coverage_score,
            dimension_confidence=dimension_confidence,
            validation_score=validation_score,
        )

        # Aggregate cache stats from all OpenAI clients used in pipeline
        all_cache_stats: dict[str, Any] = {
            "cache_hits_total": 0,
            "cache_misses_total": 0,
            "cache_hits_by_stage": {},
            "cache_misses_by_stage": {},
        }
        
        # Collect cache stats from all clients
        clients_to_check = []
        if self.document_analyzer and self.document_analyzer.openai_client:
            clients_to_check.append(("document_analyzer", self.document_analyzer.openai_client))
        if self.page_indexer and self.page_indexer.openai_client:
            clients_to_check.append(("page_indexer", self.page_indexer.openai_client))
        if self.row_house_extractor and self.row_house_extractor.openai_client:
            clients_to_check.append(("row_house_extractor", self.row_house_extractor.openai_client))
        if self.institutional_room_extractor and self.institutional_room_extractor.openai_client:
            clients_to_check.append(("institutional_room_extractor", self.institutional_room_extractor.openai_client))
        if self.structural_notes_extractor and self.structural_notes_extractor.openai_client:
            clients_to_check.append(("structural_notes_extractor", self.structural_notes_extractor.openai_client))
        
        for client_name, client in clients_to_check:
            try:
                client_stats = client.get_cache_stats()
                if client_stats:
                    all_cache_stats["cache_hits_total"] += client_stats.get("cache_hits_total", 0)
                    all_cache_stats["cache_misses_total"] += client_stats.get("cache_misses_total", 0)
                    
                    # Merge stage-level stats
                    for stage, hits in client_stats.get("cache_hits_by_stage", {}).items():
                        all_cache_stats["cache_hits_by_stage"][stage] = (
                            all_cache_stats["cache_hits_by_stage"].get(stage, 0) + hits
                        )
                    for stage, misses in client_stats.get("cache_misses_by_stage", {}).items():
                        all_cache_stats["cache_misses_by_stage"][stage] = (
                            all_cache_stats["cache_misses_by_stage"].get(stage, 0) + misses
                        )
            except Exception as e:
                logger.warning(f"Failed to get cache stats from {client_name}: {e}")
        
        # Calculate hit rate
        total_requests = all_cache_stats["cache_hits_total"] + all_cache_stats["cache_misses_total"]
        if total_requests > 0:
            all_cache_stats["cache_hit_rate"] = (
                all_cache_stats["cache_hits_total"] / total_requests * 100
            )
        else:
            all_cache_stats["cache_hit_rate"] = 0.0
        
        # Set cache stats in metrics collector
        metrics_collector.set_cache_stats(all_cache_stats)

        # Finalize and save metrics
        metrics = metrics_collector.finalize()
        metrics_collector.save(output_dir)

        result = ProjectResult(
            project_id=project_id,
            page_count=bundle.page_count,
            status="completed" if (validation_report and validation_report.passed) else "validation_failed",
            document_bundle=bundle,
            document_analysis=analysis,
            extraction=extraction,  # ExtractionResult is compatible
            validation=validation,
            model_3d=model_3d,
            costing_result=costing_result,
            validation_report=validation_report,
            bid_proposal=bid_proposal,
        )

        logger.bind(project_id=project_id).info("Pipeline completed successfully")

        return result

