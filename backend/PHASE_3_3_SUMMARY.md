# Phase 3.3 — Throttle + Concurrency Control — Summary

## Implementation Complete ✅

### Files Created/Modified

1. **`app/services/throttle.py`** — Throttle class with threading.BoundedSemaphore
2. **`app/core/config.py`** — Added `OPENAI_MAX_CONCURRENCY_PER_WORKER` (default: 3)
3. **`app/services/openai_client.py`** — Integrated throttle into `call_vision()`
4. **`app/services/metrics_collector.py`** — Added throttle metrics to schema
5. **`app/analyzers/*.py`** — Updated all callers to pass `stage_name`
6. **`tests/test_throttle.py`** — Unit tests (6 tests, all passing)

---

## 1. Throttle Implementation

**Class:** `Throttle` in `app/services/throttle.py`

**Key Features:**
- Uses `threading.BoundedSemaphore(max_concurrency)` (prevents over-release bugs)
- Context manager API: `with throttle.acquire(stage_name="stage_2", project_id="abc123"):`
- Measures wait time (ms) from acquire attempt until acquired
- Logs warning if `wait_time_ms > 250` with structured logging
- Always releases in `__exit__` (finally block)
- Thread-safe (uses `threading.Lock` for metrics)

**Singleton Pattern:**
```python
from app.services.throttle import get_throttle
throttle = get_throttle(max_concurrency=3)  # First call
throttle = get_throttle()  # Subsequent calls return same instance
```

---

## 2. Configuration

**Setting:** `OPENAI_MAX_CONCURRENCY_PER_WORKER`

**Default:** `3`

**Location:** `app/core/config.py`

**Usage:**
```python
settings = Settings()
throttle = get_throttle(settings.openai_max_concurrency_per_worker)
```

---

## 3. OpenAI Client Integration

**Updated Method:**
```python
def call_vision(
    self,
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    request_id: str | None = None,
    stage_name: str = "unknown",  # NEW
    project_id: str | None = None,  # NEW
) -> str:
```

**Throttle Wrapping:**
```python
with self.throttle.acquire(stage_name=stage_name, project_id=project_id):
    response = self.client.chat.completions.create(**call_kwargs)
```

**All Callers Updated:**
- `document_analyzer.py` → `stage_name="document_analysis"`
- `page_indexer.py` → `stage_name="page_indexing"`
- `row_house_repair_extractor.py` → `stage_name="row_house_extraction_{pass_name}"` or `"critical_recovery"`
- `institutional_room_extractor.py` → `stage_name="institutional_room_extraction"`
- `structural_notes_extractor.py` → `stage_name="structural_notes_extraction"`

---

## 4. Metrics Integration

**New Fields in `ProjectMetrics`:**
```python
throttle_wait_ms_total: float  # Total wait time across all calls
throttle_wait_ms_by_stage: dict[str, float]  # Wait time by stage
openai_calls_total: int  # Total OpenAI API calls
openai_calls_by_stage: dict[str, int]  # Calls by stage
```

**Metrics Collection:**
- Throttle tracks wait times and call counts internally
- `MetricsCollector.finalize()` retrieves throttle metrics via `throttle.get_metrics()`
- Saved to `metrics.json` alongside existing metrics

**Example Output:**
```json
{
  "throttle_wait_ms_total": 1250.5,
  "throttle_wait_ms_by_stage": {
    "document_analysis": 500.2,
    "page_indexing": 750.3
  },
  "openai_calls_total": 15,
  "openai_calls_by_stage": {
    "document_analysis": 1,
    "page_indexing": 9,
    "row_house_extraction_pass_A": 3,
    "critical_recovery": 2
  }
}
```

---

## 5. Logging Behavior

**Warning Threshold:** `250ms`

**Log Format:**
```
WARNING | Throttle wait: 350ms for stage document_analysis
         (includes project_id if provided)
```

**No Logging:** If wait time ≤ 250ms (noise control)

---

## 6. Unit Tests

**All Tests Pass (6/6):**

1. ✅ `test_throttle_enforces_concurrency` — Verifies max concurrent threads ≤ max_concurrency
2. ✅ `test_throttle_measures_wait_time` — Verifies wait time measurement
3. ✅ `test_throttle_logs_long_waits` — Verifies logging for waits > 250ms
4. ✅ `test_throttle_metrics_tracking` — Verifies metrics collection
5. ✅ `test_throttle_singleton` — Verifies singleton pattern
6. ✅ `test_throttle_reset_metrics` — Verifies metrics reset

**Run Tests:**
```bash
pytest tests/test_throttle.py -v
```

---

## 7. Thread Safety

- **BoundedSemaphore:** Prevents over-release bugs
- **threading.Lock:** Protects metrics dictionary access
- **Context Manager:** Ensures release in `finally` block
- **No Race Conditions:** All shared state protected by locks

---

## 8. Usage Example

```python
from app.services.openai_client import OpenAIClient
from app.core.config import Settings

settings = Settings()
client = OpenAIClient(settings)

# All calls are automatically throttled
response = client.call_vision(
    messages=[...],
    stage_name="document_analysis",
    project_id="abc123"
)
```

---

## 9. Benefits

✅ **Prevents 429 Storms:** Limits concurrent API calls per worker
✅ **Per-Worker Isolation:** Each worker has its own throttle instance
✅ **Observability:** Metrics track wait times and call counts
✅ **No Code Changes:** Existing code works with default `stage_name="unknown"`
✅ **Thread-Safe:** Safe for RQ workers (threaded execution)

---

## Ready for Phase 3.4 (Caching) ✅






