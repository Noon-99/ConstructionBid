"""Site context extractor with explicit provenance tracking (Task 3).

Extracts site/row context information with clear distinction between
evidence-based extraction and inference.
"""

import re
from typing import Any

from loguru import logger

from app.schemas.site_context import SiteContext, SiteContextProvenance


def extract_site_context_from_text(text: str, is_row_house: bool = True) -> SiteContext:
    """
    Extract site context from text with explicit provenance tracking.

    Args:
        text: Text content from document pages
        is_row_house: Whether this is a row house project

    Returns:
        SiteContext with provenance tracking
    """
    text_lower = text.lower()
    provenance = SiteContextProvenance()

    # Evidence extraction rules
    street_front: str | None = None
    cross_street_left: str | None = None
    cross_street_right: str | None = None
    row_condition: Literal["attached", "semi_detached", "detached", "unknown"] = "unknown"
    row_count_estimate: int | None = None
    subject_position: Literal["middle", "end", "unknown"] = "unknown"

    # Evidence rules: Look for explicit indicators
    evidence_keywords = {
        "ROW HOUSE": ["row house", "rowhouse", "row-house"],
        "ATTACHED": ["attached", "party wall", "common wall"],
        "PARTY WALL": ["party wall", "common wall"],
        "TYP. ADJ. BLDG": ["typical adjacent building", "typ. adj. bldg", "adj. bldg"],
        "EXISTING BUILDINGS": ["existing buildings", "existing bldg", "adjacent buildings"],
    }

    # Check for row condition evidence
    if any(keyword in text_lower for keyword in evidence_keywords["ATTACHED"] + evidence_keywords["PARTY WALL"]):
        row_condition = "attached"
        provenance.row_condition = "evidence"
    elif "semi" in text_lower and "detach" in text_lower:
        row_condition = "semi_detached"
        provenance.row_condition = "evidence"
    elif "detach" in text_lower and "row" not in text_lower:
        row_condition = "detached"
        provenance.row_condition = "evidence"

    # Extract street names from address blocks (evidence-based)
    # Look for patterns like "123 Main Street", "Main St", "Main Street, Queens"
    street_patterns = [
        r"\b\d+\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Place|Pl|Court|Ct)\b",
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr)\b",
    ]

    for pattern in street_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            # If we haven't set street_front yet, use first match
            if not street_front:
                street_front = match.group(0).strip()
                provenance.street_front = "evidence"
                break

    # Look for cross streets (evidence-based)
    # Patterns like "between X and Y", "corner of X and Y", "X Street and Y Street"
    cross_street_patterns = [
        r"\bbetween\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave|Road|Rd)\s+and\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave|Road|Rd)\b",
        r"\bcorner\s+of\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave|Road|Rd)\s+and\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave|Road|Rd)\b",
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave)\s+and\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave)\b",
    ]

    for pattern in cross_street_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            if match.lastindex >= 2:
                # Assume first is left, second is right (could be refined)
                if not cross_street_left:
                    cross_street_left = match.group(1) + (" Street" if "Street" not in match.group(1) and "St" not in match.group(1) else "")
                    provenance.cross_street_left = "evidence"
                if not cross_street_right:
                    cross_street_right = match.group(2) + (" Street" if "Street" not in match.group(2) and "St" not in match.group(2) else "")
                    provenance.cross_street_right = "evidence"
                break

    # Inference rules (only if row_house + repair)
    if is_row_house:
        # If we see party wall indicators but row_condition wasn't set from evidence
        if row_condition == "unknown" and any(
            keyword in text_lower for keyword in evidence_keywords["PARTY WALL"] + evidence_keywords["TYP. ADJ. BLDG"]
        ):
            row_condition = "attached"
            provenance.row_condition = "inferred"

        # Infer row count from "TYP. ADJ. BLDG" or building IDs shown
        # Look for patterns like "B-1", "B-2", "B-3" or "TYP. ADJ. BLDG" (implies at least 3)
        building_id_pattern = r"\b[B]-\d+\b"
        building_ids = re.findall(building_id_pattern, text, re.IGNORECASE)
        if building_ids:
            unique_ids = len(set(building_ids))
            if unique_ids > 1:
                row_count_estimate = unique_ids
                provenance.row_count_estimate = "evidence"  # IDs are explicit
        elif "typ" in text_lower and "adj" in text_lower:
            # "TYP. ADJ. BLDG" implies at least 3 buildings (subject + 2 adjacent)
            row_count_estimate = 3
            provenance.row_count_estimate = "inferred"

        # Infer subject position from context (if we have building IDs and subject ID mentioned)
        if building_ids and "subject" in text_lower:
            # Look for patterns like "subject building is B-2" or "subject: B-1"
            subject_patterns = [
                r"subject\s+(?:building\s+)?(?:is\s+)?([Bb]-?\d+)",
                r"subject[:\s]+([Bb]-?\d+)",
            ]
            for pattern in subject_patterns:
                subject_id_match = re.search(pattern, text, re.IGNORECASE)
                if subject_id_match:
                    subject_id_raw = subject_id_match.group(1)
                    # Normalize: ensure it has a dash if missing
                    if "-" not in subject_id_raw:
                        subject_id = f"B-{subject_id_raw.replace('B', '').replace('b', '')}"
                    else:
                        subject_id = subject_id_raw.upper()
                    # Normalize building IDs to uppercase and ensure they have dashes
                    normalized_building_ids = []
                    for bid in building_ids:
                        bid_upper = bid.upper()
                        if "-" not in bid_upper and bid_upper.startswith("B"):
                            bid_upper = f"B-{bid_upper[1:]}"
                        normalized_building_ids.append(bid_upper)
                    if subject_id in normalized_building_ids:
                        sorted_ids = sorted(set(normalized_building_ids))
                        idx = sorted_ids.index(subject_id)
                        total = len(sorted_ids)
                        if idx == 0 or idx == total - 1:
                            subject_position = "end"
                        else:
                            subject_position = "middle"
                        provenance.subject_position = "evidence"
                        break

    return SiteContext(
        street_front=street_front,
        cross_street_left=cross_street_left,
        cross_street_right=cross_street_right,
        row_condition=row_condition,
        row_count_estimate=row_count_estimate,
        subject_position=subject_position,
        provenance=provenance,
    )


