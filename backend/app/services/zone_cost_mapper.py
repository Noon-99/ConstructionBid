"""Zone cost mapper (Phase 8.3).

Maps 3D zones to bid line items and computes cost attribution.
"""

import re
from datetime import datetime
from typing import Any

from loguru import logger

from app.schemas.zone_cost_map import (
    TopLineItem,
    ZoneCostItem,
    ZoneCostMap,
)


class ZoneCostMapper:
    """Maps zones to bid line items and computes costs."""

    # Stopwords to ignore in keyword matching
    STOPWORDS = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "should",
        "could",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
    }

    def __init__(self) -> None:
        """Initialize zone cost mapper."""
        pass

    def generate(
        self,
        project_id: str,
        model_3d: dict[str, Any],
        bid_review: dict[str, Any],
        evidence_index: dict[str, Any] | None = None,
    ) -> ZoneCostMap:
        """
        Generate zone cost map.

        Args:
            project_id: Project ID
            model_3d: Model3D JSON (from model_3d.json)
            bid_review: BidReview JSON (from bid_review.json)
            evidence_index: EvidenceIndex JSON (optional, from evidence_index.json)

        Returns:
            ZoneCostMap with cost attribution for each zone
        """
        log_ctx = logger.bind(project_id=project_id, stage="zone_cost_map")
        log_ctx.info("Generating zone cost map")

        # Extract zones from model_3d
        work_zones = model_3d.get("work_zones", [])
        if not work_zones:
            log_ctx.warning("No work zones found in model_3d")
            return ZoneCostMap(
                project_id=project_id,
                generated_at=datetime.utcnow().isoformat(),
                zones=[],
                max_cost=0.0,
                min_cost=0.0,
            )

        # Extract line items from bid_review
        line_items = bid_review.get("line_items", [])
        if not line_items:
            log_ctx.warning("No line items found in bid_review")
            return ZoneCostMap(
                project_id=project_id,
                generated_at=datetime.utcnow().isoformat(),
                zones=[],
                max_cost=0.0,
                min_cost=0.0,
            )

        # Build zone evidence lookup from evidence_index
        zone_evidence_lookup: dict[str, dict[str, Any]] = {}
        if evidence_index:
            for zone_evidence in evidence_index.get("zone_evidence", []):
                zone_id = zone_evidence.get("zone_id")
                if zone_id:
                    zone_evidence_lookup[zone_id] = zone_evidence

        # Generate cost attribution for each zone
        zone_cost_items: list[ZoneCostItem] = []
        for zone in work_zones:
            zone_name = zone.get("zone_name", "")
            zone_id = zone_name  # Use zone_name as zone_id (they're the same in WorkZoneVolume)
            zone_type = zone.get("zone_type")

            # Find linked line items using priority:
            # 1. evidence_index explicit links
            # 2. keyword fallback
            # 3. none
            linked_item_indices: list[int] = []
            attribution_method: str = "none"

            # Priority 1: Check evidence_index
            if zone_id in zone_evidence_lookup:
                zone_evidence = zone_evidence_lookup[zone_id]
                linked_bid_items = zone_evidence.get("linked_bid_items", [])
                if linked_bid_items:
                    linked_item_indices = linked_bid_items
                    attribution_method = "evidence_index"
                    log_ctx.debug(
                        f"Zone '{zone_name}' linked via evidence_index: {linked_bid_items}"
                    )

            # Priority 2: Keyword fallback
            if not linked_item_indices:
                linked_item_indices = self._keyword_match_zone_to_items(
                    zone_name, line_items
                )
                if linked_item_indices:
                    attribution_method = "keyword_fallback"
                    log_ctx.debug(
                        f"Zone '{zone_name}' linked via keyword match: {linked_item_indices}"
                    )

            # Compute costs for this zone
            total_cost = 0.0
            division_breakdown: dict[str, float] = {}
            top_items_data: list[dict[str, Any]] = []

            for item_idx in linked_item_indices:
                if 0 <= item_idx < len(line_items):
                    item = line_items[item_idx]
                    item_cost = item.get("total_cost", 0.0)
                    item_division = item.get("division", "Unknown")
                    total_cost += item_cost

                    # Update division breakdown
                    division_breakdown[item_division] = (
                        division_breakdown.get(item_division, 0.0) + item_cost
                    )

                    # Collect for top items
                    top_items_data.append(
                        {
                            "line_item_index": item_idx,
                            "title": item.get("title", ""),
                            "division": item_division,
                            "total_cost": item_cost,
                            "evidence_refs": item.get("evidence_refs", []),
                        }
                    )

            # Sort by cost and take top 5
            top_items_data.sort(key=lambda x: x["total_cost"], reverse=True)
            top_items = top_items_data[:5]

            # Compute contribution percentages
            top_line_items: list[TopLineItem] = []
            for item_data in top_items:
                contribution_percent = (
                    (item_data["total_cost"] / total_cost * 100.0)
                    if total_cost > 0
                    else 0.0
                )
                # Normalize evidence_refs to ensure evidence_snippet exists
                normalized_evidence_refs = []
                for ref in item_data.get("evidence_refs", []):
                    if isinstance(ref, dict):
                        # Ensure evidence_snippet exists (required by EvidenceReference)
                        if "evidence_snippet" not in ref:
                            ref["evidence_snippet"] = ref.get("evidence", "") or f"Page {ref.get('page_number', '?')}"
                        normalized_evidence_refs.append(ref)
                    else:
                        normalized_evidence_refs.append(ref)
                
                top_line_items.append(
                    TopLineItem(
                        line_item_index=item_data["line_item_index"],
                        title=item_data["title"],
                        division=item_data["division"],
                        total_cost=item_data["total_cost"],
                        contribution_percent=contribution_percent,
                        evidence_refs=normalized_evidence_refs,
                    )
                )

            zone_cost_items.append(
                ZoneCostItem(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    zone_type=zone_type,
                    total_cost=total_cost,
                    division_breakdown=division_breakdown,
                    top_line_items=top_line_items,
                    linked_line_item_ids=linked_item_indices,
                    attribution_method=attribution_method,
                )
            )

        # Compute min/max for heatmap normalization
        costs = [z.total_cost for z in zone_cost_items if z.total_cost > 0]
        max_cost = max(costs) if costs else 0.0
        min_cost = min(costs) if costs else 0.0

        zone_cost_map = ZoneCostMap(
            project_id=project_id,
            generated_at=datetime.utcnow().isoformat(),
            zones=zone_cost_items,
            max_cost=max_cost,
            min_cost=min_cost,
        )

        log_ctx.info(
            f"Zone cost map generated: {len(zone_cost_items)} zones, "
            f"max_cost=${max_cost:.2f}, min_cost=${min_cost:.2f}"
        )

        return zone_cost_map

    def _keyword_match_zone_to_items(
        self, zone_name: str, line_items: list[dict[str, Any]]
    ) -> list[int]:
        """
        Match zone to line items using keyword matching.

        Args:
            zone_name: Zone name (e.g., "parapet_band", "lintel_band")
            line_items: List of bid line items

        Returns:
            List of line item indices that match
        """
        # Tokenize zone name (split on underscore, hyphen, space)
        zone_tokens = set(
            self._tokenize(zone_name.lower())
        )  # Convert to lowercase and tokenize

        if not zone_tokens:
            return []

        matched_indices: list[int] = []

        for idx, item in enumerate(line_items):
            item_title = item.get("title", "").lower()
            item_tokens = set(self._tokenize(item_title))

            # Check if there's significant overlap
            # Require at least 2 matching tokens (to avoid false positives)
            overlap = zone_tokens.intersection(item_tokens)
            if len(overlap) >= 2:
                matched_indices.append(idx)

        return matched_indices

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text, removing stopwords.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens (non-stopwords)
        """
        # First split on underscores, hyphens, and spaces
        # Then extract word tokens from each part
        parts = re.split(r"[_\-\s]+", text.lower())
        tokens = []
        for part in parts:
            # Extract word tokens from each part
            word_tokens = re.findall(r"\b\w+\b", part)
            tokens.extend(word_tokens)
        # Remove stopwords and short tokens
        tokens = [t for t in tokens if t not in self.STOPWORDS and len(t) > 1]
        return tokens

