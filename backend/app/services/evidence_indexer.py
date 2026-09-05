"""Evidence indexer service (Phase 6.7).

Links bid line items and 3D zones to PDF pages/evidence.
Deterministic, no AI calls.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.schemas.evidence_index import (
    BidItemEvidence,
    DetailEvidence,
    EvidenceIndex,
    EvidenceReference,
    ZoneEvidence,
)


def _extract_evidence_from_quantity_evidence(quantity_evidence: dict[str, Any]) -> EvidenceReference | None:
    """Extract EvidenceReference from quantity_evidence dict."""
    if not quantity_evidence:
        return None

    page_number = quantity_evidence.get("page_number")
    if not page_number:
        return None

    return EvidenceReference(
        page_number=page_number,
        sheet_id=quantity_evidence.get("sheet_id"),
        evidence_snippet=quantity_evidence.get("evidence_snippet", ""),
        location_type=quantity_evidence.get("location_type"),
    )


def _link_zone_to_bid_items(
    zone_label: str | None, zone_type: str, bid_items: list[dict[str, Any]]
) -> list[int]:
    """Link a zone to bid items by keyword matching (deterministic)."""
    if not zone_label:
        return []

    zone_lower = zone_label.lower()
    linked_indices: list[int] = []

    # Keywords that might link zones to bid items
    keywords = zone_lower.split()

    for idx, bid_item in enumerate(bid_items):
        description_lower = bid_item.get("description", "").lower()
        division_lower = bid_item.get("division", "").lower()

        # Exact match on zone name
        if zone_lower in description_lower or description_lower in zone_lower:
            linked_indices.append(idx)
            continue

        # Keyword overlap (at least 2 words match)
        description_words = set(description_lower.split())
        zone_words = set(keywords)
        overlap = description_words.intersection(zone_words)
        if len(overlap) >= 2:
            linked_indices.append(idx)
            continue

        # Special cases: room types
        if zone_type == "room":
            room_keywords = ["room", "space", "area", zone_lower]
            if any(kw in description_lower for kw in room_keywords):
                linked_indices.append(idx)

    return linked_indices


def generate_evidence_index(
    project_id: str, output_dir: Path | None = None
) -> EvidenceIndex:
    """
    Generate evidence index from existing artifacts.

    Args:
        project_id: Project ID
        output_dir: Base output directory (default: Path("out"))

    Returns:
        EvidenceIndex with links to PDF pages

    Raises:
        FileNotFoundError: If required artifacts are missing
    """
    if output_dir is None:
        output_dir = Path("out")

    log_ctx = logger.bind(service="evidence_indexer", project_id=project_id)
    log_ctx.info("Generating evidence index")

    project_dir = output_dir / project_id

    # Load required artifacts
    bid_proposal_path = project_dir / "bid_proposal.json"
    if not bid_proposal_path.exists():
        raise FileNotFoundError(f"bid_proposal.json not found for {project_id}")

    model_3d_path = project_dir / "model_3d.json"
    if not model_3d_path.exists():
        raise FileNotFoundError(f"model_3d.json not found for {project_id}")

    extraction_path = project_dir / "extraction_result.json"
    if not extraction_path.exists():
        raise FileNotFoundError(f"extraction_result.json not found for {project_id}")

    costing_path = project_dir / "costing_result.json"
    if not costing_path.exists():
        raise FileNotFoundError(f"costing_result.json not found for {project_id}")

    # Load JSON files
    with open(bid_proposal_path, "r") as f:
        bid_proposal = json.load(f)

    with open(model_3d_path, "r") as f:
        model_3d = json.load(f)

    with open(extraction_path, "r") as f:
        extraction = json.load(f)

    with open(costing_path, "r") as f:
        costing = json.load(f)

    # Build bid item evidence
    bid_item_evidence: list[BidItemEvidence] = []
    bid_items = bid_proposal.get("line_items", [])

    # Map cost items to bid items by description
    cost_items_by_name: dict[str, dict[str, Any]] = {}
    for category in costing.get("breakdown_by_category", []):
        for item in category.get("items", []):
            cost_items_by_name[item.get("item_name", "")] = item

    for idx, bid_item in enumerate(bid_items):
        description = bid_item.get("description", "")
        cost_item = cost_items_by_name.get(description)

        evidence_refs: list[EvidenceReference] = []

        # Try to get evidence from cost item
        if cost_item:
            quantity_evidence = cost_item.get("quantity_evidence", {})
            if quantity_evidence:
                ev_ref = _extract_evidence_from_quantity_evidence(quantity_evidence)
                if ev_ref:
                    evidence_refs.append(ev_ref)

        # If no evidence from cost item, try to extract from basis
        if not evidence_refs:
            basis = bid_item.get("basis", "")
            # Look for page references in basis (e.g., "Page 5")
            # This is a fallback, not ideal but deterministic
            if "page" in basis.lower():
                # Try to extract page number (simple heuristic)
                words = basis.lower().split()
                for i, word in enumerate(words):
                    if word == "page" and i + 1 < len(words):
                        try:
                            page_num = int(words[i + 1])
                            evidence_refs.append(
                                EvidenceReference(
                                    page_number=page_num,
                                    evidence_snippet=basis,
                                )
                            )
                        except ValueError:
                            pass

        # If still no evidence, check extraction scope items
        if not evidence_refs:
            scope_items = extraction.get("scope_of_work", [])
            for scope_item in scope_items:
                if description.lower() in scope_item.get("item", "").lower():
                    evidence_refs.append(
                        EvidenceReference(
                            page_number=scope_item.get("page_number", 0),
                            sheet_id=scope_item.get("sheet_id"),
                            evidence_snippet=scope_item.get("evidence_snippet", ""),
                        )
                    )
                    break

        bid_item_evidence.append(
            BidItemEvidence(
                line_item_index=idx,
                division=bid_item.get("division", ""),
                description=description,
                evidence_references=evidence_refs,
                quantity_source=bid_item.get("quantity_source"),
                basis=bid_item.get("basis", ""),
            )
        )

    # Build zone evidence
    zone_evidence: list[ZoneEvidence] = []

    # Process work zones
    work_zones = model_3d.get("work_zones", [])
    for zone in work_zones:
        zone_id = zone.get("zone_name", "")
        zone_type = zone.get("zone_type", "work_zone")
        label = zone.get("zone_name", "")

        evidence_refs: list[EvidenceReference] = []

        # Get evidence from zone
        page_number = zone.get("page_number")
        if page_number:
            evidence_refs.append(
                EvidenceReference(
                    page_number=page_number,
                    evidence_snippet=zone.get("evidence", ""),
                )
            )

        # Phase 7.3: Link lintel and flashing bands to extraction evidence
        if "lintel" in label.lower() and extraction.get("lintels"):
            lintels_data = extraction.get("lintels", {}).get("lintels", [])
            for lintel_data in lintels_data:
                if lintel_data.get("lintel_id") in label:
                    evidence_refs.append(
                        EvidenceReference(
                            page_number=lintel_data.get("page_number", 0),
                            sheet_id=lintel_data.get("sheet_id"),
                            evidence_snippet=lintel_data.get("evidence_snippet", ""),
                            location_type="lintel_schedule",
                        )
                    )
                    if lintel_data.get("detail_reference"):
                        evidence_refs.append(
                            EvidenceReference(
                                page_number=lintel_data.get("page_number", 0),
                                evidence_snippet=f"See {lintel_data.get('detail_reference')}",
                                location_type="detail",
                            )
                        )
                    break

        if "flashing" in label.lower():
            # Link to opening or lintel evidence
            if extraction.get("openings"):
                openings_data = extraction.get("openings", {}).get("openings", [])
                for opening_data in openings_data:
                    if opening_data.get("opening_id") in label or opening_data.get("flashing_required"):
                        evidence_refs.append(
                            EvidenceReference(
                                page_number=opening_data.get("page_number", 0),
                                sheet_id=opening_data.get("sheet_id"),
                                evidence_snippet=opening_data.get("evidence_snippet", ""),
                                location_type="opening_detail",
                            )
                        )
                        if opening_data.get("detail_reference"):
                            evidence_refs.append(
                                EvidenceReference(
                                    page_number=opening_data.get("page_number", 0),
                                    evidence_snippet=f"See {opening_data.get('detail_reference')}",
                                    location_type="detail",
                                )
                            )
                        break

        # Link to bid items
        linked_bid_items = _link_zone_to_bid_items(label, zone_type, bid_items)

        zone_evidence.append(
            ZoneEvidence(
                zone_id=zone_id,
                zone_type=zone_type,
                label=label,
                evidence_references=evidence_refs,
                linked_bid_items=linked_bid_items,
            )
        )

    # Phase 7.3: Add opening → lintel → detail evidence links
    if extraction.get("openings"):
        openings_data = extraction.get("openings", {}).get("openings", [])
        for opening_data in openings_data:
            opening_id = opening_data.get("opening_id", "")
            if not opening_id:
                continue

            opening_refs: list[EvidenceReference] = [
                EvidenceReference(
                    page_number=opening_data.get("page_number", 0),
                    sheet_id=opening_data.get("sheet_id"),
                    evidence_snippet=opening_data.get("evidence_snippet", ""),
                    location_type=opening_data.get("source", "unknown"),
                )
            ]

            # Add detail reference if available
            if opening_data.get("detail_reference"):
                opening_refs.append(
                    EvidenceReference(
                        page_number=opening_data.get("page_number", 0),
                        evidence_snippet=f"See {opening_data.get('detail_reference')}",
                        location_type="detail",
                    )
                )

            # Link to associated lintel if available
            associated_lintel_id = opening_data.get("associated_lintel_id")
            if associated_lintel_id and extraction.get("lintels"):
                lintels_data = extraction.get("lintels", {}).get("lintels", [])
                lintel_data = next(
                    (l for l in lintels_data if l.get("lintel_id") == associated_lintel_id),
                    None,
                )
                if lintel_data:
                    opening_refs.append(
                        EvidenceReference(
                            page_number=lintel_data.get("page_number", 0),
                            sheet_id=lintel_data.get("sheet_id"),
                            evidence_snippet=f"Lintel {associated_lintel_id}: {lintel_data.get('evidence_snippet', '')}",
                            location_type="lintel_schedule",
                        )
                    )
                    if lintel_data.get("detail_reference"):
                        opening_refs.append(
                            EvidenceReference(
                                page_number=lintel_data.get("page_number", 0),
                                evidence_snippet=f"Lintel detail: {lintel_data.get('detail_reference')}",
                                location_type="detail",
                            )
                        )

            # Find matching bid items for this opening
            opening_bid_items = _link_zone_to_bid_items(
                f"{opening_data.get('opening_type', 'opening')} {opening_id}",
                "opening",
                bid_items,
            )

            zone_evidence.append(
                ZoneEvidence(
                    zone_id=opening_id,
                    zone_type="opening",
                    label=f"{opening_data.get('opening_type', 'opening').title()} {opening_id}",
                    evidence_references=opening_refs,
                    linked_bid_items=opening_bid_items,
                )
            )

    # Process building volumes (if they have evidence)
    buildings = model_3d.get("buildings", [])
    for building in buildings:
        building_id = building.get("building_id", "")
        if not building_id:
            continue

        evidence = building.get("evidence", "")
        if not evidence:
            continue

        # Try to extract page number from evidence (simple heuristic)
        page_number = None
        if "page" in evidence.lower():
            words = evidence.lower().split()
            for i, word in enumerate(words):
                if word == "page" and i + 1 < len(words):
                    try:
                        page_number = int(words[i + 1])
                    except ValueError:
                        pass

        evidence_refs: list[EvidenceReference] = []
        if page_number:
            evidence_refs.append(
                EvidenceReference(
                    page_number=page_number,
                    evidence_snippet=evidence,
                )
            )

        zone_evidence.append(
            ZoneEvidence(
                zone_id=building_id,
                zone_type="building_mass",
                label=building.get("building_id", ""),
                evidence_references=evidence_refs,
                linked_bid_items=[],  # Buildings don't typically link to bid items
            )
        )

    # Phase 7.4: Add detail evidence (Detail → zone → bid → page)
    detail_evidence: list[DetailEvidence] = []
    if extraction.get("detail_graph"):
        details_data = extraction.get("detail_graph", {}).get("details", [])
        
        # Get element → detail bindings
        from app.services.detail_binding import bind_details_to_elements
        element_to_details = bind_details_to_elements(extraction)
        
        # Reverse: detail → elements
        detail_to_elements: dict[str, list[str]] = {}
        for element_id, detail_ids in element_to_details.items():
            for detail_id in detail_ids:
                if detail_id not in detail_to_elements:
                    detail_to_elements[detail_id] = []
                detail_to_elements[detail_id].append(element_id)
        
        for detail_data in details_data:
            detail_id = detail_data.get("detail_id", "")
            if not detail_id:
                continue
            
            # Get evidence references
            detail_refs: list[EvidenceReference] = [
                EvidenceReference(
                    page_number=detail_data.get("page_number", 0),
                    sheet_id=detail_data.get("sheet_id"),
                    evidence_snippet=detail_data.get("evidence_snippet", ""),
                    location_type="detail",
                )
            ]
            
            # Link to zones
            linked_zones: list[str] = []
            linked_openings: list[str] = []
            if detail_id in detail_to_elements:
                for element_id in detail_to_elements[detail_id]:
                    # Check if it's a zone or opening
                    if element_id.startswith("zone_") or element_id.startswith("room_"):
                        linked_zones.append(element_id)
                    elif element_id.startswith("WIN-") or element_id.startswith("D-") or element_id.startswith("opening_"):
                        linked_openings.append(element_id)
            
            # Link to bid items (by keyword matching)
            linked_bid_items = _link_zone_to_bid_items(
                f"{detail_data.get('detail_type', 'detail')} {detail_data.get('detail_label', '')}",
                "detail",
                bid_items,
            )
            
            detail_evidence.append(
                DetailEvidence(
                    detail_id=detail_id,
                    detail_type=detail_data.get("detail_type", "other"),
                    sheet_id=detail_data.get("sheet_id", ""),
                    detail_label=detail_data.get("detail_label", ""),
                    evidence_references=detail_refs,
                    linked_zones=linked_zones,
                    linked_openings=linked_openings,
                    linked_bid_items=linked_bid_items,
                )
            )

    index = EvidenceIndex(
        project_id=project_id,
        bid_item_evidence=bid_item_evidence,
        zone_evidence=zone_evidence,
        detail_evidence=detail_evidence,  # Phase 7.4
        generated_at=datetime.utcnow().isoformat(),
    )

    log_ctx.info(
        f"Evidence index generated: {len(bid_item_evidence)} bid items, {len(zone_evidence)} zones, {len(detail_evidence)} details"
    )

    return index


def save_evidence_index(project_id: str, index: EvidenceIndex, output_dir: Path | None = None) -> Path:
    """Save evidence index to JSON file."""
    if output_dir is None:
        output_dir = Path("out")

    project_dir = output_dir / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    output_path = project_dir / "evidence_index.json"
    with open(output_path, "w") as f:
        json.dump(index.model_dump(), f, indent=2)

    logger.info(f"Saved evidence index to {output_path}")
    return output_path

