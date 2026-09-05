"""Schema for trade packages / subcontractor breakdown (Phase 11.0)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence_index import EvidenceReference


class TradeLineItem(BaseModel):
    """Line item within a trade package."""

    line_item_index: int = Field(description="Index of the line item in bid_proposal.line_items")
    description: str = Field(description="Item description")
    division: str = Field(description="CSI division")
    quantity: float | None = Field(default=None, description="Quantity")
    unit: str | None = Field(default=None, description="Unit of measurement")
    unit_cost: float | None = Field(default=None, description="Unit cost")
    total_cost: float = Field(description="Total cost for this line item")
    basis: str = Field(description="Basis or evidence for this item")


class TradePackage(BaseModel):
    """Trade-specific bid package for subcontractor distribution (Phase 11.0)."""

    trade_id: str = Field(
        description="Trade identifier (e.g., 'masonry', 'metals', 'waterproofing', 'general_conditions', 'permits')"
    )
    trade_name: str = Field(description="Human-readable trade name (e.g., 'Masonry', 'Metals & Structural Steel')")
    divisions: list[str] = Field(
        default_factory=list,
        description="CSI divisions included in this trade package (e.g., ['04 Masonry', '04 21 00'])",
    )
    total_cost: float = Field(description="Total cost for this trade package")
    line_items: list[TradeLineItem] = Field(
        default_factory=list, description="Line items included in this trade package"
    )
    inclusions: list[str] = Field(
        default_factory=list,
        description="List of scope items explicitly included in this package",
    )
    exclusions: list[str] = Field(
        default_factory=list,
        description="List of items explicitly excluded from this package",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Trade-specific assumptions (e.g., access, weather, site conditions)",
    )
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list,
        description="Aggregated evidence references for this trade package",
    )
    detail_refs: list[str] = Field(
        default_factory=list,
        description="List of detail IDs referenced in this trade package",
    )
    generated_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp when this package was generated"
    )


class TradePackagesExport(BaseModel):
    """Complete trade packages export (Phase 11.0)."""

    project_id: str = Field(description="Project ID")
    profile_id: str | None = Field(default=None, description="Pricing profile ID used")
    generated_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp when packages were generated"
    )
    packages: list[TradePackage] = Field(
        default_factory=list, description="List of trade packages"
    )





