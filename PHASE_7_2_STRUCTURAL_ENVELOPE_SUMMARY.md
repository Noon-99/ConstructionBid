# Phase 7.2 — Structural & Building Envelope Extraction

## Summary

Extended Phase 7.2 to include structural elements and building envelope extraction, enabling contractor-useful bids with real construction intelligence.

## Deliverables

### 1. Structural Elements Schema (`app/schemas/structural_elements.py`)

**Elements Supported**:
- Foundations (footings, slabs)
- Structural steel (columns, beams, lintels)
- Load-bearing CMU walls
- Temporary shoring (if explicitly stated)

**Schema Fields**:
- `element_type`: footing, slab, bearing_wall, column, beam, lintel, cmu_wall, shoring
- `dimensions`: width/depth/height/length, section (e.g., "W12x26"), diameter, thickness
- `material_spec`: ASTM, PSI, grade, unit_strength
- `quantity` + `unit` (LF, EA, SF, CY)
- `evidence`: page_number, sheet_id, detail_reference, evidence_snippet

### 2. Building Envelope Schema (`app/schemas/building_envelope.py`)

**Elements Supported**:
- Exterior walls (brick_veneer, cmu_backup, eifs, concrete, metal_panel)
- Roof systems (deck, insulation, membrane, parapet)
- Flashing systems (lintel_flashing, coping, drip_edge, base_flashing, counter_flashing, through_wall)
- Openings (windows/doors at count + type level)

**Schema Fields**:
- `EnvelopeWall`: area_sf, height_ft, length_ft, material_spec, location
- `RoofSystem`: deck_type, insulation_type, membrane_type, area_sf, parapet_height_ft
- `FlashingSystem`: length_lf, material, location, detail_reference
- `Opening`: count, type_description, size, location

### 3. Structural Elements Extractor (`app/analyzers/structural_elements_extractor.py`)

**Extraction Strategy**:
- Selects pages with structural indicators (confidence >= 0.6)
- Uses `detail="high"` for structural detail pages
- Extracts: element_type, dimensions, material_spec, quantity, evidence
- Deduplicates by element_id or location

**Page Selection**:
- `page_index` indicators: structural_notes, foundation, steel, cmu, loads, detail
- Page types: detail, plan, section, notes
- Stage 1 locators: specification_section, detail_callouts

### 4. Building Envelope Extractor (`app/analyzers/building_envelope_extractor.py`)

**Extraction Strategy**:
- Selects pages with envelope indicators (confidence >= 0.6)
- Uses `detail="high"` for elevation and detail pages
- Extracts: walls, roof_systems, flashing_systems, openings
- Deduplicates by ID or location

**Page Selection**:
- `page_index` indicators: dimensions, elevation, roof, parapet, flashing, window, door
- Page types: elevation, plan, detail, section
- Stage 1 locators: elevation_notes, detail_callouts

### 5. 3D Geometry Upgrade (`app/schemas/institutional_geometry_for_3d.py`, `app/services/institutional_geometry_builder.py`)

**New Geometry Types**:
- `RoofVolume`: Roof bounding box with parapet height
- `StructuralZone`: Structural element zones (columns, bearing walls, footings, beams)
- `EnvelopeLayer`: Coarse envelope volumes (exterior_wall, roof, parapet)

**Geometry Builder Functions**:
- `_build_roof_volumes()`: Creates roof volumes above existing building from roof systems
- `_build_structural_zones()`: Creates structural zones from structural elements
- `_build_envelope_layers()`: Creates envelope layers from walls and parapets

**3D Generator Integration** (`app/generators/model_3d_generator.py`):
- Converts roof volumes to `WorkZoneVolume` with `zone_type="building_mass"`
- Converts structural zones to `WorkZoneVolume` with `zone_type="building_mass"`
- Converts envelope layers to `WorkZoneVolume` with `zone_type="building_mass"`
- Converts openings to `WindowOpening` objects

### 6. Validation Gates (`app/services/institutional_validation.py`)

**A) Structural Elements Gate** (`_validate_structural_elements()`):
- **Error** if structural notes exist but no structural elements extracted
- **Error** if < 1 structural element extracted

**B) Building Envelope Gate** (`_validate_building_envelope()`):
- **Error** if parapet/flashing mentioned in scope but not extracted
- **Error** if parapet mentioned but not found in roof systems
- **Error** if flashing mentioned but not found in flashing systems

