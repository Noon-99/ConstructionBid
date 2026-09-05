"""Schema for institutional room schedule and room program."""

from typing import Literal

from pydantic import BaseModel, Field


class RoomItem(BaseModel):
    """Individual room entry from room schedule (Phase 4.1)."""

    room_number: str | None = Field(
        default=None, description="Room number/identifier (e.g., '101', 'A-101', 'Gym')"
    )
    room_name: str = Field(description="Room name (e.g., 'Gymnasium', 'Locker Room', 'Office')")
    area_sf: float | None = Field(
        default=None, description="Room area in square feet"
    )
    floor: str | None = Field(
        default=None, description="Floor level (e.g., 'Ground', 'First', 'Basement', '1', '2')"
    )
    page_number: int = Field(description="Page where room is listed (required)")
    sheet_id: str | None = Field(
        default=None, description="Sheet ID if visible (e.g., 'A-3', 'S-1')"
    )
    evidence_snippet: str = Field(
        description="Exact text snippet or callout showing this room (required)"
    )


class RoomProgramTotals(BaseModel):
    """Room program totals with evidence (Phase 4.1)."""

    existing_gsf: float | None = Field(
        default=None,
        description="Total existing gross square feet (GSF) if stated",
    )
    addition_gsf: float | None = Field(
        default=None,
        description="Total addition gross square feet (GSF) if stated",
    )
    total_gsf: float | None = Field(
        default=None,
        description="Total gross square feet if stated (alternative to existing+addition)",
    )
    existing_gsf_evidence: str | None = Field(
        default=None,
        description="Evidence snippet for existing_gsf total",
    )
    addition_gsf_evidence: str | None = Field(
        default=None,
        description="Evidence snippet for addition_gsf total",
    )
    total_gsf_evidence: str | None = Field(
        default=None,
        description="Evidence snippet for total_gsf total",
    )


class InstitutionalRoomProgramResult(BaseModel):
    """Complete institutional room program result (Phase 4.1)."""

    rooms: list[RoomItem] = Field(
        default_factory=list, description="List of all rooms extracted"
    )
    totals: RoomProgramTotals = Field(
        default_factory=RoomProgramTotals,
        description="Room program totals with evidence",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="List of missing expected fields (e.g., 'totals.existing_gsf', 'rooms')",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.0,
        description="Confidence in room program completeness (0.0 to 1.0)",
    )


# Legacy alias for backward compatibility
RoomProgram = InstitutionalRoomProgramResult

