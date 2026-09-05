"""Coverage score evaluator and rescue helpers."""

from __future__ import annotations

from typing import Iterable, NamedTuple

from loguru import logger

from app.schemas.coverage_score import CoverageScoreReport, MissingTrade
from app.schemas.extraction_result import ExtractionResult
from app.schemas.trade_coverage import TradeCoverageEntry, TradeCoverageResult

# Keyword heuristics tying extraction artifacts to trades
_SCOPE_KEYWORDS = {
    "roofing": {"roof", "flashing", "parapet", "membrane", "coping", "drain"},
    "masonry": {"brick", "block", "lintel", "masonry", "cmu", "veneer", "repoint"},
    "windows": {"window", "windows", "glazing", "storefront", "curtain", "opening"},
    "pavement": {"pavement", "asphalt", "sidewalk", "concrete", "curb", "drive", "parking"},
    "structure": {"beam", "column", "girder", "footing", "foundation", "reinforcing", "slab"},
    "interiors": {"ceiling", "drywall", "paint", "floor", "tile", "partition", "finish"},
}

_SIGNAL_FEATURE_MAP = {
    "roofing_plan": {"plan"},
    "roofing_detail": {"detail", "materials"},
    "roofing_quantity": {"quantity"},
    "window_schedule": {"quantity", "materials"},
    "window_elevation": {"scope"},
    "window_detail": {"detail", "materials"},
    "paving_plan": {"plan", "scope"},
    "paving_quantity": {"quantity"},
    "masonry_elevation": {"scope"},
    "masonry_detail": {"detail"},
    "structure_plan": {"plan"},
    "structure_detail": {"detail"},
    "interiors_schedule": {"materials", "quantity"},
    "interiors_plan": {"scope"},
}

_FEATURE_WEIGHTS = {
    "scope": 0.4,
    "quantity": 0.3,
    "materials": 0.15,
    "detail": 0.1,
    "plan": 0.05,
}

_HEURISTIC_UNITS = {"ea", "each"}


def evaluate_coverage_score(
    project_id: str,
    extraction: ExtractionResult,
    trade_coverage: TradeCoverageResult,
) -> CoverageScoreReport:
    """Compare extraction artifacts with trade coverage to compute a score."""

    dominant = trade_coverage.dominant_trades or [entry.trade for entry in trade_coverage.trades[:3]]
    dominant = list(dict.fromkeys(dominant))

    matched: list[str] = []
    missing: list[MissingTrade] = []
    trade_features: dict[str, dict[str, list[str]]] = {}

    context = _collect_extraction_context(extraction)

    for trade in dominant:
        entry = _find_trade_entry(trade_coverage.trades, trade)
        if not entry:
            continue

        expected_features = _derive_expected_features(entry)
        matched_features, heuristics_flags = _match_trade_features(
            trade,
            expected_features,
            context,
            extraction,
        )
        coverage_ratio = _coverage_ratio(expected_features, matched_features)

        trade_features[trade] = {
            "expected": sorted(expected_features),
            "matched": sorted(matched_features),
        }

        if coverage_ratio >= 0.6:
            matched.append(trade)
        else:
            missing_features = sorted(
                set(expected_features) - matched_features
            )
            missing_features.extend(heuristics_flags)
            missing.append(
                MissingTrade(
                    trade=trade,
                    confidence=entry.confidence,
                    evidence_pages=[ev.page_number for ev in entry.evidence],
                    missing_features=sorted(set(missing_features)),
                )
            )

    score = (len(matched) / len(dominant)) if dominant else 1.0

    logger.bind(project_id=project_id).info(
        "Coverage score evaluated",
        score=round(score, 3),
        matched=matched,
        missing=[m.trade for m in missing],
    )

    return CoverageScoreReport(
        project_id=project_id,
        coverage_score=score,
        dominant_trades=dominant,
        matched_trades=matched,
        missing_trades=missing,
        trade_features=trade_features,
    )


def _find_trade_entry(entries: list[TradeCoverageEntry], trade: str) -> TradeCoverageEntry | None:
    for entry in entries:
        if entry.trade == trade:
            return entry
    return None


class QuantityRow(NamedTuple):
    tokens: set[str]
    quantity: float | None
    unit: str | None
    is_computed: bool


