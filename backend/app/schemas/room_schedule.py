"""Room schedule schema for institutional/commercial projects (Phase 7.1)."""

from pydantic import BaseModel, Field, field_validator


class EvidenceRef(BaseModel):
    """Evidence reference for a room schedule item."""

    page_number: int = Field(description="1-indexed page number where room is listed")
    sheet_id: str | None = Field(
        default=None, description="Sheet ID if visible (e.g., 'A-3', 'S-1')"
    )
    snippet: str = Field(description="Exact text snippet or callout showing this room")


class RoomScheduleItem(BaseModel):
    """Individual room entry from room schedule (Phase 7.1)."""

    room_id: str | None = Field(
        default=None, description="Room number/identifier (e.g., '101', 'A-101', 'Gym')"
    )
    room_name: str = Field(description="Room name (e.g., 'Gymnasium', 'Locker Room', 'Office')")
    area_sf: float = Field(description="Room area in square feet", gt=0.0)
    level: str | None = Field(
        default=None, description="Floor level (e.g., 'Ground', 'First', 'Basement', '1', '2')"
    )
    usage_type: str | None = Field(
        default=None,
        description="Usage type hint (e.g., 'gym', 'office', 'toilet', 'storage', 'corridor')",
    )
    finishes_hint: str | None = Field(
        default=None,
        description="Optional hint about finishes (e.g., 'VCT flooring', 'painted walls')",
    )
    evidence: EvidenceRef = Field(description="Evidence reference for this room")

    @field_validator("room_name")
    @classmethod
    def validate_room_name(cls, v: str) -> str:
        """Ensure room name is non-empty."""
        if not v or not v.strip():
            raise ValueError("room_name must be non-empty")
        return v.strip()


class RoomSchedule(BaseModel):
    """Complete room schedule for a project (Phase 7.1)."""

    rooms: list[RoomScheduleItem] = Field(
        default_factory=list, description="List of all rooms extracted from schedule"
    )
    total_gsf: float | None = Field(
        default=None, description="Total gross square feet if stated in schedule"
    )
    total_gsf_evidence: EvidenceRef | None = Field(
        default=None, description="Evidence for total GSF"
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="List of missing expected fields (e.g., 'rooms', 'total_gsf')",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.0,
        description="Confidence in room schedule completeness (0.0 to 1.0)",
    )






