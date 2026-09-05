"""Unit tests for bid readiness service (Phase 6.5)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.services.bid_readiness import compute_bid_readiness
from app.schemas.bid_readiness import BidReadinessResult
from app.schemas.validation_report import ValidationReport
from app.schemas.bid_proposal import BidProposal, BidSummary


def test_bid_ready_all_pass() -> None:
    """Test: passed=true, score>=0.85, geometry_quality authoritative => bid_ready=true"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        # Create validation report (passing)
        validation_data = {
            "project_id": "test_project",
            "passed": True,
            "score": 0.95,
            "issues": [],
            "rerun_performed": False,
        }
        with open(output_dir / "validation_report.json", "w") as f:
            json.dump(validation_data, f)

        # Create bid proposal
        bid_data = {
            "project_id": "test_project",
            "summary": {"total_cost": 100000.0, "cost_by_division": {}},
            "line_items": [],
            "allowances": [],
            "clarifications": [],
            "generated_at": "2024-01-01T00:00:00",
            "estimate_mode": "bid_ready",
            "bid_ready": True,
        }
        with open(output_dir / "bid_proposal.json", "w") as f:
            json.dump(bid_data, f)

        # Create costing result
        costing_data = {"total_cost": 100000.0}
        with open(output_dir / "costing_result.json", "w") as f:
            json.dump(costing_data, f)

        # Create extraction result with authoritative geometry
        extraction_data = {
            "institutional_geometry_for_3d": {
                "geometry_quality": "authoritative",
            }
        }
        with open(output_dir / "extraction_result.json", "w") as f:
            json.dump(extraction_data, f)

        result = compute_bid_readiness("test_project", output_dir)

        assert result.bid_ready is True
        assert result.readiness_score >= 0.85
        assert result.readiness_stamp_text == "BID READY"
        assert len(result.reasons_blocking) == 0


def test_bid_not_ready_validation_failed() -> None:
    """Test: passed=false => bid_ready=false"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        validation_data = {
            "project_id": "test_project",
            "passed": False,
            "score": 0.50,
            "issues": [],
            "rerun_performed": False,
        }
        with open(output_dir / "validation_report.json", "w") as f:
            json.dump(validation_data, f)

        bid_data = {
            "project_id": "test_project",
            "summary": {"total_cost": 100000.0, "cost_by_division": {}},
            "line_items": [],
            "allowances": [],
            "clarifications": [],
            "generated_at": "2024-01-01T00:00:00",
            "estimate_mode": "conceptual",
            "bid_ready": False,
        }
        with open(output_dir / "bid_proposal.json", "w") as f:
            json.dump(bid_data, f)

        with open(output_dir / "costing_result.json", "w") as f:
            json.dump({"total_cost": 100000.0}, f)

        result = compute_bid_readiness("test_project", output_dir)

        assert result.bid_ready is False
        assert "Validation did not pass" in result.reasons_blocking
        assert result.readiness_stamp_text == "PRELIMINARY — REVIEW REQUIRED"


def test_bid_not_ready_score_too_low() -> None:
    """Test: score < 0.85 => bid_ready=false"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        validation_data = {
            "project_id": "test_project",
            "passed": True,
            "score": 0.80,  # Below 0.85 threshold
            "issues": [],
            "rerun_performed": False,
        }
        with open(output_dir / "validation_report.json", "w") as f:
            json.dump(validation_data, f)

        bid_data = {
            "project_id": "test_project",
            "summary": {"total_cost": 100000.0, "cost_by_division": {}},
            "line_items": [],
            "allowances": [],
            "clarifications": [],
            "generated_at": "2024-01-01T00:00:00",
            "estimate_mode": "conceptual",
            "bid_ready": True,
        }
        with open(output_dir / "bid_proposal.json", "w") as f:
            json.dump(bid_data, f)

        with open(output_dir / "costing_result.json", "w") as f:
            json.dump({"total_cost": 100000.0}, f)

        result = compute_bid_readiness("test_project", output_dir)

        assert result.bid_ready is False
        assert any("score too low" in reason for reason in result.reasons_blocking)