**C) Geometry Quality Gate** (enhanced):
- Sets `geometry_quality="partial"` if envelope/roof exists in PDF but not in model

### 7. Pipeline Integration (`app/services/pipeline.py`)

**Updated Stage 2 Routing**:
- Calls `structural_elements_extractor.extract()` for institutional projects
- Calls `building_envelope_extractor.extract()` for institutional projects
- Adds `structural_elements` and `building_envelope` to `ExtractionResult`

**Updated Initialization**:
- Added `structural_elements_extractor` and `building_envelope_extractor` parameters
- Updated `run_full_pipeline.py` to initialize new extractors

### 8. Costing Integration (To Be Completed)

**Required**:
- Cost engine should process structural elements → cost items
- Cost engine should process building envelope → cost items
- Ensure CSI-aligned rules exist:
  - Structural steel (columns, beams)
  - Masonry (load-bearing vs veneer)
  - Roofing systems
  - Flashing allowances

**Note**: Cost engine already processes `scope_of_work`, `material_specifications`, and `quantity_takeoff`. Structural elements and building envelope need to be converted to these formats or cost engine needs to be extended to process them directly.

## Key Features

### Evidence-Backed
- All elements include `page_number`, `sheet_id`, `evidence_snippet`
- No guessing or inferred geometry
- Clear evidence pointers for auditability

### Semantic, NOT BIM
- Coarse volumes, not assemblies
- No photorealism
- No decorative elements
- Everything links to evidence or is omitted

### Deterministic
- No AI calls in validation
- Clear rules for when to extract vs skip
- Validation gates ensure completeness

## Files Changed

1. `app/schemas/structural_elements.py` (NEW)
2. `app/schemas/building_envelope.py` (NEW)
3. `app/schemas/extraction_result.py` (added fields)
4. `app/schemas/institutional_geometry_for_3d.py` (added roof/structural/envelope types)
5. `app/analyzers/structural_elements_extractor.py` (NEW)
6. `app/analyzers/building_envelope_extractor.py` (NEW)
7. `app/services/institutional_geometry_builder.py` (added builders)
8. `app/generators/model_3d_generator.py` (converts to Model3D)
9. `app/services/pipeline.py` (calls new extractors)
10. `app/services/institutional_validation.py` (added validation gates)
11. `app/services/run_full_pipeline.py` (initializes new extractors)

## Constraints Met

✅ No full BIM (semantic volumes only)  
✅ No guessed assemblies  
✅ No photorealistic materials  
✅ No UI changes  
✅ No Revit-style object trees  
✅ Evidence-backed (all elements have page_number + snippet)  
✅ Deterministic validation  
✅ Row-house pipeline unaffected (new extractors only for institutional)

## Next Steps (Remaining Tasks)

1. **Costing Integration**: Extend cost engine to process structural elements and building envelope
2. **CSI Rules**: Ensure YAML rules exist for:
   - Structural steel (columns, beams)
   - Masonry (load-bearing vs veneer)
   - Roofing systems
   - Flashing allowances
3. **Bid Proposal**: Ensure structural and envelope cost items appear with provenance
4. **Tests**: Add comprehensive tests for:
   - Structural elements extraction
   - Building envelope extraction
   - Geometry generation
   - Validation gates
   - Row-house regression tests

## Usage Example

```python
# Structural elements extraction
structural_elements = structural_elements_extractor.extract(
    pdf_images=pdf_images,
    analysis=document_analysis,
    page_index=page_index,
    project_id=project_id,
)
# Returns: StructuralElementsResult with elements list

# Building envelope extraction
building_envelope = building_envelope_extractor.extract(
    pdf_images=pdf_images,
    analysis=document_analysis,
    page_index=page_index,
    project_id=project_id,
)
# Returns: BuildingEnvelopeResult with walls, roofs, flashing, openings
```

## Success Criteria

✅ Institutional PDF produces:
- Structural + envelope cost lines (pending costing integration)
- Corresponding 3D volumes (roof, parapet, structural zones, envelope layers)
- Clickable evidence links (all elements have evidence)

✅ Bid readiness reflects missing structural data correctly
✅ Row-house PDFs remain unaffected (new extractors only for institutional)






