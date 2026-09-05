"""Work package normalizer (Phase 9.9).

Groups bid items into contractor-friendly sections based on keyword matching.
"""

import re
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.bid_proposal import BidLineItem
from app.schemas.contractor_bid import ContractorBid, ContractorBidLineItem
from app.schemas.work_packages import WorkPackage


# Keyword mapping: package_title -> list of keywords
PACKAGE_KEYWORDS: dict[str, list[str]] = {
    "Parapet Reconstruction": [
        "parapet",
        "coping",
        "roof edge",
        "roof edge repair",
        "parapet rebuild",
        "parapet reconstruction",
    ],
    "Lintels & Windows": [
        "lintel",
        "window head",
        "steel angle",
        "steel lintel",
        "window lintel",
        "door lintel",
        "concrete lintel",
    ],
    "Brick Veneer": [
        "veneer",
        "face brick",
        "brick rebuild",
        "brick replacement",
        "brick veneer",
        "masonry veneer",
    ],
    "Repointing": [
        "repoint",
        "mortar joints",
        "tuckpoint",
        "tuck pointing",
        "joint repair",
        "pointing",
        "repointing",
    ],
    "Crack Repair": [
        "crack",
        "stitching",
        "injection",
        "crack repair",
        "crack sealing",
        "epoxy injection",
    ],
    "Flashing & Waterproofing": [
        "flashing",
        "thru-wall",
        "through-wall",
        "membrane",
        "sealant",
        "waterproofing",
        "weep holes",
        "drip edge",
    ],
    "Logistics": [
        "scaffold",
        "shed",
        "dumpster",
        "cleanup",
        "protection",
        "site protection",
        "safety",
    ],
    "Permits & Inspections": [
        "permit",
        "filing",
        "inspection",
        "engineer",
        "architect",
        "DOB",
        "building department",
    ],
}


