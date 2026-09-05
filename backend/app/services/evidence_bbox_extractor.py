"""Evidence bbox extractor (Phase 8.6D).

Extracts bounding boxes for evidence snippets using PDF-native text search (preferred)
or OCR fallback (optional).
"""

import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from loguru import logger

from app.core.config import Settings
from app.schemas.evidence_bbox_index import EvidenceBboxEntry, EvidenceBboxIndex
from app.schemas.evidence_index import EvidenceIndex, EvidenceReference
from app.services.storage import StorageService


class EvidenceBboxExtractor:
    """Extract bounding boxes for evidence snippets."""

    def __init__(self, settings: Settings, storage_service: StorageService) -> None:
        """Initialize bbox extractor."""
        self.settings = settings
        self.storage_service = storage_service
        self.enable_ocr = getattr(settings, "enable_ocr_bbox_extraction", False)  # Optional config flag

    def generate(
        self,
        project_id: str,
        evidence_index: EvidenceIndex,
    ) -> EvidenceBboxIndex:
        """
        Generate evidence bbox index.

        Args:
            project_id: Project ID
            evidence_index: Evidence index from Phase 6.7/8.x

        Returns:
            EvidenceBboxIndex with bbox entries and metrics
        """
        log_ctx = logger.bind(project_id=project_id, service="evidence_bbox_extractor")

        log_ctx.info("Starting evidence bbox extraction")

        # Load source PDF
        pdf_path = self.storage_service.get_source_pdf_path(project_id)
        if not pdf_path.exists():
            log_ctx.warning(f"Source PDF not found at {pdf_path}, skipping bbox extraction")
            return EvidenceBboxIndex(
                project_id=project_id,
                generated_at=self._get_timestamp(),
                entries=[],
                metrics={"bbox_match_rate": 0.0, "total_evidence": 0},
            )

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            log_ctx.error(f"Failed to open PDF: {e}")
            return EvidenceBboxIndex(
                project_id=project_id,
                generated_at=self._get_timestamp(),
                entries=[],
                metrics={"bbox_match_rate": 0.0, "total_evidence": 0, "error": str(e)},
            )

        entries: list[EvidenceBboxEntry] = []
        total_evidence = 0
        matched_count = 0
        confidence_scores: list[float] = []
        ocr_pages_processed = 0

        # Collect all evidence references
        all_refs: list[tuple[str, EvidenceReference]] = []

        # From bid_item_evidence
        for bid_evidence in evidence_index.bid_item_evidence:
            for idx, ref in enumerate(bid_evidence.evidence_references):
                evidence_id = f"bid_item_{bid_evidence.line_item_index}_ref_{idx}"
                all_refs.append((evidence_id, ref))

        # From zone_evidence
        for zone_evidence in evidence_index.zone_evidence:
            for idx, ref in enumerate(zone_evidence.evidence_references):
                evidence_id = f"zone_{zone_evidence.zone_id}_ref_{idx}"
                all_refs.append((evidence_id, ref))

        # From detail_evidence
        for detail_evidence in evidence_index.detail_evidence:
            for idx, ref in enumerate(detail_evidence.evidence_references):
                evidence_id = f"detail_{detail_evidence.detail_id}_ref_{idx}"
                all_refs.append((evidence_id, ref))

        total_evidence = len(all_refs)
        log_ctx.info(f"Processing {total_evidence} evidence references")

        # Process each evidence reference
        for evidence_id, ref in all_refs:
            page_num = ref.page_number
            snippet = ref.evidence_snippet

            # Validate page number
            if page_num < 1 or page_num > len(doc):
                log_ctx.warning(f"Invalid page number {page_num} for evidence {evidence_id}, skipping")
                entries.append(
                    EvidenceBboxEntry(
                        evidence_id=evidence_id,
                        page_number=page_num,
                        snippet=snippet,
                        bbox=None,
                        bbox_source="none",
                    )
                )
                continue

            # Get page (0-indexed)
            page = doc[page_num - 1]

            # Try PDF-native text search first
            bbox_result = self._extract_bbox_from_pdf_text(page, snippet, page_num)

            if bbox_result:
                matched_count += 1
                if bbox_result.get("confidence"):
                    confidence_scores.append(bbox_result["confidence"])

                entries.append(
                    EvidenceBboxEntry(
                        evidence_id=evidence_id,
                        page_number=page_num,
                        snippet=snippet,
                        bbox=bbox_result["bbox"],
                        bbox_source="pdf",
                        match_confidence=bbox_result.get("confidence"),
                        match_method=bbox_result.get("method", "text_search"),
                    )
                )
            else:
                # No match found - leave bbox as null
                entries.append(
                    EvidenceBboxEntry(
                        evidence_id=evidence_id,
                        page_number=page_num,
                        snippet=snippet,
                        bbox=None,
                        bbox_source="none",
                        match_method="no_match",
                    )
                )

        doc.close()

        # Calculate metrics
        bbox_match_rate = (matched_count / total_evidence * 100) if total_evidence > 0 else 0.0
        avg_confidence = (
            sum(confidence_scores) / len(confidence_scores) if confidence_scores else None
        )

        metrics = {
            "bbox_match_rate": round(bbox_match_rate, 2),
            "total_evidence": total_evidence,
            "matched_count": matched_count,
            "ocr_pages_processed": ocr_pages_processed,
        }
        if avg_confidence is not None:
            metrics["avg_match_confidence"] = round(avg_confidence, 3)

        log_ctx.info(
            f"Bbox extraction complete: {matched_count}/{total_evidence} matched "
            f"({bbox_match_rate:.1f}%), avg confidence: {avg_confidence:.3f if avg_confidence else 'N/A'}"
        )

        return EvidenceBboxIndex(
            project_id=project_id,
            generated_at=self._get_timestamp(),
            entries=entries,
            metrics=metrics,
        )

    def _extract_bbox_from_pdf_text(
        self, page: fitz.Page, snippet: str, page_num: int
    ) -> dict[str, Any] | None:
        """
        Extract bbox from PDF using native text search.

        Args:
            page: PyMuPDF page object
            snippet: Evidence snippet text to search for
            page_num: Page number (for logging)

        Returns:
            Dict with 'bbox', 'confidence', 'method' if found, None otherwise
        """
        # Normalize snippet for search (remove extra whitespace, lowercase)
        search_text = re.sub(r"\s+", " ", snippet.strip())
        if not search_text:
            return None

        # Try exact search first
        text_instances = page.search_for(search_text)
        if text_instances:
            # Use first match (could be improved to pick best match)
            rect = text_instances[0]
            bbox = self._rect_to_normalized_bbox(rect, page)
            return {
                "bbox": bbox,
                "confidence": 1.0,
                "method": "text_search_exact",
            }

        # Try fuzzy search (substring matching)
        # Get all text blocks on the page
        text_dict = page.get_text("dict")
        best_match = None
        best_score = 0.0

        for block in text_dict.get("blocks", []):
            if "lines" not in block:
                continue

            block_text = ""
            block_rect = None

            for line in block.get("lines", []):
                line_text = ""
                line_rect = None

                for span in line.get("spans", []):
                    span_text = span.get("text", "").strip()
                    if span_text:
                        line_text += span_text + " "
                        if line_rect is None:
                            line_rect = fitz.Rect(span["bbox"])
                        else:
                            line_rect = line_rect | fitz.Rect(span["bbox"])

                if line_text and line_rect:
                    block_text += line_text + "\n"
                    if block_rect is None:
                        block_rect = line_rect
                    else:
                        block_rect = block_rect | line_rect

            if block_text and block_rect:
                # Calculate similarity score
                score = self._calculate_text_similarity(search_text.lower(), block_text.lower())
                if score > best_score and score > 0.5:  # Threshold for fuzzy match
                    best_score = score
                    best_match = {
                        "bbox": self._rect_to_normalized_bbox(block_rect, page),
                        "confidence": score,
                        "method": "fuzzy_match",
                    }

        return best_match

    def _rect_to_normalized_bbox(self, rect: fitz.Rect, page: fitz.Page) -> dict[str, float]:
        """
        Convert PyMuPDF Rect to normalized bbox (0-1).

        Args:
            rect: PyMuPDF Rect object
            page: Page object (for dimensions)

        Returns:
            Dict with x0, y0, x1, y1 normalized to 0-1
        """
        page_rect = page.rect
        width = page_rect.width
        height = page_rect.height

        return {
            "x0": max(0.0, min(1.0, rect.x0 / width)),
            "y0": max(0.0, min(1.0, rect.y0 / height)),
            "x1": max(0.0, min(1.0, rect.x1 / width)),
            "y1": max(0.0, min(1.0, rect.y1 / height)),
        }

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate text similarity score (0-1).

        Simple token overlap scoring.
        """
        # Normalize whitespace
        text1 = re.sub(r"\s+", " ", text1.strip().lower())
        text2 = re.sub(r"\s+", " ", text2.strip().lower())

        # Exact match
        if text1 in text2 or text2 in text1:
            return 1.0

        # Token overlap
        tokens1 = set(text1.split())
        tokens2 = set(text2.split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        # Jaccard similarity
        if not union:
            return 0.0

        return len(intersection) / len(union)

    def _get_timestamp(self) -> str:
        """Get ISO timestamp."""
        from datetime import datetime

        return datetime.utcnow().isoformat()






