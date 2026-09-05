"""Deterministic typology resolution service.

Fixes misclassification cases where Stage 1 analysis is structurally correct
but domain-wrong (e.g., row house repair misclassified as institutional).

This is a rule-based, deterministic layer with NO AI calls.
"""

from loguru import logger

from app.schemas.document_analysis import DocumentAnalysis
from app.services.site_context_extractor import extract_site_context_from_analysis
from app.services.site_context_extractor import extract_site_context_from_analysis
from app.services.trade_dominance_detector import detect_primary_trade
from app.services.labor_regime_detector import detect_labor_regime


def resolve_typology(analysis: DocumentAnalysis, page_texts: list[str] | None = None) -> DocumentAnalysis:
    """
    Apply deterministic rules to correct typology misclassifications.

    Args:
        analysis: DocumentAnalysis from Stage 1

    Returns:
        DocumentAnalysis with potentially corrected typology and resolution notes
    """
    notes: list[str] = []
    resolved_project_type = analysis.project_type
    resolved_scope_type = analysis.scope_type

    # Phase 1: GOVERNMENT PROJECT DETECTION (runs first - before typology resolution)
    # If procurement analyzer detected government project, mark it in resolved_project_type
    is_government_project = False
    if analysis.procurement_context and analysis.procurement_context.is_public_project:
        is_government_project = True
        notes.append(
            f"Government project detected: {analysis.issuing_authority or 'Public sector project'}"
        )
        # For government projects, we'll keep the original project_type but note it's government
        # The resolved_project_type will remain the same, but we'll add a note
    
    # Rule 0: PRIMARY TRADE DETECTION (CRITICAL - runs first)
    # ALWAYS run text-based detection first - it's the most reliable source
    # Priority order:
    # 1. Text-based detection from document_bundle (MOST RELIABLE - uses actual PDF text)
    # 2. Text-based detection by reading PDF directly (fallback if page_texts not attached)
    # 3. Preserve Stage 1 text-based detection if high confidence (>= 0.90)
    # 4. Heuristic detection from analysis (fallback - ONLY if no text available)
    
    trade_dominance = None
    
    # Check 1: Text-based detection from document_bundle (HIGHEST PRIORITY - most reliable)
    # This ALWAYS runs if page_texts is available, regardless of what Stage 1 or heuristics say
    # CRITICAL: Use function parameter if provided, otherwise check for attached attribute
    # DO NOT overwrite the function parameter - it's passed from the pipeline!
    if not page_texts and hasattr(analysis, '_document_bundle_page_texts') and analysis._document_bundle_page_texts:
        page_texts = analysis._document_bundle_page_texts
        logger.error(f"TYPOLOGY RESOLVER: Found _document_bundle_page_texts with {len(page_texts)} pages")
    elif not page_texts:
        # Fallback: Try to read PDF text directly from source_pdf_path if available
        # This ensures we can always do text-based detection even if page_texts wasn't attached
        try:
            from app.services.document_processor import DocumentProcessor
            from app.services.storage import StorageService
            from app.core.config import Settings
            
            # Try to get PDF path from analysis (might be in source_pdf_path or we can infer from project)
            # Actually, we don't have project_id here, so we can't easily get the PDF path
            # For now, log that page_texts is missing
            logger.warning("No page_texts parameter or _document_bundle_page_texts available - cannot do text-based detection fallback")
        except Exception as e:
            logger.warning(f"Failed to read PDF text as fallback: {e}")
    
    if page_texts:
        from app.analyzers.document_analyzer import DocumentAnalyzer
        from app.core.config import Settings
        from app.services.openai_client import OpenAIClient
        
        settings = Settings()
        openai_client = OpenAIClient(settings)
        analyzer = DocumentAnalyzer(settings, openai_client)
        text_result = analyzer._detect_primary_trade_from_text(page_texts, "typology_resolver")
        if text_result:
            logger.error(
                f"TEXT-BASED DETECTION IN TYPOLOGY RESOLVER: Found {text_result['primary_trade']} "
                f"(Division {text_result['primary_division']}, confidence: {text_result['confidence']}) - "
                f"OVERRIDING Stage 1 result: {analysis.primary_division}/{analysis.primary_trade}"
            )
            trade_dominance = text_result
        else:
            logger.warning("Text-based detection returned None - no masonry/roofing/window keywords found")
    
    # Check 2: Stage 1 text-based detection (if document_bundle text not available AND high confidence)
    if (not trade_dominance or trade_dominance.get("primary_division") is None) and \
       analysis.primary_division and analysis.primary_trade and analysis.trade_detection_confidence and analysis.trade_detection_confidence >= 0.90:
        logger.info(
            f"Preserving Stage 1 text-based trade detection: {analysis.primary_division}/{analysis.primary_trade} "
            f"(confidence: {analysis.trade_detection_confidence:.2f})"
        )
        trade_dominance = {
            "primary_division": analysis.primary_division,
            "primary_trade": analysis.primary_trade,
            "confidence": analysis.trade_detection_confidence,
            "evidence": [f"Text-based detection from Stage 1 (confidence: {analysis.trade_detection_confidence:.2f})"],
            "override_reason": "Preserved from Stage 1 text-based detection",
        }
    
    # Check 3: Heuristic detection from analysis (fallback - ONLY if no text-based detection available)
    # CRITICAL: This should NOT override text-based detection
    if not trade_dominance or trade_dominance.get("primary_division") is None:
        heuristic_result = detect_primary_trade(analysis)
        if heuristic_result and heuristic_result.get("primary_division"):
            logger.warning(
                f"Using heuristic detection: {heuristic_result['primary_trade']} "
                f"(Division {heuristic_result['primary_division']}) - "
                f"text-based detection was not available"
            )
            trade_dominance = heuristic_result
        else:
            logger.warning("No trade dominance detected from heuristics either")
    
    # Task 6: LABOR REGIME DETECTION (runs after trade detection)
    # Detects if project requires prevailing wage (DOT/public work) or union rates
    labor_regime_info = detect_labor_regime(analysis)
    
    if trade_dominance["primary_division"] == "07":
        # Roof replacement detected - this is PRIMARY, masonry is supporting
        notes.append(f"PRIMARY TRADE OVERRIDE: {trade_dominance['override_reason']}")
        notes.extend([f"  - {ev}" for ev in trade_dominance["evidence"][:5]])  # First 5 evidence items
        
        # For roof replacement, we may need to adjust project type
        # Roof replacement can be on any building type, but scope_type should reflect replacement
        if resolved_scope_type in ["repair", "renovation"]:
            # Roof replacement is typically "renovation" or "repair" depending on extent
            # Keep scope_type as-is but note the primary trade
            notes.append("Primary trade is Division 07 (Roofing) - masonry elements are supporting scope")
        
        # Store primary trade in analysis for downstream use
        # (We'll add this field to DocumentAnalysis schema)
        logger.info(
            f"Primary trade detected: Division {trade_dominance['primary_division']} "
            f"({trade_dominance['primary_trade']}) with confidence {trade_dominance['confidence']:.2f}"
        )
    elif trade_dominance["primary_division"] == "04":
        # Masonry is primary
        notes.append(f"Primary trade: Division 04 (Masonry)")
        logger.info(
            f"Primary trade detected: Division {trade_dominance['primary_division']} "
            f"({trade_dominance['primary_trade']}) with confidence {trade_dominance['confidence']:.2f}"
        )

    # Rule 1: Detect row-house indicators (BUT trust GPT's semantic understanding first)
    # Only override if GPT said "unknown" AND we have strong row-house evidence
    # OR if GPT said something else but we have CONFLICTING strong evidence
    
    # Check if GPT already classified as institutional - don't override with row-house
    is_institutional = (
        analysis.project_type == "institutional" 
        or (analysis.building_context and analysis.building_context.building_type == "institutional")
    )
    
    # Check for institutional indicators in evidence (hospital, medical, VA, etc.)
    # Look in building_context evidence, sheet titles, and scope locators
    institutional_keywords = ["hospital", "medical", "healthcare", "clinic", "veterans", "va", "federal", "government facility"]
    has_institutional_evidence = False
    
    # Check building context evidence
    if analysis.building_context and analysis.building_context.evidence:
        evidence_lower = analysis.building_context.evidence.lower()
        has_institutional_evidence = any(kw in evidence_lower for kw in institutional_keywords)
    
    # Check sheet titles
    if not has_institutional_evidence:
        for sheet in analysis.sheets:
            title_lower = (sheet.title or "").lower()
            if any(kw in title_lower for kw in institutional_keywords):
                has_institutional_evidence = True
                break
    
    # Check scope locators
    if not has_institutional_evidence:
        for locator in analysis.where_scope_lives:
            evidence_lower = locator.evidence.lower()
            if any(kw in evidence_lower for kw in institutional_keywords):
                has_institutional_evidence = True
                break
    
    # If GPT classified as institutional OR we see institutional evidence, DON'T force row_house
    if is_institutional or has_institutional_evidence:
        notes.append(
            f"Institutional building detected - preserving GPT's classification. "
            f"GPT classified as: {analysis.project_type}, "
            f"Building type: {analysis.building_context.building_type if analysis.building_context else 'N/A'}, "
            f"Institutional evidence found: {has_institutional_evidence}"
        )
        # Keep GPT's classification - don't override to row_house
        # resolved_project_type stays as analysis.project_type (or "institutional" if GPT said "unknown")
        if analysis.project_type == "unknown" and has_institutional_evidence:
            resolved_project_type = "institutional"
            notes.append("Upgrading 'unknown' to 'institutional' based on evidence (hospital/medical/VA indicators)")
    else:
        # Only check for row-house if NOT institutional
        row_house_indicators = _detect_row_house_indicators(analysis)
        
        # Only override if GPT said "unknown" AND we have strong row-house evidence
        # OR if we have MULTIPLE strong indicators (not just one keyword)
        if row_house_indicators and len(row_house_indicators) >= 2:
            if analysis.project_type == "unknown":
                notes.append(f"Row-house indicators detected (GPT said 'unknown'): {', '.join(row_house_indicators)}")
                resolved_project_type = "row_house"
                
                # Update building context if needed
                if analysis.building_context:
                    if not analysis.building_context.is_row_context:
                        notes.append("Forced is_row_context = true based on row-house indicators")
                        analysis.building_context.is_row_context = True
            else:
                # GPT already classified - only override if we have VERY strong conflicting evidence
                notes.append(
                    f"GPT classified as '{analysis.project_type}' but row-house indicators found: "
                    f"{', '.join(row_house_indicators)}. Trusting GPT's semantic understanding."
                )
                # Don't override - trust GPT

    # Rule 2: Conservative routing for new typologies (Phase 10.7)
    # BUT: Don't override institutional classifications - trust GPT's semantic understanding
    if resolved_project_type in ["small_commercial", "multi_family"] and not is_institutional:
        # Only override if NOT institutional and we have strong row-house indicators
        row_house_indicators = _detect_row_house_indicators(analysis)
        if row_house_indicators and len(row_house_indicators) >= 2:
            resolved_project_type = "row_house"
            notes.append(
                f"Overriding {analysis.project_type} to row_house due to row-house indicators "
                "(conservative routing)"
            )
        # Otherwise keep the new typology (routing will handle fallback later)

    # Rule 3: Elevation sheets dominate Life Safety Plans for typology
    has_elevation_sheets = any(
        sheet.sheet_type == "elevation" for sheet in analysis.sheets
    )
    has_life_safety_plan = any(
        locator.location_type == "life_safety_plan"
        for locator in analysis.where_quantities_live
    )

    if has_elevation_sheets and has_life_safety_plan:
        notes.append(
            "Elevation sheets detected alongside Life Safety Plan - "
            "elevations dominate for typology classification"
        )
        # Only override if NOT institutional and we have strong row-house evidence
        if not is_institutional and not has_institutional_evidence:
            row_house_indicators = _detect_row_house_indicators(analysis)
            if row_house_indicators and len(row_house_indicators) >= 2 and resolved_project_type != "row_house":
                resolved_project_type = "row_house"
                notes.append("Elevation-based row-house detection applied")
            else:
                notes.append("Trusting GPT's classification - insufficient row-house evidence to override")
        else:
            notes.append("Institutional building detected - preserving GPT's classification")

    # Rule 4: If scope_type == renovation AND row_context == true, change to repair
    is_row_context = (
        analysis.building_context.is_row_context if analysis.building_context else False
    ) or (resolved_project_type == "row_house")

    if resolved_scope_type == "renovation" and is_row_context:
        resolved_scope_type = "repair"
        notes.append(
            "Changed scope_type from 'renovation' to 'repair' "
            "because row-house context detected"
        )

    # Rule 3: Extract site context (Task 3) - always extract for row_house
    site_context = None
    if resolved_project_type == "row_house":
        try:
            site_context = extract_site_context_from_analysis(analysis)
            notes.append(
                f"Extracted site context: row_condition={site_context.row_condition} "
                f"(provenance: {site_context.provenance.row_condition})"
            )
        except Exception as e:
            logger.warning(f"Failed to extract site context: {e}")

    # CRITICAL: Final text-based override check (runs LAST, after all other logic)
    # This ensures text-based detection ALWAYS wins, even if typology resolver logic tried to override it
    final_primary_division = trade_dominance["primary_division"] if trade_dominance else analysis.primary_division
    final_primary_trade = trade_dominance["primary_trade"] if trade_dominance else analysis.primary_trade
    final_confidence = trade_dominance["confidence"] if trade_dominance and trade_dominance.get("confidence", 0) > 0 else analysis.trade_detection_confidence
    
    # If we have page_texts, do a final text-based check to ensure masonry/roofing is detected
    if page_texts or (hasattr(analysis, '_document_bundle_page_texts') and analysis._document_bundle_page_texts):
        from app.analyzers.document_analyzer import DocumentAnalyzer
        from app.core.config import Settings
        from app.services.openai_client import OpenAIClient
        
        settings = Settings()
        openai_client = OpenAIClient(settings)
        analyzer = DocumentAnalyzer(settings, openai_client)
        final_text_result = analyzer._detect_primary_trade_from_text(page_texts or analysis._document_bundle_page_texts, "typology_resolver_final")
        
        if final_text_result:
            # Text-based detection ALWAYS wins
            final_primary_division = final_text_result["primary_division"]
            final_primary_trade = final_text_result["primary_trade"]
            final_confidence = final_text_result["confidence"]
            logger.error(
                f"✅✅✅ FINAL TEXT-BASED OVERRIDE IN TYPOLOGY RESOLVER: "
                f"{final_primary_division}/{final_primary_trade} (confidence: {final_confidence})"
            )
            notes.append(f"Final text-based override: {final_primary_trade} (Division {final_primary_division})")
    
    # Only add resolution fields if changes were made OR site_context was extracted OR trade dominance detected OR labor regime detected
    has_trade_override = final_primary_division is not None and final_primary_division != analysis.primary_division
    has_labor_regime = labor_regime_info["labor_regime"] != "standard" or labor_regime_info["confidence"] > 0.7
    if notes or resolved_project_type != analysis.project_type or resolved_scope_type != analysis.scope_type or site_context or has_trade_override or has_labor_regime:
        # Create new DocumentAnalysis with site_context and trade dominance (immutable update)
        # CRITICAL: Preserve procurement_context and compliance fields from Stage 1
        resolved = DocumentAnalysis(
            project_type=analysis.project_type,
            scope_type=analysis.scope_type,
            sheets=analysis.sheets,
            where_scope_lives=analysis.where_scope_lives,
            where_quantities_live=analysis.where_quantities_live,
            where_materials_lives=analysis.where_materials_live,
            building_context=analysis.building_context,
            site_context=site_context,
            key_dimensions=analysis.key_dimensions,
            critical_expected_items=analysis.critical_expected_items,
            confidence=analysis.confidence,
            missing_fields=analysis.missing_fields,
            resolved_project_type=resolved_project_type,
            resolved_scope_type=resolved_scope_type,
            resolution_notes=notes,
            primary_division=final_primary_division,  # Use final override value
            primary_trade=final_primary_trade,  # Use final override value
            trade_detection_confidence=final_confidence if final_confidence and final_confidence > 0 else None,  # Use final override value
            labor_regime=labor_regime_info["labor_regime"],  # Task 6
            labor_regime_confidence=labor_regime_info["confidence"],  # Task 6
            labor_regime_evidence=labor_regime_info["evidence"],  # Task 6
            # Phase 1: Preserve procurement/compliance fields from Stage 1 procurement analyzer
            procurement_context=analysis.procurement_context,
            requires_prevailing_wage=analysis.requires_prevailing_wage,
            requires_bonds=analysis.requires_bonds,
            issuing_authority=analysis.issuing_authority,
        )

        if resolved_project_type != analysis.project_type or resolved_scope_type != analysis.scope_type:
            logger.info(
                f"Typology resolution applied: {analysis.project_type} -> {resolved_project_type}, "
                f"{analysis.scope_type} -> {resolved_scope_type} | "
                f"Notes: {len(notes)} overrides"
            )
        else:
            logger.info(f"Site context extracted for row_house project | Notes: {len(notes)}")

        return resolved

    return analysis