def _normalize_text(text: str) -> str:
    """Normalize text for keyword matching (lowercase, remove extra spaces)."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _match_keywords(text: str, keywords: list[str]) -> tuple[bool, list[str]]:
    """
    Check if text matches any keywords.

    Returns:
        Tuple of (matched, list of matched keywords)
    """
    normalized_text = _normalize_text(text)
    matched_keywords: list[str] = []

    for keyword in keywords:
        normalized_keyword = _normalize_text(keyword)
        if normalized_keyword in normalized_text:
            matched_keywords.append(keyword)

    return len(matched_keywords) > 0, matched_keywords


def _calculate_confidence(matched_keywords: list[str], text: str) -> float:
    """
    Calculate confidence score for a match.

    More specific/longer keywords = higher confidence.
    Multiple keyword matches = higher confidence.
    """
    if not matched_keywords:
        return 0.0

    # Base confidence from number of matches
    match_count = len(matched_keywords)
    base_confidence = min(0.5 + (match_count * 0.1), 0.9)

    # Boost for longer/more specific keywords
    avg_keyword_length = sum(len(k) for k in matched_keywords) / len(matched_keywords)
    length_boost = min(avg_keyword_length / 20.0, 0.1)

    return min(base_confidence + length_boost, 1.0)


def normalize_work_packages(
    bid_items: list[ContractorBidLineItem | BidLineItem],
) -> list[WorkPackage]:
    """
    Normalize bid items into work packages based on keyword matching.

    Args:
        bid_items: List of line items from contractor_bid or bid_proposal

    Returns:
        List of work packages with grouped line items
    """
    # Track which items have been assigned
    assigned_item_ids: set[str] = set()
    packages: list[WorkPackage] = []

    # Process each package type
    for package_title, keywords in PACKAGE_KEYWORDS.items():
        matched_items: list[tuple[str, ContractorBidLineItem | BidLineItem, list[str]]] = []

        for idx, item in enumerate(bid_items):
            # Get item ID and title/description
            if isinstance(item, ContractorBidLineItem):
                item_id = item.item_id
                item_text = f"{item.title} {item.basis or ''} {item.notes or ''}"
            else:  # BidLineItem
                item_id = getattr(item, "item_id", None) or f"item_{idx}"
                item_text = f"{item.description} {item.basis}"

            # Skip if already assigned
            if item_id in assigned_item_ids:
                continue

            # Check for keyword matches
            matched, matched_keywords = _match_keywords(item_text, keywords)
            if matched:
                matched_items.append((item_id, item, matched_keywords))

        # Create package if we have matches
        if matched_items:
            line_item_ids = [item_id for item_id, _, _ in matched_items]
            subtotal = sum(
                item.total_cost for _, item, _ in matched_items
            )

            # Calculate average confidence
            all_matched_keywords = [kw for _, _, kw in matched_items for kw in kw]
            avg_confidence = sum(
                _calculate_confidence(kw_list, f"{item.title if isinstance(item, ContractorBidLineItem) else item.description} {item.basis if isinstance(item, ContractorBidLineItem) else item.basis}")
                for _, item, kw_list in matched_items
            ) / len(matched_items) if matched_items else 0.5

            # Create unique package_id
            package_id = f"pkg_{package_title.lower().replace(' ', '_').replace('&', 'and')}"

            packages.append(
                WorkPackage(
                    package_id=package_id,
                    title=package_title,
                    line_item_ids=line_item_ids,
                    subtotal=subtotal,
                    keywords_matched=list(set(all_matched_keywords)),
                    confidence=avg_confidence,
                )
            )

            # Mark items as assigned
            assigned_item_ids.update(line_item_ids)

    # Create "Other" package for unassigned items
    unassigned_items: list[tuple[str, ContractorBidLineItem | BidLineItem]] = []
    for idx, item in enumerate(bid_items):
        if isinstance(item, ContractorBidLineItem):
            item_id = item.item_id
        else:
            item_id = getattr(item, "item_id", None) or f"item_{idx}"
        
        if item_id not in assigned_item_ids:
            unassigned_items.append((item_id, item))

    if unassigned_items:
        unassigned_ids = [item_id for item_id, _ in unassigned_items]
        unassigned_subtotal = sum(item.total_cost for _, item in unassigned_items)

        packages.append(
            WorkPackage(
                package_id="pkg_other",
                title="Other Work",
                line_item_ids=unassigned_ids,
                subtotal=unassigned_subtotal,
                keywords_matched=[],
                confidence=0.3,  # Lower confidence for unassigned items
            )
        )

    return packages


def generate_work_packages(
    project_id: str, output_dir: Path, settings: Settings
) -> Path:
    """
    Generate work packages from contractor_bid or bid_proposal.

    Args:
        project_id: Project ID
        output_dir: Output directory for artifacts
        settings: Application settings

    Returns:
        Path to the generated work_packages.json file

    Raises:
        FileNotFoundError: If neither contractor_bid.json nor bid_proposal.json exists
    """
    import json

    log_ctx = logger.bind(project_id=project_id, service="work_package_normalizer")
    log_ctx.info("Generating work packages")

    # Try contractor_bid first
    contractor_bid_file = output_dir / "contractor_bid.json"
    bid_items: list[ContractorBidLineItem | BidLineItem] = []

    if contractor_bid_file.exists():
        with open(contractor_bid_file, "r") as f:
            contractor_bid_data = json.load(f)
        contractor_bid = ContractorBid.model_validate(contractor_bid_data)
        log_ctx.info("Loaded contractor_bid.json")

        # Extract all line items from sections, logistics, and permits
        for section in contractor_bid.sections:
            bid_items.extend(section.line_items)
        bid_items.extend(contractor_bid.logistics)
        bid_items.extend(contractor_bid.permits_and_inspections)
    else:
        # Fallback to bid_proposal
        bid_proposal_file = output_dir / "bid_proposal.json"
        if bid_proposal_file.exists():
            from app.schemas.bid_proposal import BidProposal

            with open(bid_proposal_file, "r") as f:
                bid_proposal_data = json.load(f)
            bid_proposal = BidProposal.model_validate(bid_proposal_data)
            log_ctx.info("Loaded bid_proposal.json (fallback)")

            bid_items = bid_proposal.line_items
        else:
            raise FileNotFoundError(
                f"Neither contractor_bid.json nor bid_proposal.json found for project {project_id}"
            )

    # Normalize into work packages
    work_packages = normalize_work_packages(bid_items)

    # Save to file
    output_file = output_dir / "work_packages.json"
    with open(output_file, "w") as f:
        json.dump(
            [pkg.model_dump() for pkg in work_packages],
            f,
            indent=2,
        )

    log_ctx.info(f"Generated {len(work_packages)} work packages")

    return output_file

