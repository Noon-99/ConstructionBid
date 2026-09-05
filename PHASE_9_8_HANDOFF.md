# Phase 9.8 Handoff — Proposal Template Engine (In Progress)

## Current Status

**Phase 9.8 — Proposal Template Engine** is **90% complete** but has 2 failing tests due to nested template processing complexity.

### What's Working ✅
- All template files created (`executive_summary.md`, `scope_section.md`, `logistics.md`, `permits_inspections.md`, `payment_schedule.md`, `project_schedule.md`, `exclusions.md`, `assumptions.md`)
- Template engine service (`proposal_template_engine.py`) implemented with recursive processing
- Pipeline integration complete — generates `proposal_markdown.md` after labor breakdown
- Artifact registered in `ALLOWED_ARTIFACTS`
- 2 tests passing (missing files, estimated duration)
- Core rendering functionality works

### What Needs Fixing 🔧
- 2 tests failing: `test_render_contractor_proposal_markdown_with_contractor_bid` and `test_render_contractor_proposal_markdown_fallback_to_bid_proposal`
- Issue: Nested template processing (`{{#each sections}}` → `{{#if line_items}}` → `{{#each line_items}}`) not rendering line items correctly
- The recursive `_render_template_section()` call with `item_context` should work but line items aren't appearing in output
- Root cause: When processing `{{#each sections}}`, the `item_context` has `line_items` but nested `{{#each line_items}}` inside `{{#if line_items}}` isn't being processed correctly

### Files Modified
- `backend/app/services/proposal_template_engine.py` (complete rewrite)
- `backend/app/templates/proposal/*.md` (8 template files)
- `backend/app/services/pipeline.py` (added proposal markdown generation)
- `backend/app/api/routes/projects.py` (added `proposal_markdown` to ALLOWED_ARTIFACTS)
- `backend/tests/test_proposal_template_engine.py` (4 tests, 2 failing)

---

## Project Context & History

### Completed Phases

**Phase 7.4** — Cross-Sections, Detail Graphs & Drawing Intelligence
- Detail graph schema and extractor
- Cross-section regions in 3D model
- Evidence linking

**Phase 8.1-8.6** — Evidence-Centric Navigation
- EvidenceDrawer component (reusable)
- Evidence normalization layer
- Bid/Review/3D integration
- PDF page viewer with bbox highlighting
- Evidence deep-linking everywhere
- BBox extraction (PyMuPDF + OCR fallback)

**Phase 9.0-9.7** — Contractor Bid Synthesis Layer
- **9.0**: Bid mode guardrail (`bid_mode: "conceptual" | "contractor"`)
- **9.1A/B**: Contractor profile schema + endpoint (NYC default)
- **9.2A/B**: Expanded scope schema + engine (scaffolding, dumpsters, permits)
- **9.3A/B**: Labor breakdown schema + synthesizer (crew, productivity, costs)
- **9.4A/B**: Contractor bid schema + composer (combines conceptual + expanded + labor + overhead/profit)
- **9.5**: UI toggle (Conceptual/Contractor) in BidTab
- **9.6**: Contractor proposal PDF export (separate from conceptual `proposal.pdf`)
- **9.7**: Region resolver (NYC/NJ/TX/US_DEFAULT profiles, automatic selection)

**Phase 9.8** — Proposal Template Engine (CURRENT)
- Markdown templates for professional bid sections
- State-agnostic, works with any contractor profile
- Deterministic rendering from `contractor_bid.json` or `bid_proposal.json` fallback

---

## Our Prompt Rules & Approach

### 1. **Surgical Edits Only**
- Make minimal, targeted changes
- Don't rewrite entire files unless necessary
- Preserve existing functionality
- One change per logical unit

### 2. **No Fake/Hardcoded Data**
- Always use real data from artifacts
- Never invent values or mock data
- If data is missing, show empty states gracefully
- Use actual API responses, not placeholders

### 3. **Don't Break Existing Functionality**
- All existing tests must pass
- Verify imports don't break
- Check linter errors before and after
- Test affected code paths

### 4. **Deterministic & Additive**
- Same inputs → same outputs (no randomness)
- Add new features without modifying existing ones
- Use feature flags or mode toggles when needed
- Backward compatible changes only

### 5. **TypeScript Strict Mode**
- No `any` types
- Proper type definitions
- Fix all type errors before proceeding
- Use existing type utilities

### 6. **Backend: Pydantic Models**
- Use existing schemas where possible
- Add new fields as optional when extending
- Validate all inputs
- Use `model_dump_json()` for serialization

### 7. **Frontend: React Best Practices**
- Server components by default, `"use client"` only when needed
- Use SWR for data fetching (deduping, caching)
- Memoize derived values
- Fail closed on errors with UI feedback

### 8. **Testing Requirements**
- Unit tests for pure functions
- Integration tests for pipeline stages
- Test error cases (missing files, invalid data)
- Verify deterministic behavior

### 9. **Code Quality**
- No AI-generated fluff in comments
- Actionable comments only
- Consistent naming conventions
- Follow existing patterns

### 10. **Performance & UX**
- Skeleton loaders, not spinners
- Smooth transitions
- Prevent layout jumps
- Fast, confident feel

---

## How We Handle Tasks

### Task Breakdown
1. **Read existing code** to understand structure
2. **Create TODO list** for complex tasks (3+ steps)
3. **Make surgical changes** one at a time
4. **Test immediately** after each change
5. **Fix linter errors** before moving on
6. **Verify existing tests** still pass
7. **Update TODO list** as we progress

