"""Tests for contractor profile endpoints (Phase 9.1B)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_default_contractor_profile() -> None:
    """Test GET /v1/contractor_profiles/default returns the default profile."""
    response = client.get("/v1/contractor_profiles/default")

    assert response.status_code == 200
    data = response.json()

    # Verify required fields
    assert "profile_id" in data
    assert "region" in data
    assert "project_type" in data
    assert "labor_rates" in data
    assert "overhead_pct" in data
    assert "profit_pct" in data
    assert "contingency_pct" in data
    assert "crew_productivity" in data

    # Verify default profile values
    assert data["profile_id"] == "nyc_row_house_masonry_v1"
    assert data["region"] == "NYC"
    assert data["project_type"] == "row_house_masonry"

    # Verify labor rates structure
    assert isinstance(data["labor_rates"], dict)
    assert "masonry" in data["labor_rates"]
    assert data["labor_rates"]["masonry"] == 85.0

    # Verify percentages
    assert data["overhead_pct"] == 18.0
    assert data["profit_pct"] == 12.0
    assert data["contingency_pct"] == 5.0

    # Verify productivity structure
    assert isinstance(data["crew_productivity"], dict)
    assert "repointing_sf_per_day" in data["crew_productivity"]
    assert data["crew_productivity"]["repointing_sf_per_day"] == 120.0






