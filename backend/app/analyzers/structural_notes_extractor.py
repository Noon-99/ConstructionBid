"""Structural notes extractor for Stage 2.

Extracts structural core specifications (concrete, rebar, CMU, steel, loads, etc.)
from structural notes pages for institutional projects.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.core.config import Settings
from app.models.pdf_page_image import PdfPageImage
from app.schemas.document_analysis import DocumentAnalysis
from app.schemas.page_index import PageIndex
from app.schemas.structural_notes import (
    CMUSpec,
    CodeReference,
    ConcreteSpec,
    DesignLoads,
    FoundationRequirements,
    InspectionRequirement,
    InstitutionalStructuralNotesResult,
    LightGaugeSpec,
    RebarSpec,
    SteelSpec,
    StructuralNotes,
    SubmittalRequirement,
)
from app.services.openai_client import OpenAIClient, OpenAINonRetryableError


class StructuralNotesExtractor:
    """Extracts structural notes and specifications from construction documents."""

    def __init__(self, settings: Settings, openai_client: OpenAIClient) -> None:
        """Initialize structural notes extractor."""
        self.settings = settings
        self.openai_client = openai_client

    def extract_structural_notes(
        self,
        pdf_images: list[PdfPageImage],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        project_id: str,
    ) -> InstitutionalStructuralNotesResult:
        """
        Extract structural notes from institutional document.

        Args:
            pdf_images: All PDF page images
            analysis: DocumentAnalysis from Stage 1
            page_index: PageIndex from Stage 0.5
            project_id: Project ID for logging

        Returns:
            StructuralNotes with all structural specifications
        """
        log_ctx = logger.bind(project_id=project_id, stage="structural_notes_extraction")

        log_ctx.info("Starting structural notes extraction (Phase 4.2)")

        # Select pages with structural notes indicators (enhanced selection)
        selected_pages = self._select_structural_notes_pages(analysis, page_index, pdf_images)

        if not selected_pages:
            log_ctx.warning("No pages selected for structural notes extraction")
            return InstitutionalStructuralNotesResult(
                missing_fields=["concrete_specs", "rebar_specs", "steel_specs", "cmu_specs"],
                confidence=0.0,
            )

        log_ctx.info(f"Extracting structural notes from {len(selected_pages)} pages: {[p.page_number for p in selected_pages]}")

        # Extract from selected pages
        all_concrete: list[ConcreteSpec] = []
        all_rebar: list[RebarSpec] = []
        all_cmu: list[CMUSpec] = []
        all_steel: list[SteelSpec] = []
        all_light_gauge: list[LightGaugeSpec] = []
        all_loads_dicts: list[dict] = []  # Aggregate load dicts to merge into single DesignLoads
        all_foundation_dicts: list[dict] = []  # Aggregate foundation dicts to merge into single FoundationRequirements
        all_submittals: list[SubmittalRequirement] = []
        all_inspections: list[InspectionRequirement] = []
        all_codes: list[CodeReference] = []

        for page_image in selected_pages:
            try:
                page_result = self._extract_structural_notes_from_page(page_image, project_id)
                
                # Aggregate results
                all_concrete.extend(page_result.get("concrete_specs", []))
                all_rebar.extend(page_result.get("rebar_specs", []))
                all_cmu.extend(page_result.get("cmu_specs", []))
                all_steel.extend(page_result.get("steel_specs", []))
                all_light_gauge.extend(page_result.get("light_gauge_specs", []))
                all_loads_dicts.extend(page_result.get("design_loads", []))  # Changed from load_specs
                all_foundation_dicts.extend(page_result.get("foundation_requirements", []))  # Changed from foundation_specs
                all_submittals.extend(page_result.get("submittals", []))
                all_inspections.extend(page_result.get("inspections", []))
                all_codes.extend(page_result.get("code_references", []))
            except Exception as e:
                log_ctx.error(f"Failed to extract from page {page_image.page_number}: {e}")
                continue

        # Aggregate loads into single DesignLoads object
        design_loads = self._aggregate_design_loads(all_loads_dicts, selected_pages[0] if selected_pages else None)
        
        # Aggregate foundation into single FoundationRequirements object
        foundation_requirements = self._aggregate_foundation_requirements(
            all_foundation_dicts, selected_pages[0] if selected_pages else None
        )

        # Validate and potentially trigger recovery
        validation_result = self._validate_structural_notes(
            all_concrete, all_rebar, all_cmu, all_steel, design_loads,
            all_submittals, all_inspections, all_codes, analysis, page_index,
            pdf_images, project_id
        )

        # Build missing_fields list
        missing_fields: list[str] = []
        if not all_concrete and not all_rebar and not all_cmu and not all_steel:
            missing_fields.append("major_specs")
        contractor_readiness_count = sum([
            1 if design_loads else 0,
            1 if all_submittals else 0,
            1 if all_inspections else 0,
            1 if all_codes else 0,
        ])
        if contractor_readiness_count < 2:
            missing_fields.append("contractor_readiness")

        structural_notes = InstitutionalStructuralNotesResult(
            concrete_specs=all_concrete,
            rebar_specs=all_rebar,
            cmu_specs=all_cmu,
            steel_specs=all_steel,
            light_gauge_specs=all_light_gauge,
            design_loads=design_loads,
            foundation_requirements=foundation_requirements,
            submittals=all_submittals,
            inspections=all_inspections,
            code_compliance=all_codes,
            missing_fields=missing_fields,
            confidence=validation_result["confidence"],
        )

        log_ctx.info(
            f"Structural notes extraction complete: "
            f"concrete={len(all_concrete)}, rebar={len(all_rebar)}, cmu={len(all_cmu)}, "
            f"steel={len(all_steel)}, loads={'yes' if design_loads else 'no'}, "
            f"confidence={validation_result['confidence']:.2f}"
        )

        return structural_notes

    def _select_structural_notes_pages(
        self,
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
    ) -> list[PdfPageImage]:
        """
        Select pages containing structural notes.

        Uses page_index indicators and Stage 1 locators.
        """
        selected: set[int] = set()

        # Use page_index if available
        if page_index and hasattr(page_index, "pages"):
            for page_item in page_index.pages:
                if any(
                    ind in page_item.indicators
                    for ind in ["loads", "concrete", "steel", "cmu"]
                ) or any(
                    pt in page_item.page_types
                    for pt in ["notes", "compliance", "schedule"]
                ):
                    selected.add(page_item.page_number - 1)  # Convert to 0-indexed

        # Use Stage 1 locators for materials
        for locator in analysis.where_materials_live:
            if locator.location_type in ["specification_section", "notes", "structural_notes"]:
                if locator.page_number > 0:
                    selected.add(locator.page_number - 1)

        # Filter to available pages
        selected_pages = [
            pdf_images[i] for i in sorted(selected) if 0 <= i < len(pdf_images)
        ]

        return selected_pages

    def _extract_structural_notes_from_page(
        self, page_image: PdfPageImage, project_id: str
    ) -> dict:
        """
        Extract structural notes from a single page using OpenAI Vision.

        Returns:
            Dict with all structural spec types
        """
        prompt = self._create_structural_notes_prompt()

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{page_image.mime_type};base64,{page_image.image_base64}",
                            "detail": "high",  # High detail for structural notes extraction
                        },
                    },
                ],
            }
        ]

        log_ctx = logger.bind(
            project_id=project_id, stage="structural_notes_extraction", page=page_image.page_number
        )

        try:
            response_text = self.openai_client.call_vision(
                messages=messages,
                request_id=f"{project_id}-structural-page-{page_image.page_number}",
                stage_name="structural_notes_extraction",
                project_id=project_id,
            )

            # Parse JSON (handle markdown code blocks)
            content = response_text.strip()
            if content.startswith("```json"):
                content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
            elif content.startswith("```"):
                content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]

            parsed = json.loads(content)

            # Convert dicts to Pydantic models (validate)
            result: dict = {
                "concrete_specs": [],
                "rebar_specs": [],
                "cmu_specs": [],
                "steel_specs": [],
                "light_gauge_specs": [],
                "design_loads": [],  # Changed: list of dicts to aggregate
                "foundation_requirements": [],  # Changed: list of dicts to aggregate
                "submittals": [],
                "inspections": [],
                "code_references": [],
            }

            # Validate and convert each spec type
            for spec_dict in parsed.get("concrete_specs", []):
                try:
                    spec_dict["page_number"] = page_image.page_number
                    result["concrete_specs"].append(ConcreteSpec.model_validate(spec_dict))
                except ValidationError as e:
                    log_ctx.warning(f"Invalid concrete spec: {e}")
                    continue

            for spec_dict in parsed.get("rebar_specs", []):
                try:
                    spec_dict["page_number"] = page_image.page_number
                    result["rebar_specs"].append(RebarSpec.model_validate(spec_dict))
                except ValidationError as e:
                    log_ctx.warning(f"Invalid rebar spec: {e}")
                    continue

            for spec_dict in parsed.get("cmu_specs", []):
                try:
                    spec_dict["page_number"] = page_image.page_number
                    result["cmu_specs"].append(CMUSpec.model_validate(spec_dict))
                except ValidationError as e:
                    log_ctx.warning(f"Invalid CMU spec: {e}")
                    continue

            for spec_dict in parsed.get("steel_specs", []):
                try:
                    spec_dict["page_number"] = page_image.page_number
                    result["steel_specs"].append(SteelSpec.model_validate(spec_dict))
                except ValidationError as e:
                    log_ctx.warning(f"Invalid steel spec: {e}")
                    continue

            for spec_dict in parsed.get("light_gauge_specs", []):
                try:
                    spec_dict["page_number"] = page_image.page_number
                    result["light_gauge_specs"].append(LightGaugeSpec.model_validate(spec_dict))
                except ValidationError as e:
                    log_ctx.warning(f"Invalid light gauge spec: {e}")
                    continue

            # Parse design_loads (new structure) - can be single object or list
            design_loads_data = parsed.get("design_loads")
            if design_loads_data:
                if isinstance(design_loads_data, list):
                    for load_dict in design_loads_data:
                        load_dict["page_number"] = page_image.page_number
                        result["design_loads"].append(load_dict)
                else:
                    # Single object
                    design_loads_data["page_number"] = page_image.page_number
                    result["design_loads"].append(design_loads_data)
            
            # Backward compatibility: also parse load_specs if present
            for spec_dict in parsed.get("load_specs", []):
                try:
                    # Convert old LoadSpec format to new DesignLoads format
                    load_dict: dict = {"page_number": page_image.page_number}
                    if spec_dict.get("load_type") == "roof" and spec_dict.get("value"):
                        # Try to extract psf value
                        value_str = spec_dict["value"]
                        if "psf" in value_str.lower():
                            try:
                                load_dict["roof_live_psf"] = float(value_str.split()[0])
                            except (ValueError, IndexError):
                                pass
                    # Add other fields as needed
                    if spec_dict.get("evidence_snippet"):
                        load_dict["evidence_snippet"] = spec_dict["evidence_snippet"]
                    if spec_dict.get("sheet_id"):
                        load_dict["sheet_id"] = spec_dict["sheet_id"]
                    if spec_dict.get("code_reference"):
                        load_dict["code_reference"] = spec_dict["code_reference"]
                    result["design_loads"].append(load_dict)
                except Exception as e:
                    log_ctx.warning(f"Invalid load spec (legacy): {e}")
                    continue

            # Parse foundation_requirements (new structure)
            foundation_data = parsed.get("foundation_requirements")
            if foundation_data:
                if isinstance(foundation_data, list):
                    for found_dict in foundation_data:
                        found_dict["page_number"] = page_image.page_number
                        result["foundation_requirements"].append(found_dict)
                else:
                    # Single object
                    foundation_data["page_number"] = page_image.page_number
                    result["foundation_requirements"].append(foundation_data)
            
            # Backward compatibility: also parse foundation_specs if present
            for spec_dict in parsed.get("foundation_specs", []):
                try:
                    # Convert old FoundationSpec format to new FoundationRequirements format
                    found_dict: dict = {"page_number": page_image.page_number}
                    if spec_dict.get("bearing_capacity"):
                        # Try to extract psf value
                        bearing_str = spec_dict["bearing_capacity"]
                        if "psf" in bearing_str.lower():
                            try:
                                found_dict["soil_bearing_psf"] = float(bearing_str.split()[0])
                            except (ValueError, IndexError):
                                pass
                    if spec_dict.get("compaction"):
                        # Try to extract percentage
                        comp_str = spec_dict["compaction"]
                        if "%" in comp_str:
                            try:
                                found_dict["compaction_percent"] = float(comp_str.replace("%", "").split()[0])
                            except (ValueError, IndexError):
                                pass
                    if spec_dict.get("cover"):
                        found_dict["concrete_cover"] = spec_dict["cover"]
                    if spec_dict.get("evidence_snippet"):
                        found_dict["evidence_snippet"] = spec_dict["evidence_snippet"]
                    if spec_dict.get("sheet_id"):
                        found_dict["sheet_id"] = spec_dict["sheet_id"]
                    result["foundation_requirements"].append(found_dict)
                except Exception as e:
                    log_ctx.warning(f"Invalid foundation spec (legacy): {e}")
                    continue

            for spec_dict in parsed.get("submittals", []):
                try:
                    spec_dict["page_number"] = page_image.page_number
                    result["submittals"].append(SubmittalRequirement.model_validate(spec_dict))
                except ValidationError as e:
                    log_ctx.warning(f"Invalid submittal: {e}")
                    continue

            for spec_dict in parsed.get("inspections", []):
                try:
                    spec_dict["page_number"] = page_image.page_number
                    result["inspections"].append(InspectionRequirement.model_validate(spec_dict))
                except ValidationError as e:
                    log_ctx.warning(f"Invalid inspection: {e}")
                    continue

            for spec_dict in parsed.get("code_references", []):
                try:
                    spec_dict["page_number"] = page_image.page_number
                    result["code_references"].append(CodeReference.model_validate(spec_dict))
                except ValidationError as e:
                    log_ctx.warning(f"Invalid code reference: {e}")
                    continue

            return result

        except Exception as e:
            log_ctx.error(f"Failed to extract structural notes from page {page_image.page_number}: {e}")
            raise

    def _create_structural_notes_prompt(self) -> str:
        """Create prompt for structural notes extraction."""
        return """You are extracting structural notes and specifications from a construction document.

