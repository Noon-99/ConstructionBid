# Phase 8.6C — PDF Viewer + Evidence Highlight Overlay

## Summary

Implemented an embedded PDF viewer using PDF.js (react-pdf) that responds to EvidenceDrawer navigation. When evidence is opened, the PDF viewer automatically jumps to the correct page and highlights bbox regions when available. This creates a "contractor-grade" review experience where evidence references are instantly visible in the actual PDF.

## Deliverables

### 1. Backend — Source PDF Endpoint ✅

**File**: `backend/app/api/routes/projects.py`

**New Endpoint**:
- `GET /v1/projects/{project_id}/source.pdf` - Stream source PDF file
  - Returns PDF file with `Content-Type: application/pdf`
  - Validates project exists
  - Secure file access (no path traversal)

### 2. Frontend — PDF Navigation Context ✅

**File**: `frontend/lib/pdf-navigation-context.tsx`

**Features**:
- `PdfNavigationProvider` - Context provider for shared PDF navigation state
- `usePdfNavigation()` - Hook for components that require PDF navigation
- `usePdfNavigationSafe()` - Safe hook that returns null if context unavailable
- State management:
  - `currentPage` - Current page number (1-based)
  - `highlight` - Bbox highlight with page number, bbox coordinates, and source type
  - `goToPage(pageNumber)` - Navigate to specific page
  - `highlightBbox(highlight)` - Set bbox highlight
  - `clearHighlight()` - Clear current highlight

### 3. Frontend — PDF Viewer Component ✅

**File**: `frontend/components/pdf/PDFViewer.tsx`

**Features**:
- Uses `react-pdf` (PDF.js wrapper) for rendering
- Page navigation controls (prev/next)
- Zoom controls (50% to 300%)
- Syncs with PDF navigation context
- Bbox overlay rendering:
  - Supports `bboxSource: "pdf"` (normalized 0-1 coordinates)
  - Supports `bboxSource: "image"` (normalized 0-1 relative to image)
  - Maps coordinates to rendered page dimensions
  - Blue border + semi-transparent fill
- Keeps PDF viewer mounted for instant page jumps (no rerender delay)

### 4. Frontend — EvidenceDrawer Integration ✅

**File**: `frontend/components/evidence/EvidenceDrawer.tsx`

**Features**:
- Uses `usePdfNavigationSafe()` for optional PDF navigation
- When drawer opens:
  - Navigates PDF viewer to `initialPage` (or first evidence page)
  - Highlights bbox if `initialEvidenceIndex` provided and bbox exists
- When page thumbnail clicked:
  - Navigates PDF viewer to selected page
- When evidence snippet clicked:
  - Navigates PDF viewer to snippet's page
  - Highlights bbox if available
- Gracefully handles missing PDF navigation context (works without PDF viewer)

### 5. Frontend — Project Page Integration ✅

**File**: `frontend/app/projects/[projectId]/page.tsx`

**Features**:
- Wrapped entire page in `PdfNavigationProvider`
- Added "PDF" tab to tabs list
- PDF viewer mounted in PDF tab
- PDF viewer stays mounted (instant navigation)

### 6. Frontend — API Client ✅

**File**: `frontend/lib/api.ts`

**New Method**:
- `api.getSourcePdfUrl(projectId)` - Get source PDF URL

## Key Features

### **PDF Viewer**
- Embedded PDF.js viewer with page navigation
- Zoom controls (50% to 300%)
- Responsive layout
- Error handling for missing PDFs

### **Bbox Highlighting**
- Overlay rectangles when bbox exists
- Supports PDF coordinate space (normalized 0-1)
- Supports image coordinate space (normalized 0-1)
- Maps coordinates to rendered page dimensions
- Blue border + semi-transparent fill
- Handles null bbox gracefully (no overlay, still functional)

### **Deep-Linking**
- EvidenceDrawer → PDF viewer navigation
- Page thumbnail clicks → PDF jumps
- Evidence snippet clicks → PDF jumps + highlights
- Automatic page selection from evidence

### **Performance**
- PDF viewer stays mounted (instant page jumps)
- No rerender delay
- Smooth navigation

## Acceptance Criteria

✅ From any "View Evidence":
  - Drawer opens at right page ✅
  - PDF viewer jumps to the same page ✅
  - If bbox exists → user sees highlight ✅
✅ Evidence click scrolls PDF to region (if bbox exists) ✅
✅ Works even if bbox missing ✅
✅ No hardcoding ✅
✅ TypeScript strict passes ✅
✅ Frontend builds successfully ✅

## Out of Scope (Explicitly NOT Now)

- ❌ bbox generation (Phase 8.7)
- ❌ OCR / text selection
- ❌ PDF.js renderer customization (using default)

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

3. **Test PDF Viewer**:
   - Navigate to `/projects/{project_id}`
   - Click "PDF" tab
   - Verify PDF loads and displays
   - Test page navigation (prev/next)
   - Test zoom controls

4. **Test Evidence → PDF Navigation**:
   - Click "Evidence" on any line item (Bid/Review tab)
   - Verify PDF viewer jumps to correct page
   - Click a page thumbnail in EvidenceDrawer
   - Verify PDF viewer jumps to that page
   - Click an evidence snippet
   - Verify PDF viewer jumps to snippet's page
   - If bbox exists, verify highlight overlay appears

5. **Test Without Bbox**:
   - Open evidence with no bbox
   - Verify PDF still jumps to correct page
   - Verify no errors occur

## Example Behavior

**Before Phase 8.6C**:
- EvidenceDrawer showed page images and snippets
- No connection to actual PDF
- Manual navigation required

**After Phase 8.6C**:
- EvidenceDrawer opens → PDF viewer automatically jumps to page
- Click evidence snippet → PDF jumps + highlights region (if bbox exists)
- Click page thumbnail → PDF jumps instantly
- Bbox overlays show exact evidence location in PDF

## Technical Details

### **Bbox Coordinate Conversion**

**PDF Coordinate Space** (`bboxSource: "pdf"`):
- Bbox is normalized 0-1 relative to PDF page dimensions
- Direct mapping: `left = bbox.x0 * pageWidth`

**Image Coordinate Space** (`bboxSource: "image"`):
- Bbox is normalized 0-1 relative to image dimensions
- For now, assumes image dimensions match rendered page
- Will be refined in Phase 8.7 with actual image dimensions

### **PDF Viewer Mounting**

- PDF viewer stays mounted in PDF tab
- Navigation context allows instant page jumps
- No rerender delay when navigating from EvidenceDrawer

## What This Unlocks

After Phase 8.6C, contractors can:
- **See actual PDF pages** when reviewing evidence
- **Jump directly to evidence locations** with one click
- **See highlighted regions** when bbox is available
- **Navigate efficiently** between evidence and PDF

The system now provides a **true PDF-first review experience**: evidence references are instantly visible in the actual PDF, creating a contractor-grade review workflow.

## Next: Phase 8.7

Phase 8.7 will add bbox extraction so highlights become common, not rare:
- PDF text search + positional data (preferred)
- Fallback: image OCR bounding boxes (last resort)






