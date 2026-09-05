"""Institutional-specific validation profile (Phase 4.3).

Hard validation gates for institutional projects that run after Stage 2 extraction.
"""

from app.core.config import Settings
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.extraction_result import ExtractionResult
from app.schemas.validation_report import ValidationIssue


def validate_institutional(
    extraction: ExtractionResult,
    analysis: DocumentAnalysis,
    settings: Settings | None = None,
) -> list[ValidationIssue]:
    """
    Validate institutional project extraction (Phase 4.3, 7.1).
    
    Now includes room area completeness gate (Phase 7.1P).
    """
    """
    Validate institutional project extraction (Phase 4.3).

    Hard validation gates:
    A) Room Program (critical)
    B) Structural Notes (critical)
    C) Evidence integrity (warnings)
    D) Report enrichment with targeted recommendations

    Args:
        extraction: ExtractionResult from Stage 2
        analysis: DocumentAnalysis from Stage 1
        settings: Application settings (optional, will create default if not provided)

    Returns:
        List of ValidationIssue objects
    """
    if settings is None:
        settings = Settings()

    issues: list[ValidationIssue] = []

    # Get configurable thresholds
    room_count_min = getattr(settings, "institutional_room_count_min", 15)
    largest_room_min_sf = getattr(settings, "institutional_largest_room_min_sf", 2500.0)
    area_tolerance_pct = getattr(settings, "institutional_room_area_tolerance_pct", 5.0)

    # A) Room Program validation (critical)
    room_program_issues = _validate_room_program(
        extraction, room_count_min, largest_room_min_sf, area_tolerance_pct
    )
    issues.extend(room_program_issues)

    # B) Structural Notes validation (critical)
    structural_notes_issues = _validate_structural_notes(extraction)
    issues.extend(structural_notes_issues)

    # C) Evidence integrity (warnings)
    evidence_issues = _validate_evidence_integrity(extraction)
    issues.extend(evidence_issues)

    # D) Institutional geometry contract (Phase 4.5)
    geometry_issues = _validate_institutional_geometry(extraction)
    issues.extend(geometry_issues)

    # E) Room Schedule validation (Phase 7.1)
    room_schedule_issues = _validate_room_schedule(extraction, room_count_min, largest_room_min_sf, area_tolerance_pct)
    issues.extend(room_schedule_issues)

    # F) Finish Coverage validation (Phase 7.2)
    finish_coverage_issues = _validate_finish_coverage(extraction)
    issues.extend(finish_coverage_issues)

    # G) Geometry Quality validation (Phase 7.2)
    geometry_quality_issues = _validate_geometry_quality(extraction)
    issues.extend(geometry_quality_issues)

    # H) Structural Elements validation (Phase 7.2)
    structural_elements_issues = _validate_structural_elements(extraction)
    issues.extend(structural_elements_issues)

    # I) Building Envelope validation (Phase 7.2)
    building_envelope_issues = _validate_building_envelope(extraction)
    issues.extend(building_envelope_issues)

    # J) Openings validation (Phase 7.3)
    if analysis:
        openings_issues = _validate_openings(extraction, analysis)
        issues.extend(openings_issues)

        # K) Lintels validation (Phase 7.3)
        lintels_issues = _validate_lintels(extraction, analysis)
        issues.extend(lintels_issues)

        # L) Detail graph validation (Phase 7.4)
        detail_graph_issues = _validate_detail_graph(extraction, analysis)
        issues.extend(detail_graph_issues)

    return issues


