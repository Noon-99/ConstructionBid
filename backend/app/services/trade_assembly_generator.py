"""Trade assembly generator service (Phase 9.2).

Deterministically generates trade assemblies from bid line items using YAML rules.
"""

import json
import math
import re
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal
from app.schemas.evidence_index import EvidenceIndex, EvidenceReference
from app.schemas.trade_assemblies import (
    EquipmentComponent,
    LaborComponent,
    TradeAssembly,
    TradeAssembliesResult,
    TradeComponent,
)


def _evaluate_formula(formula: str, Q: float, waste_factor: float = 1.05) -> float:
    """
    Safely evaluate a quantity formula.

    Supports:
    - Q (quantity from bid item)
    - waste_factor (default 1.05)
    - Basic math: +, -, *, /, ceil, floor, max, min
    - Parentheses

    Args:
        formula: Formula string (e.g., "Q * 1.05", "ceil(Q / 4.0)")
        Q: Quantity value
        waste_factor: Waste factor (default 1.05)

    Returns:
        Evaluated result
    """
    # Replace Q with actual quantity
    formula = formula.replace("Q", str(Q))
    formula = formula.replace("waste_factor", str(waste_factor))

    # Safe math operations only
    safe_dict = {
        "__builtins__": {},
        "ceil": math.ceil,
        "floor": math.floor,
        "max": max,
        "min": min,
        "round": round,
    }

    try:
        result = eval(formula, safe_dict)
        return float(result)
    except Exception as e:
        logger.warning(f"Failed to evaluate formula '{formula}': {e}")
        return 0.0


def _match_bid_item_to_assembly(
    line_item: dict[str, Any], assembly_key: str, assembly_rule: dict[str, Any]
) -> bool:
    """
    Determine if a bid line item matches an assembly rule.

    Args:
        line_item: Bid line item dict
        assembly_key: Assembly key from rules (e.g., "parapet_repair")
        assembly_rule: Assembly rule dict from YAML

    Returns:
        True if line item matches this assembly
    """
    desc_lower = line_item.get("description", "").lower()
    division = line_item.get("division", "").lower()
    unit = (line_item.get("unit") or "").lower()

    # Match by keywords in description
    keywords_map = {
        "parapet_repair": ["parapet"],
        "brick_repointing": ["repoint", "re-point", "pointing", "tuckpoint"],
        "lintel_replacement": ["lintel"],
        "flashing_installation": ["flash", "flashing"],
        "crack_repair": ["crack", "epoxy", "stabil"],
    }

    keywords = keywords_map.get(assembly_key, [])
    if keywords:
        if any(keyword in desc_lower for keyword in keywords):
            # Also check unit matches if specified in rule
            rule_unit = assembly_rule.get("unit", "").lower()
            if rule_unit and unit:
                if rule_unit in unit or unit in rule_unit:
                    return True
            elif not rule_unit:
                # No unit requirement
                return True

    return False


def _generate_trade_component(
    component_rule: dict[str, Any],
    Q: float,
    waste_factor: float,
    bid_item_unit_cost: float | None = None,
) -> TradeComponent:
    """
    Generate a TradeComponent from a component rule.

    Args:
        component_rule: Component rule from YAML
        Q: Quantity from bid line item
        waste_factor: Waste factor to apply
        bid_item_unit_cost: Optional unit cost from bid item (for cost_share calculations)

    Returns:
        TradeComponent
    """
    qty_formula = component_rule.get("qty_formula", "Q * 1.0")
    qty = _evaluate_formula(qty_formula, Q, waste_factor)

    # Determine cost
    unit_cost = component_rule.get("unit_cost")
    cost_source = component_rule.get("cost_source", "ruleset")

    # If cost_share is specified, derive from bid item cost
    cost_share = component_rule.get("cost_share")
    if cost_share and bid_item_unit_cost is not None:
        unit_cost = bid_item_unit_cost * cost_share
        cost_source = "bid_item"

    if unit_cost is None:
        unit_cost = 0.0
        cost_source = "derived"

    total_cost = qty * unit_cost

    return TradeComponent(
        name=component_rule["name"],
        unit=component_rule["unit"],
        qty=qty,
        unit_cost=unit_cost,
        total_cost=total_cost,
        cost_source=cost_source,
        notes=component_rule.get("notes"),
    )


