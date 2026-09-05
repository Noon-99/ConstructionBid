"""Schema for structural notes and specifications."""

from typing import Literal

from pydantic import BaseModel, Field


class ConcreteSpec(BaseModel):
    """Concrete specification (Phase 4.2)."""

    strength_psi: float | None = Field(
        default=None, description="Concrete strength in PSI (e.g., 3000, 4000)"
    )
    slump_in: float | None = Field(
        default=None, description="Slump in inches if specified"
    )
    fiber: str | None = Field(
        default=None, description="Fiber reinforcement if specified"
    )
    notes: str | None = Field(
        default=None, description="Additional notes"
    )
    page_number: int = Field(description="Page where spec was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing this spec")


class RebarSpec(BaseModel):
    """Rebar/reinforcing steel specification (Phase 4.2)."""

    astm: str | None = Field(
        default=None, description="ASTM specification (e.g., 'ASTM A615', 'ASTM A706')"
    )
    grade: str | None = Field(
        default=None, description="Rebar grade (e.g., 'Grade 60', 'Grade 75')"
    )
    welded_wire_fabric: str | None = Field(
        default=None, description="Welded wire fabric spec if applicable"
    )
    supports_standard: str | None = Field(
        default=None, description="Supports standard if specified"
    )
    page_number: int = Field(description="Page where spec was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing this spec")


class CMUSpec(BaseModel):
    """CMU (Concrete Masonry Unit) specification (Phase 4.2)."""

    astm: str | None = Field(
        default=None, description="ASTM specification if specified"
    )
    unit_strength_psi: float | None = Field(
        default=None, description="CMU unit strength in PSI (e.g., 2000, 3000)"
    )
    installed_fm_psi: float | None = Field(
        default=None, description="Installed f'm in PSI if specified"
    )
    mortar_type: str | None = Field(
        default=None, description="Mortar type (e.g., 'Type N', 'Type M')"
    )
    grout_spec: str | None = Field(
        default=None, description="Grout specification if specified"
    )
    page_number: int = Field(description="Page where spec was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing this spec")


class SteelSpec(BaseModel):
    """Structural steel specification (Phase 4.2)."""

    w_shapes: str | None = Field(
        default=None, description="W-shapes specification (e.g., 'W12x26', 'A992')"
    )
    hss: str | None = Field(
        default=None, description="HSS specification (e.g., 'HSS6x6x1/4', 'A500')"
    )
    plates_angles: str | None = Field(
        default=None, description="Plates and angles specification"
    )
    pipes: str | None = Field(
        default=None, description="Pipe specification if applicable"
    )
    welding_electrodes: str | None = Field(
        default=None, description="Welding electrodes if specified"
    )
    galvanizing: str | None = Field(
        default=None, description="Galvanizing specification if specified"
    )
    fasteners: str | None = Field(
        default=None, description="Fasteners specification if specified"
    )
    page_number: int = Field(description="Page where spec was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing this spec")


class LightGaugeSpec(BaseModel):
    """Light gauge steel framing specification (Phase 4.2)."""

    thickness_mils: float | None = Field(
        default=None, description="Thickness in mils (e.g., 18, 20, 25)"
    )
    yield_ksi: float | None = Field(
        default=None, description="Yield strength in KSI (e.g., 33, 50)"
    )
    coatings: str | None = Field(
        default=None, description="Coatings specification if specified"
    )
    deflection_limits: str | None = Field(
        default=None, description="Deflection limits if specified (e.g., 'L/360')"
    )
    approved_systems: str | None = Field(
        default=None, description="Approved systems if specified"
    )
    page_number: int = Field(description="Page where spec was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing this spec")


class DesignLoads(BaseModel):
    """Design loads specification (Phase 4.2)."""

    roof_live_psf: float | None = Field(
        default=None, description="Roof live load in psf"
    )
    roof_dead_psf: float | None = Field(
        default=None, description="Roof dead load in psf"
    )
    collateral_psf: float | None = Field(
        default=None, description="Collateral load in psf if specified"
    )
    wind_speed_ult_mph: float | None = Field(
        default=None, description="Wind speed ultimate in mph"
    )
    wind_exposure: str | None = Field(
        default=None, description="Wind exposure category if specified"
    )
    seismic_category: str | None = Field(
        default=None, description="Seismic category if specified"
    )
    importance_factors: dict[str, float] | None = Field(
        default=None, description="Importance factors if specified"
    )
    snow_psf: float | None = Field(
        default=None, description="Snow load in psf if specified"
    )
    page_number: int = Field(description="Page where loads were found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing these loads")