def _validate_room_program(
    extraction: ExtractionResult,
    room_count_min: int,
    largest_room_min_sf: float,
    area_tolerance_pct: float,
) -> list[ValidationIssue]:
    """Validate room program (Rule A)."""
    issues: list[ValidationIssue] = []

    if not extraction.room_program:
        issues.append(
            ValidationIssue(
                code="MISSING_ROOM_PROGRAM",
                severity="error",
                message="Room program is required for institutional projects",
                affected_fields=["room_program"],
                recommended_action="Re-read pages with room_schedule or life_safety indicators",
            )
        )
        return issues

    room_program = extraction.room_program

    # A1) Room count check
    if len(room_program.rooms) < room_count_min:
        issues.append(
            ValidationIssue(
                code="INSUFFICIENT_ROOM_COUNT",
                severity="error",
                message=f"Room count {len(room_program.rooms)} is below minimum {room_count_min}",
                affected_fields=["room_program.rooms"],
                recommended_action=f"Re-read pages with room_schedule indicators (need {room_count_min - len(room_program.rooms)} more rooms)",
            )
        )

    # A2) Largest room check
    if room_program.rooms:
        rooms_with_area = [r for r in room_program.rooms if r.area_sf and r.area_sf > 0]
        if rooms_with_area:
            max_area = max(r.area_sf for r in rooms_with_area)
            largest_room = next(r for r in rooms_with_area if r.area_sf == max_area)

            if max_area < largest_room_min_sf:
                issues.append(
                    ValidationIssue(
                        code="LARGEST_ROOM_TOO_SMALL",
                        severity="error",
                        message=f"Largest room '{largest_room.room_name}' area ({max_area:.0f} SF) is below minimum {largest_room_min_sf:.0f} SF - extraction likely incomplete",
                        affected_fields=["room_program.rooms"],
                        recommended_action="Re-read life_safety plan pages to find complete room schedule",
                    )
                )
        else:
            issues.append(
                ValidationIssue(
                    code="NO_ROOM_AREAS",
                    severity="error",
                    message="No rooms with area values found - cannot validate completeness",
                    affected_fields=["room_program.rooms"],
                    recommended_action="Re-read room schedule pages with area columns",
                )
            )

    # A3) Totals validation
    if room_program.totals.existing_gsf is not None:
        extracted_sum = sum(r.area_sf or 0.0 for r in room_program.rooms if r.area_sf)
        stated_total = room_program.totals.existing_gsf

        if stated_total > 0 and extracted_sum > 0:
            diff_pct = abs(extracted_sum - stated_total) / stated_total
            if diff_pct > (area_tolerance_pct / 100.0):
                issues.append(
                    ValidationIssue(
                        code="ROOM_SUM_MISMATCH",
                        severity="error",
                        message=f"Extracted rooms sum ({extracted_sum:.0f} SF) differs from stated total ({stated_total:.0f} SF) by {diff_pct*100:.1f}% (threshold: ±{area_tolerance_pct}%)",
                        affected_fields=["room_program.rooms", "room_program.totals.existing_gsf"],
                        recommended_action="Re-read room schedule pages to resolve area discrepancy",
                    )
                )

    # A4) Addition GSF validation
    if room_program.totals.addition_gsf is not None:
        if room_program.totals.addition_gsf > 0:
            # Check if addition appears in totals and is non-zero (already validated by schema)
            # Additional check: if we have addition, we should have some rooms marked as addition
            # This is a soft check - we don't fail if missing, but could add as warning
            pass

    return issues


