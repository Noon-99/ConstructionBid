"""Dimension authority resolver for Phase 2.5A.

Deterministically resolves dimension conflicts by applying authority rules.
"""

from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field

from app.schemas.document_analysis import DocumentAnalysis, KeyDimensions
from app.schemas.extraction_result import ExtractionResult
from app.schemas.geometry_for_3d import Dimensions


class DimensionSource(BaseModel):
    """Source information for a dimension."""

    source_type: Literal[
        "plan_view",
        "elevation",
        "detail",
        "title_block",
        "site_plan",
        "notes",
        "unknown",
    ] = Field(description="Type of source")
    page_number: int | None = Field(default=None, description="Page number where dimension was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    confidence: float = Field(
        ge=0.0, le=1.0, default=0.5, description="Confidence in this dimension"
    )


class AuthoritativeDimensions(BaseModel):
    """Authoritative dimensions after resolution."""

    width: float | None = Field(default=None, description="Authoritative width")
    depth: float | None = Field(default=None, description="Authoritative depth")
    height: float | None = Field(default=None, description="Authoritative height")
    source: dict[str, str] = Field(
        default_factory=dict,
        description="Source type for each dimension (e.g., {'width': 'plan_view'})",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, default=0.0, description="Overall confidence in authoritative dimensions"
    )
    downgraded_sources: list[str] = Field(
        default_factory=list,
        description="List of sources that were downgraded or discarded",
    )
    conflicts: list[str] = Field(
        default_factory=list,
        description="List of conflicts that were resolved (for logging)",
    )


def resolve_dimension_authority(
    analysis: DocumentAnalysis, extraction: ExtractionResult
) -> AuthoritativeDimensions:
    """
    Resolve dimension conflicts using authority rules.

    Args:
        analysis: DocumentAnalysis from Stage 1
        extraction: ExtractionResult from Stage 2

    Returns:
        AuthoritativeDimensions with resolved dimensions
    """
    log_ctx = logger.bind(stage="dimension_authority")

    log_ctx.info("Resolving dimension authority")

    # Collect all dimension sources
    stage1_dims = analysis.key_dimensions
    stage2_dims = extraction.geometry_for_3d.dimensions if extraction.geometry_for_3d else None

    # Build dimension candidates with source information
    width_candidates: list[tuple[float, DimensionSource]] = []
    depth_candidates: list[tuple[float, DimensionSource]] = []
    height_candidates: list[tuple[float, DimensionSource]] = []

    # Stage 1 dimensions (from document analysis)
    if stage1_dims:
        # Infer source type from sheets
        source_type = _infer_stage1_source_type(analysis)
        source = DimensionSource(
            source_type=source_type,
            confidence=stage1_dims.confidence or 0.8,
        )

        if stage1_dims.width:
            width_candidates.append((stage1_dims.width, source))
        if stage1_dims.depth:
            depth_candidates.append((stage1_dims.depth, source))
        if stage1_dims.height:
            height_candidates.append((stage1_dims.height, source))

    # Stage 2 dimensions (from extraction)
    if stage2_dims:
        # Infer source type from extraction context
        source_type = _infer_stage2_source_type(extraction)
        source = DimensionSource(
            source_type=source_type,
            confidence=0.8,  # Default confidence for Stage 2 dimensions
        )

        if stage2_dims.width:
            width_candidates.append((stage2_dims.width, source))
        if stage2_dims.depth:
            depth_candidates.append((stage2_dims.depth, source))
        if stage2_dims.height:
            height_candidates.append((stage2_dims.height, source))

    # Resolve each dimension using authority rules
    authoritative = AuthoritativeDimensions()

    authoritative.width, authoritative.source["width"], downgraded = _resolve_dimension(
        "width", width_candidates
    )
    authoritative.downgraded_sources.extend(downgraded)
    if downgraded:
        authoritative.conflicts.append(f"width: resolved from {len(width_candidates)} sources")

    authoritative.depth, authoritative.source["depth"], downgraded = _resolve_dimension(
        "depth", depth_candidates
    )
    authoritative.downgraded_sources.extend(downgraded)
    if downgraded:
        authoritative.conflicts.append(f"depth: resolved from {len(depth_candidates)} sources")

    authoritative.height, authoritative.source["height"], downgraded = _resolve_dimension(
        "height", height_candidates
    )
    authoritative.downgraded_sources.extend(downgraded)
    if downgraded:
        authoritative.conflicts.append(f"height: resolved from {len(height_candidates)} sources")

    # Calculate overall confidence
    dims_found = sum(
        1 for d in [authoritative.width, authoritative.depth, authoritative.height] if d is not None
    )
    if dims_found > 0:
        # Base confidence on number of dimensions found and source quality
        source_scores = []
        for source_type in authoritative.source.values():
            if source_type == "plan_view":
                source_scores.append(1.0)
            elif source_type == "elevation":
                source_scores.append(0.9)
            elif source_type == "title_block":
                source_scores.append(0.95)
            elif source_type == "site_plan":
                source_scores.append(0.9)
            else:
                source_scores.append(0.7)

        authoritative.confidence = (
            sum(source_scores) / len(source_scores) if source_scores else 0.0
        ) * (dims_found / 3.0)

    log_ctx.info(
        f"Dimension authority resolved: width={authoritative.width}, "
        f"depth={authoritative.depth}, height={authoritative.height}, "
        f"confidence={authoritative.confidence:.2f}"
    )

    return authoritative


