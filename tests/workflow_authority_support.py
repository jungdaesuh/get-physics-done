"""Helpers for tests that need staged workflow authority text."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes

STAGED_WORKFLOW_AUTHORITY_NAMES = {
    "arxiv-submission",
    "autonomous",
    "execute-phase",
    "literature-review",
    "map-research",
    "new-milestone",
    "new-project",
    "peer-review",
    "plan-phase",
    "quick",
    "research-phase",
    "respond-to-referees",
    "resume-work",
    "sync-state",
    "verify-work",
    "write-paper",
}


def workflow_authority_text(workflows_dir: Path, name: str) -> str:
    """Return root workflow text plus split stage authorities when present."""

    return "\n\n".join(path.read_text(encoding="utf-8") for path in workflow_authority_paths(workflows_dir, name))


def workflow_authority_paths(workflows_dir: Path, name: str) -> tuple[Path, ...]:
    """Return root workflow path plus split stage authority paths when present."""

    workflow_name = name.removesuffix(".md")
    root = workflows_dir / f"{workflow_name}.md"
    paths = [root]
    if _uses_split_stage_authorities(workflows_dir, workflow_name):
        paths.extend(_ordered_stage_authority_paths(workflows_dir, workflow_name))
    return tuple(paths)


def _uses_split_stage_authorities(workflows_dir: Path, workflow_name: str) -> bool:
    """Return whether tests should aggregate split stage authority files."""

    stage_dir = workflows_dir / workflow_name
    if not stage_dir.is_dir():
        return False
    if workflow_name in STAGED_WORKFLOW_AUTHORITY_NAMES:
        return True
    return bool(_manifest_declared_stage_authority_paths(workflows_dir, workflow_name))


def _ordered_stage_authority_paths(workflows_dir: Path, workflow_name: str) -> tuple[Path, ...]:
    """Return staged workflow authority files in manifest order."""

    ordered = _manifest_declared_stage_authority_paths(workflows_dir, workflow_name)
    if ordered:
        return ordered
    return tuple(sorted((workflows_dir / workflow_name).glob("*.md")))


def _manifest_declared_stage_authority_paths(workflows_dir: Path, workflow_name: str) -> tuple[Path, ...]:
    """Return split workflow authority files declared by the stage manifest."""

    manifest_path = workflows_dir / f"{workflow_name}-stage-manifest.json"
    seen: set[Path] = set()
    ordered: list[Path] = []

    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        stages = payload.get("stages", [])
        if isinstance(stages, list):
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                for key in ("mode_paths", "loaded_authorities"):
                    values = stage.get(key, [])
                    if not isinstance(values, list):
                        continue
                    for value in values:
                        _append_declared_workflow_authority(
                            value,
                            workflows_dir=workflows_dir,
                            workflow_name=workflow_name,
                            seen=seen,
                            ordered=ordered,
                        )
                conditionals = stage.get("conditional_authorities", [])
                if not isinstance(conditionals, list):
                    continue
                for conditional in conditionals:
                    if not isinstance(conditional, dict):
                        continue
                    values = conditional.get("authorities", [])
                    if not isinstance(values, list):
                        continue
                    for value in values:
                        _append_declared_workflow_authority(
                            value,
                            workflows_dir=workflows_dir,
                            workflow_name=workflow_name,
                            seen=seen,
                            ordered=ordered,
                        )

    return tuple(ordered)


def _append_declared_workflow_authority(
    value: object,
    *,
    workflows_dir: Path,
    workflow_name: str,
    seen: set[Path],
    ordered: list[Path],
) -> None:
    if not isinstance(value, str):
        return
    if not value.startswith(f"workflows/{workflow_name}/") or not value.endswith(".md"):
        return
    path = workflows_dir.parent / value
    if path.exists() and path not in seen:
        seen.add(path)
        ordered.append(path)


def expanded_workflow_authority_text(
    workflows_dir: Path,
    name: str,
    *,
    src_root: Path,
    path_prefix: str,
    runtime: str | None = None,
) -> str:
    """Expand includes across a workflow's root plus staged authority files."""

    return expand_at_includes(
        workflow_authority_text(workflows_dir, name),
        src_root,
        path_prefix,
        runtime=runtime,
    )
