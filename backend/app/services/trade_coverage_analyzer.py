"""Trade coverage analyzer.

Produces broad-scope trade presence signals from the page index so downstream
stages can widen their search beyond the Stage 1 typology guess.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from loguru import logger

from app.core.config import Settings
from app.schemas.page_index import PageIndex, PageIndexItem
from app.schemas.trade_coverage import TradeCoverageEntry, TradeCoverageResult, TradeEvidence

# Lightweight keyword/indicator vocabulary for common CSI divisions.
_TRADE_KEYWORDS: dict[str, set[str]] = {
    "roofing": {
        "roof", "flashing", "parapet", "coping", "membrane", "deck", "drain",
        "insulation", "tern", "roofing", "gutter",
    },
    "masonry": {
        "brick", "block", "cmu", "parapet", "lintel", "veneer", "repoint",
        "masonry", "stone", "façade", "facade",
    },
    "windows": {
        "window", "glazing", "storefront", "frame", "curtain", "sill",
        "fenestration", "glazed",
    },
    "pavement": {
        "pavement", "asphalt", "concrete", "sidewalk", "curb", "drive", "road",
        "parking", "striping", "site", "civil",
    },
    "structure": {
        "beam", "column", "girder", "footing", "foundation", "reinforcing",
        "structural", "joist", "slab", "truss",
    },
    "interiors": {
        "interior", "finish", "drywall", "ceiling", "flooring", "paint",
        "partition", "tile", "millwork",
    },
}

# Preferred CSI division tag for each trade label.
_TRADE_DIVISIONS: dict[str, str] = {
    "roofing": "07 Thermal & Moisture Protection",
    "masonry": "04 Masonry",
    "windows": "08 Openings",
    "pavement": "32 Exterior Improvements",
    "structure": "03/05 Concrete & Metals",
    "interiors": "09 Finishes",
}

_PAGE_TYPE_WEIGHTS: dict[str, float] = {
    "plan": 4.0,
    "elevation": 4.0,
    "section": 3.5,
    "detail": 3.0,
    "schedule": 2.5,
    "notes": 1.5,
    "site_plan": 4.0,
    "unknown": 1.0,
}

_INDICATOR_WEIGHTS: dict[str, float] = {
    "flashing": 5.0,
    "parapet": 4.5,
    "lintel": 4.0,
    "room_schedule": 2.5,
    "dimensions": 2.0,
    "compliance": 1.0,
}

_DEFAULT_DOMINANCE_THRESHOLD = 0.35
_MIN_SIGNAL_FAMILIES_FOR_DOMINANCE = 2


def analyze_trade_coverage(
    project_id: str,
    page_index: PageIndex | dict | None,
    *,
    settings: Settings | None = None,
) -> TradeCoverageResult:
    """Compute trade coverage heuristics from the page index.

    Args:
        project_id: Project identifier.
        page_index: PageIndex model (or raw dict) from Stage 0.5. If ``None`` or empty,
            an empty coverage result is returned.
        settings: Optional settings. Currently used for logging context only, but
            accepted so callers can pass the existing application settings object.

    Returns:
        TradeCoverageResult structured for downstream consumption.
    """

    if not page_index:
        logger.bind(project_id=project_id).debug("No page index supplied, skipping trade coverage")
        return TradeCoverageResult(project_id=project_id, trades=[], dominant_trades=[])

    if isinstance(page_index, dict):
        page_index = PageIndex.model_validate(page_index)

    trade_scores: dict[str, float] = defaultdict(float)
    trade_evidence: dict[str, list[TradeEvidence]] = defaultdict(list)

    for page in page_index.pages:
        _update_trade_signals(page, trade_scores, trade_evidence)

    if not trade_scores:
        return TradeCoverageResult(project_id=project_id, trades=[], dominant_trades=[])

    max_score = max(trade_scores.values()) or 1.0
    trades: list[TradeCoverageEntry] = []
    dominant: list[str] = []

    for trade, score in sorted(trade_scores.items(), key=lambda item: item[1], reverse=True):
        confidence = min(1.0, score / max_score)
        evidence = trade_evidence.get(trade, [])
        unique_signal_types = sorted({stype for ev in evidence for stype in ev.signal_types})

        entry = TradeCoverageEntry(
            trade=trade,
            csi_division=_TRADE_DIVISIONS.get(trade, "Unknown"),
            confidence=confidence,
            total_score=score,
            signal_types=unique_signal_types,
            evidence=evidence,
        )
        trades.append(entry)
        if confidence >= _DEFAULT_DOMINANCE_THRESHOLD and len(unique_signal_types) >= _MIN_SIGNAL_FAMILIES_FOR_DOMINANCE:
            dominant.append(trade)

    logger.bind(project_id=project_id).info(
        "Trade coverage analyzed",
        trades=len(trades),
        dominant=dominant,
    )

    return TradeCoverageResult(project_id=project_id, trades=trades, dominant_trades=dominant)


def _update_trade_signals(
    page: PageIndexItem,
    trade_scores: dict[str, float],
    trade_evidence: dict[str, list[TradeEvidence]],
) -> None:
    """Score a single page against trade vocabularies."""

    confidence = max(page.confidence, 0.0)
    if confidence <= 0.05:
        return

    tokens = _collect_tokens(page)
    if not tokens:
        return

    type_boost = sum(_PAGE_TYPE_WEIGHTS.get(pt, 0.0) for pt in page.page_types)
    indicator_boost = sum(_INDICATOR_WEIGHTS.get(ind, 0.0) for ind in page.indicators)

    for trade, vocabulary in _TRADE_KEYWORDS.items():
        matched_keywords = vocabulary.intersection(tokens)
        if not matched_keywords and indicator_boost == 0.0:
            continue

        base_score = len(matched_keywords) * 2.0
        score = confidence * (base_score + type_boost + indicator_boost)
        if score <= 0.0:
            continue

        signal_types = _classify_signal_types(trade, page, matched_keywords)

        trade_scores[trade] += score
        trade_evidence[trade].append(
            TradeEvidence(
                page_number=page.page_number,
                sheet_id=page.sheet_id,
                sheet_title=page.sheet_title,
                signals=sorted(matched_keywords) if matched_keywords else list(page.indicators),
                signal_types=signal_types,
                score=score,
            )
        )


def _collect_tokens(page: PageIndexItem) -> set[str]:
    """Collect normalized tokens from a page index entry."""

    tokens: set[str] = set()

    def _maybe_split(text: str | None) -> Iterable[str]:
        if not text:
            return []
        return text.replace("/", " ").replace("-", " ").replace(",", " ").lower().split()

    for token in _maybe_split(page.sheet_id):
        tokens.add(token)
    for token in _maybe_split(page.sheet_title):
        tokens.add(token)

    # Include indicators directly—they are already lowercased by the indexer.
    tokens.update(ind.lower() for ind in page.indicators)

    return tokens


def _classify_signal_types(
    trade: str,
    page: PageIndexItem,
    matched_keywords: set[str],
) -> list[str]:
    """Infer normalized signal categories for coverage evidence."""

    signal_types: set[str] = set()
    page_types = {ptype.lower() for ptype in page.page_types}
    indicators = {ind.lower() for ind in page.indicators}
    keywords = {kw.lower() for kw in matched_keywords}

    def has_indicator(*targets: str) -> bool:
        return any(target in indicators for target in targets)

    def has_keyword(*targets: str) -> bool:
        return any(target in keywords for target in targets)

    if trade == "roofing":
        if "plan" in page_types or has_indicator("roof_plan"):
            signal_types.add("roofing_plan")
        if "detail" in page_types or has_indicator("flashing", "parapet"):
            signal_types.add("roofing_detail")
        if has_indicator("dimensions") or has_keyword("sf", "square"):
            signal_types.add("roofing_quantity")

    elif trade == "windows":
        if "schedule" in page_types or has_indicator("window_schedule"):
            signal_types.add("window_schedule")
        if "elevation" in page_types:
            signal_types.add("window_elevation")
        if has_indicator("details") or "detail" in page_types:
            signal_types.add("window_detail")

    elif trade == "pavement":
        if "site_plan" in page_types or has_indicator("civil", "site"):
            signal_types.add("paving_plan")
        if has_indicator("dimensions", "quantity"):
            signal_types.add("paving_quantity")

    elif trade == "masonry":
        if "elevation" in page_types or has_indicator("parapet", "lintel"):
            signal_types.add("masonry_elevation")
        if "detail" in page_types:
            signal_types.add("masonry_detail")

    elif trade == "structure":
        if "plan" in page_types and has_keyword("beam", "column", "joist"):
            signal_types.add("structure_plan")
        if "detail" in page_types or has_indicator("rebar"):
            signal_types.add("structure_detail")

    elif trade == "interiors":
        if has_indicator("finish_schedule") or "schedule" in page_types:
            signal_types.add("interiors_schedule")
        if "plan" in page_types or "elevation" in page_types:
            signal_types.add("interiors_plan")

    # Generic fallbacks when above heuristics miss
    if not signal_types:
        if "plan" in page_types:
            signal_types.add(f"{trade}_plan")
        if "detail" in page_types:
            signal_types.add(f"{trade}_detail")
        if has_indicator("schedule"):
            signal_types.add(f"{trade}_schedule")

    return sorted(signal_types)
