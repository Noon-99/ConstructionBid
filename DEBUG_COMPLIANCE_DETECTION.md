# Debugging Compliance Detection

## Issue Found
Project `dcfd6ded` has **NO procurement_context** in `document_analysis.json`, meaning the procurement analyzer either:
1. Didn't run
2. Failed silently
3. Returned empty results

## Fixes Applied

### 1. Procurement Analyzer - Always Call GPT
**File:** `backend/app/services/procurement_analyzer.py`
- **Before:** GPT only called if heuristics didn't detect public project
- **After:** GPT always called when enabled (unless heuristics already detected with high confidence)
- **Result:** Enhanced prompt runs on every project

### 2. Better Error Logging
**File:** `backend/app/analyzers/document_analyzer.py`
- Added detailed logging for procurement analysis start/completion
- Changed warning to exception logging with full stack trace
- Logs what procurement payload contains

### 3. Always Return Payload
**File:** `backend/app/services/procurement_analyzer.py`
- Ensures `procurement_context` field always exists (even if empty)
- Prevents validation errors
- Returns minimal valid payload on error

### 4. GPT Results Take Precedence
**File:** `backend/app/services/procurement_analyzer.py`
- GPT results override heuristics for `is_public_project`
- GPT results override heuristics for `requires_prevailing_wage` and `requires_bonds`

## How to Debug

### Step 1: Check Logs
Look for these log messages when running a project:

```
[INFO] Starting procurement signal analysis
[INFO] Procurement GPT detection completed
[INFO] Procurement analysis completed
```

If you see warnings or errors, check the full stack trace.

### Step 2: Verify document_analysis.json
After running a project, check:
```bash
cat out/<project_id>/document_analysis.json | jq '.procurement_context'
```

Should show:
```json
{
  "is_public_project": true/false,
  "detection_confidence": 0.0-1.0,
  "indicators": [...],
  "notes": [...],
  "source_pages": [...]
}
```

### Step 3: Check Compliance Flags
```bash
cat out/<project_id>/document_analysis.json | jq '.requires_prevailing_wage, .requires_bonds, .issuing_authority'
```

### Step 4: Verify Costing Applied Compliance
```bash
cat out/<project_id>/costing_result.json | jq '.compliance_costs, .compliance_total, .compliance_adjustments'
```

### Step 5: Check Bid Proposal Has Compliance Line Items
```bash
cat out/<project_id>/bid_proposal.json | jq '.line_items[] | select(.description | contains("Bond") or contains("Insurance") or contains("Contingency"))'
```

## Verification Script

Run the verification script:
```bash
cd backend
python scripts/verify_compliance_detection.py <project_id>
```

This will show:
- ✅/❌ Whether procurement_context exists
- ✅/❌ Whether compliance flags are set
- ✅/❌ Whether compliance costs were calculated
- ✅/❌ Whether compliance line items are in bid proposal

## Expected Flow

1. **Document Analyzer** calls `procurement_analyzer.analyze()`
2. **Procurement Analyzer**:
   - Runs heuristics on page_index
   - Calls GPT with enhanced prompt (if enabled)
   - Merges results (GPT takes precedence)
   - Returns payload with `procurement_context`, `requires_prevailing_wage`, `requires_bonds`
3. **Document Analyzer** merges procurement payload into `DocumentAnalysis`
4. **Pipeline** reads `requires_prevailing_wage` and `requires_bonds` from analysis
5. **Cost Engine** applies multipliers and calculates compliance costs
6. **Bid Proposal Generator** adds compliance costs as line items

## Common Issues

### Issue: procurement_context is null
**Cause:** Procurement analyzer failed or returned None
**Fix:** Check logs for exceptions, ensure GPT is enabled

### Issue: requires_prevailing_wage is null
**Cause:** GPT didn't detect it or returned null
**Fix:** Check GPT response, may need to enhance prompt further

### Issue: Compliance costs are 0
**Cause:** `requires_bonds` or `requires_prevailing_wage` not set to True
**Fix:** Verify procurement analyzer detected government project correctly

### Issue: No compliance line items in bid proposal
**Cause:** `compliance_costs` dict is empty
**Fix:** Check that `requires_bonds` or `requires_insurance` is True

## Testing

After fixes, re-run a government project and verify:
1. `document_analysis.json` has `procurement_context`
2. `requires_prevailing_wage` and `requires_bonds` are set
3. `costing_result.json` has `compliance_costs` > 0
4. `bid_proposal.json` has compliance line items
5. Total cost is higher than base scope cost
