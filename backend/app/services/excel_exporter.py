"""Excel export service for bid artifacts with sticky explanations.

Creates an Excel workbook summarizing bid financials, compliance signals, and
line-item evidence so that reviewers can trace how the AI arrived at each cost.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from app.core.config import Settings, get_settings


def create_bid_excel_export(
    project_id: str,
    output_dir: Path,
    settings: Settings | None = None,
) -> Path:
    """Generate an Excel workbook for a project's bid artifacts."""

    if settings is None:
        settings = get_settings()

    bid_proposal = _load_json(output_dir / "bid_proposal.json", "bid proposal")
    costing_result = _load_json(output_dir / "costing_result.json", "costing result")
    bid_review = _load_json(output_dir / "bid_review.json", "bid review", required=False)
    document_analysis = _load_json(
        output_dir / "document_analysis.json", "document analysis", required=False
    )
    trust_report = _load_json(
        output_dir / "trust_report.json", "trust report", required=False
    )

    export_path = output_dir / "bid_export.xlsx"

    workbook = _build_workbook(
        project_id=project_id,
        bid_proposal=bid_proposal,
        costing_result=costing_result,
        bid_review=bid_review,
        document_analysis=document_analysis,
        trust_report=trust_report,
        settings=settings,
    )
    export_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(export_path)

    logger.bind(project_id=project_id).info(
        "Excel export generated", path=str(export_path)
    )
    return export_path


def _load_json(path: Path, label: str, required: bool = True) -> dict[str, Any] | None:
    """Load JSON artifact, optionally skipping if missing."""

    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing {label} artifact at {path}")
        logger.debug(f"{label.title()} artifact missing at {path}, continuing without it")
        return None

    with open(path, "r") as f:
        return json.load(f)


def _build_workbook(
    project_id: str,
    bid_proposal: dict[str, Any],
    costing_result: dict[str, Any],
    bid_review: dict[str, Any] | None,
    document_analysis: dict[str, Any] | None,
    trust_report: dict[str, Any] | None,
    settings: Settings,
) -> Workbook:
    """Create the Excel workbook in memory."""

    wb = Workbook()
    summary_ws = wb.active
    summary_ws.title = "Summary"

    _populate_summary_sheet(
        summary_ws,
        project_id=project_id,
        bid_proposal=bid_proposal,
        costing_result=costing_result,
        document_analysis=document_analysis,
        trust_report=trust_report,
        settings=settings,
    )

    _populate_line_items_sheet(wb, bid_proposal, bid_review, costing_result)
    _populate_clarifications_sheet(wb, bid_proposal)
    _populate_compliance_sheet(wb, costing_result, document_analysis, trust_report)
    _populate_cost_breakdown_sheet(wb, costing_result)
    _populate_division_totals_sheet(wb, bid_proposal)

    return wb


