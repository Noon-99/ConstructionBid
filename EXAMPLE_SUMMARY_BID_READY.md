# Example `/v1/projects/{id}/summary` Output (Bid Ready Fields)

## Example 1: Bid Ready (All Conditions Pass)

```json
{
  "project_id": "abc123",
  "status": "succeeded",
  "last_updated": "2024-01-15T10:30:00",
  "validation_score": 0.95,
  "validation_passed": true,
  "total_cost": 125000.50,
  "bid_ready": true,
  "estimate_mode": "bid_ready",
  "geometry_quality": "authoritative",
  "readiness_score": 0.95,
  "readiness_stamp_text": "BID READY",
  "readiness_reasons_blocking": [],
  "readiness_warnings": [
    "2 clarification(s) present (review assumptions)"
  ]
}
```

## Example 2: Not Ready (Validation Failed)

```json
{
  "project_id": "def456",
  "status": "succeeded",
  "last_updated": "2024-01-15T11:00:00",
  "validation_score": 0.70,
  "validation_passed": false,
  "total_cost": 98000.00,
  "bid_ready": false,
  "estimate_mode": "conceptual",
  "geometry_quality": "derived_from_area",
  "readiness_score": 0.0,
  "readiness_stamp_text": "PRELIMINARY — REVIEW REQUIRED",
  "readiness_reasons_blocking": [
    "Validation did not pass",
    "Validation score too low: 70.00% (required: >= 85%)"
  ],
  "readiness_warnings": [
    "Auto-recovery was performed (targeted re-read occurred)"
  ]
}
```

## Example 3: Not Ready (Geometry Partial)

```json
{
  "project_id": "ghi789",
  "status": "succeeded",
  "last_updated": "2024-01-15T12:00:00",
  "validation_score": 0.90,
  "validation_passed": true,
  "total_cost": 150000.00,
  "bid_ready": false,
  "estimate_mode": "conceptual",
  "geometry_quality": "partial",
  "readiness_score": 0.0,
  "readiness_stamp_text": "PRELIMINARY — REVIEW REQUIRED",
  "readiness_reasons_blocking": [
    "Geometry quality is 'partial' (incomplete geometry data)"
  ],
  "readiness_warnings": []
}
```

## Example 4: Ready with Warnings

```json
{
  "project_id": "jkl012",
  "status": "succeeded",
  "last_updated": "2024-01-15T13:00:00",
  "validation_score": 0.92,
  "validation_passed": true,
  "total_cost": 200000.00,
  "bid_ready": true,
  "estimate_mode": "bid_ready",
  "geometry_quality": "authoritative",
  "readiness_score": 0.82,
  "readiness_stamp_text": "BID READY",
  "readiness_reasons_blocking": [],
  "readiness_warnings": [
    "Auto-recovery was performed (targeted re-read occurred)",
    "Low cache hit rate: 35.0% (may indicate data quality issues)",
    "3 clarification(s) present (review assumptions)"
  ]
}
```

## Field Descriptions

- **`bid_ready`**: `true` if ready for submission, `false` if review required
- **`readiness_score`**: 0.0-1.0 score (0.0 if blockers exist, otherwise based on validation score)
- **`readiness_stamp_text`**: "BID READY" or "PRELIMINARY — REVIEW REQUIRED"
- **`readiness_reasons_blocking`**: List of reasons why bid is not ready (empty if ready)
- **`readiness_warnings`**: List of warnings that don't block but should be reviewed

## Notes

- If bid readiness computation fails, these fields are omitted (summary still returns other fields)
- All fields are computed deterministically from artifacts (no AI calls)
- Warnings don't block bid_ready, but reduce readiness_score slightly






