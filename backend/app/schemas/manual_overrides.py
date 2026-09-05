"""Schema for manual pipeline overrides used during testing."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ManualOverrides(BaseModel):
    """Manual override inputs supplied by users for testing."""

    roof_area_sf: float | None = Field(
        default=None,
        ge=0,
        description="Manual override for roof area in square feet",
    )
    membrane_type: str | None = Field(
        default=None,
        description="Manual override for roof membrane/system type",
    )
    insulation_thickness_in: float | None = Field(
        default=None,
        ge=0,
        description="Manual override for roof insulation thickness in inches",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when overrides were last updated",
    )

    def sanitized(self) -> dict[str, float | str]:
        """Return override values excluding unset fields and metadata."""

        return {
            key: value
            for key, value in self.model_dump(exclude={"updated_at"}).items()
            if value is not None
        }


class ManualOverridesUpdate(BaseModel):
    """Partial update payload for manual overrides."""

    roof_area_sf: float | None = Field(default=None, ge=0)
    membrane_type: str | None = Field(default=None)
    insulation_thickness_in: float | None = Field(default=None, ge=0)
