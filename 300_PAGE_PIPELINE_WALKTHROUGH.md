# 300-Page PDF Pipeline Walkthrough

## Complete Pipeline Flow (Step-by-Step)

### 📥 **Stage 0: PDF Upload & Image Conversion** (5-10 minutes)

**What happens:**
1. User uploads 300-page PDF via `POST /v1/projects/upload`
2. PDF saved to `storage/{project_id}/source.pdf`
3. **ALL 300 pages** converted to PNG images (200 DPI)
4. Images saved to `storage/{project_id}/pages/page_1.png` ... `page_300.png`

**Current code:**
- `backend/app/services/document_processor.py::process_pdf()`
- Sequential loop: `for page_num in range(page_count):`

**300-page impact:**
- ✅ **Works fine** - Sequential is OK, ~1-2 seconds per page
- 💾 **Storage**: ~600 MB (300 pages × 2 MB/image)
- ⏱️ **Time**: 5-10 minutes

**No changes needed** ✅

---

### 📋 **Stage 0.5: Page Indexing** (50-75 minutes) 🔴 **CRITICAL BOTTLENECK**

**What happens:**
1. System loads ALL 300 page images into memory
2. For EACH page (1-300):
   - Creates OpenAI Vision API call
   - Sends page image + prompt: "What type is this page?"
   - Waits for response (10-15 seconds per call)
   - Parses JSON: `{"page_types": ["elevation"], "sheet_id": "A-1", ...}`
3. Saves `out/{project_id}/page_index.json` with all 300 classifications

**Current code:**
- `backend/app/services/page_indexer.py::index_pages()`
- Sequential loop: `for page_image in page_images:`

**300-page impact:**
- ❌ **WILL FAIL** - 300 sequential API calls
- ⏱️ **Time**: 50-75 minutes (300 × 15 seconds)
- 💰 **Cost**: $15-30 (300 × $0.05-0.10/page)
- 🚫 **Rate limits**: Will hit OpenAI 429 errors
- ⚠️ **Timeout risk**: Each call has 60-second timeout (should be OK, but risky)

**Required changes:**
1. **Batch processing**: Process 10-20 pages per batch
2. **Async/concurrent**: Use `asyncio` or `concurrent.futures` (respect rate limits)
3. **Progress tracking**: Report "Indexing page 150/300..."
4. **Caching**: Skip pages already indexed (if re-running)
5. **Resumability**: If interrupted, resume from last successful page

**Estimated fix time: 1-2 days**

---

### 🔍 **Stage 1: Document Analysis** (1-2 minutes) ✅

**What happens:**
1. Page selector picks **only 4-8 key pages**:
   - Cover/title page
   - Drawing index
   - Key elevations (front, side)
   - First detail page
2. Analyzes these pages with OpenAI Vision
3. Extracts: project type, scope, address, building type, etc.
4. Saves `out/{project_id}/document_analysis.json`

**Current code:**
- `backend/app/services/page_selector.py::select_pages_for_stage1()`
- Limits to max 4-8 pages

**300-page impact:**
- ✅ **Works fine** - Only processes 4-8 pages, not 300
- ⏱️ **Time**: 1-2 minutes
- 💰 **Cost**: $0.50-1.00

**No changes needed** ✅

---

### 🎯 **Stage 1.5: Typology Resolution** (< 1 second) ✅

**What happens:**
1. Rule-based correction (no AI)
2. Example: If Stage 1 says "unknown" but has "ROW HOUSE" keywords → override to "row_house"
3. Adds `site_context` (row condition, street names)

**300-page impact:**
- ✅ **No impact** - In-memory transformation, no page processing

**No changes needed** ✅

---

### 📝 **Stage 2: Adaptive Extraction** (10-20 minutes) ✅

**What happens:**
1. Page selector picks **relevant pages** for extraction:
   - Scope pages: elevations, details with work callouts
   - Quantity pages: schedules, dimension pages
   - Material pages: specifications, material callouts
   - Geometry pages: plans, sections
2. **Total selected**: Usually 4-20 pages (not 300!)
3. Routes to specific extractor based on project type:
   - Row house → `RowHouseRepairExtractor`
   - Institutional → `InstitutionalRoomExtractor`
