"""Assembly builder service (Phase 14.1-B).

Builds construction system assemblies from existing artifacts by grouping
related line items into logical construction systems.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal, BidLineItem
from app.schemas.evidence_index import EvidenceIndex, EvidenceReference
from app.schemas.model_3d import Model3D, WorkZoneVolume
from app.schemas.construction_system_assembly import (
    ConstructionSystemAssembly,
    ConstructionSystemsResult,
    CostSummary,
    QuantitySummary,
    SystemSubcomponent,
)


def _match_line_item_to_system(
    line_item: BidLineItem, system_type: str
) -> tuple[bool, str | None]:
    """
    Determine if a line item belongs to a construction system.

    Args:
        line_item: Bid line item
        system_type: System type (e.g., 'parapet_reconstruction', 'lintel_replacement')

    Returns:
        Tuple of (matches, subcomponent_category)
    """
    desc_lower = line_item.description.lower()
    division_lower = (line_item.division or "").lower()

    # System type to keyword mapping
    system_keywords = {
        "parapet_reconstruction": ["parapet", "coping", "roof edge"],
        "lintel_replacement": ["lintel", "steel angle", "angle lintel"],
        "flashing_installation": ["flash", "flashing", "step flashing"],
        "brick_repointing": ["repoint", "re-point", "pointing", "tuckpoint", "tuck point"],
        "crack_repair": ["crack", "epoxy", "stabil", "injection"],
        "facade_rebuild": ["facade", "veneer rebuild", "veneer replacement", "brick replacement"],
    }

    # Subcomponent category mapping
    category_keywords = {
        "demolition": ["remove", "demolish", "take down", "cut out"],
        "structure": ["rebuild", "replace", "install", "construct", "build"],
        "waterproofing": ["waterproof", "membrane", "sealant", "seal"],
        "finish": ["finish", "paint", "clean", "restore"],
        "qa": ["inspection", "test", "verify", "qc"],
        "access": ["scaffold", "access", "protection"],
    }

    keywords = system_keywords.get(system_type, [])
    if not keywords:
        return False, None

    # Check if description matches system
    matches_system = any(keyword in desc_lower for keyword in keywords)

    if not matches_system:
        return False, None

    # Determine subcomponent category
    category = None
    for cat, cat_keywords in category_keywords.items():
        if any(cat_kw in desc_lower for cat_kw in cat_keywords):
            category = cat
            break

    # Default category if not matched
    if category is None:
        # Default based on system type and division
        if "demolition" in division_lower or "demo" in desc_lower:
            category = "demolition"
        elif "04" in division_lower or "masonry" in division_lower:
            category = "structure"
        elif "07" in division_lower or "waterproof" in division_lower:
            category = "waterproofing"
        else:
            category = "other"

    return True, category


def _get_zones_for_line_item(
    line_item: BidLineItem, model_3d: Model3D | None
) -> list[str]:
    """
    Get zone IDs from model_3d that match a line item.

    Args:
        line_item: Bid line item
        model_3d: 3D model with zones

    Returns:
        List of zone IDs
    """
    if not model_3d or not model_3d.work_zones:
        return []

    desc_lower = line_item.description.lower()
    zone_ids: list[str] = []

    for zone in model_3d.work_zones:
        zone_name_lower = (zone.zone_name or "").lower()
        zone_type_lower = (zone.zone_type or "").lower()

        # Match based on zone name/type and item description
        if "parapet" in desc_lower and "parapet" in zone_name_lower:
            zone_ids.append(zone.zone_id)
        elif "lintel" in desc_lower and ("lintel" in zone_name_lower or "opening" in zone_type_lower):
            zone_ids.append(zone.zone_id)
        elif "flashing" in desc_lower and ("flashing" in zone_name_lower or "roof" in zone_type_lower):
            zone_ids.append(zone.zone_id)
        elif "repoint" in desc_lower and "facade" in zone_name_lower:
            zone_ids.append(zone.zone_id)

    return list(set(zone_ids))  # Dedupe


def _get_evidence_refs_for_line_item(
    line_item_index: int, evidence_index: EvidenceIndex | None
) -> list[EvidenceReference]:
    """
    Get evidence references for a line item.

    Args:
        line_item_index: Index of line item in bid_proposal
        evidence_index: Evidence index artifact

    Returns:
        List of evidence references
    """
    if not evidence_index or not evidence_index.bid_item_evidence:
        return []

    for bid_evidence in evidence_index.bid_item_evidence:
        if bid_evidence.line_item_index == line_item_index:
            return bid_evidence.evidence_references

    return []


def build_construction_systems(
    project_id: str,
    bid_proposal: BidProposal | dict[str, Any],
    model_3d: Model3D | dict[str, Any] | None = None,
    evidence_index: EvidenceIndex | dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> ConstructionSystemsResult:
    """
    Build construction system assemblies from bid proposal.

    Args:
        project_id: Project ID
        bid_proposal: Bid proposal (BidProposal object or dict)
        model_3d: 3D model (optional)
        evidence_index: Evidence index (optional)
        settings: Application settings (optional)

    Returns:
        ConstructionSystemsResult with grouped systems
    """
    log_ctx = logger.bind(project_id=project_id, service="assembly_builder")
    log_ctx.info("Building construction system assemblies")

    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    # Convert to objects if dicts
    if isinstance(bid_proposal, dict):
        bid_proposal = BidProposal.model_validate(bid_proposal)

    if isinstance(model_3d, dict):
        from app.schemas.model_3d import Model3D

        model_3d = Model3D.model_validate(model_3d)

    if isinstance(evidence_index, dict):
        evidence_index = EvidenceIndex.model_validate(evidence_index)

    # System types to build
    system_types = [
        "parapet_reconstruction",
        "lintel_replacement",
        "flashing_installation",
        "brick_repointing",
        "crack_repair",
        "facade_rebuild",
    ]

    systems: list[ConstructionSystemAssembly] = []
    processed_item_indices: set[int] = set()

    # Build systems for each system type
    for system_type in system_types:
        matching_items: list[tuple[int, BidLineItem]] = []
        subcomponent_map: dict[str, list[int]] = {}

        # Find all line items that match this system
        for idx, line_item in enumerate(bid_proposal.line_items):
            matches, category = _match_line_item_to_system(line_item, system_type)
            if matches:
                matching_items.append((idx, line_item))
                if category:
                    if category not in subcomponent_map:
                        subcomponent_map[category] = []
                    subcomponent_map[category].append(idx)

        if not matching_items:
            continue

        # Get all zones for this system
        all_zones: set[str] = set()
        for idx, line_item in matching_items:
            zones = _get_zones_for_line_item(line_item, model_3d)
            all_zones.update(zones)

        # Get all divisions
        all_divisions: set[str] = set()
        for idx, line_item in matching_items:
            if line_item.division:
                all_divisions.add(line_item.division)

        # Aggregate quantities
        primary_qty = 0.0
        primary_unit = ""
        secondary_quantities: dict[str, float] = {}

        for idx, line_item in matching_items:
            if line_item.quantity:
                # Use first unit as primary
                if not primary_unit:
                    primary_unit = line_item.unit or ""
                    primary_qty = line_item.quantity
                elif line_item.unit == primary_unit:
                    primary_qty += line_item.quantity
                else:
                    # Add to secondary quantities
                    unit = line_item.unit or "EA"
                    secondary_quantities[unit] = secondary_quantities.get(unit, 0.0) + line_item.quantity

        # Aggregate costs
        # Note: BidLineItem only has total_cost, not material/labor/equipment breakdown
        # We'll use total_cost and split heuristically, or try to load from costing_result
        total_cost = 0.0
        for idx, line_item in matching_items:
            total_cost += line_item.total_cost

        # Heuristic split if we can't get breakdown (typical construction: 40% material, 50% labor, 10% equipment)
        # This is approximate - ideally we'd load costing_result.json for accurate breakdown
        material_cost = total_cost * 0.4
        labor_cost = total_cost * 0.5
        equipment_cost = total_cost * 0.1

        # Get all evidence refs
        all_evidence_refs: list[EvidenceReference] = []
        for idx, _ in matching_items:
            refs = _get_evidence_refs_for_line_item(idx, evidence_index)
            all_evidence_refs.extend(refs)

        # Compute confidence (minimum of item confidences, or default)
        confidences = [
            item.confidence for idx, item in matching_items if item.confidence is not None
        ]
        system_confidence = min(confidences) if confidences else 0.7

        # Build subcomponents
        subcomponents: list[SystemSubcomponent] = []
        for category, item_indices in subcomponent_map.items():
            descriptions = [
                bid_proposal.line_items[idx].description for idx in item_indices if idx < len(bid_proposal.line_items)
            ]
            subcomponents.append(
                SystemSubcomponent(
                    category=category,  # type: ignore
                    description="; ".join(descriptions[:3]),  # First 3 descriptions
                    line_item_ids=[str(idx) for idx in item_indices],
                )
            )

        # Create system ID
        system_id = f"{system_type}_{len(systems) + 1:03d}"

        # Create system description
        system_descriptions = {
            "parapet_reconstruction": "Parapet reconstruction and repair",
            "lintel_replacement": "Lintel replacement",
            "flashing_installation": "Flashing installation",
            "brick_repointing": "Brick repointing/tuckpointing",
            "crack_repair": "Crack repair and stabilization",
            "facade_rebuild": "Facade/veneer rebuild",
        }
        system_description = system_descriptions.get(
            system_type, f"{system_type.replace('_', ' ').title()}"
        )

        # Create assembly
        system = ConstructionSystemAssembly(
            id=system_id,
            system_type=system_type,
            description=system_description,
            zones=list(all_zones),
            source_divisions=list(all_divisions),
            base_scope_items=[str(idx) for idx, _ in matching_items],
            subcomponents=subcomponents,
            quantities=QuantitySummary(
                primary_quantity=primary_qty,
                primary_unit=primary_unit or "EA",
                secondary_quantities=secondary_quantities,
            ),
            cost_summary=CostSummary(
                material_cost=material_cost,
                labor_cost=labor_cost,
                equipment_cost=equipment_cost,
                total_cost=total_cost,
            ),
            evidence_refs=all_evidence_refs,
            confidence=system_confidence,
        )

        systems.append(system)
        processed_item_indices.update(idx for idx, _ in matching_items)

        log_ctx.debug(
            f"Built system {system_id}: {len(matching_items)} items, "
            f"${total_cost:,.2f} total, {len(all_zones)} zones"
        )

    log_ctx.info(f"Built {len(systems)} construction systems from {len(bid_proposal.line_items)} line items")

    return ConstructionSystemsResult(
        project_id=project_id,
        systems=systems,
        generated_at=datetime.now(),
    )

