# Surgical Roadmap - Task Breakdown

## ✅ EXISTING (Verify Implementation)

### Phase 11.1 - Labor Breakdown
- **Status**: ✅ EXISTS (`labor_synthesizer.py`)
- **Implementation**: Has `estimated_days`, `crew`, `labor_cost`
- **Gap**: Uses estimated_days, NOT explicit hours per assembly/component
- **Needs**: Enhanced to show hours per component (Phase 11.1)

### Phase 12.1 - Proposal Narrative
- **Status**: ✅ EXISTS (`proposal_sections_generator.py`)
- **Implementation**: Has `ExecutiveSummary`, `ScopeSection`, `LogisticsSection`, `PermitsInspectionsSection`, `PaymentSchedule`, `ProjectSchedule`
- **Gap**: May be missing detailed friend-style sections (schedule weeks table, warranty, etc.)
- **Needs**: Verification and enhancement if needed

---

## ❌ MISSING (Build in Order)

### Phase 9.1 - Trade Assemblies Schema + YAML Rules
**Status**: ❌ MISSING  
**Priority**: HIGHEST (foundation for everything else)

**What to build**:
- `app/schemas/trade_assemblies.py` with:
  - `TradeAssembly` (id, title, division, unit, quantity, components[], labor[], equipment[], assumptions[], spec_refs[], evidence_refs[])
  - `TradeComponent` (name, unit, qty, unit_cost, total_cost, cost_source, notes)
  - `LaborComponent` (trade, crew, hours, rate, total_cost, basis)
  - `EquipmentComponent` (name, unit, qty, unit_cost, total_cost, basis)
  - `TradeAssembliesResult`
- `app/rules/trade_assemblies/row_house_repair.yml` with component formulas

---

### Phase 9.2 - Trade Assemblies Generator
**Status**: ❌ MISSING  
**Depends on**: Phase 9.1

**What to build**:
- `app/services/trade_assembly_generator.py`
- Loads YAML rules
- Generates assemblies from bid line items
- Computes components from formulas (e.g., `flashing_qty = Q * 1.0`)
- Saves to `out/{project_id}/trade_assemblies.json`

---

### Phase 9.3 - Trade Assemblies API Exposure
**Status**: ❌ MISSING  
**Depends on**: Phase 9.2

**What to build**:
- Add `"trade_assemblies"` to `ALLOWED_ARTIFACTS`
- Ensure GET endpoint lists it

---

### Phase 9.4 - Trade Assemblies Pipeline Integration
**Status**: ❌ MISSING  
**Depends on**: Phase 9.3

**What to build**:
- Call generator after `bid_proposal` + `evidence_index`
- Save artifact
- Make resumable

---

### Phase 10.1 - General Conditions Engine
**Status**: ❌ MISSING  
**Depends on**: Phase 9.4

**What to build**:
- `app/schemas/general_conditions.py`
- `app/services/general_conditions_estimator.py`
- Deterministic presets for:
  - Mobilization (LS)
  - Scaffolding (weeks) - trigger if exterior masonry > 200 SF OR parapet repair
  - Debris removal / dumpsters (EA)
  - Daily cleanup (days)
  - Dust control (LS)
  - Sidewalk protection (LS) - NYC flag
- Save to `out/{project_id}/general_conditions.json`

---

### Phase 11.1 - Labor Breakdown Enhancement (Explicit Hours)
**Status**: ⚠️ EXISTS BUT NEEDS ENHANCEMENT  
**Depends on**: Phase 9.4 (trade assemblies)

**What to enhance**:
- Current: Uses `estimated_days` from productivity rates
- Needed: Explicit hours per component/assembly from trade assemblies
- Create `LaborLine` (trade, crew, hours, rate, total, basis, related_assembly_id)
- Enhance `labor_model.py` to consume trade_assemblies

---

### Phase 12.1 - Proposal Narrative Enhancement
**Status**: ⚠️ EXISTS BUT NEEDS VERIFICATION  
**Depends on**: Phase 10.1, Phase 11.1

**What to verify/enhance**:
- Verify all friend-style sections exist
- Ensure schedule has weeks table
- Add warranty section if missing
- Ensure proper narrative structure

---

## 📋 TASK EXECUTION ORDER

1. ✅ **TASK 9.1** - Trade Assemblies Schema + YAML Rules (START HERE)
2. ⏳ **TASK 9.2** - Trade Assemblies Generator
3. ⏳ **TASK 9.3** - Trade Assemblies API Exposure
4. ⏳ **TASK 9.4** - Trade Assemblies Pipeline Integration
5. ⏳ **TASK 10.1** - General Conditions Engine
6. ⏳ **TASK 11.1** - Labor Breakdown Enhancement
7. ⏳ **TASK 12.1** - Proposal Narrative Verification/Enhancement

---

## 🎯 STARTING POINT

**Begin with TASK 9.1** - This is the foundation. Everything else depends on trade assemblies.





