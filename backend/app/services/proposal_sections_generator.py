"""Service for generating contractor-style proposal sections (Phase 10.9A).

This is a deterministic rendering layer that organizes bid proposal data
into contractor-style sections without changing the underlying bid_proposal.json schema.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal, BidLineItem
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.evidence_index import EvidenceIndex, EvidenceReference
from app.schemas.extraction_result import ExtractionResult
from app.schemas.detail_graph import DetailGraph
from app.schemas.proposal_sections import (
    ProposalSections,
    ExecutiveSummary,
    ScopeSection,
    LogisticsSection,
    PermitsInspectionsSection,
    PaymentSchedule,
    ProjectSchedule,
)
from app.schemas.trade_assemblies import TradeAssembliesResult
from app.schemas.general_conditions import GeneralConditions
from app.schemas.labor_breakdown import LaborBreakdown


def generate_proposal_sections(
    project_id: str, output_dir: Path, settings: Settings
) -> ProposalSections:
    """
    Generate proposal sections for a project.

    Args:
        project_id: Project ID
        output_dir: Output directory for project artifacts
        settings: Application settings

    Returns:
        ProposalSections object
    """
    log_ctx = logger.bind(project_id=project_id, service="proposal_sections_generator")
    log_ctx.info("Generating proposal sections")

    # Load artifacts (all optional but best-effort)
    bid_proposal: BidProposal | None = None
    document_analysis: DocumentAnalysis | None = None
    extraction_result: ExtractionResult | None = None
    evidence_index: EvidenceIndex | None = None
    detail_graph: DetailGraph | None = None

    try:
        with open(output_dir / "bid_proposal.json", "r") as f:
            bid_proposal = BidProposal.model_validate(json.load(f))
    except FileNotFoundError:
        log_ctx.warning("bid_proposal.json not found")
        raise
    except Exception as e:
        log_ctx.error(f"Failed to load bid_proposal.json: {e}")
        raise

    try:
        with open(output_dir / "document_analysis.json", "r") as f:
            document_analysis = DocumentAnalysis.model_validate(json.load(f))
    except Exception as e:
        log_ctx.debug(f"document_analysis.json not found or invalid: {e}")

    try:
        with open(output_dir / "extraction_result.json", "r") as f:
            extraction_result = ExtractionResult.model_validate(json.load(f))
            # Check if detail_graph is nested in extraction_result
            if extraction_result.detail_graph:
                detail_graph = extraction_result.detail_graph
    except Exception as e:
        log_ctx.debug(f"extraction_result.json not found or invalid: {e}")

    try:
        with open(output_dir / "evidence_index.json", "r") as f:
            evidence_index = EvidenceIndex.model_validate(json.load(f))
    except Exception as e:
        log_ctx.debug(f"evidence_index.json not found or invalid: {e}")

    # Try loading detail_graph standalone if not found in extraction_result
    if not detail_graph:
        try:
            with open(output_dir / "detail_graph.json", "r") as f:
                detail_graph = DetailGraph.model_validate(json.load(f))
        except Exception as e:
            log_ctx.debug(f"detail_graph.json not found or invalid: {e}")

    # Generate executive summary
    total_bid = bid_proposal.summary.total_cost
    project_overview = _generate_project_overview(document_analysis, extraction_result)
    scope_summary = _generate_scope_summary(bid_proposal, extraction_result)
    key_highlights = _extract_key_highlights(bid_proposal, document_analysis)

    executive_summary = ExecutiveSummary(
        project_overview=project_overview,
        total_bid_amount=total_bid,
        scope_summary=scope_summary,
        key_highlights=key_highlights,
    )

    # Phase 12.1: Load new artifacts for enhanced narratives
    trade_assemblies: TradeAssembliesResult | None = None
    general_conditions: GeneralConditions | None = None
    labor_breakdown: LaborBreakdown | None = None
    
    try:
        with open(output_dir / "trade_assemblies.json", "r") as f:
            trade_assemblies = TradeAssembliesResult.model_validate(json.load(f))
            log_ctx.debug("Loaded trade_assemblies.json for enhanced narratives")
    except Exception as e:
        log_ctx.debug(f"trade_assemblies.json not found or invalid: {e}")

    try:
        with open(output_dir / "general_conditions.json", "r") as f:
            general_conditions = GeneralConditions.model_validate(json.load(f))
            log_ctx.debug("Loaded general_conditions.json for enhanced narratives")
    except Exception as e:
        log_ctx.debug(f"general_conditions.json not found or invalid: {e}")

    try:
        with open(output_dir / "labor_breakdown.json", "r") as f:
            labor_breakdown = LaborBreakdown.model_validate(json.load(f))
            log_ctx.debug("Loaded labor_breakdown.json for enhanced narratives")
    except Exception as e:
        log_ctx.debug(f"labor_breakdown.json not found or invalid: {e}")

    # Map line items to sections
    section_mapping = _map_line_items_to_sections(
        bid_proposal.line_items, evidence_index, detail_graph
    )

    # Generate scope sections in deterministic order (Phase 12.1: enhanced with trade assemblies)
    scope_sections = _generate_scope_sections(
        section_mapping, bid_proposal, evidence_index, detail_graph, extraction_result, trade_assemblies
    )

    # Generate logistics section (Phase 12.1: enhanced with general conditions)
    logistics_section = _generate_logistics_section(
        bid_proposal, evidence_index, section_mapping, general_conditions
    )

    # Generate permits/inspections section (Phase 12.1: enhanced with general conditions)
    permits_section = _generate_permits_section(
        bid_proposal, evidence_index, section_mapping, general_conditions
    )

    # Default exclusions and assumptions
    exclusions = _get_default_exclusions()
    assumptions = _get_default_assumptions(document_analysis, extraction_result)

    # Payment schedule (template defaults)
    payment_schedule = PaymentSchedule(
        milestone_1="Mobilization & Material Delivery: 25%",
        milestone_2="Substantial Completion: 50%",
        milestone_3="Final Inspection: 20%",
        final_payment="Project Closeout: 5%",
    )

    # Project schedule (Phase 12.1: enhanced with labor breakdown)
    schedule = _generate_project_schedule(
        labor_breakdown, general_conditions, extraction_result
    )

    # Notes
    notes = _extract_notes(bid_proposal, extraction_result)

    log_ctx.info(
        f"Proposal sections generated: {len(scope_sections)} scope sections, "
        f"{len(exclusions)} exclusions, {len(assumptions)} assumptions"
    )

    return ProposalSections(
        project_id=project_id,
        executive_summary=executive_summary,
        scope_sections=scope_sections,
        logistics_section=logistics_section,
        permits_inspections_section=permits_section,
        exclusions=exclusions,
        assumptions=assumptions,
        payment_schedule=payment_schedule,
        schedule=schedule,
        notes=notes,
    )


def _generate_project_overview(
    document_analysis: DocumentAnalysis | None,
    extraction_result: ExtractionResult | None,
) -> str:
    """Generate project overview from available artifacts."""
    if document_analysis:
        project_type = (
            document_analysis.resolved_project_type or document_analysis.project_type
        )
        scope_type = (
            document_analysis.resolved_scope_type or document_analysis.scope_type
        )
        return f"{project_type.replace('_', ' ').title()} {scope_type.replace('_', ' ').title()} project"
    if extraction_result:
        return f"{extraction_result.project_type.replace('_', ' ').title()} {extraction_result.scope_type.replace('_', ' ').title()} project"
    return "Construction project"


def _generate_scope_summary(
    bid_proposal: BidProposal, extraction_result: ExtractionResult | None
) -> str:
    """Generate scope summary from bid proposal and extraction."""
    if extraction_result and extraction_result.scope_of_work:
        scope_items = [item.item for item in extraction_result.scope_of_work[:5]]
        if scope_items:
            return f"Scope includes: {', '.join(scope_items)}"
    
    # Fallback to top divisions
    divisions = list(bid_proposal.summary.cost_by_division.keys())[:3]
    if divisions:
        return f"Work includes {', '.join(divisions)}"
    
    return "Comprehensive construction work as detailed in bid proposal"


def _extract_key_highlights(
    bid_proposal: BidProposal, document_analysis: DocumentAnalysis | None
) -> list[str]:
    """Extract key highlights from bid proposal and analysis."""
    highlights: list[str] = []
    
    if bid_proposal.clarifications:
        for clar in bid_proposal.clarifications:
            if clar.severity == "critical":
                highlights.append(clar.text)
    
    if document_analysis and document_analysis.critical_expected_items:
        found_items = [
            item.item
            for item in document_analysis.critical_expected_items
            if item.found
        ]
        if found_items:
            highlights.append(f"Critical items identified: {', '.join(found_items)}")
    
    return highlights[:5]  # Limit to top 5


def _map_line_items_to_sections(
    line_items: list[BidLineItem],
    evidence_index: EvidenceIndex | None,
    detail_graph: DetailGraph | None,
) -> dict[str, list[int]]:
    """
    Map line items to section keys based on division + keywords.

    Returns:
        Dictionary mapping section_key to list of line item indices
    """
    mapping: dict[str, list[int]] = {
        "parapet": [],
        "lintels": [],
        "veneer": [],
        "repointing": [],
        "crack_repair": [],
        "flashing": [],
        "protection": [],
        "permits": [],
        "logistics": [],  # Temporary for logistics section
    }

    # Keywords for each section
    section_keywords = {
        "parapet": ["parapet", "cop"],
        "lintels": ["lintel", "steel angle", "header"],
        "veneer": ["veneer", "brick replacement", "masonry replacement", "rebuild"],
        "repointing": ["repoint", "tuckpoint", "pointing", "mortar"],
        "crack_repair": ["crack", "repair", "seal"],
        "flashing": ["flashing", "thru-wall", "waterproof"],
        "protection": ["protection", "safety", "netting", "barricade"],
        "permits": ["permit", "inspection", "code"],
        "logistics": ["scaffold", "equipment", "dumpster", "access", "protection"],
    }

    for idx, item in enumerate(line_items):
        description_lower = item.description.lower()
        division_lower = item.division.lower()

        # Match by keywords - check more specific sections first
        # Order matters: check lintels before veneer (since "brick lintel" should match lintels)
        matched = False
        
        # Priority order for matching (more specific first)
        priority_order = [
            "lintels",  # Check lintels before veneer
            "parapet",
            "flashing",
            "repointing",
            "crack_repair",
            "veneer",  # Veneer comes after lintels
            "logistics",  # Logistics before protection (scaffold is logistics, not protection)
            "protection",
            "permits",
        ]
        
        for section_key in priority_order:
            keywords = section_keywords.get(section_key, [])
            if any(kw in description_lower or kw in division_lower for kw in keywords):
                mapping[section_key].append(idx)
                matched = True
                break

        # Default to veneer if masonry division and not matched
        if not matched and "masonry" in division_lower:
            mapping["veneer"].append(idx)
        # Default to logistics if general conditions division
        elif not matched and ("general conditions" in division_lower or "01" in item.division):
            mapping["logistics"].append(idx)

    return mapping


def _generate_scope_sections(
    section_mapping: dict[str, list[int]],
    bid_proposal: BidProposal,
    evidence_index: EvidenceIndex | None,
    detail_graph: DetailGraph | None,
    extraction_result: ExtractionResult | None,
    trade_assemblies: TradeAssembliesResult | None = None,
) -> list[ScopeSection]:
    """Generate scope sections in deterministic order."""
    sections: list[ScopeSection] = []

    # Deterministic section order
    section_order = [
        "parapet",
        "lintels",
        "veneer",
        "repointing",
        "crack_repair",
        "flashing",
        "protection",
    ]

    for section_key in section_order:
        line_item_indices = section_mapping.get(section_key, [])
        if not line_item_indices:
            continue  # Skip empty sections

        # Collect line item IDs
        line_item_ids = [str(idx) for idx in line_item_indices]

        # Collect evidence refs
        evidence_refs: list[EvidenceReference] = []
        if evidence_index:
            for idx in line_item_indices:
                for bid_evidence in evidence_index.bid_item_evidence:
                    if bid_evidence.line_item_index == idx:
                        evidence_refs.extend(bid_evidence.evidence_references)

        # Collect detail refs
        detail_refs: list[str] = []
        if detail_graph:
            for idx in line_item_indices:
                item = bid_proposal.line_items[idx]
                # Match detail by keywords in description
                for detail in detail_graph.details:
                    desc_lower = item.description.lower()
                    if (
                        any(kw in desc_lower for kw in detail.detail_type.split("_"))
                        or any(mat in desc_lower for mat in detail.materials_referenced)
                    ):
                        if detail.detail_id not in detail_refs:
                            detail_refs.append(detail.detail_id)

        # Collect flags
        flags: list[str] = []
        for idx in line_item_indices:
            item = bid_proposal.line_items[idx]
            if item.quantity_source == "heuristic":
                flags.append("heuristic_quantity")
            if item.confidence < 0.7:
                flags.append("estimated")

        # Generate narrative (Phase 12.1: enhanced with trade assemblies)
        narrative = _generate_section_narrative(
            section_key, line_item_indices, bid_proposal, extraction_result, trade_assemblies
        )

        # Title
        title = _get_section_title(section_key)

        sections.append(
            ScopeSection(
                section_key=section_key,
                title=title,
                narrative=narrative,
                line_item_ids=line_item_ids,
                evidence_refs=evidence_refs,
                detail_refs=detail_refs,
                flags=flags,
            )
        )

    return sections


def _generate_section_narrative(
    section_key: str,
    line_item_indices: list[int],
    bid_proposal: BidProposal,
    extraction_result: ExtractionResult | None,
    trade_assemblies: TradeAssembliesResult | None = None,
) -> str:
    """
    Generate narrative for a section (Phase 12.1: enhanced with trade assemblies).
    
    Phase 12.1 enhancement: Uses trade assemblies for detailed material/labor breakdowns.
    """
    # Phase 12.1: Try to enhance narrative with trade assemblies first
    if trade_assemblies:
        # Find matching assembly for this section
        assembly_narrative = _get_assembly_narrative(section_key, line_item_indices, trade_assemblies)
        if assembly_narrative:
            return assembly_narrative
    
    # Try to find scope item descriptions from extraction result
    if extraction_result and extraction_result.scope_of_work:
        section_keywords_map = {
            "parapet": ["parapet", "cop"],
            "lintels": ["lintel"],
            "veneer": ["veneer", "brick", "replacement"],
            "repointing": ["repoint", "point"],
            "crack_repair": ["crack"],
            "flashing": ["flashing"],
            "protection": ["protection"],
        }
        
        keywords = section_keywords_map.get(section_key, [])
        matching_scope = [
            item.description
            for item in extraction_result.scope_of_work
            if any(kw in item.item.lower() or kw in item.description.lower() for kw in keywords)
        ]
        
        if matching_scope:
            return ". ".join(matching_scope[:2]) + "."

    # Fallback to template
    templates = {
        "parapet": "Parapet repair and rebuild work as detailed in bid proposal.",
        "lintels": "Lintel replacement and repair work as detailed in bid proposal.",
        "veneer": "Brick veneer and masonry work as detailed in bid proposal.",
        "repointing": "Repointing and mortar restoration work as detailed in bid proposal.",
        "crack_repair": "Crack repair and sealing work as detailed in bid proposal.",
        "flashing": "Flashing and waterproofing work as detailed in bid proposal.",
        "protection": "Site protection and safety measures as detailed in bid proposal.",
    }
    
    return templates.get(section_key, "Work as detailed in bid proposal.")


def _get_section_title(section_key: str) -> str:
    """Get title for a section key."""
    titles = {
        "parapet": "Parapet Repair and Rebuild",
        "lintels": "Lintel Replacement",
        "veneer": "Brick Veneer and Masonry Work",
        "repointing": "Repointing and Mortar Restoration",
        "crack_repair": "Crack Repair and Sealing",
        "flashing": "Flashing and Waterproofing",
        "protection": "Site Protection and Safety",
    }
    return titles.get(section_key, section_key.replace("_", " ").title())


def _get_assembly_narrative(
    section_key: str,
    line_item_indices: list[int],
    trade_assemblies: TradeAssembliesResult,
) -> str | None:
    """
    Generate enhanced narrative from trade assemblies (Phase 12.1).
    
    Returns None if no matching assembly found.
    """
    # Map section keys to assembly keywords
    section_to_keywords = {
        "parapet": ["parapet"],
        "lintels": ["lintel"],
        "veneer": ["brick", "veneer"],
        "repointing": ["repoint", "point"],
        "crack_repair": ["crack"],
        "flashing": ["flash"],
    }
    
    keywords = section_to_keywords.get(section_key, [])
    if not keywords:
        return None
    
    # Find matching assemblies
    matching_assemblies = []
    for assembly in trade_assemblies.assemblies:
        title_lower = assembly.title.lower()
        if any(kw in title_lower for kw in keywords):
            # Check if this assembly matches any of the line items
            for idx in line_item_indices:
                if str(idx) in assembly.related_bid_item_ids:
                    matching_assemblies.append(assembly)
                    break
    
    if not matching_assemblies:
        return None
    
    # Build narrative from first matching assembly
    assembly = matching_assemblies[0]
    narrative_parts = [assembly.title]
    
    # Add material components
    if assembly.components:
        materials = [comp.name for comp in assembly.components[:3]]  # Limit to 3
        if materials:
            narrative_parts.append(f"Materials: {', '.join(materials)}")
    
    # Add labor summary
    if assembly.labor:
        total_hours = sum(lab.hours for lab in assembly.labor)
        total_labor_cost = sum(lab.total_cost for lab in assembly.labor)
        if total_hours > 0:
            narrative_parts.append(f"Estimated labor: {total_hours:.1f} hours (${total_labor_cost:,.2f})")
    
    return ". ".join(narrative_parts) + "."


def _generate_project_schedule(
    labor_breakdown: LaborBreakdown | None,
    general_conditions: GeneralConditions | None,
    extraction_result: ExtractionResult | None,
) -> ProjectSchedule:
    """
    Generate project schedule (Phase 12.1: enhanced with labor breakdown).
    
    Phase 12.1 enhancement: Uses labor breakdown for estimated duration.
    """
    estimated_duration_weeks = None
    
    # Calculate duration from labor breakdown
    if labor_breakdown and labor_breakdown.activities:
        total_days = 0.0
        for activity in labor_breakdown.activities:
            if activity.estimated_days:
                total_days += activity.estimated_days
        
        if total_days > 0:
            # Add buffer for GC and contingencies (20%)
            total_days_with_buffer = total_days * 1.2
            estimated_duration_weeks = max(1, int(round(total_days_with_buffer / 5)))  # 5-day work week
    
    # Start conditions
    start_conditions = ["Contract execution"]
    if general_conditions:
        permit_items = [item for item in general_conditions.items if item.category == "permits"]
        if permit_items:
            start_conditions.append("Permit issuance")
    else:
        start_conditions.append("Permit issuance")
    
    # Critical path items (top labor activities by hours/days)
    critical_path_items: list[str] = []
    if labor_breakdown and labor_breakdown.activities:
        # Sort by estimated_days (descending)
        sorted_activities = sorted(
            [a for a in labor_breakdown.activities if a.estimated_days],
            key=lambda x: x.estimated_days or 0.0,
            reverse=True,
        )
        # Top 3 activities as critical path
        critical_path_items = [act.title for act in sorted_activities[:3]]
    
    return ProjectSchedule(
        estimated_duration_weeks=estimated_duration_weeks,
        start_conditions=start_conditions,
        critical_path_items=critical_path_items,
    )


def _generate_logistics_section(
    bid_proposal: BidProposal,
    evidence_index: EvidenceIndex | None,
    section_mapping: dict[str, list[int]],
) -> LogisticsSection:
    """Generate logistics section."""
    line_item_indices = section_mapping.get("logistics", [])
    line_item_ids = [str(idx) for idx in line_item_indices]

    evidence_refs: list[EvidenceReference] = []
    if evidence_index:
        for idx in line_item_indices:
            for bid_evidence in evidence_index.bid_item_evidence:
                if bid_evidence.line_item_index == idx:
                    evidence_refs.extend(bid_evidence.evidence_references)

    narrative = "Site protection, scaffolding, equipment, and logistics as detailed in bid proposal."

    return LogisticsSection(
        narrative=narrative,
        line_item_ids=line_item_ids,
        evidence_refs=evidence_refs,
    )


def _generate_permits_section(
    bid_proposal: BidProposal,
    evidence_index: EvidenceIndex | None,
    section_mapping: dict[str, list[int]],
    general_conditions: GeneralConditions | None = None,
) -> PermitsInspectionsSection:
    """
    Generate permits and inspections section (Phase 12.1: enhanced with general conditions).
    
    Phase 12.1 enhancement: Uses general conditions for detailed permits/inspections narrative.
    """
    line_item_indices = section_mapping.get("permits", [])
    line_item_ids = [str(idx) for idx in line_item_indices]

    evidence_refs: list[EvidenceReference] = []
    if evidence_index:
        for idx in line_item_indices:
            for bid_evidence in evidence_index.bid_item_evidence:
                if bid_evidence.line_item_index == idx:
                    evidence_refs.extend(bid_evidence.evidence_references)

    # Phase 12.1: Enhance narrative with general conditions
    if general_conditions:
        permit_items = [item for item in general_conditions.items if item.category == "permits"]
        inspection_items = [item for item in general_conditions.items if item.category == "inspections"]
        
        narrative_parts = []
        if permit_items:
            permit_total = sum(item.total_cost for item in permit_items)
            narrative_parts.append(f"Permits and filing fees: ${permit_total:,.2f}")
        if inspection_items:
            inspection_count = len(inspection_items)
            narrative_parts.append(f"{inspection_count} inspection(s) required")
        
        if narrative_parts:
            narrative = f"Permits, inspections, and regulatory compliance: {', '.join(narrative_parts)}."
        else:
            narrative = "Permits, inspections, and regulatory compliance as detailed in bid proposal."
    else:
        narrative = "Permits, inspections, and regulatory compliance as detailed in bid proposal."

    return PermitsInspectionsSection(
        narrative=narrative,
        line_item_ids=line_item_ids,
        evidence_refs=evidence_refs,
    )


def _get_default_exclusions() -> list[str]:
    """Get default exclusions."""
    return [
        "Owner-furnished materials unless specifically noted",
        "Site preparation and excavation beyond scope",
        "Structural modifications beyond scope",
        "Interior work unless specifically included",
        "Landscaping and site restoration",
        "Architectural and engineering fees",
        "Sales tax unless specifically noted",
    ]


def _get_default_assumptions(
    document_analysis: DocumentAnalysis | None,
    extraction_result: ExtractionResult | None,
) -> list[str]:
    """Get default assumptions."""
    assumptions = [
        "Work will be performed during normal business hours",
        "Site access is available as needed",
        "Existing conditions are as shown in drawings",
        "Materials are available and meet specifications",
        "Weather conditions permit work as scheduled",
    ]
    
    # Add project-specific assumptions if available
    if extraction_result and extraction_result.evidence_missing:
        for missing in extraction_result.evidence_missing[:3]:
            assumptions.append(f"Assumption made due to missing evidence: {missing}")
    
    return assumptions


def _extract_notes(
    bid_proposal: BidProposal, extraction_result: ExtractionResult | None
) -> list[str]:
    """Extract notes from bid proposal and coverage data."""
    notes: list[str] = []

    if bid_proposal.clarifications:
        for clar in bid_proposal.clarifications:
            if clar.severity != "critical":  # Critical items go to highlights
                notes.append(clar.text)

    if extraction_result and extraction_result.warranty_and_insurance:
        coverage = extraction_result.warranty_and_insurance

        warranty_parts: list[str] = []
        if coverage.warranty.manufacturer_warranty:
            warranty_parts.append(coverage.warranty.manufacturer_warranty)
        if coverage.warranty.workmanship_warranty:
            warranty_parts.append(coverage.warranty.workmanship_warranty)
        if warranty_parts:
            notes.append("Warranty provisions: " + "; ".join(warranty_parts))

        insurance = coverage.insurance
        insurance_parts: list[str] = []
        if insurance.general_liability_required or insurance.general_liability_limit:
            liability_text = "general liability"
            if insurance.general_liability_limit:
                liability_text += f" ({insurance.general_liability_limit})"
            insurance_parts.append(liability_text)
        if insurance.workers_compensation_required or insurance.workers_compensation_limit:
            wc_text = "workers compensation"
            if insurance.workers_compensation_limit:
                wc_text += f" ({insurance.workers_compensation_limit})"
            insurance_parts.append(wc_text)
        if insurance.umbrella_insurance_required or insurance.umbrella_insurance_limit:
            umbrella_text = "umbrella coverage"
            if insurance.umbrella_insurance_limit:
                umbrella_text += f" ({insurance.umbrella_insurance_limit})"
            insurance_parts.append(umbrella_text)
        if insurance_parts:
            notes.append("Insurance requirements: " + ", ".join(insurance_parts))

        bonds = coverage.bonds
        bond_parts: list[str] = []
        if bonds.performance_bond_required:
            perf_text = "performance bond"
            if bonds.performance_bond_amount:
                perf_text += f" ({bonds.performance_bond_amount})"
            bond_parts.append(perf_text)
        if bonds.payment_bond_required:
            pay_text = "payment bond"
            if bonds.payment_bond_amount:
                pay_text += f" ({bonds.payment_bond_amount})"
            bond_parts.append(pay_text)
        if bond_parts:
            notes.append("Bond requirements: " + ", ".join(bond_parts))

    return notes
