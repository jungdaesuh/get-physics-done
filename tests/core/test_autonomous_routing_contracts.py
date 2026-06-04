"""Contracts for split autonomous routing stages."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.runtime_catalog import iter_runtime_descriptors

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTONOMOUS_STAGE_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "autonomous"

LATE_STAGE_FILES = (
    "plan-execute-child-cycle.md",
    "verification-route.md",
    "gap-route.md",
    "convention-lifecycle-closeout.md",
    "blocked-recovery.md",
)


def _stage(name: str) -> str:
    return (AUTONOMOUS_STAGE_DIR / name).read_text(encoding="utf-8")


def _late_stage_text() -> str:
    return "\n\n".join(_stage(name) for name in LATE_STAGE_FILES)


def _extract_step(text: str, step_name: str) -> str:
    pattern = rf'<step name="{re.escape(step_name)}">(?P<body>.*?)</step>'
    match = re.search(pattern, text, flags=re.DOTALL)
    assert match is not None, f"missing step {step_name!r}"
    return match.group("body")


def test_autonomous_late_stage_files_are_present_and_concise() -> None:
    for name in LATE_STAGE_FILES:
        text = _stage(name)
        assert f"Stage id: `{name.removesuffix('.md').replace('-', '_')}`" in text
        assert len(text.splitlines()) < 145


def test_plan_execute_delegates_and_preserves_closeout_ownership() -> None:
    stage = _stage("plan-execute-child-cycle.md")

    assert "gpd --raw validate lifecycle-contract-gate plan-phase" in stage
    assert "gpd --raw validate lifecycle-contract-gate execute-phase" in stage
    assert "gpd:plan-phase" in stage
    assert "gpd:execute-phase" in stage
    assert "execute-phase` owns its normal phase transition / closeout path" in stage
    assert "must not duplicate closeout" in stage
    assert "gpd phase complete" not in stage

    bounded_stop = _extract_step(stage, "bounded_checkpoint_stop")
    assert "do not invoke verification" in bounded_stop
    assert "convention checks" in bounded_stop
    assert "milestone audit" in bounded_stop
    assert "another phase" in bounded_stop
    assert "gpd:resume-work" in bounded_stop


def test_verification_route_uses_verify_work_session_router_and_fails_closed() -> None:
    stage = _stage("verification-route.md")

    assert "gpd:verify-work" in stage
    assert 'gpd --raw init verify-work "${PHASE_NUM}" --stage session_router' in stage
    assert "gpd_return.status" in stage
    assert "verification_report_status" in stage
    assert "verification_report_status_payload" in stage
    assert "missing_status" in stage
    assert "unparseable" in stage
    assert "unknown_status" in stage
    assert "prose-only" in stage
    assert "non-mutating" in stage

    for status in ("passed", "human_needed", "expert_needed", "gaps_found"):
        assert f"`{status}`" in stage


def test_gap_route_is_one_retry_and_rechecks_fresh_verification_status() -> None:
    stage = _stage("gap-route.md")

    assert "gap_retry_count" in stage
    assert "gap_retry_count >= 1" in stage
    assert "Do not start another autonomous gap attempt" in stage
    assert 'gpd:plan-phase` child command with structured arguments `{phase: PHASE_NUM, mode: "gaps"}`' in stage
    assert 'gpd:execute-phase` child command with structured arguments `{phase: PHASE_NUM, mode: "gaps_only"}`' in stage
    assert "gpd:verify-work" in stage
    assert 'gpd --raw init verify-work "${PHASE_NUM}" --stage session_router' in stage
    assert "Do not reuse an earlier verification payload" in stage
    assert "Do not read report prose" in stage


def test_convention_and_lifecycle_route_through_child_commands() -> None:
    stage = _stage("convention-lifecycle-closeout.md")

    assert "gpd:validate-conventions" in stage
    assert "gpd --raw roadmap analyze" in stage
    assert 'gpd --raw init verify-work "${COMPLETE_PHASE}" --stage session_router' in stage
    assert "Every completed phase must report `passed`" in stage
    assert "gpd:audit-milestone" in stage
    assert "gpd:plan-milestone-gaps" in stage
    assert "gpd:complete-milestone" in stage
    assert "Audit markdown is not a routing source" in stage
    assert "Do not run archive verification as a local substitute" in stage


def test_blocked_recovery_renders_one_public_primary_command() -> None:
    stage = _stage("blocked-recovery.md")
    render = _extract_step(stage, "render_stage_stop")

    assert "next_runtime_command" in render
    assert "exactly one primary next runtime command" in render
    assert len(re.findall(r"(?m)^Primary:", render)) == 1
    assert "gpd --raw init" not in render
    assert "field-access" not in render
    assert "gpd:suggest-next" in render


def test_autonomous_late_stages_do_not_use_markdown_status_readers() -> None:
    text = _late_stage_text()
    forbidden_fragments = (
        "VERIFY_STATUS=$(grep",
        "AUDIT_STATUS=$(grep",
        'grep "^status:"',
        'grep -iE "^status:"',
        "Read the human_verification section from VERIFICATION.md",
        "Read gap summary from VERIFICATION.md",
        "Read the gaps summary from the audit file",
        "Read the summary from the audit file",
    )

    for fragment in forbidden_fragments:
        assert fragment not in text


def test_autonomous_late_stages_stay_provider_neutral() -> None:
    text = _late_stage_text()

    assert "runtime/provider-neutral" in text
    for descriptor in iter_runtime_descriptors():
        literals = (
            descriptor.display_name,
            descriptor.runtime_name,
            descriptor.launch_command,
            descriptor.config_dir_name,
        )
        for literal in literals:
            if literal:
                assert literal not in text
