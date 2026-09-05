"""Dimension Authority for rowhouse projects (Task 5).

Extracts building dimensions from drawings with explicit provenance.
If dimensions cannot be computed from evidence, returns null (no guessing).
"""

from typing import Any

from loguru import logger

from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.schemas.geometry_for_3d import Dimensions


def extract_rowhouse_dimensions(
    document_analysis: DocumentAnalysis,
    extraction_result: ExtractionResult | None = None,
) -> Dimensions | None:
    """
    Extract rowhouse dimensions with provenance tracking (Task 5).

    Rules:
    1. Prefer explicit callouts from extraction_result
    2. Else compute from plan view dimension strings if present
    3. Else keep null (don't invent)

    Args:
        document_analysis: Stage 1 document analysis
        extraction_result: Stage 2 extraction result (optional, may have explicit dimensions)

    Returns:
        Dimensions with provenance, or None if insufficient evidence
    """
    # Rule 1: Prefer explicit callouts from extraction_result
    if extraction_result and extraction_result.geometry_for_3d:
        dims = extraction_result.geometry_for_3d.dimensions
        if dims and dims.width and dims.depth and dims.height:
            logger.info(
                f"Using explicit dimensions from extraction: "
                f"W={dims.width}ft, D={dims.depth}ft, H={dims.height}ft"
            )
            return dims

    # Rule 2: Check document_analysis.key_dimensions (from Stage 1)
    if document_analysis.key_dimensions:
        key_dims = document_analysis.key_dimensions
        if key_dims.width and key_dims.depth and key_dims.height:
            # Collect page numbers from locators
            dimension_pages = set()
            for loc in document_analysis.where_scope_lives:
                if loc.page_number > 0:
                    dimension_pages.add(loc.page_number)
            for loc in document_analysis.where_quantities_live:
                if loc.page_number > 0:
                    dimension_pages.add(loc.page_number)

            dimensions = Dimensions(
                width=key_dims.width,
                depth=key_dims.depth,
                height=key_dims.height,
                evidence=key_dims.evidence or "From Stage 1 document analysis",
                computation_formula=None,  # Stage 1 doesn't compute, just identifies
                input_pages=sorted(list(dimension_pages)) if dimension_pages else [],
            )
            logger.info(
                f"Using dimensions from Stage 1 analysis: "
                f"W={dimensions.width}ft, D={dimensions.depth}ft, H={dimensions.height}ft"
            )
            return dimensions

    # Rule 3: If we have partial dimensions, return what we have (but log missing)
    if document_analysis.key_dimensions:
        key_dims = document_analysis.key_dimensions
        has_width = key_dims.width is not None
        has_depth = key_dims.depth is not None
        has_height = key_dims.height is not None

        if has_width or has_depth or has_height:
            dimension_pages = set()
            for loc in document_analysis.where_scope_lives:
                if loc.page_number > 0:
                    dimension_pages.add(loc.page_number)
            for loc in document_analysis.where_quantities_live:
                if loc.page_number > 0:
                    dimension_pages.add(loc.page_number)

            dimensions = Dimensions(
                width=key_dims.width,
                depth=key_dims.depth,
                height=key_dims.height,
                evidence=key_dims.evidence or "Partial dimensions from Stage 1",
                computation_formula=None,
                input_pages=sorted(list(dimension_pages)) if dimension_pages else [],
            )
            missing = []
            if not has_width:
                missing.append("width")
            if not has_depth:
                missing.append("depth")
            if not has_height:
                missing.append("height")
            logger.warning(
                f"Partial dimensions available (missing: {', '.join(missing)}): "
                f"W={dimensions.width}ft, D={dimensions.depth}ft, H={dimensions.height}ft"
            )
            return dimensions

    # Rule 4: No dimensions found - return None (don't invent)
    logger.info("No dimensions found in drawings - returning None (no guessing)")
    return None