def _validate_structural_notes(extraction: ExtractionResult) -> list[ValidationIssue]:
    """Validate structural notes (Rule B)."""
    issues: list[ValidationIssue] = []

    if not extraction.structural_notes:
        issues.append(
            ValidationIssue(
                code="MISSING_STRUCTURAL_NOTES",
                severity="error",
                message="Structural notes are required for institutional projects",
                affected_fields=["structural_notes"],
                recommended_action="Re-read pages with structural_notes, notes, or loads indicators",
            )
        )
        return issues

    structural_notes = extraction.structural_notes

    # B1) Must have at least 1 major spec type
    has_concrete = any(
        c.strength_psi for c in structural_notes.concrete_specs if c.strength_psi
    )
    has_steel = any(
        s.w_shapes or s.hss for s in structural_notes.steel_specs
    )
    has_cmu = any(
        c.unit_strength_psi for c in structural_notes.cmu_specs if c.unit_strength_psi
    )

    if not (has_concrete or has_steel or has_cmu):
        issues.append(
            ValidationIssue(
                code="MISSING_MAJOR_STRUCTURAL_SPEC",
                severity="error",
                message="Missing major spec: must have at least one concrete strength OR steel spec OR CMU spec",
                affected_fields=["structural_notes.concrete_specs", "structural_notes.steel_specs", "structural_notes.cmu_specs"],
                recommended_action="Re-read structural notes pages with concrete, steel, or CMU specifications",
            )
        )

    # B2) Contractor readiness - must have at least 2 of: loads, submittals, inspections, codes
    has_loads = structural_notes.design_loads is not None
    has_submittals = len(structural_notes.submittals) > 0
    has_inspections = len(structural_notes.inspections) > 0
    has_codes = len(structural_notes.code_compliance) > 0

    contractor_readiness_items = [has_loads, has_submittals, has_inspections, has_codes]
    contractor_readiness_count = sum(contractor_readiness_items)

    if contractor_readiness_count < 2:
        missing_items = []
        if not has_loads:
            missing_items.append("loads")
        if not has_submittals:
            missing_items.append("submittals")
        if not has_inspections:
            missing_items.append("inspections")
        if not has_codes:
            missing_items.append("code_compliance")

        issues.append(
            ValidationIssue(
                code="INCOMPLETE_CONTRACTOR_READINESS",
                severity="error",
                message=f"Contractor readiness incomplete: found {contractor_readiness_count}/4 required items (need 2 of: loads, submittals, inspections, code compliance). Missing: {', '.join(missing_items)}",
                affected_fields=["structural_notes"],
                recommended_action=f"Re-read pages with {'/'.join(missing_items)} indicators or notes/compliance page types",
            )
        )

    return issues


def _validate_evidence_integrity(extraction: ExtractionResult) -> list[ValidationIssue]:
    """Validate evidence integrity (Rule C - warnings only)."""
    issues: list[ValidationIssue] = []

    # Check room program evidence
    if extraction.room_program and extraction.room_program.rooms:
        for i, room in enumerate(extraction.room_program.rooms):
            if not room.evidence_snippet or not room.evidence_snippet.strip():
                issues.append(
                    ValidationIssue(
                        code="MISSING_ROOM_EVIDENCE",
                        severity="warning",
                        message=f"Room '{room.room_name}' (index {i}) missing evidence_snippet",
                        affected_fields=[f"room_program.rooms[{i}].evidence_snippet"],
                        recommended_action="Re-read page {room.page_number} to capture evidence",
                    )
                )
            if not room.page_number or room.page_number <= 0:
                issues.append(
                    ValidationIssue(
                        code="MISSING_ROOM_PAGE",
                        severity="warning",
                        message=f"Room '{room.room_name}' (index {i}) missing valid page_number",
                        affected_fields=[f"room_program.rooms[{i}].page_number"],
                        recommended_action="Verify page number assignment during extraction",
                    )
                )

    # Check structural notes evidence
    if extraction.structural_notes:
        sn = extraction.structural_notes

        # Check concrete specs
        for i, spec in enumerate(sn.concrete_specs):
            if not spec.evidence_snippet or not spec.evidence_snippet.strip():
                issues.append(
                    ValidationIssue(
                        code="MISSING_CONCRETE_EVIDENCE",
                        severity="warning",
                        message=f"Concrete spec {i} missing evidence_snippet",
                        affected_fields=[f"structural_notes.concrete_specs[{i}].evidence_snippet"],
                        recommended_action=f"Re-read page {spec.page_number} to capture evidence",
                    )
                )

        # Check steel specs
        for i, spec in enumerate(sn.steel_specs):
            if not spec.evidence_snippet or not spec.evidence_snippet.strip():
                issues.append(
                    ValidationIssue(
                        code="MISSING_STEEL_EVIDENCE",
                        severity="warning",
                        message=f"Steel spec {i} missing evidence_snippet",
                        affected_fields=[f"structural_notes.steel_specs[{i}].evidence_snippet"],
                        recommended_action=f"Re-read page {spec.page_number} to capture evidence",
                    )
                )

        # Check design loads
        if sn.design_loads:
            if not sn.design_loads.evidence_snippet or not sn.design_loads.evidence_snippet.strip():
                issues.append(
                    ValidationIssue(
                        code="MISSING_LOADS_EVIDENCE",
                        severity="warning",
                        message="Design loads missing evidence_snippet",
                        affected_fields=["structural_notes.design_loads.evidence_snippet"],
                        recommended_action=f"Re-read page {sn.design_loads.page_number} to capture evidence",
                    )
                )

    return issues


