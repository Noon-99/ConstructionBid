# Phase 8.6A — PDF Page Viewer in EvidenceDrawer

## Summary

Implemented a PDF-first evidence viewer that displays actual PDF page images alongside evidence snippets. EvidenceDrawer now shows page thumbnails, main page viewer, and evidence list in a three-column layout.

## Deliverables

### 1. Backend — Page Image Endpoints ✅

**File**: `backend/app/api/routes/pages.py`

**Endpoints**:
- `GET /v1/projects/{project_id}/pages` - List all pages
  - Returns: `{ project_id, page_count, pages: [{ page_number, url }] }`
  - Validates project exists
  - Reads from `storage/{project_id}/pages/page_{n}.png`
- `GET /v1/projects/{project_id}/pages/{page_number}.png` - Stream page image
  - Validates page_number (1 <= page_number <= page_count)
  - Returns PNG file with `Content-Type: image/png`
  - Prevents path traversal (deterministic filename)

**Security**:
- No arbitrary filename input
- Page numbers validated as integers
- Range validation (1 to page_count)
- Deterministic file paths only

**Integration**:
- Registered in `app/main.py`
- Uses `StorageService` for file access

### 2. Backend — Optional bbox Fields ✅

**Files**:
- `backend/app/schemas/evidence_index.py`
- `backend/app/schemas/bid_review.py`

**Added Fields**:
- `bbox: dict[str, float] | None` - Bounding box {x0, y0, x1, y1} (normalized 0..1 or absolute px)
- `bbox_source: Literal["none", "vision_box", "heuristic"] | None` - Source of bbox

**For Phase 8.6A**:
- All bbox fields set to `None` and `bbox_source="none"`
- Non-breaking change (optional fields)
- UI handles null bbox gracefully

### 3. Frontend — EvidenceDrawer Upgrade ✅

**File**: `frontend/components/evidence/EvidenceDrawer.tsx`

**New Layout** (Three Columns):
- **Left (20%)**: Page thumbnails list
  - Small images from `.../pages/{n}.png`
  - Shows page number badge
  - Highlights selected page
  - Shows evidence count badge if page has evidence
  - Click to select page
- **Center (55-60%)**: Main page image viewer
  - Full-size page image
  - Bbox overlay rectangles (if bbox exists)
  - Centered, scrollable
- **Right (20-25%)**: Evidence list
  - Details referenced (badges)
  - Evidence snippets for selected page
  - Accordion with expandable snippets
  - Shows "No region box available yet" if bbox is null

**Features**:
- Loads page list on drawer open
- Selects initial page (first page from evidence, or page 1)
- Bbox overlay rendering (absolute positioned rectangles)
- Handles null bbox gracefully
- Responsive layout

### 4. Frontend — API Client ✅

**File**: `frontend/lib/api.ts`

**New Methods**:
- `api.listPages(projectId)` - Fetch page list
- `api.getPageImageUrl(projectId, pageNumber)` - Get page image URL

### 5. Frontend — Evidence Normalizer Update ✅

**File**: `frontend/lib/evidence-normalizer.ts`

**Updated**:
- `EvidenceRef` interface includes `bbox` and `bbox_source` fields
- Normalization preserves bbox data from backend

### 6. Integration Updates ✅

**Files Updated**:
- `frontend/components/project/BidTab.tsx` - Passes `projectId` to EvidenceDrawer
- `frontend/components/project/ReviewTab.tsx` - Passes `projectId` to EvidenceDrawer
- `frontend/components/project/ModelViewer3D.tsx` - Passes `projectId` to EvidenceDrawer

### 7. Tests ✅

**File**: `backend/tests/test_page_endpoints.py`

**Test Cases**:
- `test_pages_list_ok` - List pages for existing project
- `test_pages_list_404_project` - 404 for non-existent project
- `test_page_png_ok` - Get valid page image
- `test_page_png_out_of_range_400` - 400 for out-of-range page
- `test_page_png_non_int_400` - 400 for invalid page number
- `test_page_png_negative_400` - 400 for negative page number
- `test_page_png_404_missing_file` - 404 when file doesn't exist

## Key Features

### **PDF-First Viewer**
- Real PDF page images (not OCR text)
- Thumbnail navigation
- Main viewer with zoom/scroll
- Evidence snippets linked to pages

### **Bbox Overlay Support**
- Renders overlay rectangles when bbox exists
- Handles null bbox gracefully
- Shows "No region box available yet" message
- Ready for Phase 8.7 bbox extraction

### **Secure File Access**
- No path traversal
- Deterministic file paths
- Page number validation
- Range checking

### **Professional UX**
- Three-column layout
- Page thumbnails with evidence count
- Selected page highlighting
- Evidence snippets with expand/collapse
- Responsive design

## Acceptance Criteria

✅ Clicking any line item → EvidenceDrawer opens → shows page thumbnails + real page image
✅ Selecting different pages updates the main image instantly
✅ No bbox: still useful (page + snippet references)
✅ bbox present (future) will render overlay correctly without code changes
✅ All routes are secure + unit tested
✅ Frontend builds successfully
✅ TypeScript strict passes

## Out of Scope (Explicitly NOT Now)

- ❌ bbox extraction (Phase 8.7)
- ❌ OCR
- ❌ Editing/annotation
- ❌ PDF rendering via PDF.js (using stored PNGs)

## How to Test

1. **Process a PDF**:
   ```bash
   cd backend
   python run_full_pipeline.py <pdf_path> <project_id>
   ```

2. **Start Frontend**:
   ```bash
   cd frontend
   npm run dev
   ```

3. **Test EvidenceDrawer**:
   - Navigate to `/projects/{project_id}`
   - **Bid Tab**: Click "Evidence" on any line item
   - **Review Tab**: Click "View Evidence" on any line item
   - **3D Model Tab**: Click "View Evidence" on a zone
   - Verify:
     - Page thumbnails appear on left
     - Main page image shows in center
     - Evidence snippets appear on right
     - Clicking thumbnails updates main image
     - Bbox overlays render if bbox exists (currently none)

## Example Behavior

**Before Phase 8.6A**:
- EvidenceDrawer showed only text snippets and page badges
- No visual reference to actual PDF pages

**After Phase 8.6A**:
- EvidenceDrawer shows actual PDF page images
- Three-column layout: thumbnails | page viewer | evidence
- Click thumbnail → See full page image
- Evidence snippets linked to specific pages
- Bbox overlays ready (when bbox data available)

## What This Unlocks

After Phase 8.6A, contractors can:
- **See actual PDF pages** when reviewing evidence
- **Navigate pages visually** via thumbnails
- **Link evidence snippets to pages** directly
- **Prepare for bbox overlays** (Phase 8.7)

The EvidenceDrawer is now a **true PDF-first reviewer**: visual, auditable, and ready for bbox extraction.






