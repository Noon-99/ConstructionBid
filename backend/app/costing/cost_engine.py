"""Cost engine for computing construction costs from extraction results.

All cost data comes from YAML rule files - no hardcoded prices.
"""

import yaml
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from app.schemas.costing import CostBreakdown, CostEngineResult, CostItem
from app.schemas.rule_governance import MissingRuleCandidate, RuleGovernanceReport
from app.schemas.extraction_result import ExtractionResult
from app.schemas.model_3d import Model3D
from app.schemas.pricing_profile import PricingProfile
from app.schemas.roof_assembly import RoofAssembly
from app.schemas.manual_overrides import ManualOverrides


class CostEngine:
    """Deterministic cost engine using YAML-based rules."""

    def __init__(self, rules_dir: Path | None = None) -> None:
        """
        Initialize cost engine.

        Args:
            rules_dir: Directory containing YAML cost rule files (default: app/costing/rules/)
        """
        if rules_dir is None:
            # Default to app/costing/rules/ relative to this file
            rules_dir = Path(__file__).parent / "rules"

        self.rules_dir = Path(rules_dir)
        self.rules: dict[str, dict[str, Any]] = {}
        self._load_rules()

    def _load_rules(self) -> None:
        """Load all YAML cost rule files from rules directory."""
        if not self.rules_dir.exists():
            logger.warning(f"Rules directory does not exist: {self.rules_dir}")
            return

        for rule_file in self.rules_dir.glob("*.yml"):
            try:
                with open(rule_file, "r") as f:
                    rule_data = yaml.safe_load(f)
                    rule_name = rule_file.stem
                    self.rules[rule_name] = rule_data
                    logger.info(f"Loaded cost rule: {rule_name}")
            except Exception as e:
                logger.error(f"Failed to load rule file {rule_file}: {e}")

    def _match_scope_item_to_rule(self, scope_item: Any) -> dict[str, Any] | None:
        """
        Match a scope item to a cost rule.

        Args:
            scope_item: Scope item from extraction (ScopeItem Pydantic model or dict)

        Returns:
            Matched rule dict or None
        """
        # Handle both Pydantic model and dict
        if hasattr(scope_item, "item"):
            item_name = scope_item.item.lower()
        else:
            item_name = scope_item.get("item", "").lower()

        # Try exact matches first
        for rule_name, rule_data in self.rules.items():
            rule_keywords = rule_data.get("keywords", [])
            if any(keyword in item_name for keyword in rule_keywords):
                return rule_data

        # Try partial matches
        if "window" in item_name:
            if any(keyword in item_name for keyword in ("storefront", "curtain wall", "cw-")):
                return self.rules.get("window_new_install") or self.rules.get("window_replacement")
            return self.rules.get("window_replacement") or self.rules.get("window_new_install")
        if "glazing" in item_name or "fenestration" in item_name:
            return self.rules.get("window_replacement") or self.rules.get("window_new_install")
        if "parapet" in item_name:
            return self.rules.get("parapet_rebuild")
        if "lintel" in item_name:
            return self.rules.get("lintel_replacement")
        if "brick" in item_name and "rebuild" in item_name:
            return self.rules.get("brick_rebuild")
        if "repoint" in item_name:
            return self.rules.get("repointing")
        if "crack" in item_name:
            return self.rules.get("crack_repair")
        if "flash" in item_name:
            return self.rules.get("flashing_install")

        return None

    def _guess_trade_from_scope_item(
        self, scope_item: Any
    ) -> Literal[
        "masonry",
        "roofing",
        "concrete",
        "interiors",
        "mechanical",
        "plumbing",
        "electrical",
        "site",
        "structural",
        "unknown",
    ]:
        """Heuristic guess of governing trade for a scope item."""

        text_parts: list[str] = []
        if hasattr(scope_item, "item") and scope_item.item:
            text_parts.append(scope_item.item)
        elif isinstance(scope_item, dict):
            item_val = scope_item.get("item")
            if item_val:
                text_parts.append(str(item_val))

        if hasattr(scope_item, "description") and scope_item.description:
            text_parts.append(scope_item.description)
        elif isinstance(scope_item, dict):
            desc_val = scope_item.get("description")
            if desc_val:
                text_parts.append(str(desc_val))

        combined = " ".join(text_parts).lower()

        trade_keywords = {
            "roofing": ["roof", "parapet", "flashing", "coping"],
            "masonry": ["brick", "mortar", "lintel", "stone", "repoint"],
            "concrete": ["slab", "concrete", "footing", "foundation"],
            "structural": ["beam", "column", "steel", "structural", "truss"],
            "mechanical": ["hvac", "mechanical", "air handler"],
            "plumbing": ["plumb", "pipe", "fixture"],
            "electrical": ["electrical", "lighting", "panel", "conduit"],
            "site": ["site", "paving", "sidewalk", "civil"],
            "interiors": ["interior", "finishes", "drywall", "ceiling", "flooring"],
        }

        for trade, keywords in trade_keywords.items():
            if any(keyword in combined for keyword in keywords):
                return trade  # type: ignore[return-value]

        return "unknown"

    def _match_material_to_rule(self, material: Any) -> dict[str, Any] | None:
        """
        Match a material specification to a cost rule.

        Args:
            material: Material specification from extraction (MaterialSpecification Pydantic model or dict)

        Returns:
            Matched rule dict or None
        """
        # Handle both Pydantic model and dict
        if hasattr(material, "material_name"):
            material_name = material.material_name.lower()
            application = material.application.lower() if material.application else ""
        else:
            material_name = material.get("material_name", "").lower()
            application = material.get("application", "").lower()

        # Match by application
        if "window" in application or "glazing" in application or "storefront" in application:
            return self.rules.get("window_replacement") or self.rules.get("window_new_install")
        if "lintel" in application:
            return self.rules.get("lintel_replacement")
        if "repoint" in application:
            return self.rules.get("repointing")

        # Match by material name
        if "window" in material_name or "glaz" in material_name:
            return self.rules.get("window_replacement") or self.rules.get("window_new_install")
        if "mortar" in material_name:
            return self.rules.get("repointing")
        if "lintel" in material_name or "steel" in material_name:
            return self.rules.get("lintel_replacement")

        return None

    def _calculate_quantity(
        self, scope_item: Any, extraction: ExtractionResult
    ) -> tuple[float, str, str, float, dict[str, Any]]:
        """
        Calculate quantity for a scope item with provenance (Phase 4.7).

        Args:
            scope_item: Scope item from extraction (ScopeItem Pydantic model or dict)
            extraction: Full extraction result

        Returns:
            Tuple of (quantity, unit, quantity_source, quantity_confidence, quantity_evidence)
        """
        from app.schemas.costing import QuantitySource

        # Handle both Pydantic model and dict
        if hasattr(scope_item, "item"):
            item_name = scope_item.item.lower()
            description = scope_item.description if hasattr(scope_item, "description") else ""
        else:
            item_name = scope_item.get("item", "").lower()
            description = scope_item.get("description", "")

        # Check quantity_takeoff first (from_drawing or from_schedule)
        for qty_item in extraction.quantity_takeoff:
            if item_name in qty_item.item.lower():
                if qty_item.quantity is not None:
                    # Determine source based on is_computed flag and location_type
                    if qty_item.is_computed:
                        source: QuantitySource = "computed_from_dimensions"
                        confidence = 0.8 if qty_item.computation_formula else 0.6
                        evidence = {
                            "page_number": qty_item.page_number,
                            "evidence_snippet": qty_item.evidence_snippet,
                            "computation_formula": qty_item.computation_formula,
                            "input_dimensions": qty_item.input_dimensions,
                        }
                    else:
                        # Check location_type to determine if from schedule or drawing
                        # This would need to be enhanced based on QuantityLocator data
                        source = "from_drawing"  # Default, could be "from_schedule" if we track that
                        confidence = 0.9
                        evidence = {
                            "page_number": qty_item.page_number,
                            "evidence_snippet": qty_item.evidence_snippet,
                        }
                    return (qty_item.quantity, qty_item.unit or "EA", source, confidence, evidence)

        # Promote schedule-derived window counts when direct match fails
        if "window" in item_name:
            total_qty = 0.0
            matched_unit: str | None = None
            first_page: int | None = None
            first_snippet: str | None = None

            for qty_item in extraction.quantity_takeoff:
                if hasattr(qty_item, "item"):
                    qty_item_name = (qty_item.item or "").lower()
                    qty_quantity = qty_item.quantity
                    qty_unit = qty_item.unit
                    qty_page = getattr(qty_item, "page_number", None)
                    qty_snippet = getattr(qty_item, "evidence_snippet", None)
                else:
                    qty_item_name = (qty_item.get("item") or "").lower()
                    qty_quantity = qty_item.get("quantity")
                    qty_unit = qty_item.get("unit")
                    qty_page = qty_item.get("page_number")
                    qty_snippet = qty_item.get("evidence_snippet")

                if "window" not in qty_item_name:
                    continue

                if qty_quantity:
                    total_qty += qty_quantity
                    if matched_unit is None:
                        matched_unit = qty_unit or "EA"
                        first_page = qty_page
                        first_snippet = qty_snippet

            if total_qty > 0:
                evidence = {
                    "page_number": first_page,
                    "evidence_snippet": first_snippet,
                    "aggregation": "Summed window schedule counts",
                }
                return (
                    total_qty,
                    matched_unit or "EA",
                    "from_schedule",
                    0.85,
                    evidence,
                )

        # Check authoritative dimensions for institutional projects
        if extraction.authoritative_dimensions:
            auth_dims = extraction.authoritative_dimensions
            if "slab" in item_name or "floor" in item_name:
                if auth_dims.footprint_area_sf:
                    source = "computed_from_dimensions"
                    confidence = 0.85
                    evidence = {
                        "page_number": auth_dims.footprint_area_evidence.get("page_number", 1) if isinstance(auth_dims.footprint_area_evidence, dict) else 1,
                        "evidence_snippet": str(auth_dims.footprint_area_evidence) if not isinstance(auth_dims.footprint_area_evidence, dict) else auth_dims.footprint_area_evidence.get("evidence_snippet", ""),
                        "computation_formula": "footprint_area_sf",
                    }
                    return (auth_dims.footprint_area_sf, "SF", source, confidence, evidence)

        # Check geometry_for_3d dimensions (computed_from_dimensions)
        if extraction.geometry_for_3d and extraction.geometry_for_3d.dimensions:
            dims = extraction.geometry_for_3d.dimensions
            if "parapet" in item_name and dims.width:
                source = "computed_from_dimensions"
                confidence = 0.75
                evidence = {
                    "page_number": dims.input_pages[0] if dims.input_pages else 1,
                    "evidence_snippet": dims.evidence,
                    "computation_formula": "width",
                }
                return (dims.width, "LF", source, confidence, evidence)
            if ("brick" in item_name or "repoint" in item_name) and dims.width and dims.height:
                source = "computed_from_dimensions"
                confidence = 0.75
                evidence = {
                    "page_number": dims.input_pages[0] if dims.input_pages else 1,
                    "evidence_snippet": dims.evidence,
                    "computation_formula": "width * height",
                }
                return (dims.width * dims.height, "SF", source, confidence, evidence)

        # Heuristic: look for numbers in description (low confidence)
        import re

        numbers = re.findall(r"\d+", description)
        if numbers:
            source = "heuristic"
            confidence = 0.3
            evidence = {
                "evidence_snippet": f"Extracted number from description: {description[:100]}",
            }
            return (float(numbers[0]), "EA", source, confidence, evidence)

        # Default fallback (heuristic)
        source = "heuristic"
        confidence = 0.2
        evidence = {
            "evidence_snippet": "Default fallback quantity",
        }
        if "lintel" in item_name:
            return (1.0, "EA", source, confidence, evidence)

        return (1.0, "EA", source, confidence, evidence)

    def _apply_multipliers(
        self, base_cost: float, rule: dict[str, Any], extraction: ExtractionResult
    ) -> tuple[float, dict[str, float]]:
        """
        Apply multipliers to base cost.

        Args:
            base_cost: Base unit cost
            rule: Cost rule dict
            extraction: Extraction result for context

        Returns:
            Tuple of (final_cost, applied_multipliers)
        """
        multipliers: dict[str, float] = {}
        final_cost = base_cost

        # Height multiplier
        if extraction.geometry_for_3d.dimensions and extraction.geometry_for_3d.dimensions.height:
            height = extraction.geometry_for_3d.dimensions.height
            height_mult = rule.get("height_multiplier", {})
            if height_mult:
                # Apply multiplier based on height ranges
                for range_str, mult in height_mult.items():
                    if "-" in range_str:
                        min_h, max_h = map(float, range_str.split("-"))
                        if min_h <= height <= max_h:
                            multipliers["height"] = mult
                            final_cost *= mult
                            break

        # Material multiplier (from rule)
        material_mult = rule.get("material_multiplier", 1.0)
        if material_mult != 1.0:
            multipliers["material"] = material_mult
            final_cost *= material_mult

        # Equipment multiplier (from rule)
        equipment_mult = rule.get("equipment_multiplier", 1.0)
        if equipment_mult != 1.0:
            multipliers["equipment"] = equipment_mult
            final_cost *= equipment_mult

        return (final_cost, multipliers)

    def _extract_roof_assembly(
        self, extraction: ExtractionResult, missing_data_warnings: list[str] | None = None
    ) -> RoofAssembly | None:
        """
        Task 2: Extract roof assembly from extraction result.
        
        Returns RoofAssembly if roof-related scope/materials/quantities are found,
        None otherwise.
        """
        # Check for roof-related scope items
        roof_scope_found = False
        roof_system_type = "Unknown"
        tearoff_included = True
        tearoff_scope = "unknown"  # Task 4: full, partial, none, unknown
        disposal_requirement: str | None = None  # Task 4
        insulation_thickness: float | None = None
        # Task 5: Perimeter and edge metal
        perimeter_length_lf: float | None = None
        edge_metal_lf: float | None = None
        base_flashing_lf: float | None = None
        perimeter_confidence = 0.5  # Task 5: confidence in perimeter (lower if inferred)
        evidence_parts: list[str] = []
        system_type_confidence = 0.0  # Track confidence for system type
        insulation_confidence = 0.0  # Track confidence for insulation

        # Task 3: Extract system type from scope items with evidence quotes
        for scope_item in extraction.scope_of_work:
            item_lower = (scope_item.item if hasattr(scope_item, "item") else scope_item.get("item", "")).lower()
            
            if "roof" in item_lower:
                roof_scope_found = True
                desc = scope_item.description if hasattr(scope_item, "description") else scope_item.get("description", "")
                desc_lower = desc.lower()
                evidence_snippet = scope_item.evidence_snippet if hasattr(scope_item, "evidence_snippet") else scope_item.get("evidence_snippet", "")
                evidence_lower = evidence_snippet.lower()
                
                # Task 3: Extract system type with evidence quotes
                if "epdm" in desc_lower or "epdm" in evidence_lower:
                    roof_system_type = "EPDM"
                    system_type_confidence = 0.9
                    evidence_parts.append(f"System type (EPDM): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                elif "tpo" in desc_lower or "tpo" in evidence_lower:
                    roof_system_type = "TPO"
                    system_type_confidence = 0.9
                    evidence_parts.append(f"System type (TPO): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                elif "pvc" in desc_lower or "pvc" in evidence_lower:
                    roof_system_type = "PVC"
                    system_type_confidence = 0.9
                    evidence_parts.append(f"System type (PVC): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                elif "modified bitumen" in desc_lower or "mod bit" in desc_lower or "modified bitumen" in evidence_lower:
                    roof_system_type = "Modified bitumen"
                    system_type_confidence = 0.9
                    evidence_parts.append(f"System type (Modified bitumen): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                elif "built-up" in desc_lower or "bur" in desc_lower or "built-up" in evidence_lower:
                    roof_system_type = "Built-up roof"
                    system_type_confidence = 0.9
                    evidence_parts.append(f"System type (Built-up roof): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                elif "single-ply" in desc_lower or "single-ply" in evidence_lower:
                    roof_system_type = "Single-ply"
                    system_type_confidence = 0.8  # Less specific
                    evidence_parts.append(f"System type (Single-ply): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                elif "metal" in desc_lower and "roof" in desc_lower:
                    roof_system_type = "Metal"
                    system_type_confidence = 0.9
                    evidence_parts.append(f"System type (Metal): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                
                # Task 4: Extract tear-off scope and disposal requirements
                # Check for tear-off keywords in item name, description, or evidence
                combined_text = f"{item_lower} {desc_lower} {evidence_lower}".lower()
                item_has_tearoff = "tear" in item_lower or "remove" in item_lower or "strip" in item_lower or "demolition" in item_lower
                desc_has_tearoff = "remove" in desc_lower or "tear" in desc_lower or "strip" in desc_lower or "demolition" in desc_lower
                evidence_has_tearoff = "remove" in evidence_lower or "tear" in evidence_lower or "strip" in evidence_lower or "demolition" in evidence_lower
                
                if item_has_tearoff or desc_has_tearoff or evidence_has_tearoff:
                    tearoff_included = True
                    # Determine scope: full or partial
                    if "entire" in combined_text or "full" in combined_text or "all" in combined_text or "complete" in combined_text:
                        tearoff_scope = "full"
                        evidence_parts.append(f"Tear-off scope (full): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                    elif "partial" in combined_text or "section" in combined_text or "specific" in combined_text or "area" in combined_text:
                        tearoff_scope = "partial"
                        evidence_parts.append(f"Tear-off scope (partial): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                    else:
                        tearoff_scope = "full"  # Default to full if tear-off mentioned but scope unclear
                        evidence_parts.append(f"Tear-off scope (assumed full): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")
                    
                    # Extract disposal requirements
                    if "dispose" in combined_text or "disposal" in combined_text or "dumpster" in combined_text or "carting" in combined_text or "hoisting" in combined_text:
                        disposal_requirement = evidence_snippet[:200] if evidence_snippet else desc[:200]
                        evidence_parts.append(f"Disposal requirement: {disposal_requirement}")
                elif "no tear" in combined_text or "overlay" in combined_text or "no removal" in combined_text:
                    tearoff_included = False
                    tearoff_scope = "none"
                    evidence_parts.append(f"No tear-off (overlay): {evidence_snippet[:100] if evidence_snippet else desc[:100]}")

        # Task 3: Extract system type and insulation from materials with evidence quotes
        for material in extraction.material_specifications:
            mat_name = material.material_name if hasattr(material, "material_name") else material.get("material_name", "")
            mat_name_lower = mat_name.lower()
            app = material.application if hasattr(material, "application") else material.get("application", "")
            app_lower = app.lower()
            spec = material.specification if hasattr(material, "specification") else material.get("specification", "")
            spec_lower = (spec or "").lower()
            evidence_snippet = material.evidence_snippet if hasattr(material, "evidence_snippet") else material.get("evidence_snippet", "")
            evidence_lower = (evidence_snippet or "").lower()
            
            # Task 3: Extract system type from material with evidence
            if "roof" in app_lower or "roofing" in app_lower or "membrane" in mat_name_lower:
                if "epdm" in mat_name_lower or "epdm" in spec_lower or "epdm" in evidence_lower:
                    if system_type_confidence < 0.9:  # Material evidence is stronger
                        roof_system_type = "EPDM"
                        system_type_confidence = 0.95
                        evidence_parts.append(f"System type (EPDM) from material: {evidence_snippet[:100] if evidence_snippet else spec[:100]}")
                elif "tpo" in mat_name_lower or "tpo" in spec_lower or "tpo" in evidence_lower:
                    if system_type_confidence < 0.9:
                        roof_system_type = "TPO"
                        system_type_confidence = 0.95
                        evidence_parts.append(f"System type (TPO) from material: {evidence_snippet[:100] if evidence_snippet else spec[:100]}")
                elif "pvc" in mat_name_lower or "pvc" in spec_lower or "pvc" in evidence_lower:
                    if system_type_confidence < 0.9:
                        roof_system_type = "PVC"
                        system_type_confidence = 0.95
                        evidence_parts.append(f"System type (PVC) from material: {evidence_snippet[:100] if evidence_snippet else spec[:100]}")
                elif "modified bitumen" in mat_name_lower or "modified bitumen" in spec_lower or "modified bitumen" in evidence_lower or "mod bit" in spec_lower:
                    if system_type_confidence < 0.9:
                        roof_system_type = "Modified bitumen"
                        system_type_confidence = 0.95
                        evidence_parts.append(f"System type (Modified bitumen) from material: {evidence_snippet[:100] if evidence_snippet else spec[:100]}")
            
            # Task 3: Extract insulation thickness and material with evidence quotes
            if "insulation" in mat_name_lower or "insulation" in app_lower:
                evidence_parts.append(f"Insulation material: {mat_name}")
                
                # Extract thickness in inches from specification or evidence
                import re
                thickness_text = f"{spec} {evidence_snippet}".lower()
                
                # Try multiple patterns for thickness
                thickness_patterns = [
                    r"(\d+(?:\.\d+)?)\s*(?:inch|in|''|\")",  # "2 inch", "3.5 in", "4''"
                    r"(\d+(?:\.\d+)?)\s*inch",  # "2 inch"
                    r"(\d+(?:\.\d+)?)\"",  # "2""
                ]
                
                for pattern in thickness_patterns:
                    thickness_match = re.search(pattern, thickness_text)
                    if thickness_match:
                        insulation_thickness = float(thickness_match.group(1))
                        insulation_confidence = 0.9
                        evidence_parts.append(f"Insulation thickness ({insulation_thickness} in): {evidence_snippet[:100] if evidence_snippet else spec[:100]}")
                        break
                
                # If thickness not found, note it
                if insulation_thickness is None:
                    evidence_parts.append(f"Insulation thickness NOT FOUND - evidence: {evidence_snippet[:100] if evidence_snippet else spec[:100]}")
                    insulation_confidence = 0.3  # Low confidence penalty

        # Extract roof area from quantity_takeoff
        roof_area_sf: float | None = None
        for qty in extraction.quantity_takeoff:
            item_lower = (qty.item if hasattr(qty, "item") else qty.get("item", "")).lower()
            unit_lower = (qty.unit if hasattr(qty, "unit") else qty.get("unit", "")).lower()
            
            if (
                ("roof" in item_lower and "area" in item_lower) or
                ("roof" in item_lower and ("sf" in unit_lower or "sq ft" in unit_lower))
            ):
                qty_value = qty.quantity if hasattr(qty, "quantity") else qty.get("quantity")
                if qty_value and qty_value > 0:
                    roof_area_sf = qty_value
                    evidence_parts.append(f"Quantity: {qty.item} = {qty_value} {qty.unit}")
                    break

        # Also check geometry for roof area
        if not roof_area_sf and extraction.geometry_for_3d:
            geometry = extraction.geometry_for_3d
            # Check work zones for roof plane
            # Note: WorkZone doesn't have 'area' attribute, so we can't extract area from zones
            # Roof area must come from quantity_takeoff or dimensions
            for zone in geometry.work_zones:
                if "roof" in zone.zone_name.lower():
                    # Zone found but no area attribute - area must come from elsewhere
                    # Don't try to access zone.area
                    break

        # Task 5: Extract perimeter length and edge metal/flashing from quantity_takeoff
        for qty in extraction.quantity_takeoff:
            item_lower = (qty.item if hasattr(qty, "item") else qty.get("item", "")).lower()
            unit_lower = (qty.unit if hasattr(qty, "unit") else qty.get("unit", "")).lower()
            qty_value = qty.quantity if hasattr(qty, "quantity") else qty.get("quantity")
            
            # Extract perimeter length
            if (
                ("perimeter" in item_lower or "edge length" in item_lower or "edge" in item_lower) and
                ("roof" in item_lower or "building" in item_lower) and
                ("lf" in unit_lower or "linear" in unit_lower or "ft" in unit_lower)
            ):
                if qty_value and qty_value > 0:
                    perimeter_length_lf = qty_value
                    perimeter_confidence = 0.9 if not (qty.is_computed if hasattr(qty, "is_computed") else qty.get("is_computed", False)) else 0.8
                    evidence_parts.append(f"Perimeter: {qty.item} = {qty_value} {qty.unit}")
            
            # Extract edge metal/coping
            if (
                ("edge metal" in item_lower or "coping" in item_lower or "edge" in item_lower) and
                ("metal" in item_lower or "coping" in item_lower) and
                ("lf" in unit_lower or "linear" in unit_lower or "ft" in unit_lower)
            ):
                if qty_value and qty_value > 0:
                    edge_metal_lf = qty_value
                    evidence_parts.append(f"Edge metal/coping: {qty.item} = {qty_value} {qty.unit}")
            
            # Extract base flashing
            if (
                ("base flashing" in item_lower or "perimeter flashing" in item_lower or "flashing" in item_lower) and
                ("base" in item_lower or "perimeter" in item_lower) and
                ("lf" in unit_lower or "linear" in unit_lower or "ft" in unit_lower)
            ):
                if qty_value and qty_value > 0:
                    base_flashing_lf = qty_value
                    evidence_parts.append(f"Base flashing: {qty.item} = {qty_value} {qty.unit}")

        # Task 5: If perimeter not extracted, infer from building dimensions with low confidence
        if not perimeter_length_lf and extraction.geometry_for_3d and extraction.geometry_for_3d.dimensions:
            dims = extraction.geometry_for_3d.dimensions
            if dims.width and dims.depth and dims.width > 0 and dims.depth > 0:
                perimeter_length_lf = 2 * (dims.width + dims.depth)
                perimeter_confidence = 0.4  # Low confidence - inferred
                evidence_parts.append(
                    f"Perimeter INFERRED (low confidence): 2 × (width {dims.width} + depth {dims.depth}) = {perimeter_length_lf} LF"
                )
                if missing_data_warnings is not None:
                    missing_data_warnings.append(
                        f"Roof perimeter not explicitly found - inferred from building dimensions: {perimeter_length_lf} LF (formula: 2 × (width + depth)). Review required."
                    )

        # Only create assembly if we have roof scope AND roof area
        # FALLBACK: If roof scope found but area missing, estimate from building dimensions or use default
        if roof_scope_found:
            if not roof_area_sf or roof_area_sf <= 0:
                # Try to estimate from building dimensions
                if extraction.geometry_for_3d and extraction.geometry_for_3d.dimensions:
                    dims = extraction.geometry_for_3d.dimensions
                    if dims.width and dims.depth and dims.width > 0 and dims.depth > 0:
                        roof_area_sf = dims.width * dims.depth
                        evidence_parts.append(f"Roof area estimated from building dimensions: {dims.width} × {dims.depth} = {roof_area_sf} SF")
                        if missing_data_warnings:
                            missing_data_warnings.append(f"Roof area not explicitly found - estimated from building footprint: {roof_area_sf} SF. Review required.")
                    else:
                        # Last resort: use a reasonable default for roof replacement (8,000-12,000 SF typical)
                        roof_area_sf = 10000.0  # Default 10,000 SF
                        evidence_parts.append(f"Roof area NOT FOUND - using default estimate: {roof_area_sf} SF (REVIEW REQUIRED)")
                        if missing_data_warnings:
                            missing_data_warnings.append(f"CRITICAL: Roof area not found and cannot be estimated - using default {roof_area_sf} SF. This bid requires manual review.")
            
            if roof_area_sf and roof_area_sf > 0:
                # Task 3: Add confidence notes for missing system type or insulation
                confidence_notes: list[str] = []
                if roof_system_type == "Unknown" or system_type_confidence < 0.5:
                    confidence_notes.append("SYSTEM TYPE UNKNOWN - pricing may be inaccurate. System type not found in documents.")
                if insulation_thickness is None or insulation_confidence < 0.5:
                    confidence_notes.append("INSULATION THICKNESS MISSING - pricing may be inaccurate. Thickness not found in documents.")

                evidence_str = "; ".join(evidence_parts) if evidence_parts else "Roof scope and area detected"
                if confidence_notes:
                    evidence_str += " | CONFIDENCE ISSUES: " + "; ".join(confidence_notes)

                return RoofAssembly(
                    roof_area_sf=roof_area_sf,
                    system_type=roof_system_type,
                    insulation_thickness_in=insulation_thickness,
                    tearoff_included=tearoff_included,
                    tearoff_scope=tearoff_scope,  # Task 4
                    disposal_requirement=disposal_requirement,  # Task 4
                    perimeter_length_lf=perimeter_length_lf,  # Task 5
                    edge_metal_lf=edge_metal_lf,  # Task 5
                    base_flashing_lf=base_flashing_lf,  # Task 5
                    perimeter_confidence=perimeter_confidence,  # Task 5
                    evidence=evidence_str,
                )

        return None

    def _create_roof_assembly_cost_item(
        self,
        roof_assembly: RoofAssembly,
        pricing_profile: PricingProfile | None = None,
        missing_data_warnings: list[str] | None = None,
        profile_id: str | None = None,
        labor_regime: str | None = None,
        prevailing_wage_multiplier: float = 1.5,
        union_multiplier: float = 1.0,
        *,
        override_source: Literal["manual_override", "extracted", "computed", "unknown"] = "extracted",
    ) -> CostItem | None:
        """
        Task 2: Create cost item for roof assembly.
        
        Uses roof_assembly.yml rule if available, otherwise uses default pricing.
        """
        # Try to load roof_assembly rule
        rule = self.rules.get("roof_assembly")
        
        if not rule:
            # Create default rule structure
            rule = {
                "name": "roof_assembly",
                "category": "Roofing",
                "base_unit_cost": 25.0,  # Default $25/SF for roof assembly
                "unit_type": "SF",
                "labor_hours_per_unit": 0.15,  # 0.15 hours per SF
                "labor_rate": 75.0,  # $75/hr for roofing
                "material_cost_per_unit": 12.0,  # $12/SF material
                "equipment_cost_per_unit": 2.0,  # $2/SF equipment
            }
            if missing_data_warnings is not None:
                missing_data_warnings.append(
                    "roof_assembly.yml rule not found - using default pricing"
                )

        # Get base costs
        base_unit_cost = rule.get("base_unit_cost", 25.0)
        labor_hours_per_unit = rule.get("labor_hours_per_unit", 0.15)
        base_labor_rate = rule.get("labor_rate", 75.0)
        base_material_cost = rule.get("material_cost_per_unit", 12.0)
        base_equipment_cost = rule.get("equipment_cost_per_unit", 2.0)

        # Apply pricing profile if available
        labor_rate = base_labor_rate
        material_cost = base_material_cost
        equipment_cost = base_equipment_cost
        multiplier_breakdown: list[str] = []

        if pricing_profile:
            # Apply roofing labor rate if available
            if pricing_profile.labor_rates.general_labor is not None:
                old_rate = labor_rate
                labor_rate = pricing_profile.labor_rates.general_labor
                if old_rate != labor_rate:
                    multiplier_breakdown.append(
                        f"labor_rate: {pricing_profile.region} general (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)"
                    )

        if labor_regime == "union" and union_multiplier > 1.0:
            old_rate = labor_rate
            labor_rate = labor_rate * union_multiplier
            pct = (union_multiplier - 1.0) * 100
            multiplier_breakdown.append(
                f"union_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)"
            )
        elif labor_regime == "prevailing_wage" and prevailing_wage_multiplier > 1.0:
            old_rate = labor_rate
            labor_rate = labor_rate * prevailing_wage_multiplier
            pct = (prevailing_wage_multiplier - 1.0) * 100
            multiplier_breakdown.append(
                f"prevailing_wage_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr) - DOT/public work"
            )

        # Calculate costs
        quantity = roof_assembly.roof_area_sf
        unit = "SF"
        unit_cost = base_unit_cost
        labor_cost = labor_hours_per_unit * labor_rate
        material_cost_total = material_cost * quantity
        equipment_cost_total = equipment_cost * quantity
        waste_factor = 0.05  # 5% waste for roofing
        multipliers = {}
        subtotal = (unit_cost + labor_cost + material_cost + equipment_cost) * quantity * (1 + waste_factor)

        # Create cost item
        from app.schemas.costing import QuantitySource

        return CostItem(
            item_name=f"Roof replacement system (assembly) - {roof_assembly.system_type}",
            scope_item="roof replacement",
            quantity=quantity,
            unit=unit,
            unit_cost=unit_cost,
            material_cost=material_cost,
            labor_cost=labor_cost,
            equipment_cost=equipment_cost,
            waste_factor=waste_factor,
            multipliers=multipliers,
            subtotal=subtotal,
            rule_matched="roof_assembly",
            evidence=roof_assembly.evidence,
            notes=[
                f"System type: {roof_assembly.system_type}",
                f"Tear-off: {'included' if roof_assembly.tearoff_included else 'separate'}",
            ] + ([f"Insulation: {roof_assembly.insulation_thickness_in} in"] if roof_assembly.insulation_thickness_in else []),
            quantity_source="from_drawing",
            quantity_confidence=0.85,
            quantity_evidence={
                "evidence_snippet": roof_assembly.evidence,
            },
            profile_id=profile_id,
            multiplier_breakdown=multiplier_breakdown,
            override_source=override_source,
        )

    def _create_edge_metal_cost_item(
        self,
        length_lf: float,
        pricing_profile: PricingProfile | None = None,
        missing_data_warnings: list[str] | None = None,
        profile_id: str | None = None,
        assumed: bool = False,
        labor_regime: str | None = None,
        prevailing_wage_multiplier: float = 1.5,
        union_multiplier: float = 1.0,
        *,
        override_source: Literal["manual_override", "extracted", "computed", "unknown"] = "extracted",
    ) -> CostItem | None:
        """Task 5: Create cost item for roof edge metal / coping."""

        rule = self.rules.get("roof_edge_metal")

        if not rule:
            rule = {
                "name": "roof_edge_metal",
                "category": "Roofing",
                "base_unit_cost": 25.0,
                "unit_type": "LF",
                "labor_hours_per_unit": 0.3,
                "labor_rate": 75.0,
                "material_cost_per_unit": 15.0,
                "equipment_cost_per_unit": 0.5,
                "waste_factor": 0.05,
            }
            if missing_data_warnings is not None:
                missing_data_warnings.append(
                    "roof_edge_metal.yml rule not found - using default pricing"
                )

        base_unit_cost = rule.get("base_unit_cost", 25.0)
        labor_hours_per_unit = rule.get("labor_hours_per_unit", 0.3)
        base_labor_rate = rule.get("labor_rate", 75.0)
        base_material_cost = rule.get("material_cost_per_unit", 15.0)
        base_equipment_cost = rule.get("equipment_cost_per_unit", 0.5)
        waste_factor = rule.get("waste_factor", 0.05)

        labor_rate = base_labor_rate
        material_cost = base_material_cost
        equipment_cost = base_equipment_cost
        multiplier_breakdown: list[str] = []

        if pricing_profile:
            if pricing_profile.labor_rates.general_labor is not None:
                old_rate = labor_rate
                labor_rate = pricing_profile.labor_rates.general_labor
                if old_rate != labor_rate:
                    multiplier_breakdown.append(
                        f"labor_rate: {pricing_profile.region} general (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)"
                    )

        if labor_regime == "union" and union_multiplier > 1.0:
            old_rate = labor_rate
            labor_rate = labor_rate * union_multiplier
            pct = (union_multiplier - 1.0) * 100
            multiplier_breakdown.append(
                f"union_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)"
            )
        elif labor_regime == "prevailing_wage" and prevailing_wage_multiplier > 1.0:
            old_rate = labor_rate
            labor_rate = labor_rate * prevailing_wage_multiplier
            pct = (prevailing_wage_multiplier - 1.0) * 100
            multiplier_breakdown.append(
                f"prevailing_wage_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr) - DOT/public work"
            )

        quantity = max(0.0, length_lf)
        if quantity == 0.0:
            return None

        unit = "LF"
        unit_cost = base_unit_cost
        labor_cost = labor_hours_per_unit * labor_rate
        material_cost_per_unit = material_cost
        equipment_cost_per_unit = equipment_cost
        multipliers: dict[str, float] = {}
        subtotal = (unit_cost + labor_cost + material_cost_per_unit + equipment_cost_per_unit) * quantity * (1 + waste_factor)

        from app.schemas.costing import QuantitySource

        item_name = "Roof edge metal / coping"
        if assumed:
            item_name += " (ASSUMED - review required)"

        quantity_source: QuantitySource = "from_drawing" if not assumed else "heuristic"
        quantity_confidence = 0.85 if not assumed else 0.5
        quantity_evidence = {
            "source": "perimeter_length" if assumed else "extracted_quantity",
        }

        notes = [
            f"Quantity: {quantity:.0f} LF",
        ]
        if assumed:
            notes.append("⚠️ Edge metal length not specified - using roof perimeter as estimate. Review required.")

        return CostItem(
            item_name=item_name,
            scope_item="roof_edge_metal",
            quantity=quantity,
            unit=unit,
            unit_cost=unit_cost,
            material_cost=material_cost_per_unit,
            labor_cost=labor_cost,
            equipment_cost=equipment_cost_per_unit,
            waste_factor=waste_factor,
            multipliers=multipliers,
            subtotal=subtotal,
            rule_matched="roof_edge_metal",
            evidence="Roof perimeter and edge metal requirements",
            notes=notes,
            quantity_source=quantity_source,
            quantity_confidence=quantity_confidence,
            quantity_evidence=quantity_evidence,
            profile_id=profile_id,
            multiplier_breakdown=multiplier_breakdown,
            override_source=override_source,
        )

    def _create_base_flashing_cost_item(
        self,
        length_lf: float,
        pricing_profile: PricingProfile | None = None,
        missing_data_warnings: list[str] | None = None,
        profile_id: str | None = None,
        assumed: bool = False,
        labor_regime: str | None = None,
        prevailing_wage_multiplier: float = 1.5,
        union_multiplier: float = 1.0,
        *,
        override_source: Literal["manual_override", "extracted", "computed", "unknown"] = "extracted",
    ) -> CostItem | None:
        """Task 5: Create cost item for roof base flashing."""

        rule = self.rules.get("roof_base_flashing")

        if not rule:
            rule = {
                "name": "roof_base_flashing",
                "category": "Roofing",
                "base_unit_cost": 18.0,
                "unit_type": "LF",
                "labor_hours_per_unit": 0.25,
                "labor_rate": 75.0,
                "material_cost_per_unit": 10.0,
                "equipment_cost_per_unit": 0.3,
                "waste_factor": 0.05,
            }
            if missing_data_warnings is not None:
                missing_data_warnings.append(
                    "roof_base_flashing.yml rule not found - using default pricing"
                )

        base_unit_cost = rule.get("base_unit_cost", 18.0)
        labor_hours_per_unit = rule.get("labor_hours_per_unit", 0.25)
        base_labor_rate = rule.get("labor_rate", 75.0)
        base_material_cost = rule.get("material_cost_per_unit", 10.0)
        base_equipment_cost = rule.get("equipment_cost_per_unit", 0.3)
        waste_factor = rule.get("waste_factor", 0.05)

        labor_rate = base_labor_rate
        material_cost = base_material_cost
        equipment_cost = base_equipment_cost
        multiplier_breakdown: list[str] = []

        if pricing_profile:
            if pricing_profile.labor_rates.general_labor is not None:
                old_rate = labor_rate
                labor_rate = pricing_profile.labor_rates.general_labor
                if old_rate != labor_rate:
                    multiplier_breakdown.append(
                        f"labor_rate: {pricing_profile.region} general (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)"
                    )

        if labor_regime == "union" and union_multiplier > 1.0:
            old_rate = labor_rate
            labor_rate = labor_rate * union_multiplier
            pct = (union_multiplier - 1.0) * 100
            multiplier_breakdown.append(
                f"union_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)"
            )

        quantity = max(0.0, length_lf)
        if quantity == 0.0:
            return None

        unit = "LF"
        unit_cost = base_unit_cost
        labor_cost = labor_hours_per_unit * labor_rate
        material_cost_per_unit = material_cost
        equipment_cost_per_unit = equipment_cost
        multipliers: dict[str, float] = {}
        subtotal = (unit_cost + labor_cost + material_cost_per_unit + equipment_cost_per_unit) * quantity * (1 + waste_factor)

        from app.schemas.costing import QuantitySource

        item_name = "Roof base flashing"
        if assumed:
            item_name += " (ASSUMED - review required)"

        quantity_source: QuantitySource = "from_drawing" if not assumed else "heuristic"
        quantity_confidence = 0.85 if not assumed else 0.5
        quantity_evidence = {
            "source": "perimeter_length" if assumed else "extracted_quantity",
        }

        notes = [
            f"Quantity: {quantity:.0f} LF",
        ]
        if assumed:
            notes.append("⚠️ Base flashing length not specified - using roof perimeter as estimate. Review required.")

        return CostItem(
            item_name=item_name,
            scope_item="roof_base_flashing",
            quantity=quantity,
            unit=unit,
            unit_cost=unit_cost,
            material_cost=material_cost_per_unit,
            labor_cost=labor_cost,
            equipment_cost=equipment_cost_per_unit,
            waste_factor=waste_factor,
            multipliers=multipliers,
            subtotal=subtotal,
            rule_matched="roof_base_flashing",
            evidence="Roof perimeter flashing requirements",
            notes=notes,
            quantity_source=quantity_source,
            quantity_confidence=quantity_confidence,
            quantity_evidence=quantity_evidence,
            profile_id=profile_id,
            multiplier_breakdown=multiplier_breakdown,
            override_source=override_source,
        )

    def _create_tearoff_disposal_cost_item(
        self,
        roof_assembly: RoofAssembly,
        pricing_profile: PricingProfile | None = None,
        missing_data_warnings: list[str] | None = None,
        profile_id: str | None = None,
        assumed: bool = False,
        labor_regime: str | None = None,
        prevailing_wage_multiplier: float = 1.5,
        union_multiplier: float = 1.0,
        *,
        override_source: Literal["manual_override", "extracted", "computed", "unknown"] = "extracted",
    ) -> CostItem | None:
        """
        Task 4: Create cost item for roof tear-off & disposal.
        
        This is a separate line item from the roof assembly, as tear-off/disposal
        is often a significant cost driver on large jobs.
        """
        # Try to load roof_tearoff rule
        rule = self.rules.get("roof_tearoff")
        
        if not rule:
            # Create default rule structure
            rule = {
                "name": "roof_tearoff",
                "category": "Roofing",
                "base_unit_cost": 4.0,  # Default $4/SF for tear-off & disposal
                "unit_type": "SF",
                "labor_hours_per_unit": 0.08,  # 0.08 hours per SF
                "labor_rate": 75.0,  # $75/hr for roofing labor
                "material_cost_per_unit": 0.0,  # No material cost for tear-off
                "equipment_cost_per_unit": 1.5,  # $1.5/SF for dumpster/disposal equipment
            }
            if missing_data_warnings is not None:
                missing_data_warnings.append(
                    "roof_tearoff.yml rule not found - using default pricing"
                )

        # Get base costs
        base_unit_cost = rule.get("base_unit_cost", 4.0)
        labor_hours_per_unit = rule.get("labor_hours_per_unit", 0.08)
        base_labor_rate = rule.get("labor_rate", 75.0)
        base_material_cost = rule.get("material_cost_per_unit", 0.0)
        base_equipment_cost = rule.get("equipment_cost_per_unit", 1.5)

        # Apply pricing profile if available
        labor_rate = base_labor_rate
        material_cost = base_material_cost
        equipment_cost = base_equipment_cost
        multiplier_breakdown: list[str] = []

        if pricing_profile:
            # Apply roofing labor rate if available
            if pricing_profile.labor_rates.general_labor is not None:
                old_rate = labor_rate
                labor_rate = pricing_profile.labor_rates.general_labor
                if old_rate != labor_rate:
                    multiplier_breakdown.append(
                        f"labor_rate: {pricing_profile.region} general (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)"
                    )
            
            # Apply dumpster/disposal equipment rates if available
            if pricing_profile.equipment_rates.dumpster_weekly is not None:
                # Convert weekly to per-SF (rough estimate: assume 1 week for typical job)
                # This is a simplification - in reality, disposal cost depends on job size and duration
                old_cost = equipment_cost
                # Assume dumpster weekly rate applies to portion of job
                equipment_cost = base_equipment_cost * 1.2  # 20% increase if dumpster rate specified
                if old_cost != equipment_cost:
                    multiplier_breakdown.append(
                        f"equipment_rate: {pricing_profile.region} dumpster (+20%)"
                    )

        if labor_regime == "union" and union_multiplier > 1.0:
            old_rate = labor_rate
            labor_rate = labor_rate * union_multiplier
            pct = (union_multiplier - 1.0) * 100
            multiplier_breakdown.append(
                f"union_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)"
            )
        elif labor_regime == "prevailing_wage" and prevailing_wage_multiplier > 1.0:
            old_rate = labor_rate
            labor_rate = labor_rate * prevailing_wage_multiplier
            pct = (prevailing_wage_multiplier - 1.0) * 100
            multiplier_breakdown.append(
                f"prevailing_wage_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr) - DOT/public work"
            )

        # Calculate costs
        quantity = roof_assembly.roof_area_sf
        unit = "SF"
        unit_cost = base_unit_cost
        labor_cost = labor_hours_per_unit * labor_rate
        material_cost_total = material_cost * quantity
        equipment_cost_total = equipment_cost * quantity
        waste_factor = 0.0  # No waste for tear-off
        multipliers = {}
        subtotal = (unit_cost + labor_cost + material_cost + equipment_cost) * quantity

        # Create cost item
        from app.schemas.costing import QuantitySource

        item_name = "Roof tear-off & disposal"
        if assumed:
            item_name += " (ASSUMED - review required)"
        elif roof_assembly.tearoff_scope == "partial":
            item_name += " (partial)"
        
        notes = [
            f"Tear-off scope: {roof_assembly.tearoff_scope}",
        ]
        if roof_assembly.disposal_requirement:
            notes.append(f"Disposal: {roof_assembly.disposal_requirement[:100]}")
        if assumed:
            notes.append("⚠️ Tear-off scope not specified - assumed full. Review required.")

        return CostItem(
            item_name=item_name,
            scope_item="roof tear-off",
            quantity=quantity,
            unit=unit,
            unit_cost=unit_cost,
            material_cost=material_cost,
            labor_cost=labor_cost,
            equipment_cost=equipment_cost,
            waste_factor=waste_factor,
            multipliers=multipliers,
            subtotal=subtotal,
            rule_matched="roof_tearoff",
            evidence=roof_assembly.evidence,
            notes=notes,
            quantity_source="from_drawing",
            quantity_confidence=0.85 if not assumed else 0.5,  # Lower confidence if assumed
            quantity_evidence={
                "evidence_snippet": roof_assembly.evidence,
                "tearoff_scope": roof_assembly.tearoff_scope,
                "assumed": assumed,
            },
            profile_id=profile_id,
            multiplier_breakdown=multiplier_breakdown,
            override_source=override_source,
        )

    def _apply_manual_overrides_to_roof_assembly(
        self,
        project_id: str | None,
        roof_assembly: RoofAssembly | None,
        overrides: dict[str, Any],
        missing_data_warnings: list[str],
    ) -> tuple[RoofAssembly | None, bool]:
        """Apply manual roof overrides, returning updated assembly and flag."""

        override_applied = False

        roof_area_override = overrides.get("roof_area_sf")
        membrane_override = overrides.get("membrane_type")
        insulation_override = overrides.get("insulation_thickness_in")

        if roof_assembly is None and roof_area_override:
            roof_assembly = RoofAssembly(
                roof_area_sf=roof_area_override,
                system_type=membrane_override or "Unknown",
                insulation_thickness_in=insulation_override,
                tearoff_included=True,
                tearoff_scope="unknown",
                disposal_requirement=None,
                perimeter_length_lf=None,
                edge_metal_lf=None,
                base_flashing_lf=None,
                perimeter_confidence=0.3,
                evidence="Manual override input",
            )
            override_applied = True
        elif roof_assembly is not None:
            update_payload: dict[str, Any] = {}
            if roof_area_override:
                update_payload["roof_area_sf"] = roof_area_override
            if membrane_override:
                update_payload["system_type"] = membrane_override
            if insulation_override is not None:
                update_payload["insulation_thickness_in"] = insulation_override

            if update_payload:
                override_applied = True
                evidence_bits = []
                if roof_assembly.evidence:
                    evidence_bits.append(roof_assembly.evidence)
                evidence_bits.append("Manual override applied")
                update_payload["evidence"] = " | ".join(evidence_bits)
                roof_assembly = roof_assembly.model_copy(update=update_payload)

        if override_applied:
            missing_data_warnings.append("Manual overrides applied to roof assembly for testing.")
            logger.info(
                "Manual overrides active for project %s: %s",
                project_id or "unknown",
                {k: v for k, v in overrides.items() if v is not None},
            )

        return roof_assembly, override_applied

    def compute_cost(
        self,
        extraction: ExtractionResult,
        geometry: Model3D | None = None,
        pricing_profile: PricingProfile | None = None,
        labor_regime: str | None = None,
        labor_regime_confidence: float = 0.5,
        prevailing_wage_multiplier: float = 1.5,
        union_multiplier: float = 1.0,
        requires_prevailing_wage: bool = False,
        requires_bonds: bool = False,
        requires_insurance: bool = False,
        bond_rate_pct: float = 0.0,
        insurance_rate_pct: float = 0.0,
        procurement_context: dict[str, Any] | None = None,
        *,
        project_id: str | None = None,
        manual_overrides: ManualOverrides | dict[str, Any] | None = None,
    ) -> CostEngineResult:
        """
        Compute costs from extraction result and geometry.
        
        Phase 7.4: Also binds detail references to cost items.
        """
        """
        Compute costs from extraction result and geometry.

        Args:
            extraction: Stage 2 extraction result
            geometry: Stage 3 3D model (optional, for building-specific costs)

        Returns:
            CostEngineResult with full cost breakdown
        """
        logger.info("Starting cost computation")
        if pricing_profile:
            logger.info(f"Using pricing profile: {pricing_profile.profile_id} ({pricing_profile.label})")

        cost_items: list[CostItem] = []
        missing_rule_candidates: list[MissingRuleCandidate] = []
        rules_used: list[str] = []
        missing_data_warnings: list[str] = []
        cost_justification: list[str] = []
        profile_id = pricing_profile.profile_id if pricing_profile else None

        overrides_dict: dict[str, Any] = {}
        if manual_overrides:
            if isinstance(manual_overrides, ManualOverrides):
                overrides_dict = manual_overrides.sanitized()
            else:
                overrides_dict = {k: v for k, v in manual_overrides.items() if v is not None}

        # Task 2: Check for roof assembly (primary trade = roofing)
        roof_assembly = self._extract_roof_assembly(extraction, missing_data_warnings)
        override_source: Literal["manual_override", "extracted", "computed", "unknown"] = "extracted"

        if overrides_dict:
            roof_assembly, override_applied = self._apply_manual_overrides_to_roof_assembly(
                project_id,
                roof_assembly,
                overrides_dict,
                missing_data_warnings,
            )
            if override_applied:
                override_source = "manual_override"

        if roof_assembly:
            logger.info(
                f"Roof assembly detected: {roof_assembly.system_type}, "
                f"{roof_assembly.roof_area_sf} SF, tearoff={'included' if roof_assembly.tearoff_included else 'separate'}"
            )
            # Create roof assembly line item (dominant item for roofing projects)
            roof_assembly_item = self._create_roof_assembly_cost_item(
                roof_assembly, pricing_profile, missing_data_warnings, profile_id,
                labor_regime=labor_regime, prevailing_wage_multiplier=prevailing_wage_multiplier,
                union_multiplier=union_multiplier,
                override_source=override_source,
            )
            if roof_assembly_item:
                cost_items.append(roof_assembly_item)
                rules_used.append("roof_assembly")
                cost_justification.append(
                    f"Roof replacement system (assembly): {roof_assembly.roof_area_sf} SF × "
                    f"${roof_assembly_item.unit_cost:.2f}/SF = ${roof_assembly_item.subtotal:,.2f}"
                )
            
            # Task 4: Create separate tear-off & disposal cost item if tear-off is required
            if roof_assembly.tearoff_scope in ["full", "partial"]:
                tearoff_item = self._create_tearoff_disposal_cost_item(
                    roof_assembly, pricing_profile, missing_data_warnings, profile_id,
                    labor_regime=labor_regime, prevailing_wage_multiplier=prevailing_wage_multiplier,
                    union_multiplier=union_multiplier,
                    override_source=override_source,
                )
                if tearoff_item:
                    cost_items.append(tearoff_item)
                    if "roof_tearoff" not in rules_used:
                        rules_used.append("roof_tearoff")
                    cost_justification.append(
                        f"Roof tear-off & disposal: {roof_assembly.roof_area_sf} SF × "
                        f"${tearoff_item.unit_cost:.2f}/SF = ${tearoff_item.subtotal:,.2f}"
                    )
            elif roof_assembly.tearoff_scope == "unknown":
                # If tear-off scope is unknown, add as "assumed" with review flag
                tearoff_item = self._create_tearoff_disposal_cost_item(
                    roof_assembly, pricing_profile, missing_data_warnings, profile_id, assumed=True,
                    labor_regime=labor_regime, prevailing_wage_multiplier=prevailing_wage_multiplier,
                    union_multiplier=union_multiplier,
                    override_source=override_source,
                )
                if tearoff_item:
                    cost_items.append(tearoff_item)
                    if "roof_tearoff" not in rules_used:
                        rules_used.append("roof_tearoff")
                    missing_data_warnings.append(
                        "Tear-off scope not specified - assumed full tear-off. Review required."
                    )
                    cost_justification.append(
                        f"Roof tear-off & disposal (ASSUMED - review required): {roof_assembly.roof_area_sf} SF × "
                        f"${tearoff_item.unit_cost:.2f}/SF = ${tearoff_item.subtotal:,.2f}"
                    )
            
            # Task 5: Create edge metal/coping and base flashing cost items if perimeter/edge metal exists
            if roof_assembly.perimeter_length_lf and roof_assembly.perimeter_length_lf > 0:
                # Edge metal/coping
                if roof_assembly.edge_metal_lf and roof_assembly.edge_metal_lf > 0:
                    edge_metal_item = self._create_edge_metal_cost_item(
                        roof_assembly.edge_metal_lf, pricing_profile, missing_data_warnings, profile_id,
                        labor_regime=labor_regime, prevailing_wage_multiplier=prevailing_wage_multiplier,
                        union_multiplier=union_multiplier,
                        override_source=override_source,
                    )
                    if edge_metal_item:
                        cost_items.append(edge_metal_item)
                        if "roof_edge_metal" not in rules_used:
                            rules_used.append("roof_edge_metal")
                        cost_justification.append(
                            f"Roof edge metal/coping: {roof_assembly.edge_metal_lf} LF × "
                            f"${edge_metal_item.unit_cost:.2f}/LF = ${edge_metal_item.subtotal:,.2f}"
                        )
                else:
                    # If edge metal not specified but perimeter exists, use perimeter as estimate
                    edge_metal_item = self._create_edge_metal_cost_item(
                        roof_assembly.perimeter_length_lf, pricing_profile, missing_data_warnings, profile_id, assumed=True,
                        labor_regime=labor_regime, prevailing_wage_multiplier=prevailing_wage_multiplier,
                        union_multiplier=union_multiplier,
                        override_source=override_source,
                    )
                    if edge_metal_item:
                        cost_items.append(edge_metal_item)
                        if "roof_edge_metal" not in rules_used:
                            rules_used.append("roof_edge_metal")
                        if missing_data_warnings is not None:
                            missing_data_warnings.append(
                                f"Edge metal/coping not specified - using perimeter length {roof_assembly.perimeter_length_lf} LF as estimate. Review required."
                            )
                        cost_justification.append(
                            f"Roof edge metal/coping (ASSUMED from perimeter): {roof_assembly.perimeter_length_lf} LF × "
                            f"${edge_metal_item.unit_cost:.2f}/LF = ${edge_metal_item.subtotal:,.2f}"
                        )
                
                # Base flashing
                if roof_assembly.base_flashing_lf and roof_assembly.base_flashing_lf > 0:
                    base_flashing_item = self._create_base_flashing_cost_item(
                        roof_assembly.base_flashing_lf, pricing_profile, missing_data_warnings, profile_id,
                        labor_regime=labor_regime, prevailing_wage_multiplier=prevailing_wage_multiplier,
                        union_multiplier=union_multiplier,
                        override_source=override_source,
                    )
                    if base_flashing_item:
                        cost_items.append(base_flashing_item)
                        if "roof_base_flashing" not in rules_used:
                            rules_used.append("roof_base_flashing")
                        cost_justification.append(
                            f"Roof base flashing: {roof_assembly.base_flashing_lf} LF × "
                            f"${base_flashing_item.unit_cost:.2f}/LF = ${base_flashing_item.subtotal:,.2f}"
                        )
                elif roof_assembly.perimeter_length_lf:
                    # If base flashing not specified but perimeter exists, use perimeter as estimate
                    base_flashing_item = self._create_base_flashing_cost_item(
                        roof_assembly.perimeter_length_lf, pricing_profile, missing_data_warnings, profile_id, assumed=True,
                        labor_regime=labor_regime, prevailing_wage_multiplier=prevailing_wage_multiplier,
                        union_multiplier=union_multiplier,
                        override_source=override_source,
                    )
                    if base_flashing_item:
                        cost_items.append(base_flashing_item)
                        if "roof_base_flashing" not in rules_used:
                            rules_used.append("roof_base_flashing")
                        if missing_data_warnings is not None:
                            missing_data_warnings.append(
                                f"Base flashing not specified - using perimeter length {roof_assembly.perimeter_length_lf} LF as estimate. Review required."
                            )
                        cost_justification.append(
                            f"Roof base flashing (ASSUMED from perimeter): {roof_assembly.perimeter_length_lf} LF × "
                            f"${base_flashing_item.unit_cost:.2f}/LF = ${base_flashing_item.subtotal:,.2f}"
                        )

        # Process scope items
        for scope_item in extraction.scope_of_work:
            rule = self._match_scope_item_to_rule(scope_item)
            if not rule:
                item_name = scope_item.item if hasattr(scope_item, "item") else scope_item.get("item", "Unknown")
                missing_data_warnings.append(
                    f"No cost rule found for scope item: {item_name}"
                )

                description = (
                    scope_item.description
                    if hasattr(scope_item, "description")
                    else scope_item.get("description")
                )
                evidence_snippet = (
                    scope_item.evidence_snippet
                    if hasattr(scope_item, "evidence_snippet")
                    else scope_item.get("evidence_snippet")
                )
                page_number = (
                    scope_item.page_number
                    if hasattr(scope_item, "page_number")
                    else scope_item.get("page_number")
                )
                sheet_id = (
                    scope_item.sheet_id
                    if hasattr(scope_item, "sheet_id")
                    else scope_item.get("sheet_id")
                )

                candidate = MissingRuleCandidate(
                    item_name=item_name,
                    description=description,
                    page_number=page_number,
                    sheet_id=sheet_id,
                    evidence_snippet=evidence_snippet,
                    detected_keywords=[kw for kw in (item_name or "").split() if len(kw) > 3],
                    probable_trade=self._guess_trade_from_scope_item(scope_item),
                    metadata={
                        "labor_regime": labor_regime,
                        "requires_prevailing_wage": requires_prevailing_wage,
                        "requires_bonds": requires_bonds,
                    },
                )
                missing_rule_candidates.append(candidate)
                continue

            rule_name = rule.get("name", "unknown")
            if rule_name not in rules_used:
                rules_used.append(rule_name)

            # Check if this is an allowance item
            is_allowance = rule.get("is_allowance", False) or rule.get("unit_type", "").upper() == "ALLOWANCE"
            
            # Extract item name early (needed for profile application)
            item_name = scope_item.item if hasattr(scope_item, "item") else scope_item.get("item", "Unknown")
            
            # Initialize multiplier_breakdown early for both allowance and non-allowance paths
            multiplier_breakdown: list[str] = []
            
            if is_allowance:
                # Allowance items are lump sum
                quantity = 1.0
                unit = "LS"  # Lump Sum
                base_unit_cost = rule.get("base_unit_cost", 0.0)
                base_labor_rate = rule.get("labor_rate", 50.0)
                base_material_cost = rule.get("material_cost_per_unit", 0.0)
                base_equipment_cost = rule.get("equipment_cost_per_unit", 0.0)
                
                # Phase 10.10B: Apply pricing profile for allowances
                labor_rate = base_labor_rate
                material_cost = base_material_cost
                equipment_cost = base_equipment_cost
                
                if pricing_profile:
                    # Allowances might use general labor rate
                    if pricing_profile.labor_rates.general_labor is not None:
                        old_rate = labor_rate
                        labor_rate = pricing_profile.labor_rates.general_labor
                        if old_rate != labor_rate:
                            multiplier_breakdown.append(f"labor_rate: {pricing_profile.region} general (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)")
                    
                    # Apply material multipliers if applicable
                    item_name_lower = item_name.lower()
                    if base_material_cost > 0:
                        if "brick" in item_name_lower and pricing_profile.material_multipliers.brick is not None:
                            material_cost = base_material_cost * pricing_profile.material_multipliers.brick
                            pct = (pricing_profile.material_multipliers.brick - 1.0) * 100
                            multiplier_breakdown.append(f"material_multiplier: {pricing_profile.region} brick (+{pct:.0f}%)")
                
                if labor_regime == "union" and union_multiplier > 1.0:
                    old_rate = labor_rate
                    labor_rate = labor_rate * union_multiplier
                    pct = (union_multiplier - 1.0) * 100
                    multiplier_breakdown.append(
                        f"union_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr) - collective bargaining"
                    )
                elif labor_regime == "prevailing_wage" and prevailing_wage_multiplier > 1.0:
                    old_rate = labor_rate
                    labor_rate = labor_rate * prevailing_wage_multiplier
                    pct = (prevailing_wage_multiplier - 1.0) * 100
                    multiplier_breakdown.append(
                        f"prevailing_wage_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr) - DOT/public work"
                    )
                
                unit_cost = base_unit_cost
                labor_cost = rule.get("labor_hours_per_unit", 0.0) * labor_rate
                waste_factor = 0.0
                multipliers = {}
                subtotal = base_unit_cost
                # Phase 4.7: Allowance provenance
                from app.schemas.costing import QuantitySource
                quantity_source: QuantitySource = "allowance"
                quantity_confidence = 0.9  # Allowances are intentional
                quantity_evidence = {
                    "evidence_snippet": f"Allowance item: {rule_name}",
                }
            else:
                # Calculate quantity with provenance (Phase 4.7)
                quantity, unit, quantity_source, quantity_confidence, quantity_evidence = self._calculate_quantity(
                    scope_item, extraction
                )

                # Get base costs from rule
                base_unit_cost = rule.get("base_unit_cost", 0.0)
                labor_hours_per_unit = rule.get("labor_hours_per_unit", 0.0)
                base_labor_rate = rule.get("labor_rate", 50.0)  # Default $50/hr
                base_material_cost_per_unit = rule.get("material_cost_per_unit", 0.0)
                base_equipment_cost_per_unit = rule.get("equipment_cost_per_unit", 0.0)

                # Phase 10.10B: Apply pricing profile multipliers
                labor_rate = base_labor_rate
                material_cost_per_unit = base_material_cost_per_unit
                equipment_cost_per_unit = base_equipment_cost_per_unit
                # multiplier_breakdown already initialized above

                if pricing_profile:
                    # Apply labor rate override by trade/division
                    category = rule.get("category", "").lower()
                    item_name_lower = item_name.lower()
                    
                    # Determine trade for labor rate lookup
                    if "masonry" in category or "brick" in item_name_lower or "repoint" in item_name_lower or "parapet" in item_name_lower:
                        if pricing_profile.labor_rates.masonry is not None:
                            old_rate = labor_rate
                            labor_rate = pricing_profile.labor_rates.masonry
                            if old_rate != labor_rate:
                                multiplier_breakdown.append(f"labor_rate: {pricing_profile.region} masonry (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)")
                    elif "concrete" in category or "concrete" in item_name_lower:
                        if pricing_profile.labor_rates.concrete is not None:
                            old_rate = labor_rate
                            labor_rate = pricing_profile.labor_rates.concrete
                            if old_rate != labor_rate:
                                multiplier_breakdown.append(f"labor_rate: {pricing_profile.region} concrete (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)")
                    elif "steel" in category or "steel" in item_name_lower or "lintel" in item_name_lower or "structural" in item_name_lower:
                        if pricing_profile.labor_rates.steel is not None:
                            old_rate = labor_rate
                            labor_rate = pricing_profile.labor_rates.steel
                            if old_rate != labor_rate:
                                multiplier_breakdown.append(f"labor_rate: {pricing_profile.region} steel (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)")
                    elif "carpentry" in category or "carpentry" in item_name_lower:
                        if pricing_profile.labor_rates.carpentry is not None:
                            old_rate = labor_rate
                            labor_rate = pricing_profile.labor_rates.carpentry
                            if old_rate != labor_rate:
                                multiplier_breakdown.append(f"labor_rate: {pricing_profile.region} carpentry (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)")
                    else:
                        # Default to general labor if available
                        if pricing_profile.labor_rates.general_labor is not None:
                            old_rate = labor_rate
                            labor_rate = pricing_profile.labor_rates.general_labor
                            if old_rate != labor_rate:
                                multiplier_breakdown.append(f"labor_rate: {pricing_profile.region} general (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)")
                    
                    # Check custom rates
                    for trade, rate in pricing_profile.labor_rates.custom_rates.items():
                        if trade.lower() in category or trade.lower() in item_name_lower:
                            old_rate = labor_rate
                            labor_rate = rate
                            if old_rate != labor_rate:
                                multiplier_breakdown.append(f"labor_rate: {pricing_profile.region} {trade} (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr)")

                if labor_regime == "union" and union_multiplier > 1.0:
                    old_rate = labor_rate
                    labor_rate = labor_rate * union_multiplier
                    pct = (union_multiplier - 1.0) * 100
                    multiplier_breakdown.append(
                        f"union_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr) - collective bargaining"
                    )
                elif labor_regime == "prevailing_wage" and prevailing_wage_multiplier > 1.0:
                    old_rate = labor_rate
                    labor_rate = labor_rate * prevailing_wage_multiplier
                    pct = (prevailing_wage_multiplier - 1.0) * 100
                    multiplier_breakdown.append(
                        f"prevailing_wage_multiplier: {pct:.0f}% (${old_rate:.0f}/hr → ${labor_rate:.0f}/hr) - DOT/public work"
                    )

                # Apply material multipliers by keywords
                if base_material_cost_per_unit > 0:
                    material_multiplier = 1.0
                    material_keyword = None

                    if "brick" in item_name_lower:
                        material_keyword = "brick"
                        if pricing_profile.material_multipliers.brick is not None:
                            material_multiplier = pricing_profile.material_multipliers.brick
                    elif "mortar" in item_name_lower or "repoint" in item_name_lower:
                        material_keyword = "mortar"
                        if pricing_profile.material_multipliers.mortar is not None:
                            material_multiplier = pricing_profile.material_multipliers.mortar
                    elif "concrete" in item_name_lower:
                        material_keyword = "concrete"
                        if pricing_profile.material_multipliers.concrete is not None:
                            material_multiplier = pricing_profile.material_multipliers.concrete
                    elif "steel" in item_name_lower:
                        material_keyword = "steel"
                        if pricing_profile.material_multipliers.steel is not None:
                            material_multiplier = pricing_profile.material_multipliers.steel
                    elif "cmu" in item_name_lower:
                        material_keyword = "cmu"
                        if pricing_profile.material_multipliers.cmu is not None:
                            material_multiplier = pricing_profile.material_multipliers.cmu

                    # Check custom material multipliers
                    if material_multiplier == 1.0:
                        for mat_keyword, mult in pricing_profile.material_multipliers.custom_multipliers.items():
                            if mat_keyword.lower() in item_name_lower:
                                material_multiplier = mult
                                material_keyword = mat_keyword
                                break

                    if material_multiplier != 1.0 and material_keyword:
                        old_cost = material_cost_per_unit
                        material_cost_per_unit = base_material_cost_per_unit * material_multiplier
                        pct_change = (material_multiplier - 1.0) * 100
                        multiplier_breakdown.append(f"material_multiplier: {pricing_profile.region} {material_keyword} (+{pct_change:.0f}%)")
                    
                    # Apply equipment rate multipliers/overrides
                    if base_equipment_cost_per_unit > 0:
                        equipment_keyword = None
                        equipment_multiplier = 1.0
                        
                        if "scaffold" in item_name_lower:
                            # Scaffold is typically weekly, use weekly rate if available
                            if pricing_profile.equipment_rates.scaffold_weekly is not None:
                                # This would need to be converted based on duration
                                # For now, just apply a multiplier if scaffold_weekly exists
                                equipment_keyword = "scaffold"
                                # Apply as multiplier: scaffold_weekly / base (assume base is for standard period)
                                equipment_multiplier = pricing_profile.equipment_rates.scaffold_weekly / max(base_equipment_cost_per_unit, 1.0)
                        elif "dumpster" in item_name_lower:
                            if pricing_profile.equipment_rates.dumpster_weekly is not None:
                                equipment_keyword = "dumpster"
                                equipment_multiplier = pricing_profile.equipment_rates.dumpster_weekly / max(base_equipment_cost_per_unit, 1.0)
                        elif "crane" in item_name_lower:
                            if pricing_profile.equipment_rates.crane_daily is not None:
                                equipment_keyword = "crane"
                                equipment_multiplier = pricing_profile.equipment_rates.crane_daily / max(base_equipment_cost_per_unit, 1.0)
                        
                        # Check custom equipment rates
                        if equipment_multiplier == 1.0:
                            for equip_keyword, rate in pricing_profile.equipment_rates.custom_rates.items():
                                if equip_keyword.lower() in item_name_lower:
                                    equipment_multiplier = rate / max(base_equipment_cost_per_unit, 1.0)
                                    equipment_keyword = equip_keyword
                                    break
                        
                        if equipment_multiplier != 1.0 and equipment_keyword:
                            old_cost = equipment_cost_per_unit
                            equipment_cost_per_unit = base_equipment_cost_per_unit * equipment_multiplier
                            pct_change = (equipment_multiplier - 1.0) * 100
                            multiplier_breakdown.append(f"equipment_rate: {pricing_profile.region} {equipment_keyword} (+{pct_change:.0f}%)")

                # Apply multipliers
                unit_cost, multipliers = self._apply_multipliers(
                    base_unit_cost, rule, extraction
                )

                # Calculate waste factor
                waste_factor = rule.get("waste_factor", 0.0)
                waste_cost = (unit_cost * quantity) * waste_factor

                # Calculate component costs
                material_cost = (material_cost_per_unit * quantity) * (
                    1 + waste_factor
                )  # Waste applies to materials
                labor_cost = (labor_hours_per_unit * quantity) * labor_rate
                equipment_cost = equipment_cost_per_unit * quantity

                # Subtotal
                subtotal = (unit_cost * quantity) + waste_cost
                
                # Add warning if heuristic quantity used
                if quantity_source == "heuristic":
                    missing_data_warnings.append(
                        f"Heuristic quantity used for {item_name}: {quantity} {unit} (confidence: {quantity_confidence:.1%})"
                    )

            # Extract evidence
            evidence = scope_item.evidence_snippet if hasattr(scope_item, "evidence_snippet") else scope_item.get("evidence_snippet", "")

            cost_item = CostItem(
                item_name=item_name,
                scope_item=item_name,
                quantity=quantity,
                unit=unit,
                unit_cost=unit_cost,
                material_cost=material_cost,
                labor_cost=labor_cost,
                equipment_cost=equipment_cost,
                waste_factor=waste_factor,
                multipliers=multipliers,
                subtotal=subtotal,
                rule_matched=rule_name,
                evidence=evidence,
                notes=[f"Matched rule: {rule_name}"],
                quantity_source=quantity_source,
                quantity_confidence=quantity_confidence,
                quantity_evidence=quantity_evidence,
                profile_id=profile_id,  # Phase 10.10B
                multiplier_breakdown=multiplier_breakdown,  # Phase 10.10B
            )

            cost_items.append(cost_item)
            cost_justification.append(
                f"{item_name}: {quantity} {unit} @ ${unit_cost:.2f}/{unit} = ${subtotal:.2f}"
            )

        # Process materials (add to existing items or create new)
        for material in extraction.material_specifications:
            rule = self._match_material_to_rule(material)
            if rule:
                # Materials typically augment existing scope items
                # For now, we'll create separate cost items for significant materials
                material_name = material.material_name if hasattr(material, "material_name") else material.get("material_name", "")
                if "lintel" in material_name.lower():
                    # Lintel materials are already covered by lintel replacement scope item
                    continue

        # Group by category
        breakdown_by_category: list[CostBreakdown] = []
        category_map: dict[str, list[CostItem]] = {}

        for item in cost_items:
            # Determine category from rule (if available) or item type
            category = "General"
            
            # Try to get category from the rule that was matched
            if item.rule_matched:
                matched_rule = self.rules.get(item.rule_matched.replace(" ", "_").lower())
                if matched_rule:
                    category = matched_rule.get("category", category)
            
            # Fallback to item name matching if rule doesn't specify
            if category == "General":
                item_lower = item.item_name.lower()
                if "parapet" in item_lower or "brick" in item_lower or "repoint" in item_lower or "cmu" in item_lower or "masonry" in item_lower:
                    category = "Masonry"
                elif "lintel" in item_lower or "steel" in item_lower or "structural" in item_lower or "hss" in item_lower or "beam" in item_lower:
                    category = "Structural"
                elif "concrete" in item_lower or "footing" in item_lower or "slab" in item_lower:
                    category = "Concrete"
                elif "flash" in item_lower:
                    category = "Waterproofing"
                elif "demo" in item_lower or "removal" in item_lower:
                    category = "Demo"
                elif "crack" in item_lower:
                    category = "Repairs"
                elif "light gauge" in item_lower or "metal stud" in item_lower:
                    category = "Metals"

            if category not in category_map:
                category_map[category] = []
            category_map[category].append(item)

        for category, items in category_map.items():
            subtotal = sum(item.subtotal for item in items)
            breakdown_by_category.append(
                CostBreakdown(category=category, items=items, subtotal=subtotal)
            )

        # Calculate totals
        total_cost = sum(item.subtotal for item in cost_items)
        material_cost_total = sum(item.material_cost for item in cost_items)
        labor_cost_total = sum(item.labor_cost for item in cost_items)
        equipment_cost_total = sum(item.equipment_cost for item in cost_items)
        waste_cost_total = sum(item.subtotal * item.waste_factor for item in cost_items)

        # Subtotals by category
        subtotals = {bd.category: bd.subtotal for bd in breakdown_by_category}

        # Breakdown by building (if geometry provided)
        breakdown_by_building: dict[str, list[CostItem]] = {}
        if geometry and geometry.buildings:
            # For now, assign all costs to first building
            # In future, could split by building-specific work zones
            subject_building = next(
                (b for b in geometry.buildings if b.is_subject), geometry.buildings[0]
            )
            building_id = subject_building.building_id or "subject"
            breakdown_by_building[building_id] = cost_items

        compliance_summary: list[str] = []
        
        # Build context for explanations
        procurement_context_str = ""
        if procurement_context:
            issuing_authority = procurement_context.get("issuing_authority")
            if issuing_authority:
                procurement_context_str = f" ({issuing_authority} project detected)"
            elif procurement_context.get("is_public_project"):
                procurement_context_str = " (Government/public project detected)"
        
        if labor_regime == "prevailing_wage" and prevailing_wage_multiplier > 1.0:
            pct = (prevailing_wage_multiplier - 1.0) * 100
            compliance_summary.append(
                f"Prevailing wage multiplier applied: +{pct:.0f}% to labor rates{procurement_context_str}. "
                f"Required for public/government projects per Davis-Bacon or state prevailing wage laws."
            )
        if labor_regime == "union" and union_multiplier > 1.0:
            pct = (union_multiplier - 1.0) * 100
            compliance_summary.append(
                f"Union labor multiplier applied: +{pct:.0f}% to labor rates. "
                f"Union labor regime detected in project requirements."
            )

        base_scope_cost = total_cost
        compliance_costs: dict[str, float] = {}
        
        # Phase 1: Log compliance parameters for debugging
        logger.bind(project_id=project_id).error(  # Use ERROR so it definitely shows up
            f"PHASE1: Cost engine compliance - requires_bonds={requires_bonds} (type: {type(requires_bonds).__name__}), "
            f"bond_rate_pct={bond_rate_pct} (type: {type(bond_rate_pct).__name__}), "
            f"requires_insurance={requires_insurance}, insurance_rate_pct={insurance_rate_pct}, "
            f"base_scope_cost={base_scope_cost}, labor_regime={labor_regime}"
        )

        if requires_bonds and bond_rate_pct > 0.0:
            logger.bind(project_id=project_id).error(f"PHASE1: CALCULATING BOND COST: {base_scope_cost} * ({bond_rate_pct}/100) = {base_scope_cost * (bond_rate_pct / 100.0)}")
            bond_cost = base_scope_cost * (bond_rate_pct / 100.0)
            compliance_costs["bond"] = round(bond_cost, 2)
            compliance_summary.append(
                f"Performance & Payment Bonds: +{bond_rate_pct:.2f}% of base scope (${bond_cost:,.2f}){procurement_context_str}. "
                f"Required for public/government contracts to protect the owner."
            )

        if requires_insurance and insurance_rate_pct > 0.0:
            insurance_cost = base_scope_cost * (insurance_rate_pct / 100.0)
            compliance_costs["insurance"] = round(insurance_cost, 2)
            compliance_summary.append(
                f"Supplemental Insurance: +{insurance_rate_pct:.2f}% of base scope (${insurance_cost:,.2f}){procurement_context_str}. "
                f"Additional coverage required for public/government projects."
            )

        compliance_total = sum(compliance_costs.values())
        total_cost += compliance_total

        contingency_pct = None
        contingency_amount = None
        if pricing_profile and hasattr(pricing_profile, "contingency_pct_default"):
            contingency_pct = pricing_profile.contingency_pct_default
        elif hasattr(self, "default_contingency_pct"):
            contingency_pct = getattr(self, "default_contingency_pct")  # type: ignore[attr-defined]

        # Adjust contingency recommendation for high risk contexts
        risk_multiplier = 1.0
        if requires_bonds or requires_insurance:
            risk_multiplier += 0.1
        if len(missing_data_warnings) >= 5:
            risk_multiplier += 0.1
        if len(missing_rule_candidates) >= 3:
            risk_multiplier += 0.1

        if contingency_pct is not None:
            contingency_pct = round(contingency_pct * risk_multiplier, 2)
            contingency_amount = round((base_scope_cost + compliance_total) * (contingency_pct / 100.0), 2)

        rule_governance_report: RuleGovernanceReport | None = None
        if missing_rule_candidates:
            rule_governance_report = RuleGovernanceReport(
                project_id=project_id,
                missing_rules=missing_rule_candidates,
                notes=[
                    "Cost engine detected scope items without matching YAML rules. Review and author new rules using the governance helper."
                ],
            )

        result = CostEngineResult(
            project_id=extraction.project_type,  # Use project type as ID placeholder
            breakdown_by_category=breakdown_by_category,
            breakdown_by_scope_item=cost_items,
            breakdown_by_building=breakdown_by_building,
            subtotals=subtotals,
            total_cost=total_cost,
            material_cost_total=material_cost_total,
            labor_cost_total=labor_cost_total,
            equipment_cost_total=equipment_cost_total,
            waste_cost_total=waste_cost_total,
            cost_justification=cost_justification,
            missing_data_warnings=missing_data_warnings,
            rules_used=rules_used,
            profile_id=profile_id,  # Phase 10.10B
            compliance_adjustments=compliance_summary,
            compliance_costs=compliance_costs,
            compliance_total=compliance_total,
            base_scope_cost=base_scope_cost,
            contingency_recommendation_pct=contingency_pct,
            contingency_recommendation_amount=contingency_amount,
            rule_governance=rule_governance_report,
        )

        # Phase 7.4: Bind detail references to cost items
        from app.services.detail_binding import bind_details_to_cost_items
        cost_items = bind_details_to_cost_items(extraction, cost_items)
        
        # Update breakdown_by_scope_item with detail_refs
        result.breakdown_by_scope_item = cost_items
        # Also update breakdown_by_category items
        for category_breakdown in result.breakdown_by_category:
            for item in category_breakdown.items:
                # Find matching item in cost_items and update detail_refs
                matching_item = next(
                    (ci for ci in cost_items if ci.item_name == item.item_name),
                    None,
                )
                if matching_item:
                    item.detail_refs = matching_item.detail_refs

        logger.info(
            f"Cost computation complete: ${total_cost:,.2f} total, "
            f"{len(cost_items)} items, {len(rules_used)} rules used"
        )

        return result