def _generate_labor_component(
    labor_rule: dict[str, Any], Q: float
) -> LaborComponent:
    """
    Generate a LaborComponent from a labor rule.

    Args:
        labor_rule: Labor rule from YAML
        Q: Quantity from bid line item

    Returns:
        LaborComponent
    """
    hours_formula = labor_rule.get("hours_formula", "Q * 0.5")
    hours = _evaluate_formula(hours_formula, Q)

    rate = labor_rule.get("rate")
    if rate is None:
        rate = 0.0

    total_cost = hours * rate

    return LaborComponent(
        trade=labor_rule["trade"],
        crew=labor_rule.get("crew", []),
        hours=hours,
        rate=rate,
        total_cost=total_cost,
        basis=labor_rule.get("basis", hours_formula),
    )


def _generate_equipment_component(
    equipment_rule: dict[str, Any], Q: float
) -> EquipmentComponent:
    """
    Generate an EquipmentComponent from an equipment rule.

    Args:
        equipment_rule: Equipment rule from YAML
        Q: Quantity from bid line item

    Returns:
        EquipmentComponent
    """
    qty_formula = equipment_rule.get("qty_formula", "1.0")
    qty = _evaluate_formula(qty_formula, Q)

    unit_cost = equipment_rule.get("unit_cost", 0.0)
    total_cost = qty * unit_cost

    return EquipmentComponent(
        name=equipment_rule["name"],
        unit=equipment_rule["unit"],
        qty=qty,
        unit_cost=unit_cost,
        total_cost=total_cost,
        basis=equipment_rule.get("basis", ""),
    )


def _load_ruleset(ruleset_name: str, settings: Settings) -> dict[str, Any]:
    """
    Load a ruleset YAML file.

    Args:
        ruleset_name: Ruleset filename (e.g., "row_house_repair.yml")
        settings: Application settings

    Returns:
        Parsed YAML rules dict

    Raises:
        FileNotFoundError: If ruleset file not found
    """
    rules_dir = Path(__file__).parent.parent / "rules" / "trade_assemblies"
    rules_file = rules_dir / ruleset_name

    if not rules_file.exists():
        raise FileNotFoundError(f"Ruleset not found: {rules_file}")

    with open(rules_file, "r") as f:
        rules = yaml.safe_load(f)

    return rules


def _get_evidence_for_line_item(
    line_item_index: int, evidence_index: EvidenceIndex | None
) -> list[EvidenceReference]:
    """
    Get evidence references for a bid line item.

    Args:
        line_item_index: Index of line item in bid_proposal.line_items
        evidence_index: Evidence index artifact

    Returns:
        List of EvidenceReference objects
    """
    if evidence_index is None:
        return []

    # Find evidence for this line item
    evidence_refs: list[EvidenceReference] = []
    for bid_evidence in evidence_index.bid_item_evidence:
        if bid_evidence.line_item_index == line_item_index:
            evidence_refs.extend(bid_evidence.evidence_references)
            break

    return evidence_refs