4. Each extractor has hard limits:
   - Lintels: max 5 pages
   - Details: max 8 pages
   - Openings: max 6 pages
   - Structural elements: max 5 pages
5. Extracts: scope items, quantities, materials, evidence references
6. Saves `out/{project_id}/extraction_result.json`

**Current code:**
- `backend/app/services/page_selector.py::select_pages_for_stage2()`
- Extractors have hard limits (see `backend/app/analyzers/*.py`)

**300-page impact:**
- ✅ **Works fine** - Only processes 4-20 pages, not 300
- ⏱️ **Time**: 10-20 minutes (depends on selected pages)
- 💰 **Cost**: $2-5

**No changes needed** ✅

---

### 📐 **Stage 2.5A: Dimension Authority** (< 1 second) ✅

**What happens:**
1. Deterministic dimension extraction (no AI)
2. Looks for explicit callouts, dimension strings, scale notes
3. Computes building dimensions (width, depth, height)

**300-page impact:**
- ✅ **No impact** - Uses extraction data, doesn't process pages

**No changes needed** ✅

---

### ✅ **Stage 2.5: Validation Gates** (2-5 minutes if recovery needed) ✅

**What happens:**
1. Validates extraction completeness
2. Checks for Critical-5 items (parapet, lintels, repointing, etc.)
3. If missing items → triggers recovery
4. Recovery re-reads **max 4 additional pages**
5. Saves `out/{project_id}/validation_report.json`

**300-page impact:**
- ✅ **Works fine** - Recovery limited to 4 pages
- ⏱️ **Time**: +2-5 minutes if recovery needed
- 💰 **Cost**: +$0.50-1.00

**No changes needed** ✅

---

### 🎨 **Stage 3: 3D Model Generation** (< 1 second) ✅

**What happens:**
1. Generates 3D model from extraction data (deterministic)
2. Creates zones, buildings, ghost neighbors, ground plane
3. Saves `out/{project_id}/model_3d.json`

**300-page impact:**
- ✅ **No impact** - Uses extraction data, doesn't process pages

**No changes needed** ✅

---

### 💰 **Stage 4: Costing** (< 1 second) ✅

**What happens:**
1. Computes costs from extraction + 3D model (deterministic)
2. Applies pricing profile multipliers
3. Saves `out/{project_id}/costing_result.json`
4. Generates `out/{project_id}/bid_proposal.json`

**300-page impact:**
- ✅ **No impact** - Uses extraction data, doesn't process pages

**No changes needed** ✅

---

### 📄 **Subsequent Stages** (Trade Assemblies, General Conditions, etc.) ✅

**What happens:**
1. Deterministic generation from artifacts
2. No page processing, no AI calls

**300-page impact:**
- ✅ **No impact**

**No changes needed** ✅

---

## 🔴 **The One Critical Problem: Stage 0.5**

### Current Implementation (Sequential)

```python
# backend/app/services/page_indexer.py
def index_pages(self, project_id: str, page_images: list[PdfPageImage]) -> PageIndex:
    indexed_pages: list[PageIndexItem] = []
    
    for page_image in page_images:  # ← 300 iterations!
        page_item = self._index_single_page(page_image, project_id)  # ← API call
        indexed_pages.append(page_item)
    
    return PageIndex(pages=indexed_pages)
```

**Problem:**
- 300 sequential API calls
- ~15 seconds per call = 75 minutes total
- Will hit rate limits (429 errors)
- No progress visibility
- No resumability

### Proposed Solution (Batched + Async)

```python
async def index_pages_batched(self, project_id: str, page_images: list[PdfPageImage]) -> PageIndex:
    indexed_pages: list[PageIndexItem] = []
    batch_size = 10  # Process 10 pages concurrently
    
    # Load cached results if available
    cached_index = self._load_cached_index(project_id)
    
    # Split into batches
    for batch_start in range(0, len(page_images), batch_size):
        batch = page_images[batch_start:batch_start + batch_size]
        
        # Filter out already-cached pages
        uncached_batch = [p for p in batch if p.page_number not in cached_index]
        
        if uncached_batch:
            # Process batch concurrently (respect rate limits)
            batch_results = await asyncio.gather(*[
                self._index_single_page_async(page, project_id)
                for page in uncached_batch
            ])
            
            # Save batch to cache
            self._save_batch_to_cache(project_id, batch_results)
        
        # Report progress
        self._update_progress(project_id, batch_start + len(batch), len(page_images))
    
    # Load complete index from cache
    return self._load_complete_index(project_id)
```

