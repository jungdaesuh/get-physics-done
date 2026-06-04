"""Map-research workflow init builder."""

from __future__ import annotations

from pathlib import Path

from gpd.core import workflow_staging
from gpd.core.constants import PLANNING_DIR_NAME, RESEARCH_MAP_DIR_NAME
from gpd.core.context_roots import InitRootPolicy
from gpd.core.staged_context_fields import (
    EXECUTE_PHASE_CONTRACT_GATE_FIELDS,
    STAGED_FULL_REFERENCE_RUNTIME_FIELDS,
    STAGED_REFERENCE_SUMMARY_FIELDS,
)
from gpd.core.staged_init_assembly import assemble_staged_init_payload
from gpd.core.workflow_init.dependencies import WorkflowInitDependencies
from gpd.core.workflow_init.providers import staged_reference_provider


def init_map_research(
    cwd: Path,
    focus: str | None = None,
    stage: str | None = None,
    *,
    deps: WorkflowInitDependencies,
) -> dict:
    """Assemble context for research mapping."""
    requested_cwd = cwd.expanduser().resolve(strict=False)
    effective_cwd = deps.resolve_project_scoped_cwd(requested_cwd)
    config = deps.load_config(effective_cwd)
    normalized_focus = focus.strip() if isinstance(focus, str) and focus.strip() else ""

    research_map_dir = effective_cwd / PLANNING_DIR_NAME / RESEARCH_MAP_DIR_NAME
    research_map_dir_absolute = research_map_dir.resolve(strict=False).as_posix()
    existing_maps: list[str] = []
    try:
        existing_maps = sorted(f.name for f in research_map_dir.iterdir() if f.is_file() and f.name.endswith(".md"))
    except FileNotFoundError:
        pass

    result = {
        "mapper_model": deps.resolve_model(effective_cwd, "gpd-research-mapper", config),
        "init_root_policy": InitRootPolicy.PROJECT_SCOPED.value,
        "workspace_root": requested_cwd.as_posix(),
        "project_root": effective_cwd.as_posix(),
        "project_root_source": "workspace",
        "project_root_auto_selected": False,
        "commit_docs": config["commit_docs"],
        "autonomy": config["autonomy"],
        "research_mode": config["research_mode"],
        "map_focus": normalized_focus,
        "map_focus_provided": bool(normalized_focus),
        "parallelization": config["parallelization"],
        "research_map_dir": f"{PLANNING_DIR_NAME}/{RESEARCH_MAP_DIR_NAME}",
        "research_map_dir_absolute": research_map_dir_absolute,
        "existing_maps": existing_maps,
        "has_maps": len(existing_maps) > 0,
        "planning_exists": deps.path_exists(effective_cwd, PLANNING_DIR_NAME),
        "research_map_dir_exists": deps.path_exists(effective_cwd, f"{PLANNING_DIR_NAME}/{RESEARCH_MAP_DIR_NAME}"),
        "platform": deps.detect_platform(effective_cwd),
    }
    if stage is None:
        result.update(deps.build_reference_runtime_context(effective_cwd))
        return result

    manifest = workflow_staging.load_workflow_stage_manifest("map-research")

    return assemble_staged_init_payload(
        workflow_id="map-research",
        stage_id=stage,
        cwd=effective_cwd,
        base_payload=result,
        manifest=manifest,
        providers=(
            staged_reference_provider(
                effective_cwd,
                STAGED_FULL_REFERENCE_RUNTIME_FIELDS | STAGED_REFERENCE_SUMMARY_FIELDS,
                EXECUTE_PHASE_CONTRACT_GATE_FIELDS,
                deps,
            ),
        ),
    )


__all__ = [
    "init_map_research",
]
