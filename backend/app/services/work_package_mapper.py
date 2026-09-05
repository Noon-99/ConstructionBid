"""Work package mapper service (Task 1).

Builds contractor-friendly work packages by aggregating technical zones
and line items into logical work packages.
"""

import re
from datetime import datetime
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal, BidLineItem
from app.schemas.evidence_index import EvidenceIndex
from app.schemas.model_3d import Model3D
from app.schemas.work_package_map import WorkPackage, WorkPackageMap


def _extract_root_scope_term(description: str) -> str | None:
    """
    Extract root scope term from a line item description.

    Examples:
        "Parapet repair and rebuild" -> "parapet"
        "Roof edge flashing installation" -> "flashing"
        "Brick repointing" -> "repointing"
        "Lintel replacement" -> "lintel"

    Args:
        description: Line item description

    Returns:
        Root scope term or None
    """
    desc_lower = description.lower()

    # Scope term keywords (in priority order - most specific first)
    scope_terms = {
        "parapet": ["parapet", "coping", "roof edge"],
        "flashing": ["flashing", "step flashing", "roof flashing"],
        "lintel": ["lintel", "steel lintel", "angle lintel"],
        "repointing": ["repoint", "re-point", "pointing", "tuckpoint", "tuck point"],
        "crack": ["crack repair", "crack", "epoxy", "stabil"],
        "brick": ["brick replacement", "brick rebuild", "veneer"],
    }

    for term, keywords in scope_terms.items():
        if any(keyword in desc_lower for keyword in keywords):
            return term

    return None


def _determine_trade(division: str, description: str) -> str:
    """
    Determine trade name from division and description.

    Args:
        division: CSI division
        description: Line item description

    Returns:
        Trade name
    """
    division_lower = division.lower()
    desc_lower = description.lower()

    if "04" in division_lower or "masonry" in division_lower or "brick" in desc_lower:
        return "Masonry"
    elif "05" in division_lower or "metals" in division_lower or "lintel" in desc_lower or "steel" in desc_lower:
        return "Metals"
    elif "07" in division_lower or "flashing" in desc_lower or "waterproof" in division_lower:
        return "Waterproofing"
    elif "concrete" in division_lower or "concrete" in desc_lower:
        return "Concrete"
    else:
        return "General"


def _assign_zones_to_package(
    package_scope_term: str,
    package_line_item_ids: list[str],
    model_3d: Model3D | None,
    zone_cost_map: dict[str, Any] | None,
    evidence_index: EvidenceIndex | None,
) -> list[str]:
    """
    Assign zones to a package based on scope term, evidence_index linkage, and zone_cost_map.

    Args:
        package_scope_term: Root scope term for the package
        package_line_item_ids: Line item IDs in this package
        model_3d: 3D model with zones
        zone_cost_map: Zone cost map (optional)
        evidence_index: Evidence index (optional)

    Returns:
        List of zone IDs
    """
    if not model_3d or not model_3d.work_zones:
        return []

    zone_ids: list[str] = []
    package_line_item_indices = [int(id) for id in package_line_item_ids if id.isdigit()]

    # Priority 1: Use evidence_index zone_evidence to find zones linked to package's line items
    if evidence_index and evidence_index.zone_evidence:
        for zone_evidence in evidence_index.zone_evidence:
            zone_id = zone_evidence.zone_id
            # Check if this zone has linked bid items that match our package
            linked_items = zone_evidence.linked_bid_items
            if linked_items:
                # If any linked item is in our package, include this zone
                if any(item_idx in package_line_item_indices for item_idx in linked_items):
                    zone_ids.append(zone_id)

    # Priority 2: Use zone_cost_map to find zones with costs from package's line items
    if zone_cost_map and zone_cost_map.get("zones"):
        for zone_data in zone_cost_map["zones"]:
            zone_id = zone_data.get("zone_id")
            if not zone_id or zone_id in zone_ids:
                continue
            # Check if zone's linked_line_item_ids overlap with package
            linked_item_ids = zone_data.get("linked_line_item_ids", [])
            if linked_item_ids:
                if any(item_idx in package_line_item_indices for item_idx in linked_item_ids):
                    zone_ids.append(zone_id)

    # Priority 3: Keyword fallback - match zones by name keywords
    if not zone_ids:
        scope_keywords = {
            "parapet": ["parapet", "coping", "roof"],
            "flashing": ["flash", "roof edge"],
            "lintel": ["lintel", "opening"],
            "repointing": ["facade", "wall", "repoint"],
            "crack": ["crack", "facade"],
            "brick": ["brick", "veneer", "facade"],
        }

        keywords = scope_keywords.get(package_scope_term, [])

        for zone in model_3d.work_zones:
            zone_name_lower = (zone.zone_name or "").lower()
            zone_id = zone.zone_name  # Use zone_name as zone_id

            if keywords:
                if any(keyword in zone_name_lower for keyword in keywords):
                    zone_ids.append(zone_id)

    return list(set(zone_ids))  # Dedupe


