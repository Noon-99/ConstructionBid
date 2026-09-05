"""Proposal template engine (Phase 9.8).

Deterministically renders professional contractor proposal markdown from contractor bid data.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal
from app.schemas.contractor_bid import ContractorBid
from app.services.contractor_profile_store import load_profile


def _format_currency(amount: float | None) -> str:
    """Format currency amount."""
    if amount is None:
        return "—"
    return f"${amount:,.2f}"


def _format_percentage(value: float) -> str:
    """Format percentage."""
    return f"{value:.1f}%"


def _get_context_value(context: dict[str, Any], var_path: str) -> Any:
    """Get value from context by dot-separated path."""
    parts = var_path.split(".")
    value = context
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)] if int(part) < len(value) else None
        else:
            return None
        if value is None:
            return None
    return value


def _find_matching_close_tag(text: str, start_pos: int, open_tag: str, close_tag: str) -> int | None:
    """Find the matching close tag for an open tag, handling nesting."""
    depth = 1
    pos = start_pos + len(open_tag)
    open_pattern = re.escape(open_tag)
    close_pattern = re.escape(close_tag)
    
    while pos < len(text):
        # Find next open or close tag
        next_open_match = re.search(open_pattern, text[pos:])
        next_close_match = re.search(close_pattern, text[pos:])
        
        open_pos = next_open_match.start() + pos if next_open_match else len(text)
        close_pos = next_close_match.start() + pos if next_close_match else len(text)
        
        if close_pos < open_pos:
            # Found closing tag first
            depth -= 1
            if depth == 0:
                return close_pos + len(close_tag)
            pos = close_pos + len(close_tag)
        elif open_pos < len(text):
            # Found opening tag first
            depth += 1
            pos = open_pos + len(open_tag)
        else:
            break
    
    return None


def _render_template_section(template_content: str, context: dict[str, Any]) -> str:
    """
    Simple template rendering (Phase 9.8).
    
    Supports:
    - {{variable}} - simple variable substitution
    - {{#if variable}}...{{/if}} - conditional blocks
    - {{#each list}}...{{/each}} - iteration
    - {{#unless variable}}...{{/unless}} - negative conditionals
    
    Processes iteratively from innermost to outermost.
    """
    result = template_content
    max_passes = 20
    
    for pass_num in range(max_passes):
        prev_result = result
        
        # Process {{#each}} blocks (find innermost first by processing all, innermost will be processed last due to replacement)
        while True:
            each_match = re.search(r"\{\{#each\s+([^}]+)\}\}", result)
            if not each_match:
                break
            
            start_pos = each_match.start()
            var_path = each_match.group(1).strip()
            content_start = each_match.end()
            
            # Find matching {{/each}}
            end_pos = _find_matching_close_tag(result, start_pos, each_match.group(0), "{{/each}}")
            if not end_pos:
                break
            
            block_content = result[content_start:end_pos - len("{{/each}}")]
            
            # Get list value
            value = _get_context_value(context, var_path)
            
            if isinstance(value, list) and len(value) > 0:
                rendered_items = []
                for item in value:
                    # Create item context - exclude the current list to prevent infinite recursion
                    if isinstance(item, dict):
                        filtered_context = {k: v for k, v in context.items() if k != var_path}
                        item_context = {**filtered_context, **item}
                    else:
                        filtered_context = {k: v for k, v in context.items() if k != var_path}
                        item_context = {**filtered_context, "this": item}
                    
                    # Recursively process nested template syntax
                    item_text = _render_template_section(block_content, item_context)
                    rendered_items.append(item_text)
                
                result = result[:start_pos] + "".join(rendered_items) + result[end_pos:]
            else:
                # Remove empty block
                result = result[:start_pos] + result[end_pos:]
        
        # Process {{#if}} blocks
        while True:
            if_match = re.search(r"\{\{#if\s+([^}]+)\}\}", result)
            if not if_match:
                break
            
            start_pos = if_match.start()
            var_path = if_match.group(1).strip()
            content_start = if_match.end()
            
            # Find matching {{/if}}
            end_pos = _find_matching_close_tag(result, start_pos, if_match.group(0), "{{/if}}")
            if not end_pos:
                break
            
            block_content = result[content_start:end_pos - len("{{/if}}")]
            
            # Get value
            value = _get_context_value(context, var_path)
            
            if value and (not isinstance(value, (list, dict)) or len(value) > 0):
                # Recursively process nested template syntax
                processed_content = _render_template_section(block_content, context)
                result = result[:start_pos] + processed_content + result[end_pos:]
            else:
                result = result[:start_pos] + result[end_pos:]
        
        # Process {{#unless}} blocks
        while True:
            unless_match = re.search(r"\{\{#unless\s+([^}]+)\}\}", result)
            if not unless_match:
                break
            
            start_pos = unless_match.start()
            var_path = unless_match.group(1).strip()
            content_start = unless_match.end()
            
            # Find matching {{/unless}}
            end_pos = _find_matching_close_tag(result, start_pos, unless_match.group(0), "{{/unless}}")
            if not end_pos:
                break
            
            block_content = result[content_start:end_pos - len("{{/unless}}")]
            
            # Get value
            value = _get_context_value(context, var_path)
            
            if not value or (isinstance(value, (list, dict)) and len(value) == 0):
                # Recursively process nested template syntax
                processed_content = _render_template_section(block_content, context)
                result = result[:start_pos] + processed_content + result[end_pos:]
            else:
                result = result[:start_pos] + result[end_pos:]
        
        # Replace simple variables
        def replace_var(match):
            var_path = match.group(1).strip()
            value = _get_context_value(context, var_path)
            return str(value) if value is not None else ""
        
        result = re.sub(r"\{\{([^#/]+?)\}\}", replace_var, result)
        
        # Stop if no changes
        if result == prev_result:
            break
    
    return result


def render_contractor_proposal_markdown(
    project_id: str, output_dir: Path, settings: Settings
) -> str:
    """
    Render contractor proposal markdown from contractor bid or conceptual bid (Phase 9.8).

    Args:
        project_id: Project ID
        output_dir: Output directory for artifacts
        settings: Application settings

    Returns:
        Rendered markdown string
    """
    log_ctx = logger.bind(project_id=project_id, service="proposal_template_engine")
    log_ctx.info("Rendering contractor proposal markdown")

    # Load contractor_bid.json (preferred) or bid_proposal.json (fallback)
    contractor_bid = None
    bid_proposal = None
    contractor_profile = None
    region_resolution = None
    document_analysis = None

    # Try contractor_bid first
    contractor_bid_file = output_dir / "contractor_bid.json"
    if contractor_bid_file.exists():
        with open(contractor_bid_file, "r") as f:
            contractor_bid_data = json.load(f)
        contractor_bid = ContractorBid.model_validate(contractor_bid_data)
        log_ctx.info("Loaded contractor_bid.json")
        
        # Extract region_resolution from contractor_bid
        if contractor_bid.region_resolution:
            region_resolution = contractor_bid.region_resolution.model_dump()
        
        # Load contractor profile (if profile_id is available from expanded_scope or labor_breakdown)
        try:
            expanded_scope_file = output_dir / "expanded_scope.json"
            if expanded_scope_file.exists():
                with open(expanded_scope_file, "r") as f:
                    expanded_scope_data = json.load(f)
                profile_id = expanded_scope_data.get("profile_id")
                if profile_id:
                    contractor_profile = load_profile(profile_id, settings)
        except:
            pass
    else:
        # Fallback to bid_proposal
        bid_proposal_file = output_dir / "bid_proposal.json"
        if bid_proposal_file.exists():
            with open(bid_proposal_file, "r") as f:
                bid_proposal_data = json.load(f)
            bid_proposal = BidProposal.model_validate(bid_proposal_data)
            log_ctx.info("Loaded bid_proposal.json (fallback)")
        else:
            raise FileNotFoundError(
                f"Neither contractor_bid.json nor bid_proposal.json found for project {project_id}"
            )

    # Load document_analysis for project name/address
    analysis_file = output_dir / "document_analysis.json"
    if analysis_file.exists():
        with open(analysis_file, "r") as f:
            document_analysis = json.load(f)

    # Build context for template rendering
    context: dict[str, Any] = {}

    if contractor_bid:
        # Use contractor_bid data
        context.update({
            "project_id": contractor_bid.project_id,
            "total_bid": contractor_bid.total_bid,
            "total_bid_formatted": _format_currency(contractor_bid.total_bid),
            "subtotals": {
                k: {"value": v, "formatted": _format_currency(v)}
                for k, v in contractor_bid.subtotals.items()
            },
            "sections": [
                {
                    "title": section.title,
                    "division": section.division,
                    "subtotal": section.subtotal,
                    "subtotal_formatted": _format_currency(section.subtotal),
                    "line_items": [
                        {
                            "title": item.title,
                            "quantity": item.quantity,
                            "quantity_display": f"{item.quantity:,.2f}" if item.quantity is not None else "—",
                            "unit": item.unit,
                            "unit_display": item.unit or "—",
                            "unit_cost": item.unit_cost,
                            "unit_cost_display": _format_currency(item.unit_cost),
                            "total_cost": item.total_cost,
                            "total_cost_formatted": _format_currency(item.total_cost),
                            "notes": item.notes,
                        }
                        for item in section.line_items
                    ],
                }
                for section in contractor_bid.sections
            ],
            "logistics": [
                {
                    "title": item.title,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "total_cost": item.total_cost,
                    "total_cost_formatted": _format_currency(item.total_cost),
                    "basis": item.basis,
                    "notes": item.notes,
                }
                for item in contractor_bid.logistics
            ],
            "permits_and_inspections": [
                {
                    "title": item.title,
                    "total_cost": item.total_cost,
                    "total_cost_formatted": _format_currency(item.total_cost),
                    "basis": item.basis,
                    "notes": item.notes,
                }
                for item in contractor_bid.permits_and_inspections
            ],
            "exclusions": contractor_bid.exclusions,
            "assumptions": contractor_bid.assumptions,
            "payment_schedule": [
                {
                    "title": milestone.title,
                    "percentage": milestone.percentage,
                    "percentage_formatted": _format_percentage(milestone.percentage),
                    "amount": milestone.amount,
                    "amount_formatted": _format_currency(milestone.amount),
                    "trigger": milestone.trigger,
                }
                for milestone in (contractor_bid.payment_schedule or [])
            ],
            "schedule": contractor_bid.schedule.model_dump() if contractor_bid.schedule else None,
        })
    elif bid_proposal:
        # Use bid_proposal data (fallback)
        context.update({
            "project_id": bid_proposal.project_id,
            "total_bid": bid_proposal.summary.total_cost,
            "total_bid_formatted": _format_currency(bid_proposal.summary.total_cost),
            "subtotals": {
                k: {"value": v, "formatted": _format_currency(v)}
                for k, v in bid_proposal.summary.cost_by_division.items()
            },
            "sections": [
                {
                    "title": f"{division}",
                    "division": division,
                    "subtotal": bid_proposal.summary.cost_by_division.get(division, 0),
                    "subtotal_formatted": _format_currency(bid_proposal.summary.cost_by_division.get(division, 0)),
                    "line_items": [
                        {
                            "title": item.description,
                            "quantity": item.quantity,
                            "quantity_display": f"{item.quantity:,.2f}" if item.quantity is not None else "—",
                            "unit": item.unit,
                            "unit_display": item.unit or "—",
                            "unit_cost": item.unit_cost,
                            "unit_cost_display": _format_currency(item.unit_cost),
                            "total_cost": item.total_cost,
                            "total_cost_formatted": _format_currency(item.total_cost),
                            "notes": None,
                        }
                        for item in bid_proposal.line_items
                        if item.division == division
                    ],
                }
                for division in set(item.division for item in bid_proposal.line_items)
            ],
            "logistics": [],
            "permits_and_inspections": [],
            "exclusions": [],
            "assumptions": [],
            "payment_schedule": None,
            "schedule": None,
            "clarifications": [
                {
                    "severity": clar.severity,
                    "text": clar.text,
                }
                for clar in bid_proposal.clarifications
            ],
        })

    # Add project metadata
    project_name = (
        document_analysis.get("project_name")
        if document_analysis
        else "Project Name Not Available"
    )
    project_address = (
        document_analysis.get("project_address")
        or document_analysis.get("project_location")
        if document_analysis
        else "Address not available"
    )

    context.update({
        "project_name": project_name,
        "project_address": project_address,
        "generated_date": datetime.now().strftime("%B %d, %Y"),
    })

    # Add region resolution if available
    if region_resolution:
        context["region_resolution"] = {
            **region_resolution,
            "confidence_percent": int(region_resolution.get("confidence", 0) * 100),
        }

    # Calculate estimated duration from labor breakdown if available
    labor_file = output_dir / "labor_breakdown.json"
    estimated_duration_weeks = None
    if labor_file.exists():
        try:
            with open(labor_file, "r") as f:
                labor_data = json.load(f)
            total_days = sum(
                act.get("estimated_days", 0) or 0
                for act in labor_data.get("activities", [])
            )
            if total_days > 0:
                estimated_duration_weeks = max(1, int(total_days / 5))  # 5-day work week
        except:
            pass

    if estimated_duration_weeks:
        context["estimated_duration"] = f"{estimated_duration_weeks} weeks"
        context["estimated_duration_weeks"] = estimated_duration_weeks

    if context.get("schedule") and context["schedule"].get("estimated_duration_days"):
        days = context["schedule"]["estimated_duration_days"]
        context["schedule"]["estimated_duration_weeks"] = max(1, int(days / 5))

    # Load and render template sections
    templates_dir = Path(__file__).parent.parent / "templates" / "proposal"
    
    sections: list[str] = []
    
    # Executive Summary
    exec_summary_template = (templates_dir / "executive_summary.md").read_text()
    sections.append(_render_template_section(exec_summary_template, context))
    
    # Scope Section
    scope_template = (templates_dir / "scope_section.md").read_text()
    sections.append(_render_template_section(scope_template, context))
    
    # Logistics
    if context.get("logistics"):
        logistics_template = (templates_dir / "logistics.md").read_text()
        sections.append(_render_template_section(logistics_template, context))
    
    # Permits & Inspections
    if context.get("permits_and_inspections"):
        permits_template = (templates_dir / "permits_inspections.md").read_text()
        sections.append(_render_template_section(permits_template, context))
    
    # Payment Schedule
    if context.get("payment_schedule"):
        payment_template = (templates_dir / "payment_schedule.md").read_text()
        sections.append(_render_template_section(payment_template, context))
    
    # Project Schedule
    schedule_template = (templates_dir / "project_schedule.md").read_text()
    sections.append(_render_template_section(schedule_template, context))
    
    # Exclusions
    exclusions_template = (templates_dir / "exclusions.md").read_text()
    sections.append(_render_template_section(exclusions_template, context))
    
    # Assumptions
    assumptions_template = (templates_dir / "assumptions.md").read_text()
    sections.append(_render_template_section(assumptions_template, context))
    
    # Combine all sections
    markdown = "\n\n---\n\n".join(sections)
    
    log_ctx.info(f"Rendered proposal markdown ({len(markdown)} characters)")
    
    return markdown
