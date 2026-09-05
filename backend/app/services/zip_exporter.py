"""ZIP export service for bulk proposal PDFs (Phase 6.6)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile, ZIP_DEFLATED
from io import BytesIO

from loguru import logger

from app.services.bid_readiness import compute_bid_readiness


def export_proposals_zip(
    project_ids: list[str],
    output_dir: Path | None = None,
    include_manifest: bool = True,
    fail_if_missing_pdf: bool = False,
) -> tuple[BytesIO, list[dict[str, Any]]]:
    """
    Create a ZIP file containing proposal PDFs and manifest.

    Args:
        project_ids: List of project IDs to export
        output_dir: Base output directory (default: Path("out"))
        include_manifest: Whether to include manifest.json
        fail_if_missing_pdf: If True, raise error if any PDF missing

    Returns:
        Tuple of (ZIP file bytes, manifest entries list)

    Raises:
        FileNotFoundError: If fail_if_missing_pdf=True and any PDF is missing
    """
    if output_dir is None:
        output_dir = Path("out")

    log_ctx = logger.bind(service="zip_exporter", project_count=len(project_ids))
    log_ctx.info(f"Starting bulk export for {len(project_ids)} projects")

    manifest_entries: list[dict[str, Any]] = []
    errors: list[str] = []

    # Use BytesIO for in-memory ZIP (memory-safe for reasonable sizes)
    # For very large exports (>100MB), could use tempfile fallback
    zip_buffer = BytesIO()

    with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as zip_file:
        for project_id in project_ids:
            project_dir = output_dir / project_id
            pdf_path = project_dir / "proposal.pdf"

            entry: dict[str, Any] = {
                "project_id": project_id,
                "included_pdf": False,
                "pdf_path_in_zip": None,
                "proposal_pdf_missing": not pdf_path.exists(),
                "errors": [],
            }

            # Check if project directory exists
            if not project_dir.exists():
                error_msg = f"Project directory not found: {project_dir}"
                entry["errors"].append(error_msg)
                errors.append(f"{project_id}: {error_msg}")
                if fail_if_missing_pdf:
                    raise FileNotFoundError(f"{project_id}: {error_msg}")
                manifest_entries.append(entry)
                continue

            # Try to compute bid readiness
            try:
                readiness = compute_bid_readiness(project_id, project_dir)
                entry["bid_ready"] = readiness.bid_ready
                entry["readiness_score"] = readiness.readiness_score
                entry["stamp"] = readiness.readiness_stamp_text
                entry["blocking"] = readiness.reasons_blocking
                entry["warnings"] = readiness.warnings
            except Exception as e:
                log_ctx.warning(f"Failed to compute readiness for {project_id}: {e}")
                entry["errors"].append(f"Readiness computation failed: {e}")
                entry["bid_ready"] = False
                entry["readiness_score"] = 0.0
                entry["stamp"] = "PRELIMINARY"
                entry["blocking"] = []
                entry["warnings"] = []

            # Try to load additional metadata
            try:
                # Validation score
                validation_file = project_dir / "validation_report.json"
                if validation_file.exists():
                    with open(validation_file, "r") as f:
                        validation_data = json.load(f)
                    entry["validation_score"] = validation_data.get("score", 0.0)
                else:
                    entry["validation_score"] = None

                # Total cost
                costing_file = project_dir / "costing_result.json"
                if costing_file.exists():
                    with open(costing_file, "r") as f:
                        costing_data = json.load(f)
                    entry["total_cost"] = costing_data.get("total_cost")
                else:
                    entry["total_cost"] = None

                # Geometry quality
                extraction_file = project_dir / "extraction_result.json"
                if extraction_file.exists():
                    with open(extraction_file, "r") as f:
                        extraction_data = json.load(f)
                    inst_geometry = extraction_data.get("institutional_geometry_for_3d")
                    if inst_geometry:
                        entry["geometry_quality"] = inst_geometry.get("geometry_quality")
                    else:
                        entry["geometry_quality"] = None
                else:
                    entry["geometry_quality"] = None
            except Exception as e:
                log_ctx.warning(f"Failed to load metadata for {project_id}: {e}")
                entry["errors"].append(f"Metadata load failed: {e}")

            # Add PDF to ZIP if exists
            if pdf_path.exists():
                try:
                    # Determine stamp for filename
                    stamp = "BID_READY" if entry.get("bid_ready", False) else "PRELIMINARY"
                    pdf_name_in_zip = f"proposals/{project_id}_{stamp}.pdf"

                    # Read PDF and add to ZIP
                    with open(pdf_path, "rb") as pdf_file:
                        zip_file.writestr(pdf_name_in_zip, pdf_file.read())

                    entry["included_pdf"] = True
                    entry["pdf_path_in_zip"] = pdf_name_in_zip
                    log_ctx.debug(f"Added PDF for {project_id}: {pdf_name_in_zip}")
                except Exception as e:
                    error_msg = f"Failed to read PDF: {e}"
                    entry["errors"].append(error_msg)
                    errors.append(f"{project_id}: {error_msg}")
                    if fail_if_missing_pdf:
                        raise FileNotFoundError(f"{project_id}: {error_msg}")
            else:
                error_msg = f"Proposal PDF not found: {pdf_path}"
                entry["errors"].append(error_msg)
                errors.append(f"{project_id}: {error_msg}")
                if fail_if_missing_pdf:
                    raise FileNotFoundError(f"{project_id}: {error_msg}")

            manifest_entries.append(entry)

        # Add manifest.json if requested
        if include_manifest:
            manifest_json = json.dumps(manifest_entries, indent=2)
            zip_file.writestr("manifest.json", manifest_json.encode("utf-8"))
            log_ctx.debug("Added manifest.json to ZIP")

    log_ctx.info(
        f"Export complete: {len([e for e in manifest_entries if e['included_pdf']])} PDFs included, "
        f"{len([e for e in manifest_entries if not e['included_pdf']])} skipped"
    )

    # Reset buffer position for reading
    zip_buffer.seek(0)

    return zip_buffer, manifest_entries

