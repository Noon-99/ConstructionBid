"""Detail extractor for construction details (Phase 7.4).

Extracts explicit construction details from detail sheets and callouts.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.detail_graph import DetailGraph, DetailNode
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.page_index import PageIndex
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError


class DetailExtractor:
    """Extracts construction details from construction documents."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize detail extractor."""
        self.settings = settings
        self.openai_client = openai_client

    def extract(
        self,
        pdf_images: list[PdfPageImage],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        project_id: str,
    ) -> DetailGraph:
        """
        Extract construction details from documents.

        Args:
            pdf_images: All PDF page images
            analysis: DocumentAnalysis from Stage 1
            page_index: PageIndex from Stage 0.5
            project_id: Project ID for logging

        Returns:
            DetailGraph with extracted detail nodes
        """
        log_ctx = logger.bind(project_id=project_id, stage="detail_extraction")
        log_ctx.info("Starting detail extraction (Phase 7.4)")

        # Select pages with detail indicators
        selected_pages = self._select_detail_pages(analysis, page_index, pdf_images)

        if not selected_pages:
            log_ctx.warning("No pages selected for detail extraction")
            return DetailGraph(
                details=[],
                missing_fields=["details"],
                confidence=0.0,
            )

        log_ctx.info(f"Extracting details from {len(selected_pages)} pages: {[p.page_number for p in selected_pages]}")

        # Extract details from selected pages
        all_details: list[DetailNode] = []

        primary_trade = getattr(analysis, "primary_trade", None)

        for page_image in selected_pages[:8]:  # Max 8 pages (detail sheets can be many)
            try:
                page_result = self._extract_details_from_page(
                    page_image,
                    project_id,
                    primary_trade=primary_trade,
                )
                if page_result.get("details"):
                    for detail_dict in page_result["details"]:
                        try:
                            detail = DetailNode.model_validate(detail_dict)
                            all_details.append(detail)
                        except ValidationError as e:
                            log_ctx.warning(f"Invalid detail: {e}")
                            continue
            except Exception as e:
                log_ctx.error(f"Failed to extract from page {page_image.page_number}: {e}")
                continue

        # Deduplicate details by detail_id or sheet_id + detail_label
        all_details = self._deduplicate_details(all_details)

        # Build missing_fields
        missing_fields: list[str] = []
        if not all_details:
            missing_fields.append("details")

        # Calculate confidence
        confidence = 0.8 if all_details else 0.0
        if len(all_details) < 3:
            confidence *= 0.7

        log_ctx.info(
            f"Details extracted: {len(all_details)} detail nodes, confidence={confidence:.2f}"
        )

        return DetailGraph(
            details=all_details,
            missing_fields=missing_fields,
            confidence=confidence,
        )

    def _select_detail_pages(
        self,
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
    ) -> list[PdfPageImage]:
        """Select pages containing detail information."""
        selected: set[int] = set()

        # Use page_index if available
        if page_index and hasattr(page_index, "pages"):
            for page_item in page_index.pages:
                # Bias toward detail indicators
                relevant_indicators = [
                    "detail",
                    "section",
                    "parapet",
                    "wall",
                    "window",
                    "roof",
                    "foundation",
                    "bond",
                    "prevailing_wage",
                    "compliance",
                    "spec_section",
                ]
                if any(ind in page_item.indicators for ind in relevant_indicators):
                    if page_item.confidence >= 0.6:
                        selected.add(page_item.page_number - 1)

                # Bias toward detail, section, structural page types
                relevant_types = [
                    "detail",
                    "section",
                    "structural",
                    "plan",
                    "schedule",
                    "notes",
                    "compliance",
                ]
                if any(pt in page_item.page_types for pt in relevant_types):
                    selected.add(page_item.page_number - 1)

        # Use Stage 1 locators
        for locator in analysis.where_materials_live:
            if locator.location_type in ["detail_callouts", "specification_section"]:
                if locator.page_number > 0:
                    selected.add(locator.page_number - 1)

        # Pull in procurement compliance pages
        procurement_context = getattr(analysis, "procurement_context", None)
        if procurement_context and getattr(procurement_context, "source_pages", None):
            for page_number in procurement_context.source_pages:
                if isinstance(page_number, int) and page_number > 0:
                    selected.add(page_number - 1)

        # Filter to available pages
        selected_pages = [
            pdf_images[i] for i in sorted(selected) if 0 <= i < len(pdf_images)
        ]

        return selected_pages

    def _extract_details_from_page(
        self,
        page_image: PdfPageImage,
        project_id: str,
        primary_trade: str | None = None,
    ) -> dict:
        """Extract details from a single page."""
        prompt = self._create_extraction_prompt(primary_trade)

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
            project_id=project_id, stage="detail_extraction", page=page_image.page_number
        )

        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-detail-page-{page_image.page_number}",
                stage_name="detail_extraction",
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
            return {"details": []}
        except OpenAINonRetryableError as e:
            log_ctx.error(f"OpenAI error: {e}")
            return {"details": []}

    def _create_extraction_prompt(self, primary_trade: str | None) -> str:
        """Create prompt for detail extraction."""
        trade_hint = ""
        if primary_trade:
            trade_hint = f"This project is primarily {primary_trade}. Adjust your focus accordingly by capturing detail types relevant to this trade family as well as adjacent trades (MEP, site, compliance).\n\n"

        return f"""You are extracting construction details from construction drawings.

Use intelligent pattern recognition to identify details, even if they don't have explicit detail labels. Look for visual patterns, typical construction details, and contextual clues.

Return ONLY valid JSON matching this exact schema:

{{
  "details": [
    {{
      "detail_id": "DET-001" or "S-011-D4" or null,
      "detail_type": "parapet" | "wall_section" | "window" | "lintel" | "roof" | "roof_edge" | "foundation" | "footing" | "flashing" | "coping" | "masonry" | "other",
      "sheet_id": "S-011" or null,
      "detail_label": "Detail 4" or "Typical Parapet Detail" or null,
      "applies_to": ["zone_parapet_001", "WIN-1"] or [],
      "materials_referenced": ["8\" CMU", "Steel lintel L3x3x1/4"] or [],
      "dimensions_referenced": ["12\" parapet height", "6\" flashing"] or [],
      "compliance_references": ["prevailing wage note", "payment bond requirement"] or [],
      "notes": "Special requirements or notes" or null,
      "page_number": 12,
      "evidence_snippet": "Exact text from drawing showing this detail",
      "confidence": 0.75
    }}
  ]
}}

{trade_hint}Instructions:
1. **Intelligent Detail Recognition**: Extract details using pattern recognition:
   - **Parapets**: Look for masonry walls extending above roof line, coping caps, parapet details, wall sections showing roof-to-wall transitions
   - **Masonry Work**: Look for brick repair, repointing, lintel details, wall sections, masonry details
   - **Flashing**: Look for base flashing, step flashing, counterflashing, roof edge details, penetration flashing
   - **Roof Details**: Look for roof edge details, roof-to-wall transitions, penetration details, roof drain details
   - **Windows/Openings**: Look for window details, opening details, head/sill/jamb details, storefront details
   - **Foundation**: Look for footing details, foundation wall sections, grade beam details

2. **Detail Identification**: 
   - If explicit detail labels exist (e.g., "S-011 Detail 4"), use them
   - If no explicit label but detail is clearly visible, create a descriptive label (e.g., "Typical Parapet Detail", "Roof Edge Detail")
   - Use null for detail_id and detail_label if not explicitly labeled, but still extract the detail if clearly visible

3. **Pattern Recognition**: Recognize typical construction details:
   - Parapet details: masonry wall above roof, coping, flashing at parapet base
   - Roof edge details: edge metal, gravel stop, fascia details
   - Flashing details: base flashing, step flashing, counterflashing patterns
   - Masonry details: brick coursing, repointing, lintel installation

4. Extract materials referenced in detail (CMU, steel, flashing, reinforcing, piping, conduit, etc.)

5. Extract dimensions referenced (heights, widths, thicknesses) exactly as shown

6. Capture compliance references (prevailing wage schedules, bond/insurance notes, inspection requirements) when present

7. Link to applies_to elements if referenced (zone IDs, opening IDs, structural element IDs)

8. Include notes if present

9. Provide an evidence snippet for each detail describing what you see (e.g., "Parapet detail showing 12\" CMU wall with coping cap and base flashing")

10. Estimate confidence (0.0-1.0):
    - 0.9-1.0: Explicit detail label with clear drawing
    - 0.7-0.9: Clear detail visible, typical construction pattern recognized
    - 0.5-0.7: Detail partially visible, some inference required
    - <0.5: Unclear or ambiguous

11. **CRITICAL**: Only include details you can clearly see in the drawing. Do not invent details, but do recognize typical construction patterns when clearly visible.

CRITICAL: Return ONLY the JSON object. No markdown, no code blocks, no explanation."""

    def _deduplicate_details(
        self, details: list[DetailNode]
    ) -> list[DetailNode]:
        """Deduplicate details by detail_id or sheet_id + detail_label."""
        seen: dict[str, DetailNode] = {}

        for detail in details:
            # Use detail_id if available, otherwise sheet_id + detail_label
            key = detail.detail_id or f"{detail.sheet_id}_{detail.detail_label}"
            if key not in seen:
                seen[key] = detail
            else:
                # Keep detail with better evidence
                existing = seen[key]
                if len(detail.evidence_snippet) > len(existing.evidence_snippet):
                    seen[key] = detail
                # Merge applies_to lists
                existing_applies_to = set(existing.applies_to)
                new_applies_to = set(detail.applies_to)
                existing.applies_to = list(existing_applies_to.union(new_applies_to))

        return list(seen.values())




