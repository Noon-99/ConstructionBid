"""Tests for pricing profile service (Phase 10.10A)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.schemas.pricing_profile import PricingProfile
from app.services.pricing_profile_service import load_profiles, select_profile, save_profile


@pytest.fixture
def settings() -> Settings:
    """Fixture for settings."""
    return Settings()


def test_load_profiles_loads_yaml_files(settings: Settings) -> None:
    """Test that load_profiles loads YAML files from profiles directory."""
    profiles = load_profiles(settings)

    assert len(profiles) >= 2  # Should have at least default_national and nyc_2025q1
    assert "default_national" in profiles
    assert "nyc_2025q1" in profiles

    # Verify profile structure
    default_profile = profiles["default_national"]
    assert default_profile.profile_id == "default_national"
    assert default_profile.region == "US_DEFAULT"
    assert default_profile.labor_rates.masonry is not None
    assert default_profile.material_multipliers.brick is not None


def test_select_profile_chooses_by_region(settings: Settings) -> None:
    """Test that select_profile chooses profile based on region."""
    # NYC address should select NYC profile
    profile = select_profile(
        document_analysis={"project_address": "123 Main St, New York, NY 10001"},
        extraction_result=None,
        settings=settings,
    )

    assert profile is not None
    assert profile.region == "NYC" or profile.profile_id == "nyc_2025q1"


def test_select_profile_falls_back_to_default(settings: Settings) -> None:
    """Test that select_profile falls back to default if region not found."""
    # Unknown region should use default
    profile = select_profile(
        document_analysis={"project_address": "123 Main St, Unknown City, ZZ 99999"},
        extraction_result=None,
        settings=settings,
    )

    assert profile is not None
    # Should fall back to default_national
    assert profile.profile_id == "default_national" or profile.region == "US_DEFAULT"


def test_select_profile_deterministic(settings: Settings) -> None:
    """Test that profile selection is deterministic."""
    doc_analysis = {"project_address": "123 Main St, New York, NY 10001"}

    profile1 = select_profile(
        document_analysis=doc_analysis,
        extraction_result=None,
        settings=settings,
    )

    profile2 = select_profile(
        document_analysis=doc_analysis,
        extraction_result=None,
        settings=settings,
    )

    assert profile1.profile_id == profile2.profile_id


def test_save_profile_writes_json(tmp_path: Path, settings: Settings) -> None:
    """Test that save_profile writes profile to JSON file."""
    output_dir = tmp_path / "out" / "test-project"
    
    # Load a profile
    profiles = load_profiles(settings)
    profile = profiles["default_national"]

    save_profile("test-project", profile, output_dir)

    profile_file = output_dir / "pricing_profile.json"
    assert profile_file.exists()

    # Verify JSON is valid and matches profile
    with open(profile_file, "r") as f:
        saved_data = json.load(f)

    assert saved_data["profile_id"] == profile.profile_id
    assert saved_data["region"] == profile.region
    assert saved_data["labor_rates"]["masonry"] == profile.labor_rates.masonry


def test_profile_has_required_fields(settings: Settings) -> None:
    """Test that all loaded profiles have required fields."""
    profiles = load_profiles(settings)

    for profile_id, profile in profiles.items():
        assert profile.profile_id
        assert profile.label
        assert profile.region
        assert profile.currency == "USD"
        assert profile.labor_rates is not None
        assert profile.material_multipliers is not None
        assert profile.equipment_rates is not None
        assert len(profile.overhead_pct_range) == 2
        assert len(profile.profit_pct_range) == 2
        assert profile.overhead_pct_default > 0
        assert profile.profit_pct_default > 0





