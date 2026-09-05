"""General conditions estimator service (Phase 10.1).

Deterministically generates general conditions line items based on
building type, height, region, scope triggers, and estimated duration.
"""

from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal
from app.schemas.general_conditions import (
    GeneralConditions,
    GeneralConditionsItem,
)
from app.schemas.model_3d import Model3D
from app.services.region_resolver import resolve_region


# Regional multipliers for GC costs (higher for high-cost markets)
REGIONAL_GC_MULTIPLIERS: dict[str, float] = {
    "NYC": 1.4,  # NYC is high-cost
    "NJ": 1.15,  # NJ is moderate-high
    "CA": 1.35,  # California is high-cost
    "TX": 1.05,  # Texas is moderate
    "PA": 1.1,  # Pennsylvania is moderate
    "FL": 1.1,  # Florida is moderate
    "US_DEFAULT": 1.0,  # Baseline
}

# Duration estimation heuristics (weeks based on project scope)
# This is a simple heuristic - in future could use labor breakdown
DURATION_HEURISTICS: dict[str, float] = {
    "small_repair": 2.0,  # Small repairs: 2 weeks
    "medium_repair": 4.0,  # Medium repairs: 4 weeks
    "large_repair": 8.0,  # Large repairs: 8 weeks
    "institutional": 12.0,  # Institutional projects: 12 weeks
}


