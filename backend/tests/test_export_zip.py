"""Unit tests for ZIP export service (Phase 6.6)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO
from zipfile import ZipFile

import pytest

from app.services.zip_exporter import export_proposals_zip


def test_export_zip_contains_expected_files() -> None:
    """Test: ZIP contains expected PDF filenames + manifest.json"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "out"
        output_dir.mkdir(parents=True)

        # Create fake project with PDF
        project_id = "test_project_1"
        project_dir = output_dir / project_id
        project_dir.mkdir()
        pdf_path = project_dir / "proposal.pdf"
        pdf_path.write_bytes(b"fake pdf content")

        # Create minimal bid proposal
        bid_file = project_dir / "bid_proposal.json"
        with open(bid_file, "w") as f:
            json.dump(
                {
                    "project_id": project_id,
                    "summary": {"total_cost": 100000.0, "cost_by_division": {}},
                    "line_items": [],
                    "allowances": [],
                    "clarifications": [],
                    "generated_at": "2024-01-01T00:00:00",
                    "estimate_mode": "conceptual",
                    "bid_ready": True,
                },
                f,
            )

        # Create validation report
        validation_file = project_dir / "validation_report.json"
        with open(validation_file, "w") as f:
            json.dump(
                {
                    "project_id": project_id,
                    "passed": True,
                    "score": 0.95,
                    "issues": [],
                    "rerun_performed": False,
                },
                f,
            )

        # Create costing result
        costing_file = project_dir / "costing_result.json"
        with open(costing_file, "w") as f:
            json.dump({"total_cost": 100000.0}, f)

        zip_buffer, manifest = export_proposals_zip(
            project_ids=[project_id], output_dir=output_dir
        )

        # Verify ZIP contents
        with ZipFile(zip_buffer, "r") as zip_file:
            names = zip_file.namelist()
            assert "manifest.json" in names
            assert any("test_project_1" in name and name.endswith(".pdf") for name in names)

        # Verify manifest
        assert len(manifest) == 1
        assert manifest[0]["project_id"] == project_id
        assert manifest[0]["included_pdf"] is True
        assert manifest[0]["pdf_path_in_zip"] is not None
        assert "BID_READY" in manifest[0]["pdf_path_in_zip"] or "PRELIMINARY" in manifest[0]["pdf_path_in_zip"]


def test_export_zip_skips_missing_pdf() -> None:
    """Test: Missing PDFs are skipped (not included in ZIP)"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "out"
        output_dir.mkdir(parents=True)

        project_id = "test_project_missing"
        project_dir = output_dir / project_id
        project_dir.mkdir()
        # No PDF file

        zip_buffer, manifest = export_proposals_zip(
            project_ids=[project_id],
            output_dir=output_dir,
            fail_if_missing_pdf=False,
        )

        # Verify PDF not in ZIP
        with ZipFile(zip_buffer, "r") as zip_file:
            names = zip_file.namelist()
            assert not any(name.endswith(".pdf") for name in names)
            assert "manifest.json" in names

        # Verify manifest shows missing
        assert len(manifest) == 1
        assert manifest[0]["project_id"] == project_id
        assert manifest[0]["included_pdf"] is False
        assert manifest[0]["proposal_pdf_missing"] is True


def test_export_zip_fails_if_missing_pdf() -> None:
    """Test: fail_if_missing_pdf=True raises FileNotFoundError"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "out"
        output_dir.mkdir(parents=True)

        project_id = "test_project_missing"
        project_dir = output_dir / project_id
        project_dir.mkdir()
        # No PDF file

        with pytest.raises(FileNotFoundError):
            export_proposals_zip(
                project_ids=[project_id],
                output_dir=output_dir,
                fail_if_missing_pdf=True,
            )


def test_export_zip_multiple_projects() -> None:
    """Test: Multiple projects are included in ZIP"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "out"
        output_dir.mkdir(parents=True)

        project_ids = ["project_a", "project_b"]
        for project_id in project_ids:
            project_dir = output_dir / project_id
            project_dir.mkdir()
            pdf_path = project_dir / "proposal.pdf"
            pdf_path.write_bytes(b"fake pdf")

        zip_buffer, manifest = export_proposals_zip(
            project_ids=project_ids, output_dir=output_dir
        )

        # Verify both PDFs in ZIP
        with ZipFile(zip_buffer, "r") as zip_file:
            names = zip_file.namelist()
            pdf_names = [n for n in names if n.endswith(".pdf")]
            assert len(pdf_names) == 2

        # Verify manifest has both
        assert len(manifest) == 2
        assert all(m["included_pdf"] for m in manifest)






