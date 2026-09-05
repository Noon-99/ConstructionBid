"""Acceptance harness for key trade PDFs (roof, windows, paving).

This runner executes the full pipeline on curated sample PDFs and asserts that
fundamental evidence, coverage, and costing behaviours remain stable.  It
produces per-case summaries so regressions can be diagnosed without manually
inspecting the UI.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from loguru import logger

from app.analyzers.document_analyzer import DocumentAnalyzer
from app.analyzers.institutional_room_extractor import InstitutionalRoomExtractor
from app.analyzers.row_house_repair_extractor import RowHouseRepairExtractor
from app.analyzers.structural_notes_extractor import StructuralNotesExtractor
from app.core.config import Settings, get_settings
from app.core.ids import generate_project_id
from app.core.logging import configure_logging
from app.costing.cost_engine import CostEngine
from app.generators.model_3d_generator import Model3DGenerator
from app.schemas.coverage_score import CoverageScoreReport
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.schemas.page_index import PageIndex
from app.schemas.trade_coverage import TradeCoverageResult
from app.services.coverage_evaluator import evaluate_coverage_score
from app.services.document_processor import DocumentProcessor
from app.services.openai_client import OpenAIClient
from app.services.page_indexer import PageIndexer
from app.services.pipeline import PipelineOrchestrator
from app.services.storage import StorageService
from app.services.trade_coverage_analyzer import analyze_trade_coverage

ACCEPTANCE_ROOT = Path(__file__).resolve().parent
DEFAULT_CASE_DEFINITIONS = ACCEPTANCE_ROOT / "case_definitions.json"
DEFAULT_OUTPUT_DIR = ACCEPTANCE_ROOT / "out"


@dataclass
class AnchorDefinition:
    """Expectation for a quantity anchor tied to evidence."""

    label: str
    match_item_contains: list[str]
    min_quantity: float = 0.0
    unit: str | None = None
    allow_heuristic: bool = False
    require_evidence: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnchorDefinition":
        return cls(
            label=data["label"],
            match_item_contains=[term.lower() for term in data.get("match_item_contains", [])],
            min_quantity=float(data.get("min_quantity", 0.0)),
            unit=(data.get("unit") or None),
            allow_heuristic=bool(data.get("allow_heuristic", False)),
            require_evidence=bool(data.get("require_evidence", False)),
        )


@dataclass
class AnchorResult:
    label: str
    passed: bool
    message: str
    quantity: float | None = None
    unit: str | None = None
    source_item: str | None = None
    evidence_snippet: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "passed": self.passed,
            "message": self.message,
            "quantity": self.quantity,
            "unit": self.unit,
            "source_item": self.source_item,
            "evidence_snippet": self.evidence_snippet,
        }


@dataclass
class CaseSummary:
    name: str
    project_id: str
    passed: bool
    errors: list[str]
    warnings: list[str]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "case": self.name,
            "project_id": self.project_id,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


def load_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load JSON", path=str(path), error=str(exc))
        return None


def build_pipeline(settings: Settings) -> tuple[PipelineOrchestrator, DocumentProcessor]:
    """Construct a fresh pipeline orchestrator with all dependencies."""

    openai_client = OpenAIClient(settings)
    document_analyzer = DocumentAnalyzer(settings, openai_client)
    row_house_extractor = RowHouseRepairExtractor(settings, openai_client)
    institutional_room_extractor = InstitutionalRoomExtractor(settings, openai_client)
    structural_notes_extractor = StructuralNotesExtractor(settings, openai_client)
    model_3d_generator = Model3DGenerator()
    cost_engine = CostEngine()
    page_indexer = PageIndexer(settings, openai_client)

    pipeline = PipelineOrchestrator(
        document_analyzer=document_analyzer,
        row_house_extractor=row_house_extractor,
        institutional_room_extractor=institutional_room_extractor,
        structural_notes_extractor=structural_notes_extractor,
        model_3d_generator=model_3d_generator,
        cost_engine=cost_engine,
        page_indexer=page_indexer,
        settings=settings,
    )

    storage_service = StorageService(settings)
    document_processor = DocumentProcessor(settings, storage_service)

    return pipeline, document_processor


def evaluate_scope_keywords(extraction: ExtractionResult, keywords: Iterable[str]) -> list[str]:
    lower_keywords = {kw.lower() for kw in keywords}
    found: set[str] = set()

    for scope_item in extraction.scope_of_work:
        haystack = f"{scope_item.item} {scope_item.description}".lower()
        for keyword in lower_keywords:
            if keyword in haystack:
                found.add(keyword)

    missing = sorted(lower_keywords - found)
    return missing


def evaluate_anchors(extraction: ExtractionResult, definitions: list[AnchorDefinition]) -> tuple[list[AnchorResult], list[str]]:
    results: list[AnchorResult] = []
    errors: list[str] = []

    for definition in definitions:
        result = evaluate_single_anchor(extraction, definition)
        results.append(result)
        if not result.passed:
            errors.append(f"Anchor '{definition.label}' failed: {result.message}")
    return results, errors


def evaluate_single_anchor(extraction: ExtractionResult, definition: AnchorDefinition) -> AnchorResult:
    candidates = []
    for qty in extraction.quantity_takeoff:
        item_text = (qty.item or "").lower()
        if not any(term in item_text for term in definition.match_item_contains):
            continue
        candidates.append(qty)

    if not candidates:
        return AnchorResult(
            label=definition.label,
            passed=False,
            message="No quantity_takeoff entries matched required keywords",
        )

    failure_reasons: list[str] = []
    for qty in candidates:
        unit_ok = True
        if definition.unit:
            unit_ok = qty.unit and qty.unit.lower() == definition.unit.lower()
            if not unit_ok:
                failure_reasons.append(
                    f"Quantity for '{qty.item}' has unit '{qty.unit}' but expected '{definition.unit}'"
                )
                continue

        if qty.quantity is None or qty.quantity < definition.min_quantity:
            failure_reasons.append(
                f"Quantity for '{qty.item}' below minimum ({qty.quantity} < {definition.min_quantity})"
            )
            continue

        if definition.require_evidence and qty.evidence_missing:
            failure_reasons.append(
                f"Quantity for '{qty.item}' missing evidence snippet"
            )
            continue

        if not definition.allow_heuristic and qty.evidence_missing:
            failure_reasons.append(
                f"Quantity for '{qty.item}' is heuristic-only (evidence missing)"
            )
            continue

        return AnchorResult(
            label=definition.label,
            passed=True,
            message="anchor_satisfied",
            quantity=qty.quantity,
            unit=qty.unit,
            source_item=qty.item,
            evidence_snippet=qty.evidence_snippet,
        )

    return AnchorResult(
        label=definition.label,
        passed=False,
        message="; ".join(failure_reasons) if failure_reasons else "Anchor conditions not satisfied",
    )


def compute_heuristic_fraction(costing_payload: dict[str, Any] | None) -> tuple[float, float, float]:
    if not costing_payload:
        return 0.0, 0.0, 0.0

    total_cost = float(costing_payload.get("total_cost") or 0.0)
    heuristic_total = 0.0

    for category in costing_payload.get("breakdown_by_category", []):
        for item in category.get("items", []):
            subtotal = float(item.get("subtotal") or 0.0)
            total_cost = max(total_cost, subtotal + 0.0) if total_cost == 0.0 else total_cost
            if (item.get("quantity_source") or "").lower() in {"heuristic", "assumed"}:
                heuristic_total += subtotal

    fraction = heuristic_total / total_cost if total_cost > 0 else 0.0
    return heuristic_total, total_cost, fraction


def load_selected_pages(output_dir: Path) -> dict[str, list[int]]:
    data = load_json_if_exists(output_dir / "selected_pages_debug.json") or {}
    stage1 = [entry.get("page_number") for entry in data.get("stage1_selected_pages", [])]
    stage2 = [entry.get("page_number") for entry in data.get("stage2_selected_pages", [])]
    rescue = [entry.get("page_number") for entry in data.get("rescue_stage2_selected_pages", [])]
    return {
        "stage1": [page for page in stage1 if isinstance(page, int)],
        "stage2": [page for page in stage2 if isinstance(page, int)],
        "rescue_stage2": [page for page in rescue if isinstance(page, int)],
    }


def resolve_coverage(
    project_id: str,
    pipeline_output_dir: Path,
    extraction: ExtractionResult,
    settings: Settings,
) -> tuple[CoverageScoreReport | None, TradeCoverageResult | None]:
    coverage_payload = load_json_if_exists(pipeline_output_dir / "coverage_score.json")
    if coverage_payload:
        try:
            report = CoverageScoreReport.model_validate(coverage_payload)
            trade_cov_payload = load_json_if_exists(pipeline_output_dir / "trade_coverage.json")
            trade_cov = (
                TradeCoverageResult.model_validate(trade_cov_payload)
                if trade_cov_payload
                else None
            )
            return report, trade_cov
        except Exception:  # pragma: no cover - guard against schema drift
            logger.warning("Stored coverage score could not be parsed", project_id=project_id)

    trade_cov_payload = load_json_if_exists(pipeline_output_dir / "trade_coverage.json")
    trade_cov: TradeCoverageResult | None = None
    if trade_cov_payload:
        try:
            trade_cov = TradeCoverageResult.model_validate(trade_cov_payload)
        except Exception:  # pragma: no cover
            logger.warning("Stored trade coverage could not be parsed", project_id=project_id)

    if not trade_cov:
        page_index_payload = load_json_if_exists(pipeline_output_dir / "page_index.json")
        if page_index_payload:
            try:
                page_index = PageIndex.model_validate(page_index_payload)
                trade_cov = analyze_trade_coverage(project_id, page_index, settings=settings)
            except Exception:  # pragma: no cover
                logger.warning("Failed to compute trade coverage from page index", project_id=project_id)

    if trade_cov:
        try:
            report = evaluate_coverage_score(project_id, extraction, trade_cov)
            return report, trade_cov
        except Exception:  # pragma: no cover
            logger.warning("Coverage evaluation failed", project_id=project_id)

    return None, trade_cov


def run_case(
    case: dict[str, Any],
    acceptance_root: Path,
    output_root: Path,
    settings: Settings,
) -> CaseSummary:
    name = case["name"]
    errors: list[str] = []
    warnings: list[str] = []

    pdf_path = acceptance_root / case["relative_pdf"]
    if not pdf_path.exists():
        errors.append(f"Missing input PDF at {pdf_path}")
        return CaseSummary(
            name=name,
            project_id="missing-pdf",
            passed=False,
            errors=errors,
            warnings=warnings,
            summary={},
        )

    case_output_dir = output_root / name
    case_output_dir.mkdir(parents=True, exist_ok=True)

    pipeline, document_processor = build_pipeline(settings)
    project_id = generate_project_id()

    try:
        document_bundle = document_processor.process_pdf(project_id, pdf_path)
    except Exception as exc:
        errors.append(f"Failed to process PDF: {exc}")
        return CaseSummary(
            name=name,
            project_id=project_id,
            passed=False,
            errors=errors,
            warnings=warnings,
            summary={},
        )

    try:
        result = pipeline.run_full_pipeline(project_id, document_bundle)
    except Exception as exc:
        errors.append(f"Pipeline execution failed: {exc}")
        return CaseSummary(
            name=name,
            project_id=project_id,
            passed=False,
            errors=errors,
            warnings=warnings,
            summary={},
        )

    pipeline_output_dir = pipeline._get_output_dir(project_id)  # type: ignore[attr-defined]

    document_analysis: DocumentAnalysis | None = result.document_analysis if result else None
    extraction: ExtractionResult | None = result.extraction if result else None

    if not extraction:
        errors.append("Extraction result missing")
        summary_payload = {}
    else:
        anchor_defs = [AnchorDefinition.from_dict(defn) for defn in case.get("anchor_quantities", [])]
        anchor_results, anchor_errors = evaluate_anchors(extraction, anchor_defs)
        errors.extend(anchor_errors)

        required_anchor_labels = set(case.get("required_anchor_labels", []))
        if required_anchor_labels:
            anchors_by_label = {result.label: result for result in anchor_results}
            for label in required_anchor_labels:
                anchor_result = anchors_by_label.get(label)
                if not anchor_result or not anchor_result.passed:
                    message = anchor_result.message if anchor_result else "anchor missing"
                    errors.append(
                        f"Required anchor '{label}' not satisfied: {message}"
                    )

        missing_scope_keywords = evaluate_scope_keywords(
            extraction,
            case.get("required_scope_keywords", []),
        )
        if missing_scope_keywords:
            errors.append(
                "Missing scope keywords: " + ", ".join(missing_scope_keywords)
            )

        coverage_report, trade_coverage = resolve_coverage(
            project_id,
            pipeline_output_dir,
            extraction,
            settings,
        )

        if coverage_report:
            min_coverage = float(case.get("min_coverage_score", 0.0))
            if coverage_report.coverage_score < min_coverage:
                errors.append(
                    f"Coverage score {coverage_report.coverage_score:.2f} below threshold {min_coverage:.2f}"
                )
        else:
            errors.append("Coverage score unavailable")

        expected_trade = case.get("expected_primary_trade")
        primary_trade = getattr(document_analysis, "primary_trade", None)
        if expected_trade and primary_trade != expected_trade:
            errors.append(
                f"Primary trade mismatch: expected '{expected_trade}', got '{primary_trade}'"
            )

        coverage_dict = (
            coverage_report.model_dump() if coverage_report else None
        )

        expected_missing_trades = {
            trade.lower() for trade in case.get("expected_missing_trades", [])
        }
        unexpected_missing_trades: list[dict[str, Any]] = []
        expected_missing_trade_entries: list[dict[str, Any]] = []
        primary_trade_missing = False

        if coverage_dict and coverage_dict.get("missing_trades"):
            for entry in coverage_dict["missing_trades"]:
                trade_name = entry.get("trade")
                if not trade_name:
                    continue
                normalized = trade_name.lower()
                features = "/".join(entry.get("missing_features", [])) or "unspecified"

                if expected_trade and normalized == expected_trade.lower():
                    primary_trade_missing = True
                    errors.append(
                        f"Primary trade '{expected_trade}' missing features: {features}"
                    )
                    continue

                if normalized in expected_missing_trades:
                    expected_missing_trade_entries.append(entry)
                else:
                    unexpected_missing_trades.append(entry)

            if unexpected_missing_trades:
                warnings.append(
                    "Unexpected missing trade features: "
                    + ", ".join(
                        f"{entry['trade']} ({'/'.join(entry.get('missing_features', []))})"
                        for entry in unexpected_missing_trades
                    )
                )

        if coverage_report and case.get("primary_trade_feature_ratio_min"):
            trade_name = case.get("expected_primary_trade")
            ratio_min = float(case["primary_trade_feature_ratio_min"])
            feature_info = coverage_report.trade_features.get(trade_name) if trade_name else None
            if feature_info:
                expected_features = feature_info.get("expected", [])
                matched_features = feature_info.get("matched", [])
                ratio = (len(matched_features) / len(expected_features)) if expected_features else 0.0
                if ratio < ratio_min:
                    errors.append(
                        f"Primary trade feature coverage {ratio:.2f} below minimum {ratio_min:.2f}"
                    )
            else:
                errors.append(f"Coverage report missing feature info for trade '{trade_name}'")

        validation_payload = load_json_if_exists(pipeline_output_dir / "validation_report.json") or {}
        validation_score = validation_payload.get("score")
        if validation_score is not None and "minimum_validation_score" in case:
            min_validation = float(case["minimum_validation_score"])
            if validation_score < min_validation:
                errors.append(
                    f"Validation score {validation_score:.2f} below threshold {min_validation:.2f}"
                )

        costing_payload = load_json_if_exists(pipeline_output_dir / "costing_result.json") or {}
        heuristic_total, total_cost, heuristic_fraction = compute_heuristic_fraction(costing_payload)
        max_heuristic_fraction = float(case.get("max_heuristic_cost_fraction", 1.0))
        if heuristic_fraction > max_heuristic_fraction:
            errors.append(
                "Heuristic cost share {:.1%} exceeds limit {:.1%}".format(
                    heuristic_fraction, max_heuristic_fraction
                )
            )

        cost_band = case.get("total_cost_band")
        if cost_band:
            band_min = float(cost_band.get("min", float("-inf")))
            band_max = float(cost_band.get("max", float("inf")))
            if total_cost < band_min or total_cost > band_max:
                errors.append(
                    f"Total cost {total_cost:,.2f} outside expected band [{band_min:,.2f}, {band_max:,.2f}]"
                )

        if case.get("min_bid_items"):
            bid_items = sum(len(category.get("items", [])) for category in costing_payload.get("breakdown_by_category", []))
            if bid_items < int(case["min_bid_items"]):
                errors.append(
                    f"Bid item count {bid_items} below minimum {case['min_bid_items']}"
                )

        required_non_heuristic = [item.lower() for item in case.get("required_non_heuristic_scope_items", [])]
        if required_non_heuristic:
            scope_item_status: dict[str, bool] = {name: False for name in required_non_heuristic}

            for category in costing_payload.get("breakdown_by_category", []):
                for item in category.get("items", []):
                    scope_name = (item.get("scope_item") or "").lower()
                    if scope_name in scope_item_status:
                        quantity_source = (item.get("quantity_source") or "").lower()
                        if quantity_source not in {"heuristic", "assumed", ""}:
                            scope_item_status[scope_name] = True

            for scope_name, satisfied in scope_item_status.items():
                if not satisfied:
                    errors.append(
                        f"Scope item '{scope_name}' lacks non-heuristic quantity in costing output"
                    )

        stage_pages = load_selected_pages(pipeline_output_dir)
        metrics_payload = load_json_if_exists(pipeline_output_dir / "metrics.json") or {}

        summary_payload = {
            "project_id": project_id,
            "pipeline_output_dir": str(pipeline_output_dir.resolve()),
            "primary_trade": primary_trade,
            "trade_detection_confidence": getattr(document_analysis, "trade_detection_confidence", None),
            "coverage": coverage_dict,
            "trade_feature_gaps": {
                "primary_trade_missing": primary_trade_missing,
                "unexpected": unexpected_missing_trades,
                "expected": expected_missing_trade_entries,
            },
            "anchor_quantities": [result.as_dict() for result in anchor_results],
            "heuristic_cost_share": {
                "heuristic_total": heuristic_total,
                "total_cost": total_cost,
                "fraction": heuristic_fraction,
            },
            "total_bid": costing_payload.get("total_cost"),
            "stage_pages": stage_pages,
            "metrics": metrics_payload,
            "validation_score": validation_score,
            "trade_coverage": trade_coverage.model_dump() if trade_coverage else None,
        }

        summary_path = case_output_dir / "summary.json"
        with summary_path.open("w", encoding="utf-8") as fp:
            json.dump(summary_payload, fp, indent=2, default=str)

    passed = len(errors) == 0
    return CaseSummary(
        name=name,
        project_id=project_id,
        passed=passed,
        errors=errors,
        warnings=warnings,
        summary=summary_payload if extraction else {},
    )


def load_case_definitions(definitions_path: Path) -> list[dict[str, Any]]:
    if not definitions_path.exists():
        raise FileNotFoundError(f"Case definitions not found: {definitions_path}")
    with definitions_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, list):
        raise ValueError("case_definitions.json must contain a list")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run acceptance harness for roof/windows/paving PDFs")
    parser.add_argument(
        "--case-definitions",
        type=Path,
        default=DEFAULT_CASE_DEFINITIONS,
        help="Path to case_definitions.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where summaries and logs should be written",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop immediately when a case fails",
    )

    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings)

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY must be set before running the acceptance suite")

    cases = load_case_definitions(args.case_definitions)

    output_root = args.output_dir
    output_root.mkdir(parents=True, exist_ok=True)

    results: list[CaseSummary] = []
    for case in cases:
        logger.info("Running acceptance case", case=case.get("name"))
        summary = run_case(case, ACCEPTANCE_ROOT, output_root, settings)
        results.append(summary)

        if summary.errors:
            logger.error(
                "Case failed",
                case=summary.name,
                errors=summary.errors,
            )
            if args.stop_on_fail:
                break
        else:
            logger.info("Case passed", case=summary.name)

    suite_summary = {
        "results": [result.as_dict() for result in results],
        "passed": all(result.passed for result in results),
    }

    suite_summary_path = output_root / "suite_summary.json"
    with suite_summary_path.open("w", encoding="utf-8") as fp:
        json.dump(suite_summary, fp, indent=2, default=str)

    for result in results:
        status = "PASSED" if result.passed else "FAILED"
        print(f"[{status}] {result.name} (project_id={result.project_id})")
        if result.errors:
            for error in result.errors:
                print(f"  ERROR: {error}")
        if result.warnings:
            for warning in result.warnings:
                print(f"  warning: {warning}")

    return 0 if suite_summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
