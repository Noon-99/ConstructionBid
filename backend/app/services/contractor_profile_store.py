"""Contractor profile store (Phase 9.1A).

Loads contractor profiles from JSON files for bid synthesis.
"""

import json
from pathlib import Path

from loguru import logger

from app.core.config import Settings
from app.schemas.contractor_profile import ContractorProfile


def get_profile_path(profile_id: str, settings: Settings | None = None) -> Path:
    """
    Get the file path for a contractor profile.

    Args:
        profile_id: Profile identifier (e.g., 'nyc_row_house_masonry_v1')
        settings: Optional settings (uses default if None)

    Returns:
        Path to profile JSON file
    """
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    # Profile files are stored in app/data/contractor_profiles/
    # This path is relative to the backend directory
    backend_dir = Path(__file__).parent.parent.parent
    profiles_dir = backend_dir / "app" / "data" / "contractor_profiles"
    return profiles_dir / f"{profile_id}.json"


def load_profile(profile_id: str, settings: Settings | None = None) -> ContractorProfile:
    """
    Load a contractor profile by ID.

    Args:
        profile_id: Profile identifier (e.g., 'nyc_row_house_masonry_v1')
        settings: Optional settings (uses default if None)

    Returns:
        ContractorProfile object

    Raises:
        FileNotFoundError: If profile file does not exist
        ValueError: If profile JSON is invalid
    """
    profile_path = get_profile_path(profile_id, settings)

    if not profile_path.exists():
        raise FileNotFoundError(
            f"Contractor profile not found: {profile_id} (expected at {profile_path})"
        )

    try:
        with open(profile_path, "r") as f:
            profile_data = json.load(f)

        profile = ContractorProfile.model_validate(profile_data)
        logger.info(f"Loaded contractor profile: {profile_id} (region: {profile.region}, type: {profile.project_type})")
        return profile

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in contractor profile {profile_id}: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to load contractor profile {profile_id}: {e}") from e






