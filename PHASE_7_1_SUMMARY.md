# Phase 7.1 — Institutional Room-Driven Extraction — Complete

## ✅ Completed Deliverables

### 1. **Room Schedule Schema** (`app/schemas/room_schedule.py`) - 7.1A
   - `RoomScheduleItem`: room_id, room_name, area_sf (required > 0), level, usage_type, finishes_hint, evidence
   - `EvidenceRef`: page_number, sheet_id, snippet
   - `RoomSchedule`: rooms list, total_gsf, total_gsf_evidence, missing_fields, confidence
   - Strict validation: area_sf > 0, room_name non-empty

### 2. **Extraction Result Update** (`app/schemas/extraction_result.py`)
   - Added `room_schedule: RoomSchedule | None` field
   - Maintains backward compatibility with existing `room_program` field

### 3. **Institutional Room Extractor Enhancement** (`app/analyzers/institutional_room_extractor.py`) - 7.1B
   - Added `extract_room_schedule()` method (Phase 7.1)
   - Converts existing `InstitutionalRoomProgramResult` to `RoomSchedule` format
   - Only includes rooms with explicit area_sf > 0 and evidence
   - No guessing, fully evidence-backed

### 4. **Stage 2 Routing Update** (`app/services/pipeline.py`) - 7.1C
   - Enhanced routing logic to detect institutional/commercial projects
   - Checks for `life_safety`/`room_schedule` indicators in page_index
   - Checks Stage 1 locators for room_schedule/life_safety_plan
   - Routes to institutional extractor when:
     - `project_type in ["institutional", "commercial"]` AND
     - `scope_type in ["renovation", "addition", "new_construction"]` OR
     - Has room_schedule indicators
   - **Row-house extractor path remains unchanged** (non-breaking)

### 5. **Pipeline Integration**
   - Calls `extract_room_schedule()` after `extract_rooms()`
   - Adds `room_schedule` to `ExtractionResult`
   - Maintains existing `room_program` for backward compatibility

### 6. **Validation Gates Extension** (`app/services/institutional_validation.py`) - 7.1D
   - **Room Coverage Gate**: Requires >= 10 rooms (configurable, default 15)
   - **Dominant Room Gate**: Largest room should be >= 25-30% of total (warning if < 25%, error if below absolute minimum)
   - **Gross Area Consistency Gate**: Sum of room areas within ±20% of declared GSF
   - On failure: Triggers targeted re-read on pages with `life_safety`/`room_schedule` indicators (max 4 pages)
   - Additive merge behavior on recovery

### 7. **Room-Based Finish Cost Rules** (7.1F)
   - `paint_wall_ceiling.yml`: Paint with usage-type multipliers (gym: 3.5x, office: 2.8x, etc.)
   - `flooring_vct.yml`: VCT flooring at $3.50/SF
   - `ceiling_act.yml`: Acoustic ceiling tile at $4.25/SF
   - All rules are data-driven (YAML), not hardcoded

## 🔧 Technical Details

### Routing Logic
```python
is_institutional_route = (
    project_type in ["institutional", "commercial"]
    and scope_type in ["renovation", "addition", "new_construction"]
)

has_room_schedule_indicators = (
    page_index has "room_schedule"/"life_safety" indicators
    OR Stage 1 locators have "room_schedule"/"life_safety_plan"
)

if is_institutional_route OR (institutional/commercial AND has_room_schedule_indicators):
    → Use institutional extractor
```

### Validation Rules
- **Room Coverage**: `len(rooms) >= room_count_min` (default: 15, configurable)
- **Dominant Room**: `largest_room.area_sf / total_area >= 0.25` (warning) AND `largest_room.area_sf >= largest_room_min_sf` (error)
- **GSF Consistency**: `abs(sum(room_areas) - total_gsf) / total_gsf <= 0.20` (error if exceeded)

### Evidence Requirements
- Every room must have:
  - `area_sf > 0` (strict validation)
  - `room_name` non-empty
  - `evidence` with `page_number` and `snippet`
- No guessing, no hallucinated geometry

## 📋 Files Created/Modified

### Backend
- `app/schemas/room_schedule.py` (new)
- `app/schemas/extraction_result.py` (updated - added room_schedule field)
- `app/analyzers/institutional_room_extractor.py` (updated - added extract_room_schedule method)
- `app/services/pipeline.py` (updated - enhanced routing, added room_schedule extraction)
- `app/services/institutional_validation.py` (updated - added _validate_room_schedule)
- `app/costing/rules/paint_wall_ceiling.yml` (new)
- `app/costing/rules/flooring_vct.yml` (new)
- `app/costing/rules/ceiling_act.yml` (new)

## ✅ Constraints Met

- ✅ No new AI calls beyond existing extractor calls
- ✅ Deterministic + evidence-backed
- ✅ Files <300 lines where practical
- ✅ No breaking changes to existing row-house flow
- ✅ Parallel extractor paths (institutional vs row-house)

## 🚀 Usage

1. **Automatic Routing**: System automatically detects institutional/commercial projects with room schedules
2. **Room Extraction**: Extracts rooms with area_sf and evidence from Life Safety Plans
3. **Validation**: Applies Phase 7.1 validation gates
4. **Recovery**: On failure, re-reads targeted pages (max 4) and merges additively
5. **Costing**: Room-based finish rules available for paint, flooring, ceiling

## 📝 Next Steps

- **7.1E (Geometry)**: Update geometry builder to create semantic room zones (area-only, not BIM)
- **Tests**: Add unit tests for routing, validation, and room schedule extraction
- **Integration**: Test with Recreation Center PDF (20+ rooms expected)

## 🔄 Remaining Work

1. **Geometry Builder Update (7.1E)**: Update `institutional_geometry_builder.py` to create semantic room zones from `room_schedule` with `zone_type="room"`, `footprint_source="area_only"`
2. **Unit Tests (7.1)**: Add tests for:
   - Room schedule parsing
   - Validation rules (coverage, dominant room, GSF consistency)
   - Routing correctness (institutional vs row-house)
   - Additive merge behavior on recovery

Phase 7.1 core extraction and validation is complete. Geometry builder update and tests remain.