def _populate_summary_sheet(
    ws,
    project_id: str,
    bid_proposal: dict[str, Any],
    costing_result: dict[str, Any],
    document_analysis: dict[str, Any] | None,
    trust_report: dict[str, Any] | None,
    settings: Settings,
) -> None:
    """Fill the summary sheet with top-level metrics."""

    ws.append(["Field", "Value"])
    ws.freeze_panes = "A2"

    summary_rows = []
    summary = bid_proposal.get("summary", {})

    summary_rows.append(("Project ID", project_id))
    project_name = (
        trust_report.get("project_name")
        if trust_report and trust_report.get("project_name")
        else document_analysis.get("project_address") if document_analysis else None
    )
    if project_name:
        summary_rows.append(("Project", project_name))

    summary_rows.extend(
        [
            ("Total Bid", _format_currency(summary.get("total_cost"))),
            ("Base Scope Cost", _format_currency(summary.get("base_scope_cost"))),
            ("Compliance Total", _format_currency(summary.get("compliance_total"))),
            (
                "Compliance Components",
                _format_components(summary.get("compliance_costs")),
            ),
            (
                "Contingency Recommendation",
                _format_contingency(
                    summary.get("contingency_recommendation_pct"),
                    summary.get("contingency_recommendation_amount"),
                ) or _calculate_contingency_recommendation(
                    summary.get("total_cost", 0),
                    document_analysis,
                ) or "—",
            ),
        ]
    )

    profile_id = costing_result.get("profile_id")
    if profile_id:
        summary_rows.append(("Pricing Profile", profile_id))

    # Phase 1: Add project type (Government detection)
    if document_analysis:
        procurement_context = document_analysis.get("procurement_context") or {}
        if procurement_context and procurement_context.get("is_public_project"):
            issuing_authority = document_analysis.get("issuing_authority") or procurement_context.get("issuing_authority")
            if issuing_authority:
                summary_rows.append(("Project Type", f"Government - {issuing_authority}"))
            else:
                summary_rows.append(("Project Type", "Government"))
        elif trust_report and trust_report.get("project_type"):
            summary_rows.append(("Project Type", trust_report.get("project_type")))
        
        # Phase 1: Fix labor regime - show "Prevailing Wage Required" if government project
        procurement_context = document_analysis.get("procurement_context") or {}
        is_public = procurement_context.get("is_public_project", False)
        requires_prevailing_wage = document_analysis.get("requires_prevailing_wage", False) or is_public
        labor_regime = document_analysis.get("labor_regime", "standard")
        
        if requires_prevailing_wage or is_public or labor_regime == "prevailing_wage":
            # Check if multiplier was actually applied (labor_regime must be "prevailing_wage")
            multiplier_applied = (labor_regime == "prevailing_wage")
            
            # Calculate estimated impact
            base_scope = summary.get("base_scope_cost", 0) or 0
            labor_total = costing_result.get("labor_cost_total", 0) or 0
            
            # Get multiplier percentage
            compliance_adjustments = costing_result.get("compliance_adjustments", []) or []
            prevailing_note = next(
                (adj for adj in compliance_adjustments if "prevailing wage" in adj.lower()),
                None
            )
            
            multiplier_pct = 50  # Default estimate
            if prevailing_note:
                import re
                match = re.search(r'\+(\d+)%', prevailing_note)
                if match:
                    multiplier_pct = int(match.group(1))
            
            if multiplier_applied:
                # Multiplier IS applied - show that it's included
                labor_regime_display = f"NYS Prevailing Wage Required - Verify wage determination (Estimated +{multiplier_pct}% multiplier INCLUDED in base costs)"
            else:
                # Multiplier NOT applied - calculate estimated impact
                # Estimate: if labor is typically 20-30% of base, and we add 50% to labor, impact is 10-15% of base
                estimated_impact_pct = 0.12  # Conservative 12% of base (assuming 24% labor component)
                estimated_impact = base_scope * estimated_impact_pct
                
                labor_regime_display = (
                    f"NYS Prevailing Wage: REQUIRED BUT NOT YET APPLIED | "
                    f"Action: Add ~${estimated_impact:,.0f} (~{estimated_impact_pct*100:.0f}% of base) "
                    f"after verifying wage determination | "
                    f"Multiplier: +{multiplier_pct}% on labor rates"
                )
        else:
            labor_regime_display = labor_regime.replace("_", " ").title()
        summary_rows.append(("Labor Regime", labor_regime_display))
        
        if procurement_context:
            summary_rows.append(
                (
                    "Procurement Signals",
                    ", ".join(procurement_context.get("indicators", [])) or "None",
                )
            )

    if trust_report:
        summary_rows.extend(
            [
                (
                    "Overall Confidence",
                    f"{trust_report.get('overall_confidence', 0):.0f}%",
                ),
                ("Confidence Explanation", trust_report.get("confidence_explanation", "")),
            ]
        )

    summary_rows.append(("Generated", datetime.utcnow().isoformat()))
    summary_rows.append(("Environment", "Contractor Mode" if summary.get("bid_mode") == "contractor" else "Conceptual"))
    summary_rows.append(("Config Storage Root", str(settings.storage_root)))

    for field, value in summary_rows:
        ws.append([field, value])

    _autosize_columns(ws)
    _bold_header(ws)


