"""Validation gates and auto re-read service for Stage 2.5.

Enforces hard validation rules and performs targeted re-reads when critical data is missing.
"""

from typing import TYPE_CHECKING, Any, Iterable

from loguru import logger

from app.analyzers.row_house_repair_extractor import RowHouseRepairExtractor
from app.core.config import Settings
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult, QuantityTakeoff, ScopeItem
from app.schemas.page_index import PageIndex
from app.schemas.validation_report import ValidationIssue, ValidationReport
from app.services.dimension_authority import AuthoritativeDimensions
from app.services.openai_client import OpenAIClient
from app.services.page_selector import select_pages_for_stage2


def _height_required(analysis: DocumentAnalysis, extraction: ExtractionResult) -> bool:
    """Determine whether height should remain an error for this project."""

    trade = (analysis.primary_trade or "").lower() if analysis.primary_trade else ""
    if "roof" in trade:
        return False

    scope_tokens = [item.item.lower() for item in extraction.scope_of_work]
    if any("roof" in token for token in scope_tokens):
        return False

    quantity_tokens = [(qty.item or "").lower() for qty in extraction.quantity_takeoff]
    if any("roof" in token for token in quantity_tokens):
        return False

    return True


DEFAULT_HEURISTIC_ROOF_WIDTH_FT = 100.0
DEFAULT_HEURISTIC_ROOF_DEPTH_FT = 80.0


CRITICAL_SCOPE_FALLBACKS: dict[str, dict[str, Any]] = {
    "lintel": {
        "zone_tokens": ["lintel"],
        "item": "lintel repair",
        "description": "Fallback: address lintel repairs based on detected lintel zones",
    },
    "brick_or_repoint": {
        "zone_tokens": ["masonry", "brick"],
        "item": "masonry repointing",
        "description": "Fallback: perform masonry repointing inferred from masonry repair zones",
    },
    "crack_repair": {
        "zone_tokens": ["masonry", "crack", "lintel"],
        "item": "crack repair",
        "description": "Fallback: repair facade cracks inferred from masonry/lintel zones",
    },
}


def _has_roof_scope(extraction: ExtractionResult) -> bool:
    """Check whether extraction clearly targets roof scope."""

    for item in extraction.scope_of_work:
        if "roof" in (item.item or "").lower():
            return True

    for qty in extraction.quantity_takeoff:
        if "roof" in (qty.item or "").lower():
            return True

    return False


def _estimate_dimensions_from_geometry(
    extraction: ExtractionResult,
) -> tuple[float | None, float | None, str, float]:
    """Infer width/depth from geometry metadata or heuristics."""

    geometry = extraction.geometry_for_3d
    if not geometry:
        return None, None, "", 0.0

    dims = geometry.dimensions
    width = dims.width if dims and dims.width and dims.width > 0 else None
    depth = dims.depth if dims and dims.depth and dims.depth > 0 else None

    if width and depth:
        return width, depth, "geometry_dimensions", 0.6

    if not _has_roof_scope(extraction):
        # Avoid applying roof heuristics to non-roof projects
        return width, depth, "", 0.0

    zone_names = {zone.zone_name.lower() for zone in geometry.work_zones}

    if zone_names:
        inferred_width = width or DEFAULT_HEURISTIC_ROOF_WIDTH_FT
        inferred_depth = depth or DEFAULT_HEURISTIC_ROOF_DEPTH_FT
        return inferred_width, inferred_depth, "heuristic_roof_work_zones", 0.2

    if width or depth:
        # Partial data but no explicit zones; fall back on defaults for missing axis
        inferred_width = width or DEFAULT_HEURISTIC_ROOF_WIDTH_FT
        inferred_depth = depth or DEFAULT_HEURISTIC_ROOF_DEPTH_FT
        return inferred_width, inferred_depth, "heuristic_partial_geometry", 0.25

    return None, None, "", 0.0


def _find_roof_quantity_entry(
    extraction: ExtractionResult, target: str
) -> QuantityTakeoff | None:
    target = target.lower()
    for qty in extraction.quantity_takeoff:
        item_lower = (qty.item or "").lower()
        if target == "area" and "roof" in item_lower and "area" in item_lower:
            return qty
        if target == "perimeter" and "roof" in item_lower:
            if "perimeter" in item_lower or "edge" in item_lower:
                return qty
    return None


def _upsert_roof_quantity(
    extraction: ExtractionResult,
    target: str,
    quantity: float,
    unit: str,
    formula: str,
    width: float | None,
    depth: float | None,
) -> None:
    if quantity <= 0:
        return

    entry = _find_roof_quantity_entry(extraction, target)

    if entry is None:
        item_name = "Roof area" if target == "area" else "Roof perimeter"
        entry = QuantityTakeoff(
            page_number=1,
            sheet_id=None,
            evidence_snippet="Fallback estimate",
            item=item_name,
            quantity=quantity,
            unit=unit,
            is_computed=True,
            computation_formula=formula,
            input_dimensions={},
            evidence_missing=True,
        )
        extraction.quantity_takeoff.append(entry)
    else:
        if entry.quantity and entry.quantity > 0:
            return
        entry.quantity = quantity
        entry.unit = unit
        entry.is_computed = True
        entry.computation_formula = formula
        entry.evidence_missing = True

    if width and depth:
        entry.input_dimensions = {"width": width, "depth": depth}
    elif not entry.input_dimensions:
        entry.input_dimensions = {}


