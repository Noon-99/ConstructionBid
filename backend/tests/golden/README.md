# Golden Tests for Institutional Projects

This directory contains golden test fixtures and expectations for institutional PDF extraction.

## Structure

- `fixtures/` - Test PDF files (not committed to git)
- `expectations/` - JSON expectation files defining required outputs

## Running Golden Tests

```bash
# Run all golden tests
pytest tests/test_golden_institutional.py -m golden

# Run specific test
pytest tests/test_golden_institutional.py::test_golden_recreation_center -m golden
```

## Adding a New Golden Test

1. Place a test PDF in `fixtures/{project_name}.pdf`
2. Create expectations file `expectations/{project_name}.expectations.json`
3. Add a test function in `test_golden_institutional.py` (or reuse existing)

## Expectations Schema

See `expectations/recreation_center.expectations.json` for a template.

Key fields:
- `min_room_count`: Minimum number of rooms required
- `required_rooms`: List of rooms that must be found (with name pattern and min area)
- `totals`: Expected totals with tolerance
- `required_structural_fields`: Dot-path notation for required structural fields
- `required_codes`: Code references that must be present
- `validation_requirements`: Validation pass/fail requirements

## Outputs

Test outputs are saved to `out/test_runs/{project_id}/` for inspection.
These are not committed to git.






