"""Institutional geometry builder for 3D model generation (Phase 4.5)."""

import math
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.schemas.institutional_geometry_for_3d import (
    BuildingMass,
    CoordinateSystem,
    EnvelopeLayer,
    FlashingBand,
    InstitutionalGeometryFor3D,
    LintelBand,
    OpeningCutout,
    RoofVolume,
    RoomZoneVolume,
    StructuralZone,
)
from app.schemas.model_3d import CrossSectionRegion
from app.schemas.site_context import SiteContext


def _safe_area(value: Any) -> float:
    """Convert an arbitrary area value to float, returning 0.0 on failure."""

    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def build_institutional_geometry(
    analysis: DocumentAnalysis,
    extraction: ExtractionResult,
    settings: Settings | None = None,
) -> InstitutionalGeometryFor3D:
    """
    Build institutional geometry for 3D model (Phase 4.5).

    Args:
        analysis: DocumentAnalysis from Stage 1
        extraction: ExtractionResult from Stage 2
        settings: Application settings (optional)

    Returns:
        InstitutionalGeometryFor3D with building masses and room zones
    """
    if settings is None:
        from app.core.config import Settings

        settings = Settings()

    log_ctx = logger.bind(stage="institutional_geometry_builder")
    log_ctx.info("Building institutional geometry for 3D model")

    missing_evidence: list[str] = []
    geometry_quality: str = "missing"

    # A) Build existing building mass
    existing_building = _build_existing_building(
        analysis, extraction, missing_evidence
    )

    # B) Build addition building mass if present
    addition_building = _build_addition_building(
        analysis, extraction, existing_building, missing_evidence
    )

    # C) Build room zones
    room_zones = _build_room_zones(
        extraction, existing_building, missing_evidence
    )

    # D) Build roof volumes (Phase 7.2)
    roof_volumes = _build_roof_volumes(extraction, existing_building, missing_evidence)

    # E) Build structural zones (Phase 7.2)
    structural_zones = _build_structural_zones(extraction, existing_building, missing_evidence)

    # F) Build envelope layers (Phase 7.2)
    envelope_layers = _build_envelope_layers(extraction, existing_building, missing_evidence)

    # G) Build opening cutouts (Phase 7.3)
    opening_cutouts = _build_opening_cutouts(extraction, existing_building, missing_evidence)

    # H) Build lintel bands (Phase 7.3)
    lintel_bands = _build_lintel_bands(extraction, existing_building, missing_evidence)

    # I) Build flashing bands (Phase 7.3)
    flashing_bands = _build_flashing_bands(extraction, existing_building, missing_evidence)

    # Determine geometry quality (Phase 7.2: check for envelope/roof)
    if existing_building.dimensions.get("width") and existing_building.dimensions.get("depth"):
        if addition_building and addition_building.dimensions.get("width"):
            geometry_quality = "authoritative"
        elif len(room_zones) >= 10:
            geometry_quality = "authoritative"
        else:
            # Check if envelope/roof exists but not in model (Phase 7.2)
            if extraction.building_envelope and extraction.building_envelope.roof_systems:
                if not roof_volumes:
                    geometry_quality = "partial"  # Envelope exists but not in model
                else:
                    geometry_quality = "authoritative"
            else:
                geometry_quality = "partial"
    elif existing_building.area_gsf > 0:
        geometry_quality = "derived_from_area"
    else:
        geometry_quality = "missing"

    coordinate_system = CoordinateSystem()

    return InstitutionalGeometryFor3D(
        coordinate_system=coordinate_system,
        existing_building=existing_building,
        addition_building=addition_building,
        room_zones=room_zones,
        roof_volumes=roof_volumes,
        structural_zones=structural_zones,
        envelope_layers=envelope_layers,
        opening_cutouts=opening_cutouts,
        lintel_bands=lintel_bands,
        flashing_bands=flashing_bands,
        geometry_quality=geometry_quality,
        missing_evidence=missing_evidence,
    )


