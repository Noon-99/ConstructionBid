"""Document analyzer using OpenAI Vision for document analysis."""

import base64
import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError
from app.services.procurement_analyzer import ProcurementSignalAnalyzer
from app.services.page_selector import select_pages_for_stage1


class DocumentAnalyzer:
    """Analyzes construction documents using OpenAI Vision."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize document analyzer."""
        self.settings = settings
        self.openai_client = openai_client
        self.procurement_analyzer = ProcurementSignalAnalyzer(settings, openai_client)

    def _load_image_as_base64(self, image_path: Path) -> str:
        """Load image file and return as base64 string."""
        with open(image_path, "rb") as f:
            image_data = f.read()
        return base64.b64encode(image_data).decode("utf-8")

    def _create_analysis_prompt(self) -> str:
        """Create the prompt for document analysis."""
        return """You are analyzing a construction bid document (PDF pages converted to images).

**CRITICAL: READ TEXT FIRST, THEN LOOK AT VISUAL ELEMENTS.**

Your task is to analyze the document structure and identify WHERE information lives, NOT to extract the actual values.

**MANDATORY: Read ALL text visible in the images, especially:**
- Section headers like "SCOPE OF WORK", "MASONRY NOTES", "BRICK NOTES", "STRUCTURAL STEEL NOTES"
- Project descriptions and scope statements
- General notes and specifications
- Sheet titles and detail labels

**DO NOT hallucinate or invent information.** Only report what you actually see in the images.

Return ONLY valid JSON matching this exact schema:

{
  "project_type": "row_house" | "commercial" | "institutional" | "mixed" | "single_family" | "unknown",
  "scope_type": "repair" | "renovation" | "new_construction" | "mixed" | "unknown",
  "sheets": [
    {
      "sheet_id": "A-1",
      "page_number": 1,
      "sheet_type": "elevation" | "plan" | "section" | "detail" | "schedule" | "notes" | "unknown",
      "title": "Front Elevation" or null
    }
  ],
  "where_scope_lives": [
    {
      "sheet_id": "A-1" or null,
      "page_number": 1,
      "location_type": "elevation_notes" | "general_notes" | "schedule" | "detail_callouts" | "specification_reference" | "unknown",
      "evidence": "Short evidence snippet",
      "confidence": 0.0-1.0
    }
  ],
  "where_quantities_live": [
    {
      "sheet_id": "A-3" or null,
      "page_number": 3,
      "location_type": "life_safety_plan" | "room_schedule" | "elevation_dimensions" | "area_calculations" | "specification_table" | "unknown",
      "evidence": "Short evidence snippet",
      "confidence": 0.0-1.0
    }
  ],
  "where_materials_live": [
    {
      "sheet_id": "A-2" or null,
      "page_number": 2,
      "location_type": "specification_section" | "detail_callouts" | "schedule" | "general_notes" | "unknown",
      "evidence": "Short evidence snippet",
      "confidence": 0.0-1.0
    }
  ],
  "building_context": {
    "building_type": "row_house" | "commercial" | "institutional" | "mixed" | "single_family" | "unknown",
    "is_row_context": true/false,
    "building_ids": ["B-1", "B-2"] or [],
    "addresses": ["123 Main St"] or [],
    "evidence": "Evidence for building context"
  } or null,
  "key_dimensions": {
    "width": 40.0 or null,
    "depth": 60.0 or null,
    "height": 30.0 or null,
    "area": 2400.0 or null,
    "evidence": "Where dimensions were found",
    "confidence": 0.0-1.0
  } or null,
  "critical_expected_items": [
    {
      "item": "parapet",
      "expected_for": "row_house_repair",
      "found": true/false,
      "evidence": "Evidence if found" or null,
      "confidence": 0.0-1.0
    }
  ],
  "confidence": 0.0-1.0,
  "missing_fields": ["key_dimensions", "building_context"] or [],
  "primary_division": "07" | "08" | "04" | "05" | "other" | null,
  "primary_trade": "roofing" | "windows" | "masonry" | "structure" | "pavement" | "other" | null,
  "trade_detection_confidence": 0.0-1.0,
  "labor_regime": "standard" | "prevailing_wage" | "union" | "unknown",
  "labor_regime_confidence": 0.0-1.0,
  "labor_regime_evidence": "Evidence snippet" or null
}

Instructions:
1. **READ TEXT SECTIONS FIRST**: Look for and read text sections like "SCOPE OF WORK", "MASONRY NOTES", "BRICK NOTES", "STRUCTURAL STEEL NOTES", "GENERAL NOTES". These text sections define the PRIMARY scope and trade. Record them in `where_scope_lives` with `location_type`="general_notes" or "specification_reference".

2. Identify all drawing sheets and their types (elevation, plan, section, detail, schedule, notes). **ONLY classify as "schedule" if you see an actual TABLE with headers and rows.** Do NOT invent schedules that don't exist. If a sheet contains a window or door schedule table, classify it as "schedule" in addition to any other applicable type.

3. Identify WHERE scope information likely lives (elevation notes, general notes, schedules, detail callouts). **PRIORITIZE text sections** like "SCOPE OF WORK", "MASONRY NOTES", "BRICK NOTES" - these define the primary trade. If you see window demo/install notes, storefront/glazing instructions, or head/sill/jamb detail callouts, record them as scope locators and include the specific keywords ("window", "glazing", "frame", "storefront"). **BUT: If you see "MASONRY NOTES" or "BRICK REPAIR", that's the PRIMARY scope, not windows.**

4. Identify WHERE quantities likely live (life safety plans, room schedules, dimensions on elevations, area calculations). **ONLY record window schedules if you see an actual TABLE with window marks and quantities.** Do NOT invent window schedules like "W-1 Qty 12" unless you see an actual schedule table. Window schedules with marks ("W-1", "WP-101", "CW-1") MUST be recorded here with `location_type`="schedule" and evidence snippets containing the mark strings. **If you only see window openings in elevation drawings without a schedule table, do NOT record it as a schedule.**

5. Identify WHERE materials are specified (specification sections, detail callouts, schedules, general notes). **PRIORITIZE text sections** like "MASONRY NOTES", "BRICK NOTES", "STRUCTURAL STEEL NOTES" - these define materials. If frame/glass/hardware specs appear, capture them and ensure the evidence snippet mentions the related keyword ("frame", "glazing", "low-e", "aluminum").
5. Extract building context: Use SEMANTIC UNDERSTANDING to identify building type. Look for:
   - **Institutional buildings**: hospitals, medical facilities, healthcare, clinics, VA facilities, Veterans Affairs, federal medical centers, schools, universities, government buildings, courthouses, libraries, museums
   - **Residential buildings**: row houses, townhouses, single-family homes, apartments, multi-family
   - **Commercial buildings**: offices, retail, warehouses, mixed-use
   - **Key indicators**: Building names, agency names (VA, Department of Veterans Affairs, HHS, etc.), facility types mentioned in titles or notes
   - **DO NOT rely on keywords alone** - use context and semantic understanding. For example, "REPLACE HOSPITAL WINDOWS" or "VETERANS AFFAIRS" clearly indicates institutional/medical facility, not residential.
   - If you see "hospital", "medical", "clinic", "VA", "Veterans Affairs", "healthcare facility" → classify as "institutional"
   - If you see "row house", "townhouse", "attached homes" in residential context → classify as "row_house"
   - Multi-building? addresses? building IDs?
6. Extract any explicit dimensions visible (width, depth, height, area)
7. **CRITICAL: Detect primary trade/division BEFORE classifying project type. READ TEXT SECTIONS FIRST, then use SEMANTIC UNDERSTANDING. Populate primary_division, primary_trade, and trade_detection_confidence accordingly:**
   
   **MANDATORY CHECK ORDER (MUST follow this order):**
   
   **STEP 1: READ TEXT SECTIONS FIRST - These define the PRIMARY scope:**
     - **Look for section headers**: "SCOPE OF WORK", "MASONRY NOTES", "BRICK NOTES", "BRICK REPAIR DETAILS", "STRUCTURAL STEEL NOTES"
     - **Read the "SCOPE OF WORK" section** - this explicitly states the primary trade
     - **If you see "MASONRY NOTES" or "BRICK NOTES" sections** → Division 04 (Masonry) is PRIMARY
     - **If you see "BRICK REPAIR DETAILS" sheet title** → Division 04 (Masonry) is PRIMARY
     - **If you see "STRUCTURAL STEEL NOTES" or "LINTEL SCHEDULE"** → Division 05 (Metals/Structural) is supporting, Division 04 (Masonry) is likely primary
   
   **STEP 2: Check for PRIMARY STRUCTURAL/BUILDING ENVELOPE work** (these ALWAYS take precedence over finishes):
     - **MASONRY indicators (Division 04) - CHECK FIRST**: Look for text sections titled "MASONRY NOTES", "BRICK NOTES", "BRICK REPAIR", "SCOPE OF WORK" mentioning "brick", "masonry", "wall reconstruction", "repointing", "parapet repair", "façade repair", "wall reconstruction", "structural masonry", "CMU", "concrete block", "brick wall", "masonry wall", "lintel replacement" (structural steel for masonry), "DOB" or "Department of Buildings" (NYC DOB often indicates structural/masonry work), "NYC DOB", "building code compliance", "structural work", "wall repair", "masonry restoration"
     - **ROOFING indicators (Division 07)**: "roof replacement", "roof plan", "roof membrane", "roof area", "roof SF", "waterproofing", "EPDM", "TPO", "quonset roof", "roof tear-off"
     - **STRUCTURAL indicators (Division 05)**: "structural repair", "beam replacement", "column repair", "foundation work", "structural steel", "lintel schedule" (but lintels are usually supporting masonry, not primary)
   
   **STEP 3: ONLY if NO structural/building envelope work found in TEXT SECTIONS, THEN check for FINISHES/OPENINGS work:**
     - **WINDOW / GLAZING indicators (Division 08)**: **ONLY if you see an actual window schedule TABLE** or explicit "WINDOW REPLACEMENT" scope. Do NOT classify as windows just because you see window openings in elevation drawings. Window openings in drawings are NOT a schedule.
     - **CRITICAL: "Window lintels" or "Replace window lintels" means STRUCTURAL STEEL (Division 05), NOT windows (Division 08).** Lintels are structural supports, not window replacement.
   
   **CRITICAL DECISION RULES:**
   - **IF you see text sections titled "MASONRY NOTES", "BRICK NOTES", "BRICK REPAIR DETAILS" → Division 04 (Masonry) is PRIMARY, regardless of window shapes in drawings.**
   - **IF you see "SCOPE OF WORK" mentioning "brick", "masonry", "wall reconstruction" → Division 04 (Masonry) is PRIMARY.**
   - **IF you see "window lintels" or "lintel replacement" → This is STRUCTURAL STEEL (Division 05) supporting masonry, NOT window replacement (Division 08).**
   - **IF you see window openings in elevation drawings BUT no "WINDOW SCHEDULE" table or "WINDOW REPLACEMENT" scope → Windows are NOT the primary trade.**
   - **ONLY if you see an actual WINDOW SCHEDULE TABLE or explicit "WINDOW REPLACEMENT" scope AND NO masonry/structural text sections → THEN Division 08 (Windows) can be primary.**
   - **Window schedules or glazing details in a masonry/structural project are SECONDARY/INCIDENTAL scope, not primary.**
   - **If document shows "DOB", "Department of Buildings", "NYC DOB", "building code", or structural compliance requirements → strongly consider masonry/structural as primary.**
   
   **Use semantic understanding**: **READ TEXT FIRST.** If text sections say "MASONRY NOTES", "BRICK REPAIR", "SCOPE OF WORK: brick reconstruction", that's the PRIMARY scope. Window shapes in elevation drawings are just showing the building facade, not the work scope.
   
   **DO NOT hallucinate**: Only report window schedules if you see an actual TABLE. Do NOT invent "W-1 Qty 12" unless you see it in a schedule table.
   
   Provide a confidence score (0.0-1.0) reflecting the strength of evidence collected for the detected primary trade.
8. **CRITICAL: Project type classification must use SEMANTIC UNDERSTANDING:**
   - If document shows "HOSPITAL", "MEDICAL FACILITY", "VA", "VETERANS AFFAIRS", "HEALTHCARE" → project_type should be "institutional"
   - If document shows "ROW HOUSE", "TOWNHOUSE", "ATTACHED HOMES" in residential context → project_type should be "row_house"
   - If document shows "COMMERCIAL", "OFFICE", "RETAIL" → project_type should be "commercial"
   - **DO NOT misclassify institutional buildings as residential just because you see the word "row" in a different context**
   - **Use the ACTUAL building type shown in the document, not assumptions**
9. For row-house repair projects ONLY, check for critical expected items: parapet, lintels, flashing, repointing, etc.
10. Only include items in critical_expected_items if you have STRONG evidence this is a row-house repair project (not institutional or commercial)
11. List any fields you couldn't determine in missing_fields
12. Provide evidence snippets for each claim (short, specific) - include actual text/phrases from the document that support your classification

CRITICAL: Return ONLY the JSON object. No markdown, no code blocks, no explanation, no text before or after the JSON. Start with { and end with }."""

    def _parse_json_response(self, content: str) -> dict:
        """Parse JSON from model response, handling markdown code blocks."""
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        # Try to find JSON object
        content = content.strip()
        if content.startswith("{"):
            # Find the matching closing brace
            brace_count = 0
            end_idx = -1
            for i, char in enumerate(content):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx > 0:
                content = content[:end_idx]

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {str(e)}") from e

    def _detect_primary_trade_from_text(
        self, page_texts: list[str] | None, project_id: str
    ) -> dict[str, Any] | None:
        """
        Deterministic rule-based primary trade detection from extracted text.
        
        This runs BEFORE GPT Vision to provide reliable, text-based classification.
        Returns None if no clear trade detected, otherwise returns trade info.
        """
        if not page_texts:
            return None
        
        # Combine all extracted text
        all_text = " ".join(text for text in page_texts if text and text.strip())
        if not all_text or len(all_text.strip()) < 50:  # Need substantial text
            return None
        
        all_text_lower = all_text.lower()
        log_ctx = logger.bind(project_id=project_id, stage="document_analysis")
        
        # Rule-based detection (ordered by priority/precedence)
        # 1. MASONRY (Division 04) - Highest priority for structural work
        masonry_keywords = [
            "masonry notes",
            "brick notes", 
            "brick repair",
            "masonry repair",
            "wall reconstruction",
            "repointing",
            "parapet repair",
            "façade repair",
            "scope of work.*brick",
            "scope of work.*masonry",
            "brick reconstruction",
            "masonry restoration",
        ]
        found_masonry = any(kw in all_text_lower for kw in masonry_keywords)
        if found_masonry:
            matched_keywords = [kw for kw in masonry_keywords if kw in all_text_lower]
            log_ctx.info(
                f"TEXT-BASED DETECTION: Primary trade = MASONRY (Division 04) "
                f"from keywords: {matched_keywords[:3]}"
            )
            return {
                "primary_division": "04",
                "primary_trade": "masonry",
                "confidence": 0.95,
                "source": "extracted_text",
                "evidence": f"Found masonry keywords: {', '.join(matched_keywords[:3])}",
            }
        
        # 2. ROOFING (Division 07)
        roofing_keywords = [
            "roof replacement",
            "roof plan",
            "roof membrane",
            "roof area",
            "roof sf",
            "roof tear-off",
            "waterproofing",
            "epdm",
            "tpo",
        ]
        found_roofing = any(kw in all_text_lower for kw in roofing_keywords)
        if found_roofing:
            matched_keywords = [kw for kw in roofing_keywords if kw in all_text_lower]
            log_ctx.info(
                f"TEXT-BASED DETECTION: Primary trade = ROOFING (Division 07) "
                f"from keywords: {matched_keywords[:3]}"
            )
            return {
                "primary_division": "07",
                "primary_trade": "roofing",
                "confidence": 0.95,
                "source": "extracted_text",
                "evidence": f"Found roofing keywords: {', '.join(matched_keywords[:3])}",
            }
        
        # 3. WINDOWS (Division 08) - Only if explicit window replacement scope
        window_keywords = [
            "window replacement",
            "window schedule",
            "glazing upgrade",
            "storefront installation",
            "curtain wall installation",
        ]
        found_windows = any(kw in all_text_lower for kw in window_keywords)
        if found_windows:
            matched_keywords = [kw for kw in window_keywords if kw in all_text_lower]
            log_ctx.info(
                f"TEXT-BASED DETECTION: Primary trade = WINDOWS (Division 08) "
                f"from keywords: {matched_keywords[:3]}"
            )
            return {
                "primary_division": "08",
                "primary_trade": "windows",
                "confidence": 0.90,
                "source": "extracted_text",
                "evidence": f"Found window keywords: {', '.join(matched_keywords[:3])}",
            }
        
        # No clear trade detected from text
        return None

    def analyze(
        self,
        pdf_images: list[PdfPageImage],
        project_id: str,
        page_index: Any | None = None,
        page_texts: list[str] | None = None,
    ) -> DocumentAnalysis:
        """
        Analyze PDF pages and return DocumentAnalysis.

        Args:
            pdf_images: List of PDF page images (base64 encoded)
            project_id: Project ID for logging

        Returns:
            DocumentAnalysis object

        Raises:
            ValueError: If JSON parsing fails after retry
            ValidationError: If parsed JSON doesn't match schema
        """
        log_ctx = logger.bind(project_id=project_id, stage="document_analysis")

        total_pages = len(pdf_images)
        log_ctx.info(f"Starting document analysis for {total_pages} total pages")
        
        # CRITICAL: Detect primary trade from extracted text FIRST (deterministic, reliable)
        # This prevents GPT from hallucinating based on visual elements
        text_based_trade = None
        if page_texts:
            log_ctx.error(f"PHASE1: page_texts available, length={len(page_texts)}, calling detection")
            text_based_trade = self._detect_primary_trade_from_text(page_texts, project_id)
            if text_based_trade:
                log_ctx.error(
                    f"PHASE1: Text-based trade detection SUCCESS: {text_based_trade['primary_trade']} "
                    f"(Division {text_based_trade['primary_division']}, confidence: {text_based_trade['confidence']})"
                )
            else:
                log_ctx.warning("PHASE1: Text-based detection returned None")
        else:
            log_ctx.warning("PHASE1: page_texts is None - cannot detect from text")

        # Select pages for Stage 1 (cost optimization)
        selected_page_indices = select_pages_for_stage1(
            total_pages, page_index=page_index, settings=self.settings
        )
        selected_images = [pdf_images[i] for i in selected_page_indices]

        if total_pages > 0:
            reduction_pct = 100 * (1 - len(selected_images) / total_pages)
            log_ctx.info(
                f"Stage 1 optimization: analyzing {len(selected_images)}/{total_pages} pages "
                f"(reduction: {reduction_pct:.1f}%)"
            )
        else:
            log_ctx.info(f"Stage 1: analyzing {len(selected_images)} pages")

        # Build prompt with extracted text if available
        base_prompt = self._create_analysis_prompt()
        
        # CRITICAL: If text-based detection found a trade with high confidence, lock it in BEFORE GPT Vision
        # This prevents GPT from hallucinating based on visual elements
        text_based_trade_instruction = ""
        if text_based_trade and text_based_trade.get("confidence", 0) >= 0.90:
            text_division = text_based_trade["primary_division"]
            text_trade = text_based_trade["primary_trade"]
            text_confidence = text_based_trade["confidence"]
            log_ctx.error(
                f"🔒 LOCKING IN TEXT-BASED TRADE: {text_division}/{text_trade} (confidence: {text_confidence}) - "
                f"GPT Vision MUST use this trade, do not change it"
            )
            text_based_trade_instruction = f"""

**🔒 CRITICAL: TEXT-BASED TRADE DETECTION RESULT (AUTHORITATIVE - DO NOT CHANGE):**
The extracted PDF text has been analyzed and the PRIMARY TRADE has been determined:
- primary_division: "{text_division}"
- primary_trade: "{text_trade}"
- trade_detection_confidence: {text_confidence}

**MANDATORY: You MUST use these exact values in your response. DO NOT change them based on visual elements.**
**The text-based detection is authoritative because it reads the actual PDF text (not OCR).**
**Window shapes in elevation drawings are NOT window replacement work - they're just showing the building facade.**
**If you see window shapes but the text says "MASONRY NOTES" or "BRICK REPAIR", the trade is MASONRY, not windows.**
"""
        
        # Add extracted text to prompt if available (CRITICAL: This is the actual text from PDF, not OCR)
        if page_texts:
            text_sections = []
            total_text_chars = 0
            for idx, text in enumerate(page_texts):
                if text and text.strip():
                    page_num = idx + 1
                    # Only include text from selected pages
                    if idx in selected_page_indices:
                        text_preview = text[:2000]  # Limit to 2000 chars per page
                        text_sections.append(f"\n\n=== EXTRACTED TEXT FROM PAGE {page_num} ===\n{text_preview}\n")
                        total_text_chars += len(text)
            
            if text_sections:
                text_context = "\n".join(text_sections)
                log_ctx.info(
                    f"Adding {len(text_sections)} pages of extracted text ({total_text_chars} total chars) to GPT prompt"
                )
                base_prompt = f"""{base_prompt}{text_based_trade_instruction}

**CRITICAL: EXTRACTED TEXT FROM PDF (READ THIS FIRST - THIS IS THE ACTUAL TEXT, NOT OCR):**
{text_context}

**MANDATORY INSTRUCTIONS:**
- The extracted text above is the ACTUAL text from the PDF (direct extraction, not OCR)
- **YOU MUST PRIORITIZE this extracted text over visual elements in images**
- **If you see "MASONRY NOTES", "BRICK NOTES", "SCOPE OF WORK" in the extracted text, that's the PRIMARY scope**
- **If extracted text says "masonry repair" or "brick reconstruction", set primary_division to "04" and primary_trade to "masonry"**
- **Window openings in elevation drawings are NOT window replacement work - they're just showing the building facade**
- **Only use visual elements (images) to supplement the extracted text, not replace it**
- **DO NOT classify as windows just because you see window shapes in drawings - read the extracted text first**
"""
            else:
                log_ctx.warning("page_texts provided but no text found for selected pages")
                # Still add text-based trade instruction even if no text sections
                if text_based_trade_instruction:
                    base_prompt = f"""{base_prompt}{text_based_trade_instruction}"""
        else:
            log_ctx.warning("No page_texts provided to document analyzer - text extraction may have failed")
            # Still add text-based trade instruction if we have it from earlier detection
            if text_based_trade_instruction:
                base_prompt = f"""{base_prompt}{text_based_trade_instruction}"""

        # Build messages with selected images (low detail for Stage 1)
        messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": base_prompt},
                ],
            }
        ]

        # Add selected images to the message with low detail for Stage 1
        for img in selected_images:
            messages[0]["content"].append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.mime_type};base64,{img.image_base64}",
                        "detail": "low",  # Low detail for Stage 1 cost optimization
                    },
                }
            )

        # Call OpenAI with repair retry for invalid JSON
        max_retries = 2
        for attempt in range(max_retries):
            try:
                log_ctx.info(f"Calling OpenAI Vision (attempt {attempt + 1}/{max_retries})")
                response_text = self.openai_client.call_vision(
                    messages=messages,
                    request_id=project_id,
                    stage_name="document_analysis",
                    project_id=project_id,
                )

                # Parse JSON
                try:
                    parsed = self._parse_json_response(response_text)
                except ValueError as e:
                    if attempt < max_retries - 1:
                        log_ctx.warning(
                            f"Invalid JSON on attempt {attempt + 1}, retrying with repair prompt"
                        )
                        repair_prompt = (
                            "The previous response was not valid JSON. "
                            "Return ONLY valid JSON matching the schema provided. "
                            "No markdown, no code blocks, no explanation. "
                            "Just the JSON object."
                        )
                        messages[0]["content"][0]["text"] = (
                            self._create_analysis_prompt() + "\n\n" + repair_prompt
                        )
                        continue
                    raise ValueError(
                        f"Could not parse JSON response after {max_retries} attempts: {str(e)}"
                    ) from e

                parsed = self._enforce_window_keywords(parsed, project_id=project_id)
                
                # CRITICAL: Re-detect from text if text_based_trade wasn't set (defensive)
                # This ensures we always check text even if detection was skipped earlier
                if not text_based_trade and page_texts:
                    text_based_trade = self._detect_primary_trade_from_text(page_texts, project_id)
                    if text_based_trade:
                        log_ctx.warning(f"LATE DETECTION: Found {text_based_trade['primary_trade']} from text")
                
                # CRITICAL: ALWAYS override GPT with text-based detection if available
                # Text-based detection is deterministic and reliable - FORCE IT
                log_ctx.error(f"PHASE1 OVERRIDE CHECK: text_based_trade={text_based_trade}, type={type(text_based_trade)}, page_texts={page_texts is not None}")
                
                # DEFENSIVE: Re-detect if not already done (shouldn't happen, but be safe)
                if not text_based_trade and page_texts:
                    log_ctx.error("PHASE1: text_based_trade is None but page_texts exists - re-detecting NOW")
                    text_based_trade = self._detect_primary_trade_from_text(page_texts, project_id)
                    if text_based_trade:
                        log_ctx.error(f"PHASE1: DEFENSIVE DETECTION SUCCESS: {text_based_trade['primary_trade']}")
                
                # FORCE OVERRIDE - text-based detection is ALWAYS authoritative
                if text_based_trade:
                    gpt_division = parsed.get("primary_division")
                    gpt_trade = parsed.get("primary_trade")
                    text_division = text_based_trade["primary_division"]
                    text_trade = text_based_trade["primary_trade"]
                    text_confidence = text_based_trade["confidence"]
                    
                    # FORCE override regardless of GPT's answer - text is authoritative
                    parsed["primary_division"] = text_division
                    parsed["primary_trade"] = text_trade
                    parsed["trade_detection_confidence"] = text_confidence
                    
                    log_ctx.error(
                        f"✅✅✅ FORCED OVERRIDE APPLIED: GPT said {gpt_division}/{gpt_trade}, "
                        f"text says {text_division}/{text_trade} (confidence: {text_confidence}) - "
                        f"USING TEXT-BASED RESULT. parsed now has {parsed.get('primary_division')}/{parsed.get('primary_trade')}"
                    )
                else:
                    log_ctx.error("❌ text_based_trade is None - cannot override. Using GPT classification.")
                    if page_texts:
                        log_ctx.error(f"❌ page_texts exists ({len(page_texts)} pages) but detection returned None - this is a problem!")

                # CRITICAL: Ensure override is preserved in DocumentAnalysis object
                # Double-check parsed dict has correct values before validation
                if text_based_trade:
                    parsed["primary_division"] = text_based_trade["primary_division"]
                    parsed["primary_trade"] = text_based_trade["primary_trade"]
                    parsed["trade_detection_confidence"] = text_based_trade["confidence"]
                    log_ctx.error(
                        f"✅ PRE-VALIDATION CHECK: parsed dict has {parsed.get('primary_division')}/{parsed.get('primary_trade')} "
                        f"before DocumentAnalysis.model_validate()"
                    )
                
                try:
                    doc_analysis = DocumentAnalysis.model_validate(parsed)
                    
                    # CRITICAL: Force override on DocumentAnalysis object itself if text-based detection exists
                    # This ensures it can't be overwritten by later code
                    if text_based_trade:
                        # Use model_copy to create new instance with overridden values
                        doc_analysis = doc_analysis.model_copy(update={
                            "primary_division": text_based_trade["primary_division"],
                            "primary_trade": text_based_trade["primary_trade"],
                            "trade_detection_confidence": text_based_trade["confidence"],
                        })
                        log_ctx.error(
                            f"✅✅✅ POST-VALIDATION OVERRIDE: doc_analysis now has "
                            f"{doc_analysis.primary_division}/{doc_analysis.primary_trade} "
                            f"(confidence: {doc_analysis.trade_detection_confidence})"
                        )
                except ValidationError as e:
                    if attempt < max_retries - 1:
                        log_ctx.warning(
                            f"Schema validation failed on attempt {attempt + 1}, retrying with repair prompt"
                        )
                        repair_prompt = (
                            "The previous response did not match the schema. "
                            "Return ONLY valid JSON matching the schema provided. "
                            "No markdown, no code blocks, no explanation. "
                            "Just the JSON object."
                        )
                        messages[0]["content"][0]["text"] = (
                            self._create_analysis_prompt() + "\n\n" + repair_prompt
                        )
                        continue
                    log_ctx.error(f"Schema validation failed after {max_retries} attempts")
                    raise ValueError(
                        f"Response does not match DocumentAnalysis schema after {max_retries} attempts: {str(e)}"
                    ) from e

                # Enrich with procurement/compliance context
                # Phase 1: Always run procurement analyzer (critical for compliance detection)
                log_ctx.warning(  # Use WARNING so it shows up in logs
                    "PHASE1: Starting procurement signal analysis",
                    pdf_images_count=len(pdf_images),
                    has_page_index=page_index is not None,
                    procurement_analyzer_exists=hasattr(self, 'procurement_analyzer')
                )
                try:
                    procurement_payload = self.procurement_analyzer.analyze(
                        pdf_images=pdf_images,  # Pass ALL pages, not just selected ones
                        page_index=page_index,
                        project_id=project_id,
                    )
                    log_ctx.warning(  # Use WARNING so it shows up
                        "PHASE1: Procurement analyzer returned",
                        payload_is_none=procurement_payload is None,
                        payload_type=type(procurement_payload).__name__ if procurement_payload else None,
                        payload_keys=list(procurement_payload.keys()) if isinstance(procurement_payload, dict) else None
                    )
                    if procurement_payload:
                        log_ctx.warning(  # Use WARNING so it shows up
                            "PHASE1: Procurement analysis completed",
                            is_public=procurement_payload.get("procurement_context", {}).get("is_public_project"),
                            requires_prevailing_wage=procurement_payload.get("requires_prevailing_wage"),
                            requires_bonds=procurement_payload.get("requires_bonds"),
                            issuing_authority=procurement_payload.get("issuing_authority"),
                        )
                        # CRITICAL: Preserve text-based trade override when merging procurement context
                        preserved_division = doc_analysis.primary_division
                        preserved_trade = doc_analysis.primary_trade
                        preserved_confidence = doc_analysis.trade_detection_confidence
                        
                        doc_data = doc_analysis.model_dump()
                        doc_data.update(procurement_payload)
                        
                        # FORCE preserve text-based override (if it was set)
                        if text_based_trade:
                            doc_data["primary_division"] = text_based_trade["primary_division"]
                            doc_data["primary_trade"] = text_based_trade["primary_trade"]
                            doc_data["trade_detection_confidence"] = text_based_trade["confidence"]
                            log_ctx.error(
                                f"✅ PRESERVED OVERRIDE during procurement merge: "
                                f"{doc_data.get('primary_division')}/{doc_data.get('primary_trade')}"
                            )
                        
                        doc_analysis = DocumentAnalysis.model_validate(doc_data)
                        log_ctx.warning(  # Use WARNING so it shows up
                            "PHASE1: Document analysis updated with procurement context",
                            has_procurement_context=doc_analysis.procurement_context is not None
                        )
                    else:
                        log_ctx.error("PHASE1: Procurement analyzer returned None/empty payload - this should not happen")
                        # Still merge empty procurement context to ensure field exists
                        doc_data = doc_analysis.model_dump()
                        doc_data["procurement_context"] = None
                        doc_data["requires_prevailing_wage"] = None
                        doc_data["requires_bonds"] = None
                        doc_data["issuing_authority"] = None
                        doc_analysis = DocumentAnalysis.model_validate(doc_data)
                except Exception as enrichment_error:  # pragma: no cover - defensive logging
                    log_ctx.exception(
                        f"Procurement analysis failed: {enrichment_error}",
                        exc_info=True
                    )
                    # On error, still ensure fields exist (set to None)
                    try:
                        doc_data = doc_analysis.model_dump()
                        doc_data["procurement_context"] = None
                        doc_data["requires_prevailing_wage"] = None
                        doc_data["requires_bonds"] = None
                        doc_data["issuing_authority"] = None
                        doc_analysis = DocumentAnalysis.model_validate(doc_data)
                    except Exception as fallback_error:
                        log_ctx.error(f"Failed to add empty procurement fields: {fallback_error}")

                # 🔒 FINAL AUTHORITATIVE CHECK: Text-based detection ALWAYS wins
                # This is the last line of defense - ensures text-based trade is NEVER overwritten
                if text_based_trade:
                    current_division = doc_analysis.primary_division
                    current_trade = doc_analysis.primary_trade
                    text_division = text_based_trade["primary_division"]
                    text_trade = text_based_trade["primary_trade"]
                    
                    # Only override if it's different (avoid unnecessary model_copy)
                    if current_division != text_division or current_trade != text_trade:
                        log_ctx.error(
                            f"🔒 FINAL AUTHORITATIVE OVERRIDE: Current={current_division}/{current_trade}, "
                            f"Text-based={text_division}/{text_trade} - FORCING text-based result"
                        )
                        doc_analysis = doc_analysis.model_copy(update={
                            "primary_division": text_division,
                            "primary_trade": text_trade,
                            "trade_detection_confidence": text_based_trade["confidence"],
                        })
                        log_ctx.error(
                            f"🔒 FINAL OVERRIDE APPLIED: doc_analysis now has "
                            f"{doc_analysis.primary_division}/{doc_analysis.primary_trade} "
                            f"(confidence: {doc_analysis.trade_detection_confidence})"
                        )
                    else:
                        log_ctx.info(
                            f"✅ Text-based trade already correct: {text_division}/{text_trade} "
                            f"(no override needed)"
                        )

                return doc_analysis

            except OpenAINonRetryableError as e:
                log_ctx.error(f"Non-retryable OpenAI error: {e}")
                raise

        raise ValueError("Failed to get valid response from OpenAI")

    def _enforce_window_keywords(self, payload: Any, *, project_id: str) -> Any:
        """Inject explicit window keywords into locator evidence when needed."""

        if not isinstance(payload, dict):
            return payload

        try:
            primary_trade = (payload.get("primary_trade") or "").lower()
            if primary_trade != "windows":
                return payload

            locators: list[dict[str, Any]] = []
            for key in ("where_scope_lives", "where_quantities_live", "where_materials_live"):
                value = payload.get(key)
                if isinstance(value, list):
                    locators.extend([locator for locator in value if isinstance(locator, dict)])

            if not locators:
                return payload

            evidence_text = " ".join(locator.get("evidence", "") for locator in locators).lower()
            required_keywords = {"window", "frame", "glazing"}
            missing = {kw for kw in required_keywords if kw not in evidence_text}

            if not missing:
                return payload

            logger.bind(project_id=project_id, stage="document_analysis").warning(
                "Window trade detected but missing evidence keywords %s; injecting fallback evidence",
                sorted(missing),
            )

            schedule_locator: dict[str, Any] | None = None
            for locator in locators:
                if locator.get("location_type") == "schedule":
                    schedule_locator = locator
                    break

            if not schedule_locator:
                schedule_locator = locators[0]

            existing = schedule_locator.get("evidence") or ""
            additions = [kw for kw in ("window", "frame", "glazing") if kw in missing]
            if additions:
                existing_lower = existing.lower()
                missing_to_append = [kw for kw in additions if kw not in existing_lower]
                if missing_to_append:
                    suffix = "; " if existing else ""
                    schedule_locator["evidence"] = (
                        f"{existing}{suffix}includes {' '.join(missing_to_append)} details"
                    )

            return payload
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.bind(project_id=project_id, stage="document_analysis").debug(
                "Failed to enforce window keywords", error=str(exc)
            )
            return payload

    def analyze_from_paths(
        self,
        image_paths: list[Path],
        project_id: str,
        page_index: Any | None = None,
        page_texts: list[str] | None = None,
    ) -> DocumentAnalysis:
        """Analyze PDF pages from file paths."""

        pdf_images: list[PdfPageImage] = []
        for idx, path in enumerate(image_paths, start=1):
            base64_data = self._load_image_as_base64(path)
            pdf_images.append(
                PdfPageImage(
                    page_number=idx,
                    image_base64=base64_data,
                    mime_type="image/png",
                )
            )

        return self.analyze(pdf_images, project_id, page_index=page_index, page_texts=page_texts)