def _populate_line_items_sheet(
    wb: Workbook,
    bid_proposal: dict[str, Any],
    bid_review: dict[str, Any] | None,
    costing_result: dict[str, Any] | None = None,
) -> None:
    """Populate the line items sheet with sticky explanations and cost breakdown."""

    ws = wb.create_sheet(title="Bid Line Items")
    headers = [
        "Division",
        "Description",
        "Quantity",
        "Unit",
        "Unit Cost",
        "Material Cost",
        "Labor Cost",
        "Equipment Cost",
        "Total Cost",
        "Source Sheet",
        "Confidence",
        "Notes",
    ]
    ws.append(headers)
    ws.freeze_panes = "A2"

    # Build lookup from costing_result CostItems by description
    cost_item_lookup: dict[str, dict[str, Any]] = {}
    if costing_result:
        for cost_item in costing_result.get("breakdown_by_scope_item", []):
            # Match by description (fuzzy match)
            desc = cost_item.get("item_name", "").lower()
            cost_item_lookup[desc] = cost_item

    review_lookup: dict[int, dict[str, Any]] = {}
    if bid_review:
        for item in bid_review.get("line_items", []):
            review_lookup[item.get("line_item_index", -1)] = item

    for idx, line_item in enumerate(bid_proposal.get("line_items", [])):
        review_item = review_lookup.get(idx, {})
        evidence_pages = _format_evidence_pages(review_item)
        detail_refs = review_item.get("detail_refs", []) or []
        flags = review_item.get("flags", []) or []
        
        # Try to find matching cost item for labor/material/equipment breakdown
        line_desc = line_item.get("description", "").lower()
        matching_cost_item = None
        for cost_desc, cost_item in cost_item_lookup.items():
            # Simple matching: if line item description contains key words from cost item
            if any(word in line_desc for word in cost_desc.split() if len(word) > 3):
                matching_cost_item = cost_item
                break
        
        # Calculate total costs from matching cost item
        material_cost = 0.0
        labor_cost = 0.0
        equipment_cost = 0.0
        
        if matching_cost_item:
            cost_item_qty = matching_cost_item.get("quantity", 0) or 0
            if cost_item_qty > 0:
                material_cost = matching_cost_item.get("material_cost", 0) * cost_item_qty
                labor_cost = matching_cost_item.get("labor_cost", 0) * cost_item_qty
                equipment_cost = matching_cost_item.get("equipment_cost", 0) * cost_item_qty
            else:
                line_qty = line_item.get("quantity") or 0
                if line_qty > 0:
                    material_cost = matching_cost_item.get("material_cost", 0) * line_qty
                    labor_cost = matching_cost_item.get("labor_cost", 0) * line_qty
                    equipment_cost = matching_cost_item.get("equipment_cost", 0) * line_qty

        # Build notes column: combine basis, flags, detail refs
        notes_parts = []
        qty_source = line_item.get("quantity_source", "unknown")
        if qty_source and qty_source != "unknown":
            notes_parts.append(f"Source: {qty_source.replace('_', ' ').title()}")
        
        if detail_refs:
            notes_parts.append(f"Details: {', '.join(detail_refs)}")
        
        if flags:
            notes_parts.append(f"Flags: {', '.join(flags)}")
        
        # Add basis if it's not too long
        basis = line_item.get("basis", "")
        if basis and len(basis) < 200:
            notes_parts.append(basis)
        
        notes = " | ".join(notes_parts) if notes_parts else "No additional notes"
        
        # Format confidence as percentage
        qty_confidence = line_item.get("quantity_confidence", 0.5)
        confidence_str = f"{qty_confidence*100:.0f}%"

        ws.append(
            [
                line_item.get("division"),
                line_item.get("description"),
                line_item.get("quantity"),
                line_item.get("unit"),
                _format_currency(line_item.get("unit_cost")),
                _format_currency(material_cost),
                _format_currency(labor_cost),
                _format_currency(equipment_cost),
                _format_currency(line_item.get("total_cost")),
                evidence_pages or "Estimated",
                confidence_str,
                notes,
            ]
        )

    _autosize_columns(ws, wrap_columns={11, 12})  # Wrap notes and source columns
    _bold_header(ws)


def _populate_clarifications_sheet(wb: Workbook, bid_proposal: dict[str, Any]) -> None:
    """Add clarifications & allowances for reviewer context."""

    ws = wb.create_sheet(title="Clarifications")
    ws.append(["Severity", "Clarification"])
    ws.freeze_panes = "A2"

    for clarification in bid_proposal.get("clarifications", []):
        ws.append(
            [
                clarification.get("severity", "info").title(),
                clarification.get("text", ""),
            ]
        )

    if len(ws["A"]) == 1:
        ws.append(["Info", "No clarifications captured by the pipeline."])

    _autosize_columns(ws, wrap_columns={2})
    _bold_header(ws)


