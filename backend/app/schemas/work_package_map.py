"""Schema for work package map (Task 1).

Work packages represent contractor-friendly aggregations of technical zones
and line items into logical work packages (e.g., "Parapet / Coping / Roof Edge").

This provides a contractor-grade view while preserving technical zone traceability.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WorkPackage(BaseModel):
    """A contractor-friendly work package aggregating zones and line items."""

    id: str = Field(description="Unique identifier (e.g., 'package_001', 'parapet_package')")
    title: str = Field(description="Human-readable package title (e.g., 'Parapet / Coping / Roof Edge')")
    division: str = Field(
        description="Primary CSI division (e.g., '04 Masonry', '07 56 00 Flashing')"
    )
    trade: str | None = Field(
        default=None, description="Trade name (e.g., 'Masonry', 'Metals', 'Waterproofing')"
    )
    estimated_cost: float = Field(
        ge=0.0, description="Estimated total cost for this package (sum of member line items)"
    )
    priority: Literal["high", "medium", "low"] = Field(
        default="medium", description="Package priority level"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in package grouping (minimum of member item confidences)",
    )
    basis_refs: list[str] = Field(
        default_factory=list,
        description="Evidence/specification references for this package",
    )
    member_zone_ids: list[str] = Field(
        default_factory=list, description="Zone IDs from model_3d included in this package"
    )
    member_line_item_ids: list[str] = Field(
        default_factory=list,
        description="Line item IDs (string indices) from bid_proposal included in this package",
    )


class WorkPackageMap(BaseModel):
    """Complete work package map (Task 1)."""

    project_id: str = Field(description="Project ID this map applies to")
    packages: list[WorkPackage] = Field(
        default_factory=list, description="List of work packages"
    )
    zone_to_package: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from zone_id to package_id for quick lookup",
    )
    line_item_to_package: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from line_item_id (string index) to package_id for quick lookup",
    )
    generated_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp when map was generated"
    )
    version: str = Field(
        default="1.0", description="Schema version for forward compatibility"
    )





