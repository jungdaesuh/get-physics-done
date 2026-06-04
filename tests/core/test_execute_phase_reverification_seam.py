"""Focused assertions for the execute-phase re-verification seam."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from gpd.core.handoff_artifacts import validate_handoff_artifacts_markdown
from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, machine_exact, semantic_anchor
from tests.lifecycle_contract_test_support import (
    artifact_paths,
    assert_forbidden_lifecycle_prose,
    assert_machine_contract,
    assert_semantic_contract,
    child_gate_from_text,
)
from tests.markdown_test_support import extract_marker_range, parse_markdown_table
from tests.return_skeleton_support import render_gpd_return_block

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"


def _read(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _read_execute_phase_stage(name: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def _stage_stop_row(workflow: str, stop: str) -> dict[str, str]:
    section = extract_marker_range(
        workflow,
        '<step name="convention_repair_route">',
        "</step>",
        context="consistency-check convention repair route",
    )
    table = parse_markdown_table(section, context="consistency-check stage_stop routes")
    for row in table.rows:
        if row["Stop"] == stop:
            return row
    raise AssertionError(f"missing consistency-check stage_stop row: {stop}")


def test_execute_phase_reverification_routes_on_typed_status_not_legacy_verifier_text() -> None:
    workflow = _read_execute_phase_stage("gap-reverification.md")

    select_idx = workflow.index('<step name="select_current_gap">')
    classify_idx = workflow.index('<step name="classify_gap_closure_route">')
    bridge_idx = workflow.index("verification_report_skeleton_bridge")
    verifier_idx = workflow.index('subagent_type="gpd-verifier"')

    assert select_idx < classify_idx < verifier_idx < bridge_idx
    assert "current_gap:" in workflow
    assert "failed_plan:" in workflow
    assert_semantic_contract(
        workflow,
        "gap reverification targets only unresolved prior work",
        "re-verify",
        "previously unresolved targets",
    )
    assert_machine_contract(
        workflow,
        "gap reverification status route and return fields",
        "`completed` + `passed`: continue to `consistency_check`",
        "`checkpoint`: stop and route to `gpd:resume-work`",
        "`blocked` / `failed`: stop and route to `gpd:verify-work {PHASE_NUMBER}`",
        "include files_written",
        "verification_status: passed | gaps_found | expert_needed | human_needed",
    )
    assert_forbidden_lifecycle_prose(
        workflow,
        "retired short verifier status vocabulary",
        "Return verification status: passed | gaps_found.",
    )
    assert_semantic_contract(
        workflow,
        "gap reverification ignores prose heading success",
        "prose headings",
        "untyped routing",
        "infer success",
    )
    assert_semantic_contract(
        workflow,
        "gap reverification cannot close on non-passing or malformed paths",
        "phase complete",
        "non-passing",
        "malformed path",
    )


def test_execute_phase_reverification_requires_files_written_and_disk_artifact_gate() -> None:
    workflow = _read_execute_phase_stage("gap-reverification.md")
    gate = child_gate_from_text(workflow, "gap_closure_reverification")

    assert_machine_contract(
        workflow,
        "gap reverification verifier spawn anchor",
        'subagent_type="gpd-verifier"',
    )
    assert gate.id == "gap_closure_reverification"
    assert gate.role == "gpd-verifier"
    assert gate.return_profile == "verifier"
    assert gate.required_status == "completed"
    assert artifact_paths(gate) == ("{phase_dir}/{phase_number}-VERIFICATION.md",)
    assert gate.allowed_roots == ("{phase_dir}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$REVERIFY_HANDOFF_STARTED_AT"
    assert gate.freshness.require_mtime_at_or_after_marker is True
    assert any(
        "gpd validate handoff-artifacts - --expected '{phase_dir}/{phase_number}-VERIFICATION.md'" in validator
        for validator in gate.validators
    )
    assert any("--require-files-written" in validator for validator in gate.validators)
    assert "gpd validate verification-contract {phase_dir}/{phase_number}-VERIFICATION.md" in gate.validators


def test_execute_phase_reverification_keeps_fail_closed_on_spawn_errors_and_stale_reports() -> None:
    workflow = _read_execute_phase_stage("gap-reverification.md")

    assert_semantic_contract(
        workflow,
        "gap reverification fail-closed artifact gate failures",
        "malformed",
        "files_written",
        "stale report",
        "failed validators",
        "fail closed",
    )
    assert_semantic_contract(
        workflow,
        "gap reverification non-passing route stops without loop",
        "non-passing",
        "stop",
        "auto-looping",
    )
    assert_semantic_contract(
        workflow,
        "gap reverification cannot complete on malformed result",
        "phase complete",
        "non-passing",
        "malformed path",
    )


def test_execute_phase_gap_reverification_has_debugger_and_circuit_breaker() -> None:
    workflow = _read_execute_phase_stage("gap-reverification.md")

    assert_semantic_contract(
        workflow,
        "persistent gap requires debugger before second attempt",
        "debugger",
        "before",
        "second attempt",
    )
    assert_machine_contract(
        workflow,
        "gap reverification debugger and convention command anchors",
        'subagent_type="gpd-debugger"',
        "gpd:validate-conventions",
    )
    assert_semantic_contract(
        workflow,
        "gap reverification circuit breaker prevents third cycle",
        "maximum two",
        "verification-gap closure cycles",
        "third automated cycle",
    )


def test_execute_phase_consistency_check_uses_typed_return_and_file_gate() -> None:
    workflow = _read_execute_phase_stage("consistency-check.md")
    gate = child_gate_from_text(workflow, "rapid_consistency_check")

    spawn_idx = workflow.index('<step name="spawn_rapid_checker">')
    route_idx = workflow.index('<step name="checker_return_status_route">')
    gate_idx = workflow.index("child_gate:")
    repair_idx = workflow.index('<step name="convention_repair_route">')

    assert spawn_idx < route_idx < gate_idx < repair_idx
    assert gate.id == "rapid_consistency_check"
    assert gate.role == "gpd-consistency-checker"
    assert gate.return_profile == "checker"
    assert gate.required_status == "completed"
    assert artifact_paths(gate) == ("{phase_dir}/CONSISTENCY-CHECK.md",)
    assert gate.allowed_roots == ("{phase_dir}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$CONSISTENCY_HANDOFF_STARTED_AT"
    assert gate.freshness.require_mtime_at_or_after_marker is True
    assert any("--require-files-written" in validator for validator in gate.validators)
    assert any("--fresh-after" in validator for validator in gate.validators)

    assert_prompt_contracts(
        workflow,
        machine_exact(
            "consistency check child gate machine anchors",
            (
                "gpd-consistency-checker.md",
                "<spawn_contract>",
                "expected_artifacts:",
                "{phase_dir}/CONSISTENCY-CHECK.md",
                "CONSISTENCY_HANDOFF_STARTED_AT",
            ),
        ),
        semantic_anchor(
            "runtime return canonical for consistency report",
            (
                "child response",
                "runtime return is canonical",
                "report artifact",
            ),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )
    assert "Append the same typed YAML gpd_return block to the artifact before returning" not in workflow


def test_execute_phase_consistency_check_fails_closed_on_malformed_output() -> None:
    workflow = _read_execute_phase_stage("consistency-check.md")

    assert_machine_contract(
        workflow,
        "consistency malformed output machine anchors",
        "omits `gpd_return.status`",
        "omits `files_written`",
        "gpd:validate-conventions",
    )
    assert_semantic_contract(
        workflow,
        "consistency malformed output blocks acceptance",
        "malformed output",
        "consistency check",
        "blocked",
    )
    assert_semantic_contract(
        workflow,
        "consistency route ignores prose headings",
        "prose headings",
        "untyped routing",
        "infer success",
    )
    assert_semantic_contract(
        workflow,
        "consistency parent must not synthesize checker return",
        "synthetic",
        "gpd_return",
        "checker artifact",
    )


def test_execute_phase_consistency_report_without_embedded_return_validates_via_runtime_return(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "GPD" / "phases" / "03-conventions" / "CONSISTENCY-CHECK.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Consistency Check\n\nNo embedded return block.\n", encoding="utf-8")

    runtime_return = render_gpd_return_block(
        ["GPD/phases/03-conventions/CONSISTENCY-CHECK.md"],
        extra_fields={"phase_checked": "03-conventions", "checks_performed": 3, "issues_found": 0},
    )

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        runtime_return,
        expected_artifacts=["GPD/phases/03-conventions/CONSISTENCY-CHECK.md"],
        allowed_roots=["GPD/phases/03-conventions"],
        required_suffixes=["CONSISTENCY-CHECK.md"],
        require_files_written=True,
        require_status="completed",
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )

    assert result.passed is True
    assert result.mutated is False
    assert result.mutates is False
    assert result.status == "completed"
    assert result.files_written == ["GPD/phases/03-conventions/CONSISTENCY-CHECK.md"]
    assert result.checked_files == ["GPD/phases/03-conventions/CONSISTENCY-CHECK.md"]
    assert "gpd_return:" not in report_path.read_text(encoding="utf-8")


def test_execute_phase_consistency_stops_render_from_stage_stop_routes() -> None:
    workflow = _read_execute_phase_stage("consistency-check.md")

    assert_semantic_contract(
        workflow,
        "consistency stops populate stage_stop before rendering",
        "consistency-check stop",
        "stage_stop",
        "before rendering",
    )
    expected_rows = {
        "checker spawn/error": (
            "blocked",
            "consistency_checker_unavailable",
            "consistency_check",
            "gpd:validate-conventions",
        ),
        "checker checkpoint": ("checkpoint", "consistency_checker_checkpoint", "consistency_check", "gpd:resume-work"),
        "checker blocked": ("blocked", "consistency_checker_blocked", "consistency_check", "gpd:validate-conventions"),
        "checker failed": ("failed", "consistency_checker_failed", "consistency_check", "gpd:validate-conventions"),
        "malformed output": (
            "blocked",
            "consistency_checker_malformed_output",
            "consistency_check",
            "gpd:validate-conventions",
        ),
    }
    for stop, (status, reason, checkpoint, command) in expected_rows.items():
        row = _stage_stop_row(workflow, stop)
        assert row["stage_stop.status"] == status
        assert row["reason"] == reason
        assert row["checkpoint"] == checkpoint
        assert row["next_runtime_command"] == command
    assert_machine_contract(
        workflow,
        "consistency next-up command token",
        "Primary: `{stage_stop.next_runtime_command}`",
    )
