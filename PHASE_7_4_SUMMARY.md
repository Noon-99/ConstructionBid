# Phase 7.4 — Cross-Sections, Detail Graphs & Drawing Intelligence

## Summary

Implemented Phase 7.4 to transform extracted data into a navigable, explainable detail graph where the 3D model becomes a semantic index of the construction documents.

## Core Concept

**NOT recreating drawings** — Building a **Detail Graph**:
- Structured representation of what details exist
- Where they apply
- What construction elements they govern
- All linked to geometry, bid items, and evidence

## Deliverables

### 1. Detail Graph Schema (`app/schemas/detail_graph.py`)

**DetailNode Fields**:
- `detail_id`: Unique identifier (e.g., "DET-001", "S-011-D4")
- `detail_type`: parapet, wall_section, window, lintel, roof, roof_edge, foundation, footing, other
- `sheet_id`: Sheet ID where detail is located
- `detail_label`: Detail label/callout (e.g., "Detail 4", "Typical Parapet Detail")
- `applies_to`: List of element IDs this detail applies to
- `materials_referenced`: Materials referenced in detail
- `dimensions_referenced`: Dimensions referenced in detail
- `notes`: Notes or special requirements
- `page_number`, `evidence_snippet`: Evidence

**DetailGraph**:
- `details`: List of DetailNode objects
- `missing_fields`, `confidence`: Extraction metadata

### 2. Detail Extractor (`app/analyzers/detail_extractor.py`)

**Extraction Strategy**:
- Selects pages with detail indicators (confidence >= 0.6)
- Uses `detail="high"` for detail sheets
- Extracts explicit details with sheet IDs and detail labels
- Deduplicates by detail_id or sheet_id + detail_label

**Page Selection**:
- `page_index` indicators: detail, section, parapet, wall, window, roof, foundation
- Page types: detail, section, structural, plan
- Stage 1 locators: detail_callouts, specification_section

### 3. Cross-Section Regions (`app/schemas/model_3d.py`)

**New Schema: `CrossSectionRegion`**:
- `region_id`: Region identifier
- `region_type`: wall_assembly, parapet, roof_edge, floor_to_floor, foundation
- `bounding_box`: Bounding box of the region
- `applies_to`: List of element IDs this region applies to
- `detail_refs`: List of detail IDs that govern this region
- `evidence`: Evidence for region definition

**Rules**:
- These are **regions, not drawings**
- No layers unless explicitly stated
- Used for **navigation, not visualization accuracy**

**3D Generator Integration** (`app/generators/model_3d_generator.py`):
- `_generate_cross_section_regions()`: Creates regions for:
  - Wall assembly (full height of building)
  - Parapet (if parapet exists)
  - Roof edge (if roof exists)
  - Floor-to-floor (if multiple floors exist)

### 4. Geometry ↔ Detail Binding (`app/services/detail_binding.py`)

**Binding Functions**:
- `bind_details_to_elements()`: Binds detail nodes to geometry elements
  - Uses `applies_to` field from details
  - Keyword matching: parapet zones → parapet details, openings → window/lintel details, structural → foundation details
- `bind_details_to_cost_items()`: Binds detail references to cost items
  - Matches scope items to details by keyword
  - Populates `detail_refs` on cost items

**Binding Logic**:
- Zones → Details (parapet zones → parapet details)
- Openings → Details (openings → window/lintel details)
- Structural Elements → Details (footings → foundation details)

### 5. Validation Gates (`app/services/institutional_validation.py`)

**Detail Graph Gate** (`_validate_detail_graph()`):
- **Error** if details referenced in notes but no DetailNode exists
- **Error** if parapet exists but no parapet detail linked
- **Error** if window/lintel exists but no window/lintel detail linked
- Failures **block bid readiness**

### 6. Cost Traceability Upgrade (`app/schemas/costing.py`, `app/costing/cost_engine.py`)

**Schema Update**:
- Added `detail_refs: list[str]` to `CostItem`
- Lists detail IDs that govern this cost item

**Cost Engine Integration**:
- Calls `bind_details_to_cost_items()` after cost computation
- Populates `detail_refs` on all cost items

