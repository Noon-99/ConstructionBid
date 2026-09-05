"""Procurement signal analyzer for Stage 1 document processing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from loguru import logger

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import ProcurementContext
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError


@dataclass
class ProcurementAnalysisResult:
    """Structured result for procurement signal analysis."""

    procurement_context: ProcurementContext
    requires_prevailing_wage: bool | None
    requires_bonds: bool | None
    issuing_authority: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "procurement_context": self.procurement_context.model_dump(),
            "requires_prevailing_wage": self.requires_prevailing_wage,
            "requires_bonds": self.requires_bonds,
            "issuing_authority": self.issuing_authority,
        }


class ProcurementSignalAnalyzer:
    """Detects government/compliance procurement signals without trade lock-in."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        self.settings = settings
        self.openai_client = openai_client

    def analyze(
        self,
        pdf_images: Sequence[PdfPageImage],
        page_index: Any | None,
        project_id: str,
    ) -> dict[str, Any]:
        heuristics = self._run_heuristics(page_index)
        logger.bind(project_id=project_id, stage="procurement_analyzer").debug(
            "Procurement heuristics", **heuristics
        )

        gpt_payload: dict[str, Any] | None = None
        # Phase 1: Always call GPT if enabled (enhanced prompt handles pattern recognition)
        # GPT is more reliable than heuristics for detecting government projects
        # CRITICAL: Use GPT Vision even when OCR fails (image-only PDFs)
        if self.settings.procurement_enable_gpt and pdf_images:
            # Use candidate_pages if available, otherwise use first few pages
            pages_to_use = (
                list(heuristics["candidate_pages"])
                if heuristics["candidate_pages"]
                else list(range(1, min(len(pdf_images) + 1, self.settings.procurement_max_pages_to_review + 1)))
            )
            
            # If heuristics found nothing (no text extracted), still use GPT Vision to read images
            # This handles image-only PDFs where OCR failed
            if not heuristics["candidate_pages"] and not heuristics.get("is_public_project", False):
                # No text found, but use GPT Vision to read first page (usually has title/agency info)
                pages_to_use = [1]  # Always check first page with GPT Vision
                logger.bind(project_id=project_id, stage="procurement_analyzer").info(
                    "No text extracted from page index - using GPT Vision to read images for government detection"
                )
            
            if pages_to_use:
                gpt_payload = self._call_gpt(pdf_images, pages_to_use, project_id)
                if gpt_payload:
                    logger.bind(project_id=project_id, stage="procurement_analyzer").info(
                        "Procurement GPT detection completed", 
                        is_public=gpt_payload.get("is_public_project"),
                        confidence=gpt_payload.get("detection_confidence"),
                        issuing_authority=gpt_payload.get("issuing_authority"),
                        requires_prevailing_wage=gpt_payload.get("requires_prevailing_wage"),
                        requires_bonds=gpt_payload.get("requires_bonds")
                    )
                else:
                    logger.bind(project_id=project_id, stage="procurement_analyzer").warning(
                        "Procurement GPT call returned no payload"
                    )
            else:
                logger.bind(project_id=project_id, stage="procurement_analyzer").warning(
                    "No pages available for procurement GPT analysis"
                )

        merged = self._merge_results(heuristics, gpt_payload)
        
        # Always return a payload, even if empty (ensures procurement_context field exists)
        try:
            result = ProcurementAnalysisResult(
                procurement_context=ProcurementContext(**merged["procurement_context"]),
                requires_prevailing_wage=merged.get("requires_prevailing_wage"),
                requires_bonds=merged.get("requires_bonds"),
                issuing_authority=merged.get("issuing_authority"),
            )
            payload = result.to_payload()
            logger.bind(project_id=project_id, stage="procurement_analyzer").debug(
                "Procurement analysis result",
                payload_keys=list(payload.keys()),
                is_public=merged["procurement_context"].get("is_public_project"),
            )
            return payload
        except Exception as e:
            logger.bind(project_id=project_id, stage="procurement_analyzer").exception(
                f"Failed to create procurement result: {e}",
                exc_info=True
            )
            # Return minimal valid payload on error
            return {
                "procurement_context": {
                    "is_public_project": False,
                    "detection_confidence": 0.0,
                    "indicators": [],
                    "notes": [f"Procurement analysis error: {str(e)}"],
                    "source_pages": [],
                },
                "requires_prevailing_wage": None,
                "requires_bonds": None,
                "issuing_authority": None,
            }

    # ---------------------------------------------------------------------
    # Heuristics
    # ---------------------------------------------------------------------
    def _run_heuristics(self, page_index: Any | None) -> dict[str, Any]:
        indicators: list[str] = []
        notes: list[str] = []
        candidate_pages: set[int] = set()

        public_keywords = {kw.lower() for kw in self.settings.procurement_public_keywords}
        wage_keywords = {kw.lower() for kw in self.settings.procurement_prevailing_wage_keywords}
        bond_keywords = {kw.lower() for kw in self.settings.procurement_bond_keywords}

        matches_public: set[str] = set()
        matches_prevailing: set[str] = set()
        matches_bond: set[str] = set()

        if page_index and getattr(page_index, "pages", None):
            for page in page_index.pages:
                text_tokens = self._tokenize_page(page)
                lowered = " ".join(text_tokens)
                matched_public = {kw for kw in public_keywords if kw in lowered}
                matched_wage = {kw for kw in wage_keywords if kw in lowered}
                matched_bond = {kw for kw in bond_keywords if kw in lowered}

                if matched_public or matched_wage or matched_bond:
                    candidate_pages.add(int(page.page_number))

                matches_public.update(matched_public)
                matches_prevailing.update(matched_wage)
                matches_bond.update(matched_bond)

                if matched_public:
                    indicators.extend(sorted(matched_public))
                if matched_wage:
                    notes.append(
                        f"Prevailing wage indicators on page {page.page_number}: {sorted(matched_wage)}"
                    )
                if matched_bond:
                    notes.append(
                        f"Bond/compliance indicators on page {page.page_number}: {sorted(matched_bond)}"
                    )

        base_confidence = min(1.0, 0.25 * len(matches_public))
        is_public_project = base_confidence >= self.settings.procurement_public_threshold

        requires_prevailing_wage = None
        if matches_prevailing:
            requires_prevailing_wage = True
        elif is_public_project and self.settings.procurement_default_prevailing_wage:
            requires_prevailing_wage = True

        requires_bonds = None
        if matches_bond:
            requires_bonds = True
        elif is_public_project and self.settings.procurement_default_bonds:
            requires_bonds = True

        procurement_context = {
            "is_public_project": is_public_project,
            "detection_confidence": round(base_confidence, 3),
            "indicators": sorted(set(indicators)),
            "notes": notes,
            "source_pages": sorted(candidate_pages),
        }

        return {
            "procurement_context": procurement_context,
            "requires_prevailing_wage": requires_prevailing_wage,
            "requires_bonds": requires_bonds,
            "issuing_authority": None,
            "detection_confidence": procurement_context["detection_confidence"],
            "is_public_project": is_public_project,
            "candidate_pages": sorted(candidate_pages),
        }

    def _tokenize_page(self, page: Any) -> list[str]:
        tokens: list[str] = []
        for attr in ("sheet_id", "sheet_title"):
            value = getattr(page, attr, None)
            if value:
                tokens.append(str(value).lower())
        page_types = getattr(page, "page_types", None)
        if isinstance(page_types, Iterable):
            tokens.extend(str(pt).lower() for pt in page_types)
        page_indicators = getattr(page, "indicators", None)
        if isinstance(page_indicators, Iterable):
            tokens.extend(str(ind).lower() for ind in page_indicators)
        return tokens

    # ---------------------------------------------------------------------
    # GPT support
    # ---------------------------------------------------------------------
    def _call_gpt(
        self,
        pdf_images: Sequence[PdfPageImage],
        candidate_pages: Sequence[int],
        project_id: str,
    ) -> dict[str, Any] | None:
        page_map = {img.page_number: img for img in pdf_images}
        prioritized_pages = self._select_pages_for_gpt(candidate_pages, page_map.keys())
        if not prioritized_pages:
            return None

        prompt = self._build_prompt()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        for page_number in prioritized_pages:
            image = page_map.get(page_number)
            if not image:
                continue
            messages[0]["content"].append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.mime_type};base64,{image.image_base64}",
                        "detail": "low",
                    },
                }
            )

        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-procurement",
                stage_name="procurement_signal",
                project_id=project_id,
            )
        except OpenAINonRetryableError as exc:
            logger.bind(project_id=project_id, stage="procurement_analyzer").warning(
                "OpenAI non-retryable error for procurement detection: %s", exc
            )
            return None
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.bind(project_id=project_id, stage="procurement_analyzer").warning(
                "Failed to call OpenAI for procurement detection: %s", exc
            )
            return None

        try:
            parsed = self._parse_json(response_text)
            parsed.setdefault("indicators", [])
            parsed.setdefault("notes", [])
            parsed.setdefault("issuing_authority", None)
            parsed.setdefault("requires_prevailing_wage", None)
            parsed.setdefault("requires_bonds", None)
            parsed.setdefault("detection_confidence", 0.0)
            parsed.setdefault("is_public_project", False)
            parsed.setdefault("source_pages", list(prioritized_pages))
            return parsed
        except ValueError as exc:
            logger.bind(project_id=project_id, stage="procurement_analyzer").warning(
                "Invalid JSON from procurement GPT call: %s", exc
            )
            return None

    def _select_pages_for_gpt(
        self,
        candidate_pages: Sequence[int],
        available_pages: Iterable[int],
    ) -> list[int]:
        max_pages = max(1, self.settings.procurement_max_pages_to_review)
        ordered_candidates = list(dict.fromkeys(candidate_pages))
        if not ordered_candidates:
            ordered_candidates = list(sorted(dict.fromkeys(available_pages)))[:max_pages]
        return ordered_candidates[:max_pages]

    def _build_prompt(self) -> str:
        return (
            "You are reviewing images extracted from a construction bid/procurement package. "
            "Intelligently determine whether this project is issued by a government or public-sector entity.\n\n"
            "**CRITICAL: Read the document images carefully. Even if text extraction failed, you can READ text, "
            "logos, seals, and agency names directly from the images.**\n\n"
            "Use pattern recognition and semantic understanding, not just keyword matching. Look for:\n"
            "- **Federal agencies**: Department of Veterans Affairs (VA), Veterans Affairs, VA Medical Center, "
            "Department of Defense (DOD), GSA, Federal agencies, US Government, federal facilities, "
            "Department of Health and Human Services (HHS), federal medical centers\n"
            "- **State agencies**: State of [State Name], Office of General Services (OGS), State DOT, "
            "Department of Transportation, State authorities, state facilities\n"
            "- **Local agencies**: City, County, School District, Public Authority, Municipal, local government\n"
            "- **Government agency names, seals, logos** visible in the document images\n"
            "- **Variations of agency names** (e.g., 'NYS OGS', 'New York State Office of General Services', "
            "'State of New York', 'Department of Veterans Affairs', 'VA', 'Veterans Affairs', 'VA Hospital')\n"
            "- **Public procurement language** (RFPs, IFBs, public contracts, government contracts)\n"
            "- **Statutory compliance requirements** (Davis-Bacon, prevailing wage, Section 220, wage schedules)\n"
            "- **Bond requirements** (performance bonds, payment bonds, bid bonds, surety)\n"
            "- **Public works indicators** (DOT projects, public infrastructure, government facilities, "
            "VA hospitals, federal medical centers, government buildings)\n\n"
            "**Examples of government projects you should detect:**\n"
            "- 'Department of Veterans Affairs' or 'VA' → Federal government\n"
            "- 'New York State Office of General Services' or 'NYS OGS' → State government\n"
            "- 'Department of Transportation' or 'DOT' → Government (federal or state)\n"
            "- 'City of [Name]' or 'County of [Name]' → Local government\n"
            "- Any mention of 'public project', 'government contract', 'public works'\n\n"
            "Generalize across variations: recognize that 'Department of Transportation', 'DOT', 'State DOT', "
            "and 'Highway Department' all indicate government work. 'Department of Veterans Affairs', 'VA', "
            "'Veterans Affairs', 'VA Medical Center' all indicate federal government work. Similarly, "
            "'prevailing wage', 'Davis-Bacon wages', 'wage determination', and 'Section 220' all indicate "
            "wage compliance requirements.\n\n"
            "Return ONLY valid JSON with this schema (no markdown, no explanation):\n"
            "{\n"
            "  \"is_public_project\": true | false,\n"
            "  \"detection_confidence\": number between 0 and 1,\n"
            "  \"indicators\": [\"short phrases explaining evidence\"],\n"
            "  \"notes\": [\"context or caveats\"],\n"
            "  \"issuing_authority\": string or null,\n"
            "  \"requires_prevailing_wage\": true | false | null,\n"
            "  \"requires_bonds\": true | false | null\n"
            "}\n"
            "Confidence should reflect your certainty. Set requires_prevailing_wage and requires_bonds based on "
            "evidence of wage requirements or bond language, not just because it's a public project."
        )

    def _parse_json(self, content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        content = content.strip()
        if not content:
            raise ValueError("empty response")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc

    # ---------------------------------------------------------------------
    # Merge heuristics + GPT
    # ---------------------------------------------------------------------
    def _merge_results(
        self,
        heuristics: dict[str, Any],
        gpt_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        context = heuristics["procurement_context"].copy()
        requires_prevailing_wage = heuristics.get("requires_prevailing_wage")
        requires_bonds = heuristics.get("requires_bonds")
        issuing_authority = heuristics.get("issuing_authority")

        if gpt_payload:
            # GPT results take precedence - if GPT says it's public, trust it
            gpt_is_public = gpt_payload.get("is_public_project", False)
            if gpt_is_public:
                context["is_public_project"] = True
                # Use GPT confidence if it detected public project
                gpt_confidence = float(gpt_payload.get("detection_confidence", 0.0))
                if gpt_confidence > 0:
                    context["detection_confidence"] = max(
                        context["detection_confidence"],
                        gpt_confidence,
                    )
            else:
                # Only use heuristics if GPT says it's not public
                context["is_public_project"] = bool(
                    context["is_public_project"] or False
                )
            indicators = set(context.get("indicators", []))
            indicators.update(gpt_payload.get("indicators", []) or [])
            context["indicators"] = sorted(indicators)

            notes = list(context.get("notes", []))
            notes.extend(gpt_payload.get("notes", []) or [])
            context["notes"] = notes

            source_pages = set(context.get("source_pages", []))
            source_pages.update(gpt_payload.get("source_pages", []) or [])
            context["source_pages"] = sorted(source_pages)

            issuing_authority = issuing_authority or gpt_payload.get("issuing_authority")

            if gpt_payload.get("requires_prevailing_wage") is not None:
                requires_prevailing_wage = gpt_payload["requires_prevailing_wage"]
            if gpt_payload.get("requires_bonds") is not None:
                requires_bonds = gpt_payload["requires_bonds"]

        return {
            "procurement_context": context,
            "requires_prevailing_wage": requires_prevailing_wage,
            "requires_bonds": requires_bonds,
            "issuing_authority": issuing_authority,
        }