def _validate_institutional_geometry(extraction: ExtractionResult) -> list[ValidationIssue]:
    """Validate institutional geometry contract (Phase 4.5)."""
    issues: list[ValidationIssue] = []

    if not extraction.institutional_geometry_for_3d:
        issues.append(
            ValidationIssue(
                code="MISSING_INSTITUTIONAL_GEOMETRY",
                severity="error",
                message="Institutional geometry is required for institutional projects",
                affected_fields=["institutional_geometry_for_3d"],
                recommended_action="Re-read life_safety plan pages to extract room layout",
            )
        )
        return issues

    inst_geometry = extraction.institutional_geometry_for_3d

    # Must have at least existing_building.mass OR room_zones >= 10
    has_existing_mass = inst_geometry.existing_building.area_gsf > 0
    room_zone_count = len(inst_geometry.room_zones)

    if not has_existing_mass and room_zone_count < 10:
        issues.append(
            ValidationIssue(
                code="INSUFFICIENT_GEOMETRY",
                severity="error",
                message=f"Insufficient geometry: existing building mass missing and only {room_zone_count} room zones (need >= 10)",
                affected_fields=["institutional_geometry_for_3d"],
                recommended_action="Re-read life_safety plan pages to extract complete room program",
            )
        )

    # If room program exists but geometry has <10 zones, fail
    if extraction.room_program and extraction.room_program.rooms:
        if room_zone_count < 10 and len(extraction.room_program.rooms) >= 15:
            issues.append(
                ValidationIssue(
                    code="GEOMETRY_BUILDER_INCOMPLETE",
                    severity="error",
                    message=f"Room program has {len(extraction.room_program.rooms)} rooms but geometry builder produced only {room_zone_count} zones",
                    affected_fields=["institutional_geometry_for_3d.room_zones"],
                    recommended_action="Re-read life_safety plan pages to extract room areas for geometry",
                )
            )

    return issues


def _validate_room_schedule(
    extraction: ExtractionResult,
    room_count_min: int,
    largest_room_min_sf: float,
    area_tolerance_pct: float,
) -> list[ValidationIssue]:
    """Validate room schedule (Phase 7.1) - placeholder."""
    # TODO: Implement room schedule validation
    return []


def _validate_finish_coverage(extraction: ExtractionResult) -> list[ValidationIssue]:
    """Validate finish coverage (Phase 7.2) - placeholder."""
    # TODO: Implement finish coverage validation
    return []


def _validate_geometry_quality(extraction: ExtractionResult) -> list[ValidationIssue]:
    """Validate geometry quality (Phase 7.2) - placeholder."""
    # TODO: Implement geometry quality validation
    return []


def _validate_structural_elements(extraction: ExtractionResult) -> list[ValidationIssue]:
    """Validate structural elements (Phase 7.2) - placeholder."""
    # TODO: Implement structural elements validation
    return []


def _validate_building_envelope(extraction: ExtractionResult) -> list[ValidationIssue]:
    """Validate building envelope (Phase 7.2) - placeholder."""
    # TODO: Implement building envelope validation
    return []


def _validate_openings(
    extraction: ExtractionResult, analysis: DocumentAnalysis
) -> list[ValidationIssue]:
    """Validate openings (Phase 7.3) - placeholder."""
    # TODO: Implement openings validation
    return []


def _validate_lintels(
    extraction: ExtractionResult, analysis: DocumentAnalysis
) -> list[ValidationIssue]:
    """Validate lintels (Phase 7.3) - placeholder."""
    # TODO: Implement lintels validation
    return []


