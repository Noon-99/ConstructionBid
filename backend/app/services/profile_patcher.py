"""Profile patcher service (Phase 10.3).

Allows saving profile patches as new versioned profiles without overwriting existing ones.
"""

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.contractor_profile import ContractorProfile
from app.services.contractor_profile_store import get_profile_path, load_profile


def apply_profile_patch(
    profile_id: str,
    patch: dict[str, Any],
    settings: Settings,
) -> ContractorProfile:
    """
    Apply a patch to a profile and save as a new versioned file (Phase 10.3).

    Args:
        profile_id: Base profile ID (e.g., 'nyc_row_house_masonry_v1')
        patch: Dictionary with fields to update (validated against ContractorProfile schema)
        settings: Application settings

    Returns:
        New ContractorProfile with patch applied and versioned ID

    Raises:
        FileNotFoundError: If base profile not found
        ValueError: If patch is invalid
    """
    log_ctx = logger.bind(service="profile_patcher", profile_id=profile_id)
    log_ctx.info(f"Applying patch to profile {profile_id}")

    # Load base profile
    base_profile = load_profile(profile_id, settings)

    # Build new profile data with patch applied
    new_profile_data = base_profile.model_dump(mode="json")

    # Apply patch (deep merge for nested structures)
    _deep_merge(new_profile_data, patch)

    # Validate patched data
    try:
        new_profile = ContractorProfile.model_validate(new_profile_data)
    except Exception as e:
        raise ValueError(f"Patch validation failed: {e}") from e

    # Determine new version number
    version = _get_next_version(profile_id, settings)
    base_name = _get_base_name(profile_id)
    new_profile_id = f"{base_name}_v{version}"

    # Update profile_id in the new profile
    new_profile.profile_id = new_profile_id
    new_profile_data["profile_id"] = new_profile_id

    # Save new profile file
    new_profile_path = get_profile_path(new_profile_id, settings)
    new_profile_path.parent.mkdir(parents=True, exist_ok=True)

    with open(new_profile_path, "w") as f:
        json.dump(new_profile_data, f, indent=2)

    log_ctx.info(f"Saved new profile version: {new_profile_id} at {new_profile_path}")

    return new_profile


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> None:
    """Deep merge patch into base dictionary."""
    for key, value in patch.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _get_base_name(profile_id: str) -> str:
    """Extract base name from profile_id (remove version suffix)."""
    # Match pattern: name_vN or just name
    match = re.match(r"^(.+?)_v\d+$", profile_id)
    if match:
        return match.group(1)
    return profile_id


def _get_next_version(profile_id: str, settings: Settings) -> int:
    """Get next version number for a profile."""
    base_name = _get_base_name(profile_id)
    profiles_dir = get_profile_path(profile_id, settings).parent

    # Find existing versions
    versions: list[int] = []
    pattern = re.compile(rf"^{re.escape(base_name)}_v(\d+)\.json$")

    if profiles_dir.exists():
        for file in profiles_dir.glob(f"{base_name}_v*.json"):
            match = pattern.match(file.name)
            if match:
                versions.append(int(match.group(1)))

    # Also check base_name.json (v1 implied)
    base_file = profiles_dir / f"{base_name}.json"
    if base_file.exists():
        versions.append(1)

    if versions:
        return max(versions) + 1
    return 1






