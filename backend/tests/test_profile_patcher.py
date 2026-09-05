"""Unit tests for profile patcher (Phase 10.3)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.services.profile_patcher import apply_profile_patch, _get_next_version, _get_base_name
from app.schemas.contractor_profile import ContractorProfile, LaborRates, CrewProductivity
from app.core.config import Settings


def test_get_base_name() -> None:
    """Test: Extract base name from profile_id."""
    assert _get_base_name("nyc_row_house_masonry_v1") == "nyc_row_house_masonry"
    assert _get_base_name("test_profile_v5") == "test_profile"
    assert _get_base_name("simple_name") == "simple_name"


def test_get_next_version() -> None:
    """Test: Get next version number."""
    with TemporaryDirectory() as tmpdir:
        profiles_dir = Path(tmpdir) / "app" / "data" / "contractor_profiles"
        profiles_dir.mkdir(parents=True)

        settings = Settings()

        # Mock get_profile_path to use tmpdir
        original_get_profile_path = None
        try:
            from app.services import profile_patcher
            from app.services import contractor_profile_store

            original_get_profile_path = contractor_profile_store.get_profile_path

            def mock_get_profile_path(profile_id: str, settings_inner: Settings | None = None) -> Path:
                return profiles_dir / f"{profile_id}.json"

            # Patch both in the patcher module (which imports it) and the store module
            contractor_profile_store.get_profile_path = mock_get_profile_path
            profile_patcher.get_profile_path = mock_get_profile_path

            # Test: No existing versions
            assert _get_next_version("test_profile", settings) == 1

            # Create v1 file
            v1_file = profiles_dir / "test_profile_v1.json"
            v1_file.write_text('{"profile_id": "test_profile_v1", "region": "NYC", "project_type": "test", "labor_rates": {}, "overhead_pct": 10.0, "profit_pct": 10.0, "contingency_pct": 5.0, "crew_productivity": {}}')

            assert _get_next_version("test_profile", settings) == 2

            # Create v2 file
            v2_file = profiles_dir / "test_profile_v2.json"
            v2_file.write_text('{"profile_id": "test_profile_v2", "region": "NYC", "project_type": "test", "labor_rates": {}, "overhead_pct": 10.0, "profit_pct": 10.0, "contingency_pct": 5.0, "crew_productivity": {}}')

            assert _get_next_version("test_profile", settings) == 3

        finally:
            if original_get_profile_path:
                contractor_profile_store.get_profile_path = original_get_profile_path
                if hasattr(profile_patcher, "get_profile_path"):
                    import importlib
                    importlib.reload(profile_patcher)


def test_apply_profile_patch_creates_new_version() -> None:
    """Test: Patch creates new versioned file, old profile unchanged."""
    with TemporaryDirectory() as tmpdir:
        profiles_dir = Path(tmpdir) / "app" / "data" / "contractor_profiles"
        profiles_dir.mkdir(parents=True)

        # Create base profile
        base_profile = ContractorProfile(
            profile_id="test_profile_v1",
            region="NYC",
            project_type="row_house_masonry",
            labor_rates=LaborRates(masonry=75.0),
            overhead_pct=18.0,
            profit_pct=12.0,
            contingency_pct=5.0,
            crew_productivity=CrewProductivity(),
        )

        base_file = profiles_dir / "test_profile_v1.json"
        with open(base_file, "w") as f:
            f.write(base_profile.model_dump_json(indent=2))

        # Mock get_profile_path and load_profile
        settings = Settings()
        original_get_profile_path = None
        original_load_profile = None

        try:
            from app.services import contractor_profile_store
            from app.services import profile_patcher

            original_get_profile_path = contractor_profile_store.get_profile_path
            original_load_profile = contractor_profile_store.load_profile

            def mock_get_profile_path(profile_id: str, settings_inner: Settings | None = None) -> Path:
                return profiles_dir / f"{profile_id}.json"

            def mock_load_profile(profile_id: str, settings_inner: Settings | None = None) -> ContractorProfile:
                file_path = profiles_dir / f"{profile_id}.json"
                if not file_path.exists():
                    raise FileNotFoundError(f"Profile not found: {profile_id}")
                with open(file_path, "r") as f:
                    data = json.load(f)
                return ContractorProfile.model_validate(data)

            # Patch both modules
            contractor_profile_store.get_profile_path = mock_get_profile_path
            contractor_profile_store.load_profile = mock_load_profile
            profile_patcher.get_profile_path = mock_get_profile_path
            profile_patcher.load_profile = mock_load_profile

            # Apply patch
            patch = {
                "overhead_pct": 20.0,
                "profit_pct": 15.0,
                "labor_rates": {"masonry": 80.0},
            }

            new_profile = apply_profile_patch("test_profile_v1", patch, settings)

            # Verify base profile unchanged
            with open(base_file, "r") as f:
                base_data = json.load(f)
            assert base_data["overhead_pct"] == 18.0
            assert base_data["profit_pct"] == 12.0

            # Verify new profile created
            new_file = profiles_dir / "test_profile_v2.json"
            assert new_file.exists()

            # Verify new profile has patch applied
            assert new_profile.profile_id == "test_profile_v2"
            assert new_profile.overhead_pct == 20.0
            assert new_profile.profit_pct == 15.0
            assert new_profile.labor_rates.masonry == 80.0

        finally:
            if original_get_profile_path:
                contractor_profile_store.get_profile_path = original_get_profile_path
            if original_load_profile:
                contractor_profile_store.load_profile = original_load_profile


def test_apply_profile_patch_validation() -> None:
    """Test: Patch validation against schema."""
    with TemporaryDirectory() as tmpdir:
        profiles_dir = Path(tmpdir) / "app" / "data" / "contractor_profiles"
        profiles_dir.mkdir(parents=True)

        base_profile = ContractorProfile(
            profile_id="test_profile_v1",
            region="NYC",
            project_type="row_house_masonry",
            labor_rates=LaborRates(),
            overhead_pct=18.0,
            profit_pct=12.0,
            contingency_pct=5.0,
            crew_productivity=CrewProductivity(),
        )

        base_file = profiles_dir / "test_profile_v1.json"
        with open(base_file, "w") as f:
            f.write(base_profile.model_dump_json(indent=2))

        settings = Settings()
        original_get_profile_path = None
        original_load_profile = None

        try:
            from app.services import contractor_profile_store
            from app.services import profile_patcher

            original_get_profile_path = contractor_profile_store.get_profile_path
            original_load_profile = contractor_profile_store.load_profile

            def mock_get_profile_path(profile_id: str, settings_inner: Settings | None = None) -> Path:
                return profiles_dir / f"{profile_id}.json"

            def mock_load_profile(profile_id: str, settings_inner: Settings | None = None) -> ContractorProfile:
                file_path = profiles_dir / f"{profile_id}.json"
                if not file_path.exists():
                    raise FileNotFoundError(f"Profile not found: {profile_id}")
                with open(file_path, "r") as f:
                    data = json.load(f)
                return ContractorProfile.model_validate(data)

            # Patch both modules
            contractor_profile_store.get_profile_path = mock_get_profile_path
            contractor_profile_store.load_profile = mock_load_profile
            profile_patcher.get_profile_path = mock_get_profile_path
            profile_patcher.load_profile = mock_load_profile

            # Invalid patch (overhead_pct > 100)
            patch = {"overhead_pct": 150.0}

            with pytest.raises(ValueError, match="validation failed"):
                apply_profile_patch("test_profile_v1", patch, settings)

        finally:
            if original_get_profile_path:
                contractor_profile_store.get_profile_path = original_get_profile_path
                if hasattr(profile_patcher, "get_profile_path"):
                    import importlib
                    importlib.reload(profile_patcher)
            if original_load_profile:
                contractor_profile_store.load_profile = original_load_profile
                if hasattr(profile_patcher, "load_profile"):
                    import importlib
                    importlib.reload(profile_patcher)

