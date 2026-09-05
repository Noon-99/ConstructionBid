# Phase 6.7 — Evidence-Linked Review — Complete

## ✅ Completed Deliverables

### 1. **Evidence Index Schema** (`app/schemas/evidence_index.py`)
   - `EvidenceReference`: Links to PDF pages with `page_number`, `sheet_id`, `evidence_snippet`, `location_type`
   - `BidItemEvidence`: Evidence for each bid line item with references
   - `ZoneEvidence`: Evidence for each 3D zone with linked bid items
   - `EvidenceIndex`: Complete index structure

### 2. **Evidence Indexer Service** (`app/services/evidence_indexer.py`)
   - `generate_evidence_index()`: Deterministic index generation from existing artifacts
   - Links bid items to `quantity_evidence` from cost items
   - Links zones to their evidence from model_3d
   - Links zones to bid items by keyword matching
   - `save_evidence_index()`: Saves index to JSON file

### 3. **Pipeline Integration**
   - Evidence index generated automatically after bid proposal creation
   - Saved to `out/{project_id}/evidence_index.json`
   - Integrated into `run_full_pipeline()` in `pipeline.py`

### 4. **Artifact Endpoint Support**
   - Added `"evidence_index"` to `ALLOWED_ARTIFACTS` in `projects.py`
   - Available via `GET /v1/projects/{project_id}/artifacts/evidence_index`

### 5. **Frontend Bid Tab Evidence Panel** (`BidTab.tsx`)
   - Click on line item to expand evidence panel
   - Shows evidence references with:
     - Page number badges
     - Sheet ID (if available)
     - Location type (if available)
     - Evidence snippet text
   - Displays basis text from line item
   - Empty state if no evidence available

### 6. **Frontend 3D Tab Evidence Panel** (`ModelViewer3D.tsx`)
   - Updated `InspectionPanel` to show evidence from `evidence_index`
   - Displays evidence references for selected zones
   - Shows page numbers, sheet IDs, location types, and snippets
   - Maintains existing evidence display as fallback

### 7. **Unit Tests** (`tests/test_evidence_indexer.py`)
   - ✅ Links bid items to evidence from cost items
   - ✅ Handles missing evidence gracefully
   - ✅ Saves index to JSON file
   - ✅ Raises error on missing artifacts

## 🔧 Technical Details

### Evidence Linking Logic

**Bid Items → Evidence:**
1. Primary: Extract from `cost_item.quantity_evidence` (page_number, sheet_id, evidence_snippet)
2. Fallback: Parse page numbers from `basis` text
3. Fallback: Match to `scope_of_work` items by description

**Zones → Evidence:**
1. Primary: Extract from `zone.page_number` and `zone.evidence`
2. For buildings: Parse page numbers from `building.evidence` text

**Zones → Bid Items:**
- Keyword matching (exact match or 2+ word overlap)
- Special handling for room types

### Deterministic Rules
- No AI calls
- No guessing (empty state if evidence missing)
- All links based on existing artifact data

## 📋 Files Created/Modified

### Backend
- `app/schemas/evidence_index.py` (new)
- `app/services/evidence_indexer.py` (new)
- `app/services/pipeline.py` (updated - integrated indexer)
- `app/api/routes/projects.py` (updated - added artifact)
- `tests/test_evidence_indexer.py` (new)

### Frontend
- `components/project/BidTab.tsx` (updated - evidence panel)
- `components/project/Model3DTab.tsx` (updated - load evidence_index)
- `components/project/ModelViewer3D.tsx` (updated - show evidence in panel)

## ✅ Constraints Met

- ✅ Deterministic (no AI calls)
- ✅ No guessing (empty states for missing evidence)
- ✅ Read-only (no editing)
- ✅ Uses only existing artifacts
- ✅ Tests required and passing
- ✅ Minimal scope, production-safe

## 🚀 Usage

1. **Automatic Generation**: Evidence index is generated automatically after bid proposal creation
2. **Bid Tab**: Click any line item to see evidence references
3. **3D Tab**: Click any zone to see evidence references in inspection panel
4. **API**: Access via `/v1/projects/{id}/artifacts/evidence_index`

## 📝 Next Steps

Ready for Phase 7 (Generalized Extraction) with auditable, evidence-linked bids and 3D models.