def _populate_compliance_sheet(
    wb: Workbook,
    costing_result: dict[str, Any],
    document_analysis: dict[str, Any] | None,
    trust_report: dict[str, Any] | None,
) -> None:
    """Document compliance adjustments and procurement context with detailed calculations."""

    ws = wb.create_sheet(title="Compliance & Signals")
    ws.append(["Category", "Details"])
    ws.freeze_panes = "A2"

    compliance_costs = costing_result.get("compliance_costs", {}) or {}
    compliance_adjustments = costing_result.get("compliance_adjustments", []) or []
    base_scope_cost = costing_result.get("base_scope_cost", 0) or 0

    ws.append(("Compliance Total", _format_currency(costing_result.get("compliance_total"))))
    ws.append([])  # Empty row
    
    # Detailed compliance breakdown with calculations
    ws.append(("Compliance Breakdown", ""))
    if compliance_costs:
        for cost_type, amount in compliance_costs.items():
            if base_scope_cost > 0:
                pct = (amount / base_scope_cost) * 100
                ws.append((
                    f"  {cost_type.title()}",
                    f"{_format_currency(amount)} ({pct:.2f}% of base scope)"
                ))
            else:
                ws.append((f"  {cost_type.title()}", _format_currency(amount)))
    else:
        ws.append(("  None", "No compliance costs applied"))
    
    ws.append([])  # Empty row
    ws.append(("Applied Adjustments", ""))
    for i, adjustment in enumerate(compliance_adjustments, 1):
        ws.append((f"  {i}.", adjustment))

    ws.append([])  # Empty row
    ws.append(("Procurement Context", ""))
    
    if document_analysis:
        procurement_context = document_analysis.get("procurement_context") or {}
        if procurement_context:
            is_public = procurement_context.get("is_public_project", False)
            ws.append(("  Public Project", "Yes" if is_public else "No"))
            
            issuing_authority = (
                procurement_context.get("issuing_authority")
                or document_analysis.get("issuing_authority")
                or "Unknown"
            )
            ws.append(("  Issuing Authority", issuing_authority))
            
            confidence = procurement_context.get("detection_confidence", 0.0)
            ws.append(("  Detection Confidence", f"{confidence*100:.0f}%"))
            
            indicators = procurement_context.get("indicators", [])
            if indicators:
                ws.append(("  Indicators", ""))
                for indicator in indicators:
                    ws.append(("    •", indicator))
            
            notes = procurement_context.get("notes", [])
            if notes:
                ws.append(("  Notes", ""))
                for note in notes:
                    ws.append(("    •", note))
            
            source_pages = procurement_context.get("source_pages", [])
            if source_pages:
                ws.append(("  Source Pages", ", ".join(str(p) for p in source_pages)))

        # Phase 1: Fix labor regime display - show "Prevailing Wage Required" if government project
        procurement_context = document_analysis.get("procurement_context") or {}
        is_public = procurement_context.get("is_public_project", False)
        requires_prevailing_wage = document_analysis.get("requires_prevailing_wage", False) or is_public
        labor_regime = document_analysis.get("labor_regime", "standard")
        
        ws.append([])  # Empty row
        ws.append(("Labor Regime", ""))
        
        if requires_prevailing_wage or is_public or labor_regime == "prevailing_wage":
            ws.append(("  Status", "NYS Prevailing Wage Required - Verify wage determination"))
            # Add multiplier info and impact calculation
            compliance_adjustments = costing_result.get("compliance_adjustments", []) or []
            prevailing_note = next(
                (adj for adj in compliance_adjustments if "prevailing wage" in adj.lower()),
                None
            )
            if prevailing_note:
                import re
                match = re.search(r'\+(\d+)%', prevailing_note)
                if match:
                    multiplier_pct = match.group(1)
                    ws.append(("  Multiplier Applied", f"+{multiplier_pct}% (estimated)"))
                    # Calculate estimated impact
                    base_scope = costing_result.get("base_scope_cost", 0) or 0
                    labor_total = costing_result.get("labor_cost_total", 0) or 0
                    if labor_total > 0 and base_scope > 0:
                        # Estimate impact: if labor is X% of base, and we add Y% to labor, impact is X*Y% of base
                        labor_pct = (labor_total / base_scope) * 100
                        estimated_impact = base_scope * (labor_pct / 100) * (float(multiplier_pct) / 100)
                        ws.append(("  Estimated Impact", f"~${estimated_impact:,.0f} additional"))
                        ws.append(("  Standard Rate (Est)", "$35/hr"))
                        ws.append(("  Prevailing Rate (Est)", "$49-55/hr (verify wage determination)"))
                        ws.append(("  Action Required", "Obtain NYS prevailing wage determination for project location"))
        else:
            ws.append(("  Status", labor_regime.replace("_", " ").title()))
        
        # Add prevailing wage impact section if applicable
        if requires_prevailing_wage or is_public:
            ws.append([])
            ws.append(("Prevailing Wage Impact", ""))
            base_scope = costing_result.get("base_scope_cost", 0) or 0
            labor_total = costing_result.get("labor_cost_total", 0) or 0
            if labor_total > 0 and base_scope > 0:
                labor_pct = (labor_total / base_scope) * 100
                ws.append(("  Labor as % of Base", f"{labor_pct:.1f}%"))
                ws.append(("  Standard Rate (Est)", "$35/hr"))
                ws.append(("  Prevailing Rate (Est)", "$49-55/hr (verify wage determination)"))
                ws.append(("  Estimated Impact", f"~${labor_total * 0.4:,.0f} additional (40% increase on labor)"))
                ws.append(("  Action Required", "Obtain NYS prevailing wage determination for project location"))
        ws.append(
            (
                "Labor Regime Confidence",
                f"{document_analysis.get('labor_regime_confidence', 0.5):.2f}",
            )
        )

    if trust_report:
        ws.append(("Trust Report Confidence", f"{trust_report.get('overall_confidence', 0):.0f}%"))
        ws.append(("Trust Coverage Explanation", trust_report.get("confidence_explanation", "")))

    _autosize_columns(ws, wrap_columns={2})
    _bold_header(ws)


