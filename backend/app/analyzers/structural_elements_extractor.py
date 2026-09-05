"""Structural elements extractor for institutional projects (Phase 7.2).

Extracts foundations, structural steel, CMU walls, and shoring from structural drawings.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.page_index import PageIndex
from app.schemas.structural_elements import (
    MaterialSpecification,
    StructuralElement,
    StructuralElementDimensions,
    StructuralElementsResult,
)
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError


class StructuralElementsExtractor:
    """Extracts structural elements from construction documents."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize structural elements extractor."""
        self.settings = settings
        self.openai_client = openai_client

    def extract(
        self,
        pdf_images: list[PdfPageImage],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        project_id: str,
    ) -> StructuralElementsResult:
        """
        Extract structural elements from documents.

        Args:
            pdf_images: All PDF page images
            analysis: DocumentAnalysis from Stage 1
            page_index: PageIndex from Stage 0.5
            project_id: Project ID for logging

        Returns:
            StructuralElementsResult with extracted elements
        """
        log_ctx = logger.bind(project_id=project_id, stage="structural_elements_extraction")
        log_ctx.info("Starting structural elements extraction (Phase 7.2)")

        # Select pages with structural indicators
        selected_pages = self._select_structural_pages(analysis, page_index, pdf_images)

        if not selected_pages:
            log_ctx.warning("No pages selected for structural extraction")
            return StructuralElementsResult(
                elements=[],
                missing_fields=["elements"],
                confidence=0.0,
            )

        log_ctx.info(f"Extracting structural elements from {len(selected_pages)} pages: {[p.page_number for p in selected_pages]}")

        # Extract elements from selected pages
        all_elements: list[StructuralElement] = []

        for page_image in selected_pages[:5]:  # Max 5 pages
            try:
                page_result = self._extract_elements_from_page(page_image, project_id)
                if page_result.get("elements"):
                    for elem_dict in page_result["elements"]:
                        try:
                            element = StructuralElement.model_validate(elem_dict)
                            all_elements.append(element)
                        except ValidationError as e:
                            log_ctx.warning(f"Invalid structural element: {e}")
                            continue
            except Exception as e:
                log_ctx.error(f"Failed to extract from page {page_image.page_number}: {e}")
                continue

        # Deduplicate elements by element_id or location
        all_elements = self._deduplicate_elements(all_elements)

        # Build missing_fields
        missing_fields: list[str] = []
        if not all_elements:
            missing_fields.append("elements")

        # Calculate confidence
        confidence = 0.8 if all_elements else 0.0
        if len(all_elements) < 3:
            confidence *= 0.7

        log_ctx.info(
            f"Structural elements extracted: {len(all_elements)} elements, confidence={confidence:.2f}"
        )

        return StructuralElementsResult(
            elements=all_elements,
            missing_fields=missing_fields,
            confidence=confidence,
        )

    def _select_structural_pages(
        self,
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
    ) -> list[PdfPageImage]:
        """Select pages containing structural information."""
        selected: set[int] = set()

        # Use page_index if available
        if page_index and hasattr(page_index, "pages"):
            for page_item in page_index.pages:
                # Bias toward structural indicators
                relevant_indicators = [
                    "structural_notes",
                    "foundation",
                    "steel",
                    "cmu",
                    "loads",
                    "detail",
                ]
                if any(ind in page_item.indicators for ind in relevant_indicators):
                    if page_item.confidence >= 0.6:
                        selected.add(page_item.page_number - 1)

                # Bias toward detail, plan, section page types
                relevant_types = ["detail", "plan", "section", "notes"]
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

    def _extract_elements_from_page(
        self, page_image: PdfPageImage, project_id: str
    ) -> dict:
        """Extract structural elements from a single page."""
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
            project_id=project_id, stage="structural_extraction", page=page_image.page_number
        )

        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-structural-page-{page_image.page_number}",
                stage_name="structural_elements_extraction",
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
            return {"elements": []}
        except OpenAINonRetryableError as e:
            log_ctx.error(f"OpenAI error: {e}")
            return {"elements": []}

    def _create_extraction_prompt(self) -> str:
        """Create prompt for structural elements extraction."""
        return """You are extracting structural elements from construction drawings.

Extract ONLY elements that are explicitly shown or specified. Do NOT guess or infer.

Return ONLY valid JSON matching this exact schema:

{
  "elements": [
    {
      "element_type": "footing" | "slab" | "bearing_wall" | "column" | "beam" | "lintel" | "cmu_wall" | "shoring",
      "element_id": "F-1" or null,
      "dimensions": {
        "width_ft": 2.0 or null,
        "depth_ft": 2.0 or null,
        "height_ft": 8.0 or null,
        "length_ft": 20.0 or null,
        "section": "W12x26" or null,
        "diameter_in": 6.0 or null,
        "thickness_in": 8.0 or null
      },
      "material_spec": {
        "astm": "ASTM A36" or null,
        "psi": 3000 or null,
        "grade": "Grade 60" or null,
        "unit_strength": 2000 or null
      },
      "quantity": 10.0 or null,
      "unit": "LF" | "EA" | "SF" | "CY" or null,
      "location": "North wall" or null,
      "page_number": 3,
      "sheet_id": "S-2" or null,
      "detail_reference": "S-2 Detail 3" or null,
      "evidence_snippet": "Exact text from drawing showing this element"
    }
  ]
}

Instructions:
1. Extract foundations (footings, slabs) with dimensions and material specs
2. Extract structural steel (columns, beams, lintels) with section designations
3. Extract load-bearing CMU walls with thickness and material specs
4. Extract temporary shoring only if explicitly stated
5. Include element IDs if shown (e.g., "F-1", "C-2")
6. Include detail references if called out
7. Provide evidence snippet for each element
8. Only include elements with clear evidence

CRITICAL: Return ONLY the JSON object. No markdown, no code blocks, no explanation."""

    def _deduplicate_elements(
        self, elements: list[StructuralElement]
    ) -> list[StructuralElement]:
        """Deduplicate structural elements by element_id or location."""
        seen: dict[str, StructuralElement] = {}

        for element in elements:
            key = element.element_id or f"{element.element_type}_{element.location}"
            if key not in seen:
                seen[key] = element
            else:
                # Keep element with better evidence
                existing = seen[key]
                if len(element.evidence_snippet) > len(existing.evidence_snippet):
                    seen[key] = element

        return list(seen.values())