def _derive_expected_features(entry: TradeCoverageEntry) -> set[str]:
    features: set[str] = {"scope"}
    for signal in entry.signal_types:
        features.update(_SIGNAL_FEATURE_MAP.get(signal, set()))
    return features


def _collect_extraction_context(extraction: ExtractionResult) -> dict[str, object]:
    tokens = {
        "scope": set(),
        "materials": set(),
        "detail": set(),
        "plan": set(),
    }
    quantity_rows: list[QuantityRow] = []

    def _split(text: str | None) -> Iterable[str]:
        if not text:
            return []
        return text.replace("/", " ").replace("-", " ").replace(",", " ").lower().split()

    for item in extraction.scope_of_work:
        tokens["scope"].update(_split(item.item))
        tokens["scope"].update(_split(item.description))
        tokens["detail"].update(token for token in _split(item.location) if "detail" in (item.location or "").lower())
        tokens["plan"].update(token for token in _split(item.location) if "plan" in (item.location or "").lower())

    for material in extraction.material_specifications:
        tokens["materials"].update(_split(material.material_name))
        tokens["materials"].update(_split(material.application))
        tokens["detail"].update(_split(material.detail_sheet))
        tokens["detail"].update(_split(material.specification))

    for qty in extraction.quantity_takeoff:
        row_tokens = set(_split(qty.item))
        quantity_rows.append(
            QuantityRow(
                tokens=row_tokens,
                quantity=qty.quantity,
                unit=(qty.unit or "").lower() if qty.unit else None,
                is_computed=qty.is_computed,
            )
        )
        tokens["detail"].update(_split(qty.computation_formula))
        tokens["plan"].update(qty.input_dimensions.keys())

    if extraction.openings and extraction.openings.openings:
        for opening in extraction.openings.openings:
            tokens["materials"].add(opening.opening_type.lower())
            tokens["detail"].update(_split(opening.detail_reference))

    if extraction.geometry_for_3d and getattr(extraction.geometry_for_3d, "dimensions", None):
        tokens["plan"].add("dimensions")

    return {
        "tokens": tokens,
        "quantity_rows": quantity_rows,
    }


def _match_trade_features(
    trade: str,
    expected_features: set[str],
    context: dict[str, object],
    extraction: ExtractionResult,
) -> tuple[set[str], list[str]]:
    matched: set[str] = set()
    heuristics: list[str] = []

    keywords = _SCOPE_KEYWORDS.get(trade, set())
    tokens = context["tokens"]  # type: ignore[index]
    quantity_rows: list[QuantityRow] = context["quantity_rows"]  # type: ignore[index]

    if "scope" in expected_features and keywords & tokens["scope"]:
        matched.add("scope")

    if "materials" in expected_features:
        if keywords & tokens["materials"]:
            matched.add("materials")
        elif trade == "windows" and extraction.openings and extraction.openings.openings:
            matched.add("materials")

    if "detail" in expected_features and keywords & tokens["detail"]:
        matched.add("detail")

    if "plan" in expected_features:
        if keywords & tokens["plan"]:
            matched.add("plan")
        elif trade in {"roofing", "pavement", "structure"} and getattr(
            extraction.geometry_for_3d, "dimensions", None
        ) is not None:
            matched.add("plan")

    if "quantity" in expected_features:
        quantity_matched = False
        heuristic_only = False
        for row in quantity_rows:
            if not keywords & row.tokens:
                continue
            if row.quantity is not None and row.quantity > 1:
                quantity_matched = True
                break
            if row.is_computed and row.quantity is not None:
                quantity_matched = True
                break
            if row.unit and row.unit not in _HEURISTIC_UNITS and row.quantity not in (None, 0):
                quantity_matched = True
                break
            heuristic_only = True
        if quantity_matched:
            matched.add("quantity")
        elif heuristic_only:
            heuristics.append("quantity_only_heuristic")

    return matched, heuristics


def _coverage_ratio(expected: set[str], matched: set[str]) -> float:
    if not expected:
        return 1.0
    total_weight = sum(_FEATURE_WEIGHTS.get(feature, 0.05) for feature in expected)
    matched_weight = sum(_FEATURE_WEIGHTS.get(feature, 0.05) for feature in matched if feature in expected)
    if total_weight <= 0:
        return 1.0
    return matched_weight / total_weight
