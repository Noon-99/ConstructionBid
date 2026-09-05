# Phase 6.4.1 & 6.4.2 — Critical Fixes

## ✅ Fixed Issues

### 1. Storage Path Consistency (6.4.1) ✅

**Problem:** PDF was being saved to `./storage/{project_id}/proposal.pdf` while all other artifacts are in `out/{project_id}/...`

**Solution:** Changed all PDF paths to use `out/{project_id}/proposal.pdf`

**Files Updated:**
- `app/services/pdf_exporter.py`: Changed output path from `settings.storage_root` to `Path("out")`
- `app/api/routes/projects.py`: 
  - `generate_proposal_pdf()`: Uses `Path("out") / project_id`
  - `download_proposal_pdf()`: Reads from `Path("out") / project_id / "proposal.pdf"`
  - Security check updated to validate against `Path("out")` instead of `storage_root`
- `app/workers/pdf_worker.py`: Artifact path updated to `out/{project_id}/proposal.pdf`
- `app/api/routes/projects.py`: Added `"proposal_pdf"` to `ALLOWED_ARTIFACTS` set

**Result:** PDF is now stored alongside all other artifacts in `out/{project_id}/proposal.pdf`

### 2. Strict Readiness Marker (6.4.2) ✅

**Problem:** If marker not found in 10s, PDF generation proceeded anyway → could generate blank/half-loaded PDFs

**Solution:** 
- Increased timeout to 30s
- If timeout occurs, raise exception → job fails → user sees error instead of bad PDF

**Code Change:**
```python
# Before:
page.wait_for_selector("#proposal-ready[data-ready='true']", timeout=10000)
except PlaywrightTimeoutError:
    log_ctx.warning("Proposal-ready marker not found, proceeding anyway")

# After:
page.wait_for_selector("#proposal-ready[data-ready='true']", timeout=30000)
except PlaywrightTimeoutError:
    error_msg = "Proposal page did not reach ready state within timeout (30s). Page may still be loading data."
    log_ctx.error(error_msg)
    raise RuntimeError(error_msg) from None
```

**Result:** PDF generation fails fast with clear error message if page doesn't load, preventing bad PDFs

### 3. FRONTEND_BASE_URL Confirmation ✅

**Status:** Already implemented correctly

**Evidence:**
- `app/core/config.py`: Has `frontend_base_url` setting (default: `http://localhost:3000`)
- `app/services/pdf_exporter.py`: 
  - Uses `self.frontend_base_url` from settings
  - Logs full URL: `log_ctx.info(f"Using frontend URL: {proposal_url}")`
  - URL format: `{frontend_base_url}/projects/{project_id}/proposal?print=1`

**Configuration:**
```env
FRONTEND_BASE_URL=http://frontend:3000  # Docker
FRONTEND_BASE_URL=http://localhost:3000  # Dev
```

## 📋 Summary of Changes

### Storage Path
- **Before:** `./storage/{project_id}/proposal.pdf`
- **After:** `out/{project_id}/proposal.pdf`
- **Impact:** All artifacts now in consistent location

### Readiness Marker
- **Before:** 10s timeout, proceed anyway if not found
- **After:** 30s timeout, fail with error if not found
- **Impact:** No more blank/half-loaded PDFs

### Frontend URL
- **Status:** Already correct
- **Logging:** Full URL is logged for debugging
- **Configurable:** Via `FRONTEND_BASE_URL` env var

## 🧪 Testing Checklist

- [ ] PDF saves to `out/{project_id}/proposal.pdf` (not `storage/`)
- [ ] Download endpoint reads from `out/{project_id}/proposal.pdf`
- [ ] Artifact list includes `proposal_pdf`
- [ ] If page doesn't load in 30s, job fails with clear error
- [ ] Frontend URL is logged in PDF exporter
- [ ] Run state artifact path is `out/{project_id}/proposal.pdf`

## 📝 Next Steps

Ready for Phase 6.5 — "Bid Ready" gate + PDF stamp






