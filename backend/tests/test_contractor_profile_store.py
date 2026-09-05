"""Tests for contractor profile store (Phase 9.1A)."""

import pytest

from app.core.config import Settings
from app.schemas.contractor_profile import ContractorProfile
from app.services.contractor_profile_store import load_profile, get_profile_path


def test_load_default_profile() -> None:
    """Test loading the default NYC row house masonry profile."""
    profile = load_profile("nyc_row_house_masonry_v1")

    assert profile.profile_id == "nyc_row_house_masonry_v1"
    assert profile.region == "NYC"
    assert profile.project_type == "row_house_masonry"

    # Check labor rates
    assert profile.labor_rates.masonry == 85.0
    assert profile.labor_rates.laborer == 65.0
    assert profile.labor_rates.foreman == 110.0

    # Check percentages
    assert profile.overhead_pct == 18.0
    assert profile.profit_pct == 12.0
    assert profile.contingency_pct == 5.0

    # Check logistics rates
    assert profile.logistics_rates["scaffold_weekly"] == 1200.0
    assert profile.logistics_rates["dumpster_each"] == 485.0
    assert profile.logistics_rates["sidewalk_shed_weekly"] == 400.0

    # Check productivity
    assert profile.crew_productivity.repointing_sf_per_day == 120.0
    assert profile.crew_productivity.parapet_rebuild_lf_per_day == 10.0
    assert profile.crew_productivity.lintel_each_per_day == 2.0


def test_load_profile_missing_file() -> None:
    """Test that loading a non-existent profile raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError) as exc_info:
        load_profile("nonexistent_profile_v1")

    assert "not found" in str(exc_info.value).lower()
    assert "nonexistent_profile_v1" in str(exc_info.value)


def test_profile_path_resolution() -> None:
    """Test that profile path is resolved correctly."""
    settings = Settings()
    profile_path = get_profile_path("nyc_row_house_masonry_v1", settings)

    assert profile_path.exists(), f"Profile file should exist at {profile_path}"
    assert profile_path.name == "nyc_row_house_masonry_v1.json"
    assert profile_path.suffix == ".json"


def test_profile_validation() -> None:
    """Test that profile schema validation works correctly."""
    profile = load_profile("nyc_row_house_masonry_v1")

    # Verify it's a valid ContractorProfile
    assert isinstance(profile, ContractorProfile)
    assert profile.profile_id is not None
    assert profile.region is not None
    assert profile.project_type is not None
    assert profile.labor_rates is not None
    assert profile.crew_productivity is not None

    # Verify percentages are in valid range
    assert 0.0 <= profile.overhead_pct <= 100.0
    assert 0.0 <= profile.profit_pct <= 100.0
    assert 0.0 <= profile.contingency_pct <= 100.0






