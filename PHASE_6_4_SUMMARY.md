# Phase 6.4 — Automated Proposal PDF Export (Server-Side) — Complete

## ✅ Completed Deliverables

### 1. **Backend PDF Exporter Service** (`app/services/pdf_exporter.py`)
   - Uses Playwright to render frontend proposal page
   - Generates PDF with proper formatting (Letter size, margins)
   - Waits for `#proposal-ready` DOM marker
   - Saves to `out/{project_id}/proposal.pdf`

### 2. **PDF Worker Job** (`app/workers/pdf_worker.py`)
   - RQ job function: `run_proposal_pdf_job(project_id)`
   - Per-project locking: `pdf:lock:{project_id}`
   - Updates run_state with `stage_6_4_pdf_export`
   - Stores artifact path in run_state

### 3. **API Endpoints**
   - **POST `/v1/projects/{project_id}/proposal.pdf`**: Enqueue PDF generation job
     - Returns `{ job_id, project_id, status: "queued" }`
     - Validates project and bid_proposal exist
   - **GET `/v1/projects/{project_id}/proposal.pdf`**: Download PDF
     - Streams PDF file if exists
     - Returns 404 with helpful message if not generated yet
     - Security: Validates path is within storage_root

### 4. **Frontend Updates**
   - **Proposal Page** (`/projects/[projectId]/proposal`):
     - `?print=1` query param support (hides buttons)
     - DOM marker: `<div id="proposal-ready" data-ready="true" />` when data loaded
   - **PdfButton Component** (`components/project/PdfButton.tsx`):
     - Checks if PDF exists (HEAD request)
     - "Generate Proposal PDF" button if missing
     - "Download Proposal PDF" button if available
     - Polls job status when generating
     - Shows loading state during generation

### 5. **Configuration**
   - Added `frontend_base_url` to Settings (default: `http://localhost:3000`)
   - Added `playwright>=1.40.0` to dependencies

### 6. **Run State Integration**
   - Stage name: `stage_6_4_pdf_export`
   - Tracks status, timestamps, artifacts
   - Separate from pipeline stages (0-4)

## 🔧 Technical Details

### PDF Generation Flow
1. User clicks "Generate Proposal PDF"
2. Frontend calls `POST /v1/projects/{id}/proposal.pdf`
3. Backend enqueues RQ job
4. Worker acquires lock and generates PDF
5. Playwright navigates to `{FRONTEND_BASE_URL}/projects/{id}/proposal?print=1`
6. Waits for `#proposal-ready[data-ready='true']`
7. Generates PDF with print media emulation
8. Saves to `out/{id}/proposal.pdf`
9. Updates run_state with artifact path

### Locking Mechanism
- Lock key: `pdf:lock:{project_id}`
- Timeout: 10 minutes
- Non-blocking: Returns error if already locked

### Security
- Path validation: Ensures PDF path is within `storage_root`
- Artifact allowlist: Only allows known artifact names
- No arbitrary file access

## 📝 Setup Instructions

### Install Playwright Chromium
```bash
cd backend
playwright install chromium
```

Or via Python:
```bash
python -m playwright install chromium
```

### Environment Variables
```env
FRONTEND_BASE_URL=http://localhost:3000  # Default
```

### Running the Worker
The PDF worker uses the same RQ queue as the pipeline:
```bash
rq worker pipeline --url redis://localhost:6379/0
```

## 🚀 Usage

1. **Generate PDF**:
   - Navigate to project page
   - Click "Generate Proposal PDF" button
   - Wait for job to complete (button shows "Generating PDF...")
   - Button changes to "Download Proposal PDF" when ready

2. **Download PDF**:
   - Click "Download Proposal PDF" button
   - PDF opens in new tab/downloads

3. **API Usage**:
   ```bash
   # Generate PDF
   curl -X POST http://localhost:8000/v1/projects/{id}/proposal.pdf
   
   # Download PDF
   curl http://localhost:8000/v1/projects/{id}/proposal.pdf -o proposal.pdf
   ```

## ✅ Constraints Met

- ✅ Deterministic (no manual clicking)
- ✅ Non-blocking (uses RQ)
- ✅ Separate stage name (`stage_6_4_pdf_export`)
- ✅ Security (path validation)
- ✅ No hardcoded HTML (renders from real page)
- ✅ Proper error handling

## 📋 Files Created/Modified

### Backend
- `app/services/pdf_exporter.py` (new)
- `app/workers/pdf_worker.py` (new)
- `app/api/routes/projects.py` (updated - added PDF endpoints)
- `app/core/config.py` (updated - added `frontend_base_url`)
- `pyproject.toml` (updated - added `playwright`)

### Frontend
- `app/projects/[projectId]/proposal/page.tsx` (updated - print mode + DOM marker)
- `components/project/PdfButton.tsx` (new)
- `app/projects/[projectId]/page.tsx` (updated - added PdfButton)
- `lib/api.ts` (updated - added PDF methods)

## 🧪 Testing Notes

- Backend: Routes import successfully
- Frontend: Builds without errors
- No Playwright tests in CI (as specified)

## 📝 Next Steps

- Add unit tests for PDF exporter (optional)
- Add integration test for PDF generation (optional)
- Consider caching PDFs if unchanged
- Add PDF preview in UI (optional)






