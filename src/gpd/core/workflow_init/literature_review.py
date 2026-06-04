"""Literature-review workflow init builder."""

from __future__ import annotations

from pathlib import Path

from gpd.core import workflow_staging
from gpd.core.constants import PLANNING_DIR_NAME, PROJECT_FILENAME, ROADMAP_FILENAME
from gpd.core.context_roots import InitRootPolicy
from gpd.core.staged_context_fields import (
    EXECUTE_PHASE_CONTRACT_GATE_FIELDS,
    STAGED_FULL_REFERENCE_RUNTIME_FIELDS,
    STAGED_REFERENCE_SUMMARY_FIELDS,
)
from gpd.core.staged_init_assembly import assemble_staged_init_payload
from gpd.core.utils import generate_slug
from gpd.core.workflow_init.dependencies import WorkflowInitDependencies
from gpd.core.workflow_init.providers import staged_reference_provider


def init_literature_review(
    cwd: Path,
    topic: str | None = None,
    stage: str | None = None,
    *,
    deps: WorkflowInitDependencies,
) -> dict:
    """Assemble context for literature review orchestration."""
    requested_cwd = cwd.expanduser().resolve(strict=False)
    effective_cwd = deps.resolve_project_scoped_cwd(requested_cwd)
    config = deps.load_config(effective_cwd)
    normalized_topic = topic.strip() if isinstance(topic, str) and topic.strip() else None
    slug = _generate_slug(normalized_topic)
    if normalized_topic and slug is None:
        slug = "literature-review"
    if slug:
        slug = slug[:40]

    result: dict[str, object] = {
        "topic": normalized_topic,
        "slug": slug,
        "init_root_policy": InitRootPolicy.PROJECT_SCOPED.value,
        "workspace_root": requested_cwd.as_posix(),
        "project_root": effective_cwd.as_posix(),
        "commit_docs": config["commit_docs"],
        "state_exists": deps.state_exists(effective_cwd),
        "project_exists": deps.path_exists(effective_cwd, f"{PLANNING_DIR_NAME}/{PROJECT_FILENAME}"),
        "research_mode": config["research_mode"],
        "autonomy": config["autonomy"],
        "roadmap_exists": deps.path_exists(effective_cwd, f"{PLANNING_DIR_NAME}/{ROADMAP_FILENAME}"),
        "platform": deps.detect_platform(effective_cwd),
    }
    if stage is None:
        result.update(deps.build_reference_runtime_context(effective_cwd))
        return result

    manifest = workflow_staging.load_workflow_stage_manifest("literature-review")

    return assemble_staged_init_payload(
        workflow_id="literature-review",
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


def _generate_slug(text: str | None) -> str | None:
    if not text:
        return None
    return generate_slug(text)


__all__ = [
    "init_literature_review",
]
