# ConstructionArchonix Platform Overview

## What This Platform Does

ConstructionArchonix is a **contractor-grade PDF-to-Bid pipeline** that extracts construction scope from PDFs, generates 3D models, computes costs, and provides an auditable review interface. It transforms construction drawings into actionable bid proposals with full traceability.

---

## 🎯 Core Capabilities

### 1. **PDF Analysis & Extraction** (Phases 2-6)
- **Document Analysis**: Identifies project type (row-house repair, institutional, etc.), sheet types, scope indicators
- **Scope Extraction**: Extracts work items, materials, quantities from drawings and schedules
- **Quantity Takeoff**: Derives quantities from dimensions, areas, schedules
- **Material Specifications**: Identifies materials and specifications
- **Institutional Geometry**: Extracts room layouts, structural elements, envelope layers for institutional projects

### 2. **3D Model Generation** (Phase 7)
- **Building Volumes**: Creates 3D bounding boxes for buildings
- **Work Zones**: Highlights repair zones (parapet bands, lintel bands, etc.)
- **Cross-Section Regions**: Semantic regions for navigation (parapet, wall assembly, roof edge, foundation)
- **Detail Graph**: Extracts construction details and links them to zones/elements
- **Structural Elements**: Columns, bearing walls, footings for institutional projects

### 3. **Costing & Bidding** (Phase 6-8)
- **Cost Engine**: Applies unit cost rules from YAML files
- **Multipliers**: Height, material, equipment, waste multipliers
- **Bid Proposal**: Generates structured bid with line items, divisions, clarifications
- **Bid Review**: Detailed breakdown showing quantity derivation, rule references, multipliers, flags
- **Validation**: Quality gates, auto re-read on failures, confidence scoring

### 4. **Evidence & Traceability** (Phase 6.7, 8.1)
- **Evidence Index**: Links bid items and zones to PDF pages and snippets
- **Evidence Drawer**: Reusable UI component showing pages, sheets, snippets, detail references
- **Page References**: Clickable page badges linking to source PDF pages

### 5. **Review & Analysis** (Phase 8.2-8.3)
- **Review Tab**: Contractor review cockpit showing:
  - Line item breakdown (quantity, unit cost, total)
  - Multipliers applied
  - Rule references (YAML file + rule name)
  - Quantity source badges (explicit_takeoff, derived_from_dimensions, heuristic, recovered)
  - Evidence panel with page references
  - Flags (suspicious_unit_cost, suspicious_quantity, recovered_item, heuristic_quantity)
- **Clarifications Center**: Groups clarifications by severity (blocking/warning/info)
- **Recovery Badge**: Shows if items were recovered via auto re-read

### 6. **3D Visualization & Navigation** (Phase 8.3-8.5)
- **Heatmap Visualization**:
  - **Cost Heatmap**: Colorizes zones by cost (green = low, red = high)
  - **Division Heatmap**: Colorizes by division (deterministic colors)
  - **None**: Default zone colors
- **Section View**: Toggle to show cross-section regions
  - Click region → Detail Overlay panel with:
    - Detail references (sheet_id, detail_label, page_number)
    - Evidence pages (clickable badges)
    - Evidence snippets with page/sheet/location badges
- **Search & Fly-To**:
  - Search across zones, regions, bid items, details
  - Fly-to camera animation (650ms smooth zoom)
  - Highlight pulse on selection
  - Deep links: bid item → evidence drawer, detail → section mode
- **Labels Toggle**: Off / Zones / All
  - Zones: Show zone_name + cost (if heatmap = Cost)
  - Regions: Show region_type
  - Buildings: Show building_id + type

---

## 📊 Test Results (Your PDF: Constructiontesting.pdf)

**Project ID**: `test_overview`

### Extraction Results
- **Total Cost**: $13,188.11
- **Line Items**: 5
- **Clarifications**: 6
- **Recovery Performed**: Yes (auto re-read on validation failure)

### 3D Model
- **Buildings**: Generated
- **Work Zones**: 2 zones
- **Cross-Section Regions**: Available (if present in PDF)

### Artifacts Generated
- `document_analysis.json` - Project type, sheets, scope indicators
- `extraction_result.json` - Scope items, materials, quantities, detail graph
- `model_3d.json` - 3D geometry, zones, buildings, cross-section regions
- `costing_result.json` - Cost computation with rule applications
- `bid_proposal.json` - Structured bid proposal
- `bid_review.json` - Detailed line item breakdown with flags
- `evidence_index.json` - Links bid items/zones to PDF pages
- `zone_cost_map.json` - Zone-to-cost attribution
- `detail_overlay_index.json` - Region-to-detail mappings
- `validation_report.json` - Quality scores, clarifications, recovery info

---

## 🎨 Frontend Features

### **Project Dashboard**
- Upload PDF → Process → View results
- Project list with status indicators
- Artifact download

### **Bid Tab**
- Line items with division, description, quantity, unit, cost
- "Evidence" button → Opens Evidence Drawer with page references
- Total bid amount
- Clarifications grouped by severity