class FoundationRequirements(BaseModel):
    """Foundation requirements specification (Phase 4.2)."""

    soil_bearing_psf: float | None = Field(
        default=None, description="Soil bearing capacity in psf"
    )
    compaction_percent: float | None = Field(
        default=None, description="Compaction requirement as percentage"
    )
    concrete_cover: str | None = Field(
        default=None, description="Concrete cover requirement (e.g., '3 inches', '4 inches')"
    )
    page_number: int = Field(description="Page where requirements were found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing these requirements")


class SubmittalRequirement(BaseModel):
    """Submittal requirement."""

    item: str = Field(description="Item requiring submittal (e.g., 'Mix designs', 'Shop drawings')")
    page_number: int = Field(description="Page where requirement was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing this requirement")


class InspectionRequirement(BaseModel):
    """Inspection requirement."""

    item: str = Field(description="Item requiring inspection (e.g., 'Concrete placement', 'Rebar installation')")
    page_number: int = Field(description="Page where requirement was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing this requirement")


class CodeReference(BaseModel):
    """Code or standard reference."""

    code_name: str = Field(description="Code name (e.g., 'IBC 2018', 'ACI 318', 'ASCE 7-16')")
    section: str | None = Field(
        default=None, description="Section reference if specified"
    )
    page_number: int = Field(description="Page where reference was found")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(description="Exact text snippet showing this reference")


class Submittals(BaseModel):
    """Submittal requirements (Phase 4.2)."""
    
    submittals: list[SubmittalRequirement] = Field(
        default_factory=list, description="List of required submittals"
    )


class Inspections(BaseModel):
    """Inspection requirements (Phase 4.2)."""
    
    inspections: list[InspectionRequirement] = Field(
        default_factory=list, description="List of required inspections/certs"
    )


class CodeCompliance(BaseModel):
    """Code compliance references (Phase 4.2)."""
    
    code_references: list[CodeReference] = Field(
        default_factory=list, description="List of code references (IBC, ACI, AISC, etc.)"
    )


class InstitutionalStructuralNotesResult(BaseModel):
    """Complete institutional structural notes result (Phase 4.2)."""

    concrete_specs: list[ConcreteSpec] = Field(
        default_factory=list, description="Concrete specifications"
    )
    rebar_specs: list[RebarSpec] = Field(
        default_factory=list, description="Rebar specifications"
    )
    cmu_specs: list[CMUSpec] = Field(
        default_factory=list, description="CMU specifications"
    )
    steel_specs: list[SteelSpec] = Field(
        default_factory=list, description="Steel specifications"
    )
    light_gauge_specs: list[LightGaugeSpec] = Field(
        default_factory=list, description="Light gauge framing specifications"
    )
    design_loads: DesignLoads | None = Field(
        default=None, description="Design loads specification"
    )
    foundation_requirements: FoundationRequirements | None = Field(
        default=None, description="Foundation requirements"
    )
    submittals: list[SubmittalRequirement] = Field(
        default_factory=list, description="Submittal requirements"
    )
    inspections: list[InspectionRequirement] = Field(
        default_factory=list, description="Inspection requirements"
    )
    code_compliance: list[CodeReference] = Field(
        default_factory=list, description="Code and standard references"
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="List of missing expected fields",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.0,
        description="Confidence in structural notes completeness (0.0 to 1.0)",
    )


# Legacy alias for backward compatibility
StructuralNotes = InstitutionalStructuralNotesResult

# Legacy aliases for backward compatibility with old extractor code
LightGaugeFramingSpec = LightGaugeSpec
# Keep old LoadSpec and FoundationSpec as placeholders for backward compatibility
# Note: These are used in old code but should migrate to DesignLoads/FoundationRequirements
class LoadSpec(BaseModel):
    """Legacy load specification (deprecated, use DesignLoads)."""
    load_type: str = Field(description="Type of load")
    value: str | None = None
    code_reference: str | None = None
    page_number: int = Field(description="Page where spec was found")
    sheet_id: str | None = None
    evidence_snippet: str = Field(description="Evidence snippet")

class FoundationSpec(BaseModel):
    """Legacy foundation specification (deprecated, use FoundationRequirements)."""
    bearing_capacity: str | None = None
    compaction: str | None = None
    cover: str | None = None
    page_number: int = Field(description="Page where spec was found")
    sheet_id: str | None = None
    evidence_snippet: str = Field(description="Evidence snippet")

