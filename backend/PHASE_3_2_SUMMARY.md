# Phase 3.2 — Job Queue + Workers — Summary

## Implementation Complete ✅

### Files Created/Modified

1. **`app/services/job_queue.py`** — Job queue service for enqueuing and tracking jobs
2. **`app/workers/worker.py`** — RQ worker with per-project locking
3. **`app/api/routes/jobs.py`** — Job status endpoint
4. **`app/api/routes/projects.py`** — Added `/run` and `/status` endpoints
5. **`app/core/config.py`** — Added Redis/RQ configuration
6. **`pyproject.toml`** — Added `rq` and `redis` dependencies
7. **`tests/test_job_queue.py`** — Unit tests for job queue service

---

## 1. Endpoint Response Shapes

### POST `/v1/projects/{project_id}/run`

**Request:**
```
POST /v1/projects/abc123/run
```

**Response:**
```json
{
  "project_id": "abc123",
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "queued"
}
```

**Status Codes:**
- `200` — Job enqueued successfully
- `404` — Project not found (source.pdf missing)

---

### GET `/v1/jobs/{job_id}`

**Request:**
```
GET /v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Response (Success):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "finished",
  "project_id": "abc123",
  "enqueued_at": "2025-12-15T18:00:00.000000",
  "started_at": "2025-12-15T18:00:01.000000",
  "ended_at": "2025-12-15T18:05:30.000000"
}
```

**Response (Failed):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "failed",
  "project_id": "abc123",
  "enqueued_at": "2025-12-15T18:00:00.000000",
  "started_at": "2025-12-15T18:00:01.000000",
  "ended_at": "2025-12-15T18:01:00.000000",
  "error": "Traceback: RuntimeError: Project already being processed..."
}
```

**Response (Not Found):**
```json
{
  "job_id": "non-existent",
  "status": "not_found",
  "error": "Job not found"
}
```

**Status Codes:**
- `200` — Job found
- `404` — Job not found

**RQ Status Values:**
- `queued` — Job is in queue, waiting to be processed
- `started` — Worker has started processing
- `finished` — Job completed successfully
- `failed` — Job failed with error
- `deferred` — Job deferred (not used in our implementation)

---

### GET `/v1/projects/{project_id}/status`

**Request:**
```
GET /v1/projects/abc123/status
```

**Response (Not Started):**
```json
{
  "project_id": "abc123",
  "status": "not_started",
  "stages": [],
  "last_updated": null
}
```

**Response (Running):**
```json
{
  "project_id": "abc123",
  "status": "running",
  "current_stage": "stage_2_adaptive_extraction",
  "stages": [
    {
      "stage_name": "stage_0_5_page_indexing",
      "status": "succeeded",
      "attempts": 1,
      "started_at": "2025-12-15T18:00:01.000000",
      "finished_at": "2025-12-15T18:00:05.000000",
      "artifacts": {
        "page_index": "out/abc123/page_index.json"
      }
    },
    {
      "stage_name": "stage_1_document_analysis",
      "status": "succeeded",
      "attempts": 1,
      "started_at": "2025-12-15T18:00:05.000000",
      "finished_at": "2025-12-15T18:00:30.000000",
      "artifacts": {
        "document_analysis": "out/abc123/document_analysis.json"
      }
    },
    {
      "stage_name": "stage_2_adaptive_extraction",
      "status": "running",
      "attempts": 1,
      "started_at": "2025-12-15T18:00:30.000000",
      "finished_at": null
    }
  ],
  "last_updated": "2025-12-15T18:00:30.000000"
}
```

**Response (Succeeded):**
```json
{
  "project_id": "abc123",
  "status": "succeeded",
  "current_stage": null,
  "stages": [
    {
      "stage_name": "stage_0_5_page_indexing",
      "status": "succeeded",
      "attempts": 1,
      "artifacts": {
        "page_index": "out/abc123/page_index.json"
      }
    }
    // ... all stages succeeded
  ],
  "last_updated": "2025-12-15T18:05:30.000000"
}
```

**Response (Failed):**
```json
{
  "project_id": "abc123",
  "status": "failed",
  "current_stage": null,
  "stages": [
    {
      "stage_name": "stage_2_adaptive_extraction",
      "status": "failed",
      "attempts": 2,
      "error": "RuntimeError: OpenAI API error..."
    }
  ],
  "last_updated": "2025-12-15T18:01:00.000000"
}
```

**Overall Status Values:**
- `not_started` — No run_state.json exists
- `running` — Pipeline is currently executing (current_stage is set)
- `succeeded` — All stages completed successfully
- `failed` — At least one stage failed
- `completed` — Pipeline finished (some stages may be skipped)

---

## 2. Lock Key Naming

**Lock Key Format:**
```
pipeline:lock:{project_id}
```

**Examples:**
- `pipeline:lock:abc123`
- `pipeline:lock:xyz789`

**Implementation:**
```python
lock_key = f"pipeline:lock:{project_id}"
lock = redis_conn.lock(lock_key, timeout=3600)  # 1 hour max
```

**Behavior:**
- **Non-blocking acquire:** Job fails fast if lock cannot be acquired
- **Timeout:** 3600 seconds (1 hour) maximum lock duration
- **Auto-release:** Lock released in `finally` block after job completes/fails
- **Error message:** Clear error if concurrent run detected:
  ```
  "Project {project_id} is already being processed by another job. 
   Wait for the current job to complete."
  ```

---

## 3. Worker Run Command

**Command:**
```bash
python -m app.workers.worker
```

**What it does:**
1. Connects to Redis using `REDIS_URL` from config (default: `redis://localhost:6379/0`)
2. Listens on queue name from config (default: `pipeline`)
3. Processes jobs by calling `run_pipeline_job(project_id)`
4. Logs all job lifecycle events (start, stage transitions, completion, errors)