**Benefits:**
- ⏱️ **Time**: ~15-20 minutes (10 concurrent × 15 seconds per batch)
- 🚫 **Rate limits**: Respects throttling (max 3 concurrent per worker)
- 💾 **Caching**: Skips already-indexed pages (resumable)
- 📊 **Progress**: Visible to user

---

## 📊 **Timeline Comparison**

### Current System (Sequential):
```
Stage 0:  PDF → Images           [████████░░] 5-10 min
Stage 0.5: Page Indexing         [████████████████████████████████████████████████████████████████████] 50-75 min  🔴
Stage 1:  Document Analysis      [██] 1-2 min
Stage 2:  Extraction             [██████████] 10-20 min
Stage 2.5: Validation            [██] 2-5 min
Stage 3:  3D Model               [░] <1 sec
Stage 4:  Costing                [░] <1 sec
────────────────────────────────────────────────────────
TOTAL:                           ~90-120 minutes
```

### With Fixes (Batched + Async):
```
Stage 0:  PDF → Images           [████████░░] 5-10 min
Stage 0.5: Page Indexing         [██████████] 15-20 min  ✅
Stage 1:  Document Analysis      [██] 1-2 min
Stage 2:  Extraction             [██████████] 10-20 min
Stage 2.5: Validation            [██] 2-5 min
Stage 3:  3D Model               [░] <1 sec
Stage 4:  Costing                [░] <1 sec
────────────────────────────────────────────────────────
TOTAL:                           ~35-60 minutes  ✅
```

**Time savings: ~50% reduction** 🎯

---

## 💰 **Cost Breakdown (300-Page PDF)**

| Stage | Pages Processed | API Calls | Cost |
|-------|----------------|-----------|------|
| Stage 0.5 (Page Indexing) | **300** | 300 | $15-30 |
| Stage 1 (Document Analysis) | 4-8 | 4-8 | $0.50-1.00 |
| Stage 2 (Extraction) | 4-20 | 10-20 | $2-5 |
| Stage 2.5 (Recovery) | 0-4 | 0-4 | $0.50-1.00 |
| **TOTAL** | **308-332** | **314-332** | **~$18-37** |

**Note**: Stage 0.5 is 90% of the cost. With caching, re-runs cost $3-6 (only Stage 1 + 2).

---

## ✅ **What Already Works (No Changes Needed)**

1. ✅ **Smart Page Selection**: Only processes 4-20 pages in Stages 1 & 2
2. ✅ **Background Jobs**: Pipeline runs in RQ worker (no HTTP timeout)
3. ✅ **LLM Caching**: Prevents redundant API calls
4. ✅ **Rate Limiting**: Throttle singleton (max 3 concurrent)
5. ✅ **Error Recovery**: Retry logic for transient errors
6. ✅ **Extractor Limits**: Hard caps prevent excessive processing

---

## 🎯 **Success Criteria**

1. ✅ 300-page PDF processes end-to-end without errors
2. ✅ Total pipeline time < 60 minutes (with fixes)
3. ✅ No memory errors (< 2 GB peak)
4. ✅ No rate limit errors (429)
5. ✅ Progress visible to user (percentage complete)
6. ✅ All artifacts generated correctly
7. ✅ Cost per 300-page PDF < $40
8. ✅ Re-runs are fast (cached page index)

---

## 📝 **Next Steps**

1. **Review analysis documents** (this + `300_PAGE_PDF_ANALYSIS.md`)
2. **Test current system** with 300-page PDF (see what breaks)
3. **Implement Stage 0.5 fixes** (batching + async + caching)
4. **Test incrementally**: 50 → 100 → 200 → 300 pages
5. **Deploy and monitor**

Ready to start implementation? 🚀





