"""Openings extractor for windows and doors (Phase 7.3).

Extracts openings from schedules, elevations, and detail callouts.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.openings import OpeningDetail, OpeningsResult
from app.schemas.page_index import PageIndex
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError


class OpeningsExtractor:
    """Extracts openings (windows/doors) from construction documents."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize openings extractor."""
        self.settings = settings
        self.openai_client = openai_client

    def extract(
        self,
        pdf_images: list[PdfPageImage],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        project_id: str,
    ) -> OpeningsResult:
        """
        Extract openings from documents.

        Args:
            pdf_images: All PDF page images
            analysis: DocumentAnalysis from Stage 1
            page_index: PageIndex from Stage 0.5
            project_id: Project ID for logging

        Returns:
            OpeningsResult with extracted openings
        """
        log_ctx = logger.bind(project_id=project_id, stage="openings_extraction")
        log_ctx.info("Starting openings extraction (Phase 7.3)")

        # Select pages with openings indicators
        selected_pages = self._select_openings_pages(analysis, page_index, pdf_images)

        if not selected_pages:
            log_ctx.warning("No pages selected for openings extraction")
            return OpeningsResult(
                openings=[],
                missing_fields=["openings"],
                confidence=0.0,
            )

        log_ctx.info(f"Extracting openings from {len(selected_pages)} pages: {[p.page_number for p in selected_pages]}")

        # Extract openings from selected pages
        all_openings: list[OpeningDetail] = []

        for page_image in selected_pages[:6]:  # Max 6 pages (schedules can be long)
            try:
                page_result = self._extract_openings_from_page(page_image, project_id)
                if page_result.get("openings"):
                    for opening_dict in page_result["openings"]:
                        try:
                            opening = OpeningDetail.model_validate(opening_dict)
                            all_openings.append(opening)
                        except ValidationError as e:
                            log_ctx.warning(f"Invalid opening: {e}")
                            continue
            except Exception as e:
                log_ctx.error(f"Failed to extract from page {page_image.page_number}: {e}")
                continue

        # Deduplicate openings by opening_id
        all_openings = self._deduplicate_openings(all_openings)

        # Build missing_fields
        missing_fields: list[str] = []
        if not all_openings:
            missing_fields.append("openings")

        # Calculate confidence
        confidence = 0.8 if all_openings else 0.0
        schedule_count = sum(1 for o in all_openings if o.source == "schedule")
        if schedule_count > 0:
            confidence = 0.9  # Higher confidence if from schedule
        elif len(all_openings) < 3:
            confidence *= 0.7

        log_ctx.info(
            f"Openings extracted: {len(all_openings)} openings, "
            f"{schedule_count} from schedules, confidence={confidence:.2f}"
        )

        return OpeningsResult(
            openings=all_openings,
            missing_fields=missing_fields,
            confidence=confidence,
        )

    def _select_openings_pages(
        self,
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
    ) -> list[PdfPageImage]:
        """Select pages containing openings information."""
        selected: set[int] = set()

        # Use page_index if available
        if page_index and hasattr(page_index, "pages"):
            for page_item in page_index.pages:
                # Bias toward openings indicators
                relevant_indicators = [
                    "window",
                    "door",
                    "opening",
                    "schedule",
                    "elevation",
                    "detail",
                ]
                if any(ind in page_item.indicators for ind in relevant_indicators):
                    if page_item.confidence >= 0.6:
                        selected.add(page_item.page_number - 1)

                # Bias toward schedule, elevation, detail page types
                relevant_types = ["schedule", "elevation", "detail", "plan"]
                if any(pt in page_item.page_types for pt in relevant_types):
                    selected.add(page_item.page_number - 1)

        # Use Stage 1 locators
        for locator in analysis.where_scope_lives:
            if locator.location_type in ["window_schedule", "door_schedule", "elevation_notes"]:
                if locator.page_number > 0:
                    selected.add(locator.page_number - 1)

        # Filter to available pages
        selected_pages = [
            pdf_images[i] for i in sorted(selected) if 0 <= i < len(pdf_images)
        ]

        return selected_pages

    def _extract_openings_from_page(
        self, page_image: PdfPageImage, project_id: str
    ) -> dict:
        """Extract openings from a single page."""
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
            project_id=project_id, stage="openings_extraction", page=page_image.page_number
        )

        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-openings-page-{page_image.page_number}",
                stage_name="openings_extraction",
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
            return {"openings": []}
        except OpenAINonRetryableError as e:
            log_ctx.error(f"OpenAI error: {e}")
            return {"openings": []}

    def _create_extraction_prompt(self) -> str:
        """Create prompt for openings extraction."""
        return """You are extracting openings (windows and doors) from construction drawings.

Extract ONLY openings that are explicitly shown in schedules, elevations, or detail callouts. Do NOT guess or infer.

Return ONLY valid JSON matching this exact schema:

{
  "openings": [
    {
      "opening_id": "WIN-1" or "D-101",
      "opening_type": "window" | "door" | "opening",
      "level": "1st Floor" or null,
      "count": 10 or null,
      "width_ft": 3.0 or null,
      "height_ft": 6.67 or null,
      "size": "3-0 x 6-8" or null,
      "material": "aluminum" or null,
      "associated_lintel_id": "L-1" or null,
      "flashing_required": true or false,
      "source": "schedule" | "elevation" | "detail" | "unknown",
      "page_number": 5,
      "sheet_id": "A-5" or null,
      "detail_reference": "D-2 Detail 3" or null,
      "evidence_snippet": "Exact text from drawing showing this opening"
    }
  ]
}

Instructions:
1. Extract from window/door schedules if present
2. Extract from elevations if openings are labeled
3. Extract from detail callouts (e.g., "Typical Window Detail")
4. Include opening_id if shown (e.g., "WIN-1", "D-101")
5. Include level/floor if stated
6. Include count if shown in schedule
7. Include width/height or size if stated
8. Include material if specified
9. Link to associated lintel_id if shown
10. Mark flashing_required if explicitly stated
11. Set source: "schedule" if from schedule, "elevation" if from elevation, "detail" if from detail callout
12. Provide evidence snippet for each opening
13. Only include openings with clear evidence

CRITICAL: Return ONLY the JSON object. No markdown, no code blocks, no explanation."""

    def _deduplicate_openings(
        self, openings: list[OpeningDetail]
    ) -> list[OpeningDetail]:
        """Deduplicate openings by opening_id."""
        seen: dict[str, OpeningDetail] = {}

        for opening in openings:
            key = opening.opening_id
            if key not in seen:
                seen[key] = opening
            else:
                # Keep opening with better evidence (prefer schedule source)
                existing = seen[key]
                if opening.source == "schedule" and existing.source != "schedule":
                    seen[key] = opening
                elif len(opening.evidence_snippet) > len(existing.evidence_snippet):
                    seen[key] = opening

        return list(seen.values())






