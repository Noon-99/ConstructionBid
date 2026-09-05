"""Trade package generator service (Phase 11.0).

Generates trade-specific bid packages for subcontractor distribution.
This is a non-destructive export layer - does not modify existing artifacts.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidProposal, BidLineItem
from app.schemas.proposal_sections import ProposalSections, ScopeSection
from app.schemas.evidence_index import EvidenceIndex, BidItemEvidence, EvidenceReference
from app.schemas.detail_graph import DetailGraph
from app.schemas.trade_package import (
    TradePackagesExport,
    TradePackage,
    TradeLineItem,
)


def generate_trade_packages(
    project_id: str,
    output_dir: Path,
    settings: Settings,
    bid_proposal: BidProposal | None = None,
    proposal_sections: ProposalSections | None = None,
    evidence_index: EvidenceIndex | None = None,
    detail_graph: DetailGraph | None = None,
    pricing_profile: dict[str, Any] | None = None,
) -> TradePackagesExport:
    """
    Generate trade packages from bid proposal (Phase 11.0).

    Args:
        project_id: Project ID
        output_dir: Output directory for project artifacts
        settings: Application settings
        bid_proposal: Bid proposal artifact (optional, will load if not provided)
        proposal_sections: Proposal sections artifact (optional, will load if not provided)
        evidence_index: Evidence index artifact (optional, will load if not provided)
        detail_graph: Detail graph artifact (optional, will load if not provided)
        pricing_profile: Pricing profile artifact (optional, for profile_id)

    Returns:
        TradePackagesExport with all trade packages
    """
    log_ctx = logger.bind(project_id=project_id, service="trade_package_generator")
    log_ctx.info("Generating trade packages")

    # Load artifacts if not provided
    if bid_proposal is None:
        try:
            # Try bid_proposal_v2 first, fallback to bid_proposal
            v2_file = output_dir / "bid_proposal_v2.json"
            if v2_file.exists():
                with open(v2_file, "r") as f:
                    bid_proposal = BidProposal.model_validate(json.load(f))
                log_ctx.debug("Loaded bid_proposal_v2.json")
            else:
                with open(output_dir / "bid_proposal.json", "r") as f:
                    bid_proposal = BidProposal.model_validate(json.load(f))
                log_ctx.debug("Loaded bid_proposal.json")
        except FileNotFoundError:
            raise ValueError("bid_proposal.json or bid_proposal_v2.json must exist")
        except Exception as e:
            raise ValueError(f"Failed to load bid_proposal: {e}")

    if proposal_sections is None:
        try:
            with open(output_dir / "proposal_sections.json", "r") as f:
                proposal_sections = ProposalSections.model_validate(json.load(f))
        except FileNotFoundError:
            log_ctx.warning("proposal_sections.json not found, trade packages may be incomplete")
        except Exception as e:
            log_ctx.warning(f"Failed to load proposal_sections.json: {e}")

    if evidence_index is None:
        try:
            with open(output_dir / "evidence_index.json", "r") as f:
                evidence_index = EvidenceIndex.model_validate(json.load(f))
        except FileNotFoundError:
            log_ctx.debug("evidence_index.json not found")
        except Exception as e:
            log_ctx.warning(f"Failed to load evidence_index.json: {e}")

    if detail_graph is None:
        try:
            with open(output_dir / "detail_graph.json", "r") as f:
                detail_graph = DetailGraph.model_validate(json.load(f))
        except FileNotFoundError:
            log_ctx.debug("detail_graph.json not found")
        except Exception as e:
            log_ctx.warning(f"Failed to load detail_graph.json: {e}")

    if pricing_profile is None:
        try:
            with open(output_dir / "pricing_profile.json", "r") as f:
                pricing_profile = json.load(f)
        except FileNotFoundError:
            log_ctx.debug("pricing_profile.json not found")
        except Exception as e:
            log_ctx.warning(f"Failed to load pricing_profile.json: {e}")

    profile_id = pricing_profile.get("profile_id") if pricing_profile else None

    # Validate bid_proposal if it's a dict
    if isinstance(bid_proposal, dict):
        from app.schemas.bid_proposal import BidProposal
        bid_proposal = BidProposal.model_validate(bid_proposal)

    # Map line items to trades
    trade_mapping = _map_line_items_to_trades(bid_proposal, proposal_sections)

    # Generate trade packages
    packages: list[TradePackage] = []
    for trade_id, line_item_indices in trade_mapping.items():
        if not line_item_indices:
            continue  # Skip empty trades

        package = _generate_trade_package(
            trade_id=trade_id,
            line_item_indices=line_item_indices,
            bid_proposal=bid_proposal,
            proposal_sections=proposal_sections,
            evidence_index=evidence_index,
            detail_graph=detail_graph,
        )
        packages.append(package)

    # Sort packages by total cost (descending)
    packages.sort(key=lambda p: p.total_cost, reverse=True)

    from datetime import datetime

    export = TradePackagesExport(
        project_id=project_id,
        profile_id=profile_id,
        generated_at=datetime.now(),
        packages=packages,
    )

    log_ctx.info(
        f"Generated {len(packages)} trade packages: "
        f"{', '.join([f'{p.trade_name} (${p.total_cost:,.0f})' for p in packages])}"
    )

    return export


def _map_line_items_to_trades(
    bid_proposal: BidProposal,
    proposal_sections: ProposalSections | None,
) -> dict[str, list[int]]:
    """
    Map bid line items to trades using deterministic rules (Phase 11.0).

    Returns:
        Dictionary mapping trade_id to list of line_item indices
    """
    mapping: dict[str, list[int]] = {
        "masonry": [],
        "metals": [],
        "waterproofing": [],
        "general_conditions": [],
        "permits": [],
        "other": [],
    }

    # Trade keywords mapping (deterministic rules)
    trade_keywords: dict[str, list[str]] = {
        "masonry": [
            "parapet",
            "brick",
            "veneer",
            "repoint",
            "tuckpoint",
            "mortar",
            "cmu",
            "masonry",
            "crack repair",
        ],
        "metals": [
            "lintel",
            "steel",
            "angle",
            "anchor",
            "structural steel",
            "hss",
            "beam",
            "channel",
            "galvanized",
        ],
        "waterproofing": [
            "flashing",
            "membrane",
            "waterproofing",
            "thru-wall",
            "sealant",
            "waterproof",
        ],
        "general_conditions": [
            "scaffold",
            "dumpster",
            "protection",
            "safety",
            "containment",
            "debris netting",
            "mobilization",
            "demobilization",
            "site logistics",
            "equipment rental",
        ],
        "permits": [
            "permit",
            "inspection",
            "filing",
            "controlled inspection",
            "regulatory",
        ],
    }

    # Also use proposal_sections mapping if available
    section_to_trade: dict[str, str] = {
        "parapet": "masonry",
        "lintels": "metals",
        "veneer": "masonry",
        "repointing": "masonry",
        "crack_repair": "masonry",
        "flashing": "waterproofing",
        "protection": "general_conditions",
        "logistics": "general_conditions",
        "permits": "permits",
    }

    for idx, line_item in enumerate(bid_proposal.line_items):
        description_lower = line_item.description.lower()
        division_lower = line_item.division.lower()
        assigned = False

        # Rule 1: Check by keywords in description
        for trade_id, keywords in trade_keywords.items():
            if any(kw in description_lower for kw in keywords):
                mapping[trade_id].append(idx)
                assigned = True
                break

        if assigned:
            continue

        # Rule 2: Check by CSI division
        if "04 masonry" in division_lower or "masonry" in division_lower:
            mapping["masonry"].append(idx)
            assigned = True
        elif "05 metals" in division_lower or "metals" in division_lower:
            mapping["metals"].append(idx)
            assigned = True
        elif "07 thermal" in division_lower or "waterproofing" in division_lower:
            mapping["waterproofing"].append(idx)
            assigned = True
        elif "01 general requirements" in division_lower:
            # Check if permits or logistics
            if "permit" in description_lower or "inspection" in description_lower:
                mapping["permits"].append(idx)
            elif (
                "scaffold" in description_lower
                or "dumpster" in description_lower
                or "protection" in description_lower
                or "mobilization" in description_lower
            ):
                mapping["general_conditions"].append(idx)
            else:
                mapping["general_conditions"].append(idx)
            assigned = True

        # Rule 3: Use proposal_sections mapping if available
        if not assigned and proposal_sections:
            for section in proposal_sections.scope_sections:
                if str(idx) in section.line_item_ids:
                    trade_id = section_to_trade.get(section.section_key)
                    if trade_id and trade_id in mapping:
                        mapping[trade_id].append(idx)
                        assigned = True
                        break

        # Rule 4: Check logistics and permits sections
        if not assigned and proposal_sections:
            if str(idx) in proposal_sections.logistics_section.line_item_ids:
                mapping["general_conditions"].append(idx)
                assigned = True
            elif str(idx) in proposal_sections.permits_inspections_section.line_item_ids:
                mapping["permits"].append(idx)
                assigned = True

        # Fallback to "other" if not assigned
        if not assigned:
            mapping["other"].append(idx)

    return mapping


def _generate_trade_package(
    trade_id: str,
    line_item_indices: list[int],
    bid_proposal: BidProposal,
    proposal_sections: ProposalSections | None,
    evidence_index: EvidenceIndex | None,
    detail_graph: DetailGraph | None,
) -> TradePackage:
    """Generate a single trade package."""
    # Trade metadata
    trade_config = {
        "masonry": {
            "name": "Masonry",
            "divisions": ["04 Masonry"],
            "inclusions_template": [
                "All masonry work as specified in drawings",
                "Brick and mortar materials per specifications",
                "Scaffolding access for masonry work (coordinate with GC)",
            ],
            "exclusions_template": [
                "Structural steel lintels (separate trade)",
                "Flashing installation (separate trade)",
                "Site protection and debris removal (GC scope)",
            ],
            "assumptions_template": [
                "Standard working hours (7 AM - 3 PM)",
                "Access to site provided by GC",
                "Weather delays beyond contractor control",
            ],
        },
        "metals": {
            "name": "Metals & Structural Steel",
            "divisions": ["05 Metals"],
            "inclusions_template": [
                "All structural steel and metal work per drawings",
                "Steel lintel installation and anchoring",
                "Galvanized finish per specifications",
            ],
            "exclusions_template": [
                "Masonry work around lintels (separate trade)",
                "Welding certifications and inspections (coordinate with GC)",
                "Crane and hoisting equipment (provided by GC)",
            ],
            "assumptions_template": [
                "Steel delivered to site by GC or material supplier",
                "Existing conditions verified by field survey",
                "Access and staging area provided by GC",
            ],
        },
        "waterproofing": {
            "name": "Waterproofing & Flashing",
            "divisions": ["07 Thermal and Moisture Protection"],
            "inclusions_template": [
                "All flashing installation per details",
                "Thru-wall flashing systems",
                "Membrane waterproofing as specified",
            ],
            "exclusions_template": [
                "Substrate preparation (separate trade)",
                "Surface preparation and cleaning (separate trade)",
                "Testing and inspection coordination (GC scope)",
            ],
            "assumptions_template": [
                "Substrate prepared and ready for installation",
                "Weather conditions suitable for installation",
                "Sequencing coordinated with masonry and other trades",
            ],
        },
        "general_conditions": {
            "name": "General Conditions",
            "divisions": ["01 General Requirements"],
            "inclusions_template": [
                "Scaffold erection and dismantling",
                "Site protection and safety measures",
                "Debris removal and site cleanup",
                "Mobilization and demobilization",
            ],
            "exclusions_template": [
                "Temporary utilities (GC scope)",
                "Site security (GC scope)",
                "Permits and regulatory filings (separate trade)",
            ],
            "assumptions_template": [
                "Standard construction hours",
                "Site access provided by owner/GC",
                "Weather delays beyond contractor control",
            ],
        },
        "permits": {
            "name": "Permits & Inspections",
            "divisions": ["01 General Requirements"],
            "inclusions_template": [
                "Building permit filing and fees",
                "Required inspections coordination",
                "Controlled inspections as required",
            ],
            "exclusions_template": [
                "Architectural/engineering review fees",
                "Third-party inspection services",
                "Violation remediation",
            ],
            "assumptions_template": [
                "Standard permit processing times",
                "All required documentation provided by GC",
                "Municipal inspection availability",
            ],
        },
        "other": {
            "name": "Other Trades",
            "divisions": [],
            "inclusions_template": ["Work items not assigned to other trades"],
            "exclusions_template": [],
            "assumptions_template": [],
        },
    }

    config = trade_config.get(trade_id, trade_config["other"])

    # Collect line items for this trade
    trade_line_items: list[TradeLineItem] = []
    all_evidence_refs: list[EvidenceReference] = []
    all_detail_refs: list[str] = []
    divisions_included: set[str] = set()

    for idx in line_item_indices:
        if idx >= len(bid_proposal.line_items):
            continue

        line_item = bid_proposal.line_items[idx]
        divisions_included.add(line_item.division)

        trade_line_item = TradeLineItem(
            line_item_index=idx,
            description=line_item.description,
            division=line_item.division,
            quantity=line_item.quantity,
            unit=line_item.unit,
            unit_cost=line_item.unit_cost,
            total_cost=line_item.total_cost,
            basis=line_item.basis,
        )
        trade_line_items.append(trade_line_item)

        # Collect evidence references from evidence_index
        if evidence_index:
            for bid_evidence in evidence_index.bid_item_evidence:
                if bid_evidence.line_item_index == idx:
                    all_evidence_refs.extend(bid_evidence.evidence_references)

        # Collect detail references from proposal_sections
        if proposal_sections:
            for section in proposal_sections.scope_sections:
                if str(idx) in section.line_item_ids:
                    all_detail_refs.extend(section.detail_refs)

    # Remove duplicate evidence refs (same page + snippet)
    unique_evidence: dict[tuple[int, str], EvidenceReference] = {}
    for ref in all_evidence_refs:
        key = (ref.page_number, ref.evidence_snippet or "")
        if key not in unique_evidence:
            unique_evidence[key] = ref
    all_evidence_refs = list(unique_evidence.values())

    # Remove duplicate detail refs
    all_detail_refs = list(set(all_detail_refs))

    # Calculate total cost
    total_cost = sum(item.total_cost for item in trade_line_items)

    # Generate inclusions/exclusions/assumptions
    inclusions = config["inclusions_template"].copy()
    exclusions = config["exclusions_template"].copy()
    assumptions = config["assumptions_template"].copy()

    # Add trade-specific scope items from proposal_sections
    if proposal_sections:
        for section in proposal_sections.scope_sections:
            section_trade = _get_trade_for_section(section.section_key)
            if section_trade == trade_id and any(
                str(idx) in section.line_item_ids for idx in line_item_indices
            ):
                # Add section narrative as inclusion
                if section.narrative:
                    inclusions.append(f"{section.title}: {section.narrative}")

    # If no specific divisions, infer from line items
    if not config["divisions"]:
        divisions_included = set(item.division for item in trade_line_items)

    package = TradePackage(
        trade_id=trade_id,
        trade_name=config["name"],
        divisions=list(divisions_included),
        total_cost=total_cost,
        line_items=trade_line_items,
        inclusions=inclusions,
        exclusions=exclusions,
        assumptions=assumptions,
        evidence_refs=all_evidence_refs,
        detail_refs=all_detail_refs,
        generated_at=bid_proposal.generated_at,
    )

    return package


def _get_trade_for_section(section_key: str) -> str:
    """Map proposal section key to trade_id."""
    mapping: dict[str, str] = {
        "parapet": "masonry",
        "lintels": "metals",
        "veneer": "masonry",
        "repointing": "masonry",
        "crack_repair": "masonry",
        "flashing": "waterproofing",
        "protection": "general_conditions",
        "logistics": "general_conditions",
        "permits": "permits",
    }
    return mapping.get(section_key, "other")

