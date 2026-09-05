# Phase 8.6B — Evidence Deep-Linking + "Go To Page" Everywhere

## Summary

Implemented deep-linking from anywhere in the UI to the exact PDF page in EvidenceDrawer. Added "Go to PDF Page" buttons throughout the app and standardized evidence references across all artifacts. This closes the audit loop by making every evidence reference clickable and navigable.

## Deliverables

### 1. Backend — Standardized Evidence References ✅

**Files Updated**:
- `backend/app/schemas/detail_overlay_index.py`
  - Updated `EvidenceSnippet` to include `bbox` and `bbox_source` fields (aligned with `EvidenceReference`)
- `backend/app/schemas/zone_cost_map.py`
  - Updated `TopLineItem.evidence_refs` to use `EvidenceReference` type instead of `list[dict]`

**Standardization**:
- All evidence references now use consistent shape:
  - `page_number` (1-based, int >= 1)
  - `sheet_id` (optional)
  - `evidence_snippet` / `snippet`
  - `location_type` (optional)
  - `bbox` (optional, null for Phase 8.6B)
  - `bbox_source` ("none" for Phase 8.6B)
- No invented data - all fields use `null` / empty arrays when missing

### 2. Frontend — EvidenceDrawer "Open At Page" API ✅

**File**: `frontend/components/evidence/EvidenceDrawer.tsx`

**New Props**:
- `initialPage?: number` - 1-based page number to open at
- `initialEvidenceIndex?: number` - Optional index to focus/highlight

**Features**:
- Opens at specified page when drawer opens
- Highlights and scrolls to specified evidence snippet
- Pulse animation for highlighted snippet (2 seconds)
- Auto-scrolls highlighted item into view

### 3. Frontend — EvidenceDrawer Helper ✅

**File**: `frontend/lib/evidence-drawer-helper.ts`

**Functions**:
- `openEvidenceDrawer(params)` - Centralized function for opening drawer
  - Derives `initialPage` from evidence if not provided
  - Handles empty evidence gracefully
  - Standardizes title/subtitle generation
- `getFirstPageFromEvidence(evidenceRefs)` - Helper to get first page number

### 4. Frontend — "Show All Evidence" Toggle ✅

**File**: `frontend/components/evidence/EvidenceDrawer.tsx`

**Features**:
- Toggle between "This Page" and "All Pages"
- When "This Page": Shows only evidence for selected page
- When "All Pages": Shows all evidence across all pages
- Evidence list updates dynamically based on toggle state

### 5. Frontend — "Go to PDF Page" Buttons ✅

**Bid Tab** (`frontend/components/project/BidTab.tsx`):
- Each line item row has "Evidence" button (existing)
- Added `initialPage` prop to EvidenceDrawer
- Opens drawer at first evidence page automatically

**Review Tab** (`frontend/components/project/ReviewTab.tsx`):
- Each line item has "View Evidence" button (existing)
- Added `initialPage` prop to EvidenceDrawer
- Opens drawer at first evidence page automatically

**3D Inspection Panel** (`frontend/components/project/ModelViewer3D.tsx`):
- Zone evidence drawer opens at first page
- Bid item evidence drawer opens at first page
- Both use `initialPage` prop

### 6. Integration Updates ✅

**All EvidenceDrawer Usages Updated**:
- `BidTab.tsx` - Passes `initialPage`
- `ReviewTab.tsx` - Passes `initialPage`
- `ModelViewer3D.tsx` - Passes `initialPage` for zones and bid items

## Key Features

### **Deep-Linking**
- One click from anywhere → Opens EvidenceDrawer at correct page
- Automatic page selection from evidence
- Highlight and scroll to specific snippet
- Works even if evidence is sparse (graceful empty states)

### **Show All Evidence Toggle**
- Toggle between page-filtered and all evidence
- Dynamic evidence list updates
- Clear labeling ("This Page" vs "All Pages")

### **Standardized Evidence**
- All artifacts use consistent evidence shape
- No invented data
- Graceful handling of missing fields

### **Professional UX**
- Pulse animation for highlighted snippets
- Smooth scroll to highlighted item
- Clear visual feedback
- Responsive layout

## Acceptance Criteria

✅ From Bid item → one click → EvidenceDrawer opens on correct page
✅ From 3D zone → one click → EvidenceDrawer opens showing relevant pages/snippets
✅ From Review tab → one click → EvidenceDrawer opens at first evidence page
✅ No crashes when evidence missing
✅ No bbox needed (handles null gracefully)
✅ "Show all evidence" toggle works
✅ Frontend builds successfully
✅ TypeScript strict passes

## Out of Scope (Explicitly NOT Now)

- ❌ bbox generation (next phase)
- ❌ OCR / text selection
- ❌ PDF.js renderer

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

3. **Test Deep-Linking**:
   - **Bid Tab**: Click "Evidence" on any line item → Drawer opens at first evidence page
   - **Review Tab**: Click "View Evidence" on any line item → Drawer opens at first evidence page
   - **3D Model Tab**: Click "View Evidence" on a zone → Drawer opens at first evidence page
   - Verify: Correct page is selected, evidence snippets visible

4. **Test "Show All Evidence" Toggle**:
   - Open EvidenceDrawer
   - Toggle "All Pages" → See all evidence across pages
   - Toggle "This Page" → See only evidence for selected page

5. **Test Highlighting**:
   - Open EvidenceDrawer with evidence
   - Verify first snippet is highlighted (if `initialEvidenceIndex` provided)
   - Verify smooth scroll to highlighted item

## Example Behavior

**Before Phase 8.6B**:
- EvidenceDrawer always opened at page 1
- No way to jump directly to relevant page
- No highlighting of specific snippets

**After Phase 8.6B**:
- Click "Evidence" → Drawer opens at first evidence page
- Evidence snippets automatically visible
- "Show all evidence" toggle for cross-page viewing
- Highlighted snippets with pulse animation
- Smooth scroll to highlighted items

## What This Unlocks

After Phase 8.6B, contractors can:
- **Jump directly to relevant PDF pages** from any UI element
- **See evidence instantly** without manual page navigation
- **View all evidence** or filter by page
- **Navigate efficiently** between bid items, zones, and evidence

The system now feels **"real" and reviewer-grade** even before bbox exists. Every evidence reference is clickable and navigable, closing the audit loop.






