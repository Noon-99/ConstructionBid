# Phase 8.1 — Evidence-Centric Navigation

## Summary

Implemented a reusable Evidence Drawer component that provides auditable proof for bid line items and 3D zones, sourced strictly from `evidence_index.json` and existing artifacts.

## Deliverables

### 1. Evidence Drawer Component (`frontend/components/evidence/EvidenceDrawer.tsx`)

**Features**:
- Reusable Sheet component (drawer from right)
- Responsive design (mobile-friendly)
- Sections:
  - **Details Referenced**: Shows detail labels (e.g., "S-011 Detail 4") as badges
  - **Pages**: Clickable page badges with sheet IDs
  - **Evidence Snippets**: Expandable/collapsible snippets with monospace styling
- Empty state: "No evidence linked for this item yet."
- Professional, contractor-friendly UI

**Props**:
```typescript
interface EvidenceDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  subtitle?: string;
  evidence: EvidenceRef[];
}
```

### 2. Evidence Normalization Layer (`frontend/lib/evidence-normalizer.ts`)

**Purpose**: Converts various evidence structures into one UI-safe shape.

**Type**:
```typescript
interface EvidenceRef {
  page_number: number;
  sheet_id?: string | null;
  sheet_title?: string | null;
  location_type?: string | null;
  snippet?: string | null;
  detail_refs?: string[];
  source?: "bid_item" | "zone" | "detail";
}
```

**Functions**:
- `normalizeEvidenceRefs()`: Deduplicates and sorts evidence refs
- `getEvidenceForBidItem()`: Gets evidence for a bid line item
- `getEvidenceForZone()`: Gets evidence for a 3D zone
- `getEvidenceForDetail()`: Gets evidence for a construction detail
- `enrichWithSheetTitles()`: Enriches refs with sheet titles from document_analysis
- `createBidItemKey()`: Creates stable keys for bid items

**Normalization Rules**:
- Deduplicates identical refs (same page + same snippet)
- Sorts by page_number ascending
- Limits snippets displayed to 10 initially (with "Show more")

### 3. Evidence Store Hook (`frontend/lib/useEvidenceIndex.ts`)

**Features**:
- Fetches `evidence_index` once per project page
- Caches in memory (React state)
- Optionally loads `document_analysis` for sheet titles
- Exposes helper methods:
  - `getEvidenceForBidItem(lineItemIndex)`
  - `getEvidenceForZone(zoneId)`
  - `getEvidenceForDetail(detailId)`

**Returns**:
```typescript
{
  evidenceIndex: EvidenceIndex | null;
  loading: boolean;
  error: string | null;
  getEvidenceForBidItem: (index: number) => EvidenceRef[];
  getEvidenceForZone: (zoneId: string) => EvidenceRef[];
  getEvidenceForDetail: (detailId: string) => EvidenceRef[];
}
```

### 4. Bid Tab Integration (`frontend/components/project/BidTab.tsx`)

**Changes**:
- Replaced inline evidence display with "Evidence" button
- Each line item row has an "Evidence" button in a new column
- Clicking opens `EvidenceDrawer` with evidence refs for that item
- Drawer title: `{division} — {description}`
- Subtitle: `Line item {index + 1}`
- Uses `useEvidenceIndex` hook for data fetching

### 5. 3D Tab Integration (`frontend/components/project/ModelViewer3D.tsx`)

**Changes**:
- Added "View Evidence" button in inspection panel
- Button appears for zones (not buildings)
- Clicking opens `EvidenceDrawer` with evidence refs for selected zone
- Drawer title: `Zone — {zone_name}`
- Subtitle: `Type: {zone_type}` (if available)
- Uses `useEvidenceIndex` hook for data fetching

## Key Features

### Read-Only & Deterministic
- No new extraction, no AI, no guessing
- If evidence is missing, shows empty state
- No hardcoded content

### Evidence Sources
- Primary: `evidence_index.json` (via `GET /v1/projects/{project_id}/artifacts/evidence_index`)
- Optional enrichment: `document_analysis.json` (for sheet titles)
- Optional: `page_index.json` (not used in Phase 8.1)

### UI/UX
- Beautiful, professional design (White, Green, Black color scheme via shadcn/ui)
- Drawer opens from right, responsive
- Page badges look clickable (ready for thumbnail integration)
- Snippet blocks have monospace styling (contractor-friendly)
- No clutter: professional and auditable

## Files Created/Modified

**New Files**:
- `frontend/components/evidence/EvidenceDrawer.tsx`
- `frontend/lib/evidence-normalizer.ts`
- `frontend/lib/useEvidenceIndex.ts`

**Modified Files**:
- `frontend/components/project/BidTab.tsx` (integrated EvidenceDrawer)
- `frontend/components/project/ModelViewer3D.tsx` (integrated EvidenceDrawer)
- `frontend/components/project/Model3DTab.tsx` (updated to pass projectId)

**UI Components Added** (via shadcn/ui):
- `components/ui/sheet.tsx`
- `components/ui/scroll-area.tsx`
- `components/ui/separator.tsx`
- `components/ui/accordion.tsx`

## Constraints Met

✅ Read-only  
✅ Deterministic (empty state if evidence missing)  
✅ No hardcoded content  
✅ Uses existing backend artifact endpoints  
✅ No new backend endpoints required  
✅ TypeScript strict, build passes  
✅ Mobile-friendly responsive design  

## Acceptance Criteria

✅ On a project with `evidence_index.json`:
- Bid item → opens drawer → shows page badges + snippets
- 3D zone → opens drawer → shows linked evidence

✅ On a project missing `evidence_index.json`:
- UI shows clear empty state: "No evidence linked for this item yet."

✅ No new backend endpoints required  
✅ No hardcoded example evidence  
✅ TypeScript strict, build passes  

## How to Test

1. **Upload a project**:
   ```bash
   # Upload a PDF via the UI or API
   ```

2. **Run the pipeline**:
   ```bash
   cd backend
   python run_full_pipeline.py <project_id>
   ```

3. **Open project in frontend**:
   - Navigate to `/projects/[projectId]`
   - Go to **Bid** tab
   - Click "Evidence" button on any line item
   - Verify drawer opens with evidence (if available)

4. **Test 3D evidence**:
   - Go to **3D** tab
   - Click on a zone in the 3D viewer
   - Click "View Evidence" button in inspection panel
   - Verify drawer opens with evidence (if available)

5. **Test empty state**:
   - Use a project without `evidence_index.json`
   - Click "Evidence" on any bid item
   - Verify empty state message appears

## Next Steps (Future Phases)

- **Page thumbnail viewer**: When available, page badges will navigate to page viewer
- **Detail graph integration**: Show linked details in drawer
- **Evidence search**: Search across all evidence
- **Export evidence**: Export evidence as PDF or CSV