def _build_existing_building(
    analysis: DocumentAnalysis,
    extraction: ExtractionResult,
    missing_evidence: list[str],
) -> BuildingMass:
    """Build existing building mass from authoritative dimensions or totals."""
    # A) Use authoritative dimensions if available
    auth_dims = extraction.authoritative_dimensions
    width_ft: float | None = None
    depth_ft: float | None = None
    height_ft: float | None = None

    if auth_dims:
        width_ft = auth_dims.width
        depth_ft = auth_dims.depth
        height_ft = auth_dims.height

    # Fallback to analysis/extraction dimensions
    if not width_ft and extraction.geometry_for_3d.dimensions:
        width_ft = extraction.geometry_for_3d.dimensions.width
    if not depth_ft and extraction.geometry_for_3d.dimensions:
        depth_ft = extraction.geometry_for_3d.dimensions.depth
    if not height_ft and extraction.geometry_for_3d.dimensions:
        height_ft = extraction.geometry_for_3d.dimensions.height

    # Get area from room program totals
    area_gsf = 0.0
    evidence_page = 1
    evidence_snippet = "Building dimensions from extraction"

    if extraction.room_program:
        room_program = extraction.room_program
        if room_program.totals.existing_gsf:
            area_gsf = room_program.totals.existing_gsf
            evidence_snippet = room_program.totals.existing_gsf_evidence or evidence_snippet
        elif room_program.totals.total_gsf:
            area_gsf = room_program.totals.total_gsf
            evidence_snippet = room_program.totals.total_gsf_evidence or evidence_snippet

        # Get page number from first room if available
        if room_program.rooms:
            evidence_page = room_program.rooms[0].page_number

    # If no dimensions but we have area, derive approximate dimensions
    if not width_ft or not depth_ft:
        if area_gsf > 0:
            # Use reasonable aspect ratio (1.5:1 for institutional buildings)
            aspect_ratio = 1.5
            depth_ft = math.sqrt(area_gsf / aspect_ratio)
            width_ft = area_gsf / depth_ft
            missing_evidence.append("footprint_dimensions_derived_from_area")
        else:
            missing_evidence.append("footprint_dimensions")
            missing_evidence.append("area_gsf")

    if not height_ft:
        missing_evidence.append("height")

    # Build bounding box
    bbox: dict[str, dict[str, float]] | None = None
    if width_ft and depth_ft and height_ft:
        bbox = {
            "min": {"x": 0.0, "y": 0.0, "z": 0.0},
            "max": {"x": width_ft, "y": depth_ft, "z": height_ft},
        }

    dimensions = {
        "width_ft": width_ft,
        "depth_ft": depth_ft,
        "height_ft": height_ft,
    }

    evidence = {
        "page_number": evidence_page,
        "evidence_snippet": evidence_snippet,
    }

    return BuildingMass(
        mass_id="existing_001",
        label="existing",
        dimensions=dimensions,
        area_gsf=area_gsf if area_gsf > 0 else (width_ft * depth_ft if width_ft and depth_ft else 0.0),
        bbox=bbox,
        placement={"x_offset_ft": 0.0, "y_offset_ft": 0.0, "relation": "adjacent_unknown"},
        evidence=evidence,
    )


def _build_addition_building(
    analysis: DocumentAnalysis,
    extraction: ExtractionResult,
    existing_building: BuildingMass,
    missing_evidence: list[str],
) -> BuildingMass | None:
    """Build addition building mass if addition GSF exists."""
    if not extraction.room_program:
        return None

    room_program = extraction.room_program
    addition_gsf = room_program.totals.addition_gsf

    if not addition_gsf or addition_gsf <= 0:
        return None

    # Try to get addition dimensions from drawings (placeholder - would need extraction)
    width_ft: float | None = None
    depth_ft: float | None = None
    height_ft: float | None = existing_building.dimensions.get("height_ft")

    # Derive from area if dimensions not available
    if not width_ft or not depth_ft:
        aspect_ratio = 1.5  # Configurable
        depth_ft = math.sqrt(addition_gsf / aspect_ratio)
        width_ft = addition_gsf / depth_ft
        missing_evidence.append("addition_dimensions_derived_from_area")

    # Build bounding box
    bbox: dict[str, dict[str, float]] | None = None
    if width_ft and depth_ft and height_ft:
        # Place adjacent to existing (default: east side)
        x_offset = existing_building.dimensions.get("width_ft", 0.0) or 0.0
        bbox = {
            "min": {"x": x_offset, "y": 0.0, "z": 0.0},
            "max": {"x": x_offset + width_ft, "y": depth_ft, "z": height_ft},
        }

    dimensions = {
        "width_ft": width_ft,
        "depth_ft": depth_ft,
        "height_ft": height_ft,
    }

    evidence_page = 1
    evidence_snippet = room_program.totals.addition_gsf_evidence or f"Addition {addition_gsf:.0f} GSF"
    if room_program.rooms:
        evidence_page = room_program.rooms[0].page_number

    evidence = {
        "page_number": evidence_page,
        "evidence_snippet": evidence_snippet,
    }

    return BuildingMass(
        mass_id="addition_001",
        label="addition",
        dimensions=dimensions,
        area_gsf=addition_gsf,
        bbox=bbox,
        placement={
            "x_offset_ft": existing_building.dimensions.get("width_ft", 0.0) or 0.0,
            "y_offset_ft": 0.0,
            "relation": "adjacent_unknown",
        },
        evidence=evidence,
    )


