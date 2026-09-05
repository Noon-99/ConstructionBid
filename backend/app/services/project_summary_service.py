"""Service for building high-level project context summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from loguru import logger

from app.schemas.project_summary import (
    ProjectContextSummary,
    SummaryMaterial,
    SummaryQuantity,
    SummaryScopeItem,
    SummaryWarning,
)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.bind(path=str(path)).warning("Failed to load JSON artifact", error=str(exc))
        return None


class ProjectSummaryService:
    """Builds a ProjectContextSummary from existing pipeline artifacts."""

    MAX_SCOPE_ITEMS = 4
    MAX_MATERIALS = 4
    MAX_QUANTITIES = 4
    MAX_WARNINGS = 6

    def build(self, project_id: str, output_dir: Path) -> ProjectContextSummary:
        doc_analysis = _load_json(output_dir / "document_analysis.json") or {}
        extraction = _load_json(output_dir / "extraction_result.json") or {}
        bid_proposal = _load_json(output_dir / "bid_proposal.json") or {}
        validation_report = _load_json(output_dir / "validation_report.json") or {}

        summary = ProjectContextSummary(
            project_id=project_id,
            project_type=doc_analysis.get("project_type"),
            scope_type=doc_analysis.get("scope_type"),
            primary_trade=doc_analysis.get("primary_trade"),
            primary_division=doc_analysis.get("primary_division"),
            location_summary=self._derive_location(doc_analysis, extraction),
            scope_overview=self._build_scope_items(extraction.get("scope_of_work", [])),
            materials=self._build_materials(extraction.get("material_specifications", [])),
            quantities=self._build_quantities(extraction.get("quantity_takeoff", [])),
            warnings=self._build_warnings(bid_proposal, validation_report),
            metadata=self._build_metadata(bid_proposal, validation_report),
        )

        return summary

    def _derive_location(self, doc_analysis: dict[str, Any], extraction: dict[str, Any]) -> str | None:
        building_context = doc_analysis.get("building_context") or {}
        site_context = doc_analysis.get("site_context") or {}
        geometry = extraction.get("geometry_for_3d") or {}
        geometry_site = geometry.get("site_context") or {}

        addresses = (
            building_context.get("addresses")
            or site_context.get("addresses")
            or geometry_site.get("addresses")
        )
        if isinstance(addresses, list) and addresses:
            return ", ".join(addresses[:2])
        return None

    def _build_scope_items(self, scope_entries: Iterable[dict[str, Any]]) -> list[SummaryScopeItem]:
        items: list[SummaryScopeItem] = []
        for entry in scope_entries:
            description = entry.get("item") or entry.get("description")
            if not description:
                continue
            items.append(
                SummaryScopeItem(
                    description=description,
                    evidence_page=entry.get("page_number"),
                    evidence_sheet=entry.get("sheet_id"),
                )
            )
            if len(items) >= self.MAX_SCOPE_ITEMS:
                break
        return items

    def _build_materials(self, materials: Iterable[dict[str, Any]]) -> list[SummaryMaterial]:
        out: list[SummaryMaterial] = []
        for material in materials:
            name = material.get("material_name") or material.get("specification")
            if not name:
                continue
            out.append(
                SummaryMaterial(
                    name=name,
                    application=material.get("application"),
                    evidence_page=material.get("page_number"),
                )
            )
            if len(out) >= self.MAX_MATERIALS:
                break
        return out

    def _build_quantities(self, quantities: Iterable[dict[str, Any]]) -> list[SummaryQuantity]:
        selected: list[SummaryQuantity] = []

        def append_quantity(entry: dict[str, Any]) -> None:
            quantity_value = entry.get("quantity")
            if quantity_value in (None, ""):
                return
            try:
                quantity_num = float(quantity_value)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                return
            selected.append(
                SummaryQuantity(
                    item=entry.get("item", ""),
                    quantity=quantity_num,
                    unit=entry.get("unit", ""),
                    confidence=None,
                    source=("computed" if entry.get("is_computed") else None),
                    evidence_page=entry.get("page_number"),
                )
            )

        # Prefer direct (non-computed, evidence_present) quantities first
        for entry in quantities:
            if entry.get("quantity") is None:
                continue
            if entry.get("evidence_missing"):
                continue
            if entry.get("is_computed"):
                continue
            append_quantity(entry)
            if len(selected) >= self.MAX_QUANTITIES:
                return selected

        # Fallback: include computed quantities if limit not reached
        if len(selected) < self.MAX_QUANTITIES:
            for entry in quantities:
                if entry.get("quantity") is None:
                    continue
                if entry.get("evidence_missing"):
                    continue
                if entry.get("is_computed"):
                    append_quantity(entry)
                    if len(selected) >= self.MAX_QUANTITIES:
                        break

        return selected

    def _build_warnings(
        self,
        bid_proposal: dict[str, Any],
        validation_report: dict[str, Any],
    ) -> list[SummaryWarning]:
        warnings: list[SummaryWarning] = []

        clarifications = bid_proposal.get("clarifications") or []
        for clarification in clarifications:
            message = clarification.get("text")
            if not message:
                continue
            warnings.append(
                SummaryWarning(
                    message=message,
                    severity=clarification.get("severity", "info"),
                )
            )
            if len(warnings) >= self.MAX_WARNINGS:
                return warnings

        issues = validation_report.get("issues") or []
        for issue in issues:
            message = issue.get("message")
            if not message:
                continue
            warnings.append(
                SummaryWarning(
                    message=message,
                    severity=issue.get("severity", "warning"),
                )
            )
            if len(warnings) >= self.MAX_WARNINGS:
                break

        return warnings

    def _build_metadata(
        self,
        bid_proposal: dict[str, Any],
        validation_report: dict[str, Any],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        summary = bid_proposal.get("summary") or {}
        total_cost = summary.get("total_cost")
        if total_cost is not None:
            metadata["total_cost"] = total_cost
        validation_score = validation_report.get("score")
        if validation_score is not None:
            metadata["validation_score"] = validation_score
        return metadata