def _detect_row_house_indicators(analysis: DocumentAnalysis) -> list[str]:
    """
    Detect row-house indicators from sheets and evidence.

    Returns:
        List of detected indicator descriptions
    """
    indicators: list[str] = []

    # Check sheet titles and types for row-house keywords
    row_house_keywords = [
        "row",
        "townhouse",
        "town house",
        "party wall",
        "shared wall",
        "adjacent",
        "attached",
    ]

    for sheet in analysis.sheets:
        title_lower = (sheet.title or "").lower()
        sheet_type_lower = sheet.sheet_type.lower()

        # Check title for keywords
        for keyword in row_house_keywords:
            if keyword in title_lower:
                indicators.append(f"Sheet '{sheet.sheet_id}' title contains '{keyword}'")
                break

        # Check for elevation with multiple buildings
        if sheet.sheet_type == "elevation":
            # Look for evidence in scope/quantity locators mentioning this sheet
            for locator in analysis.where_scope_lives:
                if locator.sheet_id == sheet.sheet_id:
                    evidence_lower = locator.evidence.lower()
                    if any(
                        term in evidence_lower
                        for term in ["adjacent", "party wall", "shared", "row", "multiple"]
                    ):
                        indicators.append(
                            f"Elevation sheet '{sheet.sheet_id}' evidence suggests adjacent buildings"
                        )
                        break

    # Check building context evidence
    if analysis.building_context:
        evidence_lower = analysis.building_context.evidence.lower()
        for keyword in row_house_keywords:
            if keyword in evidence_lower:
                indicators.append(f"Building context evidence contains '{keyword}'")
                break

        # Check for multiple building IDs or addresses (row context indicator)
        if len(analysis.building_context.building_ids) > 1:
            indicators.append(
                f"Multiple building IDs detected: {analysis.building_context.building_ids}"
            )
        if len(analysis.building_context.addresses) > 1:
            indicators.append(
                f"Multiple addresses detected: {analysis.building_context.addresses}"
            )

    # Check scope locator evidence for row-house terms
    for locator in analysis.where_scope_lives:
        evidence_lower = locator.evidence.lower()
        for keyword in row_house_keywords:
            if keyword in evidence_lower:
                indicators.append(f"Scope locator evidence contains '{keyword}'")
                break

    # Check for "2 Story Masonry with Cellar" or similar patterns
    for sheet in analysis.sheets:
        title_lower = (sheet.title or "").lower()
        if "masonry" in title_lower and ("cellar" in title_lower or "basement" in title_lower):
            indicators.append(f"Sheet '{sheet.sheet_id}' suggests masonry row-house construction")

    return indicators

