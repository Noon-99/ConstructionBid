"""Critical-5 recovery strategy for Phase 2.5B.

Deterministically locates and re-reads pages to recover missing Critical-5 scope items.
"""

from loguru import logger

from app.analyzers.row_house_repair_extractor import RowHouseRepairExtractor
from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.schemas.page_index import PageIndex
from app.services.openai_client import OpenAIClient


def select_pages_for_missing_criticals(
    missing_items: list[str],
    page_index: PageIndex | None,
    analysis: DocumentAnalysis,
) -> list[int]:
    """
    Select pages for re-reading missing Critical-5 items.

    Args:
        missing_items: List of missing critical item codes (e.g., ['flashing', 'brick_or_repoint'])
        analysis: DocumentAnalysis from Stage 1
        page_index: PageIndex from Stage 0.5

    Returns:
        List of 0-indexed page numbers for re-read (max 4)
    """
    selected_pages: set[int] = set()

    # Map missing items to required indicators
    item_to_indicators: dict[str, list[str]] = {
        "parapet": ["parapet", "detail"],
        "lintel": ["lintel", "detail", "schedule"],
        "flashing": ["flashing", "detail"],
        "brick_or_repoint": ["detail", "notes"],
        "crack_repair": ["crack", "detail"],
    }

    # Use page_index if available
    if page_index and hasattr(page_index, "pages"):
        for page_item in page_index.pages:
            for missing_item in missing_items:
                if missing_item in item_to_indicators:
                    required_indicators = item_to_indicators[missing_item]

                    # Check if page has required indicators
                    has_indicators = any(
                        ind in page_item.indicators for ind in required_indicators
                    )
                    has_page_type = "detail" in page_item.page_types

                    if has_indicators or (has_page_type and "detail" in required_indicators):
                        selected_pages.add(page_item.page_number - 1)  # Convert to 0-indexed

    # Use Stage 1 locators as fallback
    for missing_item in missing_items:
        if missing_item in ["flashing", "brick_or_repoint", "crack_repair"]:
            # These are often in detail sheets or notes
            for locator in analysis.where_scope_lives:
                if locator.location_type in ["detail", "notes", "specification_section"]:
                    if locator.page_number > 0:
                        selected_pages.add(locator.page_number - 1)

    # Limit to max 4 pages, prefer detail pages
    result = sorted(list(selected_pages))[:4]

    return result


def recover_missing_criticals(
    project_id: str,
    extraction: ExtractionResult,
    missing_items: list[str],
    page_index: PageIndex | None,
    analysis: DocumentAnalysis,
    pdf_images: list[PdfPageImage],
    settings: Settings,
    openai_client: OpenAIClient,
) -> ExtractionResult:
    """
    Re-read pages to recover missing Critical-5 items.

    Args:
        project_id: Project ID
        extraction: Current ExtractionResult
        missing_items: List of missing critical item codes
        page_index: PageIndex from Stage 0.5
        analysis: DocumentAnalysis from Stage 1
        pdf_images: All PDF page images
        settings: Application settings
        openai_client: OpenAI client

    Returns:
        Updated ExtractionResult with recovered items merged
    """
    log_ctx = logger.bind(project_id=project_id, stage="critical_recovery")

    log_ctx.info(f"Recovering missing Critical-5 items: {missing_items}")

    # Select pages for re-read
    rerun_pages = select_pages_for_missing_criticals(missing_items, page_index, analysis)

    if not rerun_pages:
        log_ctx.warning("No pages selected for Critical-5 recovery")
        return extraction

    log_ctx.info(f"Re-reading {len(rerun_pages)} pages for missing items: {rerun_pages}")

    # Filter to selected pages
    rerun_page_images = [
        img for img in pdf_images if (img.page_number - 1) in rerun_pages
    ]

    if not rerun_page_images:
        log_ctx.warning("Could not load page images for re-read")
        return extraction

    # Create extractor for specialized re-read
    extractor = RowHouseRepairExtractor(settings, openai_client)

    # Perform targeted re-read for missing items only
    try:
        # Extract only missing categories
        recovered_result = extractor._extract_critical_items_only(
            pdf_images=rerun_page_images,
            missing_items=missing_items,
            project_id=project_id,
        )

        # Merge results additively (don't overwrite existing items)
        merged_extraction = _merge_extraction_results(extraction, recovered_result)

        log_ctx.info(
            f"Critical-5 recovery complete: recovered {len(recovered_result.scope_of_work)} items"
        )

        return merged_extraction

    except Exception as e:
        log_ctx.error(f"Critical-5 recovery failed: {e}")
        return extraction


def _merge_extraction_results(
    base: ExtractionResult, recovered: ExtractionResult
) -> ExtractionResult:
    """
    Merge recovered extraction results into base, additively.

    Does not overwrite existing items, only adds new ones.
    """
    # Merge scope_of_work (add new items, don't duplicate)
    existing_items = {item.item.lower() for item in base.scope_of_work}
    new_scope_items = [
        item for item in recovered.scope_of_work if item.item.lower() not in existing_items
    ]
    merged_scope = base.scope_of_work + new_scope_items

    # Merge material_specifications (add new materials)
    existing_materials = {
        mat.material_name.lower() for mat in base.material_specifications
    }
    new_materials = [
        mat
        for mat in recovered.material_specifications
        if mat.material_name.lower() not in existing_materials
    ]
    merged_materials = base.material_specifications + new_materials

    # Merge work zones (add new zones)
    existing_zones = {zone.zone_name.lower() for zone in base.geometry_for_3d.work_zones}
    new_zones = [
        zone
        for zone in recovered.geometry_for_3d.work_zones
        if zone.zone_name.lower() not in existing_zones
    ]
    merged_zones = base.geometry_for_3d.work_zones + new_zones

    # Update geometry
    updated_geometry = base.geometry_for_3d.model_copy()
    updated_geometry.work_zones = merged_zones

    # Create merged result
    merged = base.model_copy()
    merged.scope_of_work = merged_scope
    merged.material_specifications = merged_materials
    merged.geometry_for_3d = updated_geometry

    return merged

