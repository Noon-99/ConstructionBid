"""Material tagger service (Phase 10.5).

Deterministic mapping from extracted scope/detail_graph keywords to material tags.
"""

import re
from typing import TYPE_CHECKING, Optional

from loguru import logger

if TYPE_CHECKING:
    from app.schemas.extraction_result import ExtractionResult

# Material tag mapping rules (deterministic)
MATERIAL_KEYWORDS: dict[str, list[str]] = {
    "brick_veneer": [
        "brick",
        "brick veneer",
        "brickwork",
        "masonry",
        "exterior brick",
        "face brick",
    ],
    "cmu": [
        "cmu",
        "concrete block",
        "concrete masonry",
        "cinder block",
        "block",
    ],
    "steel": [
        "steel",
        "galvanized",
        "angle iron",
        "lintel",
        "steel lintel",
        "steel angle",
        "metal",
        "iron",
        "l-beam",
        "i-beam",
    ],
    "flashing": [
        "flashing",
        "metal flashing",
        "counterflashing",
        "step flashing",
        "base flashing",
    ],
    "coping": [
        "coping",
        "coping stone",
        "parapet coping",
        "roof coping",
    ],
    "mortar": [
        "mortar",
        "repoint",
        "repointing",
        "tuckpoint",
        "tuckpointing",
        "joint",
        "type n",
        "type s",
        "type m",
    ],
    "concrete": [
        "concrete",
        "poured concrete",
        "cast-in-place",
        "foundation",
        "footing",
        "slab",
    ],
    "wood": [
        "wood",
        "timber",
        "lumber",
        "framing",
        "wood frame",
    ],
    "insulation": [
        "insulation",
        "rigid insulation",
        "foam",
        "spray foam",
    ],
    "gypsum": [
        "gypsum",
        "drywall",
        "sheetrock",
        "gwb",
    ],
}


def tag_materials_for_zone(
    zone_name: str,
    zone_evidence: str,
    extraction_result: Optional["ExtractionResult"] = None,
) -> tuple[list[str], float]:
    """
    Tag materials for a work zone based on evidence and extraction results (Phase 10.5).

    Args:
        zone_name: Zone identifier (e.g., 'parapet_band', 'lintel_band')
        zone_evidence: Evidence text for the zone
        extraction_result: Optional extraction result for additional context

    Returns:
        Tuple of (material_tags list, confidence 0.0-1.0)
    """
    tags: set[str] = set()
    confidence = 0.5  # Base confidence

    # Combine all text sources
    text_sources: list[str] = [zone_name.lower(), zone_evidence.lower()]

    # Add scope items that match zone name
    if extraction_result:
        for scope_item in extraction_result.scope_of_work:
            if any(keyword in zone_name.lower() for keyword in scope_item.item.lower().split()):
                text_sources.append(scope_item.item.lower())
                text_sources.append(scope_item.description.lower())

        # Add material specifications
        for material_spec in extraction_result.material_specifications:
            text_sources.append(material_spec.material_name.lower())
            if material_spec.application:
                text_sources.append(material_spec.application.lower())

        # Add detail graph references if available
        if extraction_result.detail_graph and extraction_result.detail_graph.details:
            for detail in extraction_result.detail_graph.details:
                # Match detail refs that might apply to this zone
                if detail.detail_label:
                    text_sources.append(detail.detail_label.lower())
                if detail.detail_type:
                    text_sources.append(detail.detail_type.lower())

    # Check each material against text sources
    combined_text = " ".join(text_sources)

    for material_tag, keywords in MATERIAL_KEYWORDS.items():
        for keyword in keywords:
            # Use word boundary matching for better precision
            pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
            if re.search(pattern, combined_text, re.IGNORECASE):
                tags.add(material_tag)
                # Increase confidence if found in multiple sources
                if combined_text.count(keyword.lower()) > 1:
                    confidence = min(1.0, confidence + 0.1)

    # Zone name heuristics
    if "lintel" in zone_name.lower():
        tags.add("steel")  # Lintels are typically steel
        confidence = max(confidence, 0.7)
    if "parapet" in zone_name.lower() or "coping" in zone_name.lower():
        tags.add("brick_veneer")  # Parapets often brick
        tags.add("coping")  # Parapets have coping
        confidence = max(confidence, 0.6)
    if "flashing" in zone_name.lower():
        tags.add("flashing")
        confidence = max(confidence, 0.8)
    if "foundation" in zone_name.lower() or "footing" in zone_name.lower():
        tags.add("concrete")
        confidence = max(confidence, 0.7)
    if "masonry" in zone_name.lower() or "brick" in zone_name.lower():
        tags.add("brick_veneer")
        if "repoint" in combined_text or "mortar" in combined_text:
            tags.add("mortar")
        confidence = max(confidence, 0.6)

    # Default: if no tags found, infer from zone type
    if not tags:
        # Default material tags based on zone characteristics
        if "work_zone" in zone_name.lower() or "repair" in zone_name.lower():
            tags.add("brick_veneer")  # Default for repair zones
            tags.add("mortar")  # Often involves repointing
            confidence = 0.3  # Low confidence for defaults

    return (sorted(list(tags)), min(1.0, confidence))


def tag_materials_for_building(
    building_type: str,
    building_evidence: str,
    extraction_result: Optional["ExtractionResult"] = None,
) -> tuple[list[str], float]:
    """
    Tag materials for a building based on building type and evidence (Phase 10.5).

    Args:
        building_type: Building type (e.g., 'row_house', 'institutional')
        building_evidence: Evidence text for the building
        extraction_result: Optional extraction result for additional context

    Returns:
        Tuple of (material_tags list, confidence 0.0-1.0)
    """
    tags: set[str] = set()
    confidence = 0.6  # Base confidence

    # Building type defaults
    if building_type == "row_house":
        tags.add("brick_veneer")  # Row houses typically brick
        confidence = 0.7
    elif building_type == "institutional":
        # Institutional often has CMU or concrete
        tags.add("cmu")
        tags.add("concrete")
        confidence = 0.5

    # Check evidence text
    text_sources: list[str] = [building_evidence.lower()]

    if extraction_result:
        for material_spec in extraction_result.material_specifications:
            text_sources.append(material_spec.material_name.lower())

    combined_text = " ".join(text_sources)

    # Match material keywords
    for material_tag, keywords in MATERIAL_KEYWORDS.items():
        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
            if re.search(pattern, combined_text, re.IGNORECASE):
                tags.add(material_tag)
                confidence = min(1.0, confidence + 0.2)

    return (sorted(list(tags)), min(1.0, confidence))

