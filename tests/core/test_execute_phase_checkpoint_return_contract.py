"""Execute-phase proof critic, return, checkpoint, and failure-menu contracts."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gpd.core.child_handoff import ChildGateArtifact, ChildGateTuple, parse_child_gate_markdown, validate_child_handoff
from gpd.core.return_skeleton import build_gpd_return_skeleton

REPO_ROOT = Path(__file__).resolve().parents[2]
EXECUTE_PHASE_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "execute-phase"
_YAML_BLOCK_RE = re.compile(r"```ya?ml\n(?P<body>.*?)\n```", re.DOTALL)


def _stage(name: str) -> str:
    return (EXECUTE_PHASE_DIR / name).read_text(encoding="utf-8")


def _contains_text(text: str, fragment: str) -> bool:
    return fragment in text


def _text_position(text: str, fragment: str) -> int:
    position = text.find(fragment)
    assert position >= 0
    return position


def _child_gate(stage_name: str, gate_id: str) -> ChildGateTuple:
    text = _stage(stage_name)
    for match in _YAML_BLOCK_RE.finditer(text):
        body = match.group("body")
        if "child_gate:" not in body:
            continue
        gate = parse_child_gate_markdown(f"```yaml\n{body}\n```")
        if gate.id == gate_id:
            return gate
    raise AssertionError(f"missing child_gate {gate_id} in {stage_name}")


def test_proof_critic_dispatch_owns_proof_redteam_handoff_and_gate() -> None:
    proof_dispatch = _stage("proof-critic-dispatch.md")
    gate = _child_gate("proof-critic-dispatch.md", "proof_critic_wave_audit")

    assert "CHECK_PROOF_MODEL=$(gpd resolve-model gpd-check-proof)" in proof_dispatch
    assert 'subagent_type="gpd-check-proof"' in proof_dispatch
    assert "templates/proof-redteam-schema.md" in proof_dispatch
    assert "proof-redteam-protocol.md" in proof_dispatch
    assert "Reconstruct the theorem inventory" in proof_dispatch
    assert "gpd --raw apply-return-updates" not in proof_dispatch

    assert gate.role == "gpd-check-proof"
    assert gate.return_profile == "verifier"
    assert [(artifact.path, artifact.must_be_named_in_files_written) for artifact in gate.expected_artifacts] == [
        ("{phase_dir}/{plan_id}-PROOF-REDTEAM.md", True)
    ]
    assert gate.allowed_roots == ("{phase_dir}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$PROOF_HANDOFF_STARTED_AT"
    assert gate.freshness.require_mtime_at_or_after_marker is True
    assert "gpd validate proof-redteam {phase_dir}/{plan_id}-PROOF-REDTEAM.md" in gate.validators
    assert any("--require-files-written" in validator for validator in gate.validators)
    assert any('--fresh-after "$PROOF_HANDOFF_STARTED_AT"' in validator for validator in gate.validators)
    assert "frontmatter status: passed before executor wave success" in gate.validators
    assert gate.applicator.command == "none"
    assert gate.write_allowlist == ("{phase_dir}/{plan_id}-PROOF-REDTEAM.md",)
    assert gate.status_route["checkpoint"] == "checkpoint_resume"


def test_wave_return_checkpoint_accepts_executor_summary_only_through_applicator() -> None:
    wave_return = _stage("wave-return-checkpoint.md")
    gate = _child_gate("wave-return-checkpoint.md", "wave_executor_plan_result")

    assert _contains_text(wave_return, "canonical SUMMARY applicator")
    assert _contains_text(wave_return, "Executor subagents must not write `GPD/STATE.md` directly")
    assert "proof_critic_dispatch" in wave_return
    assert 'subagent_type="gpd-check-proof"' not in wave_return
    assert '<step name="classify_child_return_status">' in wave_return
    assert '<step name="completed_executor_return_gate">' in wave_return
    assert wave_return.index('<step name="classify_child_return_status">') < wave_return.index("child_gate:")
    assert "Checkpoint returns have already routed to `checkpoint_resume`" in wave_return

    assert gate.role == "gpd-executor"
    assert gate.return_profile == "executor"
    assert [(artifact.path, artifact.must_be_named_in_files_written) for artifact in gate.expected_artifacts] == [
        ("${SUMMARY_FILE}", True)
    ]
    assert gate.allowed_roots == ("{phase_dir}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$EXECUTOR_HANDOFF_STARTED_AT"
    assert any("--require-status completed" in validator for validator in gate.validators)
    assert any("--require-files-written" in validator for validator in gate.validators)
    assert any('--fresh-after "$EXECUTOR_HANDOFF_STARTED_AT"' in validator for validator in gate.validators)
    assert "proof-redteam artifact exists and reports status: passed when proof-bearing" in gate.validators
    assert gate.applicator.command == "gpd --raw apply-return-updates ${SUMMARY_FILE}"
    assert gate.applicator.require_passed_true is True
    assert gate.write_allowlist == ("${SUMMARY_FILE}", "{phase_dir}/**")
    assert gate.status_route["checkpoint"] == "checkpoint_resume"
    assert gate.status_route["blocked"] == "wave_failure_menu"


def test_checkpoint_status_routes_to_resume_without_artifact_acceptance(tmp_path: Path) -> None:
    gate = _child_gate("wave-return-checkpoint.md", "wave_executor_plan_result")
    checkpoint_return = build_gpd_return_skeleton(
        role="gpd-executor",
        status="checkpoint",
        phase="01",
        plan="01-01",
    ).markdown

    result = validate_child_handoff(tmp_path, checkpoint_return, gate)

    assert result.passed is False
    assert result.status == "checkpoint"
    assert result.acceptance_state == "status_routed"
    assert result.status_route_used is True
    assert result.selected_route == "checkpoint_resume"
    assert result.checked_files == []
    assert result.applicator_ran is False


def test_completed_summary_read_only_gate_requires_canonical_applicator_pass(tmp_path: Path) -> None:
    summary_path = Path("GPD/phases/01-test/01-01-SUMMARY.md")
    absolute_summary = tmp_path / summary_path
    absolute_summary.parent.mkdir(parents=True)
    absolute_summary.write_text("# Summary\n", encoding="utf-8")
    fresh_after = datetime.now(UTC) - timedelta(minutes=1)
    completed_return = build_gpd_return_skeleton(
        role="gpd-executor",
        status="completed",
        files_written=(summary_path.as_posix(),),
        phase="01",
        plan="01-01",
    ).markdown
    source_gate = _child_gate("wave-return-checkpoint.md", "wave_executor_plan_result")
    concrete_gate = source_gate.model_copy(
        update={
            "expected_artifacts": (ChildGateArtifact(path=summary_path.as_posix()),),
            "allowed_roots": ("GPD/phases",),
            "validators": (),
            "write_allowlist": ("GPD/phases/**",),
        }
    )

    result = validate_child_handoff(tmp_path, completed_return, concrete_gate, fresh_after=fresh_after)

    assert result.read_only_passed is True
    assert result.requires_applicator_pass is True
    assert result.acceptance_state == "read_only_passed_needs_applicator"
    assert result.acceptance_state != "accepted"
    assert result.applicator_required_unrun is True
    assert result.passed is False
    assert result.applicator_command == "gpd --raw apply-return-updates ${SUMMARY_FILE}"


def test_checkpoint_resume_and_failure_menu_have_separate_ownership() -> None:
    checkpoint_resume = _stage("checkpoint-resume.md")
    failure_menu = _stage("wave-failure-menu.md")

    assert "bounded continuation and resume transport" in checkpoint_resume
    assert "gpd_return.status: checkpoint" in checkpoint_resume
    assert "child_gate:" not in checkpoint_resume
    assert _contains_text(checkpoint_resume, "gpd --raw apply-return-updates")
    assert _contains_text(checkpoint_resume, "--checkpoint-resume-file")
    assert _contains_text(checkpoint_resume, "do not show `gpd:resume-work` until the durable state write passes")
    assert _contains_text(checkpoint_resume, "apply completed-work updates")
    assert "Rollback wave to checkpoint" not in checkpoint_resume
    assert "Skip failed plan and dependent plans" not in checkpoint_resume

    assert "Retry failed plan only" in failure_menu
    assert "Skip failed plan and dependent plans" in failure_menu
    assert "Rollback wave to checkpoint" in failure_menu
    assert "Stop execution and preserve completed work" in failure_menu
    assert "stage_stop:" in failure_menu
    assert "child_gate:" not in failure_menu


def test_wave_checkpoint_route_names_parent_owned_checkpoint_application() -> None:
    wave_return = _stage("wave-return-checkpoint.md")

    assert _contains_text(wave_return, "parent-owned resume-file creation and durable checkpoint application")
    assert _contains_text(
        wave_return,
        'gpd --raw apply-return-updates ${CHECKPOINT_RETURN_FILE} --checkpoint-resume-file "${CHECKPOINT_RESUME_FILE}"',
    )
    assert _contains_text(wave_return, "do not run completed-artifact validators")


def test_closeout_readiness_renders_blocked_next_action_before_exit() -> None:
    closeout = _stage("closeout.md")

    readiness_call = _text_position(closeout, 'CLOSEOUT_READINESS=$(gpd --raw phase closeout-readiness')
    status_capture = _text_position(closeout[readiness_call:], "READINESS_STATUS=$?") + readiness_call
    branch = _text_position(closeout[status_capture:], 'CLOSEOUT_READY=$(echo "$CLOSEOUT_READINESS"') + status_capture

    assert readiness_call < status_capture < branch
    assert not _contains_text(closeout, 'if [ $? -ne 0 ]; then\n  echo "$CLOSEOUT_READINESS"\n  exit 1\nfi')
    assert _contains_text(closeout, 'gpd json get .next_up.rendered_markdown --default "$CLOSEOUT_READINESS"')


def test_execute_phase_bootstrap_binds_phase_aliases_before_plan_validation() -> None:
    bootstrap = _stage("phase-bootstrap.md")

    alias_binding = _text_position(bootstrap, "Bind `phase_dir` and `phase_number` from `BOOTSTRAP_INIT`")
    plan_loop = _text_position(bootstrap, 'for plan in "$phase_dir"/*-PLAN.md; do')
    wave_gate = _text_position(bootstrap, 'gpd phase validate-waves "$phase_number"')

    assert alias_binding < plan_loop < wave_gate
    assert _contains_text(bootstrap, "default phase number to `PHASE_ARG`")