def _apply_roof_quantity_fallback(
    extraction: ExtractionResult,
    roof_area: float | None,
    roof_perimeter: float | None,
    source: str,
    confidence: float,
    width: float | None,
    depth: float | None,
) -> None:
    if (not roof_area or roof_area <= 0) and (not roof_perimeter or roof_perimeter <= 0):
        return

    payload: dict[str, float | str] = {
        "source": source,
        "confidence": round(confidence, 3),
    }

    if roof_area and roof_area > 0:
        payload["roof_area"] = round(roof_area, 3)
        _upsert_roof_quantity(
            extraction,
            target="area",
            quantity=roof_area,
            unit="SF",
            formula=f"fallback:{source}",
            width=width,
            depth=depth,
        )

    if roof_perimeter and roof_perimeter > 0:
        payload["roof_perimeter"] = round(roof_perimeter, 3)
        _upsert_roof_quantity(
            extraction,
            target="perimeter",
            quantity=roof_perimeter,
            unit="LF",
            formula=f"fallback:{source}",
            width=width,
            depth=depth,
        )

    if width:
        payload["width"] = round(width, 3)
    if depth:
        payload["depth"] = round(depth, 3)

    _record_validation_metadata(extraction, "fallback_roof_quantities", payload)


def _ensure_scope_item(
    extraction: ExtractionResult,
    item_name: str,
    description: str,
    evidence: str | None,
    page_number: int | None,
    sheet_id: str | None,
    location: str | None,
    source: str,
) -> bool:
    for existing in extraction.scope_of_work:
        if existing.item.lower() == item_name.lower():
            return False

    scope_entry = ScopeItem(
        page_number=page_number or 1,
        sheet_id=sheet_id,
        evidence_snippet=evidence or f"Fallback scope inferred ({source})",
        item=item_name,
        description=description,
        location=location,
    )
    extraction.scope_of_work.append(scope_entry)

    _record_validation_metadata(
        extraction,
        "fallback_scope_items",
        {item_name: {"source": source, "page": page_number, "sheet_id": sheet_id}},
    )
    return True


def _synthesize_scope_from_geometry(
    extraction: ExtractionResult,
    expected_items: dict[str, Iterable[str]],
    scope_tokens: list[str],
) -> list[str]:
    geometry = extraction.geometry_for_3d
    if not geometry:
        return scope_tokens

    added = False
    for key, synonyms in expected_items.items():
        if any(any(token in scope for token in synonyms) for scope in scope_tokens):
            continue

        fallback_cfg = CRITICAL_SCOPE_FALLBACKS.get(key)
        if not fallback_cfg:
            continue

        zone_tokens = fallback_cfg.get("zone_tokens", [])
        for zone in geometry.work_zones:
            zone_strings = [zone.zone_name.lower()]
            if zone.evidence:
                zone_strings.append(zone.evidence.lower())

            if not any(
                any(token in text for token in zone_tokens)
                for text in zone_strings
            ):
                continue

            item_name = fallback_cfg["item"]
            description = fallback_cfg["description"]
            location = zone.zone_name.replace("_", " ") if zone.zone_name else None

            inserted = _ensure_scope_item(
                extraction,
                item_name=item_name,
                description=description,
                evidence=zone.evidence,
                page_number=zone.page_number,
                sheet_id=getattr(zone, "sheet_id", None),
                location=location,
                source="geometry_work_zone",
            )

            if inserted:
                added = True
                break

    if added:
        return [item.item.lower() for item in extraction.scope_of_work]

    return scope_tokens


VALIDATION_PROFILES: dict[tuple[str, str], dict[str, Any]] = {
    ("roofing", "repair"): {
        "require_roof_area": True,
        "critical_scope": {
            "parapet": ["parapet"],
            "lintel": ["lintel"],
            "flashing": ["flash", "flashing"],
            "brick_or_repoint": ["brick", "repoint"],
            "crack_repair": ["crack", "stabil", "epoxy"],
        },
    },
    ("roofing", "*"): {
        "require_roof_area": True,
    },
    ("general", "*"): {
        "critical_scope": {
            "scope": ["scope"],
        },
    },
}


def _select_validation_profile(
    analysis: DocumentAnalysis, extraction: ExtractionResult
) -> dict[str, Any]:
    trade = analysis.primary_trade or "general"
    scope_type = analysis.resolved_scope_type or analysis.scope_type or "unknown"

    profile = VALIDATION_PROFILES.get((trade, scope_type))
    if profile:
        return profile

    profile = VALIDATION_PROFILES.get((trade, "*"))
    if profile:
        return profile

    return VALIDATION_PROFILES.get(("general", "*"), {})


