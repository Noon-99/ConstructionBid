"""Pricing profile service (Phase 10.10A).

Loads and selects pricing profiles based on project region.
"""

import json
import yaml
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings
from app.schemas.pricing_profile import PricingProfile
from app.services.region_resolver import resolve_region


def load_profiles(settings: Settings) -> dict[str, PricingProfile]:
    """
    Load all pricing profiles from YAML files.

    Args:
        settings: Application settings

    Returns:
        Dictionary mapping profile_id to PricingProfile
    """
    profiles: dict[str, PricingProfile] = {}
    profiles_dir = Path(__file__).parent.parent / "costing" / "profiles"

    if not profiles_dir.exists():
        logger.warning(f"Pricing profiles directory not found: {profiles_dir}")
        return profiles

    for yml_file in profiles_dir.glob("*.yml"):
        try:
            with open(yml_file, "r") as f:
                profile_data = yaml.safe_load(f)
                if profile_data:
                    profile = PricingProfile.model_validate(profile_data)
                    profiles[profile.profile_id] = profile
                    logger.debug(f"Loaded pricing profile: {profile.profile_id} from {yml_file.name}")
        except Exception as e:
            logger.error(f"Failed to load pricing profile from {yml_file}: {e}")
            continue

    logger.info(f"Loaded {len(profiles)} pricing profiles")
    return profiles


def select_profile(
    document_analysis: dict[str, Any] | None = None,
    extraction_result: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> PricingProfile:
    """
    Select pricing profile based on detected region.

    Args:
        document_analysis: Document analysis artifact (for region detection)
        extraction_result: Extraction result artifact (for region detection)
        settings: Application settings (for loading profiles)

    Returns:
        Selected PricingProfile

    Raises:
        FileNotFoundError: If no profiles found or default profile missing
    """
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    # Load all profiles
    profiles = load_profiles(settings)

    if not profiles:
        raise FileNotFoundError("No pricing profiles found in profiles directory")

    # Resolve region from document analysis/extraction result
    region_result = resolve_region(document_analysis, extraction_result)
    region_id = region_result["region_id"]

    log_ctx = logger.bind(
        region_id=region_id,
        confidence=region_result["confidence"],
        service="pricing_profile_service",
    )
    log_ctx.info(f"Selecting pricing profile for region: {region_id}")

    # Try to find profile matching region
    selected_profile: PricingProfile | None = None

    # First, try exact region match
    for profile in profiles.values():
        if profile.region.upper() == region_id.upper():
            selected_profile = profile
            log_ctx.info(f"Selected profile: {profile.profile_id} (region match: {region_id})")
            break

    # If no match, try to find profile by region prefix (e.g., "NYC" in "nyc_2025q1")
    if not selected_profile:
        region_upper = region_id.upper()
        for profile in profiles.values():
            if region_upper in profile.profile_id.upper() or region_upper in profile.region.upper():
                selected_profile = profile
                log_ctx.info(f"Selected profile: {profile.profile_id} (region prefix match: {region_id})")
                break

    # Fallback to default_national if available
    if not selected_profile:
        if "default_national" in profiles:
            selected_profile = profiles["default_national"]
            log_ctx.info(
                f"No region-specific profile found for {region_id}, using default_national"
            )
        else:
            # Use first available profile as last resort
            selected_profile = list(profiles.values())[0]
            log_ctx.warning(
                f"No matching profile for {region_id} and no default_national found, "
                f"using first available profile: {selected_profile.profile_id}"
            )

    return selected_profile


def save_profile(
    project_id: str,
    profile: PricingProfile,
    output_dir: Path,
) -> None:
    """
    Save selected pricing profile to output directory.

    Args:
        project_id: Project ID
        profile: Pricing profile to save
        output_dir: Output directory for project artifacts
    """
    profile_file = output_dir / "pricing_profile.json"
    profile_file.parent.mkdir(parents=True, exist_ok=True)

    with open(profile_file, "w") as f:
        f.write(profile.model_dump_json(indent=2))

    logger.bind(project_id=project_id, profile_id=profile.profile_id).info(
        f"Saved pricing profile to {profile_file}"
    )





