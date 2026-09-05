"""Service helpers for managing manual override inputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

from loguru import logger

from app.core.config import Settings, get_settings
from app.schemas.manual_overrides import ManualOverrides, ManualOverridesUpdate
from app.services.run_state_store import RunStateStore


def _ensure_legacy_link(preferred_out: Path, legacy_out: Path) -> None:
    """Ensure backend/out points to preferred out directory via symlink."""

    legacy_out.parent.mkdir(parents=True, exist_ok=True)

    try:
        if legacy_out.exists():
            try:
                if legacy_out.resolve() == preferred_out.resolve():
                    return
            except FileNotFoundError:
                legacy_out.unlink(missing_ok=True)
            if legacy_out.is_symlink():
                legacy_out.unlink()
            else:
                shutil.rmtree(legacy_out)

        legacy_out.symlink_to(preferred_out, target_is_directory=True)
    except Exception as link_error:  # pragma: no cover - defensive
        logger.bind(source=str(legacy_out), destination=str(preferred_out)).warning(
            f"Failed to create legacy output symlink: {link_error}"
        )


def _resolve_output_dir(project_id: str, settings: Settings) -> Path:
    """Compute output directory without importing API modules (avoids cycles)."""

    project_root = settings.storage_root.parent.parent
    preferred_out = project_root / "out" / project_id
    legacy_out = settings.storage_root.parent / "out" / project_id

    if preferred_out.exists():
        preferred_out.mkdir(parents=True, exist_ok=True)
        _ensure_legacy_link(preferred_out, legacy_out)
        return preferred_out

    legacy_candidates = [
        settings.storage_root.parent / "out" / project_id,
        Path("out") / project_id,
        Path("../out") / project_id,
    ]

    for candidate in legacy_candidates:
        if candidate.exists():
            preferred_out.parent.mkdir(parents=True, exist_ok=True)
            if not preferred_out.exists():
                preferred_out.mkdir(parents=True, exist_ok=True)
                try:
                    import shutil

                    shutil.copytree(candidate, preferred_out, dirs_exist_ok=True)
                    logger.bind(project_id=project_id).info(
                        "Migrated project artifacts to unified out directory",
                        source=str(candidate),
                        destination=str(preferred_out),
                    )
                except Exception as migrate_error:  # pragma: no cover - defensive logging
                    logger.bind(project_id=project_id).warning(
                        f"Failed to migrate legacy artifacts from {candidate}: {migrate_error}"
                    )
            _ensure_legacy_link(preferred_out, legacy_out)
            return preferred_out

    preferred_out.parent.mkdir(parents=True, exist_ok=True)
    preferred_out.mkdir(parents=True, exist_ok=True)
    _ensure_legacy_link(preferred_out, legacy_out)
    return preferred_out


def _get_overrides_file(project_id: str, settings: Settings) -> Path:
    output_dir = _resolve_output_dir(project_id, settings)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "manual_overrides.json"


def load_manual_overrides(
    project_id: str,
    settings: Settings | None = None,
) -> ManualOverrides:
    """Load manual overrides for a project (returns empty defaults if missing)."""

    settings = settings or get_settings()
    overrides_file = _get_overrides_file(project_id, settings)

    if not overrides_file.exists():
        return ManualOverrides()

    try:
        with open(overrides_file, "r") as f:
            data: dict[str, Any] = json.load(f)
        return ManualOverrides.model_validate(data)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.bind(project_id=project_id).warning(
            f"Failed to load manual overrides, returning defaults: {exc}"
        )
        return ManualOverrides()


def save_manual_overrides(
    project_id: str,
    update: ManualOverridesUpdate,
    settings: Settings | None = None,
) -> ManualOverrides:
    """Persist manual overrides, merging with existing values."""

    settings = settings or get_settings()
    overrides_file = _get_overrides_file(project_id, settings)

    current = load_manual_overrides(project_id, settings)
    update_payload = update.model_dump(exclude_unset=True)
    merged = current.model_dump()
    merged.update(update_payload)
    merged["updated_at"] = datetime.now(timezone.utc)

    updated = ManualOverrides.model_validate(merged)

    overrides_file.parent.mkdir(parents=True, exist_ok=True)
    overrides_file.write_text(updated.model_dump_json(indent=2))

    # Invalidate cached costing artifacts so pipeline recomputes with new overrides
    costing_file = overrides_file.parent / "costing_result.json"
    if costing_file.exists():
        try:
            costing_file.unlink()
            logger.bind(project_id=project_id).info(
                "Removed cached costing result after manual override update",
                costing_file=str(costing_file),
            )
        except Exception as cleanup_error:  # pragma: no cover - defensive logging
            logger.bind(project_id=project_id).warning(
                f"Failed to delete costing result after override update: {cleanup_error}"
            )

    # Reset Stage 4 run state so the next pipeline run recomputes costing
    try:
        run_state_store = RunStateStore(settings)
        run_state_store.update_stage_state(
            project_id,
            "stage_4_costing",
            status="pending",
            finished_at=None,
            error=None,
        )
    except Exception as state_error:  # pragma: no cover - defensive logging
        logger.bind(project_id=project_id).warning(
            f"Failed to reset run state after override update: {state_error}"
        )

    logger.bind(project_id=project_id).info(
        "Manual overrides updated", overrides=updated.sanitized()
    )
    return updated
