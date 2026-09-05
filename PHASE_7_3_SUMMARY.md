# Phase 7.3 — Openings, Lintels, Schedules & Detail-Driven Elements

## Summary

Extended Phase 7.3 to capture openings (windows/doors) and lintels as first-class construction elements, enabling detail-driven bids with constructible intelligence.

## Deliverables

### 1. Openings Schema (`app/schemas/openings.py`)

**Fields**:
- `opening_id`: Identifier (e.g., "WIN-1", "D-101")
- `opening_type`: window, door, opening
- `level`: Floor/level (e.g., "1st Floor")
- `count`: Count if from schedule
- `width_ft`, `height_ft`: Dimensions if stated
- `size`: Size designation (e.g., "3-0 x 6-8")
- `material`: aluminum, steel, wood, storefront
- `associated_lintel_id`: Link to lintel if applicable
- `flashing_required`: Boolean flag
- `source`: schedule, elevation, detail, unknown
- `evidence`: page_number, sheet_id, detail_reference, evidence_snippet

### 2. Lintels Schema (`app/schemas/lintels.py`)

**Fields**:
- `lintel_id`: Identifier (e.g., "L-1", "LINT-101")
- `lintel_type`: steel_lintel, cmu_lintel, precast_lintel, bond_beam, header
- `section`: Section designation (e.g., "L3x3x1/4", "C8x11.5")
- `material_spec`: ASTM A36, ASTM A992, Galvanized
- `span_ft`: Span in feet
- `quantity`: Quantity if from schedule
- `associated_openings`: List of opening IDs
- `flashing_required`, `drip_edge_required`: Boolean flags
- `source`: schedule, detail, elevation, unknown
- `evidence`: page_number, sheet_id, detail_reference, evidence_snippet

### 3. Openings Extractor (`app/analyzers/openings_extractor.py`)

**Extraction Strategy**:
- Selects pages with openings indicators (confidence >= 0.6)
- Uses `detail="high"` for schedules and detail pages
- Extracts from: window/door schedules, elevations, detail callouts
- Deduplicates by `opening_id` (prefers schedule source)

**Page Selection**:
- `page_index` indicators: window, door, opening, schedule, elevation, detail
- Page types: schedule, elevation, detail, plan
- Stage 1 locators: window_schedule, door_schedule, elevation_notes

### 4. Lintels Extractor (`app/analyzers/lintels_extractor.py`)

**Extraction Strategy**:
- Selects pages with lintel indicators (confidence >= 0.6)
- Uses `detail="high"` for schedules and detail pages
- Extracts from: lintel schedules, detail callouts, structural drawings
- Deduplicates by `lintel_id` (prefers schedule source)

**Page Selection**:
- `page_index` indicators: lintel, header, structural, detail, schedule
- Page types: detail, structural, schedule, section
- Stage 1 locators: specification_section, detail_callouts

### 5. 3D Geometry Upgrade (`app/schemas/institutional_geometry_for_3d.py`, `app/services/institutional_geometry_builder.py`)

**New Geometry Types**:
- `OpeningCutout`: Window/door cutouts in facade geometry
- `LintelBand`: Lintel bands above openings
- `FlashingBand`: Flashing bands at openings

**Geometry Builder Functions**:
- `_build_opening_cutouts()`: Creates cutouts from openings (with level offsets)
- `_build_lintel_bands()`: Creates lintel bands above openings
- `_build_flashing_bands()`: Creates flashing bands at openings requiring flashing

**3D Generator Integration** (`app/generators/model_3d_generator.py`):
- Converts opening cutouts to `WindowOpening` objects
- Converts lintel bands to `WorkZoneVolume` with `zone_type="work_zone"`
- Converts flashing bands to `WorkZoneVolume` with `zone_type="work_zone"`

### 6. Validation Gates (`app/services/institutional_validation.py`)

**A) Openings Gate** (`_validate_openings()`):
- **Error** if window/door schedule exists but no openings extracted

**B) Lintels Gate** (`_validate_lintels()`):
- **Error** if lintel schedule exists but no lintels extracted
- **Error** if openings exist but no lintels (blocks bid readiness)
- **Warning** if lintels exist but no flashing reference

### 7. Costing Integration (`app/services/structural_envelope_to_scope.py`)

**New Conversion Functions**:
- `convert_openings_to_scope()`: Converts openings to scope items (window/door replacement or new install)
- `convert_lintels_to_scope()`: Converts lintels to scope items (steel lintel install + flashing if required)