### Example Surgical Prompt Format

```
TASK X.Y — Feature Name (Brief Description)

CURSOR PROMPT:

[Clear goal statement]

Backend:
- [Specific file/function to modify]
- [Exact changes needed]
- [Schema updates if any]

Frontend:
- [Component/file to modify]
- [UI changes needed]
- [State management if any]

Tests:
- [What to test]
- [Expected behavior]

Constraints:
- [What NOT to change]
- [Backward compatibility requirements]
- [Performance considerations]

Deliverables:
- [Specific files changed]
- [Tests passing]
- [No breaking changes]
```

---

## Current Issue: Nested Template Processing

### Problem
The template engine processes nested structures like:
```
{{#each sections}}
  {{#if line_items}}
    {{#each line_items}}
      | {{title}} |
    {{/each}}
  {{/if}}
{{/each}}
```

But `line_items` aren't rendering in the final output.

### Debugging Findings
- `item_context` correctly contains `line_items` when processing `{{#each sections}}`
- `_get_context_value(item_context, "line_items")` returns the list correctly
- The recursive `_render_template_section(block_content, item_context)` call should process nested blocks
- But the final output shows empty table rows

### Suspected Issue
The recursive processing might be:
1. Processing `{{#if line_items}}` before `{{#each line_items}}` is ready
2. Not finding the correct matching close tags for nested structures
3. Context scoping issue when merging `item_context`

### Next Steps to Fix
1. Add debug logging to see what `item_context` contains at each recursion level
2. Verify `_find_matching_close_tag()` correctly handles nested tags
3. Test with a simpler nested structure first (e.g., `{{#each}}` → `{{#each}}` without `{{#if}}`)
4. Consider processing blocks in a different order (process `{{#if}}` before `{{#each}}` in nested contexts)

---

## Files to Review

### Key Files
- `backend/app/services/proposal_template_engine.py` — Main template engine (472 lines)
- `backend/app/templates/proposal/scope_section.md` — Scope template with nested structure
- `backend/tests/test_proposal_template_engine.py` — Failing tests to fix

### Related Files
- `backend/app/services/pipeline.py` — Pipeline integration (line ~1255)
- `backend/app/api/routes/projects.py` — Artifact allowlist
- `backend/app/schemas/contractor_bid.py` — Contractor bid schema
- `backend/app/schemas/bid_proposal.py` — Conceptual bid schema (fallback)

---

## Next Chat Prompt

Copy this into the next chat:

---

**CONTEXT: Phase 9.8 — Proposal Template Engine (90% Complete)**

We're implementing a deterministic proposal template engine that renders professional contractor bid markdown from `contractor_bid.json` (or `bid_proposal.json` fallback). The engine uses simple markdown templates with Handlebars-like syntax (`{{variable}}`, `{{#if}}`, `{{#each}}`, `{{#unless}}`).

**Current Status:**
- ✅ All 8 template files created
- ✅ Template engine service implemented with recursive processing
- ✅ Pipeline integration complete
- ✅ Artifact registered
- ✅ 2/4 tests passing
- ❌ 2 tests failing: nested template processing not rendering `line_items` correctly

**The Issue:**
When processing nested structures like `{{#each sections}}` → `{{#if line_items}}` → `{{#each line_items}}`, the inner `line_items` aren't appearing in the final output. The `item_context` correctly contains `line_items`, but the recursive `_render_template_section()` call isn't processing them.

**Files:**
- `backend/app/services/proposal_template_engine.py` (main engine)
- `backend/app/templates/proposal/scope_section.md` (nested template)
- `backend/tests/test_proposal_template_engine.py` (failing tests)

**Our Rules:**
- Surgical edits only
- No fake data
- Don't break existing functionality
- Deterministic & additive
- TypeScript strict
- Test immediately

**Task:**
Fix the nested template processing so that `{{#each line_items}}` inside `{{#each sections}}` correctly renders line item rows in the markdown output. Verify both failing tests pass.

**Approach:**
1. Add debug logging to trace `item_context` at each recursion level
2. Verify `_find_matching_close_tag()` handles nested tags correctly
3. Test with simpler nested structure first
4. Fix the root cause (likely context scoping or processing order)
5. Run tests to verify fix

---

## Quick Reference: Project Structure

```
backend/
  app/
    services/
      proposal_template_engine.py  ← CURRENT FOCUS
      contractor_bid_composer.py
      scope_expander.py
      labor_synthesizer.py
      region_resolver.py
    templates/
      proposal/  ← 8 markdown templates
    schemas/
      contractor_bid.py
      expanded_scope.py
      labor_breakdown.py
    api/routes/
      projects.py  ← Artifact allowlist
  tests/
    test_proposal_template_engine.py  ← 2 failing tests

frontend/
  components/project/
    BidTab.tsx  ← Contractor toggle UI
  app/projects/[projectId]/
    contractor-proposal/page.tsx  ← Contractor PDF route
```

---

## Success Criteria

Phase 9.8 is complete when:
- ✅ All 4 tests pass
- ✅ `proposal_markdown.md` is generated in pipeline
- ✅ Markdown contains all sections with proper formatting
- ✅ Line items render correctly in scope section table
- ✅ No breaking changes to existing functionality
- ✅ No linter errors

---

**Ready to continue!** 🚀
