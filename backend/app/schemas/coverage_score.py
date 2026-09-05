"""Schema for coverage score evaluation."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class MissingTrade(BaseModel):
    """A trade detected in coverage analysis but missing from extraction outputs."""

    trade: str = Field(description="Trade label (e.g., 'roofing')")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence from trade coverage")
    evidence_pages: List[int] = Field(default_factory=list, description="1-indexed pages with supporting evidence")
    missing_features: List[str] = Field(
        default_factory=list,
        description="Coverage features (scope, quantity, detail, plan) that were not satisfied",
    )


class CoverageScoreReport(BaseModel):
    """Coverage score summary compared against extraction artifacts."""

    project_id: str = Field(description="Project identifier")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of evaluation")
    coverage_score: float = Field(ge=0.0, le=1.0, description="Matched trades / dominant trades ratio")
    dominant_trades: List[str] = Field(default_factory=list, description="Trades considered dominant during evaluation")
    matched_trades: List[str] = Field(default_factory=list, description="Trades satisfied by extraction outputs")
    missing_trades: List[MissingTrade] = Field(default_factory=list, description="Trades lacking supporting extraction artifacts")
    trade_features: dict[str, dict[str, List[str]]] = Field(
        default_factory=dict,
        description="Per-trade feature coverage metadata: {'expected': [...], 'matched': [...]}",
    )
