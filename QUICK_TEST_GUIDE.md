# Quick Test Guide — ConstructionArchonix

## Your Test Project: `test_overview`

Your PDF (`Constructiontesting.pdf`) has been processed! Here's what was extracted:

### 📊 Results Summary

**Bid Proposal**:
- **Total Bid**: $13,188.11
- **Line Items**: 5
- **Quality Score**: 0.85 (Bid Ready, but review recommended)
- **Clarifications**: 6
- **Recovery**: Yes (auto re-read performed)

**Line Items**:
1. **Parapet repair** - $2,150.50 | Flag: `recovered_item`
2. **Brick repointing** - $9,828.00 | Flag: `recovered_item`
3. **Lintel replacement** - $1,134.00 | Flag: `heuristic_quantity`
4. **Flashing installation** - $33.26 | Flags: `recovered_item`, `heuristic_quantity`
5. **Crack repair** - $42.35 | Flags: `recovered_item`, `heuristic_quantity`

**3D Model**:
- **Buildings**: 2
- **Work Zones**: 2 (parapet_band, lintel_band)

---

## 🚀 How to View in Frontend

### Step 1: Start Frontend Server
```bash
cd /Users/thanoonthabet/ConstructionArchonix/frontend
npm run dev
```

### Step 2: Open Browser
Navigate to: `http://localhost:3000/projects/test_overview`

---

## 🎯 What to Test

### **1. Bid Tab** (Phase 8.1)
- ✅ View 5 line items with costs
- ✅ Click "Evidence" button on any line item
- ✅ See Evidence Drawer with:
  - Page badges (clickable)
  - Evidence snippets
  - Detail references (if any)

### **2. Review Tab** (Phase 8.2)
- ✅ See detailed line item breakdown:
  - Quantity, unit, unit cost, total
  - Quantity source badge (explicit_takeoff, derived_from_dimensions, heuristic, recovered)
  - Multipliers applied
  - Rule references (YAML file + rule name)
  - Evidence panel with "View Evidence" button
  - Flags highlighted (recovered_item, heuristic_quantity)
- ✅ See "Recovered via re-read" banner (recovery was performed)
- ✅ Clarifications Center grouped by severity

### **3. 3D Model Tab** (Phases 8.3-8.5)

#### **Normal View**:
- ✅ **Heatmap Toggle**: None / Cost / Division
  - Try "Cost" → Zones colorized by cost (green = low, red = high)
  - Try "Division" → Zones colorized by division
- ✅ **Labels Toggle**: Off / Zones / All
  - Try "Zones" → See zone names
  - Try "All" → See zones, regions, buildings
- ✅ **Search Bar**: 
  - Type "parapet" → See zones/regions with "parapet"
  - Type "lintel" → See bid items and zones
  - Press `Enter` on first result → Camera flies to it
  - Press `Esc` → Closes dropdown
- ✅ **Click a Zone** → Inspection panel shows:
  - Zone info
  - Zone cost breakdown (if available)
  - Top contributing line items
  - "View Evidence" button

#### **Section View**:
- ✅ Toggle to "Section" → Cross-section regions appear (if available)
- ✅ Click a region → Detail Overlay panel shows:
  - Detail references (sheet_id, detail_label, page_number)
  - Evidence pages (clickable badges)
  - Evidence snippets

---

## 🔍 Key Features to Verify

### **Evidence-Centric Navigation** (Phase 8.1)
- Every bid item has an "Evidence" button
- Every zone has a "View Evidence" button
- Evidence Drawer shows real page references from PDF

### **Review Cockpit** (Phase 8.2)
- Line items show quantity derivation
- Flags highlight suspicious items
- Recovery badge shows if auto re-read was performed
- Clarifications grouped by severity

### **3D Heatmap** (Phase 8.3)
- Zones colorized by cost impact
- Click zone → See cost drivers
- Top contributing items with percentages

### **Section View** (Phase 8.4)
- Cross-section regions as translucent volumes
- Click region → See detail references
- Evidence snippets with page badges

### **Search & Fly-To** (Phase 8.5)
- Search works across all entities
- Fly-to animation smooth and accurate
- Deep links open correct panels

---

## 📝 Notes on Your Test Results

**Quality Score: 0.85**
- Above threshold (0.8) → "Bid Ready"
- But close to threshold → Review recommended

**6 Clarifications**
- System identified assumptions
- Review these in Clarifications Center

**Recovery Performed**
- Auto re-read was triggered
- Some items were recovered
- See "Recovered via re-read" banner in Review tab

**Flags**
- `recovered_item`: Item was recovered via auto re-read
- `heuristic_quantity`: Quantity was estimated (not explicitly found)
- Review flagged items carefully

**Zone Cost Map**
- Zones exist but no cost attribution yet
- This is normal if evidence_index doesn't have explicit links
- Keyword fallback may work in some cases

---

## 🎨 UI Tour

### **Navigation**
- **Projects** → List of all processed projects
- **Project Detail** → Tabs: Overview, Bid, Review, 3D Model

### **Bid Tab**
- Line items table
- Evidence buttons
- Total bid amount

### **Review Tab**
- Collapsible line item panels
- Cost breakdown
- Evidence links
- Flags and clarifications

### **3D Model Tab**
- 3D viewer (Three.js)
- Control panel (view mode, heatmap, labels)
- Search bar
- Inspection panel (right side)

---

## 🐛 If Something Doesn't Work

1. **Check backend is running**: `cd backend && python -m uvicorn app.main:app --reload`
2. **Check frontend is running**: `cd frontend && npm run dev`
3. **Check artifacts exist**: `ls -lh backend/out/test_overview/*.json`
4. **Check browser console**: F12 → Console tab for errors

---

## 📚 Full Documentation

See `PLATFORM_OVERVIEW.md` for complete feature list and architecture.

---

**Ready to test!** Start the frontend and navigate to `/projects/test_overview` 🚀