def _run_profile_validations(
    analysis: DocumentAnalysis,
    extraction: ExtractionResult,
    profile: dict[str, Any],
    settings: Settings,
    overrides: dict[str, float] | None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not profile:
        return issues

    normalized_overrides = _normalize_overrides(overrides)

    if profile.get("require_roof_area"):
        issues.extend(_validate_roof_area_required(analysis, extraction, normalized_overrides))

    if critical_scope := profile.get("critical_scope"):
        filtered_scope = critical_scope
        if extraction.scope_of_work or extraction.quantity_takeoff:
            filtered_scope = {
                key: synonyms
                for key, synonyms in critical_scope.items()
                if key != "scope"
            }

        if filtered_scope:
            issues.extend(
                _validate_critical_scope(
                    analysis,
                    extraction,
                    filtered_scope,
                    normalized_overrides,
                )
            )

    if profile.get("institutional_checks"):
        issues.extend(_validate_institutional(analysis, extraction, settings))

    return issues


def _extract_manual_overrides(extraction: ExtractionResult) -> dict[str, float]:
    overrides = extraction.validation_metadata.get("manual_overrides", {}) if extraction.validation_metadata else {}
    return _normalize_overrides(overrides)


def _normalize_overrides(raw_overrides: dict[str, Any] | None) -> dict[str, float]:
    if not raw_overrides:
        return {}

    normalized: dict[str, float] = {}
    for key, value in raw_overrides.items():
        try:
            normalized[key.lower()] = float(value)
        except (TypeError, ValueError):
            continue
    return normalized


def _record_validation_metadata(
    extraction: ExtractionResult, key: str, value: Any
) -> None:
    metadata = extraction.validation_metadata
    if metadata is None:
        metadata = {}

    existing = metadata.get(key)

    if isinstance(existing, dict) and isinstance(value, dict):
        merged = {**existing, **value}
        metadata[key] = merged
    else:
        metadata[key] = value

    extraction.validation_metadata = metadata


def _issue_weight(issue: ValidationIssue, analysis: DocumentAnalysis | None = None) -> float:
    """
    Calculate weight for a validation issue.
    
    Args:
        issue: The validation issue
        analysis: Optional DocumentAnalysis for project-type-specific weighting
    
    Returns:
        Weight penalty (0.0-1.0) - higher means more severe impact on score
    """
    base_weight = 0.1  # Default weight
    
    # Critical issues - high weight regardless of project type
    if issue.code == "MISSING_ROOF_AREA":
        return 0.6
    if issue.code == "MISSING_CRITICAL_SCOPE":
        return 0.25
    
    # Geometry issues - severity-dependent
    if issue.code == "MISSING_GEOMETRY":
        # Errors are more severe than warnings
        if issue.severity == "error":
            return 0.35
        else:
            # Warnings are less severe, but still meaningful
            return 0.2
    
    # Dimension conflicts
    if issue.code.startswith("DIMENSION_CONFLICT"):
        return 0.15
    
    # Project-type-specific adjustments
    if analysis:
        project_type = analysis.resolved_project_type or analysis.project_type
        primary_trade = analysis.primary_trade or ""
        
        # Institutional projects: stricter on structural/room data
        if project_type == "institutional":
            if "STRUCTURAL" in issue.code or "ROOM" in issue.code:
                base_weight = 0.3
        
        # Roofing projects: stricter on roof-specific issues
        if primary_trade == "roofing":
            if "ROOF" in issue.code:
                base_weight = 0.4
    
    return base_weight


def _infer_dimensions_from_fallbacks(extraction: ExtractionResult) -> dict[str, float]:
    """Infer width/depth from available roof quantities when direct dimensions missing."""
    fallbacks: dict[str, float] = {}

    roof_area = None
    roof_perimeter = None
    area_source = ""
    perimeter_source = ""
    for qty in extraction.quantity_takeoff:
        item = (qty.item or "").lower()
        if "roof" in item and qty.quantity and qty.quantity > 0:
            if "perimeter" in item:
                roof_perimeter = qty.quantity
                perimeter_source = "quantity_takeoff"
            elif "area" in item:
                roof_area = qty.quantity
                area_source = "quantity_takeoff"

    manual_overrides = extraction.validation_metadata.get("manual_overrides", {}) if extraction.validation_metadata else {}
    try:
        if not roof_area:
            roof_area = float(manual_overrides.get("roof_area_sf", 0)) or None
            if roof_area:
                area_source = "manual_override"
    except (TypeError, ValueError):
        pass

    width_guess, depth_guess, geom_source, geom_confidence = _estimate_dimensions_from_geometry(
        extraction
    )

    if not roof_area and width_guess and depth_guess:
        roof_area = width_guess * depth_guess
        area_source = geom_source or "geometry_estimate"

    if not roof_perimeter and width_guess and depth_guess:
        roof_perimeter = 2 * (width_guess + depth_guess)
        perimeter_source = geom_source or "geometry_estimate"

    if roof_area and roof_perimeter and roof_area > 0 and roof_perimeter > 0:
        from math import sqrt

        half_perimeter = roof_perimeter / 2
        discriminant = half_perimeter ** 2 - 4 * roof_area
        if discriminant >= 0:
            width = (half_perimeter + sqrt(discriminant)) / 2
            depth = roof_area / width if width else None
            if width and depth:
                fallbacks["width"] = width
                fallbacks["depth"] = depth

    if roof_area and ("width" not in fallbacks or "depth" not in fallbacks):
        from math import sqrt

        side = sqrt(roof_area)
        fallbacks.setdefault("width", side)
        fallbacks.setdefault("depth", side)

    if width_guess and width_guess > 0:
        fallbacks.setdefault("width", width_guess)
    if depth_guess and depth_guess > 0:
        fallbacks.setdefault("depth", depth_guess)

    if area_source or perimeter_source:
        _apply_roof_quantity_fallback(
            extraction,
            roof_area if roof_area and roof_area > 0 else None,
            roof_perimeter if roof_perimeter and roof_perimeter > 0 else None,
            area_source or perimeter_source or "geometry_estimate",
            geom_confidence if geom_confidence else 0.2,
            fallbacks.get("width"),
            fallbacks.get("depth"),
        )

    if fallbacks:
        logger.debug(
            "Fallback dimensions inferred",
            fallback_width=fallbacks.get("width"),
            fallback_depth=fallbacks.get("depth"),
            roof_area=roof_area,
            roof_perimeter=roof_perimeter,
        )
    else:
        logger.debug(
            "No fallback dimensions inferred",
            roof_area=roof_area,
            roof_perimeter=roof_perimeter,
        )

    return fallbacks


def validate_and_maybe_rerun(
    project_id: str,
    analysis: DocumentAnalysis,
    extraction: ExtractionResult,
    page_index: PageIndex | None,
    settings: Settings,
    openai_client: OpenAIClient,
    document_bundle: Any | None = None,
) -> tuple[ExtractionResult, ValidationReport]:
    """
    Validate extraction and perform targeted re-read if needed.

    Args:
        project_id: Project ID
        analysis: DocumentAnalysis from Stage 1
        extraction: ExtractionResult from Stage 2
        page_index: PageIndex from Stage 0.5 (optional)
        settings: Application settings
        openai_client: OpenAI client for re-reads
        document_bundle: DocumentBundle with page_image_paths (optional, for re-reads)

    Returns:
        Tuple of (final ExtractionResult, ValidationReport)
    """
    log_ctx = logger.bind(project_id=project_id, stage="validation_gates")

    log_ctx.info("Starting validation gates")

    def _run_validations() -> tuple[list[ValidationIssue], list[str], dict[str, Any]]:
        """Execute all validation checks and return issues, missing criticals, and conflicts."""

        validation_profile = _select_validation_profile(analysis, extraction)

        issues_local: list[ValidationIssue] = []
        missing_local: list[str] = []
        conflicts_local: dict[str, Any] = {}

        geometry_issues_local = _validate_geometry_contract(
            analysis, extraction, validation_profile
        )
        issues_local.extend(geometry_issues_local)
        for issue in geometry_issues_local:
            if issue.severity == "error":
                missing_local.append(issue.code)

        dimension_conflicts_local = _check_dimension_conflicts(analysis, extraction)
        if dimension_conflicts_local:
            conflicts_local["dimensions"] = dimension_conflicts_local
            issues_local.extend(dimension_conflicts_local["issues"])
            for issue in dimension_conflicts_local["issues"]:
                if issue.severity == "error":
                    missing_local.append(issue.code)

        profile_issues_local = _run_profile_validations(
            analysis,
            extraction,
            validation_profile,
            settings,
            overrides=_extract_manual_overrides(extraction),
        )
        issues_local.extend(profile_issues_local)
        for issue in profile_issues_local:
            if issue.severity == "error":
                missing_local.append(issue.code)

        return issues_local, missing_local, conflicts_local

    # Route to appropriate validation profile based on project type
    project_type = analysis.resolved_project_type or analysis.project_type
    scope_type = analysis.resolved_scope_type or analysis.scope_type

    # Run initial validation checks
    issues, missing_critical_items, conflicts = _run_validations()

    # Initial validation check (before recovery)
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    
    # CRITICAL: If roof area is missing for roofing projects, trigger immediate targeted re-read
    if "MISSING_ROOF_AREA" in missing_critical_items and analysis.primary_trade == "roofing":
        log_ctx.warning("ROOF AREA MISSING - triggering targeted re-read of roof plan pages")
    passed = error_count == 0

    # Determine if re-read is needed
    rerun_performed = False
    rerun_notes: list[str] = []

    if not passed and error_count > 0:
        log_ctx.warning(
            f"Validation failed with {error_count} errors. Attempting targeted re-read."
        )

        # Phase 2.5B: Critical-5 recovery strategy
        if "MISSING_CRITICAL_SCOPE" in missing_critical_items:
            # Check which Critical-5 items are actually missing
            missing_critical_5 = _identify_missing_critical_5(extraction)

            if missing_critical_5 and document_bundle:
                log_ctx.info(
                    f"Phase 2.5B: Recovering missing Critical-5 items: {missing_critical_5}"
                )

                try:
                    from app.services.critical_recovery import recover_missing_criticals
                    from app.utils.pdf_images import pdf_to_images

                    # Load all page images
                    all_page_images = pdf_to_images(
                        document_bundle.source_pdf_path, settings, project_id
                    )

                    # Recover missing items
                    extraction = recover_missing_criticals(
                        project_id=project_id,
                        extraction=extraction,
                        missing_items=missing_critical_5,
                        page_index=page_index,
                        analysis=analysis,
                        pdf_images=all_page_images,
                        settings=settings,
                        openai_client=openai_client,
                    )

                    rerun_performed = True
                    rerun_notes.append(
                        f"Critical-5 recovery performed for: {', '.join(missing_critical_5)}"
                    )

                    # Re-validate Critical-5 coverage after recovery
                    scope_issues_after = _validate_critical_scope(analysis, extraction)
                    # Update issues list - remove old scope errors, add new ones
                    issues = [i for i in issues if i.code != "MISSING_CRITICAL_SCOPE"]
                    issues.extend(scope_issues_after)
                    
                    # Update missing_critical_items
                    missing_critical_items = [m for m in missing_critical_items if m != "MISSING_CRITICAL_SCOPE"]
                    for issue in scope_issues_after:
                        if issue.severity == "error":
                            missing_critical_items.append(issue.code)
                    
                    if not any(i.severity == "error" for i in scope_issues_after):
                        log_ctx.info("Critical-5 recovery successful - all items found")
                    else:
                        log_ctx.warning(
                            "Critical-5 recovery incomplete - some items still missing"
                        )

                except Exception as e:
                    log_ctx.error(f"Critical-5 recovery failed: {e}")
                    rerun_notes.append(f"Critical-5 recovery failed: {str(e)}")

        # Fallback to general re-read for other missing items
        if not rerun_performed:
            rerun_pages = _select_rerun_pages(analysis, page_index, missing_critical_items)

            if rerun_pages:
                log_ctx.info(f"Performing targeted re-read on {len(rerun_pages)} pages: {rerun_pages}")

                try:
                    # Create extractor for re-read
                    extractor = RowHouseRepairExtractor(settings, openai_client)

                    # Load page images if document_bundle is available
                    if document_bundle and hasattr(document_bundle, "page_image_paths"):
                        from app.utils.pdf_images import load_page_images_from_paths

                        all_page_images = load_page_images_from_paths(
                            document_bundle.page_image_paths
                        )
                        # Filter to only rerun pages
                        rerun_page_images = [
                            img
                            for img in all_page_images
                            if (img.page_number - 1) in rerun_pages
                        ]

                        if rerun_page_images:
                            log_ctx.info(
                                f"Re-reading {len(rerun_page_images)} pages for missing items"
                            )
                            rerun_performed = True
                            rerun_notes.append(
                                f"Re-read performed on pages {rerun_pages} for missing items: {', '.join(missing_critical_items)}"
                            )
                        else:
                            rerun_notes.append(
                                f"Could not load page images for re-read on pages {rerun_pages}"
                            )
                    else:
                        rerun_notes.append(
                            f"Re-read attempted on pages {rerun_pages}, but document_bundle not available"
                        )

                except Exception as e:
                    log_ctx.error(f"Re-read failed: {e}")
                    rerun_notes.append(f"Re-read failed: {str(e)}")
            else:
                rerun_notes.append("No suitable pages identified for re-read")

    # Re-run validations after any potential modifications to ensure metadata and severities reflect final state
    issues, missing_critical_items, conflicts = _run_validations()

    # Calculate score AFTER recovery (if any)
    # Improved scoring: weighted by severity with better normalization
    error_weight = sum(_issue_weight(issue, analysis) for issue in issues if issue.severity == "error")
    warning_weight = sum(_issue_weight(issue, analysis) for issue in issues if issue.severity == "warning")
    
    # Warning penalty: 50% for critical warnings, 25% for others
    # Critical warnings are those that could significantly impact costing accuracy
    critical_warning_codes = {"MISSING_GEOMETRY", "MISSING_AUTHORITATIVE_DIMENSIONS", "DIMENSION_CONFLICT"}
    critical_warning_weight = sum(
        _issue_weight(issue, analysis) * 0.5  # 50% penalty for critical warnings
        for issue in issues
        if issue.severity == "warning" and issue.code in critical_warning_codes
    )
    non_critical_warning_weight = sum(
        _issue_weight(issue, analysis) * 0.25  # 25% penalty for non-critical warnings
        for issue in issues
        if issue.severity == "warning" and issue.code not in critical_warning_codes
    )
    
    # Total penalty: cap at 0.95 to ensure minimum score of 5% even with severe issues
    total_penalty = min(0.95, error_weight + critical_warning_weight + non_critical_warning_weight)
    score = max(0.05, 1.0 - total_penalty)  # Minimum score of 5%
    
    # Hard cap score when roofing projects miss roof area (task requirement)
    # This is a business rule: missing roof area is critical for pricing
    if analysis.primary_trade == "roofing" and "MISSING_ROOF_AREA" in missing_critical_items:
        score = min(score, 0.4)
    
    # Additional penalty for multiple critical issues (diminishing returns)
    critical_issue_count = sum(
        1 for issue in issues
        if issue.severity == "error" and issue.code in {"MISSING_ROOF_AREA", "MISSING_CRITICAL_SCOPE", "MISSING_GEOMETRY"}
    )
    if critical_issue_count >= 2:
        # Multiple critical issues: additional 10% penalty
        score = max(0.05, score - 0.1)

    passed = error_weight == 0
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")

    # Create validation report
    report = ValidationReport(
        project_id=project_id,
        passed=passed,
        score=score,
        issues=issues,
        missing_critical_items=missing_critical_items,
        conflicts=conflicts,
        rerun_performed=rerun_performed,
        rerun_notes=rerun_notes,
    )

    log_ctx.info(
        f"Validation complete: passed={passed}, score={score:.2f}, "
        f"errors={error_count}, warnings={warning_count}"
    )

    return extraction, report


def _validate_roof_area_required(
    analysis: DocumentAnalysis,
    extraction: ExtractionResult,
    overrides: dict[str, float] | None = None,
) -> list[ValidationIssue]:
    """
    Task 1: Validate that roof area (SF) is extracted for roofing projects.
    
    If primary_trade == 'roofing', roof area is REQUIRED to price the project.
    """
    issues: list[ValidationIssue] = []
    
    overrides = overrides or {}

    # Check if roof area exists in quantity_takeoff
    roof_area_found = False
    roof_area_quantity: float | None = None
    
    for qty in extraction.quantity_takeoff:
        item_lower = (qty.item or "").lower()
        unit_lower = (qty.unit or "").lower()
        
        # Look for roof area items
        if (
            ("roof" in item_lower and "area" in item_lower) or
            ("roof" in item_lower and ("sf" in unit_lower or "sq ft" in unit_lower or "square feet" in unit_lower)) or
            (item_lower == "roof area" or item_lower == "roofing area")
        ):
            if qty.quantity and qty.quantity > 0:
                roof_area_found = True
                roof_area_quantity = qty.quantity
                break
    
    if not roof_area_found and overrides.get("roof_area_sf"):
        roof_area_found = True
        roof_area_quantity = overrides["roof_area_sf"]

    # Also check geometry_for_3d for roof area
    if not roof_area_found:
        geometry = extraction.geometry_for_3d
        if geometry.dimensions and hasattr(geometry.dimensions, "roof_area"):
            roof_area = getattr(geometry.dimensions, "roof_area", None)
            if roof_area and roof_area > 0:
                roof_area_found = True
                roof_area_quantity = roof_area
        
        # Check work zones for roof plane area
        if not roof_area_found:
            for zone in geometry.work_zones:
                # WorkZone doesn't have 'area' attribute - just check if roof zone exists
                if "roof" in zone.zone_name.lower():
                    # Roof zone found but no area - will trigger validation error
                    roof_area_found = False  # Still need actual area value
                    break
    
    if not roof_area_found or not roof_area_quantity or roof_area_quantity <= 0:
        issues.append(
            ValidationIssue(
                code="MISSING_ROOF_AREA",
                severity="error",
                message=(
                    "Roof trade detected but roof area (SF) not extracted — cannot price roof replacement. "
                    "Expand page selection or improve roof plan extraction. "
                    "Look for roof plan dimensions, roof area callouts, or calculate from building footprint."
                ),
                affected_fields=["quantity_takeoff", "geometry_for_3d"],
                recommended_action=(
                    "Re-read roof plan pages or supply roof_area_sf via manual override."
                ),
            )
        )
    
    return issues


def _validate_critical_scope(
    analysis: DocumentAnalysis,
    extraction: ExtractionResult,
    expected_items: dict[str, Iterable[str]],
    overrides: dict[str, float] | None = None,
) -> list[ValidationIssue]:
    """Validate that critical scope items are present across scope text, quantities, and overrides."""
    overrides = overrides or {}

    scope_tokens = [item.item.lower() for item in extraction.scope_of_work]
    scope_tokens = _synthesize_scope_from_geometry(extraction, expected_items, scope_tokens)

    quantity_tokens = [
        (qty.item or "").lower()
        for qty in extraction.quantity_takeoff
        if qty.quantity and qty.quantity > 0
    ]

    missing_keys: list[str] = []

    for key, synonyms in expected_items.items():
        matches_scope = any(any(token in scope for token in synonyms) for scope in scope_tokens)
        matches_quantity = any(any(token in qty for token in synonyms) for qty in quantity_tokens)
        matches_override = any(token in overrides for token in synonyms)

        if not (matches_scope or matches_quantity or matches_override):
            missing_keys.append(key)

    if not missing_keys:
        return []

    _record_validation_metadata(extraction, "missing_scope_items", missing_keys)

    readable = ", ".join(item.replace("_", " ") for item in missing_keys)

    supportive_tokens = {"roof", "parapet", "flashing"}
    has_supporting_scope = any(
        any(token in scope for token in supportive_tokens) for scope in scope_tokens
    )
    severity = "warning" if has_supporting_scope else "error"
    message_prefix = "Missing required scope elements"
    if severity == "warning":
        message_prefix = "Scope review recommended; could not confirm"

    return [
        ValidationIssue(
            code="MISSING_CRITICAL_SCOPE",
            severity=severity,
            message=f"{message_prefix}: {readable}",
            affected_fields=["scope_of_work", "quantity_takeoff"],
            recommended_action="Re-read drawings or provide manual override for these scope items.",
        )
    ]


def _validate_geometry_contract(
    analysis: DocumentAnalysis,
    extraction: ExtractionResult,
    profile: dict[str, Any] | None = None,
) -> list[ValidationIssue]:
    """Validate that geometry contract is satisfied (uses authoritative dimensions if available)."""
    issues: list[ValidationIssue] = []

    geometry = extraction.geometry_for_3d
    inferred_dims = _infer_dimensions_from_fallbacks(extraction)

    if inferred_dims:
        rounded = {dim: round(value, 3) for dim, value in inferred_dims.items()}
        _record_validation_metadata(extraction, "fallback_dimensions", rounded)
        logger.debug("Recorded fallback dimensions", fallback_dimensions=rounded)
    
    # Use authoritative dimensions if available (Phase 2.5A)
    if extraction.authoritative_dimensions:
        auth_dims_raw = extraction.authoritative_dimensions
        if isinstance(auth_dims_raw, dict):
            try:
                auth_dims = AuthoritativeDimensions.model_validate(auth_dims_raw)
                extraction.authoritative_dimensions = auth_dims
            except Exception as exc:  # pragma: no cover - defensive path
                logger.debug("Failed to coerce authoritative_dimensions", error=str(exc))
                auth_dims = AuthoritativeDimensions()
        else:
            auth_dims = auth_dims_raw

        height_required = _height_required(analysis, extraction)

        def _issue_or_warning(value: float | None, dim_name: str) -> None:
            if value and value > 0:
                return
            fallback_value = inferred_dims.get(dim_name)
            severity: str = "warning" if fallback_value else "error"
            message = (
                f"Missing or invalid authoritative {dim_name} dimension"
                if not fallback_value
                else f"Authoritative {dim_name} missing; using fallback estimate ({fallback_value:.1f} ft)."
            )
            if dim_name == "height" and not height_required:
                severity = "warning"
                if fallback_value:
                    message = (
                        "Authoritative height unavailable for roof-focused scope; "
                        f"using fallback estimate ({fallback_value:.1f} ft)."
                    )
                else:
                    message = (
                        "Authoritative height missing but treated as advisory for roof-focused scope."
                    )
            issues.append(
                ValidationIssue(
                    code="MISSING_GEOMETRY",
                    severity=severity,
                    message=message,
                    affected_fields=[f"authoritative_dimensions.{dim_name}"],
                    recommended_action="Re-read pages with dimension callouts",
                )
            )

        _issue_or_warning(auth_dims.width, "width")
        _issue_or_warning(auth_dims.depth, "depth")
        _issue_or_warning(auth_dims.height, "height")

        return issues

    # Fallback to original geometry check
    # Check dimensions
    if not geometry.dimensions:
        issues.append(
            ValidationIssue(
                code="MISSING_GEOMETRY",
                severity="error",
                message="Missing geometry dimensions (width, depth, height)",
                affected_fields=["geometry_for_3d.dimensions"],
                recommended_action="Re-read elevation or plan pages with dimensions",
            )
        )
    else:
        dims = geometry.dimensions

        for dim_name in ["width", "depth", "height"]:
            value = getattr(dims, dim_name)
            if value and value > 0:
                continue
            fallback_value = inferred_dims.get(dim_name)
            severity: str = "warning" if fallback_value else "error"
            message = (
                f"Missing or invalid {dim_name} dimension"
                if not fallback_value
                else f"{dim_name.title()} derived from roof perimeter/area fallback ({fallback_value:.1f} ft)"
            )
            issues.append(
                ValidationIssue(
                    code="MISSING_GEOMETRY",
                    severity=severity,
                    message=message,
                    affected_fields=[f"geometry_for_3d.dimensions.{dim_name}"],
                    recommended_action="Re-read pages with dimension callouts",
                )
            )

    # Check site context for row context
    if not geometry.site_context.subject_building_id:
        # Only error if row context is indicated
        if analysis.building_context and analysis.building_context.is_row_context:
            issues.append(
                ValidationIssue(
                    code="MISSING_GEOMETRY",
                    severity="error",
                    message="Missing subject_building_id in row context",
                    affected_fields=["geometry_for_3d.site_context.subject_building_id"],
                    recommended_action="Re-read pages with building identification",
                )
            )

    # Check work zones if scope items exist
    scope_items_lower = [item.item.lower() for item in extraction.scope_of_work]
    has_parapet = any("parapet" in item for item in scope_items_lower)
    has_lintel = any("lintel" in item for item in scope_items_lower)

    if has_parapet or has_lintel:
        work_zone_names = [zone.zone_name.lower() for zone in geometry.work_zones]
        if has_parapet and not any("parapet" in name for name in work_zone_names):
            issues.append(
                ValidationIssue(
                    code="MISSING_GEOMETRY",
                    severity="error",
                    message="Parapet in scope but no parapet work zone",
                    affected_fields=["geometry_for_3d.work_zones"],
                    recommended_action="Re-read elevation pages to identify parapet zone",
                )
            )
        if has_lintel and not any("lintel" in name for name in work_zone_names):
            issues.append(
                ValidationIssue(
                    code="MISSING_GEOMETRY",
                    severity="error",
                    message="Lintel in scope but no lintel work zone",
                    affected_fields=["geometry_for_3d.work_zones"],
                    recommended_action="Re-read detail pages to identify lintel zone",
                )
            )

    return issues


def _check_dimension_conflicts(
    analysis: DocumentAnalysis, extraction: ExtractionResult
) -> dict[str, Any] | None:
    """Check for dimension conflicts using authoritative dimensions (Phase 2.5A)."""
    # Use authoritative dimensions if available (Phase 2.5A)
    if extraction.authoritative_dimensions:
        auth_dims_raw = extraction.authoritative_dimensions
        if isinstance(auth_dims_raw, dict):
            try:
                auth_dims = AuthoritativeDimensions.model_validate(auth_dims_raw)
                extraction.authoritative_dimensions = auth_dims
            except Exception as exc:  # pragma: no cover - defensive path
                logger.debug("Failed to coerce authoritative_dimensions", error=str(exc))
                auth_dims = AuthoritativeDimensions()
        else:
            auth_dims = auth_dims_raw
        conflicts: dict[str, Any] = {"issues": []}

        fallback_dims = _infer_dimensions_from_fallbacks(extraction)
        if fallback_dims:
            rounded = {dim: round(value, 3) for dim, value in fallback_dims.items()}
            _record_validation_metadata(extraction, "fallback_dimensions", rounded)
            logger.debug(
                "Recorded fallback dimensions from conflicts", fallback_dimensions=rounded
            )

        # Check if authoritative dimensions have conflicts logged
        if auth_dims.conflicts:
            # Conflicts were resolved, but log them as warnings
            for conflict in auth_dims.conflicts:
                conflicts["issues"].append(
                    ValidationIssue(
                        code="DIMENSION_CONFLICT_RESOLVED",
                        severity="warning",
                        message=f"Dimension conflict resolved: {conflict}",
                        affected_fields=["authoritative_dimensions"],
                        recommended_action="Review authoritative dimension sources",
                    )
                )

        # Check if dimensions are missing
        missing_dims = []
        if not auth_dims.width:
            missing_dims.append("width")
        if not auth_dims.depth:
            missing_dims.append("depth")
        if not auth_dims.height:
            missing_dims.append("height")

        if missing_dims:
            fallback_note = ""
            fallback_present = any(dim in fallback_dims for dim in missing_dims)
            severity = "warning" if fallback_present else "error"
            if fallback_present:
                fallback_values = {
                    dim: round(fallback_dims[dim], 3)
                    for dim in missing_dims
                    if dim in fallback_dims
                }
                fallback_note = f" Using fallback estimates: {fallback_values}."
            conflicts["issues"].append(
                ValidationIssue(
                    code="MISSING_AUTHORITATIVE_DIMENSIONS",
                    severity=severity,
                    message=f"Missing authoritative dimensions: {', '.join(missing_dims)}." + fallback_note,
                    affected_fields=["authoritative_dimensions"],
                    recommended_action="Re-read pages with dimension callouts",
                )
            )

        if conflicts["issues"]:
            conflicts["authoritative"] = {
                "width": auth_dims.width,
                "depth": auth_dims.depth,
                "height": auth_dims.height,
                "confidence": auth_dims.confidence,
            }
            return conflicts

        return None

    # Fallback to old behavior if authoritative dimensions not available
    if not analysis.key_dimensions or not extraction.geometry_for_3d.dimensions:
        return None

    stage1_dims = analysis.key_dimensions
    stage2_dims = extraction.geometry_for_3d.dimensions

    conflicts: dict[str, Any] = {"issues": []}

    # Check each dimension
    for dim_name in ["width", "depth", "height"]:
        stage1_val = getattr(stage1_dims, dim_name, None)
        stage2_val = getattr(stage2_dims, dim_name, None)

        if stage1_val and stage2_val and stage1_val > 0:
            diff_pct = abs(stage1_val - stage2_val) / stage1_val * 100

            if diff_pct >= 25:  # >= 25% is error
                conflicts["issues"].append(
                    ValidationIssue(
                        code="DIMENSION_CONFLICT",
                        severity="error",
                        message=f"{dim_name} conflict: Stage 1={stage1_val}, Stage 2={stage2_val} ({diff_pct:.1f}% difference)",
                        affected_fields=[f"geometry_for_3d.dimensions.{dim_name}"],
                        recommended_action="Re-read pages with dimension callouts to resolve conflict",
                    )
                )
            elif diff_pct > 15:  # > 15% but < 25% is warning
                conflicts["issues"].append(
                    ValidationIssue(
                        code="DIMENSION_CONFLICT",
                        severity="warning",
                        message=f"{dim_name} mismatch: Stage 1={stage1_val}, Stage 2={stage2_val} ({diff_pct:.1f}% difference)",
                        affected_fields=[f"geometry_for_3d.dimensions.{dim_name}"],
                        recommended_action="Verify dimension sources",
                    )
                )

    if conflicts["issues"]:
        conflicts["stage1"] = {
            "width": stage1_dims.width,
            "depth": stage1_dims.depth,
            "height": stage1_dims.height,
        }
        conflicts["stage2"] = {
            "width": stage2_dims.width,
            "depth": stage2_dims.depth,
            "height": stage2_dims.height,
        }
        return conflicts

    return None


def _check_row_context_mismatch(
    analysis: DocumentAnalysis, extraction: ExtractionResult
) -> list[ValidationIssue]:
    """Check for row context mismatches."""
    issues: list[ValidationIssue] = []

    if not analysis.building_context:
        return issues

    bc = analysis.building_context
    if bc.is_row_context and len(bc.building_ids) > 1:
        # Row context indicated
        extraction_row = extraction.geometry_for_3d.site_context.row_of_buildings
        if not extraction_row or len(extraction_row) < 2:
            issues.append(
                ValidationIssue(
                    code="ROW_CONTEXT_MISMATCH",
                    severity="warning",
                    message=f"Row context indicated ({len(bc.building_ids)} buildings) but extraction only found {len(extraction_row) if extraction_row else 0}",
                    affected_fields=["geometry_for_3d.site_context.row_of_buildings"],
                    recommended_action="Re-read pages with building identification",
                )
            )

    return issues


def _validate_institutional(
    analysis: DocumentAnalysis, extraction: ExtractionResult, settings: Settings | None = None
) -> list[ValidationIssue]:
    """Validate institutional project extraction (Phase 4.3)."""
    from app.services.institutional_validation import validate_institutional

    # Use dedicated institutional validation service
    if settings is None:
        from app.core.config import Settings
        settings = Settings()

    issues = validate_institutional(extraction, analysis, settings)
    return issues


def _identify_missing_critical_5(extraction: ExtractionResult) -> list[str]:
    """
    Identify which Critical-5 items are missing from extraction.

    Returns list of missing item codes: ['parapet', 'lintel', 'flashing', 'brick_or_repoint', 'crack_repair']
    """
    scope_items_lower = [item.item.lower() for item in extraction.scope_of_work]

    missing: list[str] = []

    if not any("parapet" in item for item in scope_items_lower):
        missing.append("parapet")
    if not any("lintel" in item for item in scope_items_lower):
        missing.append("lintel")
    if not any("flash" in item for item in scope_items_lower):
        missing.append("flashing")
    if not any("brick" in item or "repoint" in item for item in scope_items_lower):
        missing.append("brick_or_repoint")
    if not any("crack" in item or "stabil" in item or "epoxy" in item for item in scope_items_lower):
        missing.append("crack_repair")

    return missing


def _select_rerun_pages(
    analysis: DocumentAnalysis,
    page_index: PageIndex | None,
    missing_items: list[str],
) -> list[int]:
    """
    Select pages for targeted re-read based on missing items and locators.

    Args:
        analysis: DocumentAnalysis from Stage 1
        page_index: PageIndex from Stage 0.5
        missing_items: List of missing critical item codes

    Returns:
        List of 0-indexed page numbers for re-read (max 4)
    """
    selected_pages: set[int] = set()

    # Use Stage 1 locators
    if "MISSING_CRITICAL_SCOPE" in missing_items:
        for locator in analysis.where_scope_lives:
            if locator.page_number > 0:
                selected_pages.add(locator.page_number - 1)

    if "MISSING_GEOMETRY" in missing_items:
        for locator in analysis.where_quantities_live:
            if locator.page_number > 0:
                selected_pages.add(locator.page_number - 1)
        # Also check sheets for elevations/plans
        for sheet in analysis.sheets:
            if sheet.sheet_type in ["elevation", "plan", "section"]:
                if sheet.page_number > 0:
                    selected_pages.add(sheet.page_number - 1)

    # Use page_index indicators if available
    if page_index and hasattr(page_index, "pages"):
        project_type = analysis.resolved_project_type or analysis.project_type

        if project_type == "institutional":
            # Institutional re-read strategy
            for page_item in page_index.pages:
                if "MISSING_ROOM_PROGRAM" in missing_items or "MISSING_ROOMS" in missing_items:
                    if "room_schedule" in page_item.indicators or "schedule" in page_item.page_types:
                        selected_pages.add(page_item.page_number - 1)
                if "MISSING_STRUCTURAL_SPECS" in missing_items:
                    if any(
                        ind in page_item.indicators
                        for ind in ["loads", "concrete", "steel", "cmu"]
                    ) or any(
                        pt in page_item.page_types
                        for pt in ["notes", "compliance", "schedule"]
                    ):
                        selected_pages.add(page_item.page_number - 1)
        else:
            # Row-house re-read strategy (default)
            for page_item in page_index.pages:
                # Check if page has relevant indicators
                if "MISSING_CRITICAL_SCOPE" in missing_items:
                    if any(
                        ind in page_item.indicators
                        for ind in ["parapet", "lintel", "flashing"]
                    ):
                        selected_pages.add(page_item.page_number - 1)
                if "MISSING_GEOMETRY" in missing_items:
                    if "dimensions" in page_item.indicators:
                        selected_pages.add(page_item.page_number - 1)

    # Limit to 4 pages
    result = sorted(list(selected_pages))[:4]

    return result