def _build_room_zones(
    extraction: ExtractionResult,
    existing_building: BuildingMass,
    missing_evidence: list[str],
) -> list[RoomZoneVolume]:
    """
    Build room zones (Phase 7.2).
    
    If building dimensions available: uses packing algorithm.
    If no dimensions: creates area-only prisms (derived_from_area quality).
    """
    # Try room_schedule first (Phase 7.1), then fall back to room_program
    rooms_to_use = []
    if extraction.room_schedule and extraction.room_schedule.rooms:
        # Convert RoomScheduleItem to RoomItem-like structure
        for room_item in extraction.room_schedule.rooms:
            # Create a simple dict-like structure
            rooms_to_use.append({
                "room_number": room_item.room_id,
                "room_name": room_item.room_name,
                "area_sf": _safe_area(room_item.area_sf),
                "floor": room_item.level,
                "page_number": room_item.evidence.page_number,
                "evidence_snippet": room_item.evidence.snippet,
            })
    elif extraction.room_program and extraction.room_program.rooms:
        # Use room_program (Phase 4.1)
        for room in extraction.room_program.rooms:
            rooms_to_use.append({
                "room_number": room.room_number,
                "room_name": room.room_name,
                "area_sf": _safe_area(room.area_sf),
                "floor": room.floor,
                "page_number": room.page_number,
                "evidence_snippet": room.evidence_snippet,
            })
    
    if not rooms_to_use:
        return []

    width_ft = existing_building.dimensions.get("width_ft")
    depth_ft = existing_building.dimensions.get("depth_ft")
    height_ft = existing_building.dimensions.get("height_ft") or 10.0  # Default height

    # If no building dimensions, create area-only prisms
    if not width_ft or not depth_ft:
        missing_evidence.append("room_layout_dimensions")
        return _build_area_only_prisms(rooms_to_use, height_ft, missing_evidence)

    # Sort rooms by area descending (largest first)
    rooms_with_area = []
    for room in rooms_to_use:
        area = _safe_area(room.get("area_sf"))
        if area > 0:
            rooms_with_area.append((room, area))
    rooms_with_area.sort(key=lambda x: x[1], reverse=True)

    if not rooms_with_area:
        missing_evidence.append("room_areas")
        return []

    # Pack rooms into 2D layout (shelf packing algorithm)
    room_zones: list[RoomZoneVolume] = []
    padding = 2.0  # Gap between rooms in feet
    current_x = padding
    current_y = padding
    current_row_height = 0.0
    max_y = 0.0

    for room, area_sf in rooms_with_area:
        # Calculate room dimensions (maintain reasonable aspect ratio)
        room_aspect = 1.5  # Prefer wider rooms
        room_depth = math.sqrt(area_sf / room_aspect)
        room_width = area_sf / room_depth

        # Check if room fits in current row
        if current_x + room_width + padding > width_ft - padding:
            # Move to next row
            current_y += current_row_height + padding
            current_x = padding
            current_row_height = 0.0

        # Ensure room fits in available space
        if room_width > width_ft - 2 * padding:
            room_width = width_ft - 2 * padding
            room_depth = area_sf / room_width

        if room_depth > depth_ft - current_y - padding:
            # Room too tall, scale it down
            scale = (depth_ft - current_y - padding) / room_depth
            room_depth *= scale
            room_width = area_sf / room_depth

        # Create bounding box
        bbox = {
            "min": {"x": current_x, "y": current_y, "z": 0.0},
            "max": {"x": current_x + room_width, "y": current_y + room_depth, "z": height_ft},
        }

        # Create zone
        zone_id = f"room_{room.get('room_number') or len(room_zones) + 1}"
        room_zone = RoomZoneVolume(
            room_number=room.get("room_number"),
            room_name=room.get("room_name", "Unknown"),
            area_sf=area_sf,
            floor=room.get("floor"),
            zone_id=zone_id,
            bbox=bbox,
            assignment_confidence=0.8 if room.get("area_sf") else 0.5,
            evidence={
                "page_number": room.get("page_number", 1),
                "evidence_snippet": room.get("evidence_snippet", "Room schedule"),
            },
            notes="layout unknown, packed by area for visualization",
        )

        room_zones.append(room_zone)

        # Update position for next room
        current_x += room_width + padding
        current_row_height = max(current_row_height, room_depth)
        max_y = max(max_y, current_y + room_depth)

    return room_zones


