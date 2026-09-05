"""Page selection service for optimizing Stage 1 and Stage 2 API costs."""

from typing import Any, Iterable
from pathlib import Path

from loguru import logger

from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.trade_coverage import TradeCoverageResult
from app.core.config import Settings


def select_pages_for_stage1(
    total_pages: int,
    page_index: Any | None = None,
    settings: Settings | None = None,
) -> list[int]:
    """
    Select a small subset of pages for Stage 1 document analysis.

    Strategy:
    - For large PDFs (>= large_pdf_threshold): Use index-driven selection with wider sampling
    - For small PDFs: Use conservative heuristic (first/middle/last)
    - If page_index is available: Select best pages based on indicators and types
      (elevations > plans > details > notes, prioritize pages with dimensions)
    - If no page_index: Fall back to first/middle/last heuristic

    Args:
        total_pages: Total number of pages in the document
        page_index: Optional PageIndex from Stage 0.5
        settings: Optional Settings for thresholds (defaults to Settings() if None)

    Returns:
        List of 0-indexed page numbers to analyze in Stage 1
    """
    if total_pages <= 0:
        return []

    if settings is None:
        settings = Settings()

    # For large PDFs, use index-driven selection with wider sampling
    if total_pages >= settings.large_pdf_threshold:
        if page_index is not None and hasattr(page_index, "pages") and page_index.pages:
            selected = _select_pages_for_large_pdf_stage1(page_index, total_pages, settings)
            if selected:
                logger.info(
                    f"Stage 1 page selection (large PDF, index-driven): {len(selected)}/{total_pages} pages"
                )
                return selected
        # Fallback to stratified sampling for large PDFs without index
        selected = _stratified_sampling_for_large_pdf(total_pages, settings.stage1_max_pages_large)
        logger.info(
            f"Stage 1 page selection (large PDF, stratified): {len(selected)}/{total_pages} pages"
        )
        return selected

    # Small PDFs: Use index if available (existing logic)
    if page_index is not None and hasattr(page_index, "pages") and page_index.pages:
        selected = _select_pages_from_index(page_index, total_pages, max_pages=4)
        if selected:
            logger.info(
                f"Stage 1 page selection from index: {len(selected)}/{total_pages} pages"
            )
            return selected

    # Fallback to conservative heuristic for small PDFs
    if total_pages <= 4:
        # If 4 or fewer pages, analyze all
        return list(range(total_pages))

    selected: list[int] = []

    # Always include first page (cover/drawing index)
    selected.append(0)

    # Include last page
    if total_pages > 1:
        selected.append(total_pages - 1)

    # Add middle pages to reach up to 4 pages total
    if total_pages > 2 and len(selected) < 4:
        # Add one page from middle section
        mid_page = total_pages // 2
        if mid_page not in selected:
            selected.append(mid_page)

    # If we still have space and pages, add strategic pages
    if total_pages > 3 and len(selected) < 4:
        # Add a page between first and middle
        if len(selected) >= 2:
            gap = (selected[1] - selected[0]) // 2
            if gap > 0 and (selected[0] + gap) not in selected:
                selected.append(selected[0] + gap)
        # Or add a page between middle and last
        if len(selected) < 4 and len(selected) >= 2:
            last_idx = len(selected) - 1
            gap = (selected[last_idx] - selected[last_idx - 1]) // 2
            if gap > 0 and (selected[last_idx - 1] + gap) not in selected:
                selected.append(selected[last_idx - 1] + gap)

    # Dedupe and sort
    selected = sorted(list(set(selected)))

    # Final cap at 4
    if len(selected) > 4:
        selected = selected[:4]

    logger.info(
        f"Stage 1 page selection (heuristic): {len(selected)}/{total_pages} pages "
        f"(reduction: {100 * (1 - len(selected) / total_pages):.1f}%)"
    )

    return selected


