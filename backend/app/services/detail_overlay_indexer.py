"""Detail overlay indexer (Phase 8.4).

Maps cross-section regions to detail references and evidence for section view navigation.
"""

from datetime import datetime
from typing import Any

from loguru import logger

from app.schemas.detail_overlay_index import (
    DetailOverlayIndex,
    DetailOverlayRef,
    EvidenceSnippet,
)


class DetailOverlayIndexer:
    """Generates detail overlay index from cross-section regions, detail graph, and evidence."""

    def __init__(self) -> None:
        """Initialize detail overlay indexer."""
        pass

    def generate(
        self,
        project_id: str,
        model_3d: dict[str, Any],
        detail_graph: dict[str, Any] | None = None,
        evidence_index: dict[str, Any] | None = None,
    ) -> DetailOverlayIndex:
        """
        Generate detail overlay index.

        Args:
            project_id: Project ID
            model_3d: Model3D JSON (from model_3d.json)
            detail_graph: DetailGraph JSON (from extraction_result.detail_graph, optional)
            evidence_index: EvidenceIndex JSON (from evidence_index.json, optional)

        Returns:
            DetailOverlayIndex with region-to-detail mappings
        """
        log_ctx = logger.bind(project_id=project_id, stage="detail_overlay_index")
        log_ctx.info("Generating detail overlay index")

        # Extract cross-section regions from model_3d
        cross_section_regions = model_3d.get("cross_section_regions", [])
        if not cross_section_regions:
            log_ctx.warning("No cross-section regions found in model_3d")
            return DetailOverlayIndex(
                project_id=project_id,
                generated_at=datetime.utcnow().isoformat(),
                regions=[],
            )

        # Build detail lookup from detail_graph
        detail_lookup: dict[str, dict[str, Any]] = {}
        if detail_graph:
            for detail in detail_graph.get("details", []):
                detail_id = detail.get("detail_id")
                if detail_id:
                    detail_lookup[detail_id] = detail

        # Build detail evidence lookup from evidence_index
        detail_evidence_lookup: dict[str, dict[str, Any]] = {}
        if evidence_index:
            for detail_evidence in evidence_index.get("detail_evidence", []):
                detail_id = detail_evidence.get("detail_id")
                if detail_id:
                    detail_evidence_lookup[detail_id] = detail_evidence

        # Generate overlay refs for each region
        overlay_refs: list[DetailOverlayRef] = []
        for region in cross_section_regions:
            region_id = region.get("region_id", "")
            region_type = region.get("region_type", "")
            detail_refs = region.get("detail_refs", [])

            # Collect detail IDs from region
            detail_ids: list[str] = list(detail_refs) if detail_refs else []

            # Build detail_refs with sheet_id, detail_label, page_number
            detail_refs_list: list[dict] = []
            evidence_pages_set: set[int] = set()
            snippets_list: list[EvidenceSnippet] = []

            for detail_id in detail_ids:
                # Get detail info from detail_graph
                detail_info = detail_lookup.get(detail_id)
                if detail_info:
                    detail_refs_list.append(
                        {
                            "detail_id": detail_id,
                            "sheet_id": detail_info.get("sheet_id", ""),
                            "detail_label": detail_info.get("detail_label", ""),
                            "page_number": detail_info.get("page_number", 1),
                            "detail_type": detail_info.get("detail_type", ""),
                        }
                    )
                    # Add page number to evidence pages
                    page_num = detail_info.get("page_number", 1)
                    if page_num > 0:
                        evidence_pages_set.add(page_num)

                    # Add evidence snippet from detail_graph
                    evidence_snippet = detail_info.get("evidence_snippet", "")
                    if evidence_snippet:
                        snippets_list.append(
                            EvidenceSnippet(
                                page_number=page_num,
                                sheet_id=detail_info.get("sheet_id"),
                                snippet=evidence_snippet,
                                location_type="detail",
                            )
                        )

                # Get additional evidence from evidence_index
                detail_evidence = detail_evidence_lookup.get(detail_id)
                if detail_evidence:
                    for evidence_ref in detail_evidence.get("evidence_references", []):
                        page_num = evidence_ref.get("page_number", 1)
                        if page_num > 0:
                            evidence_pages_set.add(page_num)

                        snippets_list.append(
                            EvidenceSnippet(
                                page_number=page_num,
                                sheet_id=evidence_ref.get("sheet_id"),
                                snippet=evidence_ref.get("evidence_snippet", ""),
                                location_type=evidence_ref.get("location_type"),
                            )
                        )

            # Add region evidence snippet if available
            region_evidence = region.get("evidence", "")
            if region_evidence:
                # Try to extract page number from evidence (heuristic)
                # This is a fallback if no detail evidence is found
                if not snippets_list:
                    snippets_list.append(
                        EvidenceSnippet(
                            page_number=1,  # Default if not found
                            sheet_id=None,
                            snippet=region_evidence,
                            location_type="region_evidence",
                        )
                    )

            overlay_refs.append(
                DetailOverlayRef(
                    region_id=region_id,
                    region_type=region_type,
                    detail_ids=detail_ids,
                    detail_refs=detail_refs_list,
                    evidence_pages=sorted(list(evidence_pages_set)),
                    snippets=snippets_list,
                )
            )

        index = DetailOverlayIndex(
            project_id=project_id,
            generated_at=datetime.utcnow().isoformat(),
            regions=overlay_refs,
        )

        log_ctx.info(
            f"Detail overlay index generated: {len(overlay_refs)} regions, "
            f"{sum(len(r.detail_ids) for r in overlay_refs)} detail links"
        )

        return index