def generate_trade_assemblies(
    project_id: str,
    bid_proposal: BidProposal | dict[str, Any],
    evidence_index: EvidenceIndex | dict[str, Any] | None = None,
    ruleset: str = "row_house_repair.yml",
    settings: Settings | None = None,
) -> TradeAssembliesResult:
    """
    Generate trade assemblies from bid proposal using deterministic rules.

    Args:
        project_id: Project ID
        bid_proposal: Bid proposal (BidProposal object or dict)
        evidence_index: Evidence index (EvidenceIndex object or dict, optional)
        ruleset: Ruleset filename (default: "row_house_repair.yml")
        settings: Application settings (for loading rules)

    Returns:
        TradeAssembliesResult with generated assemblies
    """
    log_ctx = logger.bind(project_id=project_id, service="trade_assembly_generator")
    log_ctx.info(f"Generating trade assemblies using ruleset: {ruleset}")

    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    # Convert to objects if dicts
    if isinstance(bid_proposal, dict):
        bid_proposal = BidProposal.model_validate(bid_proposal)
    if isinstance(evidence_index, dict):
        evidence_index = EvidenceIndex.model_validate(evidence_index)

    # Load ruleset
    rules = _load_ruleset(ruleset, settings)
    assemblies_rules = rules.get("assemblies", {})
    default_waste_factor = rules.get("default_waste_factor", 1.05)

    log_ctx.info(f"Loaded {len(assemblies_rules)} assembly rules from {ruleset}")

    # Generate assemblies for matching bid items
    generated_assemblies: list[TradeAssembly] = []
    assembly_counter: dict[str, int] = {}  # Track assembly instances per type

    for idx, line_item in enumerate(bid_proposal.line_items):
        line_item_dict = line_item.model_dump() if hasattr(line_item, "model_dump") else line_item

        # Try to match this line item to an assembly rule
        matched_assembly_key = None
        matched_assembly_rule = None

        for assembly_key, assembly_rule in assemblies_rules.items():
            if _match_bid_item_to_assembly(line_item_dict, assembly_key, assembly_rule):
                matched_assembly_key = assembly_key
                matched_assembly_rule = assembly_rule
                break

        if not matched_assembly_key:
            # No matching assembly rule - skip this line item
            continue

        # Get quantity
        Q = line_item.quantity if line_item.quantity is not None else 0.0
        if Q <= 0:
            log_ctx.debug(f"Skipping line item {idx} with zero/null quantity")
            continue

        # Get waste factor for this assembly (or use default)
        waste_factor = assembly_rule.get("waste_factor", default_waste_factor)

        # Generate components
        components: list[TradeComponent] = []
        for component_rule in assembly_rule.get("components", []):
            bid_unit_cost = line_item.unit_cost
            component = _generate_trade_component(
                component_rule, Q, waste_factor, bid_unit_cost
            )
            components.append(component)

        # Generate labor
        labor: list[LaborComponent] = []
        for labor_rule in assembly_rule.get("labor", []):
            labor_comp = _generate_labor_component(labor_rule, Q)
            labor.append(labor_comp)

        # Generate equipment
        equipment: list[EquipmentComponent] = []
        for equipment_rule in assembly_rule.get("equipment", []):
            equip_comp = _generate_equipment_component(equipment_rule, Q)
            equipment.append(equip_comp)

        # Get evidence references
        evidence_refs = _get_evidence_for_line_item(idx, evidence_index)

        # Generate assembly ID
        assembly_counter[matched_assembly_key] = assembly_counter.get(matched_assembly_key, 0) + 1
        assembly_id = f"{matched_assembly_key}_{assembly_counter[matched_assembly_key]:03d}"

        # Create assembly
        assembly = TradeAssembly(
            id=assembly_id,
            title=assembly_rule["title"],
            division=assembly_rule["division"],
            unit=assembly_rule["unit"],
            quantity=Q,
            related_bid_item_ids=[str(idx)],
            components=components,
            labor=labor,
            equipment=equipment,
            assumptions=assembly_rule.get("assumptions", []),
            spec_refs=assembly_rule.get("spec_refs", []),
            evidence_refs=evidence_refs,
            ruleset_used=ruleset,
        )

        generated_assemblies.append(assembly)
        log_ctx.debug(
            f"Generated assembly {assembly_id} for line item {idx}: "
            f"{len(components)} components, {len(labor)} labor items, {len(equipment)} equipment"
        )

    log_ctx.info(
        f"Generated {len(generated_assemblies)} trade assemblies from {len(bid_proposal.line_items)} bid items"
    )

    return TradeAssembliesResult(
        project_id=project_id,
        assemblies=generated_assemblies,
        version="1.0",
    )