Extract ALL structural specifications visible on this page, including:

1. CONCRETE SPECS:
   - Strength in PSI (e.g., 3000, 4000)
   - Application (footings, slabs, walls)
   - Mix design references

2. REBAR SPECS:
   - Grade (e.g., Grade 60, ASTM A615)
   - Size (e.g., #4, #5, #6)
   - Application

3. CMU SPECS:
   - Strength in PSI
   - Mortar type (Type N, Type M)
   - ASTM references
   - Grout specifications

4. STEEL SPECS:
   - Grade (A992, A500, A36, A53)
   - Shape (W12x26, HSS6x6x1/4)
   - Galvanized (yes/no if specified)
   - Application

5. LIGHT GAUGE FRAMING:
   - Thickness in mils (18, 20, 25)
   - Yield strength in KSI (33, 50)
   - Deflection limits (L/360, etc.)

6. LOADS:
   - Roof loads (psf)
   - Wind loads (mph or psf)
   - Seismic (category or value)
   - Live/dead loads
   - Code references (ASCE 7, etc.)

7. FOUNDATION:
   - Bearing capacity (psf)
   - Compaction requirements
   - Cover requirements

8. SUBMITTALS:
   - Items requiring submittal (mix designs, shop drawings, etc.)

9. INSPECTIONS:
   - Items requiring inspection (concrete placement, rebar, etc.)

10. CODE REFERENCES:
    - Code names (IBC, ACI, ASCE, etc.)
    - Section references

Return ONLY valid JSON matching this schema:

{
  "concrete_specs": [
    {
      "strength_psi": 4000.0,
      "application": "footings",
      "mix_design": null,
      "sheet_id": "S-1",
      "evidence_snippet": "Concrete: 4000 PSI for footings"
    }
  ],
  "rebar_specs": [
    {
      "grade": "Grade 60",
      "size": "#5",
      "application": "footings",
      "sheet_id": "S-1",
      "evidence_snippet": "Rebar: Grade 60, #5 bars"
    }
  ],
  "cmu_specs": [],
  "steel_specs": [],
  "light_gauge_specs": [],
  "load_specs": [
    {
      "load_type": "roof",
      "value": "50 psf",
      "code_reference": "ASCE 7-16",
      "sheet_id": "S-1",
      "evidence_snippet": "Roof live load: 50 psf per ASCE 7-16"
    }
  ],
  "foundation_specs": [],
  "submittals": [],
  "inspections": [],
  "code_references": []
}

Return ONLY the JSON object. No markdown, no code blocks, no explanation."""

    def _aggregate_design_loads(
        self, loads_dicts: list[dict], reference_page: Any | None
    ) -> DesignLoads | None:
        """Aggregate multiple load dicts into single DesignLoads object."""
        if not loads_dicts:
            return None
        
        # Merge all load values (take first non-null value for each field)
        aggregated: dict[str, Any] = {
            "page_number": reference_page.page_number if reference_page else 0,
            "sheet_id": None,
            "evidence_snippet": "",
        }
        
        evidence_parts: list[str] = []
        
        for load_dict in loads_dicts:
            for key in ["roof_live_psf", "roof_dead_psf", "collateral_psf", "wind_speed_ult_mph",
                       "wind_exposure", "seismic_category", "snow_psf"]:
                if key in load_dict and load_dict[key] is not None and key not in aggregated:
                    aggregated[key] = load_dict[key]
            
            if "importance_factors" in load_dict and load_dict["importance_factors"]:
                if "importance_factors" not in aggregated:
                    aggregated["importance_factors"] = load_dict["importance_factors"]
                else:
                    # Merge importance factors
                    existing = aggregated["importance_factors"] or {}
                    new = load_dict["importance_factors"] or {}
                    aggregated["importance_factors"] = {**existing, **new}
            
            if load_dict.get("evidence_snippet"):
                evidence_parts.append(load_dict["evidence_snippet"])
            
            if load_dict.get("sheet_id") and not aggregated["sheet_id"]:
                aggregated["sheet_id"] = load_dict["sheet_id"]
        
        aggregated["evidence_snippet"] = " | ".join(evidence_parts[:3])  # Limit to first 3
        
        try:
            return DesignLoads.model_validate(aggregated)
        except ValidationError:
            return None

    def _aggregate_foundation_requirements(
        self, foundation_dicts: list[dict], reference_page: Any | None
    ) -> FoundationRequirements | None:
        """Aggregate multiple foundation dicts into single FoundationRequirements object."""
        if not foundation_dicts:
            return None
        
        # Merge all foundation values (take first non-null value for each field)
        aggregated: dict[str, Any] = {
            "page_number": reference_page.page_number if reference_page else 0,
            "sheet_id": None,
            "evidence_snippet": "",
        }
        
        evidence_parts: list[str] = []
        
        for found_dict in foundation_dicts:
            for key in ["soil_bearing_psf", "compaction_percent", "concrete_cover"]:
                if key in found_dict and found_dict[key] is not None and key not in aggregated:
                    aggregated[key] = found_dict[key]
            
            if found_dict.get("evidence_snippet"):
                evidence_parts.append(found_dict["evidence_snippet"])
            
            if found_dict.get("sheet_id") and not aggregated["sheet_id"]:
                aggregated["sheet_id"] = found_dict["sheet_id"]
        
        aggregated["evidence_snippet"] = " | ".join(evidence_parts[:3])  # Limit to first 3
        
        try:
            return FoundationRequirements.model_validate(aggregated)
        except ValidationError:
            return None

    def _validate_structural_notes(
        self,
        concrete_specs: list[ConcreteSpec],
        rebar_specs: list[RebarSpec],
        cmu_specs: list[CMUSpec],
        steel_specs: list[SteelSpec],
        design_loads: DesignLoads | None,
        submittals: list[SubmittalRequirement],
        inspections: list[InspectionRequirement],
        code_references: list[CodeReference],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
        project_id: str,
    ) -> dict[str, Any]:
        """
        Validate structural notes and trigger recovery if needed (Phase 4.2).

        Validation gates:
        - Must have at least one: concrete strength spec OR steel spec OR CMU spec
        - Must have at least 2 of: loads, submittals, inspections, code compliance

        Returns:
            Dict with validation results
        """
        log_ctx = logger.bind(project_id=project_id, stage="structural_notes_validation")
        
        validation_passed = True
        issues: list[str] = []
        confidence = 1.0

        # Gate 1: Must have at least one major spec type
        has_major_spec = (
            any(c.strength_psi for c in concrete_specs if c.strength_psi) or
            any(s.w_shapes or s.hss for s in steel_specs) or
            any(c.unit_strength_psi for c in cmu_specs if c.unit_strength_psi)
        )
        
        if not has_major_spec:
            validation_passed = False
            issues.append("Missing major spec: must have at least one concrete strength OR steel spec OR CMU spec")
            confidence = 0.3

        # Gate 2: Contractor readiness - must have at least 2 of: loads, submittals, inspections, codes
        contractor_readiness_items = [
            design_loads is not None,
            len(submittals) > 0,
            len(inspections) > 0,
            len(code_references) > 0,
        ]
        contractor_readiness_count = sum(contractor_readiness_items)
        
        if contractor_readiness_count < 2:
            validation_passed = False
            issues.append(
                f"Contractor readiness incomplete: found {contractor_readiness_count}/4 required items "
                "(need 2 of: loads, submittals, inspections, code compliance)"
            )
            confidence = max(0.3, confidence * (contractor_readiness_count / 2))

        # Trigger recovery if validation failed
        if not validation_passed:
            log_ctx.warning(f"Structural notes validation failed: {', '.join(issues)}")
            log_ctx.info("Triggering targeted recovery re-read")
            
            recovery_result = self._recover_structural_notes(
                concrete_specs, rebar_specs, cmu_specs, steel_specs,
                design_loads, submittals, inspections, code_references,
                analysis, page_index, pdf_images, project_id
            )
            
            # Merge recovery results (additive, prefer higher confidence)
            if recovery_result:
                concrete_specs.extend(recovery_result.get("concrete_specs", []))
                rebar_specs.extend(recovery_result.get("rebar_specs", []))
                cmu_specs.extend(recovery_result.get("cmu_specs", []))
                steel_specs.extend(recovery_result.get("steel_specs", []))
                
                # Update design_loads if recovery found one
                if recovery_result.get("design_loads"):
                    recovery_loads_dicts = recovery_result.get("design_loads", [])
                    recovered_loads = self._aggregate_design_loads(recovery_loads_dicts, None)
                    if recovered_loads and not design_loads:
                        design_loads = recovered_loads
                
                # Add to lists
                submittals.extend(recovery_result.get("submittals", []))
                inspections.extend(recovery_result.get("inspections", []))
                code_references.extend(recovery_result.get("code_references", []))
                
                # Re-validate
                has_major_spec_after = (
                    any(c.strength_psi for c in concrete_specs if c.strength_psi) or
                    any(s.w_shapes or s.hss for s in steel_specs) or
                    any(c.unit_strength_psi for c in cmu_specs if c.unit_strength_psi)
                )
                contractor_readiness_after = sum([
                    design_loads is not None,
                    len(submittals) > 0,
                    len(inspections) > 0,
                    len(code_references) > 0,
                ])
                
                if has_major_spec_after and contractor_readiness_after >= 2:
                    validation_passed = True
                    issues = []
                    confidence = min(1.0, confidence + 0.2)
                    log_ctx.info("Recovery successful - validation now passes")
        
        return {
            "validation_passed": validation_passed,
            "issues": issues,
            "confidence": confidence,
        }

    def _recover_structural_notes(
        self,
        existing_concrete: list[ConcreteSpec],
        existing_rebar: list[RebarSpec],
        existing_cmu: list[CMUSpec],
        existing_steel: list[SteelSpec],
        existing_loads: DesignLoads | None,
        existing_submittals: list[SubmittalRequirement],
        existing_inspections: list[InspectionRequirement],
        existing_codes: list[CodeReference],
        analysis: DocumentAnalysis,
        page_index: PageIndex | None,
        pdf_images: list[PdfPageImage],
        project_id: str,
    ) -> dict[str, Any] | None:
        """
        Perform targeted recovery re-read for missing structural notes (Phase 4.2).

        Re-reads up to 4 pages with strongest notes/structural_notes/loads indicators.
        """
        log_ctx = logger.bind(project_id=project_id, stage="structural_notes_recovery")
        
        # Select recovery pages (up to 4)
        recovery_pages: list[PdfPageImage] = []
        already_read_pages = set()  # Could track pages already read
        
        if page_index and hasattr(page_index, "pages"):
            # Score pages by structural notes indicators
            scored_pages: list[tuple[int, float]] = []
            
            for page_item in page_index.pages:
                page_num = page_item.page_number
                if page_num in already_read_pages:
                    continue
                
                score = 0.0
                # Boost for strong indicators
                if "structural_notes" in page_item.indicators:
                    score += 10.0
                if "loads" in page_item.indicators:
                    score += 8.0
                if "notes" in page_item.page_types:
                    score += 8.0
                if "compliance" in page_item.page_types:
                    score += 5.0
                if "detail" in page_item.page_types:
                    score += 5.0
                if "index" in page_item.page_types:
                    score += 3.0
                
                score *= page_item.confidence
                
                page_idx = page_num - 1
                if 0 <= page_idx < len(pdf_images):
                    scored_pages.append((page_idx, score))
            
            # Sort by score and take top 4
            scored_pages.sort(key=lambda x: x[1], reverse=True)
            recovery_indices = [idx for idx, _ in scored_pages[:4]]
            
            recovery_pages = [
                pdf_images[i] for i in recovery_indices if 0 <= i < len(pdf_images)
            ]
        
        if not recovery_pages:
            log_ctx.warning("No additional pages available for recovery")
            return None
        
        log_ctx.info(f"Recovery: re-reading {len(recovery_pages)} pages: {[p.page_number for p in recovery_pages]}")
        
        # Extract from recovery pages
        recovery_result: dict[str, Any] = {
            "concrete_specs": [],
            "rebar_specs": [],
            "cmu_specs": [],
            "steel_specs": [],
            "design_loads": [],
            "submittals": [],
            "inspections": [],
            "code_references": [],
        }
        
        for page_image in recovery_pages:
            try:
                page_result = self._extract_structural_notes_from_page(page_image, project_id)
                recovery_result["concrete_specs"].extend(page_result.get("concrete_specs", []))
                recovery_result["rebar_specs"].extend(page_result.get("rebar_specs", []))
                recovery_result["cmu_specs"].extend(page_result.get("cmu_specs", []))
                recovery_result["steel_specs"].extend(page_result.get("steel_specs", []))
                recovery_result["design_loads"].extend(page_result.get("design_loads", []))
                recovery_result["submittals"].extend(page_result.get("submittals", []))
                recovery_result["inspections"].extend(page_result.get("inspections", []))
                recovery_result["code_references"].extend(page_result.get("code_references", []))
            except Exception as e:
                log_ctx.error(f"Failed recovery extraction from page {page_image.page_number}: {e}")
                continue
        
        return recovery_result

