"""Lintels extractor for headers and lintels (Phase 7.3).

Extracts lintels from schedules, detail callouts, and structural drawings.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.lintels import LintelDetail, LintelsResult
from app.schemas.page_index import PageIndex
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError


class LintelsExtractor:
    """Extracts lintels and headers from construction documents."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize lintels extractor."""
        self.settings = settings
        self.openai_client = openai_client

    def extract(
        self,
        pdf_images: list[PdfPageImage],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        project_id: str,
    ) -> LintelsResult:
        """
        Extract lintels from documents.

        Args:
            pdf_images: All PDF page images
            analysis: DocumentAnalysis from Stage 1
            page_index: PageIndex from Stage 0.5
            project_id: Project ID for logging

        Returns:
            LintelsResult with extracted lintels
        """
        log_ctx = logger.bind(project_id=project_id, stage="lintels_extraction")
        log_ctx.info("Starting lintels extraction (Phase 7.3)")

        # Select pages with lintel indicators
        selected_pages = self._select_lintel_pages(analysis, page_index, pdf_images)

        if not selected_pages:
            log_ctx.warning("No pages selected for lintels extraction")
            return LintelsResult(
                lintels=[],
                missing_fields=["lintels"],
                confidence=0.0,
            )

        log_ctx.info(f"Extracting lintels from {len(selected_pages)} pages: {[p.page_number for p in selected_pages]}")

        # Extract lintels from selected pages
        all_lintels: list[LintelDetail] = []

        for page_image in selected_pages[:5]:  # Max 5 pages
            try:
                page_result = self._extract_lintels_from_page(page_image, project_id)
                if page_result.get("lintels"):
                    for lintel_dict in page_result["lintels"]:
                        try:
                            lintel = LintelDetail.model_validate(lintel_dict)
                            all_lintels.append(lintel)
                        except ValidationError as e:
                            log_ctx.warning(f"Invalid lintel: {e}")
                            continue
            except Exception as e:
                log_ctx.error(f"Failed to extract from page {page_image.page_number}: {e}")
                continue

        # Deduplicate lintels by lintel_id
        all_lintels = self._deduplicate_lintels(all_lintels)

        # Build missing_fields
        missing_fields: list[str] = []
        if not all_lintels:
            missing_fields.append("lintels")

        # Calculate confidence
        confidence = 0.8 if all_lintels else 0.0
        schedule_count = sum(1 for l in all_lintels if l.source == "schedule")
        if schedule_count > 0:
            confidence = 0.9  # Higher confidence if from schedule
        elif len(all_lintels) < 2:
            confidence *= 0.7

        log_ctx.info(
            f"Lintels extracted: {len(all_lintels)} lintels, "
            f"{schedule_count} from schedules, confidence={confidence:.2f}"
        )

        return LintelsResult(
            lintels=all_lintels,
            missing_fields=missing_fields,
            confidence=confidence,
        )

    def _select_lintel_pages(
        self,
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
    ) -> list[PdfPageImage]:
        """Select pages containing lintel information."""
        selected: set[int] = set()

        # Use page_index if available
        if page_index and hasattr(page_index, "pages"):
            for page_item in page_index.pages:
                # Bias toward lintel indicators
                relevant_indicators = [
                    "lintel",
                    "header",
                    "structural",
                    "detail",
                    "schedule",
                ]
                if any(ind in page_item.indicators for ind in relevant_indicators):
                    if page_item.confidence >= 0.6:
                        selected.add(page_item.page_number - 1)

                # Bias toward detail, structural, schedule page types
                relevant_types = ["detail", "structural", "schedule", "section"]
                if any(pt in page_item.page_types for pt in relevant_types):
                    selected.add(page_item.page_number - 1)

        # Use Stage 1 locators
        for locator in analysis.where_materials_live:
            if locator.location_type in ["specification_section", "detail_callouts"]:
                if locator.page_number > 0:
                    selected.add(locator.page_number - 1)

        # Filter to available pages
        selected_pages = [
            pdf_images[i] for i in sorted(selected) if 0 <= i < len(pdf_images)
        ]

        return selected_pages

    def _extract_lintels_from_page(
        self, page_image: PdfPageImage, project_id: str
    ) -> dict:
        """Extract lintels from a single page."""
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
            project_id=project_id, stage="lintels_extraction", page=page_image.page_number
        )

        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-lintels-page-{page_image.page_number}",
                stage_name="lintels_extraction",
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
            return {"lintels": []}
        except OpenAINonRetryableError as e:
            log_ctx.error(f"OpenAI error: {e}")
            return {"lintels": []}

    def _create_extraction_prompt(self) -> str:
        """Create prompt for lintels extraction."""
        return """You are extracting lintels and headers from construction drawings.

Extract ONLY lintels that are explicitly shown in schedules, detail callouts, or structural drawings. Do NOT guess or infer.

Return ONLY valid JSON matching this exact schema:

{
  "lintels": [
    {
      "lintel_id": "L-1" or "LINT-101",
      "lintel_type": "steel_lintel" | "cmu_lintel" | "precast_lintel" | "bond_beam" | "header",
      "section": "L3x3x1/4" or "C8x11.5" or "8x16 CMU" or null,
      "material_spec": "ASTM A36" or "ASTM A992" or "Galvanized" or null,
      "span_ft": 8.0 or null,
      "quantity": 10 or null,
      "associated_openings": ["WIN-1", "WIN-2"] or [],
      "flashing_required": true or false,
      "drip_edge_required": true or false,
      "source": "schedule" | "detail" | "elevation" | "unknown",
      "page_number": 6,
      "sheet_id": "S-2" or null,
      "detail_reference": "S-2 Detail 5" or null,
      "evidence_snippet": "Exact text from drawing showing this lintel"
    }
  ]
}

Instructions:
1. Extract from lintel schedules if present
2. Extract from detail callouts (e.g., "Typical Lintel Detail")
3. Extract from structural drawings if lintels are shown
4. Include lintel_id if shown (e.g., "L-1", "LINT-101")
5. Include section designation if shown (e.g., "L3x3x1/4", "C8x11.5")
6. Include material spec if specified (ASTM, galvanizing, etc.)
7. Include span if stated
8. Include quantity if shown in schedule
9. Link to associated openings if shown
10. Mark flashing_required and drip_edge_required if explicitly stated
11. Set source: "schedule" if from schedule, "detail" if from detail, "elevation" if from elevation
12. Provide evidence snippet for each lintel
13. Only include lintels with clear evidence

CRITICAL: Return ONLY the JSON object. No markdown, no code blocks, no explanation."""

    def _deduplicate_lintels(
        self, lintels: list[LintelDetail]
    ) -> list[LintelDetail]:
        """Deduplicate lintels by lintel_id."""
        seen: dict[str, LintelDetail] = {}

        for lintel in lintels:
            key = lintel.lintel_id
            if key not in seen:
                seen[key] = lintel
            else:
                # Keep lintel with better evidence (prefer schedule source)
                existing = seen[key]
                if lintel.source == "schedule" and existing.source != "schedule":
                    seen[key] = lintel
                elif len(lintel.evidence_snippet) > len(existing.evidence_snippet):
                    seen[key] = lintel

        return list(seen.values())






