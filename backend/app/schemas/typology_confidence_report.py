"""Schema for typology confidence report (Phase 10.7).

Explains why a particular typology was chosen and confidence level.
"""

from typing import Literal

from pydantic import BaseModel, Field


class TypologyIndicator(BaseModel):
    """Indicator that influenced typology decision."""

    indicator_type: Literal[
        "sheet_type",
        "location_type",
        "keyword_match",
        "building_context",
        "scope_pattern",
        "default_fallback",
    ] = Field(description="Type of indicator")
    indicator_value: str = Field(description="Specific value or pattern matched")
    strength: Literal["strong", "moderate", "weak"] = Field(description="Indicator strength")
    confidence_contribution: float = Field(
        ge=0.0, le=1.0, description="How much this indicator contributes to confidence (0.0-1.0)"
    )


class TypologyConfidenceReport(BaseModel):
    """Report explaining typology classification decision (Phase 10.7)."""

    project_id: str = Field(description="Project ID")
    final_project_type: Literal[
        "row_house",
        "commercial",
        "small_commercial",
        "multi_family",
        "institutional",
        "mixed",
        "single_family",
        "unknown",
    ] = Field(description="Final resolved project type")
    original_project_type: Literal[
        "row_house",
        "commercial",
        "small_commercial",
        "multi_family",
        "institutional",
        "mixed",
        "single_family",
        "unknown",
    ] = Field(description="Original project type from Stage 1")
    overall_confidence: float = Field(
        ge=0.0, le=1.0, description="Overall confidence in typology classification (0.0-1.0)"
    )
    indicators: list[TypologyIndicator] = Field(
        default_factory=list, description="Indicators that influenced the decision"
    )
    routing_decision: Literal[
        "row_house_path",
        "institutional_path",
        "fallback_row_house",
    ] = Field(
        description="Which extraction path was chosen and why"
    )
    routing_reason: str = Field(description="Explanation for routing decision")
    was_overridden: bool = Field(
        default=False, description="True if typology_resolver overrode Stage 1 classification"
    )
    override_reasons: list[str] = Field(
        default_factory=list, description="Reasons for override if was_overridden=True"
    )






