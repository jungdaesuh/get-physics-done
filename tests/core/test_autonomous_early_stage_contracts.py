"""Focused contracts for the early staged autonomous workflow authorities."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AUTONOMOUS_STAGE_DIR = WORKFLOWS_DIR / "autonomous"
AUTONOMOUS_STAGE_MANIFEST = WORKFLOWS_DIR / "autonomous-stage-manifest.json"

EARLY_STAGE_FILES = {
    "initialize_discover": "initialize-discover.md",
    "phase_route": "phase-route.md",
    "discuss_delegate": "discuss-delegate.md",
}


def _stage_text(stage_id: str) -> str:
    return (AUTONOMOUS_STAGE_DIR / EARLY_STAGE_FILES[stage_id]).read_text(encoding="utf-8")


def _combined_early_stage_text() -> str:
    return "\n\n".join(_stage_text(stage_id) for stage_id in EARLY_STAGE_FILES)


def _assert_contains_all(text: str, fragments: tuple[str, ...]) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    assert missing == []


def _assert_contains_none(text: str, fragments: tuple[str, ...]) -> None:
    unexpected = [fragment for fragment in fragments if fragment in text]
    assert unexpected == []


def test_autonomous_early_stage_files_declare_target_stage_ids() -> None:
    for stage_id, filename in EARLY_STAGE_FILES.items():
        path = AUTONOMOUS_STAGE_DIR / filename

        assert path.exists(), f"missing autonomous stage file: {filename}"
        assert f'<stage id="{stage_id}">' in path.read_text(encoding="utf-8")


def test_initialize_discover_keeps_roadmap_discovery_and_child_delegation() -> None:
    text = _stage_text("initialize_discover")

    _assert_contains_all(
        text,
        (
            "Autonomous mode is an orchestrator, not a Markdown status parser.",
            "gpd --raw init autonomous --stage initialize_discover",
            "gpd --raw roadmap analyze",
            "--from",
            "gpd --raw roadmap get-phase ${PHASE_NUM}",
            "gpd --raw init verify-work",
            "verification_report_status",
            "gpd:discuss-phase",
            "gpd:plan-phase",
            "gpd:execute-phase",
            "gpd:verify-work",
            "gpd:write-paper",
            "gpd:validate-conventions",
            "gpd:audit-milestone",
            "gpd:complete-milestone",
        ),
    )

    _assert_contains_none(
        _combined_early_stage_text(),
        (
            "VERIFY_STATUS=$(grep",
            "AUDIT_STATUS=$(grep",
            'grep "^status:"',
            'grep -iE "^status:"',
            "Read the human_verification section from VERIFICATION.md",
            "Read gap summary from VERIFICATION.md",
        ),
    )


def test_phase_route_preserves_paper_workflow_choice_and_context_route() -> None:
    text = _stage_text("phase_route")

    _assert_contains_all(
        text,
        (
            '<stage id="phase_route">',
            "gpd --raw init autonomous --stage phase_route",
            "gpd --raw roadmap get-phase ${PHASE_NUM}",
            "pure paper-writing phases",
            "Use gpd:write-paper",
            "Use normal discuss->plan->execute",
            "`gpd:write-paper` with structured arguments `{phase: PHASE_NUM}`",
            "derivation/computation indicator",
            "PHASE_STATE=$(gpd --raw init phase-op ${PHASE_NUM})",
            "route to `discuss_delegate`",
            "route to `plan_execute_child_cycle`",
        ),
    )

    _assert_contains_none(
        text,
        (
            "Invoke the runtime-installed `gpd:plan-phase` child command",
            "Invoke the runtime-installed `gpd:execute-phase` child command",
            "Invoke the runtime-installed `gpd:verify-work` child command",
            "write `*-CONTEXT.md`",
        ),
    )


def test_discuss_delegate_uses_discuss_phase_without_cloning_smart_discuss() -> None:
    text = _stage_text("discuss_delegate")

    _assert_contains_all(
        text,
        (
            '<stage id="discuss_delegate">',
            "gpd --raw init autonomous --stage discuss_delegate",
            "`gpd:discuss-phase` with structured arguments `{phase: PHASE_NUM, auto: true}`",
            "gpd:discuss-phase ${PHASE_NUM} --auto",
            "PHASE_STATE=$(gpd --raw init phase-op ${PHASE_NUM})",
            "has_context",
            "route to `plan_execute_child_cycle`",
        ),
    )

    _assert_contains_none(
        text,
        (
            "Generate 3-4 gray areas",
            "Use exactly this structure",
            'gpd commit "docs(',
            'find GPD/phases -name "*-CONTEXT.md"',
            "all 9 sections",
            "<prior_decisions>",
            "CONTEXT.md following the same template",
        ),
    )


def test_autonomous_manifest_matches_owned_early_stage_files_when_present() -> None:
    if not AUTONOMOUS_STAGE_MANIFEST.exists():
        pytest.skip("Worker 1 owns autonomous-stage-manifest.json")

    payload = json.loads(AUTONOMOUS_STAGE_MANIFEST.read_text(encoding="utf-8"))
    stages = {stage["id"]: stage for stage in payload["stages"]}

    for stage_id, filename in EARLY_STAGE_FILES.items():
        assert stage_id in stages
        expected_authority = f"workflows/autonomous/{filename}"
        stage = stages[stage_id]
        assert expected_authority in stage["mode_paths"]
        assert expected_authority in stage["loaded_authorities"]
