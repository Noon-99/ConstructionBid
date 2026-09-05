"""Row-house repair extractor for Stage 2 extraction."""

import base64
import json
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.schemas.page_index import PageIndex
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError
from app.services.page_selector import select_pages_for_stage2


class RowHouseRepairExtractor:
    """Extracts scope, materials, quantities, and geometry for row-house repair projects."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize row-house repair extractor."""
        self.settings = settings
        self.openai_client = openai_client

    def _load_image_as_base64(self, image_path: Path) -> str:
        """Load image file and return as base64 string."""
        with open(image_path, "rb") as f:
            image_data = f.read()
        return base64.b64encode(image_data).decode("utf-8")

    def _structure_text_for_extraction(self, page_texts: list[str], page_indices: list[int], project_id: str) -> str:
        """
        Pre-process extracted text into structured sections for easier GPT extraction.
        
        This makes scope items look like materials (numbered lists) so GPT-4o-mini
        can extract them as easily as it extracts materials. Works for any trade.
        """
        from loguru import logger
        import re
        log_ctx = logger.bind(project_id=project_id, stage="text_structuring")
        
        # General scope-relevant section headers (works for any trade)
        scope_keywords = [
            "SCOPE OF WORK", "SCOPE:", "WORK INCLUDES", "WORK TO INCLUDE", "WORK:",
            "NOTES:", "GENERAL NOTES", "DRAWING NOTES", "CONSTRUCTION NOTES",
            "SPECIAL INSTRUCTIONS", "SPECIFICATIONS", "SPEC:"
        ]
        
        # General scope action verbs/phrases (works for any trade)
        scope_actions = [
            "rebuild", "reconstruction", "reconstruct", "repair", "replace",
            "replacement", "install", "installation", "repoint", "repointing",
            "pointing", "restore", "restoration", "demolish", "remove",
            "removal", "reinforce", "reinforcement", "construct", "construction",
            "modify", "modification", "upgrade", "renovate", "renovation"
        ]
        
        scope_items = []
        
        # Intelligent approach: find scope sections first, then extract items
        for page_idx in page_indices:
            if 0 <= page_idx < len(page_texts):
                text = page_texts[page_idx]
                if not text or not text.strip():
                    continue
                
                lines = text.split('\n')
                in_scope_section = False
                current_section_lines = []
                
                for line in lines:
                    line_upper = line.upper().strip()
                    line_lower = line.lower().strip()
                    
                    # Check if this line starts a scope section
                    is_section_header = any(keyword in line_upper for keyword in scope_keywords)
                    
                    if is_section_header:
                        # Process previous section if it had scope items
                        if in_scope_section and current_section_lines:
                            section_text = '\n'.join(current_section_lines)
                            # Extract scope items from this section
                            sentences = re.split(r'[.!?]\s+', section_text)
                            for sentence in sentences:
                                sentence = sentence.strip()
                                if len(sentence) < 20 or len(sentence) > 250:
                                    continue
                                sentence_lower = sentence.lower()
                                # Check for scope actions
                                if any(action in sentence_lower for action in scope_actions):
                                    sentence_clean = ' '.join(sentence.split())
                                    if not any(sentence_clean.lower() in existing.lower() or existing.lower() in sentence_clean.lower() for existing in scope_items):
                                        scope_items.append(sentence_clean)
                        
                        # Start new scope section
                        in_scope_section = True
                        current_section_lines = [line]
                    elif in_scope_section:
                        # Continue collecting section content
                        if line.strip():
                            current_section_lines.append(line)
                        # Stop if we hit another major section (all caps header)
                        elif len(line_upper) > 5 and line_upper.isupper() and not line_upper.startswith('THE '):
                            in_scope_section = False
                            current_section_lines = []
                    else:
                        # Not in scope section, but check for standalone scope sentences
                        if any(action in line_lower for action in scope_actions):
                            sentence_clean = ' '.join(line.split())
                            if len(sentence_clean) >= 20 and len(sentence_clean) <= 250:
                                if not any(sentence_clean.lower() in existing.lower() or existing.lower() in sentence_clean.lower() for existing in scope_items):
                                    scope_items.append(sentence_clean)
        
        log_ctx.info(f"Text structuring: Found {len(scope_items)} scope items from text")
        if scope_items:
            log_ctx.info(f"First 3 scope items: {scope_items[:3]}")
        
        # Format structured output - make it VERY prominent
        structured = "\n" + "="*80 + "\n"
        structured += "**CRITICAL: SCOPE ITEMS TO EXTRACT (NUMBERED LIST BELOW)**\n"
        structured += "="*80 + "\n\n"
        
        if scope_items:
            structured += "**EXTRACT EACH NUMBERED ITEM BELOW AS A SCOPE ITEM:**\n\n"
            for i, item in enumerate(scope_items[:30], 1):  # Limit to 30 items
                structured += f"**SCOPE ITEM {i}:** {item}\n\n"
            structured += "\n" + "="*80 + "\n"
            structured += "**END OF SCOPE ITEMS LIST - EXTRACT ALL ITEMS ABOVE**\n"
            structured += "="*80 + "\n\n"
        else:
            structured += "**SCOPE ITEMS DETECTED IN TEXT:**\n"
            structured += "(No scope items detected in structured format - extract from full text below)\n\n"
        
        # Also include full text for materials/quantities extraction
        selected_page_texts = []
        for page_idx in page_indices:
            if 0 <= page_idx < len(page_texts):
                text = page_texts[page_idx]
                if text and text.strip():
                    selected_page_texts.append(f"Page {page_idx + 1} text:\n{text}")
        
        if selected_page_texts:
            structured += "**FULL TEXT FOR MATERIALS/QUANTITIES EXTRACTION:**\n"
            structured += "\n\n---\n\n".join(selected_page_texts)
        
        return structured
    
    def _create_extraction_prompt_pass_a(self, page_indices: list[int], primary_trade: str | None = None, page_texts: list[str] | None = None) -> str:
        """Create prompt for Pass A: Targeted Read from locator pages."""
        pages_str = ", ".join(str(p + 1) for p in page_indices)  # 0-indexed to 1-indexed
        
        # Structure text for easier extraction (makes scope items look like materials)
        extracted_text_section = ""
        if page_texts:
            # Get project_id from context if available (for logging)
            project_id = getattr(self, '_current_project_id', 'unknown')
            structured_text = self._structure_text_for_extraction(page_texts, page_indices, project_id)
            extracted_text_section = f"\n\n{structured_text}\n\n**END OF STRUCTURED TEXT**\n\n"
        
        # If primary trade is roofing, prioritize roof scope extraction
        if primary_trade == "roofing":
            return f"""You are extracting detailed information from a ROOF REPLACEMENT construction document.

**CRITICAL: This is a ROOF REPLACEMENT project (Division 07 - Roofing is PRIMARY).**
Masonry elements (parapets, flashing) are SUPPORTING SCOPE, not primary scope.

You are analyzing pages {pages_str} which were identified in Stage 1 as containing scope, materials, quantities, or geometry information.

Extract ALL visible information from these pages, PRIORITIZING ROOF SCOPE:

1. SCOPE OF WORK (ROOF PRIMARY):
   - **ROOF MEMBRANE REMOVAL / TEAR-OFF (CRITICAL)**:
     * Extract tear-off scope: "full" (entire roof), "partial" (specific areas), "none" (overlay/no tear-off)
     * Look for: "remove existing roof", "roof removal", "strip roof", "tear-off", "demolition", "overlay", "no tear-off"
     * Include EXACT evidence quote showing tear-off scope
     * If tear-off scope not specified, mark as "unknown" and note in evidence
   - **DISPOSAL REQUIREMENTS (if mentioned)**:
     * Extract disposal requirements: "dumpster required", "off-site disposal", "recycling required", "carting", "hoisting"
     * Include EXACT evidence quote if disposal is mentioned
     * If not mentioned, mark as null
   - **ROOF MEMBRANE INSTALLATION** (CRITICAL: Look for "EPDM", "TPO", "PVC", "modified bitumen", "built-up roof", "BUR", "single-ply", "roof membrane", "roofing system")
   - **ROOF INSULATION** (CRITICAL: Look for "roof insulation", "insulation replacement", "rigid insulation", R-values)
   - **ROOF AREA** (CRITICAL: Look for "roof area", "roof SF", "square feet", roof plan dimensions, roof outline)
   - **ROOF DRAINS** (Look for "roof drain", "drain modifications", "drain replacement")
   - **EXPANSION JOINTS** (as roof system, not just detail)
   - **ROOF EDGE METAL** (Look for "roof edge", "coping", "fascia", "gravel stop")
   - **ROOF PENETRATIONS** (Look for "penetration", "curb", "roof penetration")
   - **QUONSET/DOME ROOF** (if present - look for curved roof geometry)
   - Supporting scope: Parapet repair/replacement (supporting, not primary)
   - Supporting scope: Flashing installation/repair (supporting, not primary)
   - Supporting scope: Lintel replacement/repair (if present)
   - Supporting scope: Brick rebuild (if present)
   - Supporting scope: Repointing (if present)

2. MATERIAL SPECIFICATIONS (ROOF PRIMARY):
   - **ROOF MEMBRANE SYSTEM TYPE (REQUIRED)**:
     * Extract EXACT system type: "TPO", "EPDM", "PVC", "Modified bitumen", "Built-up roof" (BUR), "Single-ply", "Metal"
     * Look for explicit mentions in specs, details, or notes
     * Include EXACT evidence quote (e.g., "60 mil EPDM membrane per ASTM D4637")
     * If system type is NOT explicitly stated, mark as "Unknown" and note in evidence why it's unknown
   - **ROOF INSULATION (REQUIRED)**:
     * Extract insulation THICKNESS in inches (e.g., "2 inch", "3.5 inch", "4 inches")
     * Extract insulation MATERIAL type (e.g., "polyiso", "polyisocyanurate", "XPS", "EPS", "rigid insulation")
     * Extract R-VALUE if mentioned (e.g., "R-20", "R-30")
     * Extract NUMBER OF LAYERS if mentioned (e.g., "2 layers", "double layer")
     * Include EXACT evidence quote from specs or details
     * If thickness/material NOT found, mark as null but note in evidence that it's missing
   - **ROOF DRAIN MATERIALS** (Look for drain specifications)
   - **ROOF EDGE METAL** (Look for coping, fascia, gravel stop specifications)
   - Supporting: Mortar types (Type N, Type S, etc.) - if masonry work present
   - Supporting: Brick specifications - if masonry work present
   - Supporting: Lintel materials - if lintel work present
   - Supporting: Flashing materials - supporting scope
   - Supporting: Sealants
   - Any product codes or spec references

3. QUANTITY TAKEOFF (ROOF PRIMARY):
   - **ROOF AREA (CRITICAL - REQUIRED)** - Extract roof square footage (SF) from roof plan, dimensions, or calculations
     * **MANDATORY**: You MUST extract or calculate roof area. If not explicitly stated:
       - Look for roof plan dimensions (length × width)
       - Look for building footprint dimensions (use as roof area if no roof plan)
       - Look for area callouts on roof plan (e.g., "8,000 SF", "10,000 sq ft")
       - Calculate from visible dimensions: area = length × width
       - If only partial dimensions visible, estimate and mark as computed with low confidence
     * **NEVER return null for roof area if this is a roof project** - always provide a value, even if estimated
   - **ROOF PERIMETER LENGTH (CRITICAL)** - Extract roof perimeter in linear feet (LF) from roof plan outline or building dimensions
     * Look for: "perimeter", "edge length", "roof edge", "building perimeter", or calculate from roof plan outline
     * If not explicitly stated, calculate from building width/depth: perimeter = 2 × (width + depth)
     * Include formula and input dimensions if calculated
   - **EDGE METAL / COPING LINEAR FEET** - Extract if mentioned (e.g., "edge metal 200 LF", "coping 150 LF")
   - **BASE FLASHING LINEAR FEET** - Extract if mentioned (e.g., "base flashing 180 LF", "flashing at perimeter")
   - **ROOF MEMBRANE AREA** - Usually same as roof area
   - **ROOF INSULATION AREA** - Usually same as roof area
   - **ROOF DRAIN COUNT** - Number of drains
   - **ROOF PENETRATION COUNT** - Number of penetrations
   - Extract explicit dimensions if visible
   - Calculate quantities ONLY if you have clear evidence (dimensions visible)
   - Include formula and input dimensions for any calculations
   - If roof area is not explicitly stated, calculate from roof plan dimensions

4. GEOMETRY FOR 3D (ROOF PRIMARY):
   - **ROOF PLANE DIMENSIONS** (width, depth, area) - CRITICAL for roof projects
   - **ROOF SLOPE/PITCH** (if visible)
   - **ROOF ZONES** (if roof has different areas/zones)
   - **QUONSET/DOME GEOMETRY** (if curved roof - radius, arc length)
   - Building dimensions (width, depth, height) if explicit
   - Supporting: Work zones (parapet band, lintel band, facade regions) - if masonry work present
   - Supporting: Row context (building IDs, addresses, subject building) - if applicable

Return ONLY valid JSON matching this schema:

{{
  "scope_of_work": [
    {{
      "item": "roof membrane removal" or "roof tear-off" or "roof demolition",
      "description": "Remove existing roof membrane - MUST specify scope: 'full' (entire roof), 'partial' (specific areas), or 'none' (overlay). Include disposal requirements if mentioned.",
      "location": "entire roof" or "roof area" or "specific zones",
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Exact quoted text showing tear-off scope and disposal (e.g., 'Remove existing roof membrane - entire roof' or 'Tear-off existing roof and dispose off-site' or 'Overlay new membrane - no tear-off required')"
    }},
    {{
      "item": "roof membrane installation",
      "description": "Install new [EPDM/TPO/PVC/modified bitumen] roof membrane - MUST include system type",
      "location": "entire roof" or "roof area",
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Exact quoted text mentioning roof membrane type (e.g., '60 mil EPDM membrane per ASTM D4637' or 'TPO single-ply membrane' or 'Modified bitumen 2-ply system')"
    }},
    {{
      "item": "roof insulation",
      "description": "Install roof insulation - MUST include thickness (inches), material type, R-value if mentioned, and number of layers if mentioned",
      "location": "entire roof" or "roof area",
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Exact quoted text with thickness and material (e.g., '2 inch polyisocyanurate insulation R-20' or '3.5 inch rigid insulation' or '2 layers of 2 inch polyiso')"
    }},
    {{
      "item": "roof area",
      "description": "Roof replacement area",
      "location": "entire roof",
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Roof plan or dimension callout"
    }}
  ],
  "material_specifications": [
    {{
      "material_name": "EPDM Roof Membrane" or "TPO Roof Membrane" or "PVC Roof Membrane" or "Modified Bitumen Roof Membrane" or "Built-up Roof Membrane" or "Metal Roof Membrane" or "Single-ply Roof Membrane",
      "specification": "60 mil EPDM" or "ASTM D4637" or "TPO 60 mil" or "PVC membrane" or product code - MUST include system type,
      "application": "Roof membrane",
      "detail_sheet": "D-1" or null,
      "page_number": 2,
      "sheet_id": "A-2" or null,
      "evidence_snippet": "Exact quoted spec text with system type (e.g., '60 mil EPDM membrane per ASTM D4637' or 'TPO single-ply membrane 60 mil' or 'Modified bitumen 2-ply system'). If system type not found, quote what IS present and note 'system type not specified'"
    }},
    {{
      "material_name": "Roof Insulation" or "Polyisocyanurate Insulation" or "Polyiso Insulation" or "XPS Insulation" or "EPS Insulation" or "Rigid Insulation",
      "specification": "R-20 rigid insulation" or "2 inch polyiso" or "3.5 inch polyisocyanurate R-30" or "2 layers 2 inch polyiso" - MUST include thickness in inches and material type if available,
      "application": "Roof insulation",
      "detail_sheet": "D-1" or null,
      "page_number": 2,
      "sheet_id": "A-2" or null,
      "evidence_snippet": "Exact quoted text with thickness (inches), material type, R-value if mentioned, and layers if mentioned (e.g., '2 inch polyisocyanurate insulation R-20' or '3.5 inch rigid insulation' or '2 layers of 2 inch polyiso R-20 each'). If thickness/material not found, quote what IS present and note what's missing"
    }}
  ],
  "quantity_takeoff": [
    {{
      "item": "Roof area",
      "quantity": 8000.0,  // REQUIRED: MUST provide a value, never null. If not explicitly stated, calculate from dimensions or estimate from building footprint
      "unit": "sq ft" or "SF",
      "is_computed": true,  // Set to true if calculated or estimated
      "computation_formula": "length * width" or "estimated from building footprint" or "from roof plan dimensions",
      "input_dimensions": {{"length": 100, "width": 80}} or {{"estimated": true}},
      "evidence_missing": false,  // Set to false if you calculated/estimated from available dimensions
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Roof plan dimensions or area callout or calculation formula"
    }},
    {{
      "item": "Roof perimeter" or "Roof edge length" or "Building perimeter",
      "quantity": 360.0 or null,
      "unit": "lf" or "linear feet" or "LF",
      "is_computed": true/false,
      "computation_formula": "2 * (width + depth)" or "from roof plan outline" or null,
      "input_dimensions": {{"width": 100, "depth": 80}} or {{}},
      "evidence_missing": true/false,
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Roof plan perimeter or building dimensions"
    }},
    {{
      "item": "Edge metal" or "Coping" or "Roof edge metal",
      "quantity": 360.0 or null,
      "unit": "lf" or "linear feet" or "LF",
      "is_computed": false,
      "computation_formula": null,
      "input_dimensions": {{}},
      "evidence_missing": true/false,
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Edge metal or coping specification"
    }},
    {{
      "item": "Base flashing" or "Perimeter flashing",
      "quantity": 360.0 or null,
      "unit": "lf" or "linear feet" or "LF",
      "is_computed": false,
      "computation_formula": null,
      "input_dimensions": {{}},
      "evidence_missing": true/false,
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Base flashing specification"
    }}
  ],
  "geometry_for_3d": {{
    "site_context": {{
      "building_type": "commercial" or "institutional" or "row_house" or null,
      "row_of_buildings": ["B-1", "B-2"] or [],
      "subject_building_id": "B-2" or null,
      "addresses": ["123 Main St"] or [],
      "evidence": "Evidence for site context"
    }},
    "building_dimensions": {{
      "width": 100.0 or null,
      "depth": 80.0 or null,
      "height": 30.0 or null,
      "roof_area": 8000.0,  // REQUIRED: MUST provide a value, never null. Calculate from roof plan dimensions if not explicitly stated
      "roof_slope": "flat" or "1/4:12" or null,
      "evidence": "Where dimensions were found"
    }},
    "work_zones": [
      {{
        "zone_name": "roof_plane",
        "facade_region": "entire roof",
        "z_min": 0.0 or null,
        "z_max": 30.0 or null,
        "area": 8000.0 or null,
        "evidence": "Roof plan"
      }}
    ]
  }},
  "warranty_and_insurance": {{
    "warranty": {{
      "manufacturer_warranty": "20-year EPDM membrane warranty" or "15-year TPO warranty" or null,
      "manufacturer_warranty_duration": "20 years" or "15 years" or "lifetime" or null,
      "workmanship_warranty": "2-year workmanship warranty" or "5-year installation warranty" or null,
      "workmanship_warranty_duration": "2 years" or "5 years" or null,
      "warranty_evidence": "Page 5, Section 07 50 00: 'Manufacturer warranty: 20-year EPDM membrane warranty' or 'Workmanship warranty: 2 years' or null"
    }},
    "insurance": {{
      "general_liability_required": true/false,
      "general_liability_limit": "$2,000,000" or "$5,000,000" or null,
      "workers_compensation_required": true/false,
      "workers_compensation_limit": "$1,000,000" or null,
      "umbrella_insurance_required": true/false,
      "umbrella_insurance_limit": "$5,000,000" or null,
      "insurance_evidence": "Page 1, General Requirements: 'Contractor shall maintain general liability insurance of $2,000,000' or null"
    }},
    "bonds": {{
      "performance_bond_required": true/false,
      "performance_bond_amount": "100% of contract" or "$500,000" or null,
      "payment_bond_required": true/false,
      "payment_bond_amount": "100% of contract" or "$500,000" or null,
      "bond_evidence": "Page 1, General Requirements: 'Performance bond required: 100% of contract value' or null"
    }}
  }}
}}

CRITICAL FOR ROOF PROJECTS:
- You MUST extract roof area (SF) - this is the PRIMARY quantity
- If roof area is not explicitly stated, calculate from roof plan dimensions
- **SYSTEM TYPE IS REQUIRED**: Extract exact roof membrane system type (TPO/EPDM/PVC/etc) with evidence quotes. If not found, mark as "Unknown" and explain why in evidence.
- **INSULATION THICKNESS IS REQUIRED**: Extract insulation thickness in inches, material type (polyiso/XPS/EPS), R-value if mentioned, and number of layers if mentioned. Include exact evidence quotes. If not found, mark thickness as null but note in evidence what IS present and what's missing.
- Roof membrane, insulation, and most roof work is priced per SF of roof area
- Parapet repair, flashing, etc. are SUPPORTING scope, not primary
- If you see "quonset" or "dome" roof, note the curved geometry
- **CONFIDENCE PENALTY**: If system type or insulation thickness is missing, this reduces pricing accuracy - note this clearly in evidence

TASK 8: WARRANTY & INSURANCE EXTRACTION (REQUIRED):
- **WARRANTY**: Look for manufacturer warranty (e.g., "20-year EPDM warranty", "15-year TPO warranty") and workmanship warranty (e.g., "2-year workmanship warranty", "5-year installation warranty") in specifications, general requirements, or warranty sections. Extract duration and details with evidence.
- **INSURANCE**: Look for insurance requirements in general requirements, contract terms, or bid documents. Extract:
  * General liability insurance (required yes/no, limit if specified)
  * Workers compensation insurance (required yes/no, limit if specified)
  * Umbrella insurance (required yes/no, limit if specified)
- **BONDS**: Look for bond requirements in general requirements or contract terms. Extract:
  * Performance bond (required yes/no, amount if specified)
  * Payment bond (required yes/no, amount if specified)
- Include page numbers and evidence snippets for all warranty/insurance/bond information found
- If not found, set fields to null/false but note in evidence that warranty/insurance/bond requirements were not found in documents

CRITICAL: Return ONLY the JSON object. No markdown, no code blocks, no explanation, no text before or after the JSON. Start with {{ and end with }}."""

        elif primary_trade == "masonry":
            return f"""You are extracting detailed information from a MASONRY REPAIR/RECONSTRUCTION construction document.

**CRITICAL: This is a MASONRY project (Division 04 - Masonry is PRIMARY).**
Window openings in elevation drawings are just showing the building facade - they are NOT window replacement work.
Lintel replacement is STRUCTURAL STEEL (Division 05) supporting masonry, NOT window replacement (Division 08).

{extracted_text_section}

**CRITICAL EXTRACTION RULES - READ IN THIS ORDER:**

1. **PRIMARY SOURCE = TEXT SECTIONS (READ FIRST)**
   - Read "MASONRY NOTES" section completely - this defines the PRIMARY scope
   - Read "BRICK NOTES" section completely - this defines materials and methods
   - Read "SCOPE OF WORK" section - this explicitly states what work is being done
   - Read "STRUCTURAL STEEL NOTES" or "LINTEL SCHEDULE" - this is supporting structural work
   - **TEXT TAKES PRIORITY OVER VISUAL ELEMENTS**
   - If text says "MASONRY NOTES" or "BRICK REPAIR", that's the PRIMARY scope, not windows

2. **ONLY EXTRACT IF EXPLICITLY STATED IN TEXT**
   - "Type N mortar" = extract mortar type
   - "Replace window lintels" = extract LINTEL work (Division 05 - Structural Steel), NOT window replacement
   - "W-1 Qty 12" = only extract if in an actual TABLE/schedule
   - **DO NOT invent window schedules** - only extract if you see an actual schedule table
   - **DO NOT extract windows** just because you see window openings in elevation drawings

3. **DISTINGUISH STRUCTURAL VS FINISHES**
   - "Window lintels" = Division 05 (Structural Steel) - these are BEAMS above openings
   - "Window replacement" = Division 08 (Openings) - this is replacing window units
   - **CRITICAL: "Replace 2nd Floor Window Lintels" means replace the STEEL BEAMS, NOT the windows**
   - This project is about LINTELS (structural support for masonry), not window replacement

4. **MASONRY SCOPE ITEMS TO FIND (in order of priority):**
   - Brick repair/replacement (from "MASONRY NOTES" or "BRICK NOTES")
   - Mortar type and specifications (Type N, Type M, ASTM C270, etc.)
   - Wall reconstruction (rebuild outer wythe, wall repair)
   - Parapet reconstruction/repair
   - Masonry units (CMU, concrete block)
   - Pointing/repointing
   - Crack repair
   - Lintel replacement (structural steel - Division 05, supporting masonry)

You are analyzing pages {pages_str} which were identified in Stage 1 as containing scope, materials, quantities, or geometry information.

**EXTRACTION PROCESS (FOLLOW THIS ORDER EXACTLY):**

1. **FIRST - EXTRACT SCOPE ITEMS FROM NUMBERED LIST:**
   - **CRITICAL**: Look for the section marked "**CRITICAL: SCOPE ITEMS TO EXTRACT (NUMBERED LIST BELOW)**"
   - **MANDATORY**: Extract EVERY item marked "**SCOPE ITEM 1:**", "**SCOPE ITEM 2:**", etc.
   - **FORMAT**: Each numbered item should become one entry in your `scope_of_work` array
   - **EXAMPLE**: If you see "**SCOPE ITEM 1:** Rebuild outer wythe of brick", extract:
     ```json
     {{
       "item": "Brick wall reconstruction",
       "description": "Rebuild outer wythe of brick",
       "page_number": 1,
       "evidence_snippet": "Rebuild outer wythe of brick"
     }}
     ```
   - **EXAMPLE**: If you see "**SCOPE ITEM 2:** Replace window lintels", extract:
     ```json
     {{
       "item": "Lintel replacement",
       "description": "Replace window lintels",
       "page_number": 1,
       "evidence_snippet": "Replace window lintels"
     }}
     ```
   - **IMPORTANT**: Extract ALL numbered scope items - if you see 10 numbered items, return 10 scope items

2. **SECOND**: Read the "FULL TEXT FOR MATERIALS/QUANTITIES EXTRACTION" section for materials and quantities

3. **THIRD**: Analyze the images to see elevations, details, and drawings for additional context

**CRITICAL VALIDATION:**
- If the structured text shows numbered scope items (e.g., "**SCOPE ITEM 1:**", "**SCOPE ITEM 2:**"), you MUST extract them
- The number of scope items you return should match (or be close to) the number of numbered items in the structured text
- If you see 10 numbered scope items but return 0 scope items, your extraction is INCORRECT

Extract ALL visible information, PRIORITIZING MASONRY SCOPE:

1. SCOPE OF WORK (MASONRY PRIMARY):
   - **BRICK WALL RECONSTRUCTION / REPAIR** (CRITICAL):
     * Extract scope: "rebuild outer wythe", "brick wall reconstruction", "brick repair", "wall reconstruction", "repointing", "brick pointing"
     * Look for: "MASONRY NOTES", "BRICK NOTES", "BRICK REPAIR DETAILS", "SCOPE OF WORK" mentioning brick/masonry
     * Include EXACT evidence quote showing masonry scope
   - **PARAPET RECONSTRUCTION / REPAIR** (CRITICAL):
     * Extract scope: "parapet reconstruction", "parapet repair", "rebuild parapet"
     * Look for parapet details, parapet sections
     * Include EXACT evidence quote
   - **LINTEL REPLACEMENT** (Supporting - Division 05):
     * Extract scope: "lintel replacement", "replace lintels", "steel lintel installation"
     * Note: Lintels are STRUCTURAL STEEL supports, NOT window replacement
     * Include lintel schedule if present
   - **REPOINTING / BRICK POINTING** (if mentioned)
   - **WALL AREA / LINEAR FEET** (CRITICAL: Extract masonry wall area in SF or linear feet)
   - Supporting scope: Flashing installation/repair (supporting, not primary)
   - Supporting scope: Window work (ONLY if explicitly mentioned as window replacement, not just lintels)

2. MATERIAL SPECIFICATIONS (MASONRY PRIMARY):
   - **BRICK SPECIFICATIONS (REQUIRED)**:
     * Extract brick type: "structural facing brick", "solid brick", "CMU", "concrete block", "brick matching existing"
     * Extract brick standards: ASTM C62, ASTM C216, etc.
     * Extract brick pattern: "running bond", "Flemish bond", etc.
   - **MORTAR SPECIFICATIONS (REQUIRED)**:
     * Extract mortar type: "Type M", "Type N", "Type S" (below ground vs above ground)
     * Extract mortar standard: ASTM C270
     * Include EXACT evidence quote
   - **LINTEL MATERIALS** (Supporting - Division 05):
     * Extract lintel material: "hot dip galvanized structural steel", "steel lintel", lintel sizes
     * Extract lintel schedule if present
   - **FLASHING MATERIALS** (Supporting)
   - **CMU / CONCRETE BLOCK** (if mentioned)
   - Any product codes or spec references

3. QUANTITY TAKEOFF (MASONRY PRIMARY):
   - **MASONRY WALL AREA (CRITICAL - REQUIRED)** - Extract masonry square footage (SF) from elevations, dimensions, or calculations
     * **MANDATORY**: You MUST extract or calculate masonry wall area. If not explicitly stated:
       - Look for elevation dimensions (height × width)
       - Look for wall area callouts
       - Calculate from building dimensions if available
       - If area cannot be determined, mark as null but note in evidence
   - **MASONRY LINEAR FEET** (if mentioned - parapet length, wall length)
   - **LINTEL QUANTITY** (Supporting - count from lintel schedule or openings)
   - **BRICK QUANTITY** (if mentioned in SF or units)
   - **PARAPET HEIGHT / LENGTH** (if mentioned)
   - **REPOINTING AREA** (if mentioned)

4. GEOMETRY / EVIDENCE LINKAGE:
   - Capture elevations showing masonry work, wall sections, parapet details
   - Note alignment with building elevations or grids when stated
   - Link to detail sheets (e.g., "S-011 Detail 4 - Parapet Reconstruction")

**CRITICAL: DO NOT extract window schedules unless you see an actual TABLE with window marks and quantities.**
**Window openings in elevation drawings are NOT a window schedule.**
**"Window lintels" means STRUCTURAL STEEL lintels, NOT window replacement.**

**FINAL CHECKLIST BEFORE RETURNING:**
- Did you read the "MASONRY NOTES" or "BRICK NOTES" text sections? (These are PRIMARY)
- Did you extract mortar specifications? (Type N, Type M, ASTM C270, etc.)
- Did you extract brick repair/reconstruction scope? (rebuild outer wythe, wall repair, etc.)
- Did you distinguish lintels (structural steel) from windows (openings)?
- Did you avoid inventing window schedules that don't exist?

Return ONLY valid JSON matching the same schema as roofing/windows prompts above, but with masonry-specific items.

**CRITICAL JSON FORMATTING RULES:**
- ALL strings MUST be properly closed with double quotes "
- NO newlines inside string values - use \\n for line breaks
- ALL commas MUST be present between array/object items
- NO trailing commas
- ALL braces and brackets MUST be properly closed
- Test your JSON before returning - it MUST be valid JSON that can be parsed

**EXAMPLE OF CORRECT JSON FORMAT:**
```json
{{
  "scope_of_work": [
    {{
      "item": "Brick wall reconstruction",
      "description": "Rebuild outer wythe of brick from 2nd floor window lintels to bottom of parapet",
      "page_number": 1,
      "evidence_snippet": "Rebuild outer wythe of brick"
    }}
  ]
}}
```

**DO NOT RETURN:**
- Strings with unescaped newlines
- Missing commas between items
- Unclosed quotes
- Invalid JSON syntax

Return ONLY valid, parseable JSON.
"""



        elif primary_trade == "windows":
            return f"""You are extracting detailed information from a WINDOW SYSTEM construction document.

**CRITICAL: Division 08 (Windows / Openings) is the PRIMARY scope.**
Any masonry or envelope notes are SUPPORTING context.

You are analyzing pages {pages_str} that Stage 1 flagged for scope, materials, quantities, schedules, or elevations.

Extract ALL relevant information, prioritizing WINDOWS:

1. SCOPE OF WORK (WINDOW PRIMARY):
   - **EXISTING WINDOW REMOVAL / DEMO** (look for "remove windows", "demo glazing", "replace storefront")
   - **NEW WINDOW / GLAZING INSTALLATION** (capture window types, series, performance notes)
   - **CURTAIN WALL / STOREFRONT SYSTEMS** (note systems, anchorage, sealant requirements)
   - **OPENING PREP & PATCH / FLASHING / AIR BARRIER TIE-INS** (record substrate or waterproofing requirements)
   - Supporting scope: Interior/exterior trim, sill replacement, hardware upgrades, protection requirements
   - Include exact evidence snippets for every scope item. If critical window scope is missing, note it in `evidence_missing` (e.g., "window_scope").

2. MATERIAL SPECIFICATIONS (WINDOW PRIMARY):
   - **FRAME / SYSTEM** (aluminum, thermally broken, vinyl, wood, storefront, curtain wall) with finish/spec references (AAMA, ASTM)
   - **GLASS / GLAZING** (IGU, laminated, tempered, low-E, SHGC/U-factor values)
   - **HARDWARE / ACCESSORIES** (operable type, mullions, anchors, sealants, weather-stripping)
   - Include sheet references or detail callouts. If key materials not specified, add to `evidence_missing` (e.g., "window_materials").

3. WINDOW SCHEDULE / QUANTITIES (MANDATORY):
   - Locate every window schedule table, tag legend, or elevation callout. For **each** schedule row or tag, extract:
     * `window_mark` (e.g., "W-1", "WP-101", "CW-1") – embed this in the `item` field (e.g., "W-1 windows").
     * Description/type (operable type, series, remarks) – capture in `item` or `description`.
     * Width & height (inches) or module size – store in `input_dimensions` (e.g., `{{"width_in": 36, "height_in": 60}}`).
     * Quantity (numeric) – set `quantity` to the count listed; set `unit` to "ea" (or LF/SF if specified).
     * Any comments (fire rating, glazing performance) – include in `description`.
   - Create one `quantity_takeoff` entry per mark (or per elevation if grouped). Do **not** skip rows even if partially filled—capture available data and set missing fields to null or leave them off.
   - Set `evidence_missing` to **false** when a schedule value (quantity or size) is captured. Only mark it true if the schedule truly omits the quantity and no count can be inferred.
   - If no schedule is present after reviewing the supplied pages, add "window_schedule" and "window_quantities" to `evidence_missing`.

4. ADDITIONAL QUANTITY HINTS:
   - Counts of existing vs new windows, phased replacements, storefront lengths.
   - Curtain wall or ribbon window spans (LF) and elevations.
   - Any glazing area totals (SF). Provide formulas and dimensions when calculated.

5. GEOMETRY / EVIDENCE LINKAGE:
   - Capture elevations/sections showing head/sill/jamb details, anchor diagrams, typical conditions.
   - Note alignment with building elevations or grids when stated.

6. WARRANTY / PERFORMANCE NOTES (if present): NFRC ratings, warranty durations, testing standards (ASTM E1105, AAMA 502, etc.).

**STRICT JSON OUTPUT REQUIREMENT**
Return ONLY valid JSON matching this schema (no markdown, no text before/after):

{{
  "scope_of_work": [
    {{
      "item": "Remove existing double-hung windows",
      "description": "Demo W-1 units and prep openings for new thermally broken frames",
      "location": "South elevation",
      "page_number": 4,
      "sheet_id": "A-4",
      "evidence_snippet": "Remove existing windows and install new thermally broken frames"
    }}
  ],
  "material_specifications": [
    {{
      "material_name": "Thermally broken aluminum frame",
      "specification": "AAMA 2605 powder coat",
      "application": "New W-1 window units",
      "detail_sheet": "A-2",
      "page_number": 2,
      "sheet_id": "A-2",
      "evidence_snippet": "Provide thermally broken aluminum frames per AAMA 2605"
    }}
  ],
  "quantity_takeoff": [
    {{
      "item": "W-1 windows",
      "quantity": 12,
      "unit": "ea",
      "is_computed": false,
      "computation_formula": null,
      "input_dimensions": {{"width_in": 36, "height_in": 60}},
      "evidence_missing": false,
      "page_number": 1,
      "sheet_id": "A-1",
      "evidence_snippet": "W-1 3'-0\" x 5'-0\" Qty 12 double-hung"
    }}
  ],
  "geometry_for_3d": {{...}},
  "evidence_missing": []
}}

Populate all arrays with **at least one entry** when window notes or schedules are visible. Populate as much detail as present; leave values null rather than inventing data.
"""

        # Default prompt for masonry/row-house repair (existing logic)
        return f"""You are extracting detailed information from a row-house repair construction document.

You are analyzing pages {pages_str} which were identified in Stage 1 as containing scope, materials, quantities, or geometry information.

Extract ALL visible information from these pages:

1. SCOPE OF WORK:
   - Parapet repair/replacement
   - Lintel replacement/repair (CRITICAL: Look for "lintel", "replace lintel", "steel lintel", "typical lintel detail", "detail 1/2/3", "angle", steel angle sizes like "L3x3x1/4", schedule references like "S-011")
   - Brick rebuild
   - Repointing (tuckpointing)
   - Crack repairs
   - Flashing installation/repair
   - Any other repair work mentioned

2. MATERIAL SPECIFICATIONS:
   - Mortar types (Type N, Type S, etc.)
   - Brick specifications
   - Lintel materials (CRITICAL: steel angles, sizes like "L3x3x1/4", ASTM specs, schedule references like "S-011", "typical lintel detail")
   - Flashing materials
   - Sealants
   - Any product codes or spec references

3. QUANTITY TAKEOFF:
   - Extract explicit dimensions if visible
   - Calculate quantities ONLY if you have clear evidence (dimensions visible)
   - Include formula and input dimensions for any calculations

4. GEOMETRY FOR 3D:
   - Building dimensions (width, depth, height) if explicit
   - Work zones (parapet band, lintel band, facade regions)
   - Lintel zone: If lintels are found, create a work zone with zone_name="lintel_band" and facade_region="lintel band" or z_min/z_max if height info exists
   - Row context (building IDs, addresses, subject building)

5. WARRANTY & INSURANCE (TASK 8):
   - **WARRANTY**: Look for manufacturer warranty (e.g., "20-year warranty", "15-year warranty") and workmanship warranty (e.g., "2-year workmanship warranty") in specifications, general requirements, or warranty sections. Extract duration and details with evidence.
   - **INSURANCE**: Look for insurance requirements in general requirements, contract terms, or bid documents. Extract general liability, workers compensation, and umbrella insurance requirements with limits if specified.
   - **BONDS**: Look for bond requirements (performance bond, payment bond) in general requirements or contract terms. Extract requirements and amounts if specified.
   - Include page numbers and evidence snippets for all warranty/insurance/bond information found.
   - If not found, set fields to null/false but note in evidence that warranty/insurance/bond requirements were not found in documents.

Return ONLY valid JSON matching this schema:

{{
  "scope_of_work": [
    {{
      "item": "parapet repair",
      "description": "Full description",
      "location": "front facade",
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Exact text or callout"
    }},
    {{
      "item": "lintel replacement",
      "description": "Full description including count if visible",
      "location": "window openings" or "door openings" or null,
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Exact text mentioning lintel, steel angle, schedule, or detail"
    }}
  ],
  "material_specifications": [
    {{
      "material_name": "Type N Mortar",
      "specification": "ASTM C270",
      "application": "Repointing",
      "detail_sheet": "D-1" or null,
      "page_number": 2,
      "sheet_id": "A-2" or null,
      "evidence_snippet": "Exact spec text"
    }},
    {{
      "material_name": "Steel Lintel" or "Steel Angle Lintel",
      "specification": "L3x3x1/4" or "ASTM A36" or "S-011" or schedule reference or null,
      "application": "Window lintel replacement" or "Door lintel replacement",
      "detail_sheet": "D-1" or "S-011" or null,
      "page_number": 2,
      "sheet_id": "A-2" or null,
      "evidence_snippet": "Exact text mentioning lintel material, size, or schedule"
    }}
  ],
  "quantity_takeoff": [
    {{
      "item": "Brick replacement",
      "quantity": 150.0 or null,
      "unit": "sq ft",
      "is_computed": true/false,
      "computation_formula": "width * height" or null,
      "input_dimensions": {{"width": 20, "height": 7.5}} or {{}},
      "evidence_missing": true/false,
      "page_number": 1,
      "sheet_id": "A-1" or null,
      "evidence_snippet": "Dimension callout or calculation evidence"
    }}
  ],
  "geometry_for_3d": {{
    "site_context": {{
      "building_type": "row_house",
      "row_of_buildings": ["B-1", "B-2"] or [],
      "subject_building_id": "B-2" or null,
      "addresses": ["123 Main St"] or [],
      "evidence": "Evidence for site context"
    }},
    "dimensions": {{
      "width": 20.0 or null,
      "depth": 40.0 or null,
      "height": 30.0 or null,
      "evidence": "Where found",
      "computation_formula": null or "sum(elevation_dimensions)",
      "input_pages": [1, 2] or []
    }} or null,
    "work_zones": [
      {{
        "zone_name": "parapet_band",
        "z_min": 28.0 or null,
        "z_max": 30.0 or null,
        "facade_region": "parapet band" or null,
        "page_number": 1,
        "sheet_id": "A-1" or null,
        "evidence": "Evidence for zone"
      }},
      {{
        "zone_name": "lintel_band",
        "z_min": 8.0 or null,
        "z_max": 10.0 or null,
        "facade_region": "lintel band" or null,
        "page_number": 1,
        "sheet_id": "A-1" or null,
        "evidence": "Evidence for lintel zone (mention lintel, steel angle, schedule, or detail)"
      }}
    ],
    "evidence_missing": ["height", "work_zone_z_ranges"] or []
  }},
  "evidence_missing": ["parapet_repair", "lintels"] or [],
  "warranty_and_insurance": {{
    "warranty": {{
      "manufacturer_warranty": "20-year warranty" or "15-year warranty" or null,
      "manufacturer_warranty_duration": "20 years" or "15 years" or "lifetime" or null,
      "workmanship_warranty": "2-year workmanship warranty" or "5-year installation warranty" or null,
      "workmanship_warranty_duration": "2 years" or "5 years" or null,
      "warranty_evidence": "Page 5, Section 07 50 00: 'Manufacturer warranty: 20-year warranty' or 'Workmanship warranty: 2 years' or null"
    }},
    "insurance": {{
      "general_liability_required": true/false,
      "general_liability_limit": "$2,000,000" or "$5,000,000" or null,
      "workers_compensation_required": true/false,
      "workers_compensation_limit": "$1,000,000" or null,
      "umbrella_insurance_required": true/false,
      "umbrella_insurance_limit": "$5,000,000" or null,
      "insurance_evidence": "Page 1, General Requirements: 'Contractor shall maintain general liability insurance of $2,000,000' or null"
    }},
    "bonds": {{
      "performance_bond_required": true/false,
      "performance_bond_amount": "100% of contract" or "$500,000" or null,
      "payment_bond_required": true/false,
      "payment_bond_amount": "100% of contract" or "$500,000" or null,
      "bond_evidence": "Page 1, General Requirements: 'Performance bond required: 100% of contract value' or null"
    }}
  }}
}}

CRITICAL: Return ONLY the JSON object. No markdown, no code blocks."""

    def _create_extraction_prompt_pass_b(
        self, page_indices: list[int], missing_items: list[str], primary_trade: str | None = None
    ) -> str:
        """Create prompt for Pass B: Gap Fill for missing critical items."""
        pages_str = ", ".join(str(p + 1) for p in page_indices)
        missing_str = ", ".join(missing_items)
        if primary_trade == "windows":
            return f"""You are doing a second pass to capture missing WINDOW information: {missing_str}

Analyze pages {pages_str} (window schedules, elevations, details, and related plans) to recover:
- Window scope notes (demo, new installation, flashing/air barrier instructions)
- Window/glazing material specifications (frames, glass make-up, hardware)
- Window schedule rows (marks, sizes, quantities, performance comments)
- Any dimensional hints needed to compute quantities (vision glass area, mullion spacing)

Return ONLY valid JSON with the same schema as Pass A, but focus exclusively on the missing window items. If a requested item still cannot be found, keep it in `evidence_missing` with a short note explaining why (e.g., "schedule not present on reviewed sheets")."""

        return f"""You are doing a second pass to find missing critical items: {missing_str}

Analyze pages {pages_str} (elevations and details) to find:
- Parapet repair/replacement information
- Lintel specifications/repair
- Flashing details
- Repointing specifications

Return ONLY valid JSON with the same schema as Pass A, but focus ONLY on the missing items.
If still not found, include them in evidence_missing."""

    def _parse_json_response(self, content: str) -> dict:
        """Parse JSON from model response, handling markdown code blocks."""
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        # Find JSON object
        content = content.strip()
        if content.startswith("{"):
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
            from loguru import logger
            logger.warning(f"JSON parse error: {str(e)}, attempting to fix...")
            
            # Try to fix common JSON issues - more aggressive approach
            logger.warning(f"Original JSON error: {str(e)}")
            
            # Strategy 1: Try to fix unterminated strings
            try:
                fixed_content = self._fix_json_strings(content)
                logger.info("Attempting to parse fixed JSON (string fix)...")
                return json.loads(fixed_content)
            except Exception as e2:
                logger.warning(f"String fix failed: {str(e2)}")
            
            # Strategy 2: Try to extract valid JSON portion
            try:
                fixed_content = self._extract_valid_json(content)
                if fixed_content and len(fixed_content) > 100:  # Only if substantial
                    logger.info("Attempting to parse extracted JSON portion...")
                    return json.loads(fixed_content)
            except Exception as e3:
                logger.warning(f"Extract valid JSON failed: {str(e3)}")
            
            # Strategy 3: Try to fix missing comma delimiters
            try:
                import re
                # Check if error is about missing comma
                if "Expecting ',' delimiter" in str(e):
                    error_pos_match = re.search(r'char (\d+)', str(e))
                    if error_pos_match:
                        error_pos = int(error_pos_match.group(1))
                        # Look backwards from error position to find where to add comma
                        before_error = content[:error_pos].rstrip()
                        # If it ends with a quote or closing brace/bracket, we might need a comma
                        if before_error and not before_error[-1] in [',', '{', '[', ':']:
                            # Try adding comma before the problematic character
                            fixed_content = content[:error_pos] + ',' + content[error_pos:]
                            logger.info("Attempting to parse JSON with added comma...")
                            return json.loads(fixed_content)
            except Exception as e4:
                logger.warning(f"Comma fix failed: {str(e4)}")
            
            # Strategy 4: Try to truncate at error position and close structures
            try:
                import re
                error_pos_match = re.search(r'char (\d+)', str(e))
                if error_pos_match:
                    error_pos = int(error_pos_match.group(1))
                    truncated = content[:error_pos]
                    # Close any open strings, arrays, objects
                    truncated = truncated.rstrip()
                    if not truncated.endswith('"'):
                        truncated += '"'
                    # Close arrays and objects
                    open_braces = truncated.count('{') - truncated.count('}')
                    open_brackets = truncated.count('[') - truncated.count(']')
                    truncated += ']' * open_brackets + '}' * open_braces
                    logger.info("Attempting to parse truncated JSON...")
                    return json.loads(truncated)
            except Exception as e5:
                logger.warning(f"Truncate fix failed: {str(e5)}")
            
            # If all else fails, raise the original error
            logger.error(f"All JSON fix strategies failed. Original error: {str(e)}")
            raise ValueError(f"Invalid JSON response: {str(e)}") from e
    
    def _emergency_json_extraction(self, content: str) -> dict:
        """Emergency extraction: try to salvage data from completely broken JSON."""
        import re
        from loguru import logger
        
        result = {
            "scope_of_work": [],
            "material_specifications": [],
            "quantity_takeoff": [],
            "geometry_for_3d": {},
            "site_context": {},
            "project_context": {}
        }
        
        try:
            # Remove markdown code blocks
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*$', '', content, flags=re.MULTILINE)
            
            # Find all scope items by looking for the pattern: "item": "...", "description": "..."
            # This pattern works even with unterminated strings
            item_pattern = r'"item"\s*:\s*"([^"]+)"\s*,\s*"description"\s*:\s*"([^"]*)"'
            
            # Also try to find items with multiline descriptions (broken strings)
            # Look for: "item": "...", then find description even if string is broken
            multiline_pattern = r'"item"\s*:\s*"([^"]+)"\s*,\s*"description"\s*:\s*"([^"]*?)(?:"\s*,\s*"page_number"|"\s*,\s*"evidence_snippet"|$)'
            
            # Try both patterns
            for pattern in [item_pattern, multiline_pattern]:
                for match in re.finditer(pattern, content, re.DOTALL):
                    try:
                        item_name = match.group(1).strip()
                        description = match.group(2).strip() if match.group(2) else ""
                        
                        # Clean up description - remove any trailing incomplete parts
                        if description:
                            # Remove anything after a quote that might be part of broken JSON
                            description = re.sub(r'"[^"]*$', '', description)
                            description = description.strip()
                        
                        if item_name and len(item_name) > 3:  # Valid item name
                            # Try to find page_number if available
                            page_num = 1
                            page_match = re.search(r'"page_number"\s*:\s*(\d+)', content[match.end():match.end()+200])
                            if page_match:
                                page_num = int(page_match.group(1))
                            
                            # Try to find evidence_snippet
                            evidence = description[:200] if description else item_name
                            evidence_match = re.search(r'"evidence_snippet"\s*:\s*"([^"]*)', content[match.end():match.end()+500])
                            if evidence_match:
                                evidence = evidence_match.group(1).strip()[:200]
                            
                            result["scope_of_work"].append({
                                "item": item_name,
                                "description": description if description else item_name,
                                "page_number": page_num,
                                "evidence_snippet": evidence
                            })
                    except Exception as e:
                        logger.debug(f"Failed to extract item from match: {e}")
                        continue
            
            # Remove duplicates
            seen = set()
            unique_items = []
            for item in result["scope_of_work"]:
                key = (item["item"], item.get("description", ""))
                if key not in seen:
                    seen.add(key)
                    unique_items.append(item)
            result["scope_of_work"] = unique_items
            
            # If we got any scope items, return the result
            if result["scope_of_work"]:
                logger.warning(f"Emergency extraction recovered {len(result['scope_of_work'])} scope items from broken JSON")
                return result
            else:
                logger.error("Emergency extraction found no scope items")
        except Exception as e:
            logger.error(f"Emergency extraction failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return None
    
    def _fix_json_strings(self, content: str) -> str:
        """Fix unterminated strings in JSON by closing them properly."""
        import re
        
        # More robust approach: find the error line and fix it
        lines = content.split('\n')
        fixed_lines = []
        
        # Track string state across lines
        in_string = False
        escape_next = False
        
        for line_num, line in enumerate(lines):
            fixed_line = []
            i = 0
            
            while i < len(line):
                char = line[i]
                
                if escape_next:
                    fixed_line.append(char)
                    escape_next = False
                    i += 1
                    continue
                
                if char == '\\':
                    escape_next = True
                    fixed_line.append(char)
                    i += 1
                    continue
                
                if char == '"':
                    if in_string:
                        # Closing quote
                        in_string = False
                    else:
                        # Opening quote
                        in_string = True
                    fixed_line.append(char)
                    i += 1
                    continue
                
                fixed_line.append(char)
                i += 1
            
            # If we're still in a string at the end of the line, close it
            if in_string:
                # Add closing quote before any trailing punctuation
                stripped = ''.join(fixed_line).rstrip()
                if stripped.endswith(','):
                    fixed_line = list(stripped[:-1]) + ['"', ',']
                elif stripped.endswith(':'):
                    fixed_line = list(stripped) + ['"']
                else:
                    fixed_line = list(stripped) + ['"']
                in_string = False
            
            fixed_lines.append(''.join(fixed_line))
        
        return '\n'.join(fixed_lines)
    
    def _extract_valid_json(self, content: str) -> str:
        """Extract the largest valid JSON portion from malformed JSON."""
        import re
        
        # Try to find the last complete JSON object by balancing braces
        brace_count = 0
        last_valid_pos = -1
        
        for i, char in enumerate(content):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    last_valid_pos = i
        
        if last_valid_pos > 0:
            return content[:last_valid_pos + 1]
        
        # If that doesn't work, try to truncate at the error position
        error_match = re.search(r'char (\d+)', str(content))
        if error_match:
            error_pos = int(error_match.group(1))
            truncated = content[:error_pos]
            # Try to close any open structures
            open_braces = truncated.count('{') - truncated.count('}')
            open_brackets = truncated.count('[') - truncated.count(']')
            truncated += ']' * open_brackets + '}' * open_braces
            return truncated
        
        return ""

    def extract(
        self,
        pdf_images: list[PdfPageImage],
        analysis: DocumentAnalysis,
        project_id: str,
        page_texts: list[str] | None = None,
    ) -> ExtractionResult:
        """
        Extract scope, materials, quantities, and geometry for row-house repair.

        Args:
            pdf_images: All PDF page images (0-indexed)
            analysis: DocumentAnalysis after TypologyResolver
            project_id: Project ID for logging
            page_texts: Extracted text from PDF pages (0-indexed list, same length as pdf_images)

        Returns:
            ExtractionResult with all extracted information
        """
        log_ctx = logger.bind(project_id=project_id, stage="row_house_extraction")
        
        # Store project_id for text structuring function
        self._current_project_id = project_id

        # Get resolved types (use resolved if available, else original)
        project_type = analysis.resolved_project_type or analysis.project_type
        scope_type = analysis.resolved_scope_type or analysis.scope_type

        # Normalize unknown types (fallback routing sends unknown types here)
        if project_type == "unknown":
            project_type = "row_house"
        if scope_type == "unknown":
            scope_type = "repair"

        # Validate types (after normalization)
        if project_type != "row_house" or scope_type != "repair":
            raise ValueError(
                f"Extractor only handles row_house + repair (or unknown fallback), got {project_type} + {scope_type}"
            )

        log_ctx.info("Starting row-house repair extraction")

        # Select pages for Stage 2 (load page index if available for richer trade-aware selection)
        page_index_model: PageIndex | None = None
        index_path = Path("out") / project_id / "page_index.json"
        if index_path.exists():
            try:
                with index_path.open("r", encoding="utf-8") as fp:
                    page_index_payload = json.load(fp)
                page_index_model = PageIndex.model_validate(page_index_payload)
            except Exception as exc:  # pragma: no cover - defensive logging
                log_ctx.debug("Failed to load page_index for extraction", error=str(exc))

        total_pages = len(pdf_images)
        page_selection = select_pages_for_stage2(
            analysis,
            project_id=project_id,
            page_index=page_index_model,
            total_pages=total_pages,
            settings=self.settings,
        )
        all_selected_pages = sorted(
            list(
                set(
                    page_selection["scope_pages"]
                    + page_selection["quantity_pages"]
                    + page_selection["materials_pages"]
                    + page_selection["geometry_pages"]
                )
            )
        )

        if not all_selected_pages:
            raise ValueError("No pages selected for Stage 2 extraction")

        log_ctx.info(
            f"Stage 2 page selection: {len(all_selected_pages)} pages "
            f"(scope: {len(page_selection['scope_pages'])}, "
            f"quantities: {len(page_selection['quantity_pages'])}, "
            f"materials: {len(page_selection['materials_pages'])}, "
            f"geometry: {len(page_selection['geometry_pages'])})"
        )

        # Pass A: Targeted Read from selected pages
        log_ctx.info(f"Pass A: Extracting from {len(all_selected_pages)} selected pages")
        # Get primary_trade from analysis if available
        primary_trade = getattr(analysis, 'primary_trade', None) if analysis else None
        
        # CRITICAL: Log which prompt will be used and text availability
        text_status = f"page_texts={'✅ PROVIDED' if page_texts else '❌ MISSING'} ({len(page_texts) if page_texts else 0} pages)"
        if primary_trade == "masonry":
            log_ctx.critical(f"✅✅✅ EXTRACTION USING MASONRY PROMPT - primary_trade={primary_trade}, {text_status}")
            logger.critical(f"[{project_id}] ✅✅✅ EXTRACTION USING MASONRY PROMPT - primary_trade={primary_trade}, {text_status}")
            if page_texts:
                total_chars = sum(len(t) for t in page_texts if t)
                log_ctx.info(f"Text available for extraction: {total_chars} total characters across {len([t for t in page_texts if t])} pages")
        elif primary_trade == "windows":
            log_ctx.critical(f"❌❌❌ EXTRACTION USING WINDOWS PROMPT - primary_trade={primary_trade}, {text_status}")
            logger.critical(f"[{project_id}] ❌❌❌ EXTRACTION USING WINDOWS PROMPT - primary_trade={primary_trade}, {text_status}")
        else:
            log_ctx.critical(f"⚠️⚠️⚠️ EXTRACTION USING DEFAULT PROMPT - primary_trade={primary_trade}, {text_status}")
            logger.critical(f"[{project_id}] ⚠️⚠️⚠️ EXTRACTION USING DEFAULT PROMPT - primary_trade={primary_trade}, {text_status}")
        
        pass_a_result = self._extract_pass(
            pdf_images=pdf_images,
            page_indices=all_selected_pages,
            prompt_fn=lambda pages: self._create_extraction_prompt_pass_a(pages, primary_trade, page_texts),
            project_id=project_id,
            pass_name="A",
        )
        pass_a_result = self._normalize_extraction_payload(pass_a_result, project_id=project_id, label="pass_a")
        pass_a_result = self._sanitize_extraction_dict(pass_a_result, project_id=project_id, label="pass_a")
        pass_a_result = self._inject_window_fallback_items(
            pass_a_result,
            analysis,
            project_id=project_id,
        )
        log_ctx.debug(f"Pass A extraction payload type: {type(pass_a_result)}")

        # Check for missing critical items
        missing_items_raw = pass_a_result.get("evidence_missing", [])
        if isinstance(missing_items_raw, str):
            missing_items = [missing_items_raw]
        else:
            missing_items = list(missing_items_raw)

        if primary_trade == "windows":
            critical_items = [
                "window_scope",
                "window_materials",
                "window_schedule",
                "window_quantities",
            ]
        else:
            critical_items = ["parapet", "lintel", "flashing", "repointing"]

        # Also check if lintels are in scope_of_work
        scope_items = pass_a_result.get("scope_of_work", [])
        has_lintels = any(
            "lintel" in item.get("item", "").lower() for item in scope_items
        )
        if primary_trade != "windows" and not has_lintels and "lintels" not in missing_items:
            missing_items.append("lintels")

        # Check if lintels are in scope_of_work or material_specifications
        scope_items = pass_a_result.get("scope_of_work", [])
        material_items = pass_a_result.get("material_specifications", [])
        has_lintels = any(
            "lintel" in item.get("item", "").lower() for item in scope_items
        ) or any(
            "lintel" in item.get("material_name", "").lower() for item in material_items
        )

        if primary_trade != "windows":
            if not has_lintels:
                if not any("lintel" in m.lower() for m in missing_items):
                    missing_items.append("lintels")
            else:
                missing_items = [m for m in missing_items if "lintel" not in m.lower()]

        pass_a_result["evidence_missing"] = missing_items

        missing_critical = [
            item for item in critical_items if any(item.lower() in m.lower() for m in missing_items)
        ]

        # Pass B: Gap Fill if critical items missing
        if missing_critical:
            # Select elevation and detail pages for gap fill
            gap_fill_pages = []
            for sheet in analysis.sheets:
                if sheet.page_number <= 0:
                    continue

                include_for_gap_fill = False
                if sheet.sheet_type in ["elevation", "detail", "section"]:
                    include_for_gap_fill = True
                elif primary_trade == "windows" and sheet.sheet_type in ["schedule", "plan"]:
                    include_for_gap_fill = True

                if primary_trade == "windows" and not include_for_gap_fill:
                    title_tokens = (sheet.title or "") + " " + (sheet.sheet_id or "")
                    lowered = title_tokens.lower()
                    if any(token in lowered for token in ["window", "glazing", "fenestration", "storefront", "curtain"]):
                        include_for_gap_fill = True

                if include_for_gap_fill:
                    page_idx = sheet.page_number - 1
                    if page_idx not in all_selected_pages and page_idx not in gap_fill_pages:
                        gap_fill_pages.append(page_idx)

            if gap_fill_pages:
                log_ctx.info(
                    f"Pass B: Gap fill for missing items {missing_critical} "
                    f"on {len(gap_fill_pages)} additional pages"
                )
                pass_b_result = self._extract_pass(
                    pdf_images=pdf_images,
                    page_indices=gap_fill_pages,
                    prompt_fn=lambda pages: self._create_extraction_prompt_pass_b(
                        pages, missing_critical, primary_trade
                    ),
                    project_id=project_id,
                    pass_name="B",
                )
                pass_b_result = self._normalize_extraction_payload(pass_b_result, project_id=project_id, label="pass_b")
                pass_b_result = self._sanitize_extraction_dict(pass_b_result, project_id=project_id, label="pass_b")
                log_ctx.debug(f"Pass B extraction payload type: {type(pass_b_result)}")

                # Merge Pass B results into Pass A
                pass_a_result = self._merge_extraction_results(pass_a_result, pass_b_result)
                pass_a_result = self._sanitize_extraction_dict(pass_a_result, project_id=project_id, label="merged")
                pass_a_result = self._inject_window_fallback_items(
                    pass_a_result,
                    analysis,
                    project_id=project_id,
                )

                # Re-check for lintels after merge and remove from missing if found
                scope_items = pass_a_result.get("scope_of_work", [])
                material_items = pass_a_result.get("material_specifications", [])
                has_lintels_after_merge = any(
                    "lintel" in item.get("item", "").lower() for item in scope_items
                ) or any(
                    "lintel" in item.get("material_name", "").lower() for item in material_items
                )
                if has_lintels_after_merge:
                    missing_items = pass_a_result.get("evidence_missing", [])
                    missing_items = [m for m in missing_items if "lintel" not in m.lower()]
                    pass_a_result["evidence_missing"] = missing_items

        # Add required fields before validation
        pass_a_result["project_type"] = "row_house"
        pass_a_result["scope_type"] = "repair"

        # Apply fallbacks from Stage 1 (dimensions and site context)
        pass_a_result = self._apply_dimension_fallback(analysis, pass_a_result)
        pass_a_result = self._apply_site_context_fallback(analysis, pass_a_result)

        # Ensure required fields exist before validation
        if "geometry_for_3d" in pass_a_result:
            geo = pass_a_result["geometry_for_3d"]
            # Ensure site_context exists and has required fields
            if "site_context" not in geo or geo.get("site_context") is None:
                geo["site_context"] = {}
            if not isinstance(geo["site_context"], dict):
                geo["site_context"] = {}
            if "building_type" not in geo["site_context"] or geo["site_context"].get("building_type") is None:
                geo["site_context"]["building_type"] = "unknown"
            if "evidence" not in geo["site_context"] or not geo["site_context"].get("evidence"):
                geo["site_context"]["evidence"] = "Site context from extraction"
            if "row_of_buildings" not in geo["site_context"]:
                geo["site_context"]["row_of_buildings"] = []
            if "addresses" not in geo["site_context"]:
                geo["site_context"]["addresses"] = []
            # Ensure work_zones have required fields
            if "work_zones" in geo:
                for zone in geo["work_zones"]:
                    if isinstance(zone, dict):
                        if "page_number" not in zone or zone.get("page_number") is None:
                            zone["page_number"] = 1
                        if "evidence" not in zone or not zone.get("evidence"):
                            zone["evidence"] = "Work zone from extraction"

        # Validate and return
        result = ExtractionResult.model_validate(pass_a_result)

        # Ensure warranty/insurance evidence has meaningful defaults
        if result.warranty_and_insurance:
            if (
                not result.warranty_and_insurance.warranty.warranty_evidence
                or result.warranty_and_insurance.warranty.warranty_evidence.strip() == ""
            ):
                result.warranty_and_insurance.warranty.warranty_evidence = (
                    "Warranty requirements not found in reviewed documents"
                )
            if (
                not result.warranty_and_insurance.insurance.insurance_evidence
                or result.warranty_and_insurance.insurance.insurance_evidence.strip() == ""
            ):
                result.warranty_and_insurance.insurance.insurance_evidence = (
                    "Insurance requirements not found in reviewed documents"
                )
            if (
                not result.warranty_and_insurance.bonds.bond_evidence
                or result.warranty_and_insurance.bonds.bond_evidence.strip() == ""
            ):
                result.warranty_and_insurance.bonds.bond_evidence = (
                    "Bond requirements not found in reviewed documents"
                )

        result.validation_metadata = {
            "pages_used": all_selected_pages,
            "passes": 2 if missing_critical and gap_fill_pages else 1,
            "detail": "high",
        }

        log_ctx.info(
            f"Extraction completed: {len(result.scope_of_work)} scope items, "
            f"{len(result.material_specifications)} materials, "
            f"{len(result.quantity_takeoff)} quantities"
        )

        return result

    def _extract_critical_items_only(
        self,
        pdf_images: list[PdfPageImage],
        missing_items: list[str],
        project_id: str,
    ) -> ExtractionResult:
        """
        Extract only missing Critical-5 items from selected pages.

        Used for Phase 2.5B recovery strategy.
        """
        log_ctx = logger.bind(project_id=project_id, stage="critical_recovery_extraction")

        # Create specialized prompt for missing items only
        prompt = self._create_critical_items_prompt(missing_items)

        # Build messages with selected images (high detail)
        messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        for img in pdf_images:
            messages[0]["content"].append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.mime_type};base64,{img.image_base64}",
                        "detail": "high",
                    },
                }
            )

        # Call OpenAI
        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-critical_recovery",
                stage_name="critical_recovery",
                project_id=project_id,
            )

            # Parse and validate
            parsed = self._parse_json_response(response_text)

            # Create minimal ExtractionResult with only recovered items
            from app.schemas.extraction_result import ExtractionResult, ScopeItem
            from app.schemas.geometry_for_3d import GeometryFor3D, SiteContext

            recovered_scope = [
                ScopeItem.model_validate(item) for item in parsed.get("scope_of_work", [])
            ]

            return ExtractionResult(
                project_type="row_house",
                scope_type="repair",
                scope_of_work=recovered_scope,
                material_specifications=[],
                quantity_takeoff=[],
                geometry_for_3d=GeometryFor3D(
                    site_context=SiteContext(
                        building_type="row_house",
                        row_of_buildings=[],
                        addresses=[],
                        evidence="Recovery extraction",
                    ),
                    work_zones=[],
                    evidence_missing=[],
                ),
                validation_metadata={},
                evidence_missing=[],
            )

        except Exception as e:
            log_ctx.error(f"Critical items extraction failed: {e}")
            raise

    def _create_critical_items_prompt(self, missing_items: list[str]) -> str:
        """Create prompt for extracting only missing Critical-5 items."""
        items_str = ", ".join(missing_items)
        return f"""You are extracting ONLY the following missing Critical-5 scope items from this construction document:
{items_str}

Extract ONLY these items. Ignore everything else.

For each item found, provide:
- item: exact name
- description: detailed description
- location: where on building
- page_number: page where found
- sheet_id: sheet ID if visible
- evidence_snippet: exact text showing this item

Return ONLY valid JSON:
{{
  "scope_of_work": [
    {{
      "item": "flashing installation",
      "description": "Install new flashing at parapet",
      "location": "parapet",
      "page_number": 3,
      "sheet_id": "A-3",
      "evidence_snippet": "Install new flashing per detail 3/A-3"
    }}
  ]
}}

Return ONLY the JSON object. No markdown, no code blocks."""

    def _extract_pass(
        self,
        pdf_images: list[PdfPageImage],
        page_indices: list[int],
        prompt_fn: Callable[[list[int]], str],
        project_id: str,
        pass_name: str,
    ) -> dict:
        """Execute one extraction pass."""
        log_ctx = logger.bind(project_id=project_id, stage=f"extraction_pass_{pass_name}")

        # Build messages with selected images (high detail for Stage 2)
        selected_images = [pdf_images[i] for i in page_indices if i < len(pdf_images)]
        
        # Log extraction attempt details
        log_ctx.info(f"Extraction pass {pass_name}: analyzing {len(selected_images)} pages (indices: {page_indices})")
        
        # Get prompt text and log it
        prompt_text = prompt_fn(page_indices)
        log_ctx.debug(f"Extraction prompt (first 500 chars): {prompt_text[:500]}...")
        if "CRITICAL: SCOPE ITEMS TO EXTRACT" in prompt_text or "SCOPE ITEM" in prompt_text or "STRUCTURED TEXT FOR EXTRACTION" in prompt_text or "EXTRACTED TEXT FROM SELECTED PAGES" in prompt_text:
            log_ctx.info("✅ Extraction prompt includes structured/extracted text from PDF")
        else:
            log_ctx.warning("⚠️ Extraction prompt does NOT include extracted text - may rely only on visual analysis")

        messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]

        for img in selected_images:
            messages[0]["content"].append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.mime_type};base64,{img.image_base64}",
                        "detail": "high",  # High detail for Stage 2
                    },
                }
            )

        # Call OpenAI with retry
        max_retries = 2
        for attempt in range(max_retries):
            try:
                log_ctx.info(f"Calling OpenAI Vision (attempt {attempt + 1}/{max_retries})")
                response_text = self.openai_client.call_vision(
                    messages=messages,
                    request_id=f"{project_id}_pass_{pass_name}",
                    stage_name=f"row_house_extraction_{pass_name}",
                    project_id=project_id,
                )

                try:
                    parsed = self._parse_json_response(response_text)
                    if not isinstance(parsed, dict):
                        raise ValueError("Extraction response was not a JSON object")
                    
                    # Log extraction result
                    scope_items = parsed.get("scope_of_work", [])
                    material_items = parsed.get("material_specifications", [])
                    quantity_items = parsed.get("quantity_takeoff", [])
                    log_ctx.info(f"Extraction result: {len(scope_items)} scope items, {len(material_items)} materials, {len(quantity_items)} quantities")
                    if len(scope_items) == 0:
                        log_ctx.warning(f"⚠️ Zero scope items extracted - check if text was included in prompt")
                    
                    return parsed
                except ValueError as e:
                    # Log the actual response for debugging
                    log_ctx.error(f"JSON parse failed. Response length: {len(response_text)}, first 1000 chars: {response_text[:1000]}")
                    log_ctx.error(f"JSON parse failed. Last 500 chars: {response_text[-500:]}")
                    
                    if attempt < max_retries - 1:
                        log_ctx.warning(f"Invalid JSON on attempt {attempt + 1}, retrying")
                        continue
                    else:
                        # Last attempt failed - try to extract what we can from the broken JSON
                        log_ctx.error("All retries failed. Attempting emergency JSON extraction...")
                        emergency_result = self._emergency_json_extraction(response_text)
                        if emergency_result and emergency_result.get("scope_of_work"):
                            log_ctx.warning(f"Emergency extraction succeeded with {len(emergency_result['scope_of_work'])} scope items")
                            return emergency_result
                        else:
                            log_ctx.error("Emergency extraction found no data - raising original error")
                            raise

            except OpenAINonRetryableError as e:
                log_ctx.error(f"Non-retryable OpenAI error: {e}")
                raise

        raise ValueError("Failed to get valid response from OpenAI")

    def _normalize_extraction_payload(self, payload: Any, *, project_id: str, label: str) -> dict:
        """Ensure extraction payload is a dict, repairing JSON strings when possible."""

        if isinstance(payload, dict):
            return payload

        log_ctx = logger.bind(project_id=project_id, stage="row_house_extraction", label=label)

        if isinstance(payload, str):
            try:
                parsed = self._parse_json_response(payload)
                if isinstance(parsed, dict):
                    log_ctx.warning("Extraction payload was string; reparsed into JSON object")
                    return parsed
            except ValueError as exc:
                log_ctx.error(
                    "Failed to parse string payload into JSON object",
                    error=str(exc),
                )

        raise ValueError(f"Extraction payload for {label} was not a JSON object")

    def _sanitize_extraction_dict(self, payload: dict, *, project_id: str, label: str) -> dict:
        """Coerce known fields to the expected container shapes and log repairs."""

        if not isinstance(payload, dict):
            return payload

        log_ctx = logger.bind(project_id=project_id, stage="row_house_extraction", label=label)

        def _ensure_dict(field: str) -> None:
            value = payload.get(field)
            if value is None or isinstance(value, dict):
                return
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        payload[field] = parsed
                        log_ctx.warning(f"Field '{field}' was string; reparsed into dict")
                        return
                except Exception as exc:  # pragma: no cover - defensive logging
                    log_ctx.debug(
                        f"Failed to parse string field '{field}' into dict",
                        error=str(exc),
                    )
            log_ctx.warning(f"Field '{field}' had unexpected type {type(value)}, coercing to dict")
            payload[field] = {}

        def _ensure_list(field: str) -> None:
            value = payload.get(field)
            if value is None or isinstance(value, list):
                return
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        payload[field] = parsed
                        log_ctx.warning(f"Field '{field}' was string; reparsed into list")
                        return
                except Exception as exc:  # pragma: no cover - defensive logging
                    log_ctx.debug(
                        f"Failed to parse string field '{field}' into list",
                        error=str(exc),
                    )
            log_ctx.warning(f"Field '{field}' had unexpected type {type(value)}, coercing to list")
            payload[field] = []
        
        def _fix_material_fields() -> None:
            """Fix material_specifications items to have required fields."""
            materials = payload.get("material_specifications", [])
            if not isinstance(materials, list):
                return
            
            for i, item in enumerate(materials):
                if not isinstance(item, dict):
                    continue
                
                # Fix missing material_name
                if "material_name" not in item or not item.get("material_name"):
                    description = item.get("description", "")
                    if description:
                        # Extract material name from description
                        item["material_name"] = description.split(",")[0].split("(")[0].strip()[:100]
                    else:
                        item["material_name"] = "Unknown material"
                    log_ctx.debug(f"Fixed material {i}: added material_name={item['material_name']}")
                
                # Fix missing page_number
                if "page_number" not in item or item.get("page_number") is None:
                    source = item.get("source", "")
                    import re
                    page_match = re.search(r'page\s*(\d+)', source.lower())
                    if page_match:
                        item["page_number"] = int(page_match.group(1))
                    else:
                        item["page_number"] = 1  # Default
                    log_ctx.debug(f"Fixed material {i}: added page_number={item['page_number']}")
                
                # Fix missing evidence_snippet
                if "evidence_snippet" not in item or not item.get("evidence_snippet"):
                    evidence = item.get("description") or item.get("source") or "Material specification found in document"
                    item["evidence_snippet"] = evidence[:200]  # Limit length
                    log_ctx.debug(f"Fixed material {i}: added evidence_snippet")

        _ensure_list("scope_of_work")
        _ensure_list("material_specifications")
        _ensure_list("quantity_takeoff")
        
        # Fix material_specifications to have required fields
        _fix_material_fields()

        for dict_field in ["geometry_for_3d", "site_context", "project_context"]:
            if dict_field == "site_context":
                # site_context lives under geometry_for_3d but we sanitize top-level if present
                continue
            _ensure_dict(dict_field)

        if isinstance(payload.get("geometry_for_3d"), dict):
            geo = payload["geometry_for_3d"]
            if not isinstance(geo, dict):
                geo = {}
                payload["geometry_for_3d"] = geo
            if "site_context" in geo and not isinstance(geo.get("site_context"), dict):
                value = geo.get("site_context")
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, dict):
                            geo["site_context"] = parsed
                            log_ctx.warning("geometry_for_3d.site_context reparsed into dict from string")
                        else:
                            geo["site_context"] = {}
                    except Exception as exc:  # pragma: no cover
                        log_ctx.debug(
                            "Failed to parse geometry_for_3d.site_context string",
                            error=str(exc),
                        )
                        geo["site_context"] = {}
                else:
                    log_ctx.warning(
                        "geometry_for_3d.site_context had unexpected type {type(value)}, coercing to dict"
                    )
                    geo["site_context"] = {}

            if "work_zones" in geo and not isinstance(geo.get("work_zones"), list):
                value = geo.get("work_zones")
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, list):
                            geo["work_zones"] = parsed
                            log_ctx.warning("geometry_for_3d.work_zones reparsed into list from string")
                        else:
                            geo["work_zones"] = []
                    except Exception as exc:  # pragma: no cover
                        log_ctx.debug(
                            "Failed to parse geometry_for_3d.work_zones string",
                            error=str(exc),
                        )
                        geo["work_zones"] = []
                else:
                    log_ctx.warning(
                        f"geometry_for_3d.work_zones had unexpected type {type(value)}, coercing to list"
                    )
                    geo["work_zones"] = []

        for list_field in ["scope_of_work", "material_specifications", "quantity_takeoff", "evidence_missing"]:
            _ensure_list(list_field)

        return payload

    def _inject_window_fallback_items(
        self,
        extraction_dict: dict,
        analysis: DocumentAnalysis | None,
        *,
        project_id: str,
    ) -> dict:
        """Populate minimal window scope/material/quantity entries when extraction is empty."""

        if not isinstance(extraction_dict, dict) or not analysis:
            return extraction_dict

        if (analysis.primary_trade or "").lower() != "windows":
            return extraction_dict

        log_ctx = logger.bind(project_id=project_id, stage="row_house_extraction", fallback="windows")

        def _ensure_list(field: str) -> list:
            value = extraction_dict.get(field)
            if isinstance(value, list):
                return value
            extraction_dict[field] = []
            return extraction_dict[field]

        scope_list = _ensure_list("scope_of_work")
        material_list = _ensure_list("material_specifications")
        quantity_list = _ensure_list("quantity_takeoff")
        missing_list = _ensure_list("evidence_missing")

        def _has_keyword_entry(entries: list[dict], fields: tuple[str, ...], keywords: tuple[str, ...]) -> bool:
            for entry in entries:
                for field in fields:
                    text = (entry.get(field) or "").lower()
                    if any(keyword in text for keyword in keywords):
                        return True
            return False

        keywords = ("window", "glazing", "frame")

        # Scope fallback
        if not scope_list or not _has_keyword_entry(scope_list, ("item", "description"), keywords):
            scope_locator = None
            for locator in analysis.where_scope_lives:
                evidence_text = (locator.evidence or "").lower()
                if any(keyword in evidence_text for keyword in keywords):
                    scope_locator = locator
                    break
            if not scope_locator and analysis.where_scope_lives:
                scope_locator = analysis.where_scope_lives[0]

            if scope_locator:
                scope_item = {
                    "item": "Window removal and glazing replacement",
                    "description": "Remove existing windows and glazing; install new frames and glass per notes",
                    "location": None,
                    "page_number": scope_locator.page_number or 1,
                    "sheet_id": scope_locator.sheet_id,
                    "evidence_snippet": scope_locator.evidence,
                }
                scope_list.append(scope_item)
                log_ctx.info("Injected fallback window scope item from Stage 1 analysis")
            elif analysis.where_materials_live:
                material_locator = analysis.where_materials_live[0]
                scope_item = {
                    "item": "Window glazing installation",
                    "description": "Install new glazing units with thermally broken frames",
                    "location": None,
                    "page_number": material_locator.page_number or 1,
                    "sheet_id": material_locator.sheet_id,
                    "evidence_snippet": material_locator.evidence,
                }
                scope_list.append(scope_item)
                log_ctx.info("Injected fallback window scope item from materials locator")

        # Detail fallback to capture glazing detail references
        if analysis:
            detail_sheet = next(
                (sheet for sheet in analysis.sheets if sheet.sheet_type in {"detail", "elevation"}),
                None,
            )
            if detail_sheet and not _has_keyword_entry(scope_list, ("item", "description"), ("glazing detail", "jamb", "head")):
                scope_list.append(
                    {
                        "item": "Reference glazing head/jamb detail",
                        "description": "Coordinate glazing head, sill, and jamb details per window elevations",
                        "location": None,
                        "page_number": detail_sheet.page_number,
                        "sheet_id": detail_sheet.sheet_id,
                        "evidence_snippet": f"Glazing detail referenced on sheet {detail_sheet.sheet_id}",
                    }
                )
                log_ctx.info("Injected glazing detail scope item from elevation/detail sheet")

        # Materials fallback
        if not material_list or not _has_keyword_entry(material_list, ("material_name", "specification", "application"), keywords):
            material_locator = None
            for locator in analysis.where_materials_live:
                evidence_text = (locator.evidence or "").lower()
                if any(keyword in evidence_text for keyword in keywords):
                    material_locator = locator
                    break
            if not material_locator and analysis.where_materials_live:
                material_locator = analysis.where_materials_live[0]

            if material_locator:
                material_item = {
                    "material_name": "Window frame and glazing system",
                    "specification": "See window schedule for frame and glazing performance",
                    "application": "Window replacements",
                    "detail_sheet": material_locator.sheet_id,
                    "page_number": material_locator.page_number or 1,
                    "sheet_id": material_locator.sheet_id,
                    "evidence_snippet": material_locator.evidence,
                }
                material_list.append(material_item)
                log_ctx.info("Injected fallback window material specification from Stage 1 analysis")
            elif analysis.where_scope_lives:
                scope_locator = analysis.where_scope_lives[0]
                material_item = {
                    "material_name": "Window glazing package",
                    "specification": "Fallback: glazing details referenced in scope notes",
                    "application": "Window replacements",
                    "detail_sheet": scope_locator.sheet_id,
                    "page_number": scope_locator.page_number or 1,
                    "sheet_id": scope_locator.sheet_id,
                    "evidence_snippet": scope_locator.evidence,
                }
                material_list.append(material_item)
                log_ctx.info("Injected fallback window material specification from scope locator")

        # Quantity fallback
        if not quantity_list or not _has_keyword_entry(quantity_list, ("item",), ("window",)):
            quantity_locator = None
            for locator in analysis.where_quantities_live:
                evidence_text = (locator.evidence or "").lower()
                if "window" in evidence_text or "schedule" in evidence_text:
                    quantity_locator = locator
                    break
            if not quantity_locator and analysis.where_quantities_live:
                quantity_locator = analysis.where_quantities_live[0]

            if quantity_locator:
                quantity_item = {
                    "item": "Window schedule quantity",
                    "quantity": 1.0,
                    "unit": "ea",
                    "is_computed": False,
                    "computation_formula": None,
                    "input_dimensions": {},
                    "evidence_missing": False,
                    "page_number": quantity_locator.page_number or 1,
                    "sheet_id": quantity_locator.sheet_id,
                    "evidence_snippet": quantity_locator.evidence,
                }
                quantity_list.append(quantity_item)
                log_ctx.info("Injected fallback window quantity item from Stage 1 analysis")
            elif analysis.where_scope_lives:
                scope_locator = analysis.where_scope_lives[0]
                quantity_item = {
                    "item": "Window scope placeholder",
                    "quantity": 1.0,
                    "unit": "ea",
                    "is_computed": False,
                    "computation_formula": None,
                    "input_dimensions": {},
                    "evidence_missing": False,
                    "page_number": scope_locator.page_number or 1,
                    "sheet_id": scope_locator.sheet_id,
                    "evidence_snippet": scope_locator.evidence,
                }
                quantity_list.append(quantity_item)
                log_ctx.info("Injected fallback window quantity item from scope locator")

        if scope_list or material_list or quantity_list:
            removal_targets = {"window_scope", "window_materials", "window_schedule", "window_quantities"}
            extraction_dict["evidence_missing"] = [
                item for item in missing_list if item.lower() not in removal_targets
            ]

        # Add a detail item when elevations or detail sheets mention windows
        if analysis and any(sheet.sheet_type in {"elevation", "detail"} for sheet in analysis.sheets):
            geometry = extraction_dict.get("geometry_for_3d")
            if isinstance(geometry, dict):
                work_zones = geometry.setdefault("work_zones", [])
                if isinstance(work_zones, list) and not any(
                    isinstance(zone, dict) and zone.get("zone_name") == "window_elevation"
                    for zone in work_zones
                ):
                    elevation_sheet = next((
                        sheet for sheet in analysis.sheets if sheet.sheet_type in {"elevation", "detail"}
                    ), None)
                    work_zones.append(
                        {
                            "zone_name": "window_elevation",
                            "z_min": None,
                            "z_max": None,
                            "facade_region": None,
                            "page_number": (elevation_sheet.page_number if elevation_sheet else 1),
                            "sheet_id": (elevation_sheet.sheet_id if elevation_sheet else None),
                            "evidence": "Window elevation/detail referencing glazing head/sill details",
                        }
                    )

        return extraction_dict

    def _merge_extraction_results(self, pass_a: dict, pass_b: dict) -> dict:
        """Merge Pass B results into Pass A, avoiding duplicates."""
        if not isinstance(pass_a, dict):
            return pass_a
        if not isinstance(pass_b, dict):
            return pass_a

        merged = pass_a.copy()

        # Merge scope items (dedupe by item name)
        a_scope_items = {item["item"]: item for item in pass_a.get("scope_of_work", [])}
        for item in pass_b.get("scope_of_work", []):
            if item["item"] not in a_scope_items:
                a_scope_items[item["item"]] = item
        merged["scope_of_work"] = list(a_scope_items.values())

        # Merge materials (dedupe by material_name)
        a_materials = {
            item["material_name"]: item for item in pass_a.get("material_specifications", [])
        }
        for item in pass_b.get("material_specifications", []):
            if item["material_name"] not in a_materials:
                a_materials[item["material_name"]] = item
        merged["material_specifications"] = list(a_materials.values())

        # Merge quantities (dedupe by item)
        a_quantities = {item["item"]: item for item in pass_a.get("quantity_takeoff", [])}
        for item in pass_b.get("quantity_takeoff", []):
            if item["item"] not in a_quantities:
                a_quantities[item["item"]] = item
        merged["quantity_takeoff"] = list(a_quantities.values())

        # Merge work zones (dedupe by zone_name)
        # Ensure work zones have required fields (page_number, etc.)
        a_zones = {}
        geometry_a = pass_a.get("geometry_for_3d")
        if not isinstance(geometry_a, dict):
            geometry_a = {}

        for zone in geometry_a.get("work_zones", []):
            if not isinstance(zone, dict):
                continue
            zone_name = zone.get("zone_name") or "unknown"
            # Ensure required fields exist
            if "page_number" not in zone or zone.get("page_number") is None:
                zone["page_number"] = 1  # Default to page 1 if missing
            if "evidence" not in zone or not zone.get("evidence"):
                zone["evidence"] = "Work zone from extraction"
            a_zones[zone_name] = zone
        geometry_b = pass_b.get("geometry_for_3d")
        if not isinstance(geometry_b, dict):
            geometry_b = {}

        for zone in geometry_b.get("work_zones", []):
            if not isinstance(zone, dict):
                continue
            zone_name = zone.get("zone_name") or "unknown"
            if zone_name not in a_zones:
                # Ensure required fields exist
                if "page_number" not in zone or zone.get("page_number") is None:
                    zone["page_number"] = 1  # Default to page 1 if missing
                if "evidence" not in zone or not zone.get("evidence"):
                    zone["evidence"] = "Work zone from extraction"
                a_zones[zone_name] = zone
        if "geometry_for_3d" not in merged or not isinstance(merged["geometry_for_3d"], dict):
            merged["geometry_for_3d"] = {}
        merged["geometry_for_3d"]["work_zones"] = list(a_zones.values())
        
        # Ensure site_context.building_type is set if geometry_for_3d exists
        if "geometry_for_3d" in merged:
            if "site_context" not in merged["geometry_for_3d"] or merged["geometry_for_3d"]["site_context"] is None:
                merged["geometry_for_3d"]["site_context"] = {}
            if not isinstance(merged["geometry_for_3d"]["site_context"], dict):
                merged["geometry_for_3d"]["site_context"] = {}
            if "building_type" not in merged["geometry_for_3d"]["site_context"] or merged["geometry_for_3d"]["site_context"].get("building_type") is None:
                merged["geometry_for_3d"]["site_context"]["building_type"] = "unknown"
            if "evidence" not in merged["geometry_for_3d"]["site_context"] or not merged["geometry_for_3d"]["site_context"].get("evidence"):
                merged["geometry_for_3d"]["site_context"]["evidence"] = "Site context from extraction"
            if "row_of_buildings" not in merged["geometry_for_3d"]["site_context"]:
                merged["geometry_for_3d"]["site_context"]["row_of_buildings"] = []
            if "addresses" not in merged["geometry_for_3d"]["site_context"]:
                merged["geometry_for_3d"]["site_context"]["addresses"] = []

        # Merge evidence_missing (union)
        merged["evidence_missing"] = sorted(
            list(set(pass_a.get("evidence_missing", []) + pass_b.get("evidence_missing", [])))
        )

        return merged

    def _apply_dimension_fallback(
        self, analysis: DocumentAnalysis, extraction_dict: dict
    ) -> dict:
        """
        Apply dimension fallback from Stage 1 if Stage 2 extraction missed dimensions.

        If geometry_for_3d.dimensions is null or missing width/depth/height,
        fill from Stage 1 analysis.key_dimensions.

        Args:
            analysis: DocumentAnalysis from Stage 1
            extraction_dict: Raw extraction result dictionary

        Returns:
            Updated extraction_dict with dimensions filled from Stage 1 if needed
        """
        # Get geometry_for_3d from extraction
        geometry_dict = extraction_dict.get("geometry_for_3d", {})

        # Check if dimensions are missing or incomplete
        dims_dict = geometry_dict.get("dimensions")
        needs_fallback = False

        if dims_dict is None:
            needs_fallback = True
            dims_dict = {}
        else:
            # Check if any critical dimension is missing
            if (
                dims_dict.get("width") is None
                or dims_dict.get("depth") is None
                or dims_dict.get("height") is None
            ):
                needs_fallback = True

        # Apply fallback from Stage 1 if needed
        if needs_fallback and analysis.key_dimensions:
            stage1_dims = analysis.key_dimensions

            # Fill missing dimensions from Stage 1
            if dims_dict.get("width") is None and stage1_dims.width is not None:
                dims_dict["width"] = stage1_dims.width
                log_ctx = logger.bind(
                    project_id="fallback", stage="dimension_fallback"
                )
                log_ctx.info(
                    f"Fallback: width={stage1_dims.width} from Stage 1 key_dimensions"
                )

            if dims_dict.get("depth") is None and stage1_dims.depth is not None:
                dims_dict["depth"] = stage1_dims.depth
                log_ctx = logger.bind(
                    project_id="fallback", stage="dimension_fallback"
                )
                log_ctx.info(
                    f"Fallback: depth={stage1_dims.depth} from Stage 1 key_dimensions"
                )

            if dims_dict.get("height") is None and stage1_dims.height is not None:
                dims_dict["height"] = stage1_dims.height
                log_ctx = logger.bind(
                    project_id="fallback", stage="dimension_fallback"
                )
                log_ctx.info(
                    f"Fallback: height={stage1_dims.height} from Stage 1 key_dimensions"
                )

            if dims_dict.get("area") is None and stage1_dims.area is not None:
                dims_dict["area"] = stage1_dims.area

            # Update evidence to indicate fallback
            if "evidence" not in dims_dict or not dims_dict["evidence"]:
                dims_dict["evidence"] = "fallback_from_stage1"
            else:
                dims_dict["evidence"] = (
                    f"{dims_dict['evidence']} (with fallback from Stage 1)"
                )

            # Preserve computation info if it exists
            if "computation_formula" not in dims_dict:
                dims_dict["computation_formula"] = None
            if "input_pages" not in dims_dict:
                dims_dict["input_pages"] = []

            # Update geometry_for_3d with filled dimensions
            geometry_dict["dimensions"] = dims_dict
            extraction_dict["geometry_for_3d"] = geometry_dict

            logger.info(
                "Applied dimension fallback from Stage 1: "
                f"width={dims_dict.get('width')}, "
                f"depth={dims_dict.get('depth')}, "
                f"height={dims_dict.get('height')}"
            )

        return extraction_dict

    def _apply_site_context_fallback(
        self, analysis: DocumentAnalysis, extraction_dict: dict
    ) -> dict:
        """
        Apply site context fallback from Stage 1 if Stage 2 extraction missed it.

        If geometry_for_3d.site_context has empty row_of_buildings or addresses,
        fill from Stage 1 analysis.building_context.

        Args:
            analysis: DocumentAnalysis from Stage 1
            extraction_dict: Raw extraction result dictionary

        Returns:
            Updated extraction_dict with site context filled from Stage 1 if needed
        """
        geometry_dict = extraction_dict.get("geometry_for_3d", {})
        site_context_dict = geometry_dict.get("site_context", {})

        # Apply fallback from Stage 1 building_context if available
        if analysis.building_context:
            bc = analysis.building_context

            # Fill row_of_buildings if empty
            if not site_context_dict.get("row_of_buildings") and bc.building_ids:
                site_context_dict["row_of_buildings"] = bc.building_ids
                logger.info(
                    f"Fallback: row_of_buildings={bc.building_ids} from Stage 1 building_context"
                )

            # Fill addresses if empty
            if not site_context_dict.get("addresses") and bc.addresses:
                site_context_dict["addresses"] = bc.addresses
                logger.info(
                    f"Fallback: addresses={bc.addresses} from Stage 1 building_context"
                )

            # Fill subject_building_id if missing and we have building_ids
            if (
                not site_context_dict.get("subject_building_id")
                and bc.building_ids
                and len(bc.building_ids) > 0
            ):
                # Use first building ID as subject (or could use logic to determine)
                site_context_dict["subject_building_id"] = bc.building_ids[0]
                logger.info(
                    f"Fallback: subject_building_id={bc.building_ids[0]} from Stage 1"
                )

            # Update evidence
            if "evidence" not in site_context_dict or not site_context_dict["evidence"]:
                site_context_dict["evidence"] = "fallback_from_stage1"
            else:
                site_context_dict["evidence"] = (
                    f"{site_context_dict['evidence']} (with fallback from Stage 1)"
                )

            geometry_dict["site_context"] = site_context_dict
            extraction_dict["geometry_for_3d"] = geometry_dict

        return extraction_dict