def _select_pages_from_index(
    page_index: Any, total_pages: int, max_pages: int = 4
) -> list[int]:
    """
    Select best pages for Stage 1 based on page index.

    Prioritizes:
    1. Pages with dimensions indicator
    2. Elevations > plans > details > notes
    3. Higher confidence pages

    Args:
        page_index: PageIndex from Stage 0.5
        total_pages: Total number of pages
        max_pages: Maximum pages to select (default 4 for small PDFs)

    Returns:
        List of 0-indexed page numbers
    """
    if not hasattr(page_index, "pages") or not page_index.pages:
        return []

    # Score each page
    scored_pages: list[tuple[int, float]] = []

    window_priority_indicators = {
        "window_schedule",
        "window_tag",
        "glazing",
        "storefront",
        "window_detail",
        "mullion",
    }

    for page_item in page_index.pages:
        page_num_0_indexed = page_item.page_number - 1  # Convert to 0-indexed
        if page_num_0_indexed < 0 or page_num_0_indexed >= total_pages:
            continue

        score = 0.0

        # Boost for dimensions indicator
        if "dimensions" in page_item.indicators:
            score += 10.0

        # Boost for page types (elevations are most valuable for Stage 1)
        type_scores = {
            "elevation": 8.0,
            "plan": 6.0,
            "detail": 4.0,
            "schedule": 3.0,
            "notes": 2.0,
            "cover": 1.0,
            "index": 1.0,
        }
        for page_type in page_item.page_types:
            score += type_scores.get(page_type, 0.0)
            if page_type == "schedule":
                score += 2.0

        # Boost for other indicators
        indicator_scores = {
            "lintel": 2.0,
            "parapet": 2.0,
            "flashing": 1.5,
            "room_schedule": 1.0,
            "window_schedule": 15.0,
            "glazing": 10.0,
            "storefront": 10.0,
            "window_detail": 8.0,
            "mullion": 6.0,
            "window_tag": 12.0,
        }
        for indicator in page_item.indicators:
            score += indicator_scores.get(indicator, 0.0)

        # Multiply by confidence
        score *= page_item.confidence

        window_priority = bool(window_priority_indicators.intersection(page_item.indicators))
        scored_pages.append((page_num_0_indexed, score, window_priority))

    # Sort by score (descending) and take top max_pages
    scored_pages.sort(key=lambda x: x[1], reverse=True)
    selected = [page_num for page_num, _, _ in scored_pages[:max_pages]]

    # Ensure at least two high-value window pages are included if available
    window_pages = [page_num for page_num, _, is_window in scored_pages if is_window]
    for page_num in window_pages[:2]:
        if page_num not in selected:
            selected.append(page_num)

    # Limit to max_pages while keeping window pages prioritized
    if len(selected) > max_pages:
        selected.sort()
        # Keep window pages first
        window_selected = [p for p in selected if any(
            p == page_num for page_num, _, is_window in scored_pages if is_window and page_num == p
        )]
        non_window_selected = [p for p in selected if p not in window_selected]
        trimmed = window_selected + non_window_selected
        selected = trimmed[:max_pages]

    # Ensure we have at least one page
    if not selected and total_pages > 0:
        selected = [0]  # Fallback to first page

    return sorted(selected)


def _select_pages_for_large_pdf_stage1(
    page_index: Any, total_pages: int, settings: Settings
) -> list[int]:
    """
    Select pages for Stage 1 on large PDFs using index-driven selection with coverage.

    Strategy:
    - Score all pages by type/indicators/confidence
    - Ensure coverage: 2 pages from first 10%, 6+ from middle 80%, 2 from last 10%
    - Cap at stage1_max_pages_large

    Args:
        page_index: PageIndex from Stage 0.5
        total_pages: Total number of pages
        settings: Settings for max pages

    Returns:
        List of 0-indexed page numbers
    """
    if not hasattr(page_index, "pages") or not page_index.pages:
        return []

    # Score each page (use same scoring as _select_pages_from_index but filter by confidence)
    scored_pages: list[tuple[int, float]] = []
    first_10pct_end = max(1, int(total_pages * 0.1))
    last_10pct_start = max(0, int(total_pages * 0.9))

    for page_item in page_index.pages:
        page_num_0_indexed = page_item.page_number - 1
        if page_num_0_indexed < 0 or page_num_0_indexed >= total_pages:
            continue

        # Filter by minimum confidence
        if page_item.confidence < 0.6:
            continue

        score = 0.0

        # Boost for dimensions indicator
        if "dimensions" in page_item.indicators:
            score += 10.0

        # Boost for page types
        type_scores = {
            "elevation": 8.0,
            "plan": 6.0,
            "detail": 4.0,
            "schedule": 3.0,
            "notes": 2.0,
            "cover": 1.0,
            "index": 1.0,
        }
        for page_type in page_item.page_types:
            score += type_scores.get(page_type, 0.0)
            if page_type == "schedule":
                score += 2.0

        # Boost for indicators
        indicator_scores = {
            "lintel": 2.0,
            "parapet": 2.0,
            "flashing": 1.5,
            "room_schedule": 1.0,
            "compliance": 1.0,
            "window_schedule": 6.0,
            "glazing": 4.0,
            "storefront": 4.0,
            "window_detail": 4.0,
            "mullion": 3.0,
        }
        for indicator in page_item.indicators:
            score += indicator_scores.get(indicator, 0.0)

        # Multiply by confidence
        score *= page_item.confidence

        scored_pages.append((page_num_0_indexed, score))

    # Sort by score
    scored_pages.sort(key=lambda x: x[1], reverse=True)

    # Ensure coverage across document
    selected: list[int] = []
    early_pages = [p for p, _ in scored_pages if p < first_10pct_end]
    middle_pages = [
        p for p, _ in scored_pages if first_10pct_end <= p < last_10pct_start
    ]
    late_pages = [p for p, _ in scored_pages if p >= last_10pct_start]

    # Take 2 from early, 6+ from middle (prioritize by score), 2 from late
    selected.extend(sorted(early_pages[:2]))
    selected.extend(sorted(middle_pages[: settings.stage1_max_pages_large - 4]))
    selected.extend(sorted(late_pages[:2]))

    # Fill remaining slots from top-scored overall
    selected_set = set(selected)
    for page_num, _ in scored_pages:
        if len(selected) >= settings.stage1_max_pages_large:
            break
        if page_num not in selected_set:
            selected.append(page_num)
            selected_set.add(page_num)

    # Ensure we have at least first page
    if not selected and total_pages > 0:
        selected = [0]

    return sorted(selected)


