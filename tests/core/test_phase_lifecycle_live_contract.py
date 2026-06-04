"""End-to-end phase lifecycle contracts that mirror live agent handoffs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpd.adapters import get_adapter
from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.cli import app
from gpd.core.commands import cmd_apply_return_updates
from gpd.core.phase_lifecycle import phase_lifecycle_decision
from gpd.core.state import default_state_dict, generate_state_markdown
from gpd.core.suggest import suggest_next
from tests.helpers.cli import StableCliRunner, cli_text, json_output_from_result
from tests.runtime_install_helpers import seed_complete_runtime_install

RUNNER = StableCliRunner()
_RUNTIME_NAMES = tuple(descriptor.runtime_name for descriptor in iter_runtime_descriptors())
_FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS = (
    "gpd --raw init",
    "--raw init",
    "gpd --raw stage field-access",
    "--raw stage field-access",
)


def _write_phase_project(
    root: Path,
    *,
    phase: str = "02",
    phase_name: str = "analysis",
    current_plan: int = 2,
    total_plans: int = 2,
    status: str = "Ready to execute",
    summaries: int = 2,
) -> Path:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / f"{phase}-{phase_name}"
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n## Phase 1: Setup\n\n## Phase 2: Analysis\n\n## Phase 3: Synthesis\n",
        encoding="utf-8",
    )
    for index in range(1, total_plans + 1):
        (phase_dir / f"{phase}-{index:02d}-PLAN.md").write_text(
            f"# Phase {phase} Plan {index:02d}\n",
            encoding="utf-8",
        )
    for index in range(1, summaries + 1):
        (phase_dir / f"{phase}-{index:02d}-SUMMARY.md").write_text(
            f"# Phase {phase} Plan {index:02d} Summary\n",
            encoding="utf-8",
        )

    state = default_state_dict()
    state["position"]["current_phase"] = phase
    state["position"]["current_phase_name"] = phase_name.title()
    state["position"]["current_plan"] = str(current_plan)
    state["position"]["total_plans_in_phase"] = total_plans
    state["position"]["total_phases"] = 3
    state["position"]["progress_percent"] = 66
    state["position"]["status"] = status
    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    return phase_dir


def _write_completed_return(summary_path: Path, *, phase: str = "02", plan: str = "02") -> None:
    summary_path.write_text(
        "# Completed Summary\n\n"
        "```yaml\n"
        "gpd_return:\n"
        "  status: completed\n"
        f"  files_written: [{summary_path.as_posix()}]\n"
        "  issues: []\n"
        f"  next_actions: [gpd:verify-work {phase}]\n"
        f'  phase: "{phase}"\n'
        f'  plan: "{plan}"\n'
        "  tasks_completed: 1\n"
        "  tasks_total: 1\n"
        "  duration_seconds: 12\n"
        "  state_updates:\n"
        "    advance_plan: true\n"
        "    update_progress: true\n"
        "    record_metric:\n"
        f'      phase: "{phase}"\n'
        f'      plan: "{plan}"\n'
        '      duration: "12s"\n'
        '      tasks: "1"\n'
        '      files: "1"\n'
        "```\n",
        encoding="utf-8",
    )


def _write_gap_verification(report_path: Path, *, status: str = "gaps_found") -> None:
    report_path.write_text(
        "---\n"
        "phase: 02-analysis\n"
        'verified: "2026-05-07T00:00:00Z"\n'
        f"status: {status}\n"
        'score: "0/1 contract targets verified"\n'
        "---\n\n"
        "# Phase 02 Verification\n\n"
        "```bash\n"
        "printf 'missing benchmark evidence\\n'\n"
        "```\n\n"
        "**Output:**\n\n"
        "```output\n"
        "missing benchmark evidence\n"
        "```\n\n"
        "FAIL: benchmark evidence is absent.\n",
        encoding="utf-8",
    )


def _write_passed_verification(report_path: Path) -> None:
    report_path.write_text(
        "---\n"
        "phase: 02-analysis\n"
        'verified: "2026-05-07T00:00:00Z"\n'
        "status: passed\n"
        'score: "1/1 contract targets verified"\n'
        "---\n\n"
        "# Phase 02 Verification\n\n"
        "```bash\n"
        "printf 'all lifecycle contracts verified\\n'\n"
        "```\n\n"
        "**Output:**\n\n"
        "```output\n"
        "all lifecycle contracts verified\n"
        "```\n\n"
        "PASS: lifecycle contract evidence is complete.\n",
        encoding="utf-8",
    )


def _mark_closed_to_next_phase(root: Path, *, next_phase: str = "03") -> None:
    state_path = root / "GPD" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["position"]["current_phase"] = next_phase
    state["position"]["current_phase_name"] = "Synthesis"
    state["position"]["current_plan"] = None
    state["position"]["total_plans_in_phase"] = None
    state["position"]["status"] = "Ready to plan"
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (root / "GPD" / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")


def _snapshot_closeout_surfaces(root: Path) -> dict[Path, str | None]:
    paths = [
        root / "GPD" / "ROADMAP.md",
        root / "GPD" / "STATE.md",
        root / "GPD" / "state.json",
        root / "GPD" / "CHECKPOINTS.md",
    ]
    return {path: path.read_text(encoding="utf-8") if path.exists() else None for path in paths}


def _assert_closeout_surfaces_unchanged(snapshot: dict[Path, str | None]) -> None:
    for path, before in snapshot.items():
        after = path.read_text(encoding="utf-8") if path.exists() else None
        assert after == before


def _invoke_apply_return(tmp_path: Path, report: str):
    return RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "apply-return-updates",
            report,
        ],
    )


def test_apply_return_updates_completes_last_plan_from_ready_to_execute_state(tmp_path: Path) -> None:
    """A final-plan child return should not require manual Ready -> Executing repair."""
    phase_dir = _write_phase_project(tmp_path, status="Ready to execute")
    summary = phase_dir / "02-02-SUMMARY.md"
    _write_completed_return(summary)

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "apply-return-updates",
            "GPD/phases/02-analysis/02-02-SUMMARY.md",
        ],
    )

    payload = json_output_from_result(result)
    assert payload["passed"] is True
    assert "advance_plan:last_plan" in payload["applied_state_operations"]
    state = json.loads((tmp_path / "GPD" / "state.json").read_text(encoding="utf-8"))
    assert str(state["position"]["current_plan"]) == "2"
    assert state["position"]["status"] == "Phase complete \u2014 ready for verification"


def test_phase_complete_without_canonical_verification_fails_closed_without_mutation(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Verified")
    before = _snapshot_closeout_surfaces(tmp_path)

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "complete",
            "02",
        ],
    )

    failure_text = cli_text(result, expect_exit=1) + (str(result.exception) if result.exception else "")
    assert "canonical verification report missing" in failure_text
    assert not (tmp_path / "GPD" / "ROADMAP.md.lock").exists()
    assert not (tmp_path / "GPD" / "CHECKPOINTS.md").exists()
    assert not (tmp_path / "GPD" / "phase-checkpoints").exists()
    assert not any(path.name.endswith("VERIFICATION.md") for path in phase_dir.iterdir())
    _assert_closeout_surfaces_unchanged(before)


def test_phase_complete_with_non_passing_verification_fails_closed_without_mutation(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Blocked")
    verification_report = phase_dir / "02-VERIFICATION.md"
    _write_gap_verification(verification_report, status="gaps_found")
    before = _snapshot_closeout_surfaces(tmp_path)
    before_report = verification_report.read_text(encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "complete",
            "02",
        ],
    )

    failure_text = cli_text(result, expect_exit=1) + (str(result.exception) if result.exception else "")
    assert "canonical verification report must have top-level frontmatter status 'passed'" in failure_text
    assert not (tmp_path / "GPD" / "ROADMAP.md.lock").exists()
    assert verification_report.read_text(encoding="utf-8") == before_report
    assert not (tmp_path / "GPD" / "CHECKPOINTS.md").exists()
    assert not (tmp_path / "GPD" / "phase-checkpoints").exists()
    _assert_closeout_surfaces_unchanged(before)


def test_apply_return_updates_rejects_report_without_gpd_return_without_mutating_state(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Ready to execute")
    report = phase_dir / "CONSISTENCY-CHECK.md"
    report.write_text("# Consistency Check\n\nNo issues found.\n", encoding="utf-8")
    before_state = (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "apply-return-updates",
            "GPD/phases/02-analysis/CONSISTENCY-CHECK.md",
        ],
    )

    payload = json_output_from_result(result, expect_exit=1)
    assert payload["passed"] is False
    assert payload["errors"] == ["No gpd_return YAML block found"]
    assert payload["primary_failure_class"] == "return_missing"
    assert payload["failure_classes"] == ["return_missing"]
    assert payload["failures"][0]["code"] == "missing_block"
    assert payload["failures"][0]["repairable"] is True
    assert payload["failures"][0]["repair_hint"].startswith("Retry the child with one fenced")
    assert (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8") == before_state


def test_apply_return_updates_rejects_malformed_required_fields_as_repairable_without_mutating_state(
    tmp_path: Path,
) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Ready to execute")
    report = phase_dir / "MALFORMED-RETURN.md"
    report.write_text(
        "# Malformed Return\n\n```yaml\ngpd_return:\n  files_written: [GPD/phases/02-analysis/02-02-SUMMARY.md]\n```\n",
        encoding="utf-8",
    )
    state_path = tmp_path / "GPD" / "state.json"
    before_state = state_path.read_text(encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "apply-return-updates",
            "GPD/phases/02-analysis/MALFORMED-RETURN.md",
        ],
    )

    payload = json_output_from_result(result, expect_exit=1)
    assert payload["passed"] is False
    assert payload["mutated"] is False
    assert payload["primary_failure_class"] == "return_malformed_repairable"
    assert payload["failure_classes"] == ["return_malformed_repairable"]
    assert {failure["code"] for failure in payload["failures"]} == {"missing_required_fields"}
    assert all(failure["repairable"] is True for failure in payload["failures"])
    assert all(failure["repair_hint"].startswith("Retry with status, files_written") for failure in payload["failures"])
    assert "Missing required field: status" in payload["errors"]
    assert "Missing required field: issues" in payload["errors"]
    assert "Missing required field: next_actions" in payload["errors"]
    assert state_path.read_text(encoding="utf-8") == before_state


def test_apply_return_updates_rejects_multiple_gpd_returns_without_mutating_state(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Ready to execute")
    report = phase_dir / "AMBIGUOUS-RETURN.md"
    report.write_text(
        "# Ambiguous Return\n\n"
        "```yaml\n"
        "gpd_return:\n"
        "  status: completed\n"
        "  files_written: [GPD/phases/02-analysis/02-02-SUMMARY.md]\n"
        "  issues: []\n"
        "  next_actions: [gpd:verify-work 02]\n"
        "  state_updates:\n"
        "    advance_plan: true\n"
        "    update_progress: true\n"
        "```\n\n"
        "```yaml\n"
        "gpd_return:\n"
        "  status: blocked\n"
        "  files_written: []\n"
        "  issues: [conflicting return]\n"
        "  next_actions: [gpd:resume-work]\n"
        "  blockers:\n"
        "    - conflicting return\n"
        "```\n",
        encoding="utf-8",
    )
    state_path = tmp_path / "GPD" / "state.json"
    before_state = state_path.read_text(encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "apply-return-updates",
            "GPD/phases/02-analysis/AMBIGUOUS-RETURN.md",
        ],
    )

    payload = json_output_from_result(result, expect_exit=1)
    assert payload["passed"] is False
    assert payload["mutated"] is False
    assert payload["errors"] == ["Multiple gpd_return YAML blocks found: expected exactly one, got 2"]
    assert payload["primary_failure_class"] == "return_malformed_blocking"
    assert payload["failure_classes"] == ["return_malformed_blocking"]
    assert payload["failures"][0]["code"] == "ambiguous_multiple_returns"
    assert payload["failures"][0]["repairable"] is False
    assert payload["failures"][0]["repair_hint"].startswith("Retry with exactly one canonical")
    assert payload["applied_state_operations"] == []
    assert state_path.read_text(encoding="utf-8") == before_state


def test_malformed_child_return_retry_then_stop_chain_preserves_state_bytes(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Ready to execute")
    state_path = tmp_path / "GPD" / "state.json"
    state_md_path = tmp_path / "GPD" / "STATE.md"
    initial_state = state_path.read_bytes()
    initial_state_md = state_md_path.read_bytes()
    initial_surfaces = _snapshot_closeout_surfaces(tmp_path)

    retry_report = phase_dir / "FIRST-BAD-RETURN.md"
    retry_report.write_text("# Child Report\n\nFinished the work but omitted the return block.\n", encoding="utf-8")

    retry_result = _invoke_apply_return(tmp_path, "GPD/phases/02-analysis/FIRST-BAD-RETURN.md")

    retry_payload = json_output_from_result(retry_result, expect_exit=1)
    assert retry_payload["passed"] is False
    assert retry_payload["mutated"] is False
    assert retry_payload["primary_failure_class"] == "return_missing"
    assert retry_payload["failure_classes"] == ["return_missing"]
    assert retry_payload["failures"][0]["repairable"] is True
    assert state_path.read_bytes() == initial_state
    assert state_md_path.read_bytes() == initial_state_md
    _assert_closeout_surfaces_unchanged(initial_surfaces)

    stop_report = phase_dir / "SECOND-BAD-RETURN.md"
    stop_report.write_text(
        "# Ambiguous Child Report\n\n"
        "```yaml\n"
        "gpd_return:\n"
        "  status: completed\n"
        "  files_written: [GPD/phases/02-analysis/02-02-SUMMARY.md]\n"
        "  issues: []\n"
        "  next_actions: [gpd:verify-work 02]\n"
        "```\n\n"
        "```yaml\n"
        "gpd_return:\n"
        "  status: blocked\n"
        "  files_written: []\n"
        "  issues: [ambiguous duplicate return]\n"
        "  next_actions: [gpd:resume-work]\n"
        "```\n",
        encoding="utf-8",
    )

    stop_result = _invoke_apply_return(tmp_path, "GPD/phases/02-analysis/SECOND-BAD-RETURN.md")

    stop_payload = json_output_from_result(stop_result, expect_exit=1)
    assert stop_payload["passed"] is False
    assert stop_payload["mutated"] is False
    assert stop_payload["primary_failure_class"] == "return_malformed_blocking"
    assert stop_payload["failure_classes"] == ["return_malformed_blocking"]
    assert stop_payload["failures"][0]["code"] == "ambiguous_multiple_returns"
    assert stop_payload["failures"][0]["repairable"] is False
    assert stop_payload["applied_state_operations"] == []
    assert state_path.read_bytes() == initial_state
    assert state_md_path.read_bytes() == initial_state_md
    assert not (tmp_path / "GPD" / "phase-checkpoints").exists()
    _assert_closeout_surfaces_unchanged(initial_surfaces)


def test_apply_return_updates_rejects_intermediate_plan_direct_phase_completion_without_mutation(
    tmp_path: Path,
) -> None:
    phase_dir = _write_phase_project(tmp_path, current_plan=1, total_plans=2, status="Ready to execute", summaries=1)
    report = phase_dir / "02-01-DIRECT-COMPLETE.md"
    report.write_text(
        "# Direct Completion Attempt\n\n"
        "```yaml\n"
        "gpd_return:\n"
        "  status: completed\n"
        "  files_written: [GPD/phases/02-analysis/02-01-SUMMARY.md]\n"
        "  issues: []\n"
        "  next_actions: [gpd:verify-work 02]\n"
        '  phase: "02"\n'
        '  plan: "01"\n'
        "  state_updates:\n"
        "    complete_phase: true\n"
        "```\n",
        encoding="utf-8",
    )
    state_path = tmp_path / "GPD" / "state.json"
    state_md_path = tmp_path / "GPD" / "STATE.md"
    before_state = state_path.read_text(encoding="utf-8")
    before_state_md = state_md_path.read_text(encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "apply-return-updates",
            "GPD/phases/02-analysis/02-01-DIRECT-COMPLETE.md",
        ],
    )

    payload = json_output_from_result(result, expect_exit=1)
    assert payload["passed"] is False
    assert payload["mutated"] is False
    assert payload["primary_failure_class"] == "applicator_failed"
    assert payload["applied_state_operations"] == []
    assert any("state_updates.complete_phase" in error for error in payload["errors"])
    assert state_path.read_text(encoding="utf-8") == before_state
    assert state_md_path.read_text(encoding="utf-8") == before_state_md


def test_checkpoint_intent_core_apply_updates_exposes_bounded_segment_resume(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Executing", summaries=1)
    resume_file = phase_dir / ".continue-here.md"
    resume_file.write_text("Resume from first-result checkpoint.\n", encoding="utf-8")
    return_file = phase_dir / "02-02-CHECKPOINT.md"
    return_file.write_text(
        "# Checkpoint\n\n"
        "```yaml\n"
        "gpd_return:\n"
        "  status: checkpoint\n"
        "  files_written: []\n"
        "  issues: []\n"
        "  next_actions: [gpd:resume-work]\n"
        '  phase: "02"\n'
        '  plan: "02"\n'
        "  checkpoint_intent:\n"
        "    checkpoint_reason: first_result_gate\n"
        "    awaiting: user_review\n"
        "    first_result_gate_pending: true\n"
        "    downstream_locked: true\n"
        "```\n",
        encoding="utf-8",
    )

    apply_result = cmd_apply_return_updates(
        tmp_path,
        return_file,
        checkpoint_resume_file="GPD/phases/02-analysis/.continue-here.md",
    )

    assert apply_result.passed is True
    assert apply_result.applied_continuation_operations == ["set_bounded_segment"]
    resume_result = RUNNER.invoke(app, ["--raw", "--cwd", str(tmp_path), "init", "resume"])
    payload = json_output_from_result(resume_result)
    assert payload["active_resume_kind"] == "bounded_segment"
    assert payload["active_resume_pointer"] == "GPD/phases/02-analysis/.continue-here.md"
    assert payload["active_bounded_segment"]["checkpoint_reason"] == "first_result_gate"
    assert payload["active_bounded_segment"]["first_result_gate_pending"] is True


@pytest.mark.parametrize("report_status", ["gaps_found", "human_needed", "expert_needed"])
@pytest.mark.parametrize("initial_status", ["verifying", "Phase complete \u2014 ready for verification"])
def test_record_verification_maps_non_passing_report_to_blocked_and_keeps_state_surfaces_in_sync(
    tmp_path: Path,
    initial_status: str,
    report_status: str,
) -> None:
    phase_dir = _write_phase_project(tmp_path, status=initial_status)
    verification_report = phase_dir / "02-VERIFICATION.md"
    _write_gap_verification(verification_report, status=report_status)
    before_report = verification_report.read_text(encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "state",
            "record-verification",
            "--phase",
            "02",
        ],
    )

    payload = json_output_from_result(result)
    assert payload["recorded"] is True
    assert payload["status"] == "Blocked"
    assert payload["previous_status"] == initial_status
    assert verification_report.read_text(encoding="utf-8") == before_report

    state = json.loads((tmp_path / "GPD" / "state.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "GPD" / "STATE.md").read_text(encoding="utf-8")
    assert state["position"]["status"] == "Blocked"
    assert state["position"]["status"] != "Verified"
    assert "**Status:** Blocked" in markdown

    decision = phase_lifecycle_decision(tmp_path, "02")
    assert decision.state_status == "Blocked"
    assert decision.decision == "needs_verification"
    assert decision.closeout_ready is False
    assert decision.primary_action == "verify-work"
    assert decision.primary_owner == "runtime"
    assert decision.primary_command == "gpd:verify-work 02"
    assert decision.next_up["primary_command"]["action"] == "verify-work"
    assert decision.next_up["primary_command"]["owner"] == "runtime"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:verify-work 02"
    assert decision.closeout_readiness.closeout_command is None

    validation = RUNNER.invoke(app, ["--raw", "--cwd", str(tmp_path), "state", "validate"])
    validation_payload = json_output_from_result(validation)
    assert validation_payload["valid"] is True
    assert validation_payload["integrity_status"] == "healthy"


@pytest.mark.parametrize("initial_status", ["Ready to execute", "Planning", "Complete"])
def test_record_verification_invalid_status_transition_preserves_state_bytes(
    tmp_path: Path,
    initial_status: str,
) -> None:
    phase_dir = _write_phase_project(tmp_path, status=initial_status)
    verification_report = phase_dir / "02-VERIFICATION.md"
    _write_passed_verification(verification_report)
    state_path = tmp_path / "GPD" / "state.json"
    state_md_path = tmp_path / "GPD" / "STATE.md"
    before_state = state_path.read_bytes()
    before_state_md = state_md_path.read_bytes()
    before_report = verification_report.read_bytes()

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "state",
            "record-verification",
            "--phase",
            "02",
        ],
    )

    payload = json_output_from_result(result, expect_exit=1)
    assert payload["recorded"] is False
    assert payload["previous_status"] == initial_status
    assert "state_record_verification requires Status" in payload["error"]
    assert state_path.read_bytes() == before_state
    assert state_md_path.read_bytes() == before_state_md
    assert verification_report.read_bytes() == before_report


@pytest.mark.parametrize("initial_status", ["verifying", "Phase complete \u2014 ready for verification"])
def test_record_verification_maps_passing_report_to_verified_and_keeps_state_surfaces_in_sync(
    tmp_path: Path,
    initial_status: str,
) -> None:
    phase_dir = _write_phase_project(tmp_path, status=initial_status)
    verification_report = phase_dir / "02-VERIFICATION.md"
    _write_passed_verification(verification_report)
    before_report = verification_report.read_text(encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "state",
            "record-verification",
            "--phase",
            "02",
        ],
    )

    payload = json_output_from_result(result)
    assert payload["recorded"] is True
    assert payload["status"] == "Verified"
    assert payload["previous_status"] == initial_status
    assert verification_report.read_text(encoding="utf-8") == before_report

    state = json.loads((tmp_path / "GPD" / "state.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "GPD" / "STATE.md").read_text(encoding="utf-8")
    assert state["position"]["status"] == "Verified"
    assert "**Status:** Verified" in markdown

    validation = RUNNER.invoke(app, ["--raw", "--cwd", str(tmp_path), "state", "validate"])
    validation_payload = json_output_from_result(validation)
    assert validation_payload["valid"] is True
    assert validation_payload["integrity_status"] == "healthy"


def test_record_verification_manual_status_override_requires_admin_flag(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Verifying")
    state_path = tmp_path / "GPD" / "state.json"
    state_md_path = tmp_path / "GPD" / "STATE.md"
    before_state = state_path.read_text(encoding="utf-8")
    before_state_md = state_md_path.read_text(encoding="utf-8")

    blocked_result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "state",
            "record-verification",
            "--phase",
            "02",
            "--status",
            "passed",
        ],
    )

    blocked_payload = json_output_from_result(blocked_result, expect_exit=1)
    assert blocked_payload["recorded"] is False
    assert "admin_override=True" in blocked_payload["error"]
    assert state_path.read_text(encoding="utf-8") == before_state
    assert state_md_path.read_text(encoding="utf-8") == before_state_md
    assert not any(path.name.endswith("VERIFICATION.md") for path in phase_dir.iterdir())

    admin_result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "state",
            "record-verification",
            "--phase",
            "02",
            "--status",
            "passed",
            "--admin-status-override",
        ],
    )

    admin_payload = json_output_from_result(admin_result)
    assert admin_payload["recorded"] is True
    assert admin_payload["status"] == "Verified"
    assert not any(path.name.endswith("VERIFICATION.md") for path in phase_dir.iterdir())


def test_closeout_readiness_raw_closed_phase_missing_next_context_routes_to_discuss(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Verified")
    _write_passed_verification(phase_dir / "02-VERIFICATION.md")
    _mark_closed_to_next_phase(tmp_path)
    before_readiness = _snapshot_closeout_surfaces(tmp_path)

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "closeout-readiness",
            "02",
            "--require-verification",
        ],
    )

    payload = json_output_from_result(result, expect_exit=1)
    assert payload["ready"] is False
    assert payload["read_only"] is True
    assert payload["mutated"] is False
    assert "next_up" in payload
    route = payload["lifecycle_route"]
    assert route["status"] == "closed"
    assert route["status_class"] == "closed_ready_next_phase"
    assert route["transition_owner"] == "runtime"
    assert route["next_phase"] == "03"
    assert route["next_phase_context_class"] == "missing_context"
    assert route["primary_runtime_command"]["command"] == "gpd:discuss-phase 03"
    assert route["primary_runtime_command_text"] == "gpd:discuss-phase 03"
    assert route["stage_stop_next_runtime_command"] == "gpd:discuss-phase 03"
    assert payload["lifecycle_next_up"]["primary"]["command"] == "gpd:discuss-phase 03"
    assert payload["next_up"]["primary_command"]["command"] == "gpd:discuss-phase 03"
    assert payload["next_up"]["stage_stop_next_runtime_command"] == route["stage_stop_next_runtime_command"]
    assert all(fragment not in route["rendered_markdown"] for fragment in _FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS)
    assert all(
        fragment not in payload["next_up"]["rendered_markdown"] for fragment in _FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS
    )
    _assert_closeout_surfaces_unchanged(before_readiness)


def test_closeout_readiness_raw_closed_phase_with_next_context_routes_to_plan(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Verified")
    _write_passed_verification(phase_dir / "02-VERIFICATION.md")
    next_phase_dir = tmp_path / "GPD" / "phases" / "03-synthesis"
    next_phase_dir.mkdir(parents=True)
    (next_phase_dir / "03-CONTEXT.md").write_text("# Phase 03 Context\n", encoding="utf-8")
    _mark_closed_to_next_phase(tmp_path)
    before_readiness = _snapshot_closeout_surfaces(tmp_path)

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "closeout-readiness",
            "02",
            "--require-verification",
        ],
    )

    payload = json_output_from_result(result, expect_exit=1)
    assert "next_up" in payload
    route = payload["lifecycle_route"]
    assert route["status"] == "closed"
    assert route["status_class"] == "closed_ready_next_phase"
    assert route["transition_owner"] == "runtime"
    assert route["next_phase"] == "03"
    assert route["next_phase_context_class"] == "has_context"
    assert route["primary_runtime_command"]["command"] == "gpd:plan-phase 03"
    assert route["primary_runtime_command_text"] == "gpd:plan-phase 03"
    assert route["stage_stop_next_runtime_command"] == "gpd:plan-phase 03"
    assert payload["lifecycle_next_up"]["primary"]["command"] == "gpd:plan-phase 03"
    assert payload["next_up"]["primary_command"]["command"] == "gpd:plan-phase 03"
    assert payload["next_up"]["stage_stop_next_runtime_command"] == route["stage_stop_next_runtime_command"]
    assert all(fragment not in route["rendered_markdown"] for fragment in _FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS)
    assert all(
        fragment not in payload["next_up"]["rendered_markdown"] for fragment in _FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS
    )
    _assert_closeout_surfaces_unchanged(before_readiness)


def test_full_lifecycle_chain_checks_closeout_readiness_before_phase_complete(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, status="Ready to execute")
    summary = phase_dir / "02-02-SUMMARY.md"
    _write_completed_return(summary)

    apply_result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "apply-return-updates",
            "GPD/phases/02-analysis/02-02-SUMMARY.md",
        ],
    )

    apply_payload = json_output_from_result(apply_result)
    assert apply_payload["passed"] is True
    assert "advance_plan:last_plan" in apply_payload["applied_state_operations"]
    state = json.loads((tmp_path / "GPD" / "state.json").read_text(encoding="utf-8"))
    assert state["position"]["status"] == "Phase complete \u2014 ready for verification"

    verification_report = phase_dir / "02-VERIFICATION.md"
    _write_passed_verification(verification_report)
    record_result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "state",
            "record-verification",
            "--phase",
            "02",
        ],
    )

    record_payload = json_output_from_result(record_result)
    assert record_payload["recorded"] is True
    assert record_payload["status"] == "Verified"

    before_readiness = _snapshot_closeout_surfaces(tmp_path)
    readiness_result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "closeout-readiness",
            "02",
            "--require-verification",
        ],
    )

    readiness_payload = json_output_from_result(readiness_result)
    assert readiness_payload["ready"] is True
    assert readiness_payload["read_only"] is True
    assert readiness_payload["mutated"] is False
    assert readiness_payload["mutation_allowed"] is True
    assert readiness_payload["verification_status"] == "passed"
    assert readiness_payload["closeout_command"] == "gpd phase complete 02"
    state = json.loads((tmp_path / "GPD" / "state.json").read_text(encoding="utf-8"))
    assert state["position"]["status"] == "Verified"
    _assert_closeout_surfaces_unchanged(before_readiness)

    decision = phase_lifecycle_decision(tmp_path, "02")
    assert decision.decision == "ready_for_closeout"
    assert decision.closeout_ready is True
    assert decision.primary_action == "phase-complete"
    assert decision.primary_owner == "local_transition"
    assert decision.primary_command == "gpd phase complete 02"
    assert decision.next_up["primary_command"]["owner"] == "local_transition"
    assert decision.next_up["after_this_completes"]["owner"] == "runtime"
    assert decision.next_up["after_this_completes"]["command"] == "gpd:suggest-next"
    assert decision.next_up["stage_stop_next_runtime_command"] == "gpd:suggest-next"
    assert "gpd phase complete" not in decision.next_up["stage_stop_next_runtime_command"]

    complete_result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "complete",
            "02",
        ],
    )

    complete_payload = json_output_from_result(complete_result)
    assert complete_payload["completed_phase"] == "02"
    assert complete_payload["all_plans_complete"] is True
    assert complete_payload["next_phase"] == "03"
    assert complete_payload["state_updated"] is True
    state = json.loads((tmp_path / "GPD" / "state.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "GPD" / "STATE.md").read_text(encoding="utf-8")
    assert state["position"]["current_phase"] == "03"
    assert state["position"]["status"] == "Ready to plan"
    assert "**Status:** Ready to plan" in markdown


@pytest.mark.parametrize("runtime", _RUNTIME_NAMES)
def test_completed_phase_suggests_active_runtime_verify_work_not_structural_verify_phase(
    tmp_path: Path,
    runtime: str,
) -> None:
    adapter = get_adapter(runtime)
    seed_complete_runtime_install(tmp_path / adapter.local_config_dir_name, runtime=runtime)
    _write_phase_project(tmp_path, status="Phase complete \u2014 ready for verification", summaries=2)

    result = suggest_next(tmp_path)

    verify = next((suggestion for suggestion in result.suggestions if suggestion.action == "verify-work"), None)
    assert verify is not None, (
        f"No 'verify-work' suggestion found for runtime={runtime!r}; "
        f"got: {[suggestion.action for suggestion in result.suggestions]}"
    )
    assert verify.command == f"{adapter.format_command('verify-work')} 02"
    assert "gpd verify phase" not in verify.command