**Environment Variables:**
```bash
export REDIS_URL="redis://localhost:6379/0"  # Optional, has default
export RQ_QUEUE_NAME="pipeline"              # Optional, has default
```

**Alternative (using rq command directly):**
```bash
rq worker pipeline --url redis://localhost:6379/0
```

**Worker Output:**
```
2025-12-15 18:00:00 | INFO | Starting RQ worker for queue: pipeline
2025-12-15 18:00:05 | INFO | abc123: Starting pipeline job
2025-12-15 18:00:05 | INFO | abc123: Lock acquired, running pipeline
2025-12-15 18:00:05 | INFO | abc123: Running full pipeline
2025-12-15 18:05:30 | INFO | abc123: Pipeline completed: status=completed
2025-12-15 18:05:30 | INFO | abc123: Lock released
```

---

## 4. Key Features

### Per-Project Locking
- Prevents concurrent pipeline runs for the same project
- Non-blocking: fails fast if lock cannot be acquired
- Auto-released in `finally` block

### Resume from Run State
- Pipeline automatically resumes from next incomplete stage
- Uses Phase 3.1 run_state.json to determine what to skip
- No duplicate work for completed stages

### Clean Status Tracking
- RQ job status: `queued` → `started` → `finished`/`failed`
- Project status: `not_started` → `running` → `succeeded`/`failed`
- Stage-level status in run_state.json

### Structured Logging
- All logs include `project_id` and `job_id`
- Logs at: enqueue, start, stage transitions, completion, errors

---

## 5. Testing

**Unit Tests:**
- ✅ `test_enqueue_project_run` — Verifies job enqueued with correct meta
- ✅ `test_get_job_status_success` — Verifies status retrieval for finished job
- ✅ `test_get_job_status_failed` — Verifies error handling for failed job
- ✅ `test_get_job_status_not_found` — Verifies handling of missing job

**Run Tests:**
```bash
pytest tests/test_job_queue.py -v
```

---

## 6. Local Development Setup

**1. Start Redis:**
```bash
redis-server
# or
docker run -d -p 6379:6379 redis:7-alpine
```

**2. Start Worker:**
```bash
python -m app.workers.worker
```

**3. Start API:**
```bash
uvicorn app.main:app --reload
```

**4. Upload PDF & Run:**
```bash
# Upload PDF
curl -X POST http://localhost:8000/v1/projects/upload \
  -F "file=@test.pdf"

# Get project_id from response, then:
curl -X POST http://localhost:8000/v1/projects/{project_id}/run

# Poll job status
curl http://localhost:8000/v1/jobs/{job_id}

# Poll project status
curl http://localhost:8000/v1/projects/{project_id}/status
```

---

## Ready for Production ✅

All requirements met:
- ✅ Redis + RQ integration
- ✅ Per-project locking
- ✅ Resume from run_state
- ✅ Clean status APIs
- ✅ Structured logging
- ✅ Unit tests
- ✅ No hardcoded paths/sleeps
- ✅ Files <300 lines






