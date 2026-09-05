# Phase 7.1P — Proof Runner + Routing Robustness

## Summary

Implemented Phase 7.1P: Dev-only CLI script for testing institutional extraction and improved routing reliability.

## Deliverables

### 1. CLI Script: `app/scripts/run_institutional_room_extract.py`

**Purpose**: Dev-only tool to test Phase 7.1 institutional extraction path, even if Stage 1 misclassifies.

**Features**:
- Runs full pipeline (Stage 0 → 0.5 → 1 → 1.5 → 2 → 2.5 → 3 → 4)
- Supports `--force-project-type institutional` to override classification
- Supports `--force-use-institutional-extractor` to bypass routing
- Prints summary: room_count, total_room_area, top 5 rooms, validation_score, bid_ready
- Saves `room_schedule.json` separately when forced

**Usage**:
```bash
python app/scripts/run_institutional_room_extract.py path/to/pdf.pdf
python app/scripts/run_institutional_room_extract.py path/to/pdf.pdf --force-project-type institutional
python app/scripts/run_institutional_room_extract.py path/to/pdf.pdf --force-use-institutional-extractor
```

### 2. Improved Stage 2 Routing (`app/services/pipeline.py`)

**Enhancements**:
- **Strong Signal**: Triggers institutional extractor if `page_index` shows `room_schedule`/`life_safety` with confidence >= 0.6, regardless of `scope_type`
- **Medium Signal**: Triggers if Stage 1 locators indicate `room_schedule`/`life_safety_plan`, even if `scope_type` is unreliable
- **Logging**: Logs why institutional path was chosen (indicator + page numbers)
- **Warning**: Warns if routing despite problematic `scope_type` (e.g., "repair" or "unknown")

**Routing Logic**:
```python
# A) Strong signal: page_index confidence >= 0.6
strong_signal = page_index has room_schedule/life_safety with confidence >= 0.6

# B) Medium signal: Stage 1 locators
medium_signal = where_quantities_lives has room_schedule/life_safety_plan

# C) Traditional route
is_institutional_route = project_type in ["institutional", "commercial"] 
                        AND scope_type in ["renovation", "addition", "new_construction"]

# Decision
should_route = strong_signal OR is_institutional_route OR (medium_signal AND not row_house)
```

**Key Improvement**: No longer blocks on unreliable `scope_type` if we have strong indicators.

### 3. Room Area Completeness Validation Gate (`app/services/institutional_validation.py`)

**New Function**: `_validate_room_schedule()` (Phase 7.1)

**Validation Rules**:
1. **Room Coverage Gate**: >= 10 rooms (configurable)
2. **Dominant Room Gate**: Largest room >= 25-30% of total (warning for rec center/gym)
3. **Gross Area Consistency Gate**: Sum(room areas) within ±20% of declared GSF
4. **Room Area Completeness Gate** (NEW):
   - **Error** if `sum(room areas) < 70% of existing_gsf`
   - **Warning** if outside ±20% but >= 70%

**Example**:
- GSF = 1000 SF
- Room areas = 300 SF (30% coverage) → **ERROR**: "Room area completeness: only 30% of declared GSF"
- Room areas = 750 SF (75% coverage, 25% difference) → **WARNING**: "Outside ±20% tolerance"
- Room areas = 850 SF (85% coverage, 15% difference) → **PASS**

### 4. Unit Tests (`tests/test_phase_7_1_routing.py`)

**Test Coverage**:
- ✅ Routing triggers on `page_index` indicators with confidence >= 0.6
- ✅ Routing triggers on Stage 1 locators (medium signal)
- ✅ Routing does NOT trigger if confidence < 0.6
- ✅ Routing does NOT override row-house projects
- ✅ Room area completeness gate errors if < 70% of GSF
- ✅ Room area completeness gate passes if >= 70% of GSF
- ✅ Room area completeness gate warns if outside ±20% but >= 70%

## Key Improvements

### Before Phase 7.1P
- Routing required: `project_type == "institutional"` AND `scope_type in ["renovation", "addition", "new_construction"]`
- Problem: If Stage 1 misclassifies `scope_type` as "repair", institutional extraction never runs
- No validation for room area completeness vs. GSF

### After Phase 7.1P
- Routing triggers on **strong indicators** (confidence >= 0.6) even if `scope_type` is unreliable
- Routing triggers on **medium indicators** (Stage 1 locators) even if `scope_type` is "unknown"
- **Room area completeness gate** ensures we capture >= 70% of building area
- **Dev CLI script** allows testing even with misclassified projects

## Testing

To test Phase 7.1P on an institutional PDF:

```bash
# Normal run (uses routing)
python app/scripts/run_institutional_room_extract.py institutional.pdf

# Force institutional type
python app/scripts/run_institutional_room_extract.py institutional.pdf --force-project-type institutional

# Force extractor (bypass routing)
python app/scripts/run_institutional_room_extract.py institutional.pdf --force-use-institutional-extractor
```

**Expected Output**:
```
Room Count: 25
Total Room Area: 12,500 SF
Declared GSF: 15,000 SF
Coverage: 83.3%

Top 5 Rooms by Area:
  1. Gymnasium: 3,500 SF
  2. Auditorium: 2,000 SF
  3. Cafeteria: 1,500 SF
  4. Library: 1,200 SF
  5. Office Suite: 800 SF

Validation Score: 0.95
Validation Passed: ✅
Bid Ready: ✅
Readiness Score: 0.92
```

## Files Changed

1. `app/scripts/run_institutional_room_extract.py` (NEW)
2. `app/services/pipeline.py` (routing improvements)
3. `app/services/institutional_validation.py` (room area completeness gate)
4. `tests/test_phase_7_1_routing.py` (NEW)

## Constraints Met

✅ No new AI calls  
✅ No breaking changes to row-house flow  
✅ Minimal changes, production-safe  
✅ Dev-only script (no API endpoint)  
✅ Deterministic validation rules  
✅ Files <300 lines (except CLI script which is ~260 lines)

## Next Steps

1. Run the CLI script on an institutional PDF to verify extraction
2. Verify routing triggers correctly on `page_index` indicators
3. Verify room area completeness gate catches incomplete extractions
4. Test with a PDF that has `scope_type="repair"` but strong `room_schedule` indicators






