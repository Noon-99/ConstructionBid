"""Schema for Stage 2 extraction results."""

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.geometry_for_3d import GeometryFor3D

try:
    from app.schemas.warranty_insurance import WarrantyAndInsurance
except ImportError:
    if TYPE_CHECKING:
        from app.schemas.warranty_insurance import WarrantyAndInsurance
    else:
        WarrantyAndInsurance = Any

# Import for runtime (Pydantic needs these at validation time)
try:
    from app.schemas.institutional_geometry_for_3d import InstitutionalGeometryFor3D
    from app.schemas.institutional_rooms import RoomProgram
    from app.schemas.room_schedule import RoomSchedule
    from app.schemas.structural_notes import StructuralNotes
    from app.schemas.structural_elements import StructuralElementsResult
    from app.schemas.building_envelope import BuildingEnvelopeResult
    from app.services.dimension_authority import AuthoritativeDimensions
except ImportError:
    # Fallback for TYPE_CHECKING if imports fail
    if TYPE_CHECKING:
        from app.schemas.institutional_geometry_for_3d import InstitutionalGeometryFor3D
        from app.schemas.institutional_rooms import RoomProgram
        from app.schemas.room_schedule import RoomSchedule
        from app.schemas.structural_notes import StructuralNotes
        from app.schemas.structural_elements import StructuralElementsResult
        from app.schemas.building_envelope import BuildingEnvelopeResult
        from app.services.dimension_authority import AuthoritativeDimensions
    else:
        InstitutionalGeometryFor3D = Any
        RoomProgram = Any
        RoomSchedule = Any
        StructuralNotes = Any
        StructuralElementsResult = Any
        BuildingEnvelopeResult = Any
        OpeningsResult = Any
        LintelsResult = Any
        DetailGraph = Any
        AuthoritativeDimensions = Any
from app.schemas.institutional_rooms import RoomProgram
try:
    from app.schemas.room_schedule import RoomSchedule
    from app.schemas.structural_elements import StructuralElementsResult
    from app.schemas.building_envelope import BuildingEnvelopeResult
    from app.schemas.openings import OpeningsResult
    from app.schemas.lintels import LintelsResult
    from app.schemas.detail_graph import DetailGraph
except ImportError:
    RoomSchedule = Any
    StructuralElementsResult = Any
    BuildingEnvelopeResult = Any
    OpeningsResult = Any
    LintelsResult = Any


class ExtractedItem(BaseModel):
    """Base class for extracted items with evidence."""

    page_number: int = Field(description="Page number where item was found (1-indexed)")
    sheet_id: str | None = Field(default=None, description="Sheet ID if available")
    evidence_snippet: str = Field(
        description="Short excerpt or callout text that supports this extraction"
    )


class ScopeItem(ExtractedItem):
    """Extracted scope of work item."""

    item: str = Field(description="Scope item name (e.g., 'parapet repair', 'lintel replacement')")
    description: str = Field(description="Detailed description of the work")
    location: str | None = Field(
        default=None, description="Location on building (e.g., 'front facade', 'side wall')"
    )


class MaterialSpecification(ExtractedItem):
    """Extracted material specification."""

    material_name: str = Field(description="Material name (e.g., 'Type N Mortar')")
    specification: str | None = Field(
        default=None, description="Specification reference or product code"
    )
    application: str | None = Field(
        default=None, description="Where/how material is applied"
    )
    detail_sheet: str | None = Field(
        default=None, description="Detail sheet reference if available"
    )