def extract_site_context_from_analysis(analysis: Any) -> SiteContext:
    """
    Extract site context from DocumentAnalysis with provenance tracking.

    Args:
        analysis: DocumentAnalysis object

    Returns:
        SiteContext with provenance
    """
    is_row_house = (
        (analysis.resolved_project_type or analysis.project_type) == "row_house"
    )

    # Build text from building_context evidence
    evidence_text = ""
    if analysis.building_context:
        evidence_text = analysis.building_context.evidence
        # Add addresses if present (these are evidence)
        if analysis.building_context.addresses:
            evidence_text += " " + " ".join(analysis.building_context.addresses)

    site_context = extract_site_context_from_text(evidence_text, is_row_house=is_row_house)

    # If building_context has addresses, extract street_front from first address
    if analysis.building_context and analysis.building_context.addresses:
        first_address = analysis.building_context.addresses[0]
        # Try to extract street name from address
        street_match = re.search(
            r"\d+\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd)",
            first_address,
            re.IGNORECASE,
        )
        if street_match and not site_context.street_front:
            site_context.street_front = street_match.group(1) + " Street"
            site_context.provenance.street_front = "evidence"

    # Update row_condition from building_context if available
    if analysis.building_context and analysis.building_context.is_row_context:
        if site_context.row_condition == "unknown":
            site_context.row_condition = "attached"  # Default for row context
            site_context.provenance.row_condition = "inferred"

    return site_context

