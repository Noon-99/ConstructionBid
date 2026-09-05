"""Finish mapping service for institutional projects (Phase 7.2).

Deterministic mapping from room types to finish assemblies.
Config-driven via YAML, no hardcoding.
"""

import yaml
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.room_schedule import RoomSchedule, RoomScheduleItem


class FinishMapper:
    """Maps room types to finish assemblies deterministically."""

    def __init__(self, settings: Settings) -> None:
        """Initialize finish mapper with config."""
        self.settings = settings
        self.finish_rules = self._load_finish_rules()

    def _load_finish_rules(self) -> dict[str, Any]:
        """Load finish mapping rules from YAML config."""
        # Default rules path
        rules_dir = Path(__file__).parent.parent / "costing" / "rules"
        
        # Load finish-specific rules
        finish_rules: dict[str, Any] = {}
        
        # Paint rule
        paint_file = rules_dir / "paint_wall_ceiling.yml"
        if paint_file.exists():
            with open(paint_file, "r") as f:
                paint_rule = yaml.safe_load(f)
                if paint_rule:
                    finish_rules["paint"] = paint_rule
        
        # Flooring rule
        flooring_file = rules_dir / "flooring_vct.yml"
        if flooring_file.exists():
            with open(flooring_file, "r") as f:
                flooring_rule = yaml.safe_load(f)
                if flooring_rule:
                    finish_rules["flooring"] = flooring_rule
        
        # Ceiling rule
        ceiling_file = rules_dir / "ceiling_act.yml"
        if ceiling_file.exists():
            with open(ceiling_file, "r") as f:
                ceiling_rule = yaml.safe_load(f)
                if ceiling_rule:
                    finish_rules["ceiling"] = ceiling_rule
        
        logger.info(f"Loaded {len(finish_rules)} finish mapping rules")
        return finish_rules

    def map_room_to_finishes(
        self, room: RoomScheduleItem
    ) -> dict[str, dict[str, Any]]:
        """
        Map a room to finish assemblies.

        Args:
            room: Room schedule item

        Returns:
            Dictionary of finish types to quantities:
            {
                "paint": {"quantity_sf": 500, "rule": {...}},
                "flooring": {"quantity_sf": 250, "rule": {...}},
                "ceiling": {"quantity_sf": 250, "rule": {...}}
            }
        """
        finishes: dict[str, dict[str, Any]] = {}
        
        # Base area from room
        room_area = room.area_sf
        
        # Determine usage type for multipliers
        usage_type = room.usage_type or self._infer_usage_type(room.room_name)
        
        # Paint: wall + ceiling area (uses multipliers from YAML)
        if "paint" in self.finish_rules:
            paint_rule = self.finish_rules["paint"]
            # Get multiplier from rule (multipliers dict in YAML)
            multipliers = paint_rule.get("multipliers", {})
            multiplier = multipliers.get(usage_type or "default", multipliers.get("default", 2.8))
            
            # Multiplier already accounts for wall + ceiling area
            paint_area = room_area * multiplier
            finishes["paint"] = {
                "quantity_sf": paint_area,
                "rule": paint_rule,
                "basis": f"Room {room.room_id or room.room_name} area: {room_area} SF × {multiplier} multiplier ({usage_type or 'default'})",
                "evidence": {
                    "page_number": room.evidence.page_number,
                    "sheet_id": room.evidence.sheet_id,
                    "evidence_snippet": f"Room schedule area: {room.room_name}",
                },
            }
        
        # Flooring: direct area (may have usage type adjustments)
        if "flooring" in self.finish_rules:
            flooring_rule = self.finish_rules["flooring"]
            flooring_area = room_area
            
            # Adjust by usage type if specified (check multipliers dict)
            multipliers = flooring_rule.get("multipliers", {})
            if usage_type in multipliers:
                flooring_area *= multipliers[usage_type]
            elif "default" in multipliers:
                flooring_area *= multipliers["default"]
            
            finishes["flooring"] = {
                "quantity_sf": flooring_area,
                "rule": flooring_rule,
                "basis": f"Room {room.room_id or room.room_name} area: {room_area} SF",
                "evidence": {
                    "page_number": room.evidence.page_number,
                    "sheet_id": room.evidence.sheet_id,
                    "evidence_snippet": f"Room schedule area: {room.room_name}",
                },
            }
        
        # Ceiling: direct area (typically same as floor)
        if "ceiling" in self.finish_rules:
            ceiling_rule = self.finish_rules["ceiling"]
            ceiling_area = room_area
            
            # Adjust by usage type if specified (check multipliers dict)
            multipliers = ceiling_rule.get("multipliers", {})
            if usage_type in multipliers:
                ceiling_area *= multipliers[usage_type]
            elif "default" in multipliers:
                ceiling_area *= multipliers["default"]
            
            finishes["ceiling"] = {
                "quantity_sf": ceiling_area,
                "rule": ceiling_rule,
                "basis": f"Room {room.room_id or room.room_name} area: {room_area} SF",
                "evidence": {
                    "page_number": room.evidence.page_number,
                    "sheet_id": room.evidence.sheet_id,
                    "evidence_snippet": f"Room schedule area: {room.room_name}",
                },
            }
        
        return finishes

    def map_schedule_to_finishes(
        self, room_schedule: RoomSchedule
    ) -> dict[str, dict[str, Any]]:
        """
        Map entire room schedule to finish quantities.

        Args:
            room_schedule: Complete room schedule

        Returns:
            Aggregated finish quantities:
            {
                "paint": {"total_sf": 5000, "rooms": [...], "evidence": {...}},
                "flooring": {"total_sf": 2500, "rooms": [...], "evidence": {...}},
                "ceiling": {"total_sf": 2500, "rooms": [...], "evidence": {...}}
            }
        """
        aggregated: dict[str, dict[str, Any]] = {}
        
        for room in room_schedule.rooms:
            room_finishes = self.map_room_to_finishes(room)
            
            for finish_type, finish_data in room_finishes.items():
                if finish_type not in aggregated:
                    aggregated[finish_type] = {
                        "total_sf": 0.0,
                        "rooms": [],
                        "evidence": [],
                    }
                
                aggregated[finish_type]["total_sf"] += finish_data["quantity_sf"]
                aggregated[finish_type]["rooms"].append({
                    "room_id": room.room_id,
                    "room_name": room.room_name,
                    "area_sf": room.area_sf,
                    "quantity_sf": finish_data["quantity_sf"],
                    "basis": finish_data["basis"],
                })
                aggregated[finish_type]["evidence"].append(finish_data["evidence"])
        
        return aggregated

    def _infer_usage_type(self, room_name: str) -> str | None:
        """
        Infer usage type from room name (deterministic, no AI).

        Args:
            room_name: Room name string

        Returns:
            Inferred usage type or None
        """
        room_name_lower = room_name.lower()
        
        # Gym/athletic
        if any(word in room_name_lower for word in ["gym", "gymnasium", "athletic", "basketball", "court"]):
            return "gym"
        
        # Toilet/restroom
        if any(word in room_name_lower for word in ["toilet", "restroom", "bathroom", "lavatory", "wc"]):
            return "toilet"
        
        # Office
        if any(word in room_name_lower for word in ["office", "desk", "workstation"]):
            return "office"
        
        # Classroom
        if any(word in room_name_lower for word in ["classroom", "class", "room"]):
            return "classroom"
        
        # Corridor/hallway
        if any(word in room_name_lower for word in ["corridor", "hallway", "hall", "passage"]):
            return "corridor"
        
        # Kitchen/cafeteria
        if any(word in room_name_lower for word in ["kitchen", "cafeteria", "dining"]):
            return "kitchen"
        
        # Auditorium
        if any(word in room_name_lower for word in ["auditorium", "theater", "theatre"]):
            return "auditorium"
        
        return None

