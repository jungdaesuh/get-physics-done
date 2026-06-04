"""Integration checks for shared staged workflow authority helpers."""

from __future__ import annotations

import json
from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
EXPECTED_SPLIT_WORKFLOWS = {
    "arxiv-submission",
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


def _declared_split_stage_authorities(workflow_id: str) -> tuple[Path, ...]:
    manifest_path = WORKFLOWS_DIR / f"{workflow_id}-stage-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    seen: set[Path] = set()
    paths: list[Path] = []
    for stage in payload.get("stages", []):
        for key in ("mode_paths", "loaded_authorities"):
            for authority in stage.get(key, []):
                if not authority.startswith(f"workflows/{workflow_id}/") or not authority.endswith(".md"):
                    continue
                path = WORKFLOWS_DIR.parent / authority
                if path.exists() and path not in seen:
                    seen.add(path)
                    paths.append(path)
    return tuple(paths)


def test_workflow_authority_text_includes_manifest_declared_split_stage_files() -> None:
    split_workflows: set[str] = set()

    for manifest_path in sorted(WORKFLOWS_DIR.glob("*-stage-manifest.json")):
        workflow_id = manifest_path.name.removesuffix("-stage-manifest.json")
        stage_authority_paths = _declared_split_stage_authorities(workflow_id)
        if not stage_authority_paths:
            continue

        split_workflows.add(workflow_id)
        authority_text = workflow_authority_text(WORKFLOWS_DIR, workflow_id)
        for path in stage_authority_paths:
            assert path.read_text(encoding="utf-8") in authority_text

    assert EXPECTED_SPLIT_WORKFLOWS <= split_workflows
