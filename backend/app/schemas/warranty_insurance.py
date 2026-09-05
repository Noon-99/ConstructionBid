"""Schema for warranty and insurance extraction (Task 8).

Extracted from project documents (evidence-backed), not contractor declarations.
"""

from typing import Literal

from pydantic import BaseModel, Field


class WarrantyExtraction(BaseModel):
    """Extracted warranty information from project documents."""

    manufacturer_warranty: str | None = Field(
        default=None,
        description="Manufacturer warranty details (e.g., '20-year EPDM membrane warranty', '15-year TPO warranty')",
    )
    manufacturer_warranty_duration: str | None = Field(
        default=None,
        description="Manufacturer warranty duration (e.g., '20 years', '15 years', 'lifetime')",
    )
    workmanship_warranty: str | None = Field(
        default=None,
        description="Workmanship warranty details (e.g., '2-year workmanship warranty', '5-year installation warranty')",
    )
    workmanship_warranty_duration: str | None = Field(
        default=None,
        description="Workmanship warranty duration (e.g., '2 years', '5 years')",
    )
    warranty_evidence: str | None = Field(
        default=None,
        description="Evidence snippet for warranty information (page numbers, spec references)",
    )


class InsuranceExtraction(BaseModel):
    """Extracted insurance requirements from project documents."""

    general_liability_required: bool = Field(
        default=False,
        description="Whether general liability insurance is required",
    )
    general_liability_limit: str | None = Field(
        default=None,
        description="General liability insurance limit (e.g., '$2,000,000', '$5,000,000')",
    )
    workers_compensation_required: bool = Field(
        default=False,
        description="Whether workers compensation insurance is required",
    )
    workers_compensation_limit: str | None = Field(
        default=None,
        description="Workers compensation insurance limit if specified",
    )
    umbrella_insurance_required: bool = Field(
        default=False,
        description="Whether umbrella insurance is required",
    )
    umbrella_insurance_limit: str | None = Field(
        default=None,
        description="Umbrella insurance limit if specified",
    )
    insurance_evidence: str | None = Field(
        default=None,
        description="Evidence snippet for insurance requirements (page numbers, spec references)",
    )


class BondExtraction(BaseModel):
    """Extracted bond requirements from project documents."""

    performance_bond_required: bool = Field(
        default=False,
        description="Whether performance bond is required",
    )
    performance_bond_amount: str | None = Field(
        default=None,
        description="Performance bond amount (e.g., '100% of contract', '$500,000')",
    )
    payment_bond_required: bool = Field(
        default=False,
        description="Whether payment bond is required",
    )
    payment_bond_amount: str | None = Field(
        default=None,
        description="Payment bond amount if specified",
    )
    bond_evidence: str | None = Field(
        default=None,
        description="Evidence snippet for bond requirements (page numbers, spec references)",
    )


class WarrantyAndInsurance(BaseModel):
    """Complete warranty and insurance extraction from project documents (Task 8)."""

    warranty: WarrantyExtraction = Field(
        default_factory=WarrantyExtraction,
        description="Extracted warranty information",
    )
    insurance: InsuranceExtraction = Field(
        default_factory=InsuranceExtraction,
        description="Extracted insurance requirements",
    )
    bonds: BondExtraction = Field(
        default_factory=BondExtraction,
        description="Extracted bond requirements",
    )