**YAML Cost Rules** (Phase 7.3):
- `window_replacement.yml`: Window replacement (EA-based)
- `window_new_install.yml`: New window installation (EA-based)
- `door_replacement.yml`: Door replacement (EA-based)
- `door_new_install.yml`: New door installation (EA-based)
- `steel_lintel_install.yml`: Steel lintel installation (EA-based)
- `flashing_per_opening.yml`: Flashing per opening (LF-based)

### 8. Evidence Index Expansion (`app/services/evidence_indexer.py`)

**New Linking**:
- **Openings → Lintels**: Links openings to associated lintels via `associated_lintel_id`
- **Openings → Details**: Links openings to detail references
- **Lintels → Openings**: Links lintels to associated openings
- **Lintels → Details**: Links lintels to detail references
- **Lintel Bands**: Links lintel work zones to lintel evidence
- **Flashing Bands**: Links flashing work zones to flashing evidence

**Evidence Chain**:
- Opening → Lintel → Detail → Bid Item
- Clicking a window in 3D shows: lintel spec, flashing detail, cost line, source sheet

## Key Features

### Detail-Driven
- Extracts from schedules, elevations, and detail callouts
- Links openings to lintels and details
- No guessing or inferred sizes

### Evidence-Backed
- All elements include `page_number`, `sheet_id`, `detail_reference`, `evidence_snippet`
- Clear source tracking (schedule, elevation, detail)
- Evidence chain: opening → lintel → detail → bid item

### Constructible Intelligence
- Lintels as first-class structural elements
- Flashing requirements tracked
- Material specs (ASTM, galvanizing) preserved
- Section designations (L3x3x1/4, C8x11.5) captured

### Validation Hard Gates
- Schedule → extraction requirement
- Openings → lintels requirement (blocks bid readiness)
- Deterministic validation (no AI calls)

## Files Created/Modified

**New Files**:
- `app/schemas/openings.py`
- `app/schemas/lintels.py`
- `app/analyzers/openings_extractor.py`
- `app/analyzers/lintels_extractor.py`
- `app/costing/rules/window_replacement.yml`
- `app/costing/rules/window_new_install.yml`
- `app/costing/rules/door_replacement.yml`
- `app/costing/rules/door_new_install.yml`
- `app/costing/rules/steel_lintel_install.yml`
- `app/costing/rules/flashing_per_opening.yml`

**Modified Files**:
- `app/schemas/extraction_result.py` (added `openings`, `lintels` fields)
- `app/schemas/institutional_geometry_for_3d.py` (added opening cutouts, lintel bands, flashing bands)
- `app/services/institutional_geometry_builder.py` (added builders)
- `app/generators/model_3d_generator.py` (converts to Model3D)
- `app/services/pipeline.py` (calls new extractors)
- `app/services/institutional_validation.py` (added validation gates)
- `app/services/structural_envelope_to_scope.py` (added conversion functions)
- `app/services/evidence_indexer.py` (extended linking)
- `backend/run_full_pipeline.py` (initializes extractors)

## Constraints Met

✅ No Revit-level parametrics (coarse volumes only)  
✅ No inferred window sizes (only if stated)  
✅ No photoreal textures  
✅ No UI redesign  
✅ No schedule guessing (only explicit schedules)  
✅ Evidence-backed (all elements have page_number + snippet)  
✅ Deterministic validation  
✅ Row-house pipeline unaffected (new extractors only for institutional)

## Success Criteria

✅ Institutional PDF with window schedule produces:
- Correct opening counts
- Lintel extraction
- Matching bid items
- Clickable 3D elements with evidence

✅ Row-house PDFs still pass unchanged

✅ Bid readiness blocks missing lintels correctly

## Usage Example

```python
# Openings extraction
openings = openings_extractor.extract(
    pdf_images=pdf_images,
    analysis=document_analysis,
    page_index=page_index,
    project_id=project_id,
)
# Returns: OpeningsResult with openings list

# Lintels extraction
lintels = lintels_extractor.extract(
    pdf_images=pdf_images,
    analysis=document_analysis,
    page_index=page_index,
    project_id=project_id,
)
# Returns: LintelsResult with lintels list
```

## Next Steps (Future Enhancements)

1. **Enhanced Geometry Placement**: Use actual coordinates from elevations for precise opening placement
2. **Lintel-Opening Auto-Linking**: Automatically link lintels to openings based on proximity/level
3. **Flashing Detail Extraction**: Extract specific flashing details from detail sheets
4. **Opening Material Matching**: Match opening materials to cost rule multipliers
5. **Lintel Section Validation**: Validate lintel sections against span requirements






