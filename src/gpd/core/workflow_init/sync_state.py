"""Sync-state workflow init builder."""

from __future__ import annotations

from pathlib import Path

from gpd.core import workflow_staging
from gpd.core.constants import PLANNING_DIR_NAME, STATE_JSON_BACKUP_FILENAME, STATE_MD_FILENAME
from gpd.core.context_roots import InitRootPolicy
from gpd.core.context_staged_providers import build_selected_file_context, file_context_provider
from gpd.core.staged_context_fields import (
    PROJECT_CONTRACT_GATE_FIELDS,
    SYNC_STATE_FILE_CONTENT_FIELDS,
    SYNC_STATE_STRUCTURED_STATE_FIELDS,
)
from gpd.core.staged_init_assembly import assemble_staged_init_payload
from gpd.core.workflow_init.dependencies import WorkflowInitDependencies
from gpd.core.workflow_init.providers import staged_contract_provider, staged_structured_state_provider

_SYNC_STATE_FILE_CONTEXT_PATHS = {
    "state_md_content": f"{PLANNING_DIR_NAME}/{STATE_MD_FILENAME}",
    "state_json_content": f"{PLANNING_DIR_NAME}/state.json",
    "state_json_backup_content": f"{PLANNING_DIR_NAME}/{STATE_JSON_BACKUP_FILENAME}",
}


def init_sync_state(cwd: Path, *, stage: str | None = None, deps: WorkflowInitDependencies) -> dict:
    """Assemble context for state reconciliation."""
    requested_cwd = cwd.expanduser().resolve(strict=False)
    effective_cwd = deps.resolve_project_scoped_cwd(requested_cwd)
    sync_state_reentry_guidance = (
        "sync-state is current-workspace-only because it can mutate state files. "
        "It will not inspect or repair a recent project from another folder; open the target project folder "
        "or pass --cwd to that project before rerunning sync-state."
    )

    base_result = {
        "workspace_root": requested_cwd.as_posix(),
        "project_root": effective_cwd.as_posix(),
        "project_root_source": "current_workspace",
        "project_root_auto_selected": False,
        "init_root_policy": InitRootPolicy.CURRENT_WORKSPACE_ONLY.value,
        "project_reentry_mode": "current-workspace",
        "project_reentry_guidance": sync_state_reentry_guidance,
        "state_md_exists": deps.path_exists(effective_cwd, f"{PLANNING_DIR_NAME}/{STATE_MD_FILENAME}"),
        "state_json_exists": deps.path_exists(effective_cwd, f"{PLANNING_DIR_NAME}/state.json"),
        "state_json_backup_exists": deps.path_exists(
            effective_cwd,
            f"{PLANNING_DIR_NAME}/{STATE_JSON_BACKUP_FILENAME}",
        ),
        "state_recovery_guidance": deps.backup_only_state_guidance(effective_cwd),
        "platform": deps.detect_platform(effective_cwd),
    }

    if stage is None:
        result = dict(base_result)
        result.update(deps.build_structured_state_runtime_context(effective_cwd))
        result.update(deps.build_new_project_contract_runtime_context(effective_cwd))
        result.update(
            build_selected_file_context(
                effective_cwd,
                SYNC_STATE_FILE_CONTENT_FIELDS,
                _SYNC_STATE_FILE_CONTEXT_PATHS,
                deps.read_file_truncated,
            )
        )
        return result

    manifest = workflow_staging.load_workflow_stage_manifest("sync-state")

    return assemble_staged_init_payload(
        workflow_id="sync-state",
        stage_id=stage,
        cwd=effective_cwd,
        base_payload=base_result,
        manifest=manifest,
        providers=(
            staged_structured_state_provider(effective_cwd, SYNC_STATE_STRUCTURED_STATE_FIELDS, deps),
            staged_contract_provider(effective_cwd, PROJECT_CONTRACT_GATE_FIELDS, deps),
            file_context_provider(
                SYNC_STATE_FILE_CONTENT_FIELDS,
                cwd=effective_cwd,
                field_paths=_SYNC_STATE_FILE_CONTEXT_PATHS,
                read_file=deps.read_file_truncated,
            ),
        ),
    )


__all__ = [
    "init_sync_state",
]
