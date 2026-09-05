"""Schema for site context with explicit provenance tracking (Task 3).

SiteContext tracks row/neighbor context information with explicit tags
for whether each field came from evidence or was inferred.
"""

from typing import Literal

from pydantic import BaseModel, Field


class SiteContextProvenance(BaseModel):
    """Provenance tracking for site context fields."""

    street_front: Literal["evidence", "inferred", "unknown"] = Field(
        default="unknown",
        description="Source of street_front field: 'evidence' if found in drawings, 'inferred' if deduced, 'unknown' if not available",
    )
    cross_street_left: Literal["evidence", "inferred", "unknown"] = Field(
        default="unknown",
        description="Source of cross_street_left field",
    )
    cross_street_right: Literal["evidence", "inferred", "unknown"] = Field(
        default="unknown",
        description="Source of cross_street_right field",
    )
    row_condition: Literal["evidence", "inferred", "unknown"] = Field(
        default="unknown",
        description="Source of row_condition field",
    )
    row_count_estimate: Literal["evidence", "inferred", "unknown"] = Field(
        default="unknown",
        description="Source of row_count_estimate field",
    )
    subject_position: Literal["evidence", "inferred", "unknown"] = Field(
        default="unknown",
        description="Source of subject_position field",
    )


class SiteContext(BaseModel):
    """Site context information with explicit provenance tracking (Task 3)."""

    street_front: str | None = Field(
        default=None,
        description="Street name of the front facade (e.g., 'Main Street', '123 Main St'). Only include if explicitly found in drawings.",
    )
    cross_street_left: str | None = Field(
        default=None,
        description="Cross street name to the left (when facing building from street_front). Only include if explicitly found in drawings.",
    )
    cross_street_right: str | None = Field(
        default=None,
        description="Cross street name to the right (when facing building from street_front). Only include if explicitly found in drawings.",
    )
    row_condition: Literal["attached", "semi_detached", "detached", "unknown"] = Field(
        default="unknown",
        description="Type of row condition: 'attached' (party walls), 'semi_detached' (one shared wall), 'detached' (no shared walls), 'unknown'",
    )
    row_count_estimate: int | None = Field(
        default=None,
        ge=1,
        description="Estimated number of buildings in the row (only if can be inferred from drawings, e.g., 'TYP. ADJ. BLDG' or multiple building IDs shown). Never guess specific neighbor addresses.",
    )
    subject_position: Literal["middle", "end", "unknown"] = Field(
        default="unknown",
        description="Position of subject building in row: 'middle' (has neighbors on both sides), 'end' (at end of row), 'unknown'",
    )
    provenance: SiteContextProvenance = Field(
        default_factory=SiteContextProvenance,
        description="Provenance tracking for each field - whether it came from evidence, was inferred, or is unknown",
    )





