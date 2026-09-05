"""Coverage & Warranty declarations generator (contractor-declared, no AI extraction)."""

from datetime import datetime
from typing import Optional

from loguru import logger

from app.schemas.coverage_declarations import (
    CoverageDeclarations,
    InsuranceDeclaration,
    WarrantyDeclaration,
)


def generate_coverage_declarations(
    project_id: str, existing: Optional[dict] = None
) -> CoverageDeclarations:
    """
    Generate coverage declarations with defaults (all not_declared).

    Args:
        project_id: Project ID
        existing: Optional existing declarations dict to merge

    Returns:
        CoverageDeclarations with defaults (all statuses = "not_declared")
    """
    log_ctx = logger.bind(project_id=project_id, service="coverage_declarations_generator")
    log_ctx.info("Generating coverage declarations")

    # Default insurance declaration
    default_insurance = InsuranceDeclaration(
        general_liability_limit=None,
        general_liability_status="not_declared",
        workers_comp_status="not_declared",
        umbrella_limit=None,
        umbrella_status="not_declared",
        bond_status="not_declared",
        notes=None,
    )

    # Default warranty declaration
    default_warranty = WarrantyDeclaration(
        workmanship_duration=None,
        workmanship_status="not_declared",
        materials_basis=None,
        materials_status="not_declared",
        notes=None,
    )

    # If existing data provided, merge safely
    if existing:
        try:
            # Merge insurance
            if "insurance" in existing and isinstance(existing["insurance"], dict):
                ins_data = existing["insurance"]
                default_insurance = InsuranceDeclaration(
                    general_liability_limit=ins_data.get("general_liability_limit"),
                    general_liability_status=ins_data.get(
                        "general_liability_status", "not_declared"
                    ),
                    workers_comp_status=ins_data.get("workers_comp_status", "not_declared"),
                    umbrella_limit=ins_data.get("umbrella_limit"),
                    umbrella_status=ins_data.get("umbrella_status", "not_declared"),
                    bond_status=ins_data.get("bond_status", "not_declared"),
                    notes=ins_data.get("notes"),
                )

            # Merge warranty
            if "warranty" in existing and isinstance(existing["warranty"], dict):
                war_data = existing["warranty"]
                default_warranty = WarrantyDeclaration(
                    workmanship_duration=war_data.get("workmanship_duration"),
                    workmanship_status=war_data.get("workmanship_status", "not_declared"),
                    materials_basis=war_data.get("materials_basis"),
                    materials_status=war_data.get("materials_status", "not_declared"),
                    notes=war_data.get("notes"),
                )

            log_ctx.debug("Merged existing coverage declarations")
        except Exception as e:
            log_ctx.warning(f"Failed to merge existing declarations, using defaults: {e}")

    declarations = CoverageDeclarations(
        insurance=default_insurance,
        warranty=default_warranty,
        source="contractor_declared",
        updated_at=datetime.now().isoformat(),
    )

    log_ctx.info(
        f"Coverage declarations generated: "
        f"insurance={default_insurance.general_liability_status}, "
        f"warranty={default_warranty.workmanship_status}"
    )

    return declarations





