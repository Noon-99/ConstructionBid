"""Pydantic models for trade coverage analysis results."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TradeEvidence(BaseModel):
    """Signals tying a trade to a specific drawing page."""

    page_number: int = Field(description="1-indexed page number from the source PDF")
    sheet_id: Optional[str] = Field(default=None, description="Sheet identifier if available")
    sheet_title: Optional[str] = Field(default=None, description="Sheet title if available")
    signals: List[str] = Field(default_factory=list, description="Keywords or indicators found on the page")
    signal_types: List[str] = Field(
        default_factory=list,
        description="Normalized signal categories (e.g., roofing_plan, window_schedule)",
    )
    score: float = Field(ge=0.0, description="Relative strength of this evidence for the trade")


class TradeCoverageEntry(BaseModel):
    """Aggregated coverage details for a single trade."""

    trade: str = Field(description="Human-readable trade label, e.g., 'Roofing' or 'Windows'")
    csi_division: str = Field(description="CSI division code or identifier")
    confidence: float = Field(ge=0.0, le=1.0, description="Normalized confidence that the trade is present")
    total_score: float = Field(ge=0.0, description="Raw coverage score prior to normalization")
    signal_types: List[str] = Field(
        default_factory=list,
        description="Unique signal categories observed for this trade",
    )
    evidence: List[TradeEvidence] = Field(default_factory=list, description="Supporting evidence pages")


class TradeCoverageResult(BaseModel):
    """Top-level trade coverage report for a project."""

    project_id: str = Field(description="Project identifier")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of coverage analysis")
    trades: List[TradeCoverageEntry] = Field(default_factory=list, description="Detected trade signals sorted by confidence")
    dominant_trades: List[str] = Field(
        default_factory=list,
        description="Trade labels whose confidence cleared the dominance threshold",
    )
