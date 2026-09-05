"""Unit tests for coverage declarations generator."""

import json
from datetime import datetime

import pytest

from app.schemas.coverage_declarations import (
    CoverageDeclarations,
    InsuranceDeclaration,
    WarrantyDeclaration,
)
from app.services.coverage_declarations_generator import generate_coverage_declarations


def test_generate_defaults():
    """Test that generator returns defaults (all not_declared)."""
    result = generate_coverage_declarations("test_project")

    assert isinstance(result, CoverageDeclarations)
    assert result.source == "contractor_declared"
    assert result.updated_at is not None

    # Insurance defaults
    assert result.insurance.general_liability_status == "not_declared"
    assert result.insurance.general_liability_limit is None
    assert result.insurance.workers_comp_status == "not_declared"
    assert result.insurance.umbrella_status == "not_declared"
    assert result.insurance.umbrella_limit is None
    assert result.insurance.bond_status == "not_declared"
    assert result.insurance.notes is None

    # Warranty defaults
    assert result.warranty.workmanship_status == "not_declared"
    assert result.warranty.workmanship_duration is None
    assert result.warranty.materials_status == "not_declared"
    assert result.warranty.materials_basis is None
    assert result.warranty.notes is None


def test_merge_existing_data():
    """Test that merge works (existing data preserved)."""
    existing = {
        "insurance": {
            "general_liability_status": "declared",
            "general_liability_limit": "$2M/$4M",
            "workers_comp_status": "declared",
            "umbrella_status": "not_declared",
            "umbrella_limit": None,
            "bond_status": "available",
            "notes": "Current through 2025",
        },
        "warranty": {
            "workmanship_status": "declared",
            "workmanship_duration": "2 years",
            "materials_status": "declared",
            "materials_basis": "manufacturer",
            "notes": "Standard warranty",
        },
        "source": "contractor_declared",
        "updated_at": "2025-01-01T00:00:00",
    }

    result = generate_coverage_declarations("test_project", existing=existing)

    # Verify merged values
    assert result.insurance.general_liability_status == "declared"
    assert result.insurance.general_liability_limit == "$2M/$4M"
    assert result.insurance.workers_comp_status == "declared"
    assert result.insurance.bond_status == "available"
    assert result.insurance.notes == "Current through 2025"

    assert result.warranty.workmanship_status == "declared"
    assert result.warranty.workmanship_duration == "2 years"
    assert result.warranty.materials_status == "declared"
    assert result.warranty.materials_basis == "manufacturer"
    assert result.warranty.notes == "Standard warranty"


def test_merge_partial_data():
    """Test that merge handles partial/missing keys gracefully."""
    existing = {
        "insurance": {
            "general_liability_status": "declared",
            # Missing other fields
        },
        # Missing warranty
    }

    result = generate_coverage_declarations("test_project", existing=existing)

    # Should not crash, should use defaults for missing fields
    assert result.insurance.general_liability_status == "declared"
    assert result.insurance.workers_comp_status == "not_declared"  # Default
    assert result.warranty.workmanship_status == "not_declared"  # Default


def test_merge_invalid_data():
    """Test that merge handles invalid data gracefully."""
    existing = {
        "insurance": "invalid",  # Should be dict
        "warranty": None,
    }

    # Should not crash, should use defaults
    result = generate_coverage_declarations("test_project", existing=existing)
    assert result.insurance.general_liability_status == "not_declared"
    assert result.warranty.workmanship_status == "not_declared"


def test_serialization():
    """Test that result can be serialized to JSON."""
    result = generate_coverage_declarations("test_project")
    json_str = result.model_dump_json(indent=2)
    data = json.loads(json_str)

    assert data["source"] == "contractor_declared"
    assert data["insurance"]["general_liability_status"] == "not_declared"
    assert data["warranty"]["workmanship_status"] == "not_declared"
    assert "updated_at" in data





