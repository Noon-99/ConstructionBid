"""Contractor profile endpoints (Phase 9.1B, 10.3)."""

from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.config import Settings, get_settings
from app.services.contractor_profile_store import load_profile
from app.services.profile_patcher import apply_profile_patch

router = APIRouter(tags=["contractor_profiles"])


@router.get("/contractor_profiles/default")
async def get_default_contractor_profile() -> dict:
    """
    Get the default contractor profile (Phase 9.1B).

    Returns the contractor profile specified by DEFAULT_CONTRACTOR_PROFILE_ID.
    """
    settings = get_settings()
    profile_id = settings.default_contractor_profile_id

    try:
        profile = load_profile(profile_id, settings)
        return profile.model_dump(mode="json")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Default contractor profile not found: {profile_id}. {str(e)}",
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load contractor profile {profile_id}: {str(e)}",
        ) from e


@router.post("/profiles/{profile_id}/patch")
async def patch_profile(
    profile_id: str,
    patch: dict[str, Any],
    settings: Settings = get_settings(),
) -> dict:
    """
    Apply a patch to a profile and save as new versioned file (Phase 10.3).

    Args:
        profile_id: Base profile ID (e.g., 'nyc_row_house_masonry_v1')
        patch: Dictionary with fields to update (validated against ContractorProfile schema)

    Returns:
        New ContractorProfile with patch applied

    Raises:
        404: If base profile not found
        400: If patch validation fails
    """
    try:
        new_profile = apply_profile_patch(profile_id, patch, settings)
        return new_profile.model_dump(mode="json")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Profile not found: {profile_id}. {str(e)}",
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Patch validation failed: {str(e)}",
        ) from e

