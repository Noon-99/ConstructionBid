"""Region resolver service (Phase 9.7).

Deterministically resolves project region from document analysis and extraction results
to select appropriate contractor profiles.
"""

import re
from typing import Any

from loguru import logger


# Zipcode ranges for common states (minimal set for Phase 9.7)
ZIPCODE_TO_STATE: dict[tuple[int, int], str] = {
    # NYC zipcodes (10001-14999)
    (10001, 14999): "NYC",
    # New Jersey (07000-08999)
    (7000, 8999): "NJ",
    # Texas (75000-79999, 77000-79999)
    (75000, 79999): "TX",
    # Pennsylvania (15000-19999)
    (15000, 19999): "PA",
    # California (90000-96199)
    (90000, 96199): "CA",
    # Florida (32000-34999)
    (32000, 34999): "FL",
}

# State abbreviations mapping
STATE_ABBREVIATIONS: dict[str, str] = {
    "NY": "NYC",
    "NJ": "NJ",
    "TX": "TX",
    "PA": "PA",
    "CA": "CA",
    "FL": "FL",
}


def resolve_region(
    document_analysis: dict[str, Any] | None = None,
    extraction_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve project region from available signals (Phase 9.7).

    Args:
        document_analysis: Document analysis artifact (may contain project_address, project_location, text_blocks)
        extraction_result: Extraction result artifact (may contain location signals)

    Returns:
        Dictionary with:
            region_id: str (e.g., "NYC", "NJ", "TX", "US_DEFAULT")
            confidence: float (0.0-1.0)
            evidence: list[str] (strings describing why this region was selected)
    """
    evidence: list[str] = []
    confidence = 0.0
    region_id = "US_DEFAULT"

    # Signal 1: Look for explicit address lines in document_analysis text_blocks
    if document_analysis:
        text_blocks = document_analysis.get("text_blocks", [])
        if isinstance(text_blocks, list):
            for block in text_blocks:
                if isinstance(block, dict):
                    text = block.get("text", "") or ""
                    if isinstance(text, str):
                        region_signal = _extract_region_from_text(text)
                        if region_signal:
                            evidence.append(f"Found region signal in text block: {region_signal}")
                            region_id = region_signal
                            confidence = 0.8
                            break

        # Signal 2: Check project_address or project_location fields
        project_address = document_analysis.get("project_address") or document_analysis.get("project_location")
        if project_address:
            region_signal = _extract_region_from_text(str(project_address))
            if region_signal:
                evidence.append(f"Found region in project address: {project_address}")
                region_id = region_signal
                confidence = 0.9

    # Signal 3: Check extraction_result for location signals
    if extraction_result:
        # Look for any location-related fields
        location_fields = ["project_location", "address", "location", "site_address"]
        for field in location_fields:
            value = extraction_result.get(field)
            if value:
                region_signal = _extract_region_from_text(str(value))
                if region_signal:
                    evidence.append(f"Found region in extraction result {field}: {value}")
                    region_id = region_signal
                    confidence = 0.85
                    break

    # Signal 4: If "DOB" or "NYC" references appear, bias to NYC
    if document_analysis:
        text_content = str(document_analysis).lower()
        if "dob" in text_content or "nyc" in text_content or "new york city" in text_content:
            if region_id == "US_DEFAULT" or confidence < 0.7:
                evidence.append("Found NYC/DOB references in document")
                region_id = "NYC"
                confidence = max(confidence, 0.7)

    # If no signals found, use default
    if region_id == "US_DEFAULT":
        evidence.append("No location signals found, using default region")

    logger.info(f"Resolved region: {region_id} (confidence: {confidence:.2f}, evidence: {evidence})")

    return {
        "region_id": region_id,
        "confidence": confidence,
        "evidence": evidence,
    }


def _extract_region_from_text(text: str) -> str | None:
    """
    Extract region identifier from text string.

    Args:
        text: Text to analyze

    Returns:
        Region ID (e.g., "NYC", "NJ", "TX") or None if not found
    """
    text_upper = text.upper()

    # Check for state abbreviations
    for abbrev, region in STATE_ABBREVIATIONS.items():
        # Look for patterns like "NY 11385", "Queens, NY", "NYC", etc.
        if re.search(rf"\b{abbrev}\b", text_upper):
            return region

    # Check for explicit region names
    if re.search(r"\bNYC\b|\bNEW\s+YORK\s+CITY\b", text_upper):
        return "NYC"
    if re.search(r"\bNEW\s+JERSEY\b|\bNJ\b", text_upper):
        return "NJ"
    if re.search(r"\bTEXAS\b|\bTX\b", text_upper):
        return "TX"
    if re.search(r"\bPENNSYLVANIA\b|\bPA\b", text_upper):
        return "PA"
    if re.search(r"\bCALIFORNIA\b|\bCA\b", text_upper):
        return "CA"
    if re.search(r"\bFLORIDA\b|\bFL\b", text_upper):
        return "FL"

    # Extract zipcode and map to state
    zipcode_match = re.search(r"\b(\d{5})\b", text)
    if zipcode_match:
        zipcode = int(zipcode_match.group(1))
        for (min_zip, max_zip), region in ZIPCODE_TO_STATE.items():
            if min_zip <= zipcode <= max_zip:
                return region

    return None


def select_profile_id(region_id: str, project_type: str = "row_house_masonry") -> str:
    """
    Select contractor profile ID based on region and project type (Phase 9.7).

    Args:
        region_id: Region identifier (e.g., "NYC", "NJ", "TX", "US_DEFAULT")
        project_type: Project type (e.g., "row_house_masonry", "institutional_new_construction")

    Returns:
        Profile ID (e.g., "nyc_row_house_masonry_v1")
    """
    # Mapping: region_id -> profile_id
    profile_mapping: dict[str, str] = {
        "NYC": "nyc_row_house_masonry_v1",
        "NJ": "nj_row_house_masonry_v1",
        "TX": "tx_row_house_masonry_v1",
        "US_DEFAULT": "us_default_v1",
    }

    # For now, we only have row_house_masonry profiles
    # In future, this could be: f"{region_id.lower()}_{project_type}_v1"
    profile_id = profile_mapping.get(region_id, "us_default_v1")

    logger.debug(f"Selected profile: {profile_id} for region={region_id}, project_type={project_type}")

    return profile_id