def _build_area_only_prisms(
    rooms: list[dict[str, Any]],
    default_height: float,
    missing_evidence: list[str],
) -> list[RoomZoneVolume]:
    """
    Build area-only room prisms when footprint evidence is unavailable (Phase 7.2).
    
    Creates simple rectangular prisms from area using stable heuristic.
    Marks geometry_quality as "derived_from_area" with clear notes.
    """
    room_zones: list[RoomZoneVolume] = []
    
    # Stable aspect ratio for area-only rooms (1.5:1 width:depth)
    aspect_ratio = 1.5
    
    # Stack rooms vertically (simple stacking, no spatial layout)
    z_offset = 0.0
    z_spacing = 0.1  # Small gap between stacked rooms
    
    for i, room in enumerate(rooms):
        area_sf = _safe_area(room.get("area_sf"))

        if area_sf <= 0:
            if "room_area_missing_or_invalid" not in missing_evidence:
                missing_evidence.append("room_area_missing_or_invalid")
            continue
        
        # Derive width/depth from area using aspect ratio
        depth_ft = math.sqrt(area_sf / aspect_ratio)
        width_ft = area_sf / depth_ft
        
        # Create bounding box (stacked vertically)
        bbox = {
            "min": {"x": 0.0, "y": 0.0, "z": z_offset},
            "max": {"x": width_ft, "y": depth_ft, "z": z_offset + default_height},
        }
        
        zone_id = f"room_{room.get('room_number') or i + 1}"
        room_zone = RoomZoneVolume(
            room_number=room.get("room_number"),
            room_name=room.get("room_name", "Unknown"),
            area_sf=area_sf,
            floor=room.get("floor"),
            zone_id=zone_id,
            bbox=bbox,
            assignment_confidence=0.7,  # Lower confidence for derived geometry
            evidence={
                "page_number": room.get("page_number", 1),
                "evidence_snippet": f"Room schedule area: {room.get('room_name')} ({area_sf:.0f} SF)",
            },
            notes=f"Area-only prism: footprint derived from area using {aspect_ratio}:1 aspect ratio. No layout evidence available.",
        )
        
        room_zones.append(room_zone)
        z_offset += default_height + z_spacing
    
    missing_evidence.append("room_footprints_derived_from_area_only")
    return room_zones


def _build_roof_volumes(
    extraction: ExtractionResult,
    existing_building: BuildingMass,
    missing_evidence: list[str],
) -> list[RoofVolume]:
    """Build roof volumes from building envelope extraction (Phase 7.2)."""
    if not extraction.building_envelope or not extraction.building_envelope.roof_systems:
        return []

    roof_volumes: list[RoofVolume] = []
    existing_bbox = existing_building.bbox

    if not existing_bbox:
        missing_evidence.append("roof_geometry_missing_building_dimensions")
        return []

    for roof in extraction.building_envelope.roof_systems:
        # Create roof volume above existing building
        roof_z_min = existing_bbox["max"]["z"]  # Top of building
        roof_z_max = roof_z_min + 1.0  # 1 ft roof thickness (default)
        parapet_z = roof_z_max
        if roof.parapet_height_ft:
            parapet_z = roof_z_max + roof.parapet_height_ft

        roof_bbox = {
            "min": {
                "x": existing_bbox["min"]["x"],
                "y": existing_bbox["min"]["y"],
                "z": roof_z_min,
            },
            "max": {
                "x": existing_bbox["max"]["x"],
                "y": existing_bbox["max"]["y"],
                "z": parapet_z,
            },
        }

        roof_volume = RoofVolume(
            roof_id=roof.roof_id or "roof_001",
            bbox=roof_bbox,
            parapet_height_ft=roof.parapet_height_ft,
            evidence={
                "page_number": roof.page_number,
                "evidence_snippet": roof.evidence_snippet,
            },
        )
        roof_volumes.append(roof_volume)

    return roof_volumes


