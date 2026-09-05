"""Helper to convert structural elements and building envelope to scope items for costing (Phase 7.2)."""

from app.schemas.extraction_result import ScopeItem
from app.schemas.structural_elements import StructuralElement
from app.schemas.building_envelope import (
    BuildingEnvelopeResult,
    EnvelopeWall,
    FlashingSystem,
    Opening,
    RoofSystem,
)
from app.schemas.openings import OpeningDetail, OpeningsResult
from app.schemas.lintels import LintelDetail, LintelsResult


def convert_structural_elements_to_scope(
    structural_elements: list[StructuralElement],
) -> list[ScopeItem]:
    """
    Convert structural elements to scope items for costing.

    Args:
        structural_elements: List of structural elements

    Returns:
        List of ScopeItem objects
    """
    scope_items: list[ScopeItem] = []

    for element in structural_elements:
        # Create scope item description
        desc_parts = [element.element_type.replace("_", " ").title()]
        if element.element_id:
            desc_parts.append(f"({element.element_id})")
        if element.location:
            desc_parts.append(f"- {element.location}")
        if element.dimensions.section:
            desc_parts.append(f"Section: {element.dimensions.section}")

        description = " ".join(desc_parts)

        scope_item = ScopeItem(
            item=element.element_type,
            description=description,
            location=element.location or "Building",
            page_number=element.page_number,
            sheet_id=element.sheet_id,
            evidence_snippet=element.evidence_snippet,
        )
        scope_items.append(scope_item)

    return scope_items


def convert_building_envelope_to_scope(
    building_envelope: BuildingEnvelopeResult,
) -> list[ScopeItem]:
    """
    Convert building envelope elements to scope items for costing.

    Args:
        building_envelope: Building envelope extraction result

    Returns:
        List of ScopeItem objects
    """
    scope_items: list[ScopeItem] = []

    # Convert walls
    for wall in building_envelope.walls:
        desc_parts = [wall.wall_type.replace("_", " ").title()]
        if wall.material_spec:
            desc_parts.append(f"({wall.material_spec})")
        if wall.area_sf:
            desc_parts.append(f"- {wall.area_sf:.0f} SF")

        description = " ".join(desc_parts)

        scope_item = ScopeItem(
            item=f"{wall.wall_type} wall",
            description=description,
            location=wall.location or "Exterior",
            page_number=wall.page_number,
            sheet_id=wall.sheet_id,
            evidence_snippet=wall.evidence_snippet,
        )
        scope_items.append(scope_item)

    # Convert roof systems
    for roof in building_envelope.roof_systems:
        desc_parts = ["Roof System"]
        if roof.deck_type:
            desc_parts.append(f"Deck: {roof.deck_type}")
        if roof.membrane_type:
            desc_parts.append(f"Membrane: {roof.membrane_type}")
        if roof.area_sf:
            desc_parts.append(f"- {roof.area_sf:.0f} SF")
        if roof.parapet_height_ft:
            desc_parts.append(f"Parapet: {roof.parapet_height_ft:.1f} ft")

        description = " ".join(desc_parts)

        scope_item = ScopeItem(
            item="roof_system",
            description=description,
            location="Roof",
            page_number=roof.page_number,
            sheet_id=roof.sheet_id,
            evidence_snippet=roof.evidence_snippet,
        )
        scope_items.append(scope_item)

    # Convert flashing systems
    for flashing in building_envelope.flashing_systems:
        desc_parts = [flashing.flashing_type.replace("_", " ").title()]
        if flashing.material:
            desc_parts.append(f"({flashing.material})")
        if flashing.length_lf:
            desc_parts.append(f"- {flashing.length_lf:.0f} LF")

        description = " ".join(desc_parts)

        scope_item = ScopeItem(
            item=f"{flashing.flashing_type} flashing",
            description=description,
            location=flashing.location or "Building",
            page_number=flashing.page_number,
            sheet_id=flashing.sheet_id,
            evidence_snippet=flashing.evidence_snippet,
        )
        scope_items.append(scope_item)

    # Convert openings (simplified - just count)
    for opening in building_envelope.openings:
        if opening.count and opening.count > 0:
            desc_parts = [opening.opening_type.title()]
            if opening.type_description:
                desc_parts.append(f"({opening.type_description})")
            desc_parts.append(f"- {opening.count} EA")
            if opening.size:
                desc_parts.append(f"Size: {opening.size}")

            description = " ".join(desc_parts)

            scope_item = ScopeItem(
                item=f"{opening.opening_type} opening",
                description=description,
                location=opening.location or "Building",
                page_number=opening.page_number,
                sheet_id=opening.sheet_id,
                evidence_snippet=opening.evidence_snippet,
            )
            scope_items.append(scope_item)

    return scope_items


def convert_openings_to_scope(
    openings: OpeningsResult,
) -> list[ScopeItem]:
    """
    Convert openings to scope items for costing (Phase 7.3).

    Args:
        openings: Openings extraction result

    Returns:
        List of ScopeItem objects
    """
    scope_items: list[ScopeItem] = []

    for opening in openings.openings:
        # Determine if replacement or new install (simplified - assume new if not specified)
        item_name = f"{opening.opening_type} new install"
        if "replace" in opening.evidence_snippet.lower():
            item_name = f"{opening.opening_type} replacement"

        desc_parts = [opening.opening_type.title()]
        if opening.material:
            desc_parts.append(f"({opening.material})")
        if opening.size:
            desc_parts.append(f"Size: {opening.size}")
        elif opening.width_ft and opening.height_ft:
            desc_parts.append(f"{opening.width_ft:.1f}' x {opening.height_ft:.1f}'")
        if opening.level:
            desc_parts.append(f"Level: {opening.level}")

        description = " ".join(desc_parts)

        scope_item = ScopeItem(
            item=item_name,
            description=description,
            location=opening.level or "Building",
            page_number=opening.page_number,
            sheet_id=opening.sheet_id,
            evidence_snippet=opening.evidence_snippet,
        )
        scope_items.append(scope_item)

    return scope_items


def convert_lintels_to_scope(
    lintels: LintelsResult,
) -> list[ScopeItem]:
    """
    Convert lintels to scope items for costing (Phase 7.3).

    Args:
        lintels: Lintels extraction result

    Returns:
        List of ScopeItem objects
    """
    scope_items: list[ScopeItem] = []

    for lintel in lintels.lintels:
        desc_parts = [lintel.lintel_type.replace("_", " ").title()]
        if lintel.section:
            desc_parts.append(f"({lintel.section})")
        if lintel.material_spec:
            desc_parts.append(f"Material: {lintel.material_spec}")
        if lintel.span_ft:
            desc_parts.append(f"Span: {lintel.span_ft:.1f}'")

        description = " ".join(desc_parts)

        scope_item = ScopeItem(
            item="steel lintel install",  # Default to steel lintel rule
            description=description,
            location="Above openings",
            page_number=lintel.page_number,
            sheet_id=lintel.sheet_id,
            evidence_snippet=lintel.evidence_snippet,
        )
        scope_items.append(scope_item)

        # Add flashing if required
        if lintel.flashing_required:
            flashing_desc = f"Flashing for lintel {lintel.lintel_id}"
            if lintel.span_ft:
                flashing_desc += f" ({lintel.span_ft:.1f} LF)"
            
            flashing_item = ScopeItem(
                item="flashing per opening",
                description=flashing_desc,
                location="At lintel",
                page_number=lintel.page_number,
                sheet_id=lintel.sheet_id,
                evidence_snippet=lintel.evidence_snippet,
            )
            scope_items.append(flashing_item)

    return scope_items

