# Phase 8.3 — 3D ↔ Bid Heatmap + Zone Cost Attribution

## Summary

Implemented a spatial cost visualization system that colorizes 3D zones by cost impact and shows cost drivers when clicking zones. This closes the loop: **Bid ↔ Geometry ↔ Evidence** in one view.

## Deliverables

### 1. Zone Cost Map Schema (`app/schemas/zone_cost_map.py`)

**ZoneCostItem Fields**:
- `zone_id`, `zone_name`, `zone_type`
- `total_cost`: Total cost attributed to this zone
- `division_breakdown`: Cost breakdown by division (e.g., `{"04 Masonry": 1000.0, "05 Metals": 500.0}`)
- `top_line_items`: Top 5 line items by cost contribution (with title, division, total_cost, contribution_percent, evidence_refs)
- `linked_line_item_ids`: All linked bid line item indices
- `attribution_method`: "evidence_index" | "keyword_fallback" | "none"

**ZoneCostMap**:
- `project_id`, `generated_at`
- `zones`: List of ZoneCostItem
- `max_cost`, `min_cost`: For heatmap normalization

### 2. Zone Cost Mapper (`app/services/zone_cost_mapper.py`)

**Features**:
- Reads `model_3d.json`, `bid_review.json`, `evidence_index.json`
- Maps zones to line items with priority:
  1. **evidence_index explicit links**: Uses `ZoneEvidence.linked_bid_items`
  2. **keyword fallback**: Tokenizes zone_name and line item titles, matches on 2+ overlapping tokens (ignores stopwords)
  3. **none**: If no match found
- Computes:
  - Total cost per zone (sum of linked line items)
  - Division breakdown (aggregate by division)
  - Top 5 line items by cost (with contribution percentages)
- Tokenization handles underscores, hyphens, and spaces

**Integration**:
- Called after bid_review generation (Phase 8.2)
- Saves to `out/{project_id}/zone_cost_map.json`
- Added to `ALLOWED_ARTIFACTS` in API routes

### 3. Frontend Heatmap Visualization

**Model3DTab Updates**:
- Loads `zone_cost_map.json` (optional)
- Passes `zoneCostMap` to `ModelViewer3D`

**ModelViewer3D Updates**:
- **Heatmap Toggle**: Three modes:
  - **None**: Default zone colors (room = light blue, work_zone = orange)
  - **Cost**: Color gradient from green (low) to red (high) based on normalized cost
  - **Division**: Deterministic colors per division (04 Masonry = orange, 05 Metals = blue, etc.)
- **Legend**: Shows min/max cost range when in Cost mode
- **Zone Colorization**: 
  - Cost mode: Interpolates RGB from green (0) to red (1) based on normalized cost
  - Division mode: Uses top division by cost for color
  - Gray for zones with no attribution
- **Inspection Panel Updates**:
  - Shows zone total cost
  - Lists top contributing line items with:
    - Title, division badge
    - Total cost and contribution percentage
    - "Evidence" button to open EvidenceDrawer for that line item
  - Shows division breakdown (sorted by cost)
  - Attribution method badge

### 4. Unit Tests (`tests/test_zone_cost_mapper.py`)

**Test Coverage**:
- ✅ Evidence_index attribution (explicit links)
- ✅ Keyword fallback attribution (token matching)
- ✅ None attribution (no matches)
- ✅ Multiple items per zone (correct totals and breakdown)
- ✅ Min/max cost computation (for heatmap normalization)

All tests passing.

## Key Features

### Deterministic Attribution
- No AI, no guessing
- Priority-based: evidence_index > keyword > none
- Keyword matching requires 2+ token overlap (reduces false positives)
- Tokenization handles underscores, hyphens, spaces

### Cost Visualization
- **Cost Heatmap**: Green (low) → Red (high) gradient
- **Division Heatmap**: Consistent colors per division
- **No Data**: Gray for zones with no attribution
- **Legend**: Shows cost range in Cost mode

### Cost Breakdown
- Top 5 contributing items with percentages
- Division breakdown sorted by cost
- Evidence links work for each line item
- Attribution method shown (evidence_index/keyword_fallback/none)

## Files Created/Modified

**New Files**:
- `backend/app/schemas/zone_cost_map.py`
- `backend/app/services/zone_cost_mapper.py`
- `backend/tests/test_zone_cost_mapper.py`

**Modified Files**:
- `backend/app/services/pipeline.py` (integrated zone_cost_map generation)
- `backend/app/api/routes/projects.py` (added "zone_cost_map" to ALLOWED_ARTIFACTS)
- `frontend/components/project/Model3DTab.tsx` (loads zone_cost_map)
- `frontend/components/project/ModelViewer3D.tsx` (heatmap toggle, colorization, cost breakdown)

## Constraints Met

✅ Deterministic logic only (no AI)  
✅ No invented data; empty states if missing  
✅ Minimal changes: one new artifact + UI enhancements  
✅ Unit tests for zone cost mapping  
✅ Professional layout (shadcn cards, badges)  
✅ TypeScript strict, build passes  

## Acceptance Criteria

✅ `zone_cost_map.json` artifact generated and visible in UI  
✅ 3D heatmap works (None / Cost / Division modes)  
✅ Zone selection shows cost drivers + evidence links  
✅ Top contributing items displayed with percentages  
✅ Division breakdown shown  
✅ Evidence buttons open EvidenceDrawer for line items  
✅ Tests passing  

## How to Test

1. **Run pipeline on a PDF**:
   ```bash
   cd backend
   python run_full_pipeline.py <pdf_path> <project_id>
   ```

2. **Verify zone_cost_map.json generated**:
   ```bash
   ls -lh out/<project_id>/zone_cost_map.json
   python -c "import json; r = json.load(open('out/<project_id>/zone_cost_map.json')); print(f'Zones: {len(r[\"zones\"])}, Max: \${r[\"max_cost\"]:.2f}')"
   ```

3. **Open project in frontend**:
   - Navigate to `/projects/[projectId]`
   - Go to **3D Model** tab
   - Verify heatmap toggle appears (if zone_cost_map exists)
   - Toggle between None / Cost / Division
   - Click a zone → verify inspection panel shows:
     - Zone total cost
     - Top contributing items
     - Division breakdown
   - Click "Evidence" on a line item → verify EvidenceDrawer opens

4. **Test attribution methods**:
   - Zones with evidence_index links should show "evidence_index" badge
   - Zones with keyword matches should show "keyword_fallback" badge
   - Zones with no matches should show "none" badge and $0.00 cost

## Example Output

For a test project:
- **2 zones** mapped
- **Zone 1**: Parapet band — $2,150.50 (evidence_index attribution)
  - Top item: Parapet repair — $2,150.50 (100%)
  - Division: 04 Masonry — $2,150.50
- **Zone 2**: Lintel band — $1,134.00 (keyword_fallback attribution)
  - Top item: Lintel replacement — $1,134.00 (100%)
  - Division: 05 Metals — $1,134.00

## What This Unlocks

After Phase 8.3, the 3D model becomes a **spatial index** for the bid:
- **"Is the 3D another way to view the PDF?"** → Yes! Click zones to see cost drivers
- **"Where is the expensive work?"** → Red zones in Cost heatmap
- **"What drives this zone's cost?"** → Top items with evidence links
- **"Which divisions dominate?"** → Division heatmap shows at a glance

The loop is closed: **Bid ↔ Geometry ↔ Evidence** in one unified view.