def _estimate_duration(
    bid_proposal: BidProposal,
    building_type: str,
    document_analysis: dict[str, Any] | None = None,
    extraction_result: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> float:
    """
    Estimate project duration in weeks.

    Task 7: For roofing projects, estimate duration from roof_area_sf / production_rate_sf_per_day.
    For other projects, use cost-based heuristics.

    Args:
        bid_proposal: Bid proposal with line items
        building_type: Building type
        document_analysis: Document analysis (optional, for primary_trade detection)
        extraction_result: Extraction result (optional, for roof_area_sf)
        settings: Application settings (optional, for production_rate_sf_per_day)

    Returns:
        Estimated duration in weeks
    """
    # Task 7: For roofing projects, estimate duration from roof area and production rate
    primary_trade = None
    if document_analysis:
        primary_trade = document_analysis.get("primary_trade")
    
    if primary_trade == "roofing":
        # Extract roof area from extraction_result or bid_proposal
        roof_area_sf = None
        
        # Try extraction_result first
        if extraction_result:
            # Check quantity_takeoff for roof area
            quantity_takeoff = extraction_result.get("quantity_takeoff", [])
            for qty in quantity_takeoff:
                item_lower = (qty.get("item", "") if isinstance(qty, dict) else getattr(qty, "item", "")).lower()
                unit_lower = (qty.get("unit", "") if isinstance(qty, dict) else getattr(qty, "unit", "")).lower()
                if "roof" in item_lower and ("sf" in unit_lower or "sq ft" in unit_lower):
                    roof_area_sf = qty.get("quantity") if isinstance(qty, dict) else getattr(qty, "quantity", None)
                    break
            
            # Check geometry_for_3d work_zones
            if not roof_area_sf:
                geometry = extraction_result.get("geometry_for_3d")
                if geometry:
                    work_zones = geometry.get("work_zones", [])
                    for zone in work_zones:
                        zone_name_lower = (zone.get("zone_name", "") if isinstance(zone, dict) else getattr(zone, "zone_name", "")).lower()
                        if "roof" in zone_name_lower:
                            roof_area_sf = zone.get("area") if isinstance(zone, dict) else getattr(zone, "area", None)
                            break
        
        # Fallback: check bid_proposal line items for roof area
        if not roof_area_sf:
            for item in bid_proposal.line_items:
                desc_lower = item.description.lower()
                if "roof" in desc_lower and item.quantity and item.unit and "sf" in item.unit.lower():
                    roof_area_sf = item.quantity
                    break
        
        # If roof area found, calculate duration from production rate
        if roof_area_sf and roof_area_sf > 0:
            production_rate_sf_per_day = 1000.0  # Default
            if settings and hasattr(settings, "roofing_production_rate_sf_per_day"):
                production_rate_sf_per_day = settings.roofing_production_rate_sf_per_day
            
            # Calculate duration: roof_area_sf / production_rate_sf_per_day = days
            # Convert to weeks (assume 5 working days per week)
            duration_days = roof_area_sf / production_rate_sf_per_day
            duration_weeks = duration_days / 5.0  # 5 working days per week
            
            # Add buffer for weather, setup, cleanup (20% buffer)
            duration_weeks = duration_weeks * 1.2
            
            # Minimum 1 week, round to 0.5 weeks
            duration_weeks = max(1.0, round(duration_weeks * 2) / 2)
            
            logger.info(
                f"Roofing project duration estimated: {roof_area_sf:.0f} SF / {production_rate_sf_per_day:.0f} SF/day = "
                f"{duration_days:.1f} days = {duration_weeks:.1f} weeks (with 20% buffer)"
            )
            
            return duration_weeks
    
    # Fallback: Simple heuristic based on total cost (for non-roofing or if roof area not found)
    total_cost = bid_proposal.summary.total_cost

    if building_type == "institutional":
        return DURATION_HEURISTICS["institutional"]

    if total_cost < 50000:
        return DURATION_HEURISTICS["small_repair"]
    elif total_cost < 150000:
        return DURATION_HEURISTICS["medium_repair"]
    else:
        return DURATION_HEURISTICS["large_repair"]


def _get_building_height(model_3d: Model3D | None) -> float | None:
    """
    Extract building height from 3D model.

    Args:
        model_3d: 3D model (optional)

    Returns:
        Height in feet, or None if unavailable
    """
    if not model_3d or not model_3d.buildings:
        return None

    # Get the subject building (main building)
    subject_building = None
    for building in model_3d.buildings:
        if building.is_subject:
            subject_building = building
            break

    # Fall back to first building if no subject building
    if not subject_building and model_3d.buildings:
        subject_building = model_3d.buildings[0]

    if subject_building and subject_building.bounding_box:
        height = subject_building.bounding_box.max.z - subject_building.bounding_box.min.z
        return height if height > 0 else None

    return None


def _detect_scope_triggers(bid_proposal: BidProposal) -> set[str]:
    """
    Detect scope triggers from bid proposal.

    Args:
        bid_proposal: Bid proposal with line items

    Returns:
        Set of scope trigger strings
    """
    triggers: set[str] = set()

    desc_text = " ".join([item.description.lower() for item in bid_proposal.line_items])

    # Exterior work triggers
    if any(
        keyword in desc_text
        for keyword in ["parapet", "repoint", "brick", "veneer", "masonry", "facade"]
    ):
        triggers.add("exterior_masonry")

    if any(keyword in desc_text for keyword in ["flash", "flashing", "waterproof"]):
        triggers.add("waterproofing")

    if any(keyword in desc_text for keyword in ["lintel", "steel", "metal"]):
        triggers.add("metals_work")

    # Height-based triggers
    # These will be applied after we know building height

    return triggers


def _generate_gc_items(
    building_type: str,
    building_height_ft: float | None,
    duration_weeks: float,
    region_id: str,
    scope_triggers: set[str],
) -> list[GeneralConditionsItem]:
    """
    Generate general conditions line items based on project parameters.

    Args:
        building_type: Building type
        building_height_ft: Building height in feet
        duration_weeks: Estimated project duration in weeks
        region_id: Region identifier
        scope_triggers: Set of scope trigger strings

    Returns:
        List of GeneralConditionsItem objects
    """
    items: list[GeneralConditionsItem] = []
    regional_multiplier = REGIONAL_GC_MULTIPLIERS.get(region_id, 1.0)

    # 1. Project Management / Supervision
    # Base: $800/week for small projects, $1200/week for medium+, $1500/week for institutional
    if building_type == "institutional":
        mgmt_rate = 1500.0
    elif duration_weeks <= 4:
        mgmt_rate = 800.0
    else:
        mgmt_rate = 1200.0

    mgmt_cost = mgmt_rate * duration_weeks * regional_multiplier
    items.append(
        GeneralConditionsItem(
            item_id="gc_001",
            title="Project Management & Supervision",
            division="01 50 00",
            category="management",
            quantity=duration_weeks,
            unit="week",
            unit_cost=mgmt_rate * regional_multiplier,
            total_cost=mgmt_cost,
            basis=f"Project duration: {duration_weeks:.1f} weeks",
            trigger=None,
            region_factor=regional_multiplier,
        )
    )

    # 2. Site Protection / Barriers
    # Required for exterior work
    if "exterior_masonry" in scope_triggers or "waterproofing" in scope_triggers:
        # Base: $500/week for protection
        protection_cost = 500.0 * duration_weeks * regional_multiplier
        items.append(
            GeneralConditionsItem(
                item_id="gc_002",
                title="Site Protection & Barriers",
                division="01 50 00",
                category="site_protection",
                quantity=duration_weeks,
                unit="week",
                unit_cost=500.0 * regional_multiplier,
                total_cost=protection_cost,
                basis=f"Required for exterior work, {duration_weeks:.1f} weeks",
                trigger="exterior_masonry",
                region_factor=regional_multiplier,
            )
        )

    # 3. Temporary Facilities / Site Office
    # Required for institutional or projects > 8 weeks
    if building_type == "institutional" or duration_weeks >= 8:
        # Base: $600/week for site trailer
        trailer_cost = 600.0 * duration_weeks * regional_multiplier
        items.append(
            GeneralConditionsItem(
                item_id="gc_003",
                title="Temporary Site Facilities",
                division="01 51 00",
                category="temporary_facilities",
                quantity=duration_weeks,
                unit="week",
                unit_cost=600.0 * regional_multiplier,
                total_cost=trailer_cost,
                basis=f"Required for {building_type} project, {duration_weeks:.1f} weeks",
                trigger=None,
                region_factor=regional_multiplier,
            )
        )

    # 4. Temporary Utilities
    # Base: $200/week for temporary power/water
    utilities_cost = 200.0 * duration_weeks * regional_multiplier
    items.append(
        GeneralConditionsItem(
            item_id="gc_004",
            title="Temporary Utilities (Power & Water)",
            division="01 55 00",
            category="utilities",
            quantity=duration_weeks,
            unit="week",
            unit_cost=200.0 * regional_multiplier,
            total_cost=utilities_cost,
            basis=f"Temporary utilities for {duration_weeks:.1f} weeks",
            trigger=None,
            region_factor=regional_multiplier,
        )
    )

    # 5. Cleanup / Debris Removal
    # Base: $400/week for cleanup
    cleanup_cost = 400.0 * duration_weeks * regional_multiplier
    items.append(
        GeneralConditionsItem(
            item_id="gc_005",
            title="Daily Cleanup & Debris Removal",
            division="01 74 00",
            category="cleanup",
            quantity=duration_weeks,
            unit="week",
            unit_cost=400.0 * regional_multiplier,
            total_cost=cleanup_cost,
            basis=f"Daily cleanup for {duration_weeks:.1f} weeks",
            trigger=None,
            region_factor=regional_multiplier,
        )
    )

    # 6. Safety Equipment / First Aid
    # Required for all projects
    # Base: $150/week for safety supplies
    safety_cost = 150.0 * duration_weeks * regional_multiplier
    items.append(
        GeneralConditionsItem(
            item_id="gc_006",
            title="Safety Equipment & First Aid",
            division="01 75 00",
            category="safety",
            quantity=duration_weeks,
            unit="week",
            unit_cost=150.0 * regional_multiplier,
            total_cost=safety_cost,
            basis=f"Safety supplies for {duration_weeks:.1f} weeks",
            trigger=None,
            region_factor=regional_multiplier,
        )
    )

    # 7. Permits / Filing Fees
    # Regional and scope-dependent
    permit_cost = _estimate_permits_cost(region_id, building_type, scope_triggers)
    if permit_cost > 0:
        items.append(
            GeneralConditionsItem(
                item_id="gc_007",
                title="Permits & Filing Fees",
                division="01 29 00",
                category="permits",
                quantity=1.0,
                unit="lump_sum",
                unit_cost=permit_cost,
                total_cost=permit_cost,
                basis=f"Permits for {building_type} project in {region_id}",
                trigger=None,
                region_factor=regional_multiplier,
            )
        )

    # 8. Inspections / Testing
    # Typically required for masonry work
    if "exterior_masonry" in scope_triggers:
        # Base: $300 per inspection, estimate 3-5 inspections
        num_inspections = 4.0 if building_type == "institutional" else 3.0
        inspection_cost = 300.0 * num_inspections * regional_multiplier
        items.append(
            GeneralConditionsItem(
                item_id="gc_008",
                title="Inspections & Testing",
                division="01 45 00",
                category="inspections",
                quantity=num_inspections,
                unit="each",
                unit_cost=300.0 * regional_multiplier,
                total_cost=inspection_cost,
                basis=f"Masonry inspections, {num_inspections:.0f} inspections",
                trigger="exterior_masonry",
                region_factor=regional_multiplier,
            )
        )

    # 9. Mobilization / Demobilization
    # One-time costs
    mobilization_cost = 2000.0 * regional_multiplier
    items.append(
        GeneralConditionsItem(
            item_id="gc_009",
            title="Mobilization & Demobilization",
            division="01 50 00",
            category="mobilization",
            quantity=1.0,
            unit="lump_sum",
            unit_cost=mobilization_cost,
            total_cost=mobilization_cost,
            basis="One-time setup and breakdown",
            trigger=None,
            region_factor=regional_multiplier,
        )
    )

    # 10. Security (if required for institutional or long-duration projects)
    if building_type == "institutional" or duration_weeks >= 12:
        security_cost = 400.0 * duration_weeks * regional_multiplier
        items.append(
            GeneralConditionsItem(
                item_id="gc_010",
                title="Site Security",
                division="01 50 00",
                category="security",
                quantity=duration_weeks,
                unit="week",
                unit_cost=400.0 * regional_multiplier,
                total_cost=security_cost,
                basis=f"Security for {building_type} project, {duration_weeks:.1f} weeks",
                trigger=None,
                region_factor=regional_multiplier,
            )
        )

    return items


def _estimate_permits_cost(
    region_id: str, building_type: str, scope_triggers: set[str]
) -> float:
    """
    Estimate permit costs based on region and scope.

    Args:
        region_id: Region identifier
        building_type: Building type
        scope_triggers: Set of scope triggers

    Returns:
        Estimated permit cost in dollars
    """
    # Base permit costs by region
    base_permits: dict[str, float] = {
        "NYC": 2500.0,  # NYC DOB fees are high
        "NJ": 800.0,
        "CA": 2000.0,
        "TX": 600.0,
        "PA": 700.0,
        "FL": 750.0,
        "US_DEFAULT": 500.0,
    }

    base_cost = base_permits.get(region_id, 500.0)

    # Institutional projects typically require more permits
    if building_type == "institutional":
        base_cost *= 1.5

    return base_cost


def estimate_general_conditions(
    project_id: str,
    building_type: str,
    bid_proposal: BidProposal | dict[str, Any],
    model_3d: Model3D | dict[str, Any] | None = None,
    document_analysis: dict[str, Any] | None = None,
    extraction_result: dict[str, Any] | None = None,
    region_resolution: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> GeneralConditions:
    """
    Estimate general conditions for a project.

    Args:
        project_id: Project ID
        building_type: Building type (e.g., "row_house", "institutional")
        bid_proposal: Bid proposal (BidProposal object or dict)
        model_3d: 3D model (optional, for building height)
        document_analysis: Document analysis artifact (optional, for region resolution)
        extraction_result: Extraction result artifact (optional, for region resolution)
        region_resolution: Pre-resolved region (optional, skips region resolution)
        settings: Application settings (optional)

    Returns:
        GeneralConditions with estimated items and costs
    """
    log_ctx = logger.bind(project_id=project_id, service="general_conditions_estimator")
    log_ctx.info(f"Estimating general conditions for {building_type} project")

    # Convert to objects if dicts
    if isinstance(bid_proposal, dict):
        from app.schemas.bid_proposal import BidProposal as BidProposalSchema

        bid_proposal = BidProposalSchema.model_validate(bid_proposal)

    model_3d_obj = None
    if isinstance(model_3d, dict):
        from app.schemas.model_3d import Model3D as Model3DSchema

        model_3d_obj = Model3DSchema.model_validate(model_3d)
    elif model_3d is not None:
        model_3d_obj = model_3d

    # Resolve region if not provided
    if region_resolution is None:
        region_resolution = resolve_region(document_analysis, extraction_result)

    region_id = region_resolution.get("region_id", "US_DEFAULT")
    log_ctx.info(f"Resolved region: {region_id}")

    # Get building height
    building_height_ft = _get_building_height(model_3d_obj)
    if building_height_ft:
        log_ctx.info(f"Building height: {building_height_ft:.1f} ft")

    # Estimate duration (Task 7: uses roof area and production rate for roofing projects)
    duration_weeks = _estimate_duration(
        bid_proposal,
        building_type,
        document_analysis=document_analysis,
        extraction_result=extraction_result,
        settings=settings,
    )
    log_ctx.info(f"Estimated duration: {duration_weeks:.1f} weeks")

    # Detect scope triggers
    scope_triggers = _detect_scope_triggers(bid_proposal)
    log_ctx.info(f"Scope triggers: {', '.join(scope_triggers) if scope_triggers else 'none'}")

    # Generate GC items
    items = _generate_gc_items(
        building_type,
        building_height_ft,
        duration_weeks,
        region_id,
        scope_triggers,
    )

    # Calculate totals
    total_cost = sum(item.total_cost for item in items)
    base_bid_total = bid_proposal.summary.total_cost
    total_cost_percent = (total_cost / base_bid_total * 100) if base_bid_total > 0 else None

    log_ctx.info(
        f"Generated {len(items)} GC items, total: ${total_cost:,.2f} "
        f"({total_cost_percent:.1f}% of base bid)" if total_cost_percent else ""
    )

    return GeneralConditions(
        project_id=project_id,
        building_type=building_type,
        building_height_ft=building_height_ft,
        estimated_duration_weeks=duration_weeks,
        region_id=region_id,
        items=items,
        total_cost=total_cost,
        total_cost_percent_of_base=total_cost_percent,
    )


