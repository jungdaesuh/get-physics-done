"""Quick workflow init builder."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from gpd.core import workflow_staging
from gpd.core.constants import PLANNING_DIR_NAME, PROJECT_FILENAME, ROADMAP_FILENAME
from gpd.core.staged_context_fields import QUICK_CONTRACT_GATE_FIELDS, QUICK_REFERENCE_RUNTIME_FIELDS
from gpd.core.staged_init_assembly import assemble_staged_init_payload
from gpd.core.utils import generate_slug
from gpd.core.workflow_init.dependencies import WorkflowInitDependencies
from gpd.core.workflow_init.providers import staged_reference_provider


def init_quick(
    cwd: Path,
    description: str | None = None,
    stage: str | None = None,
    *,
    deps: WorkflowInitDependencies,
) -> dict:
    """Assemble context for quick task execution."""
    config = deps.load_config(cwd)
    now = datetime.now(UTC)
    normalized_description = description.strip() if isinstance(description, str) else description
    slug = _generate_slug(normalized_description)
    if normalized_description and slug is None:
        slug = "task"
    if slug:
        slug = slug[:40]

    quick_dir = cwd / PLANNING_DIR_NAME / "quick"
    next_num = 1
    try:
        existing = []
        for entry in quick_dir.iterdir():
            match = re.match(r"^(\d+)-", entry.name)
            if match:
                existing.append(int(match.group(1)))
        if existing:
            next_num = max(existing) + 1
    except (FileNotFoundError, PermissionError):
        pass

    result = {
        "planner_model": deps.resolve_model(cwd, "gpd-planner", config),
        "executor_model": deps.resolve_model(cwd, "gpd-executor", config),
        "commit_docs": config["commit_docs"],
        "autonomy": config["autonomy"],
        "research_mode": config["research_mode"],
        "next_num": next_num,
        "slug": slug,
        "description": normalized_description,
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.isoformat(),
        "quick_dir": f"{PLANNING_DIR_NAME}/quick",
        "task_dir": f"{PLANNING_DIR_NAME}/quick/{next_num}-{slug}" if slug else None,
        "roadmap_exists": deps.path_exists(cwd, f"{PLANNING_DIR_NAME}/{ROADMAP_FILENAME}"),
        "project_exists": deps.path_exists(cwd, f"{PLANNING_DIR_NAME}/{PROJECT_FILENAME}"),
        "planning_exists": deps.path_exists(cwd, PLANNING_DIR_NAME),
        "platform": deps.detect_platform(cwd),
    }

    if stage is None:
        result.update(deps.build_reference_runtime_context(cwd))
        result.update(deps.build_state_memory_runtime_context(cwd))
        return result

    if not result["project_exists"]:
        raise ValueError(
            "quick staged init requires an initialized GPD project (GPD/PROJECT.md); "
            "run command-context validation before loading staged quick authoring context"
        )

    manifest = workflow_staging.load_workflow_stage_manifest("quick")

    return assemble_staged_init_payload(
        workflow_id="quick",
        stage_id=stage,
        cwd=cwd,
        base_payload=result,
        manifest=manifest,
        providers=(staged_reference_provider(cwd, QUICK_REFERENCE_RUNTIME_FIELDS, QUICK_CONTRACT_GATE_FIELDS, deps),),
    )


def _generate_slug(text: str | None) -> str | None:
    if not text:
        return None
    return generate_slug(text)


__all__ = [
    "init_quick",
]
