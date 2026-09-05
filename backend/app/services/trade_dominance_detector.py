"""Primary trade dominance detection service.

Detects the primary trade/division BEFORE typology resolution to ensure correct
project framing. This is critical for projects like roof replacement that might
be misclassified as masonry repair if masonry elements (parapets, flashing) are
present but are supporting scope, not primary scope.

This runs BEFORE typology resolution and can override project classification.
"""

from loguru import logger

from app.schemas.document_analysis import DocumentAnalysis


def detect_primary_trade(analysis: DocumentAnalysis) -> dict[str, any]:
    """
    Detect primary trade/division from document analysis.
    
    This runs BEFORE typology resolution to ensure roof replacement projects
    are correctly identified as Division 07 (Roofing) primary, not Division 04 (Masonry).
    
    Args:
        analysis: DocumentAnalysis from Stage 1
        
    Returns:
        Dictionary with:
        - primary_division: "07" | "04" | None (None = no override)
        - primary_trade: "roofing" | "masonry" | None
        - confidence: float 0.0-1.0
        - evidence: list of evidence strings
        - override_reason: str explaining why override occurred
    """
    evidence: list[str] = []
    confidence = 0.0
    
    # Trade-specific indicator scans (ordered by priority)
    roof_indicators = _detect_roof_replacement_indicators(analysis)
    window_indicators = _detect_window_system_indicators(analysis)
    masonry_indicators = _detect_masonry_indicators(analysis)
    
    # Decision logic: Roof replacement dominates if present
    if roof_indicators:
        evidence.extend(roof_indicators)
        confidence = min(0.9, 0.5 + (len(roof_indicators) * 0.1))
        
        return {
            "primary_division": "07",
            "primary_trade": "roofing",
            "confidence": confidence,
            "evidence": evidence,
            "override_reason": f"Roof replacement indicators detected: {len(roof_indicators)} indicators. "
                              f"Division 07 (Roofing) is primary. Masonry elements are supporting scope.",
        }
    
    # Division 08 (windows / openings) takes precedence when clearly signaled
    if window_indicators:
        evidence.extend(window_indicators)
        confidence = min(0.85, 0.45 + (len(window_indicators) * 0.1))

        return {
            "primary_division": "08",
            "primary_trade": "windows",
            "confidence": confidence,
            "evidence": evidence,
            "override_reason": (
                f"Window system indicators detected: {len(window_indicators)} indicators. "
                "Division 08 (Openings) is primary."
            ),
        }

    # If no roof or window indicators but masonry indicators, masonry is primary
    if masonry_indicators and not roof_indicators:
        evidence.extend(masonry_indicators)
        confidence = min(0.8, 0.4 + (len(masonry_indicators) * 0.1))
        
        return {
            "primary_division": "04",
            "primary_trade": "masonry",
            "confidence": confidence,
            "evidence": evidence,
            "override_reason": f"Masonry indicators detected: {len(masonry_indicators)} indicators. "
                              f"Division 04 (Masonry) is primary.",
        }
    
    # No clear trade dominance
    return {
        "primary_division": None,
        "primary_trade": None,
        "confidence": 0.0,
        "evidence": [],
        "override_reason": "No clear trade dominance detected. Proceeding with default typology resolution.",
    }


def _detect_roof_replacement_indicators(analysis: DocumentAnalysis) -> list[str]:
    """
    Detect roof replacement indicators from sheets, titles, and evidence.
    
    Returns:
        List of detected indicator descriptions
    """
    indicators: list[str] = []
    
    # Roof replacement keywords (HIGH PRIORITY)
    roof_keywords = [
        "roof replacement",
        "roofing replacement",
        "roof repair",
        "roof renovation",
        "roof system",
        "roof membrane",
        "roofing system",
        "roof area",
        "roof sf",
        "roof square feet",
        "roof plan",
        "roofing plan",
        "roof detail",
        "roofing detail",
        "roof section",
        "roofing section",
        "waterproofing",
        "roof assembly",
        "roofing assembly",
        "epdm",
        "tpo",
        "pvc roof",
        "modified bitumen",
        "built-up roof",
        "bur",
        "single-ply",
        "roof insulation",
        "roofing insulation",
        "roof drain",
        "roofing drain",
        "expansion joint roof",
        "roof expansion joint",
        "quonset",
        "quonset roof",
        "dome roof",
        "curved roof",
    ]
    
    # Check sheet titles and types
    for sheet in analysis.sheets:
        title_lower = (sheet.title or "").lower()
        sheet_type_lower = sheet.sheet_type.lower()
        
        # Check title for roof keywords
        for keyword in roof_keywords:
            if keyword in title_lower:
                indicators.append(f"Sheet '{sheet.sheet_id}' title contains roof keyword: '{keyword}'")
                break
        
        # Check for roof plan sheet type
        if "roof" in sheet_type_lower or "plan" in sheet_type_lower:
            # Look for evidence in scope/quantity locators
            for locator in analysis.where_scope_lives + analysis.where_quantities_live:
                if locator.sheet_id == sheet.sheet_id:
                    evidence_lower = locator.evidence.lower()
                    if any(keyword in evidence_lower for keyword in roof_keywords):
                        indicators.append(
                            f"Sheet '{sheet.sheet_id}' ({sheet_type_lower}) contains roof evidence"
                        )
                        break
    
    # Check scope locator evidence for roof keywords
    for locator in analysis.where_scope_lives:
        evidence_lower = locator.evidence.lower()
        for keyword in roof_keywords:
            if keyword in evidence_lower:
                indicators.append(f"Scope locator evidence contains roof keyword: '{keyword}'")
                break
    
    # Check quantity locator evidence for roof area/quantities
    for locator in analysis.where_quantities_live:
        evidence_lower = locator.evidence.lower()
        if any(term in evidence_lower for term in ["roof", "roofing", "roof area", "roof sf", "square feet roof"]):
            indicators.append(f"Quantity locator evidence suggests roof quantities")
            break
    
    # Check building context evidence
    if analysis.building_context:
        evidence_lower = analysis.building_context.evidence.lower()
        for keyword in roof_keywords:
            if keyword in evidence_lower:
                indicators.append(f"Building context evidence contains roof keyword: '{keyword}'")
                break
    
    # Check key dimensions for roof area
    if analysis.key_dimensions and analysis.key_dimensions.area:
        # If area is large (>5000 SF) and no clear building type, could be roof
        if analysis.key_dimensions.area > 5000:
            evidence_text = (analysis.key_dimensions.evidence or "").lower()
            if "roof" in evidence_text:
                indicators.append(f"Large area ({analysis.key_dimensions.area} SF) with roof evidence")
    
    return indicators