def _build_structural_zones(
    extraction: ExtractionResult,
    existing_building: BuildingMass,
    missing_evidence: list[str],
) -> list[StructuralZone]:
    """Build structural zones from structural elements extraction (Phase 7.2)."""
    if not extraction.structural_elements or not extraction.structural_elements.elements:
        return []

    structural_zones: list[StructuralZone] = []
    existing_bbox = existing_building.bbox

    if not existing_bbox:
        missing_evidence.append("structural_zones_missing_building_dimensions")
        return []

    for element in extraction.structural_elements.elements:
        # Create bounding box from element dimensions
        if element.dimensions.width_ft and element.dimensions.depth_ft:
            # Place at building base (simplified)
            struct_bbox = {
                "min": {
                    "x": existing_bbox["min"]["x"],
                    "y": existing_bbox["min"]["y"],
                    "z": existing_bbox["min"]["z"],
                },
                "max": {
                    "x": existing_bbox["min"]["x"] + (element.dimensions.width_ft or 1.0),
                    "y": existing_bbox["min"]["y"] + (element.dimensions.depth_ft or 1.0),
                    "z": existing_bbox["min"]["z"] + (element.dimensions.height_ft or 10.0),
                },
            }

            struct_zone = StructuralZone(
                zone_id=element.element_id or f"{element.element_type}_001",
                element_type=element.element_type,  # type: ignore
                bbox=struct_bbox,
                evidence={
                    "page_number": element.page_number,
                    "evidence_snippet": element.evidence_snippet,
                },
            )
            structural_zones.append(struct_zone)

    return structural_zones


def _build_envelope_layers(
    extraction: ExtractionResult,
    existing_building: BuildingMass,
    missing_evidence: list[str],
) -> list[EnvelopeLayer]:
    """Build envelope layers from building envelope extraction (Phase 7.2)."""
    if not extraction.building_envelope:
        return []

    envelope_layers: list[EnvelopeLayer] = []
    existing_bbox = existing_building.bbox

    if not existing_bbox:
        missing_evidence.append("envelope_layers_missing_building_dimensions")
        return []

    # Create envelope layers from walls
    for wall in extraction.building_envelope.walls:
        if wall.height_ft and wall.length_ft:
            # Create wall layer (simplified - placed on building perimeter)
            wall_bbox = {
                "min": {
                    "x": existing_bbox["min"]["x"],
                    "y": existing_bbox["min"]["y"],
                    "z": existing_bbox["min"]["z"],
                },
                "max": {
                    "x": existing_bbox["min"]["x"] + 0.67,  # Wall thickness (8" CMU = 0.67 ft)
                    "y": existing_bbox["min"]["y"] + wall.length_ft,
                    "z": existing_bbox["min"]["z"] + wall.height_ft,
                },
            }

            env_layer = EnvelopeLayer(
                layer_id=wall.wall_id or "wall_001",
                layer_type="exterior_wall",
                bbox=wall_bbox,
                evidence={
                    "page_number": wall.page_number,
                    "evidence_snippet": wall.evidence_snippet,
                },
            )
            envelope_layers.append(env_layer)

    # Create parapet layer from roof parapet
    for roof in extraction.building_envelope.roof_systems:
        if roof.parapet_height_ft and roof.parapet_height_ft > 0:
            parapet_bbox = {
                "min": {
                    "x": existing_bbox["min"]["x"],
                    "y": existing_bbox["min"]["y"],
                    "z": existing_bbox["max"]["z"],
                },
                "max": {
                    "x": existing_bbox["max"]["x"],
                    "y": existing_bbox["max"]["y"],
                    "z": existing_bbox["max"]["z"] + roof.parapet_height_ft,
                },
            }

            env_layer = EnvelopeLayer(
                layer_id=f"parapet_{roof.roof_id or '001'}",
                layer_type="parapet",
                bbox=parapet_bbox,
                evidence={
                    "page_number": roof.page_number,
                    "evidence_snippet": roof.evidence_snippet,
                },
            )
            envelope_layers.append(env_layer)

    return envelope_layers


