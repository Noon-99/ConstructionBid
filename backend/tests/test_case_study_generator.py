"""Tests for compliance case study generator."""

from pathlib import Path

import json

import pytest

from app.schemas.case_study import ComplianceCaseStudy
from app.services.case_study_generator import generate_compliance_case_study


@pytest.fixture()
def sample_output_dir(tmp_path: Path) -> Path:
    data = {
        "bid_proposal.json": {
            "summary": {
                "base_scope_cost": 100000.0,
                "compliance_total": 15000.0,
                "total_cost": 115000.0,
                "compliance_costs": {"prevailing_wage": 8000.0, "bond": 7000.0},
            }
        },
        "costing_result.json": {
            "compliance_adjustments": ["prevailing_wage", "bond"],
        },
        "document_analysis.json": {
            "project_address": "2317 Greene St, Ogdensburg, NY",
            "labor_regime": "prevailing_wage",
            "requires_bonds": True,
            "procurement_context": {
                "indicators": ["Department of Transportation", "Prevailing wage"],
                "notes": ["DOT Region 7 spec packet mentions Davis-Bacon."],
                "source_pages": [1, 2],
            },
            "project_schedule": {"bid_submission_date": "2025-02-19"},
        },
        "trust_report.json": {
            "project_name": "NYS OGS Roof Replacement",
            "overall_confidence": 92.0,
            "confidence_explanation": "Evidence coverage above 80% with recovered quantities.",
        },
        "bid_review.json": {
            "recovery_performed": True,
            "recovery_pages": [4, 5],
        },
    }
    for name, content in data.items():
        (tmp_path / name).write_text(json.dumps(content))
    return tmp_path


def test_generate_case_study_basic(sample_output_dir: Path) -> None:
    case_study = generate_compliance_case_study(
        project_id="test_project",
        output_dir=sample_output_dir,
    )

    assert isinstance(case_study, ComplianceCaseStudy)
    assert case_study.project_id == "test_project"
    assert case_study.project_name == "NYS OGS Roof Replacement"
    assert case_study.location == "2317 Greene St, Ogdensburg, NY"
    assert case_study.prevailing_wage_applied is True
    assert case_study.bonds_required is True
    assert case_study.compliance_breakdown == {"prevailing_wage": 8000.0, "bond": 7000.0}
    assert case_study.compliance_delta_pct == 15.0
    assert "Prevailing wage" in case_study.summary
    assert case_study.recommendations

    artifact_path = sample_output_dir / "case_study.json"
    assert artifact_path.exists()
    serialized = json.loads(artifact_path.read_text())
    assert serialized["project_id"] == "test_project"
    assert serialized["summary"] == case_study.summary