def test_bid_not_ready_geometry_partial() -> None:
    """Test: geometry_quality='partial' => bid_ready=false"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        validation_data = {
            "project_id": "test_project",
            "passed": True,
            "score": 0.90,
            "issues": [],
            "rerun_performed": False,
        }
        with open(output_dir / "validation_report.json", "w") as f:
            json.dump(validation_data, f)

        bid_data = {
            "project_id": "test_project",
            "summary": {"total_cost": 100000.0, "cost_by_division": {}},
            "line_items": [],
            "allowances": [],
            "clarifications": [],
            "generated_at": "2024-01-01T00:00:00",
            "estimate_mode": "conceptual",
            "bid_ready": True,
        }
        with open(output_dir / "bid_proposal.json", "w") as f:
            json.dump(bid_data, f)

        with open(output_dir / "costing_result.json", "w") as f:
            json.dump({"total_cost": 100000.0}, f)

        extraction_data = {
            "institutional_geometry_for_3d": {
                "geometry_quality": "partial",
            }
        }
        with open(output_dir / "extraction_result.json", "w") as f:
            json.dump(extraction_data, f)

        result = compute_bid_readiness("test_project", output_dir)

        assert result.bid_ready is False
        assert any("partial" in reason.lower() for reason in result.reasons_blocking)


def test_warning_rerun_performed() -> None:
    """Test: rerun_performed=true => warning only (doesn't block)"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        validation_data = {
            "project_id": "test_project",
            "passed": True,
            "score": 0.95,
            "issues": [],
            "rerun_performed": True,  # Auto-recovery occurred
        }
        with open(output_dir / "validation_report.json", "w") as f:
            json.dump(validation_data, f)

        bid_data = {
            "project_id": "test_project",
            "summary": {"total_cost": 100000.0, "cost_by_division": {}},
            "line_items": [],
            "allowances": [],
            "clarifications": [],
            "generated_at": "2024-01-01T00:00:00",
            "estimate_mode": "bid_ready",
            "bid_ready": True,
        }
        with open(output_dir / "bid_proposal.json", "w") as f:
            json.dump(bid_data, f)

        with open(output_dir / "costing_result.json", "w") as f:
            json.dump({"total_cost": 100000.0}, f)

        result = compute_bid_readiness("test_project", output_dir)

        assert result.bid_ready is True  # Should still be ready
        assert any("Auto-recovery" in warning for warning in result.warnings)
        assert len(result.reasons_blocking) == 0


def test_warning_clarifications_exist() -> None:
    """Test: clarifications exist => warning only"""
    with TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_project"
        output_dir.mkdir(parents=True)

        validation_data = {
            "project_id": "test_project",
            "passed": True,
            "score": 0.95,
            "issues": [],
            "rerun_performed": False,
        }
        with open(output_dir / "validation_report.json", "w") as f:
            json.dump(validation_data, f)

        bid_data = {
            "project_id": "test_project",
            "summary": {"total_cost": 100000.0, "cost_by_division": {}},
            "line_items": [],
            "allowances": [],
            "clarifications": [
                {"text": "Assumption: wall height estimated", "severity": "info"}
            ],
            "generated_at": "2024-01-01T00:00:00",
            "estimate_mode": "conceptual",
            "bid_ready": True,
        }
        with open(output_dir / "bid_proposal.json", "w") as f:
            json.dump(bid_data, f)

        with open(output_dir / "costing_result.json", "w") as f:
            json.dump({"total_cost": 100000.0}, f)

        result = compute_bid_readiness("test_project", output_dir)

        assert result.bid_ready is True  # Should still be ready
        assert any("clarification" in warning.lower() for warning in result.warnings)
        assert len(result.reasons_blocking) == 0






