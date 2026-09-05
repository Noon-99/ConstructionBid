"""Schema for calibration pack (Phase 10.3).

Calibration pack contains key assumptions and suggested adjustments for contractor review.
"""

from typing import Any

from pydantic import BaseModel, Field


class LineItemCalibration(BaseModel):
    """Calibration data for a line item."""

    line_item_id: str = Field(description="Line item identifier")
    title: str = Field(description="Line item description")
    division: str = Field(description="CSI division")
    quantity: float | None = Field(default=None, description="Quantity")
    unit: str | None = Field(default=None, description="Unit of measurement")
    unit_cost: float | None = Field(default=None, description="Current unit cost")
    total_cost: float = Field(description="Total cost")
    quantity_source: str | None = Field(
        default=None, description="Quantity source (e.g., 'heuristic', 'from_drawing')"
    )
    confidence: float = Field(description="Confidence in this line item")
    flags: list[str] = Field(
        default_factory=list,
        description="Flags (e.g., 'heuristic_quantity', 'suspicious_unit_cost')",
    )
    component_splits: dict[str, float] | None = Field(
        default=None,
        description="Component splits from pricing_v2 if available (material, labor, equipment, overhead_profit)",
    )


class SuggestedAdjustments(BaseModel):
    """Suggested fields to adjust in contractor profile."""

    labor_rates: dict[str, float | None] = Field(
        default_factory=dict,
        description="Suggested labor rates by trade (None if no suggestion)",
    )
    scaffold_weekly_cost: float | None = Field(
        default=None, description="Suggested scaffold weekly cost"
    )
    dumpster_cost: float | None = Field(
        default=None, description="Suggested dumpster cost"
    )
    overhead_pct: float | None = Field(
        default=None, description="Suggested overhead percentage"
    )
    profit_pct: float | None = Field(
        default=None, description="Suggested profit percentage"
    )
    notes: list[str] = Field(
        default_factory=list, description="Notes about suggested adjustments"
    )


class CalibrationPack(BaseModel):
    """Calibration pack for contractor review (Phase 10.3)."""

    project_id: str = Field(description="Project ID")
    profile_id: str | None = Field(
        default=None, description="Contractor profile ID used"
    )
    region_id: str | None = Field(default=None, description="Region identifier")
    top_line_items: list[LineItemCalibration] = Field(
        default_factory=list,
        description="Top 10 line items by cost",
    )
    flagged_line_items: list[LineItemCalibration] = Field(
        default_factory=list,
        description="Line items flagged as heuristic_quantity or suspicious_unit_cost",
    )
    suggested_adjustments: SuggestedAdjustments = Field(
        description="Suggested adjustments to contractor profile"
    )