def _infer_stage1_source_type(analysis: DocumentAnalysis) -> Literal[
    "plan_view", "elevation", "detail", "title_block", "site_plan", "notes", "unknown"
]:
    """Infer source type from Stage 1 analysis sheets."""
    for sheet in analysis.sheets:
        if sheet.sheet_type == "plan":
            return "plan_view"
        elif sheet.sheet_type == "elevation":
            return "elevation"
        elif sheet.sheet_type == "site_plan":
            return "site_plan"
        elif sheet.sheet_type == "detail":
            return "detail"
        elif sheet.sheet_type == "notes":
            return "notes"

    return "unknown"


def _infer_stage2_source_type(extraction: ExtractionResult) -> Literal[
    "plan_view", "elevation", "detail", "title_block", "site_plan", "notes", "unknown"
]:
    """Infer source type from Stage 2 extraction context."""
    # Check geometry evidence
    if extraction.geometry_for_3d and extraction.geometry_for_3d.dimensions:
        dims = extraction.geometry_for_3d.dimensions
        evidence = dims.evidence or ""
        evidence_lower = evidence.lower()

        # Check evidence text for keywords
        if "plan" in evidence_lower or "footprint" in evidence_lower:
            return "plan_view"
        elif "elevation" in evidence_lower or "facade" in evidence_lower:
            return "elevation"
        elif "detail" in evidence_lower:
            return "detail"
        elif "site" in evidence_lower:
            return "site_plan"
        elif "page" in evidence_lower or "found" in evidence_lower:
            # If dimensions were found on pages, check if we can infer from page numbers
            # For now, default to "notes" as a reasonable fallback for manual/spec documents
            # This is better than "unknown" as it's in the authority hierarchy
            return "notes"

    return "unknown"


def _resolve_dimension(
    dim_name: str, candidates: list[tuple[float, DimensionSource]]
) -> tuple[float | None, str, list[str]]:
    """
    Resolve a dimension using authority rules.

    Args:
        dim_name: Name of dimension ('width', 'depth', 'height')
        candidates: List of (value, source) tuples

    Returns:
        Tuple of (resolved_value, source_type, downgraded_sources)
    """
    if not candidates:
        return None, "unknown", []

    # Authority hierarchy for each dimension type
    if dim_name == "width":
        authority_order = ["plan_view", "title_block", "site_plan", "elevation", "notes", "detail"]
    elif dim_name == "depth":
        authority_order = ["plan_view", "site_plan", "elevation", "notes", "detail"]
    elif dim_name == "height":
        authority_order = ["elevation", "notes", "plan_view", "detail"]
    else:
        authority_order = ["plan_view", "elevation", "notes", "detail"]

    # Group candidates by source type
    by_source: dict[str, list[tuple[float, DimensionSource]]] = {}
    for value, source in candidates:
        source_type = source.source_type
        if source_type not in by_source:
            by_source[source_type] = []
        by_source[source_type].append((value, source))

    # Find highest authority source
    selected_value: float | None = None
    selected_source_type: str = "unknown"
    downgraded: list[str] = []

    for source_type in authority_order:
        if source_type in by_source:
            # Check if values agree within 10%
            values = [v for v, _ in by_source[source_type]]
            if len(values) == 1:
                selected_value = values[0]
                selected_source_type = source_type
                break
            else:
                # Check agreement
                min_val = min(values)
                max_val = max(values)
                if min_val > 0:
                    diff_pct = abs(max_val - min_val) / min_val * 100
                    if diff_pct <= 10:
                        # Values agree, use average
                        selected_value = sum(values) / len(values)
                        selected_source_type = source_type
                        break
                    else:
                        # Conflict within same authority level - use first (log conflict)
                        selected_value = values[0]
                        selected_source_type = source_type
                        downgraded.append(f"{source_type}_{dim_name}_conflict")
                        break

    # Fallback: if no dimension selected from authority hierarchy, use first available candidate
    # This handles cases where source type is "unknown" or not in authority_order
    if selected_value is None and candidates:
        # Use the first candidate as fallback
        selected_value, fallback_source = candidates[0]
        selected_source_type = fallback_source.source_type
        # Mark that we used a fallback
        downgraded.append(f"fallback_{dim_name}_{selected_source_type}")

    # Mark lower authority sources as downgraded
    selected_index = authority_order.index(selected_source_type) if selected_source_type in authority_order else len(authority_order)
    for source_type in by_source:
        if source_type != selected_source_type:
            if source_type in authority_order:
                source_index = authority_order.index(source_type)
                if source_index > selected_index:
                    downgraded.append(f"{source_type}_{dim_name}")

    return selected_value, selected_source_type, downgraded

