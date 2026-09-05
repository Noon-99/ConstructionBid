# Phase 8.2 — Reviewer UX: Bid Line Item Breakdown + Clarifications Center

## Summary

Implemented a contractor-grade "review cockpit" UI that provides detailed breakdown of each bid line item with evidence, flags, and clarifications.

## Deliverables

### 1. Bid Review Schema (`app/schemas/bid_review.py`)

**BidLineItemReview Fields**:
- `line_item_id`, `line_item_index`, `division`, `title`
- `quantity`, `unit`, `unit_cost`, `total_cost`
- `rule_refs`: List of `RuleRef` (rule_name, yaml_file, match_keywords_used)
- `multipliers_applied`: List of `MultiplierApplied` (name, factor)
- `quantity_source`: explicit_takeoff | derived_from_dimensions | heuristic | recovered | allowance | unknown
- `evidence_refs`: List of `EvidenceRef` (page_number, sheet_id, snippet)
- `flags`: List of flags (suspicious_unit_cost, suspicious_quantity, recovered_item, heuristic_quantity)

**BidReview**:
- `project_id`, `total_bid`
- `line_items`: List of BidLineItemReview
- `recovery_performed`: Whether recovery/re-read was performed
- `recovery_pages`: Pages that were re-read
- `generated_at`: ISO timestamp

### 2. Bid Review Generator (`app/services/bid_review_generator.py`)

**Features**:
- Generates review breakdown from `bid_proposal.json`, `costing_result.json`, `validation_report.json`, and `evidence_index.json`
- Maps cost items to bid line items by keyword matching
- Extracts rule references, multipliers, and evidence
- Generates flags deterministically:
  - `recovered_item`: If recovery_performed and item keywords match rerun_notes
  - `heuristic_quantity`: If quantity_source == "heuristic"
  - `suspicious_quantity`: If quantity <= 0.01 (non-allowance)
  - `suspicious_unit_cost`: Unit-cost thresholds by unit type:
    - SF: < $0.50 or > $500
    - LF: < $1 or > $1000
    - EA: < $1 or > $5000
    - CY: < $10 or > $2000
    - Generic: < $1 or > $1000

**Integration**:
- Called after bid_proposal and evidence_index generation
- Saves to `out/{project_id}/bid_review.json`
- Added to `ALLOWED_ARTIFACTS` in API routes

### 3. Review Tab Component (`frontend/components/project/ReviewTab.tsx`)

**Features**:
- **Recovery Banner**: Shows if recovery_performed with pages re-read
- **Summary Card**: Total bid, line items count, flagged items, recovered items, heuristic items
- **Line Item Breakdown**: Collapsible accordion for each item showing:
  - Quantity, unit cost, total cost, quantity source badge
  - Multipliers applied (with badges)
  - Rule references (rule name + YAML file)
  - Evidence panel with page badges + "View Evidence" button
  - Flags highlighted (amber/red based on severity)
- **Clarifications Center**: Groups clarifications by severity (critical/warning/info) with icons

**UI Components**:
- Uses shadcn/ui: Card, Accordion, Badge, Alert, Button, Separator
- Professional, contractor-friendly layout
- Color-coded flags (destructive for suspicious, secondary for recovered/heuristic)

### 4. Clarifications Center

**Features**:
- Pulls clarifications from `bid_proposal.json`
- Groups by severity:
  - **Critical**: Red alerts with AlertCircle icon
  - **Warning**: Amber alerts with AlertTriangle icon
  - **Info**: Blue alerts with Info icon
- Shows count for each severity group
- Each clarification shows full text

### 5. Unit Tests (`tests/test_bid_review_generator.py`)

**Test Coverage**:
- ✅ Basic bid review generation
- ✅ Flag generation (suspicious costs, quantities, heuristic)
- ✅ Recovered item detection
- ✅ Evidence references from evidence_index
- ✅ Suspicious unit cost detection by unit type

All tests passing.

## Key Features

### Deterministic Flag Generation
- No AI, no guessing
- Rule-based thresholds for suspicious costs
- Keyword matching for recovered items
- Unit-type-specific cost thresholds

### Evidence Integration
- Links to evidence_index for page/sheet references
- Falls back to quantity_evidence from cost items
- "View Evidence" button opens EvidenceDrawer (Phase 8.1)

### Recovery Tracking
- Shows recovery banner if rerun_performed
- Lists pages that were re-read
- Shows rerun_notes from validation report
- Flags items that were recovered

### Professional UI
- Clean, contractor-friendly layout
- Color-coded flags (red for suspicious, amber for warnings)
- Collapsible breakdowns to reduce clutter
- Clear quantity source badges

## Files Created/Modified

**New Files**:
- `backend/app/schemas/bid_review.py`
- `backend/app/services/bid_review_generator.py`
- `frontend/components/project/ReviewTab.tsx`
- `backend/tests/test_bid_review_generator.py`

**Modified Files**:
- `backend/app/services/pipeline.py` (integrated bid_review generation)
- `backend/app/api/routes/projects.py` (added "bid_review" to ALLOWED_ARTIFACTS)
- `frontend/app/projects/[projectId]/page.tsx` (added Review tab)

## Constraints Met

✅ Deterministic logic only (no AI)  
✅ No invented data; empty states if missing  
✅ Minimal changes: one new artifact + one new tab  
✅ Unit tests for bid_review generation and flag rules  
✅ Professional layout (shadcn cards, badges)  
✅ TypeScript strict, build passes  

## Acceptance Criteria

✅ `bid_review.json` artifact generated and visible in UI  
✅ Each line item shows: quantity, unit cost, multipliers, rules, evidence, flags  
✅ Clarifications grouped by severity with icons  
✅ Recovery banner shows when rerun_performed=true  
✅ Flags highlighted (amber/red)  
✅ Tests passing  

## How to Test

1. **Run pipeline on a PDF**:
   ```bash
   cd backend
   python run_full_pipeline.py <pdf_path>
   ```

2. **Verify bid_review.json generated**:
   ```bash
   ls -lh out/<project_id>/bid_review.json
   ```

3. **Open project in frontend**:
   - Navigate to `/projects/[projectId]`
   - Go to **Review** tab
   - Verify line items show breakdowns
   - Click "View Evidence" to open EvidenceDrawer
   - Check flags are highlighted correctly

4. **Test with recovery**:
   - Use a project that triggered recovery
   - Verify recovery banner appears
   - Verify recovered items are flagged

## Example Output

For the test PDF:
- **5 line items** reviewed
- **Recovery performed**: True (pages 5, 6 re-read)
- **7 flags** total across items
- Flags include: suspicious_unit_cost, recovered_item, heuristic_quantity

## What This Unlocks

After Phase 8.2, contractors can:
- **Answer "Why this price?"**: See exact rule, multipliers, quantity source
- **Answer "Where is the proof?"**: Click evidence to see pages/snippets
- **Spot anomalies instantly**: Flags highlight suspicious costs/quantities
- **Review assumptions**: Clarifications center shows all system assumptions

Ready for **Phase 8.3 — 3D ↔ Bid heatmap**.






