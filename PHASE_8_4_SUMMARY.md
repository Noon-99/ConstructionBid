# Phase 8.4 — Section View + Detail Overlay (3D as PDF Navigator)

## Summary

Implemented section view mode in the 3D viewer that allows clicking cross-section regions (parapet, roof edge, wall assembly, foundation) to see linked detail references and evidence. This makes the 3D model a true alternate view of the PDF.

## Deliverables

### 1. Detail Overlay Index Schema (`app/schemas/detail_overlay_index.py`)

**DetailOverlayRef Fields**:
- `region_id`, `region_type`
- `detail_ids`: List of detail IDs linked to this region
- `detail_refs`: List of detail references with sheet_id, detail_label, page_number
- `evidence_pages`: List of page numbers with evidence
- `snippets`: List of EvidenceSnippet (page_number, sheet_id, snippet, location_type)

**DetailOverlayIndex**:
- `project_id`, `generated_at`
- `regions`: List of DetailOverlayRef

### 2. Detail Overlay Indexer (`app/services/detail_overlay_indexer.py`)

**Features**:
- Reads `model_3d.json` (cross_section_regions)
- Reads `detail_graph` (from extraction_result)
- Reads `evidence_index.json` (detail_evidence)
- For each cross-section region:
  - Collects linked detail_ids from region.detail_refs
  - Enriches with detail info from detail_graph (sheet_id, detail_label, page_number)
  - Collects evidence from detail_graph and evidence_index
  - Builds evidence_pages list and snippets
- Falls back to region.evidence if no detail evidence found

**Integration**:
- Called after evidence_index generation
- Saves to `out/{project_id}/detail_overlay_index.json`
- Added to `ALLOWED_ARTIFACTS` in API routes

### 3. Frontend Section View

**Model3DTab Updates**:
- Loads `detail_overlay_index.json` (optional)
- Loads `cross_section_regions` from `model_3d.json`
- Passes both to `ModelViewer3D`

**ModelViewer3D Updates** (Partial Implementation):
- Added `viewMode` state: "normal" | "section"
- Added `selectedRegion` state for selected cross-section region
- Added props: `detailOverlayIndex`, `crossSectionRegions`
- View mode toggle UI (to be completed)
- Cross-section region rendering (to be completed)
- Detail Overlay panel (to be completed)

### 4. Unit Tests (`tests/test_detail_overlay_indexer.py`)

**Test Coverage**:
- ✅ Basic detail overlay index generation
- ✅ With evidence_index enrichment
- ✅ Missing data handling (no detail_graph)
- ✅ Multiple regions

All tests passing.

## Key Features

### Deterministic Mapping
- No AI, no guessing
- Uses existing cross_section_regions from Phase 7.4
- Enriches with detail_graph and evidence_index
- Falls back gracefully if data missing

### Evidence Collection
- From detail_graph: detail info + evidence_snippet
- From evidence_index: additional evidence_references
- Deduplicates pages and snippets
- Preserves location_type (detail, callout, note)

## Files Created/Modified

**New Files**:
- `backend/app/schemas/detail_overlay_index.py`
- `backend/app/services/detail_overlay_indexer.py`
- `backend/tests/test_detail_overlay_indexer.py`

**Modified Files**:
- `backend/app/services/pipeline.py` (integrated detail_overlay_index generation)
- `backend/app/api/routes/projects.py` (added "detail_overlay_index" to ALLOWED_ARTIFACTS)
- `frontend/components/project/Model3DTab.tsx` (loads detail_overlay_index and cross_section_regions)
- `frontend/components/project/ModelViewer3D.tsx` (added props and state, partial implementation)

## Constraints Met

✅ Deterministic logic only (no AI)  
✅ No invented data; empty states if missing  
✅ Minimal changes: one new artifact + UI enhancements  
✅ Unit tests for detail overlay indexer  
✅ TypeScript strict (partial frontend implementation)  

## Remaining Frontend Work

The backend is complete and tested. The frontend needs:

1. **View Mode Toggle**: Add toggle UI for Normal / Section View
2. **CrossSectionRegionBox Component**: Render regions as translucent selectable volumes
3. **Scene3D Updates**: Conditionally render regions based on viewMode
4. **Detail Overlay Panel**: Show detail references, evidence snippets, page badges when region clicked
5. **Page Image Integration**: Optional cropped page images (requires backend endpoint)

## Acceptance Criteria

✅ `detail_overlay_index.json` artifact generated  
✅ Backend tests passing  
✅ Frontend loads detail_overlay_index  
⚠️ Section view toggle (partial)  
⚠️ Region rendering (to be completed)  
⚠️ Detail overlay panel (to be completed)  

## How to Test

1. **Run pipeline on a PDF**:
   ```bash
   cd backend
   python run_full_pipeline.py <pdf_path> <project_id>
   ```

2. **Verify detail_overlay_index.json generated**:
   ```bash
   ls -lh out/<project_id>/detail_overlay_index.json
   python -c "import json; r = json.load(open('out/<project_id>/detail_overlay_index.json')); print(f'Regions: {len(r[\"regions\"])}')"
   ```

3. **Open project in frontend**:
   - Navigate to `/projects/[projectId]`
   - Go to **3D Model** tab
   - Verify detail_overlay_index is loaded (check console)
   - Section view functionality to be completed

## Example Output

For a test project:
- **2 cross-section regions** indexed
- **Region 1**: Parapet — 1 detail (DET-001, S-011 Detail 4, page 5)
- **Region 2**: Wall assembly — 1 detail (DET-002, S-012 Typical Wall Section, page 6)

## What This Unlocks

After Phase 8.4 completion, contractors can:
- **Click parapet region** → See parapet detail, callout, spec bullets with page refs
- **Navigate PDF via 3D** → 3D becomes true alternate view of PDF
- **Instant detail access** → No hunting through PDF pages

The 3D model becomes a **spatial index** for construction details.