class QuantityTakeoff(ExtractedItem):
    """Extracted quantity with computation evidence."""

    item: str = Field(description="Item name (e.g., 'Brick replacement', 'Repointing')")
    quantity: float | None = Field(
        default=None, description="Quantity value (units depend on item type)"
    )
    unit: str | None = Field(default=None, description="Unit of measurement (e.g., 'sq ft', 'lf')")
    is_computed: bool = Field(
        default=False, description="True if quantity was computed from dimensions"
    )
    computation_formula: str | None = Field(
        default=None, description="Formula if computed (e.g., 'width * height')"
    )
    input_dimensions: dict[str, float] = Field(
        default_factory=dict,
        description="Input dimensions used for computation (e.g., {'width': 40, 'height': 30})",
    )
    evidence_missing: bool = Field(
        default=False,
        description="True if quantity could not be determined and no computation was possible",
    )


class ExtractionResult(BaseModel):
    """Complete Stage 2 extraction result."""

    project_type: Literal["row_house", "institutional", "commercial", "mixed", "single_family", "unknown"] = Field(
        description="Project type"
    )
    scope_type: Literal["repair", "renovation", "new_construction", "addition", "mixed", "unknown"] = Field(
        description="Scope type"
    )
    scope_of_work: list[ScopeItem] = Field(
        default_factory=list, description="Extracted scope items"
    )
    material_specifications: list[MaterialSpecification] = Field(
        default_factory=list, description="Extracted material specifications"
    )
    quantity_takeoff: list[QuantityTakeoff] = Field(
        default_factory=list, description="Extracted quantities"
    )
    geometry_for_3d: GeometryFor3D = Field(description="Geometry information for 3D")
    validation_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about extraction validation (pages used, passes, etc.)",
    )
    evidence_missing: list[str] = Field(
        default_factory=list,
        description="List of missing critical items (e.g., 'parapet_repair', 'lintel_specs')",
    )
    room_program: RoomProgram | None = Field(
        default=None,
        description="Room program for institutional projects (optional, only for institutional typology)",
    )
    structural_notes: StructuralNotes | None = Field(
        default=None,
        description="Structural notes and specifications (optional, only for institutional typology)",
    )
    authoritative_dimensions: "AuthoritativeDimensions | None" = Field(
        default=None,
        description="Authoritative dimensions after resolution (Phase 2.5A)",
    )
    institutional_geometry_for_3d: "InstitutionalGeometryFor3D | None" = Field(
        default=None,
        description="Institutional geometry for 3D model (Phase 4.5, optional, only for institutional typology)",
    )
    room_schedule: RoomSchedule | None = Field(
        default=None,
        description="Room schedule for institutional/commercial projects (Phase 7.1, optional)",
    )
    structural_elements: "StructuralElementsResult | None" = Field(
        default=None,
        description="Structural elements extraction (Phase 7.2, optional)",
    )
    building_envelope: "BuildingEnvelopeResult | None" = Field(
        default=None,
        description="Building envelope elements extraction (Phase 7.2, optional)",
    )
    openings: "OpeningsResult | None" = Field(
        default=None,
        description="Openings extraction (windows/doors) (Phase 7.3, optional)",
    )
    lintels: "LintelsResult | None" = Field(
        default=None,
        description="Lintels and headers extraction (Phase 7.3, optional)",
    )
    detail_graph: "DetailGraph | None" = Field(
        default=None,
        description="Detail graph extraction (Phase 7.4, optional)",
    )
    warranty_and_insurance: "WarrantyAndInsurance | None" = Field(
        default=None,
        description="Warranty and insurance extraction from project documents (Task 8, optional)",
    )

    @field_validator("authoritative_dimensions", mode="before")
    @classmethod
    def _coerce_authoritative_dimensions(cls, value: Any) -> Any:
        if value is None:
            return value

        try:
            from app.services.dimension_authority import (
                AuthoritativeDimensions as _AuthoritativeDimensions,
            )
        except Exception:  # pragma: no cover - defensive guard
            _AuthoritativeDimensions = None

        if _AuthoritativeDimensions and isinstance(value, _AuthoritativeDimensions):
            return value

        if isinstance(value, dict) and _AuthoritativeDimensions:
            try:
                return _AuthoritativeDimensions.model_validate(value)
            except Exception:  # pragma: no cover - defensive guard
                return value

        return value

