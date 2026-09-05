"""Detail binding service (Phase 7.4).

Binds geometry elements (zones, openings, structural elements) to construction details.
"""

from app.schemas.detail_graph import DetailGraph, DetailNode
from app.schemas.extraction_result import ExtractionResult


def bind_details_to_elements(
    extraction: ExtractionResult,
) -> dict[str, list[str]]:
    """
    Bind detail nodes to geometry elements.

    Args:
        extraction: Extraction result with detail_graph and geometry elements

    Returns:
        Dictionary mapping element IDs to list of detail IDs
    """
    bindings: dict[str, list[str]] = {}

    if not extraction.detail_graph or not extraction.detail_graph.details:
        return bindings

    # For each detail, bind to elements in applies_to
    for detail in extraction.detail_graph.details:
        for element_id in detail.applies_to:
            if element_id not in bindings:
                bindings[element_id] = []
            bindings[element_id].append(detail.detail_id)

    # Also bind by keyword matching (deterministic)
    # Zones → Details
    if extraction.institutional_geometry_for_3d:
        inst_geometry = extraction.institutional_geometry_for_3d
        
        # Parapet zones → parapet details
        parapet_zones = [
            z for z in inst_geometry.envelope_layers
            if z.layer_type == "parapet"
        ]
        parapet_details = [
            d for d in extraction.detail_graph.details
            if d.detail_type == "parapet"
        ]
        for zone in parapet_zones:
            for detail in parapet_details:
                if zone.layer_id not in bindings:
                    bindings[zone.layer_id] = []
                if detail.detail_id not in bindings[zone.layer_id]:
                    bindings[zone.layer_id].append(detail.detail_id)

        # Opening cutouts → window/lintel details
        if inst_geometry.opening_cutouts:
            window_details = [
                d for d in extraction.detail_graph.details
                if d.detail_type in ["window", "lintel"]
            ]
            for cutout in inst_geometry.opening_cutouts:
                for detail in window_details:
                    if cutout.opening_id not in bindings:
                        bindings[cutout.opening_id] = []
                    if detail.detail_id not in bindings[cutout.opening_id]:
                        bindings[cutout.opening_id].append(detail.detail_id)

    # Openings → Details
    if extraction.openings and extraction.openings.openings:
        window_details = [
            d for d in extraction.detail_graph.details
            if d.detail_type in ["window", "lintel"]
        ]
        for opening in extraction.openings.openings:
            for detail in window_details:
                if opening.opening_id not in bindings:
                    bindings[opening.opening_id] = []
                if detail.detail_id not in bindings[opening.opening_id]:
                    bindings[opening.opening_id].append(detail.detail_id)

    # Structural elements → Details
    if extraction.structural_elements and extraction.structural_elements.elements:
        foundation_details = [
            d for d in extraction.detail_graph.details
            if d.detail_type in ["foundation", "footing"]
        ]
        for element in extraction.structural_elements.elements:
            if element.element_type in ["footing", "slab"]:
                for detail in foundation_details:
                    element_id = element.element_id or f"{element.element_type}_{element.location}"
                    if element_id not in bindings:
                        bindings[element_id] = []
                    if detail.detail_id not in bindings[element_id]:
                        bindings[element_id].append(detail.detail_id)

    return bindings


def bind_details_to_cost_items(
    extraction: ExtractionResult,
    cost_items: list,
) -> list:
    """
    Bind detail references to cost items (Phase 7.4).

    Args:
        extraction: Extraction result with detail_graph
        cost_items: List of CostItem objects (or dicts)

    Returns:
        List of cost items with detail_refs populated
    """
    if not extraction.detail_graph or not extraction.detail_graph.details:
        return cost_items

    # Get element → detail bindings
    element_to_details = bind_details_to_elements(extraction)

    # Map scope items to details
    scope_to_details: dict[str, list[str]] = {}
    for scope_item in extraction.scope_of_work:
        # Try to match scope item to elements
        scope_key = scope_item.item.lower()
        
        # Match by keyword
        for detail in extraction.detail_graph.details:
            detail_keywords = [
                detail.detail_type,
                detail.sheet_id.lower(),
                detail.detail_label.lower(),
            ]
            if any(kw in scope_key for kw in detail_keywords):
                if scope_item.item not in scope_to_details:
                    scope_to_details[scope_item.item] = []
                if detail.detail_id not in scope_to_details[scope_item.item]:
                    scope_to_details[scope_item.item].append(detail.detail_id)

    # Add detail_refs to cost items
    # Map detail_id to DetailNode for downstream metadata
    detail_lookup = {
        detail.detail_id: detail for detail in extraction.detail_graph.details
    }

    for cost_item in cost_items:
        # Get cost item name/description
        item_name = cost_item.item_name if hasattr(cost_item, "item_name") else cost_item.get("item_name", "")
        
        # Match to scope items
        matched_detail_ids: list[str] | None = None
        for scope_item_name, detail_ids in scope_to_details.items():
            if scope_item_name.lower() in item_name.lower() or item_name.lower() in scope_item_name.lower():
                if hasattr(cost_item, "detail_refs"):
                    cost_item.detail_refs.extend(detail_ids)
                    matched_detail_ids = cost_item.detail_refs
                elif isinstance(cost_item, dict):
                    if "detail_refs" not in cost_item:
                        cost_item["detail_refs"] = []
                    cost_item["detail_refs"].extend(detail_ids)
                    matched_detail_ids = cost_item["detail_refs"]
                break

        # Enrich cost item notes with compliance references from bound details
        detail_ids_to_check: list[str] = []
        if matched_detail_ids is not None:
            detail_ids_to_check = list(matched_detail_ids)
        else:
            if hasattr(cost_item, "detail_refs"):
                detail_ids_to_check = list(cost_item.detail_refs)
            elif isinstance(cost_item, dict) and "detail_refs" in cost_item:
                detail_ids_to_check = list(cost_item["detail_refs"])

        if detail_ids_to_check:
            compliance_refs: set[str] = set()
            for detail_id in detail_ids_to_check:
                detail = detail_lookup.get(detail_id)
                if not detail:
                    continue
                compliance_refs.update(detail.compliance_references)

            if compliance_refs:
                compliance_note = "Compliance references: " + ", ".join(sorted(compliance_refs))
                if hasattr(cost_item, "notes"):
                    if compliance_note not in cost_item.notes:
                        cost_item.notes.append(compliance_note)
                elif isinstance(cost_item, dict):
                    cost_item.setdefault("notes", [])
                    if compliance_note not in cost_item["notes"]:
                        cost_item["notes"].append(compliance_note)

    return cost_items






