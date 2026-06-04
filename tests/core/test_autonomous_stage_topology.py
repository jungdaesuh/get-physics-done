"""Autonomous staged workflow topology and scaffold budgets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpd.core.context import init_autonomous
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.prompt_metrics_support import measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
COMMANDS_DIR = SOURCE_ROOT / "commands"
WORKFLOWS_DIR = SOURCE_ROOT / "specs" / "workflows"
PATH_PREFIX = "/runtime/"

AUTONOMOUS_STAGE_IDS = (
    "initialize_discover",
    "phase_route",
    "discuss_delegate",
    "plan_execute_child_cycle",
    "verification_route",
    "gap_route",
    "convention_lifecycle_closeout",
    "blocked_recovery",
)
AUTONOMOUS_STAGE_AUTHORITY_BY_ID = {
    "initialize_discover": "workflows/autonomous/initialize-discover.md",
    "phase_route": "workflows/autonomous/phase-route.md",
    "discuss_delegate": "workflows/autonomous/discuss-delegate.md",
    "plan_execute_child_cycle": "workflows/autonomous/plan-execute-child-cycle.md",
    "verification_route": "workflows/autonomous/verification-route.md",
    "gap_route": "workflows/autonomous/gap-route.md",
    "convention_lifecycle_closeout": "workflows/autonomous/convention-lifecycle-closeout.md",
    "blocked_recovery": "workflows/autonomous/blocked-recovery.md",
}


def _write_autonomous_project(root: Path) -> None:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / "01-first"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (gpd_dir / "config.json").write_text("{}", encoding="utf-8")
    (gpd_dir / "state.json").write_text(json.dumps({}), encoding="utf-8")
    (gpd_dir / "STATE.md").write_text("# State\n", encoding="utf-8")
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n"
        "## Milestone v1.0: Test Milestone\n\n"
        "## Phase 1: First\n"
        "**Goal:** Establish the first result.\n\n"
        "## Phase 2: Second\n"
        "**Goal:** Continue from the second phase.\n",
        encoding="utf-8",
    )


def test_autonomous_stage_manifest_declares_forward_only_scaffold() -> None:
    manifest = load_workflow_stage_manifest("autonomous")

    assert manifest.stage_ids() == AUTONOMOUS_STAGE_IDS
    assert manifest.stage("initialize_discover").next_stages == (
        "phase_route",
        "convention_lifecycle_closeout",
    )
    assert manifest.stage("plan_execute_child_cycle").next_stages == (
        "verification_route",
        "blocked_recovery",
    )
    assert manifest.stage("blocked_recovery").next_stages == ()

    for stage in manifest.stages:
        expected_authority = AUTONOMOUS_STAGE_AUTHORITY_BY_ID[stage.id]
        assert stage.mode_paths == (expected_authority,)
        assert stage.loaded_authorities == (expected_authority,)
        assert stage.writes_allowed == ()
        assert "workflows/autonomous.md" not in stage.eager_authorities()
        assert "workflows/autonomous.md" in stage.must_not_eager_load
        assert expected_authority not in stage.must_not_eager_load


def test_autonomous_command_and_root_use_first_stage_index_shape() -> None:
    command_text = (COMMANDS_DIR / "autonomous.md").read_text(encoding="utf-8")
    root_text = (WORKFLOWS_DIR / "autonomous.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/autonomous/initialize-discover.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/autonomous.md" not in command_text
    assert "Compatibility index for the staged `autonomous` workflow." in root_text
    assert "Do not load this index as a stage authority." in root_text
    for stage_id, authority in AUTONOMOUS_STAGE_AUTHORITY_BY_ID.items():
        assert f"`{stage_id}`" in root_text
        assert authority in root_text
    for stage_owned_fragment in (
        "lifecycle-contract-gate",
        "gpd validate plan-contract",
        "gpd --raw init verify-work",
        "Bounded checkpoint stop override",
        "Post-Execution Verification Routing",
    ):
        assert stage_owned_fragment not in root_text
    assert "Smart Discuss" not in root_text


def test_autonomous_scaffold_prompt_budgets_are_small() -> None:
    command_metrics = measure_prompt_surface(
        COMMANDS_DIR / "autonomous.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    root_metrics = measure_prompt_surface(
        WORKFLOWS_DIR / "autonomous.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert command_metrics.raw_include_count == 1
    assert command_metrics.expanded_char_count < 4_000
    assert root_metrics.expanded_char_count < 2_500


def test_init_autonomous_stage_payload_matches_manifest_and_from_phase(tmp_path: Path) -> None:
    _write_autonomous_project(tmp_path)
    manifest = load_workflow_stage_manifest("autonomous")

    payload = init_autonomous(tmp_path, stage="phase_route", from_phase="2")

    assert payload["autonomous_from_phase"] == "2"
    assert payload["autonomous_current_phase_number"] == "2"
    assert payload["phase_number"] == "2"
    assert payload["phase_found"] is False
    assert payload["staged_loading"] == manifest.staged_loading_payload("phase_route")
    assert (
        tuple(field for field in payload if field != "staged_loading")
        == manifest.stage("phase_route").required_init_fields
    )


def test_init_autonomous_rejects_unknown_stage_with_allowed_values(tmp_path: Path) -> None:
    _write_autonomous_project(tmp_path)

    with pytest.raises(ValueError, match="Unknown autonomous stage 'bogus'. Allowed values:"):
        init_autonomous(tmp_path, stage="bogus")
