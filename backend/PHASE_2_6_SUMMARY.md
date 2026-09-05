# Phase 2.6 — Acceptance Testing + Regression Harness

## Implementation Summary

### ✅ Task 2.6A — Golden Test Run

**Created:** `tests/regression_cases/run_golden_test.py`

This script runs the full pipeline on a test PDF and asserts:

1. **Critical-5 coverage ≥ 4/5** (ideally 5/5)
   - Checks for: parapet, lintel, flashing, brick/repoint, crack_repair
   - Calculates coverage ratio

2. **Dimension conflicts resolved**
   - Verifies `authoritative_dimensions` exists
   - Checks width, depth, height are present
   - Confirms conflicts were resolved

3. **Stage 3 and 4 run**
   - Verifies `model_3d` is generated
   - Verifies `costing_result` is computed
   - Confirms they only run if validation passes

4. **Validation score ≥ 0.85**
   - Reads from `validation_report.json`
   - Fails if score too low

5. **Recovery triggered appropriately**
   - Checks `rerun_performed` flag
   - Validates recovery used ≤4 pages
   - Verifies recovery notes are present

**Usage:**
```bash
cd backend
python -m tests.regression_cases.run_golden_test path/to/test.pdf [output_dir]
```

### ✅ Task 2.6B — Regression Suite Structure

**Created:**
- `tests/regression_cases/row_house_001/expectations.json`
- `tests/regression_cases/institutional_001/expectations.json`
- `tests/regression_cases/expectations_schema.json`
- `tests/regression_cases/README.md`

**Structure:**
```
regression_cases/
  row_house_001/
    input.pdf          # Test PDF (to be added)
    expectations.json   # Measurable expectations
  institutional_001/
    input.pdf
    expectations.json
  expectations_schema.json  # JSON schema
  run_golden_test.py   # Test runner
  README.md            # Documentation
```

**Expectations.json includes:**
- `project_type`, `scope_type`
- `required_scope_keys` (list of keywords)
- `dimension_ranges` (min/max bounds)
- `minimum_room_count` (for institutional)
- `gate_pass_expectation` (boolean)
- `minimum_validation_score`
- `critical_5_minimum_coverage`
- `stage_3_expected`, `stage_4_expected`

### ✅ Task 2.6C — Evaluation Metrics

**Created:** `app/services/metrics_collector.py`

**Metrics Collected:**
- **Per Stage:**
  - `pages_sent`: Number of pages sent
  - `tokens_prompt`, `tokens_completion`, `tokens_total`
  - `latency_seconds`
  - `cost_estimate_usd`

- **Aggregated:**
  - `total_pages_sent_stage1`
  - `total_pages_sent_stage2`
  - `total_pages_sent_recovery`
  - `total_tokens`
  - `total_cost_estimate_usd`
  - `total_latency_seconds`

- **Quality:**
  - `critical_coverage_score` (0.0-1.0)
  - `dimension_confidence` (0.0-1.0)
  - `validation_score` (0.0-1.0)

**Integration:**
- Metrics collector integrated into `PipelineOrchestrator.run_full_pipeline()`
- Tracks pages sent at each stage
- Records token usage from OpenAI client
- Calculates cost estimates (gpt-4o-mini pricing)
- Saves `metrics.json` to `out/{project_id}/metrics.json`

**OpenAI Client Updates:**
- Added `last_usage` tracking
- Added `get_last_usage()` method
- Token usage automatically captured after each API call

## Next Steps

1. **Run Golden Test:**
   ```bash
   python -m tests.regression_cases.run_golden_test /path/to/QueensConstruction.pdf
   ```

2. **Verify Output:**
   - Check `out/{project_id}/validation_report.json`
   - Check `out/{project_id}/metrics.json`
   - Verify all assertions pass

3. **If Tests Fail:**
   - Review `validation_report.json` for errors
   - Check `metrics.json` for token usage patterns
   - Adjust page selection or recovery logic as needed

## Files Created/Modified

**New Files:**
- `tests/regression_cases/run_golden_test.py`
- `tests/regression_cases/expectations_schema.json`
- `tests/regression_cases/row_house_001/expectations.json`
- `tests/regression_cases/institutional_001/expectations.json`
- `tests/regression_cases/README.md`
- `app/services/metrics_collector.py`
- `PHASE_2_6_SUMMARY.md`

**Modified Files:**
- `app/services/openai_client.py` - Added token usage tracking
- `app/services/pipeline.py` - Integrated metrics collection

## Notes

- Token usage tracking is approximate for multi-call stages (like page indexing)
- Cost estimates use gpt-4o-mini pricing ($0.15/$0.60 per 1M tokens)
- Metrics are saved automatically after each pipeline run
- Golden test can be run standalone or integrated into CI/CD