def _validate_detail_graph(
    extraction: ExtractionResult, analysis: DocumentAnalysis
) -> list[ValidationIssue]:
    """
    Validate detail graph (Phase 7.4).
    
    Hard gates:
    - Error if details referenced in notes but no DetailNode exists
    - Error if parapet exists but no parapet detail linked
    - Error if window/lintel exists but no window/lintel detail linked
    """
    issues: list[ValidationIssue] = []

    # If no detail graph, that's okay (optional)
    if not extraction.detail_graph or not extraction.detail_graph.details:
        return issues

    detail_graph = extraction.detail_graph
    detail_ids = {detail.detail_id for detail in detail_graph.details}

    # Check if details are referenced in notes but don't exist
    # Look for detail references in structural notes, scope, etc.
    if extraction.structural_notes:
        # Check for detail references in notes
        notes_text = ""
        if extraction.structural_notes.general_notes:
            notes_text = " ".join(extraction.structural_notes.general_notes).lower()
        
        # Look for detail callouts (e.g., "See Detail 4", "Detail S-011-D4")
        import re
        detail_patterns = [
            r"detail\s+([a-z0-9\-]+)",
            r"d([0-9]+)",
            r"s-([0-9]+)-d([0-9]+)",
        ]
        
        for pattern in detail_patterns:
            matches = re.findall(pattern, notes_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    detail_ref = "-".join(match).upper()
                else:
                    detail_ref = match.upper()
                
                # Check if this detail exists
                found = False
                for detail in detail_graph.details:
                    if detail_ref in detail.detail_id.upper() or detail_ref in detail.detail_label.upper():
                        found = True
                        break
                
                if not found:
                    issues.append(
                        ValidationIssue(
                            code="DETAIL_REFERENCED_BUT_MISSING",
                            severity="error",
                            message=f"Detail '{detail_ref}' referenced in notes but no DetailNode exists",
                            affected_fields=["detail_graph.details", "structural_notes"],
                            recommended_action=f"Re-read detail sheets to extract detail '{detail_ref}'",
                        )
                    )

    # Check if parapet exists but no parapet detail linked
    if extraction.institutional_geometry_for_3d:
        inst_geometry = extraction.institutional_geometry_for_3d
        parapet_zones = [
            z for z in inst_geometry.envelope_layers
            if z.layer_type == "parapet"
        ]
        
        if parapet_zones:
            parapet_details = [
                d for d in detail_graph.details
                if d.detail_type == "parapet"
            ]
            
            if not parapet_details:
                issues.append(
                    ValidationIssue(
                        code="PARAPET_EXISTS_BUT_NO_DETAIL",
                        severity="error",
                        message="Parapet exists in geometry but no parapet detail is linked",
                        affected_fields=["detail_graph.details", "institutional_geometry_for_3d.envelope_layers"],
                        recommended_action="Re-read detail sheets to extract parapet detail",
                    )
                )

    # Check if window/lintel exists but no window/lintel detail linked
    if extraction.openings and extraction.openings.openings:
        window_details = [
            d for d in detail_graph.details
            if d.detail_type in ["window", "lintel"]
        ]
        
        if not window_details:
            issues.append(
                ValidationIssue(
                    code="OPENINGS_EXIST_BUT_NO_DETAIL",
                    severity="error",
                    message="Openings exist but no window/lintel detail is linked",
                    affected_fields=["detail_graph.details", "openings"],
                    recommended_action="Re-read detail sheets to extract window/lintel details",
                )
            )
    
    if extraction.lintels and extraction.lintels.lintels:
        lintel_details = [
            d for d in detail_graph.details
            if d.detail_type == "lintel"
        ]
        
        if not lintel_details:
            issues.append(
                ValidationIssue(
                    code="LINTELS_EXIST_BUT_NO_DETAIL",
                    severity="error",
                    message="Lintels exist but no lintel detail is linked",
                    affected_fields=["detail_graph.details", "lintels"],
                    recommended_action="Re-read detail sheets to extract lintel details",
                )
            )

    return issues

