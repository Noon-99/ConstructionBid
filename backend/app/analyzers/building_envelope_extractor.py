"""Building envelope extractor for institutional projects (Phase 7.2).

Extracts exterior walls, roof systems, flashing, and openings from drawings.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.building_envelope import (
    BuildingEnvelopeResult,
    EnvelopeWall,
    FlashingSystem,
    Opening,
    RoofSystem,
)
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.page_index import PageIndex
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError


class BuildingEnvelopeExtractor:
    """Extracts building envelope elements from construction documents."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize building envelope extractor."""
        self.settings = settings
        self.openai_client = openai_client

    def extract(
        self,
        pdf_images: list[PdfPageImage],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        project_id: str,
    ) -> BuildingEnvelopeResult:
        """
        Extract building envelope elements from documents.

        Args:
            pdf_images: All PDF page images
            analysis: DocumentAnalysis from Stage 1
            page_index: PageIndex from Stage 0.5
            project_id: Project ID for logging

        Returns:
            BuildingEnvelopeResult with extracted elements
        """
        log_ctx = logger.bind(project_id=project_id, stage="building_envelope_extraction")
        log_ctx.info("Starting building envelope extraction (Phase 7.2)")

        # Select pages with envelope indicators
        selected_pages = self._select_envelope_pages(analysis, page_index, pdf_images)

        if not selected_pages:
            log_ctx.warning("No pages selected for envelope extraction")
            return BuildingEnvelopeResult(
                walls=[],
                roof_systems=[],
                flashing_systems=[],
                openings=[],
                missing_fields=["walls", "roof", "flashing", "openings"],
                confidence=0.0,
            )

        log_ctx.info(f"Extracting envelope elements from {len(selected_pages)} pages: {[p.page_number for p in selected_pages]}")

        # Extract elements from selected pages
        all_walls: list[EnvelopeWall] = []
        all_roofs: list[RoofSystem] = []
        all_flashing: list[FlashingSystem] = []
        all_openings: list[Opening] = []

        for page_image in selected_pages[:5]:  # Max 5 pages
            try:
                page_result = self._extract_envelope_from_page(page_image, project_id)
                
                # Parse walls
                for wall_dict in page_result.get("walls", []):
                    try:
                        wall = EnvelopeWall.model_validate(wall_dict)
                        all_walls.append(wall)
                    except ValidationError as e:
                        log_ctx.warning(f"Invalid wall: {e}")
                        continue
                
                # Parse roofs
                for roof_dict in page_result.get("roof_systems", []):
                    try:
                        roof = RoofSystem.model_validate(roof_dict)
                        all_roofs.append(roof)
                    except ValidationError as e:
                        log_ctx.warning(f"Invalid roof: {e}")
                        continue
                
                # Parse flashing
                for flash_dict in page_result.get("flashing_systems", []):
                    try:
                        flashing = FlashingSystem.model_validate(flash_dict)
                        all_flashing.append(flashing)
                    except ValidationError as e:
                        log_ctx.warning(f"Invalid flashing: {e}")
                        continue
                
                # Parse openings
                for opening_dict in page_result.get("openings", []):
                    try:
                        opening = Opening.model_validate(opening_dict)
                        all_openings.append(opening)
                    except ValidationError as e:
                        log_ctx.warning(f"Invalid opening: {e}")
                        continue
                        
            except Exception as e:
                log_ctx.error(f"Failed to extract from page {page_image.page_number}: {e}")
                continue

        # Deduplicate
        all_walls = self._deduplicate_walls(all_walls)
        all_roofs = self._deduplicate_roofs(all_roofs)
        all_flashing = self._deduplicate_flashing(all_flashing)
        all_openings = self._deduplicate_openings(all_openings)

        # Build missing_fields
        missing_fields: list[str] = []
        if not all_walls:
            missing_fields.append("walls")
        if not all_roofs:
            missing_fields.append("roof_systems")
        if not all_flashing:
            missing_fields.append("flashing_systems")
        if not all_openings:
            missing_fields.append("openings")

        # Calculate confidence
        confidence = 0.8 if (all_walls or all_roofs) else 0.0
        if len(all_walls) + len(all_roofs) < 2:
            confidence *= 0.7

        log_ctx.info(
            f"Envelope extracted: {len(all_walls)} walls, {len(all_roofs)} roofs, "
            f"{len(all_flashing)} flashing, {len(all_openings)} openings, confidence={confidence:.2f}"
        )

        return BuildingEnvelopeResult(
            walls=all_walls,
            roof_systems=all_roofs,
            flashing_systems=all_flashing,
            openings=all_openings,
            missing_fields=missing_fields,
            confidence=confidence,
        )

    def _select_envelope_pages(
        self,
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
    ) -> list[PdfPageImage]:
        """Select pages containing envelope information."""
        selected: set[int] = set()

        # Use page_index if available
        if page_index and hasattr(page_index, "pages"):
            for page_item in page_index.pages:
                # Bias toward envelope indicators
                relevant_indicators = [
                    "dimensions",
                    "elevation",
                    "roof",
                    "parapet",
                    "flashing",
                    "window",
                    "door",
                ]
                if any(ind in page_item.indicators for ind in relevant_indicators):
                    if page_item.confidence >= 0.6:
                        selected.add(page_item.page_number - 1)

                # Bias toward elevation, plan, detail page types
                relevant_types = ["elevation", "plan", "detail", "section"]
                if any(pt in page_item.page_types for pt in relevant_types):
                    selected.add(page_item.page_number - 1)

        # Use Stage 1 locators
        for locator in analysis.where_scope_lives:
            if locator.location_type in ["elevation_notes", "detail_callouts"]:
                if locator.page_number > 0:
                    selected.add(locator.page_number - 1)

        # Filter to available pages
        selected_pages = [
            pdf_images[i] for i in sorted(selected) if 0 <= i < len(pdf_images)
        ]

        return selected_pages

    def _extract_envelope_from_page(
        self, page_image: PdfPageImage, project_id: str
    ) -> dict:
        """Extract envelope elements from a single page."""
        prompt = self._create_extraction_prompt()

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{page_image.mime_type};base64,{page_image.image_base64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ]

        log_ctx = logger.bind(
            project_id=project_id, stage="envelope_extraction", page=page_image.page_number
        )

        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-envelope-page-{page_image.page_number}",
                stage_name="building_envelope_extraction",
                project_id=project_id,
            )

            # Parse JSON
            content = response_text.strip()
            if content.startswith("```json"):
                content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
            elif content.startswith("```"):
                content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]

            parsed = json.loads(content)
            return parsed

        except json.JSONDecodeError as e:
            log_ctx.error(f"Failed to parse JSON response: {e}")
            return {"walls": [], "roof_systems": [], "flashing_systems": [], "openings": []}
        except OpenAINonRetryableError as e:
            log_ctx.error(f"OpenAI error: {e}")
            return {"walls": [], "roof_systems": [], "flashing_systems": [], "openings": []}

    def _create_extraction_prompt(self) -> str:
        """Create prompt for building envelope extraction."""
        return """You are extracting building envelope elements from construction drawings.

Extract ONLY elements that are explicitly shown or specified. Do NOT guess or infer.

Return ONLY valid JSON matching this exact schema:

{
  "walls": [
    {
      "wall_id": "W-1" or null,
      "wall_type": "brick_veneer" | "cmu_backup" | "eifs" | "concrete" | "metal_panel",
      "area_sf": 500.0 or null,
      "height_ft": 30.0 or null,
      "length_ft": 50.0 or null,
      "material_spec": "8\\" CMU" or null,
      "location": "North elevation" or null,
      "page_number": 2,
      "sheet_id": "A-2" or null,
      "evidence_snippet": "Exact text from drawing"
    }
  ],
  "roof_systems": [
    {
      "roof_id": "R-1" or null,
      "deck_type": "concrete" | "steel" | "wood" | "composite" or null,
      "insulation_type": "R-30 rigid" or null,
      "membrane_type": "epdm" | "tpo" | "pvc" | "modified_bitumen" | "built_up" or null,
      "area_sf": 2000.0 or null,
      "parapet_height_ft": 2.0 or null,
      "page_number": 3,
      "sheet_id": "A-3" or null,
      "evidence_snippet": "Exact text from drawing"
    }
  ],
  "flashing_systems": [
    {
      "flashing_id": "FL-1" or null,
      "flashing_type": "lintel_flashing" | "coping" | "drip_edge" | "base_flashing" | "counter_flashing" | "through_wall",
      "length_lf": 100.0 or null,
      "material": "Copper" or null,
      "location": "Parapet coping" or null,
      "page_number": 3,
      "sheet_id": "A-3" or null,
      "detail_reference": "D-2 Detail 4" or null,
      "evidence_snippet": "Exact text from drawing"
    }
  ],
  "openings": [
    {
      "opening_id": "WIN-1" or null,
      "opening_type": "window" | "door" | "opening",
      "count": 10 or null,
      "type_description": "Double-hung window" or null,
      "size": "3-0 x 6-8" or null,
      "location": "North elevation" or null,
      "page_number": 2,
      "sheet_id": "A-2" or null,
      "evidence_snippet": "Exact text from drawing"
    }
  ]
}

Instructions:
1. Extract exterior walls only if explicitly specified (brick veneer, CMU backup, EIFS, etc.)
2. Extract roof systems (deck, insulation, membrane, parapet) only if shown
3. Extract flashing systems (lintel flashing, coping, drip edge) only if specified
4. Extract openings at count + type level (no guessing dimensions)
5. Include evidence snippet for each element
6. Only include elements with clear evidence

CRITICAL: Return ONLY the JSON object. No markdown, no code blocks, no explanation."""

    def _deduplicate_walls(self, walls: list[EnvelopeWall]) -> list[EnvelopeWall]:
        """Deduplicate walls by wall_id or location."""
        seen: dict[str, EnvelopeWall] = {}
        for wall in walls:
            key = wall.wall_id or f"{wall.wall_type}_{wall.location}"
            if key not in seen:
                seen[key] = wall
        return list(seen.values())

    def _deduplicate_roofs(self, roofs: list[RoofSystem]) -> list[RoofSystem]:
        """Deduplicate roofs by roof_id."""
        seen: dict[str, RoofSystem] = {}
        for roof in roofs:
            key = roof.roof_id or "roof_1"
            if key not in seen:
                seen[key] = roof
        return list(seen.values())

    def _deduplicate_flashing(self, flashing: list[FlashingSystem]) -> list[FlashingSystem]:
        """Deduplicate flashing by flashing_id or location."""
        seen: dict[str, FlashingSystem] = {}
        for flash in flashing:
            key = flash.flashing_id or f"{flash.flashing_type}_{flash.location}"
            if key not in seen:
                seen[key] = flash
        return list(seen.values())

    def _deduplicate_openings(self, openings: list[Opening]) -> list[Opening]:
        """Deduplicate openings by opening_id or location+type."""
        seen: dict[str, Opening] = {}
        for opening in openings:
            key = opening.opening_id or f"{opening.opening_type}_{opening.location}"
            if key not in seen:
                seen[key] = opening
        return list(seen.values())