def _format_currency(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _format_components(components: dict[str, Any] | None) -> str:
    if not components:
        return "None"
    return ", ".join(f"{key.title()}: {_format_currency(val)}" for key, val in components.items())


def _format_contingency(pct: Any, amount: Any) -> str:
    if pct is None and amount is None:
        return None  # Return None so we can calculate it
    parts: list[str] = []
    if pct is not None:
        try:
            parts.append(f"{float(pct):.2f}%")
        except (TypeError, ValueError):
            parts.append(str(pct))
    if amount is not None:
        parts.append(_format_currency(amount))
    return " / ".join(parts) if parts else None


def _calculate_contingency_recommendation(
    total_cost: float,
    document_analysis: dict[str, Any] | None,
) -> str:
    """Calculate contingency recommendation if missing."""
    if total_cost <= 0:
        return None
    
    # Check if government project - recommend 10% for government projects
    procurement_context = document_analysis.get("procurement_context") or {} if document_analysis else {}
    is_public = procurement_context.get("is_public_project", False)
    
    if is_public:
        # Government projects: 10% contingency
        pct = 10.0
        amount = total_cost * 0.10
        return f"{pct:.1f}% ({_format_currency(amount)}) - Recommended for government projects"
    else:
        # Commercial projects: 5% contingency
        pct = 5.0
        amount = total_cost * 0.05
        return f"{pct:.1f}% ({_format_currency(amount)}) - Recommended for commercial projects"


def _format_evidence_pages(review_item: dict[str, Any]) -> str:
    """Format evidence pages with sheet IDs if available."""
    evidence_refs = review_item.get("evidence_refs", []) or []
    if not evidence_refs:
        return ""
    
    # Group by sheet_id if available, otherwise use page_number
    formatted_refs = []
    for ref in evidence_refs:
        sheet_id = ref.get("sheet_id")
        page_num = ref.get("page_number")
        if sheet_id:
            formatted_refs.append(f"{sheet_id} (p.{page_num})" if page_num else sheet_id)
        elif page_num:
            formatted_refs.append(f"p.{page_num}")
    
    return ", ".join(sorted(set(formatted_refs)))


def _compose_sticky_explanation(
    line_item: dict[str, Any],
    review_item: dict[str, Any],
) -> str:
    explanations: list[str] = []

    basis = line_item.get("basis")
    if basis:
        explanations.append(basis)

    multipliers = review_item.get("multipliers_applied", []) or []
    compliance_multipliers = [
        m.get("name")
        for m in multipliers
        if isinstance(m.get("name"), str) and "compliance" in m.get("name", "").lower()
    ]
    if compliance_multipliers:
        explanations.append("Compliance factors: " + ", ".join(compliance_multipliers))

    flags = review_item.get("flags", []) or []
    if flags:
        explanations.append("Flags: " + ", ".join(flags))

    evidence_refs = review_item.get("evidence_refs", []) or []
    snippets = [ref.get("snippet") for ref in evidence_refs if ref.get("snippet")]
    if snippets:
        explanations.append("Evidence snippets: " + " | ".join(snippets[:2]))

    if not explanations:
        return "No additional context captured."

    return "\n".join(explanations)


def _autosize_columns(ws, wrap_columns: set[int] | None = None) -> None:
    wrap_columns = wrap_columns or set()
    for column_cells in ws.columns:
        column_index = column_cells[0].column if column_cells else 1
        letter = get_column_letter(column_index)
        max_length = 0
        for cell in column_cells:
            cell_value = cell.value
            if isinstance(cell_value, str):
                max_length = max(max_length, len(cell_value.split("\n")[0]))
        adjusted = min(max(max_length + 2, 12), 60)
        ws.column_dimensions[letter].width = adjusted

        if column_index in wrap_columns:
            for cell in column_cells:
                cell.alignment = Alignment(wrap_text=True, vertical="top")


def _bold_header(ws) -> None:
    header_font = Font(bold=True)
    if ws.max_row == 0:
        return
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")


def _populate_cost_breakdown_sheet(
    wb: Workbook,
    costing_result: dict[str, Any],
) -> None:
    """Add cost breakdown by labor/material/equipment for contractor review."""
    
    ws = wb.create_sheet(title="Cost Breakdown")
    ws.append(["Category", "Amount", "Percentage of Total"])
    ws.freeze_panes = "A2"
    
    total_cost = costing_result.get("total_cost", 0) or 0
    material_total = costing_result.get("material_cost_total", 0) or 0
    labor_total = costing_result.get("labor_cost_total", 0) or 0
    equipment_total = costing_result.get("equipment_cost_total", 0) or 0
    waste_total = costing_result.get("waste_cost_total", 0) or 0
    compliance_total = costing_result.get("compliance_total", 0) or 0
    
    if total_cost > 0:
        ws.append(["Material Cost", _format_currency(material_total), f"{(material_total/total_cost)*100:.1f}%"])
        ws.append(["Labor Cost", _format_currency(labor_total), f"{(labor_total/total_cost)*100:.1f}%"])
        ws.append(["Equipment Cost", _format_currency(equipment_total), f"{(equipment_total/total_cost)*100:.1f}%"])
        if waste_total > 0:
            ws.append(["Waste Factor", _format_currency(waste_total), f"{(waste_total/total_cost)*100:.1f}%"])
        if compliance_total > 0:
            ws.append(["Compliance Costs", _format_currency(compliance_total), f"{(compliance_total/total_cost)*100:.1f}%"])
        ws.append([])  # Empty row
        ws.append(["Total Cost", _format_currency(total_cost), "100.0%"])
    
    _autosize_columns(ws)
    _bold_header(ws)


def _populate_division_totals_sheet(
    wb: Workbook,
    bid_proposal: dict[str, Any],
) -> None:
    """Add division/subtotal breakdown for contractor review."""
    
    ws = wb.create_sheet(title="Division Totals")
    ws.append(["Division", "Subtotal", "Line Items Count"])
    ws.freeze_panes = "A2"
    
    summary = bid_proposal.get("summary", {})
    cost_by_division = summary.get("cost_by_division", {}) or {}
    
    # Sort by division number if possible
    def sort_key(div: str) -> tuple:
        # Extract division number (e.g., "01 General Requirements" -> (1, "General Requirements"))
        parts = div.split(" ", 1)
        try:
            num = int(parts[0])
            return (num, parts[1] if len(parts) > 1 else "")
        except (ValueError, IndexError):
            return (999, div)
    
    sorted_divisions = sorted(cost_by_division.items(), key=lambda x: sort_key(x[0]))
    
    for division, subtotal in sorted_divisions:
        # Count line items in this division
        line_items = bid_proposal.get("line_items", [])
        count = sum(1 for item in line_items if item.get("division") == division)
        ws.append([division, _format_currency(subtotal), count])
    
    # Add total row
    total_cost = summary.get("total_cost", 0) or 0
    total_items = len(bid_proposal.get("line_items", []))
    ws.append([])
    ws.append(["TOTAL", _format_currency(total_cost), total_items])
    
    _autosize_columns(ws)
    _bold_header(ws)
