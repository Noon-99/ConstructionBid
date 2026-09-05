"""Labor regime detection service.

Detects labor regime (standard, prevailing_wage, union) from document analysis.
This is critical for public work / DOT projects that require prevailing wage rates.

Task 6: Do not auto-assume prevailing wage unless the document explicitly indicates
DOT/public work—then set labor_regime with evidence + confidence.
"""

from loguru import logger

from app.schemas.document_analysis import DocumentAnalysis


def detect_labor_regime(analysis: DocumentAnalysis) -> dict[str, any]:
    """
    Detect labor regime from document analysis.
    
    Task 6: Detects if project requires prevailing wage (DOT/public work) or union rates.
    Only sets prevailing_wage if explicitly indicated in documents.
    
    Args:
        analysis: DocumentAnalysis from Stage 1
        
    Returns:
        Dictionary with:
        - labor_regime: "standard" | "prevailing_wage" | "union" | "unknown"
        - confidence: float 0.0-1.0
        - evidence: str with evidence quotes
    """
    evidence_parts: list[str] = []
    confidence = 0.5  # Default to low confidence
    
    # DOT / Public work indicators (HIGH PRIORITY)
    dot_indicators = _detect_dot_public_work_indicators(analysis)
    
    # Union indicators
    union_indicators = _detect_union_indicators(analysis)
    
    # Decision logic: DOT/public work dominates
    if dot_indicators:
        evidence_parts.extend(dot_indicators)
        confidence = min(0.95, 0.7 + (len(dot_indicators) * 0.1))
        
        return {
            "labor_regime": "prevailing_wage",
            "confidence": confidence,
            "evidence": "; ".join(evidence_parts),
        }
    
    # If union indicators but no DOT, union regime
    if union_indicators and not dot_indicators:
        evidence_parts.extend(union_indicators)
        confidence = min(0.9, 0.6 + (len(union_indicators) * 0.1))
        
        return {
            "labor_regime": "union",
            "confidence": confidence,
            "evidence": "; ".join(evidence_parts),
        }
    
    # Default to standard
    return {
        "labor_regime": "standard",
        "confidence": 0.5,
        "evidence": "No DOT/public work or union indicators detected. Using standard labor rates.",
    }


def _detect_dot_public_work_indicators(analysis: DocumentAnalysis) -> list[str]:
    """
    Detect DOT/public work indicators that require prevailing wage.
    
    Returns:
        List of detected indicator descriptions with evidence quotes
    """
    indicators: list[str] = []
    
    # DOT/public work keywords (HIGH PRIORITY)
    dot_keywords = [
        "dot",
        "department of transportation",
        "nys dot",
        "ny dot",
        "state dot",
        "public work",
        "public works",
        "prevailing wage",
        "davis-bacon",
        "davis bacon",
        "federal project",
        "state project",
        "municipal project",
        "government project",
        "public bid",
        "public contract",
        "wage determination",
        "certified payroll",
    ]
    
    # Check sheet titles
    for sheet in analysis.sheets:
        title_lower = (sheet.title or "").lower()
        for keyword in dot_keywords:
            if keyword in title_lower:
                indicators.append(f"Sheet '{sheet.sheet_id}' title contains DOT/public work keyword: '{keyword}'")
                break
    
    # Check scope locator evidence
    for locator in analysis.where_scope_lives:
        evidence_lower = locator.evidence.lower()
        for keyword in dot_keywords:
            if keyword in evidence_lower:
                indicators.append(f"Scope locator evidence contains DOT/public work keyword: '{keyword}' - '{locator.evidence[:100]}'")
                break
    
    # Check building context evidence
    if analysis.building_context:
        evidence_lower = analysis.building_context.evidence.lower()
        for keyword in dot_keywords:
            if keyword in evidence_lower:
                indicators.append(f"Building context evidence contains DOT/public work keyword: '{keyword}'")
                break
    
    return indicators


def _detect_union_indicators(analysis: DocumentAnalysis) -> list[str]:
    """
    Detect union labor indicators.
    
    Returns:
        List of detected indicator descriptions with evidence quotes
    """
    indicators: list[str] = []
    
    # Union keywords
    union_keywords = [
        "union",
        "union labor",
        "unionized",
        "collective bargaining",
        "union contract",
        "union rates",
        "union wage",
    ]
    
    # Check sheet titles
    for sheet in analysis.sheets:
        title_lower = (sheet.title or "").lower()
        for keyword in union_keywords:
            if keyword in title_lower:
                indicators.append(f"Sheet '{sheet.sheet_id}' title contains union keyword: '{keyword}'")
                break
    
    # Check scope locator evidence
    for locator in analysis.where_scope_lives:
        evidence_lower = locator.evidence.lower()
        for keyword in union_keywords:
            if keyword in evidence_lower:
                indicators.append(f"Scope locator evidence contains union keyword: '{keyword}' - '{locator.evidence[:100]}'")
                break
    
    return indicators