def map_work_packages(
    project_id: str,
    bid_proposal: BidProposal | dict[str, Any],
    model_3d: Model3D | dict[str, Any] | None = None,
    zone_cost_map: dict[str, Any] | None = None,
    evidence_index: EvidenceIndex | dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> WorkPackageMap:
    """
    Map zones and line items into contractor-friendly work packages.

    Args:
        project_id: Project ID
        bid_proposal: Bid proposal (BidProposal object or dict)
        model_3d: 3D model (optional)
        zone_cost_map: Zone cost map (optional)
        evidence_index: Evidence index (optional)
        settings: Application settings (optional)

    Returns:
        WorkPackageMap with grouped packages
    """
    log_ctx = logger.bind(project_id=project_id, service="work_package_mapper")
    log_ctx.info("Mapping work packages")

    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    # Convert to objects if dicts
    if isinstance(bid_proposal, dict):
        bid_proposal = BidProposal.model_validate(bid_proposal)

    if isinstance(model_3d, dict):
        model_3d = Model3D.model_validate(model_3d)

    if isinstance(evidence_index, dict):
        # Handle empty evidence_index gracefully
        if evidence_index:
            evidence_index = EvidenceIndex.model_validate(evidence_index)
        else:
            from datetime import datetime
            evidence_index = EvidenceIndex(
                project_id=project_id,
                generated_at=datetime.now().isoformat(),
                bid_item_evidence=[],
                zone_evidence=[],
                detail_evidence=[],
            )

    # Step 1: Seed packages from bid line items
    # Group line items by root scope term
    scope_term_to_items: dict[str, list[tuple[int, BidLineItem]]] = {}

    for idx, line_item in enumerate(bid_proposal.line_items):
        scope_term = _extract_root_scope_term(line_item.description)
        if scope_term:
            if scope_term not in scope_term_to_items:
                scope_term_to_items[scope_term] = []
            scope_term_to_items[scope_term].append((idx, line_item))
        else:
            # If no scope term found, create a generic package
            generic_term = "general"
            if generic_term not in scope_term_to_items:
                scope_term_to_items[generic_term] = []
            scope_term_to_items[generic_term].append((idx, line_item))

    log_ctx.debug(f"Found {len(scope_term_to_items)} package candidates from line items")

    # Step 2: Merge related scope terms (e.g., parapet + roof_edge flashing)
    # For now, keep them separate but we could merge if needed
    # This is where we'd implement: "parapet + roof_edge flashing → 'Parapet / Coping / Roof Edge'"

    # Step 3: Create work packages
    packages: list[WorkPackage] = []
    zone_to_package: dict[str, str] = {}
    line_item_to_package: dict[str, str] = {}

    package_id_counter = 1

    for scope_term, items in scope_term_to_items.items():
        if not items:
            continue

        # Get first item's division (use most common if multiple)
        divisions = [item[1].division for item in items]
        primary_division = max(set(divisions), key=divisions.count) if divisions else "Unknown"

        # Get first item's description for trade determination
        first_description = items[0][1].description
        trade = _determine_trade(primary_division, first_description)

        # Create package title
        # Convert scope_term to title (e.g., "parapet" -> "Parapet Work")
        title_map = {
            "parapet": "Parapet / Coping / Roof Edge",
            "flashing": "Flashing Installation",
            "lintel": "Lintel Replacement",
            "repointing": "Brick Repointing",
            "crack": "Crack Repair",
            "brick": "Brick Work / Veneer",
            "general": "General Work",
        }
        package_title = title_map.get(scope_term, scope_term.replace("_", " ").title() + " Work")

        # Aggregate costs
        total_cost = sum(item[1].total_cost for item in items)

        # Compute confidence (minimum of item confidences)
        confidences = [item[1].confidence for item in items if item[1].confidence is not None]
        package_confidence = min(confidences) if confidences else 0.7

        # Determine priority based on cost
        if total_cost > 20000:
            priority = "high"
        elif total_cost > 5000:
            priority = "medium"
        else:
            priority = "low"

        # Get member line item IDs
        line_item_ids = [str(idx) for idx, _ in items]

        # Assign zones to this package
        zone_ids = _assign_zones_to_package(
            scope_term, line_item_ids, model_3d, zone_cost_map, evidence_index
        )

        # Build basis_refs from line items (extract spec refs if available)
        basis_refs: list[str] = []
        for _, item in items:
            # Extract any spec references from basis field
            basis = item.basis or ""
            # Simple heuristic: look for patterns like "Detail 1/2", "Spec 04 21 13"
            spec_patterns = re.findall(r"(Detail\s+[\d/]+|Spec\s+[\d\s]+|Section\s+[\d.]+)", basis, re.IGNORECASE)
            basis_refs.extend(spec_patterns)

        # Remove duplicates
        basis_refs = list(set(basis_refs))

        # Create package ID
        package_id = f"package_{package_id_counter:03d}"
        package_id_counter += 1

        # Create package
        package = WorkPackage(
            id=package_id,
            title=package_title,
            division=primary_division,
            trade=trade,
            estimated_cost=total_cost,
            priority=priority,
            confidence=package_confidence,
            basis_refs=basis_refs,
            member_zone_ids=zone_ids,
            member_line_item_ids=line_item_ids,
        )

        packages.append(package)

        # Build lookup maps
        for zone_id in zone_ids:
            zone_to_package[zone_id] = package_id
        for line_item_id in line_item_ids:
            line_item_to_package[line_item_id] = package_id

        log_ctx.debug(
            f"Created package {package_id}: {package_title}, "
            f"{len(zone_ids)} zones, {len(line_item_ids)} line items, ${total_cost:,.2f}"
        )

    log_ctx.info(
        f"Created {len(packages)} work packages from {len(bid_proposal.line_items)} line items"
    )

    return WorkPackageMap(
        project_id=project_id,
        packages=packages,
        zone_to_package=zone_to_package,
        line_item_to_package=line_item_to_package,
        generated_at=datetime.now(),
    )