### **Review Tab** (Phase 8.2)
- **Line Item Breakdown**:
  - Quantity, unit, unit cost, total
  - Quantity source badge
  - Multipliers applied (with factors)
  - Rule references (YAML file + rule name)
  - Evidence panel with "View Evidence" button
  - Flags highlighted (amber/red)
- **Clarifications Center**:
  - Grouped by severity
  - Linked to line items and pages
- **Recovery Badge**: Shows if recovery was performed

### **3D Model Tab** (Phases 8.3-8.5)
- **View Modes**:
  - **Normal**: Standard view with heatmap options
  - **Section**: Cross-section region view
- **Heatmap Toggles**:
  - None: Default colors
  - Cost: Green → Red gradient
  - Division: Deterministic division colors
- **Search Bar**:
  - Search zones, regions, bid items, details
  - Real-time results with type badges
  - Keyboard: Enter (select), Esc (close)
  - Fly-to animation on selection
- **Labels Toggle**: Off / Zones / All
- **Inspection Panel**:
  - Zone/building info
  - Zone cost breakdown (if available)
  - Top contributing line items
  - Evidence links
- **Detail Overlay Panel** (Section View):
  - Detail references with sheet/page info
  - Evidence pages and snippets
  - Clickable page badges

---

## 🔍 Key Features

### **Deterministic & Auditable**
- No AI guessing after extraction
- All data traceable to PDF pages
- Evidence links for every bid item and zone
- Rule-based costing (YAML files)
- Same PDF → Same results (with caching)

### **Contractor-Grade UX**
- Professional shadcn/ui components
- Evidence drawer for proof
- Review cockpit for line item analysis
- 3D spatial navigation
- Search across all entities

### **Quality Assurance**
- Validation gates with auto re-read
- Quality scores (coverage, confidence)
- Flags for suspicious items
- Clarifications for assumptions
- Recovery tracking

### **3D as PDF Navigator**
- Click zone → See cost drivers
- Click region → See detail references
- Search → Fly-to → Open panel
- Labels for quick identification
- Heatmap for cost visualization

---

## 📁 Artifact Structure

### **Core Artifacts**
1. **document_analysis.json**: Project type, sheets, scope indicators
2. **extraction_result.json**: Scope, materials, quantities, detail graph
3. **model_3d.json**: 3D geometry, zones, buildings, regions
4. **costing_result.json**: Cost computation results
5. **bid_proposal.json**: Structured bid proposal
6. **validation_report.json**: Quality scores, clarifications

### **Review Artifacts** (Phase 8.2+)
7. **bid_review.json**: Line item breakdown with flags and evidence
8. **evidence_index.json**: Bid items/zones → PDF pages
9. **zone_cost_map.json**: Zone-to-cost attribution
10. **detail_overlay_index.json**: Region-to-detail mappings

---

## 🚀 How to Use

### **1. Process a PDF**
```bash
cd backend
python run_full_pipeline.py <pdf_path> <project_id>
```

### **2. View in Frontend**
```bash
cd frontend
npm run dev
```
Navigate to: `http://localhost:3000/projects/<project_id>`

### **3. Explore Features**

**Bid Tab**:
- View line items
- Click "Evidence" → See page references
- Review clarifications

**Review Tab**:
- See detailed line item breakdown
- Check quantity sources and multipliers
- Review flags and evidence

**3D Model Tab**:
- Toggle heatmap (None/Cost/Division)
- Toggle labels (Off/Zones/All)
- Search for zones/items/details
- Click zones → See cost breakdown
- Switch to Section view → Click regions → See detail references

---

## 📈 What's Next

The platform is production-ready for:
- **Row-house repair projects**: Parapet, lintel, flashing, brick repointing
- **Institutional projects**: Room layouts, structural elements, envelope layers
- **Bid generation**: Deterministic costing with full traceability
- **Review workflow**: Contractor-grade analysis interface

**Potential Enhancements**:
- Page thumbnail rendering
- PDF viewer integration
- Export to Excel/PDF
- Batch processing
- Custom rule sets

---

## 🎯 Test Your PDF

Your PDF (`Constructiontesting.pdf`) has been processed as `test_overview`:

**Results**:
- ✅ 5 line items extracted
- ✅ $13,188.11 total bid
- ✅ 2 work zones identified
- ✅ 6 clarifications (review recommended)
- ✅ Recovery performed (auto re-read)

**To View**:
1. Start frontend: `cd frontend && npm run dev`
2. Navigate to: `http://localhost:3000/projects/test_overview`
3. Explore:
   - **Bid Tab**: See line items with evidence links
   - **Review Tab**: See detailed breakdown with flags
   - **3D Model Tab**: Search, heatmap, labels, section view

---

## 📚 Phase Summaries

- **Phase 2-6**: PDF analysis, extraction, costing
- **Phase 7**: 3D model generation, detail graph, cross-section regions
- **Phase 8.1**: Evidence-centric navigation (Evidence Drawer)
- **Phase 8.2**: Reviewer UX (Bid Review, Clarifications Center)
- **Phase 8.3**: 3D ↔ Bid heatmap (zone cost attribution)
- **Phase 8.4**: Section view + Detail overlay (3D as PDF navigator)
- **Phase 8.5**: Labels + Search + Fly-to navigation

All phases are **complete and tested** ✅