def _build_opening_cutouts(
    extraction: ExtractionResult,
    existing_building: BuildingMass,
    missing_evidence: list[str],
) -> list[OpeningCutout]:
    """Build opening cutouts from openings extraction (Phase 7.3)."""
    if not extraction.openings or not extraction.openings.openings:
        return []

    opening_cutouts: list[OpeningCutout] = []
    existing_bbox = existing_building.bbox

    if not existing_bbox:
        missing_evidence.append("opening_cutouts_missing_building_dimensions")
        return []

    for opening in extraction.openings.openings:
        # Create cutout bbox (simplified - placed on building face)
        if opening.width_ft and opening.height_ft:
            cutout_bbox = {
                "min": {
                    "x": existing_bbox["min"]["x"],
                    "y": existing_bbox["min"]["y"],
                    "z": existing_bbox["min"]["z"] + (opening.sill_height_ft or 0.0),
                },
                "max": {
                    "x": existing_bbox["min"]["x"] + opening.width_ft,
                    "y": existing_bbox["min"]["y"] + 0.67,  # Wall thickness
                    "z": existing_bbox["min"]["z"] + (opening.sill_height_ft or 0.0) + opening.height_ft,
                },
            }

            opening_cutout = OpeningCutout(
                opening_id=opening.opening_id or f"opening_{len(opening_cutouts) + 1}",
                opening_type=opening.opening_type,  # type: ignore
                bbox=cutout_bbox,
                evidence={
                    "page_number": opening.page_number,
                    "evidence_snippet": opening.evidence_snippet,
                },
            )
            opening_cutouts.append(opening_cutout)

    return opening_cutouts


def _build_lintel_bands(
    extraction: ExtractionResult,
    existing_building: BuildingMass,
    missing_evidence: list[str],
) -> list[LintelBand]:
    """Build lintel bands from lintels extraction (Phase 7.3)."""
    if not extraction.lintels or not extraction.lintels.lintels:
        return []

    lintel_bands: list[LintelBand] = []
    existing_bbox = existing_building.bbox

    if not existing_bbox:
        missing_evidence.append("lintel_bands_missing_building_dimensions")
        return []

    for lintel in extraction.lintels.lintels:
        if lintel.length_ft:
            lintel_bbox = {
                "min": {
                    "x": existing_bbox["min"]["x"],
                    "y": existing_bbox["min"]["y"],
                    "z": existing_bbox["min"]["z"] + (lintel.elevation_ft or 0.0),
                },
                "max": {
                    "x": existing_bbox["min"]["x"] + lintel.length_ft,
                    "y": existing_bbox["min"]["y"] + 0.67,  # Wall thickness
                    "z": existing_bbox["min"]["z"] + (lintel.elevation_ft or 0.0) + (lintel.height_ft or 0.5),
                },
            }

            lintel_band = LintelBand(
                lintel_id=lintel.lintel_id or f"lintel_{len(lintel_bands) + 1}",
                bbox=lintel_bbox,
                evidence={
                    "page_number": lintel.page_number,
                    "evidence_snippet": lintel.evidence_snippet,
                },
            )
            lintel_bands.append(lintel_band)

    return lintel_bands


def _build_flashing_bands(
    extraction: ExtractionResult,
    existing_building: BuildingMass,
    missing_evidence: list[str],
) -> list[FlashingBand]:
    """Build flashing bands from details extraction (Phase 7.3)."""
    if not hasattr(extraction, 'details') or not extraction.details or not extraction.details.details:
        return []

    flashing_bands: list[FlashingBand] = []
    existing_bbox = existing_building.bbox

    if not existing_bbox:
        missing_evidence.append("flashing_bands_missing_building_dimensions")
        return []

    # Create flashing bands from details (simplified)
    for detail in extraction.details.details:
        if "flashing" in detail.detail_type.lower() or "flashing" in (detail.title or "").lower():
            flashing_bbox = {
                "min": {
                    "x": existing_bbox["min"]["x"],
                    "y": existing_bbox["min"]["y"],
                    "z": existing_bbox["max"]["z"] - 1.0,  # Near roof level
                },
                "max": {
                    "x": existing_bbox["max"]["x"],
                    "y": existing_bbox["min"]["y"] + 0.67,  # Wall thickness
                    "z": existing_bbox["max"]["z"],
                },
            }

            flashing_band = FlashingBand(
                flashing_id=detail.detail_id or f"flashing_{len(flashing_bands) + 1}",
                bbox=flashing_bbox,
                evidence={
                    "page_number": detail.page_number,
                    "evidence_snippet": detail.evidence_snippet,
                },
            )
            flashing_bands.append(flashing_band)

    return flashing_bands

