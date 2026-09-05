# Phase 3.1 — Run State + Resumable Pipeline — Summary

## Implementation Complete ✅

### Files Created/Modified

1. **`app/schemas/run_state.py`** — Pydantic models for run state
2. **`app/services/run_state_store.py`** — Atomic storage service for run state
3. **`app/services/pipeline.py`** — Updated with run state integration
4. **`tests/test_run_state_store.py`** — Unit tests for run state store
5. **`tests/test_pipeline_run_state.py`** — Unit tests for pipeline integration

---

## 1. Example `run_state.json` Output

```json
{
  "project_id": "example_project",
  "current_stage": null,
  "stages": [
    {
      "stage_name": "stage_0_5_page_indexing",
      "status": "succeeded",
      "started_at": "2025-12-15T18:09:13.477000",
      "finished_at": "2025-12-15T18:09:13.477000",
      "attempts": 1,
      "artifacts": {
        "page_index": "out/example_project/page_index.json"
      },
      "error": null
    },
    {
      "stage_name": "stage_1_document_analysis",
      "status": "succeeded",
      "started_at": "2025-12-15T18:09:13.477000",
      "finished_at": "2025-12-15T18:09:13.477000",
      "attempts": 1,
      "artifacts": {
        "document_analysis": "out/example_project/document_analysis.json"
      },
      "error": null
    }
  ],
  "last_updated": "2025-12-15T18:09:13.477000"
}
```

**Location:** `storage/{project_id}/run_state.json`

---

## 2. How Pipeline Decides "Artifact Exists"

The pipeline uses the `_check_artifacts_exist()` method:

```python
def _check_artifacts_exist(self, artifacts: dict[str, str]) -> bool:
    """
    Check if all artifact files exist.
    
    - If artifacts dict is empty → returns True (for in-memory stages)
    - Otherwise → checks each artifact path exists on disk
    - Returns False if ANY artifact is missing
    """
```

**Logic:**
1. **Empty artifacts dict** → Returns `True` (allows skipping in-memory transformation stages based on status only)
2. **Non-empty artifacts** → Checks each file path using `Path.exists()`
3. **All artifacts exist** → Returns `True` (stage can be skipped)
4. **Any artifact missing** → Returns `False` (stage must run)

**Example:**
- `stage_0_5_page_indexing` has artifact `{"page_index": "out/proj/page_index.json"}`
- Pipeline checks: `Path("out/proj/page_index.json").exists()`
- If file exists → skip stage
- If file missing → run stage

---

## 3. Stage List Names

The pipeline uses these stage names (matching method names):

| Stage Name | Method | Produces Artifacts? | Artifact Paths |
|------------|--------|---------------------|----------------|
| `stage_0_pdf_to_images` | `run_stage_0_pdf_to_images()` | No | (uses existing DocumentBundle) |
| `stage_0_5_page_indexing` | `run_stage_0_5_page_indexing()` | Yes | `{"page_index": "out/{project_id}/page_index.json"}` |
| `stage_1_document_analysis` | `run_stage_1_document_analysis()` | Yes | `{"document_analysis": "out/{project_id}/document_analysis.json"}` |
| `stage_1_5_typology_resolution` | `run_stage_1_5_typology_resolution()` | No | `{}` (in-memory transformation) |
| `stage_2_adaptive_extraction` | `run_stage_2_adaptive_extraction()` | Yes | `{"extraction_result": "out/{project_id}/extraction_result.json"}` |
| `stage_2_5a_dimension_authority` | `run_stage_2_5a_dimension_authority()` | No | `{}` (in-memory transformation) |
| `stage_2_5_validation_gates` | `run_stage_2_5_validation_gates()` | Yes | `{"validation_report": "out/{project_id}/validation_report.json"}` |
| `stage_3_model_generation` | `run_stage_3_model_generation()` | Yes | `{"model_3d": "out/{project_id}/model_3d.json"}` |
| `stage_4_costing` | `run_stage_4_costing()` | Yes | `{"costing_result": "out/{project_id}/costing_result.json"}` |

**Note:** Stages with empty artifacts (`{}`) are in-memory transformations. They can be skipped based on `status == "succeeded"` only (no file check needed).

---

## 4. Stage Skipping Logic

The `_should_skip_stage()` method implements:

1. **Stage succeeded + artifacts exist** → Skip (return cached result)
2. **Stage succeeded + artifacts missing** → Re-run (artifacts were deleted)
3. **Stage failed + attempts < 3** → Retry
4. **Stage failed + attempts >= 3** → Skip (max retries reached)
5. **Stage pending/running** → Run normally

---

## 5. Run State Storage

- **Location:** `storage/{project_id}/run_state.json`
- **Atomic writes:** Writes to `.tmp` file first, then renames (prevents corruption)
- **Safe reads:** Returns default `ProjectRunState` if file missing/invalid
- **Auto-initialization:** Creates default state on first access

---

## 6. Integration Points

- **Pipeline initialization:** `PipelineOrchestrator(settings=settings)` creates `RunStateStore`
- **Stage execution:** All stages wrapped with `_execute_stage_with_state()`
- **Artifact tracking:** Each stage declares expected artifacts before execution
- **Error handling:** Failed stages store error message + traceback summary

---

## 7. Testing

All unit tests pass:
- ✅ `test_load_missing_state` — Default state creation
- ✅ `test_save_and_load_state` — Persistence
- ✅ `test_get_stage_state` — Stage lookup
- ✅ `test_update_stage_state` — State updates
- ✅ `test_atomic_write` — Atomic file operations
- ✅ `test_invalid_json_handling` — Error recovery

---

## Ready for Phase 3.2 (Job Queue) ✅