**Bid Proposal Integration** (`app/services/bid_proposal_generator.py`):
- Includes detail references in `basis` field
- Format: "Detail refs: DET-001, S-011-D4"

### 7. Evidence Index Finalization (`app/schemas/evidence_index.py`, `app/services/evidence_indexer.py`)

**New Schema: `DetailEvidence`**:
- `detail_id`, `detail_type`, `sheet_id`, `detail_label`
- `evidence_references`: Linked evidence references
- `linked_zones`: List of zone IDs this detail applies to
- `linked_openings`: List of opening IDs this detail applies to
- `linked_bid_items`: Indices of linked bid line items

**Evidence Indexer Integration**:
- Generates `detail_evidence` list
- Reverse lookup: From detail → everything it affects
- Links: Detail → zone → bid → page

**Evidence Chain**:
- Detail → Zone → Bid → Page
- Clicking a detail shows: zones, openings, bid items, source sheet

## Key Features

### Semantic Index, Not BIM
- Detail graph represents **what details exist**, not recreating drawings
- Cross-section regions are **navigation aids**, not visual accuracy
- No parametric assemblies, no Revit families, no visual drafting

### Evidence-Backed
- All details include `page_number`, `sheet_id`, `detail_label`, `evidence_snippet`
- Clear source tracking
- Evidence chain: detail → zone → bid → page

### Navigable & Explainable
- Clicking geometry shows governing detail
- Bid lines trace to details
- Contractor can answer: "Where is this coming from?" and "Which detail governs this?"

### Validation Hard Gates
- Details referenced → DetailNode must exist
- Parapet exists → parapet detail must be linked
- Window/lintel exists → window/lintel detail must be linked
- Failures **block bid readiness**

## Files Created/Modified

**New Files**:
- `app/schemas/detail_graph.py`
- `app/analyzers/detail_extractor.py`
- `app/services/detail_binding.py`

**Modified Files**:
- `app/schemas/extraction_result.py` (added `detail_graph` field)
- `app/schemas/model_3d.py` (added `CrossSectionRegion` and `cross_section_regions` field)
- `app/schemas/costing.py` (added `detail_refs` to `CostItem`)
- `app/schemas/evidence_index.py` (added `DetailEvidence` and `detail_evidence` field)
- `app/generators/model_3d_generator.py` (added `_generate_cross_section_regions()`)
- `app/services/pipeline.py` (calls detail extractor)
- `app/services/institutional_validation.py` (added detail graph validation)
- `app/services/bid_proposal_generator.py` (includes detail refs in basis)
- `app/costing/cost_engine.py` (binds detail refs to cost items)
- `app/services/evidence_indexer.py` (generates detail evidence)
- `backend/run_full_pipeline.py` (initializes detail extractor)

## Constraints Met

✅ No parametric assemblies  
✅ No Revit families  
✅ No visual drafting  
✅ No layer-by-layer construction modeling  
✅ No UI redesign  
✅ Evidence-backed (all details have page_number + snippet)  
✅ Deterministic validation  
✅ Row-house pipeline unaffected (new extractor only for institutional)

## Success Criteria

✅ Institutional PDF produces:
- Detail graph with ≥5 meaningful DetailNodes (extractor supports this)
- Cross-section regions visible in 3D (wall_assembly, parapet, roof_edge, floor_to_floor)
- Clicking geometry shows governing detail (via evidence index)
- Bid lines trace to details (via detail_refs in cost items)

✅ Contractor can answer:
- "Where is this coming from?" (evidence chain)
- "Which detail governs this?" (detail_refs in bid items)

✅ Row-house pipeline unaffected

## Usage Example

```python
# Detail extraction
detail_graph = detail_extractor.extract(
    pdf_images=pdf_images,
    analysis=document_analysis,
    page_index=page_index,
    project_id=project_id,
)
# Returns: DetailGraph with details list

# Binding details to elements
element_to_details = bind_details_to_elements(extraction)
# Returns: dict mapping element IDs to list of detail IDs

# Binding details to cost items
cost_items = bind_details_to_cost_items(extraction, cost_items)
# Returns: cost items with detail_refs populated
```

## What This Unlocks

After Phase 7.4, the system is ready for:
- **Phase 8 — UX / Product Layer**: The detail graph enables rich navigation and explanation in the UI