def _stratified_sampling_for_large_pdf(total_pages: int, max_pages: int) -> list[int]:
    """
    Stratified sampling for large PDFs without page_index.

    Ensures coverage: first + multiple middle buckets + last.

    Args:
        total_pages: Total number of pages
        max_pages: Maximum pages to select

    Returns:
        List of 0-indexed page numbers
    """
    selected: list[int] = []

    # Always include first page
    selected.append(0)

    # Include last page
    if total_pages > 1:
        selected.append(total_pages - 1)

    # Fill middle with evenly distributed samples
    remaining_slots = max_pages - len(selected)
    if remaining_slots > 0 and total_pages > 2:
        step = max(1, (total_pages - 2) // (remaining_slots + 1))
        for i in range(1, total_pages - 1, step):
            if len(selected) >= max_pages:
                break
            if i not in selected:
                selected.append(i)

    return sorted(selected)


_TRADE_CATEGORY_MAP: dict[str, tuple[str, ...]] = {
    "roofing": ("scope", "geometry"),
    "masonry": ("scope", "geometry"),
    "windows": ("scope", "materials"),
    "pavement": ("scope", "geometry"),
    "structure": ("scope", "geometry"),
    "interiors": ("scope", "materials"),
    "civil": ("scope", "geometry", "quantity"),
    "sitework": ("scope", "geometry", "quantity"),
    "landscape": ("scope", "materials"),
    "mechanical": ("scope", "quantity", "materials"),
    "hvac": ("scope", "quantity", "materials"),
    "plumbing": ("scope", "quantity", "materials"),
    "electrical": ("scope", "quantity", "materials"),
    "fire_protection": ("scope", "materials"),
    "demolition": ("scope", "materials"),
    "concrete": ("scope", "quantity"),
    "steel": ("scope", "geometry"),
    "doors": ("scope", "materials"),
    "glazing": ("scope", "materials"),
}

_TRADE_SIGNAL_CATEGORY_MAP: dict[str, tuple[str, ...]] = {
    "roofing_plan": ("geometry", "scope"),
    "roofing_detail": ("scope", "materials"),
    "roofing_quantity": ("quantity", "scope"),
    "window_schedule": ("materials", "quantity"),
    "window_elevation": ("scope",),
    "window_detail": ("materials", "scope"),
    "paving_plan": ("geometry", "scope"),
    "paving_quantity": ("quantity", "scope"),
    "masonry_elevation": ("scope",),
    "masonry_detail": ("scope", "materials"),
    "structure_plan": ("geometry", "scope"),
    "structure_detail": ("scope", "geometry"),
    "interiors_schedule": ("materials", "quantity"),
    "interiors_plan": ("scope",),
    "civil_plan": ("geometry", "scope"),
    "civil_detail": ("scope", "materials"),
    "site_detail": ("geometry", "scope"),
    "landscape_plan": ("scope", "materials"),
    "mechanical_plan": ("scope", "quantity"),
    "mechanical_schedule": ("materials", "quantity"),
    "plumbing_riser": ("scope", "quantity"),
    "plumbing_detail": ("materials", "scope"),
    "electrical_plan": ("scope", "quantity"),
    "lighting_schedule": ("materials", "quantity"),
    "fire_protection_plan": ("scope", "materials"),
    "fire_protection_detail": ("scope", "materials"),
    "demolition_plan": ("scope",),
    "spec_section": ("materials", "scope"),
    "compliance_notice": ("scope", "materials"),
}

_DEFAULT_TRADE_CATEGORIES: tuple[str, ...] = ("scope", "geometry")
_MAX_EVIDENCE_PAGES_PER_TRADE = 3
_MAX_EVIDENCE_PAGES_DOMINANT = 6
_MIN_PAGES_PER_DOMINANT_TRADE = 2


def select_pages_for_stage2(
    analysis: DocumentAnalysis,
    project_id: str | None = None,
    page_index: Any | None = None,
    total_pages: int | None = None,
    settings: Settings | None = None,
    trade_coverage: TradeCoverageResult | dict[str, Any] | None = None,
) -> dict[str, list[int]]:
    """
    Select pages for Stage 2 extraction based on Stage 1 analysis and page_index.

    For large PDFs, also consults page_index directly to find high-signal pages
    (plans/elevations/details with strong indicators) independent of Stage 1 findings.

    Args:
        analysis: DocumentAnalysis result from Stage 1
        project_id: Optional project ID (for loading page_index if not provided)
        page_index: Optional PageIndex from Stage 0.5
        total_pages: Optional total pages (for large PDF detection)
        settings: Optional Settings for thresholds

    Returns:
        Dictionary with keys: scope_pages, quantity_pages, materials_pages, geometry_pages
        Each value is a sorted, deduplicated list of 0-indexed page numbers
    """
    if settings is None:
        settings = Settings()

    scope_pages: set[int] = set()
    quantity_pages: set[int] = set()
    materials_pages: set[int] = set()
    geometry_pages: set[int] = set()

    # Extract pages from Stage 1 analysis (existing logic)
    for locator in analysis.where_scope_lives:
        if locator.page_number > 0:
            scope_pages.add(locator.page_number - 1)

    for locator in analysis.where_quantities_live:
        if locator.page_number > 0:
            quantity_pages.add(locator.page_number - 1)

    for locator in analysis.where_materials_live:
        if locator.page_number > 0:
            materials_pages.add(locator.page_number - 1)

    for sheet in analysis.sheets:
        if sheet.sheet_type in ["plan", "elevation", "section", "3d_view", "site_plan", "detail", "schedule", "notes", "compliance"]:
            if sheet.page_number > 0:
                geometry_pages.add(sheet.page_number - 1)

    # Incorporate procurement/compliance context to ensure Stage 2 evaluates governing notes
    procurement_context = getattr(analysis, "procurement_context", None)
    if procurement_context and getattr(procurement_context, "source_pages", None):
        compliance_pages = {
            page_number - 1
            for page_number in procurement_context.source_pages
            if isinstance(page_number, int) and page_number > 0
        }
        if compliance_pages:
            scope_pages.update(compliance_pages)
            materials_pages.update(compliance_pages)
            # If prevailing wage or labor regime flagged, quantities often live in compliance schedules
            requires_quantities = bool(getattr(analysis, "requires_prevailing_wage", False)) or (
                getattr(analysis, "labor_regime", "standard") == "prevailing_wage"
            )
            if requires_quantities:
                quantity_pages.update(compliance_pages)

    # For large PDFs, also consult page_index directly for high-signal pages
    if total_pages and total_pages >= settings.large_pdf_threshold:
        # Load page_index if not provided but project_id is available
        if page_index is None and project_id:
            page_index = _load_page_index(project_id)

        if page_index and hasattr(page_index, "pages") and page_index.pages:
            index_set = set(
                _select_index_pages_for_stage2(
                    page_index, total_pages, settings.stage2_max_pages_large
                )
            )
            scope_pages.update(index_set)
            geometry_pages.update(index_set)
            # Keep quantities/materials from Stage 1 if found, else use index pages
            if not quantity_pages:
                quantity_pages.update(index_set)
            if not materials_pages:
                materials_pages.update(index_set)

    primary_trade = getattr(analysis, "primary_trade", None)

    # Incorporate trade coverage hints
    if trade_coverage is None and project_id:
        trade_coverage = _load_trade_coverage(project_id)

    if isinstance(trade_coverage, dict):
        trade_coverage = TradeCoverageResult.model_validate(trade_coverage)

    if isinstance(trade_coverage, TradeCoverageResult):
        dominant_trades = set(trade_coverage.dominant_trades or [])
        pages_by_trade: dict[str, set[int]] = {}
        category_sets = {
            "scope": scope_pages,
            "quantity": quantity_pages,
            "materials": materials_pages,
            "geometry": geometry_pages,
        }

        for entry in trade_coverage.trades:
            if not entry.evidence:
                continue

            pages_by_trade.setdefault(entry.trade, set())
            evidence_sorted = sorted(entry.evidence, key=lambda ev: ev.score, reverse=True)
            max_pages = _MAX_EVIDENCE_PAGES_PER_TRADE
            if entry.trade in dominant_trades:
                max_pages = min(len(evidence_sorted), _MAX_EVIDENCE_PAGES_DOMINANT)

            for idx, evidence in enumerate(evidence_sorted):
                if idx >= max_pages:
                    break
                if evidence.page_number <= 0:
                    continue
                page_idx = evidence.page_number - 1
                categories = _categories_for_signal(entry.trade, evidence.signal_types)
                for category in categories:
                    target = category_sets.get(category)
                    if target is not None:
                        target.add(page_idx)
                pages_by_trade[entry.trade].add(page_idx)

        # Ensure dominant trades have minimum coverage by adding remaining evidence pages if needed
        for entry in trade_coverage.trades:
            if entry.trade not in dominant_trades:
                continue
            current_pages = pages_by_trade.get(entry.trade, set())
            if len(current_pages) >= _MIN_PAGES_PER_DOMINANT_TRADE:
                continue

            needed = _MIN_PAGES_PER_DOMINANT_TRADE - len(current_pages)
            for evidence in sorted(entry.evidence, key=lambda ev: ev.score, reverse=True):
                if evidence.page_number <= 0:
                    continue
                page_idx = evidence.page_number - 1
                if page_idx in current_pages:
                    continue
                categories = _categories_for_signal(entry.trade, evidence.signal_types)
                for category in categories:
                    category_sets.get(category, scope_pages).add(page_idx)
                current_pages.add(page_idx)
                if len(current_pages) >= _MIN_PAGES_PER_DOMINANT_TRADE:
                    break

    # If windows is the detected primary trade, guarantee schedule/detail coverage
    if primary_trade == "windows":
        window_focus_pages = _identify_window_focus_pages(page_index, total_pages)
        for page_idx in window_focus_pages:
            scope_pages.add(page_idx)
            materials_pages.add(page_idx)
            quantity_pages.add(page_idx)

    # Dedupe and sort each list
    max_per_category: int | None = None
    if total_pages and total_pages >= settings.large_pdf_threshold:
        max_per_category = max(1, settings.stage2_max_pages_large // 2)

    def _finalize(pages: set[int]) -> list[int]:
        ordered = sorted(pages)
        if max_per_category is not None:
            return ordered[:max_per_category]
        return ordered

    scope_pages_list = _finalize(scope_pages)
    quantity_pages_list = _finalize(quantity_pages)
    materials_pages_list = _finalize(materials_pages)
    geometry_pages_list = _finalize(geometry_pages)

    # Cap each category for large PDFs
    result = {
        "scope_pages": scope_pages_list,
        "quantity_pages": quantity_pages_list,
        "materials_pages": materials_pages_list,
        "geometry_pages": geometry_pages_list,
    }

    total_selected = len(
        set(
            scope_pages_list
            + quantity_pages_list
            + materials_pages_list
            + geometry_pages_list
        )
    )

    logger.info(
        f"Stage 2 page selection: {total_selected} unique pages "
        f"(scope: {len(scope_pages_list)}, quantities: {len(quantity_pages_list)}, "
        f"materials: {len(materials_pages_list)}, geometry: {len(geometry_pages_list)})"
    )

    return result


def _identify_window_focus_pages(
    page_index: Any | None,
    total_pages: int | None,
    *,
    max_pages: int = 4,
) -> list[int]:
    """Select high-signal pages for window systems when Division 08 is primary."""

    if not page_index or not hasattr(page_index, "pages"):
        return []

    scored: list[tuple[int, float]] = []
    window_indicators = {"window", "glazing", "fenestration", "storefront", "curtain", "vision", "mullion"}

    for page in page_index.pages:
        page_idx = page.page_number - 1
        if page_idx < 0 or (total_pages is not None and page_idx >= total_pages):
            continue

        score = 0.0

        for page_type in page.page_types:
            if page_type.lower() in {"schedule", "elevation", "plan", "detail"}:
                score += 4.0

        for indicator in page.indicators:
            if indicator.lower() in window_indicators:
                score += 5.0
            if indicator.lower() == "room_schedule":
                score += 3.0

        sheet_tokens = (page.sheet_title or "") + " " + (page.sheet_id or "")
        if any(token in sheet_tokens.lower() for token in window_indicators):
            score += 4.0

        score *= max(page.confidence, 0.0)

        if score > 0:
            scored.append((page_idx, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    selected = [idx for idx, _ in scored[:max_pages]]
    return selected


def _load_page_index(project_id: str) -> Any | None:
    """
    Load page_index.json for a project.

    Args:
        project_id: Project ID

    Returns:
        PageIndex object or None if not found
    """
    try:
        import json
        from app.schemas.page_index import PageIndex

        index_file = Path("out") / project_id / "page_index.json"
        if index_file.exists():
            with open(index_file, "r") as f:
                data = json.load(f)
            return PageIndex.model_validate(data)
    except Exception as e:
        logger.debug(f"Failed to load page_index for {project_id}: {e}")
    return None


def _load_trade_coverage(project_id: str) -> TradeCoverageResult | None:
    """Load trade_coverage.json for a project if it exists."""

    try:
        import json

        coverage_file = Path("out") / project_id / "trade_coverage.json"
        if coverage_file.exists():
            with open(coverage_file, "r") as f:
                data = json.load(f)
            return TradeCoverageResult.model_validate(data)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.debug(f"Failed to load trade coverage for {project_id}: {exc}")
    return None


def _categories_for_signal(trade: str, signal_types: list[str]) -> tuple[str, ...]:
    """Map trade signal types to Stage 2 page categories."""

    collected: list[str] = []

    for signal in signal_types:
        mapped = _TRADE_SIGNAL_CATEGORY_MAP.get(signal)
        if mapped:
            collected.extend(mapped)

    if not collected:
        collected.extend(_TRADE_CATEGORY_MAP.get(trade, _DEFAULT_TRADE_CATEGORIES))

    # Preserve order but remove duplicates
    seen: set[str] = set()
    ordered: list[str] = []
    for category in collected:
        if category not in seen:
            ordered.append(category)
            seen.add(category)

    return tuple(ordered or _DEFAULT_TRADE_CATEGORIES)


def _select_index_pages_for_stage2(
    page_index: Any, total_pages: int, max_pages: int
) -> list[int]:
    """
    Select high-signal pages from index for Stage 2 extraction.

    Prioritizes pages with strong indicators for scope/items:
    - Plans/elevations/details
    - Indicators: lintel, parapet, flashing, dimensions, room_schedule

    Args:
        page_index: PageIndex from Stage 0.5
        total_pages: Total number of pages
        max_pages: Maximum pages to select

    Returns:
        List of 0-indexed page numbers
    """
    if not hasattr(page_index, "pages") or not page_index.pages:
        return []

    scored_pages: list[tuple[int, float]] = []

    for page_item in page_index.pages:
        page_num_0_indexed = page_item.page_number - 1
        if page_num_0_indexed < 0 or page_num_0_indexed >= total_pages:
            continue

        # Filter by minimum confidence
        if page_item.confidence < 0.6:
            continue

        score = 0.0

        # Strong boost for page types that contain scope items
        type_scores = {
            "plan": 10.0,
            "elevation": 9.0,
            "detail": 8.0,
            "schedule": 6.0,
            "notes": 3.5,
            "compliance": 7.0,
        }
        for page_type in page_item.page_types:
            score += type_scores.get(page_type, 0.0)

        # Strong boost for construction indicators
        indicator_scores = {
            "lintel": 5.0,
            "parapet": 5.0,
            "flashing": 4.0,
            "dimensions": 4.0,
            "room_schedule": 3.0,
            "compliance": 4.0,
            "prevailing_wage": 4.0,
            "bond": 3.5,
            "insurance": 2.5,
            "wage_schedule": 3.5,
        }
        for indicator in page_item.indicators:
            score += indicator_scores.get(indicator, 0.0)

        # Multiply by confidence
        score *= page_item.confidence

        scored_pages.append((page_num_0_indexed, score))

    # Sort by score and take top max_pages
    scored_pages.sort(key=lambda x: x[1], reverse=True)
    selected = [page_num for page_num, _ in scored_pages[:max_pages]]

    return sorted(selected)
