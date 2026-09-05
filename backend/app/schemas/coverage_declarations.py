"""Schema for Coverage & Warranty declarations (contractor-declared insurance and warranty)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class InsuranceDeclaration(BaseModel):
    """Insurance declaration (contractor-declared)."""

    general_liability_limit: Optional[str] = Field(
        default=None, description="General liability limit (e.g., '$1M', '$2M/$4M')"
    )
    general_liability_status: Literal["declared", "not_declared"] = Field(
        default="not_declared", description="Whether general liability is declared"
    )
    workers_comp_status: Literal["declared", "not_declared"] = Field(
        default="not_declared", description="Whether workers compensation is declared"
    )
    umbrella_limit: Optional[str] = Field(
        default=None, description="Umbrella policy limit (e.g., '$5M')"
    )
    umbrella_status: Literal["declared", "not_declared"] = Field(
        default="not_declared", description="Whether umbrella policy is declared"
    )
    bond_status: Literal["available", "not_available", "not_declared"] = Field(
        default="not_declared", description="Bond availability status"
    )
    notes: Optional[str] = Field(default=None, description="Additional insurance notes")


class WarrantyDeclaration(BaseModel):
    """Warranty declaration (contractor-declared)."""

    workmanship_duration: Optional[str] = Field(
        default=None, description="Workmanship warranty duration (e.g., '1 year', '2 years')"
    )
    workmanship_status: Literal["declared", "not_declared"] = Field(
        default="not_declared", description="Whether workmanship warranty is declared"
    )
    materials_basis: Optional[str] = Field(
        default=None, description="Materials warranty basis (e.g., 'manufacturer', 'contractor')"
    )
    materials_status: Literal["declared", "not_declared"] = Field(
        default="not_declared", description="Whether materials warranty is declared"
    )
    notes: Optional[str] = Field(default=None, description="Additional warranty notes")


class CoverageDeclarations(BaseModel):
    """Coverage & Warranty declarations (contractor-declared, not evidence-backed)."""

    insurance: InsuranceDeclaration = Field(description="Insurance declarations")
    warranty: WarrantyDeclaration = Field(description="Warranty declarations")
    source: Literal["contractor_declared"] = Field(
        default="contractor_declared", description="Source of declarations (always contractor-declared)"
    )
    updated_at: Optional[str] = Field(
        default=None, description="ISO timestamp when declarations were last updated"
    )





