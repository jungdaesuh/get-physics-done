"""Group-expansion contracts for formerly long explicit workflow manifests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpd.core.workflow_staging import load_workflow_stage_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
GROUPED_LONG_MANIFEST_WORKFLOWS = ("new-project", "resume-work", "sync-state")


def _raw_manifest(workflow_id: str) -> dict[str, object]:
    path = WORKFLOWS_DIR / f"{workflow_id}-stage-manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _expanded_group_fields(
    *,
    groups: dict[str, list[str]],
    raw_stage: dict[str, object],
) -> tuple[str, ...]:
    fields: list[str] = []
    for group_name in raw_stage["required_init_field_groups"]:
        assert isinstance(group_name, str)
        fields.extend(groups[group_name])
    for field_name in raw_stage.get("required_init_fields", []):
        assert isinstance(field_name, str)
        fields.append(field_name)
    return tuple(fields)


@pytest.mark.parametrize("workflow_id", GROUPED_LONG_MANIFEST_WORKFLOWS)
def test_long_manifest_stages_are_group_backed_and_expand_in_order(workflow_id: str) -> None:
    payload = _raw_manifest(workflow_id)
    groups = payload["required_init_field_groups"]
    raw_stages = payload["stages"]
    assert isinstance(groups, dict)
    assert groups
    assert isinstance(raw_stages, list)

    manifest = load_workflow_stage_manifest(workflow_id)
    for raw_stage in raw_stages:
        assert isinstance(raw_stage, dict)
        assert "required_init_field_groups" in raw_stage
        assert raw_stage["required_init_field_groups"]
        assert "required_init_fields" not in raw_stage
        assert manifest.stage(str(raw_stage["id"])).required_init_fields == _expanded_group_fields(
            groups=groups,
            raw_stage=raw_stage,
        )
