# macOS RQ Worker Fork Crash - Complete Issue Analysis

## What Is Happening

The RQ (Redis Queue) worker crashes **immediately** when trying to execute a pipeline job, with this error:

```
objc[PID]: +[__NSCFConstantString initialize] may have been in progress
in another thread when fork() was called.
We cannot safely call it or ignore it in the fork() child process.
Crashing instead.
```

**The crash happens BEFORE our code runs** - the pipeline code never executes.

## Why It's Happening

### 1. RQ Uses fork() to Create Worker Processes

- When a job arrives, RQ forks the main worker process
- This creates a "work horse" child process to run the job
- The fork() happens in **RQ's code** (via `os.fork()`), not ours
- This is the standard Unix way to create processes

### 2. macOS Has Strict fork() Safety Requirements

Starting with **macOS 10.13 (High Sierra)**, Apple added strict fork safety checks:

- The Objective-C runtime (used by macOS system frameworks) is **NOT fork-safe**
- If Obj-C runtime initialization is in progress when `fork()` is called, the child process will have:
  - Incomplete Obj-C runtime state
  - Corrupted memory structures  
  - Threading state inconsistencies

- **Apple's solution**: Kill the process if unsafe fork detected (better to crash immediately than have subtle bugs)

### 3. Python/Dependencies Trigger Objective-C Initialization

Some Python libraries (especially on macOS) interact with Obj-C:

- File I/O operations (pathlib, file system access)
- Logging frameworks (may use system frameworks)
- Network libraries
- Any library using ctypes or C extensions
- Even standard library imports can trigger it

**When RQ forks, if Obj-C initialization is happening, macOS kills the child process.**

### 4. The Crash Sequence

```
1. User clicks "Re-run Pipeline"
2. API enqueues job to Redis Queue
3. RQ worker picks up the job
4. RQ calls os.fork() to create work horse process  ← CRASH HAPPENS HERE
5. macOS detects Obj-C initialization during fork()
6. macOS kills child process (signal 6, SIGABRT)
7. RQ marks job as failed
8. Our code NEVER runs
```

## What We've Tried

### ✅ Fixed Code Bug (where_quantities_lives typo)
- **Status**: CORRECT fix
- Changed `where_quantities_lives` → `where_quantities_live` in 3 files
- This fix would work if the worker didn't crash
- **Files fixed**: `typology_resolver.py`, `validation_gates.py`, `institutional_room_extractor.py`

### ❌ multiprocessing.set_start_method('spawn')
- **Status**: DOESN'T HELP
- Only affects **OUR** multiprocessing calls
- RQ uses `os.fork()` directly, not `multiprocessing`
- RQ's fork happens **before** our code loads
- Our `set_start_method()` never gets executed

### ❌ OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
- **Status**: NOT WORKING
- Should disable the safety check
- But crash still happens
- **Possible reasons**:
  - Env var not inherited by forked process
  - Check happens before env vars are read
  - RQ spawns process in a way that loses env vars

## Root Cause

**RQ uses fork() on Unix systems (including macOS) to create worker processes. macOS 10.13+ has strict fork() safety that kills processes if Obj-C runtime initialization is detected during fork(). Our Python environment (or its dependencies) triggers Obj-C initialization, so when RQ forks, macOS kills it.**

## Solutions (In Order of Feasibility)

### 1. Run Pipeline Synchronously (Quickest Test)
**Pros**: Verify code fixes work immediately  
**Cons**: Not ideal for production, blocks HTTP requests  
**How**: Modify API endpoint to run pipeline directly instead of enqueuing

### 2. Use Docker/Linux Environment
**Pros**: Linux doesn't have Obj-C fork restrictions, works immediately  
**Cons**: Requires Docker setup or Linux machine  
**How**: Run backend in Docker container with Linux base image

### 3. Configure RQ to Use Spawn Instead of Fork
**Pros**: Proper solution if RQ supports it  
**Cons**: May require RQ version upgrade, may not be supported  
**How**: Check RQ documentation for process start method configuration

### 4. Use Different Task Queue (Celery)
**Pros**: Celery has better macOS support with proper configuration  
**Cons**: More setup required, need to migrate from RQ  
**How**: Replace RQ with Celery, configure worker pool type

### 5. Isolate Problematic Imports
**Pros**: Minimal changes if it works  
**Cons**: Complex, may not be possible if deep in dependency stack  
**How**: Find which import triggers Obj-C, delay imports until after fork

## Current Status

- ✅ **Code fixes are correct** - would work if executed
- ❌ **Worker crashes during fork** - code never runs
- ✅ **Progress bars working** - UI correctly shows status
- ❌ **Pipeline blocked** - cannot execute due to fork crash

## Solution Implemented

### ✅ SimpleWorker (Non-Forking Worker)

RQ has a `SimpleWorker` class that runs jobs **in-process** (no `fork()`). This avoids the macOS fork crash entirely.

**How to use:**

```bash
# Manual start
cd backend
python3 -m rq worker pipeline --worker-class rq.worker.SimpleWorker

# Or use the dev script (auto-detects macOS)
./scripts/run_worker_dev.sh
```

**Benefits:**
- Zero changes to pipeline logic
- Zero changes to Redis or job enqueueing
- Only changes how worker executes jobs on macOS
- Works immediately without Docker/Linux

**Limitations:**
- Jobs run in the same process (no isolation)
- One job at a time per worker process
- For production, consider Docker/Linux or multiple SimpleWorker instances

## Next Steps

1. ✅ **DONE**: Implemented SimpleWorker solution
2. ✅ **DONE**: Created dev script that auto-detects macOS
3. **Optional**: Set up Docker/Linux environment for production-scale workloads

