"""Root policy and workspace-classifier helpers for context assembly."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from gpd.core.constants import (
    ENV_GPD_ACTIVE_RUNTIME,
    PLANNING_DIR_NAME,
    RESEARCH_MAP_DIR_NAME,
)
from gpd.core.context_scan import _discover_research_file_samples
from gpd.core.manuscript_artifacts import resolve_current_manuscript_entrypoint
from gpd.core.project_reentry import recoverable_project_context
from gpd.core.root_resolution import (
    RootResolutionPolicy,
    resolve_project_roots,
    resolve_state_json_root,
)

__all__ = [
    "InitRootPolicy",
    "_detect_platform",
    "_path_exists",
    "_resolve_cwd_for_root_policy",
    "_resolve_project_scoped_cwd",
    "_resolve_workspace_locked_cwd",
    "_start_folder_state",
    "_workspace_start_classifier_context",
]


class InitRootPolicy(StrEnum):
    """High-level workspace/project policy for init payload assembly."""

    WORKSPACE_LOCKED = "workspace_locked"
    PROJECT_SCOPED = "project_scoped"
    PROJECT_REENTRY_ALLOWED = "project_reentry_allowed"
    CURRENT_WORKSPACE_ONLY = "current_workspace_only"


def _path_exists(cwd: Path, target: str) -> bool:
    """Check if a relative path exists under cwd."""
    return (cwd / target).exists()


def _new_project_init_progress_context(cwd: Path) -> dict[str, object]:
    """Return structured interrupted-initialization routing context."""

    relative_path = f"{PLANNING_DIR_NAME}/init-progress.json"
    progress_path = cwd / relative_path
    result: dict[str, object] = {
        "init_progress_exists": progress_path.exists(),
        "init_progress_status": "absent",
        "init_progress_valid": False,
        "init_progress_corrupt": False,
        "init_progress_step": None,
        "init_progress_description": None,
        "init_progress_path": relative_path,
    }
    if not progress_path.exists():
        return result

    try:
        raw = progress_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        result["init_progress_status"] = "corrupt_init_progress"
        result["init_progress_corrupt"] = True
        return result

    if not isinstance(payload, Mapping):
        result["init_progress_status"] = "corrupt_init_progress"
        result["init_progress_corrupt"] = True
        return result

    step = payload.get("step")
    description = payload.get("description")
    if isinstance(step, str):
        normalized_step = step.strip()
    elif isinstance(step, (int, float)) and not isinstance(step, bool):
        normalized_step = str(step)
    else:
        normalized_step = ""
    normalized_description = description.strip() if isinstance(description, str) else ""
    if not normalized_step:
        result["init_progress_status"] = "corrupt_init_progress"
        result["init_progress_corrupt"] = True
        return result

    result.update(
        {
            "init_progress_status": "interrupted_init_progress",
            "init_progress_valid": True,
            "init_progress_step": normalized_step,
            "init_progress_description": normalized_description,
        }
    )
    return result


def _detect_platform(cwd: Path | None = None) -> str:
    """Detect the active AI runtime, if any."""
    resolved_cwd = cwd or Path.cwd()
    resolved_home = Path.home()
    runtime_unknown = "unknown"
    try:
        import os

        from gpd.adapters.runtime_catalog import normalize_runtime_name
        from gpd.hooks.runtime_detect import RUNTIME_UNKNOWN, detect_runtime_for_gpd_use

        runtime_unknown = RUNTIME_UNKNOWN
        explicit_override = normalize_runtime_name(os.environ.get(ENV_GPD_ACTIVE_RUNTIME))
        if explicit_override:
            return explicit_override
        detected = detect_runtime_for_gpd_use(cwd=resolved_cwd, home=resolved_home)
        if isinstance(detected, str) and detected.strip():
            return detected
    except Exception:
        pass

    return runtime_unknown


def _workspace_start_classifier_context(cwd: Path) -> tuple[Path, Path, dict[str, object]]:
    """Return the read-only workspace classifier facts shared by start/new-project."""

    requested_cwd = cwd.expanduser().resolve(strict=False)
    project_cwd = _resolve_workspace_locked_cwd(requested_cwd)

    research_file_samples = _discover_research_file_samples(requested_cwd)
    has_research_files = bool(research_file_samples)
    has_research_map = _path_exists(project_cwd, f"{PLANNING_DIR_NAME}/{RESEARCH_MAP_DIR_NAME}")

    has_project_manifest = (
        _path_exists(requested_cwd, "requirements.txt")
        or _path_exists(requested_cwd, "pyproject.toml")
        or _path_exists(requested_cwd, "Makefile")
        or resolve_current_manuscript_entrypoint(requested_cwd) is not None
    )

    state_exists, roadmap_exists, project_file_exists = recoverable_project_context(project_cwd)
    recoverable_project_exists = state_exists or roadmap_exists or project_file_exists
    partial_project_exists = recoverable_project_exists and not project_file_exists
    if project_file_exists:
        project_recovery_status = "initialized"
    elif recoverable_project_exists:
        project_recovery_status = "partial"
    else:
        project_recovery_status = "none"

    return (
        requested_cwd,
        project_cwd,
        {
            "project_exists": project_file_exists,
            "state_exists": state_exists,
            "roadmap_exists": roadmap_exists,
            "recoverable_project_exists": recoverable_project_exists,
            "partial_project_exists": partial_project_exists,
            "project_recovery_status": project_recovery_status,
            **_new_project_init_progress_context(project_cwd),
            "has_research_map": has_research_map,
            "planning_exists": _path_exists(project_cwd, PLANNING_DIR_NAME),
            "has_research_files": has_research_files,
            "research_file_samples": research_file_samples,
            "has_project_manifest": has_project_manifest,
            "needs_research_map": (has_research_files or has_project_manifest) and not has_research_map,
            "has_git": _path_exists(project_cwd, ".git"),
            "platform": _detect_platform(project_cwd),
        },
    )


def _start_folder_state(classifier: Mapping[str, object]) -> str:
    """Return the normalized start-router state for a classifier payload."""

    if classifier.get("project_exists") is True:
        return "initialized_project"
    if classifier.get("partial_project_exists") is True or classifier.get("init_progress_exists") is True:
        return "partial_project"
    if classifier.get("has_research_map") is True:
        return "research_map"
    if classifier.get("needs_research_map") is True:
        return "existing_research"
    return "fresh"


def _resolve_project_scoped_cwd(cwd: Path) -> Path:
    """Return the nearest verified current-workspace project root, else the normalized cwd."""

    return _resolve_cwd_for_root_policy(cwd, policy=RootResolutionPolicy.PROJECT_SCOPED)


def _resolve_workspace_locked_cwd(cwd: Path) -> Path:
    """Return the requested workspace unless it is itself a verified GPD root."""

    return _resolve_cwd_for_root_policy(cwd, policy=RootResolutionPolicy.WORKSPACE_LOCKED)


def _resolve_cwd_for_root_policy(cwd: Path, *, policy: RootResolutionPolicy) -> Path:
    """Resolve *cwd* according to one explicit root policy."""

    requested_cwd = cwd.expanduser().resolve(strict=False)
    resolution = resolve_project_roots(requested_cwd, policy=policy)
    if resolution is None:
        return requested_cwd
    if resolution.has_project_layout:
        return resolution.project_root
    if policy == RootResolutionPolicy.PROJECT_SCOPED:
        state_root = resolve_state_json_root(requested_cwd, policy=policy)
        if state_root is not None:
            return state_root
    return requested_cwd
