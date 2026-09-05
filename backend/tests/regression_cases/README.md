# Regression Test Suite

This directory contains regression test cases for the Construction Bid AI pipeline.

## Structure

```
regression_cases/
  row_house_001/
    input.pdf          # Test PDF file
    expectations.json   # Expected results
  institutional_001/
    input.pdf
    expectations.json
  expectations_schema.json  # JSON schema for expectations
  run_golden_test.py   # Golden test runner
```

## Running Tests

### Golden Test (Single PDF)

```bash
cd backend
python -m tests.regression_cases.run_golden_test path/to/test.pdf [output_dir]
```

The golden test will:
- Run the full pipeline
- Assert Critical-5 coverage ≥ 4/5
- Verify dimension conflicts are resolved
- Confirm Stage 3 and 4 run
- Check validation score ≥ 0.85
- Validate recovery behavior

### Expectations Schema

Each test case has an `expectations.json` file with measurable expectations:

- `project_type`: Expected project type
- `scope_type`: Expected scope type
- `required_scope_keys`: List of scope keywords that must be present
- `dimension_ranges`: Expected dimension ranges (min/max)
- `minimum_room_count`: For institutional projects
- `gate_pass_expectation`: Whether validation should pass
- `minimum_validation_score`: Minimum expected score
- `critical_5_minimum_coverage`: Minimum Critical-5 items (for row_house repair)
- `stage_3_expected`: Whether Stage 3 should run
- `stage_4_expected`: Whether Stage 4 should run

## Metrics

Each pipeline run generates `metrics.json` in the output directory with:

- Pages sent per stage
- Token usage (prompt, completion, total)
- Cost estimates
- Latency per stage
- Critical coverage score
- Dimension confidence
- Validation score

## Adding New Test Cases

1. Create a new folder: `{project_type}_{number}/`
2. Add `input.pdf` to the folder
3. Create `expectations.json` following the schema
4. Run the golden test to verify