def _detect_window_system_indicators(analysis: DocumentAnalysis) -> list[str]:
    """Detect Division 08 (windows / openings) indicators from analysis artifacts."""

    indicators: list[str] = []

    window_keywords = [
        "window",
        "windows",
        "glazing",
        "storefront",
        "curtain wall",
        "curtainwall",
        "fenestration",
        "vision glass",
        "aluminum frame",
        "wp-",  # common window mark prefix
        "w-",   # generic window tag prefix
        "ig unit",
        "insulated glass",
        "sill detail",
        "head detail",
        "jamb detail",
        "mullion",
    ]

    schedule_keywords = [
        "window schedule",
        "door & window schedule",
        "door and window schedule",
        "glazing schedule",
    ]

    def _matches_keywords(text: str | None, keywords: list[str]) -> str | None:
        if not text:
            return None
        lower_text = text.lower()
        for keyword in keywords:
            if keyword in lower_text:
                return keyword
        return None

    # Inspect sheet titles and identifiers
    for sheet in analysis.sheets:
        match = _matches_keywords(sheet.title, schedule_keywords + window_keywords)
        if match:
            indicators.append(
                f"Sheet '{sheet.sheet_id}' title includes Division 08 keyword '{match}'"
            )
            continue

        match = _matches_keywords(sheet.sheet_id, window_keywords)
        if match:
            indicators.append(
                f"Sheet ID '{sheet.sheet_id}' includes Division 08 keyword '{match}'"
            )

        if sheet.sheet_type.lower() in {"schedule", "elevation"}:
            indicators.append(
                f"Sheet '{sheet.sheet_id}' classified as {sheet.sheet_type} implicating window scope"
            )

    # Inspect locators for scope, quantities, materials referencing windows
    for locator in analysis.where_scope_lives + analysis.where_quantities_live + analysis.where_materials_live:
        match = _matches_keywords(locator.evidence, schedule_keywords + window_keywords)
        if match:
            indicators.append(
                f"Locator evidence references Division 08 keyword '{match}'"
            )

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_indicators: list[str] = []
    for entry in indicators:
        if entry not in seen:
            unique_indicators.append(entry)
            seen.add(entry)

    return unique_indicators


def _detect_masonry_indicators(analysis: DocumentAnalysis) -> list[str]:
    """
    Detect masonry indicators from sheets, titles, and evidence.
    
    Returns:
        List of detected indicator descriptions
    """
    indicators: list[str] = []
    
    # Masonry keywords
    masonry_keywords = [
        "masonry repair",
        "masonry restoration",
        "brick repair",
        "brick replacement",
        "repointing",
        "tuckpointing",
        "parapet repair",
        "parapet replacement",
        "façade repair",
        "facade repair",
        "masonry façade",
        "masonry facade",
        "brick façade",
        "brick facade",
        "stone repair",
        "stone replacement",
        "masonry wall",
        "brick wall",
        "masonry construction",
    ]
    
    # Check sheet titles
    for sheet in analysis.sheets:
        title_lower = (sheet.title or "").lower()
        for keyword in masonry_keywords:
            if keyword in title_lower:
                indicators.append(f"Sheet '{sheet.sheet_id}' title contains masonry keyword: '{keyword}'")
                break
    
    # Check scope locator evidence
    for locator in analysis.where_scope_lives:
        evidence_lower = locator.evidence.lower()
        for keyword in masonry_keywords:
            if keyword in evidence_lower:
                indicators.append(f"Scope locator evidence contains masonry keyword: '{keyword}'")
                break
    
    return indicators




