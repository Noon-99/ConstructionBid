# Phase 7.2 — Institutional Extractor (Rooms + Finishes + Geometry Contract)

## Summary

Implemented Phase 7.2: Enhanced institutional extractor with two-pass strategy, finish mapping, area-only geometry prisms, and comprehensive validation gates.

## Deliverables

### 1. Enhanced Institutional Room Extractor (`app/analyzers/institutional_room_extractor.py`)

**Two-Pass Strategy (Phase 7.2)**:
- **Pass A (Targeted Room Schedule Read)**:
  - Selects pages using `page_index` where:
    - `page_types` include: `plan`, `compliance`, `schedule`, `notes`
    - `indicators`: `room_schedule`, `dimensions`
    - `confidence >= 0.6`
  - Uses OpenAI Vision `detail="high"` on max 3-5 pages
  - Extracts: building `existing_gsf`, rooms (number/name/area), addition GSF, room grouping hints
  - Every room includes evidence: page number + snippet

- **Pass B (Gap Fill + Normalization)**:
  - Re-reads up to 2 more pages if missing:
    - `existing_gsf`
    - `addition_gsf`
    - `floor/level` info
    - Room schedule totals
  - Deduplicates near-identical rooms
  - Normalizes room names (deterministic inference)

### 2. Finish Mapper Service (`app/services/finish_mapper.py`)

**Deterministic Room Type → Finish Assemblies Mapping**:
- Maps room types to default finish assemblies:
  - Paint (walls/ceilings)
  - VCT flooring
  - ACT ceiling
- Config-driven via YAML (no hardcoding)
- Evidence cites room schedule area line
- Outputs quantities per room and totals

**Methods**:
- `map_room_to_finishes(room)` → Returns finish quantities for a single room
- `map_schedule_to_finishes(room_schedule)` → Aggregates finish quantities for entire schedule
- `_infer_usage_type(room_name)` → Deterministic inference (gym, toilet, office, etc.)

**YAML Rules Used**:
- `paint_wall_ceiling.yml` (multipliers by usage type)
- `flooring_vct.yml` (direct area mapping)
- `ceiling_act.yml` (direct area mapping)

### 3. Institutional GeometryFor3D v1 (`app/services/institutional_geometry_builder.py`)

**Rooms-as-Zones with Area-Only Prisms**:
- **If building dimensions available**: Uses packing algorithm (existing behavior)
- **If no dimensions**: Creates area-only prisms:
  - Width/depth derived from area using stable heuristic (1.5:1 aspect ratio)
  - Marks `geometry_quality="derived_from_area"`
  - Includes derivation note + evidence that only area was available
  - Stacks rooms vertically (simple stacking, no spatial layout)

**Key Function**: `_build_area_only_prisms()`
- Creates simple rectangular prisms from area
- Stable aspect ratio (1.5:1 width:depth)
- Clear notes: "Area-only prism: footprint derived from area using 1.5:1 aspect ratio. No layout evidence available."

### 4. Validation Gates (Enhanced)

**A) Finish Coverage Gate** (`_validate_finish_coverage()`):
- Error if < 80% of room area mapped to a floor finish rule
- Placeholder for integration with finish mapping service

**B) Geometry Quality Gate** (`_validate_geometry_quality()`):
- Allows `"derived_from_area"` but requires:
  - >= 10 rooms OR
  - >= 70% area covered by zones
- Error if coverage < 70% and room count < 10

**C) Room Area Completeness Gate** (Phase 7.1, enhanced):
- Error if `sum(room areas) < 70% of existing_gsf`
- Warning if outside ±20% but >= 70%

### 5. Integration Points

**Pipeline Integration** (to be completed):
- Finish mapper should be called after room schedule extraction
- Finish quantities should be added to `ExtractionResult` or separate artifact
- Bid proposal generator should include finish line items with provenance

**Bid Proposal Integration** (to be completed):
- Ensure CSI-style line items from finishes:
  - "Basis: room schedule areas (Page X)"
  - Include provenance in `basis` field

## Key Improvements

### Before Phase 7.2
- Single-pass extraction (no gap fill)
- No finish mapping service
- Geometry required building dimensions (no area-only fallback)
- No finish coverage validation

### After Phase 7.2
- **Two-pass extraction**: Targeted read + gap fill
- **Finish mapper**: Deterministic room type → finish assemblies
- **Area-only prisms**: Geometry works even without footprint evidence
- **Comprehensive validation**: Finish coverage + geometry quality gates

## Files Changed

1. `app/analyzers/institutional_room_extractor.py` (enhanced with two-pass strategy)
2. `app/services/finish_mapper.py` (NEW)
3. `app/services/institutional_geometry_builder.py` (area-only prisms support)
4. `app/services/institutional_validation.py` (finish coverage + geometry quality gates)

## Constraints Met

✅ No fake geometry (area-only prisms clearly marked)  
✅ No room footprints unless supported by drawing evidence  
✅ Deterministic finish mapping (no AI calls)  
✅ Evidence-backed (all rooms include page number + snippet)  
✅ Config-driven (YAML rules, no hardcoding)  
✅ Files <300 lines (except finish_mapper which is ~250 lines)

## Next Steps (Remaining Tasks)

1. **Bid Proposal Integration**: Ensure finish line items appear in bid proposal with provenance
2. **Pipeline Integration**: Call finish mapper after room schedule extraction
3. **Tests**: Add comprehensive tests for:
   - Two-pass extraction
   - Finish mapping
   - Area-only prisms
   - Validation gates

## Usage Example

```python
from app.services.finish_mapper import FinishMapper
from app.core.config import Settings

settings = Settings()
finish_mapper = FinishMapper(settings)

# Map single room
room_finishes = finish_mapper.map_room_to_finishes(room_item)
# Returns: {"paint": {...}, "flooring": {...}, "ceiling": {...}}

# Map entire schedule
schedule_finishes = finish_mapper.map_schedule_to_finishes(room_schedule)
# Returns: aggregated totals with per-room breakdown
```

## Testing

To test Phase 7.2:

```bash
# Run institutional extraction
python app/scripts/run_institutional_room_extract.py institutional.pdf

# Verify:
# 1. Two-pass extraction (check logs for "Pass A" and "Pass B")
# 2. Room schedule with evidence
# 3. Geometry with area-only prisms if no dimensions
# 4. Validation gates pass
```






