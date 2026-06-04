"""Focused tests for read-only child handoff validation."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_args

from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.child_handoff import (
    AcceptanceState,
    ChildGateApplicator,
    ChildGateArtifact,
    ChildGateFreshness,
    ChildGateTuple,
    render_child_gate_markdown,
    validate_child_handoff,
)
from gpd.core.handoff_artifacts import HandoffFailureClass
from tests.return_skeleton_support import render_gpd_return_block as _return_block


def _files_only_return_block(files_written: list[str]) -> str:
    files_written_yaml = (
        "  files_written: []\n"
        if not files_written
        else "  files_written:\n" + "\n".join(f"    - {json.dumps(path)}" for path in files_written) + "\n"
    )
    return f"```yaml\ngpd_return:\n{files_written_yaml}```\n"


def _gate(
    *,
    expected_artifacts: tuple[ChildGateArtifact, ...] = (),
    allowed_roots: tuple[str, ...] = (".",),
    freshness: ChildGateFreshness | None = None,
    validators: tuple[str, ...] = (),
    applicator: ChildGateApplicator | None = None,
    status_route: dict[str, str] | None = None,
    write_allowlist: tuple[str, ...] = (),
) -> ChildGateTuple:
    return ChildGateTuple(
        id="planner_initial_plan",
        role="gpd-planner",
        required_status="completed",
        expected_artifacts=expected_artifacts,
        allowed_roots=allowed_roots,
        freshness=freshness,
        validators=validators,
        applicator=applicator or ChildGateApplicator(command="none"),
        status_route=status_route or {"completed": "accept_success"},
        write_allowlist=write_allowlist,
        failure_route={
            "return_missing": "retry_once",
            "return_malformed_repairable": "repair_prompt_once",
            "return_malformed_blocking": "fail_closed",
            "return_status_route": "route_by_status",
            "artifact_missing": "retry_once",
            "artifact_stale": "retry_once",
            "artifact_path_repairable": "repair_path_once",
            "artifact_root_blocked": "fail_closed",
            "validator_failed": "revision_loop",
            "applicator_failed": "fail_closed",
        },
    )


def _gate_markdown(gate: ChildGateTuple) -> str:
    return render_child_gate_markdown(gate)


def test_child_handoff_acceptance_state_values_are_explicit_contract() -> None:
    assert get_args(AcceptanceState) == (
        "failed",
        "status_routed",
        "read_only_passed_needs_applicator",
        "accepted",
    )


def test_child_handoff_accepts_valid_readable_artifact(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")

    result = validate_child_handoff(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        _gate(
            expected_artifacts=(ChildGateArtifact(path="GPD/phases/01-test/01-01-PLAN.md"),),
            allowed_roots=("GPD/phases/01-test",),
            validators=("readable",),
        ),
    )

    assert result.passed is True
    assert result.mutated is False
    assert result.mutates is False
    assert result.read_only_passed is True
    assert result.requires_applicator_pass is False
    assert result.acceptance_complete is True
    assert result.acceptance_state == "accepted"
    assert result.applicator_required_unrun is False
    assert result.primary_failure_class is None
    assert result.failure_classes == []
    assert result.selected_route == "accept_success"
    assert result.next_action_class == "accept_success"
    assert result.validator_results[0].passed is True


def test_child_handoff_classifies_missing_return_without_mutation(tmp_path: Path) -> None:
    result = validate_child_handoff(tmp_path, "no return here\n", _gate())

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class == HandoffFailureClass.RETURN_MISSING
    assert result.failure_classes == [HandoffFailureClass.RETURN_MISSING]
    assert result.failures[0].code == "missing_gpd_return_block"
    assert result.read_only_passed is False
    assert result.acceptance_complete is False
    assert result.acceptance_state == "failed"
    assert result.selected_route == "retry_once"


def test_child_handoff_classifies_malformed_return_without_mutation(tmp_path: Path) -> None:
    result = validate_child_handoff(
        tmp_path,
        _files_only_return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        _gate(),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class == HandoffFailureClass.RETURN_MALFORMED_REPAIRABLE
    assert result.failure_classes == [HandoffFailureClass.RETURN_MALFORMED_REPAIRABLE]
    assert result.acceptance_state == "failed"
    assert result.selected_route == "repair_prompt_once"


def test_child_handoff_classifies_missing_artifact_without_mutation(tmp_path: Path) -> None:
    result = validate_child_handoff(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        _gate(
            expected_artifacts=(ChildGateArtifact(path="GPD/phases/01-test/01-01-PLAN.md"),),
            allowed_roots=("GPD/phases/01-test",),
        ),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_MISSING
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_MISSING]
    assert result.acceptance_state == "failed"
    assert result.selected_route == "retry_once"


def test_child_handoff_classifies_stale_artifact_without_mutation(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")
    stale_time = datetime.now(tz=UTC) - timedelta(hours=2)
    os.utime(plan_path, (stale_time.timestamp(), stale_time.timestamp()))

    result = validate_child_handoff(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        _gate(allowed_roots=("GPD/phases/01-test",)),
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_STALE
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_STALE]
    assert result.failures[0].code == "artifact_stale"
    assert result.acceptance_state == "failed"
    assert result.selected_route == "retry_once"


def test_child_handoff_fails_closed_when_tuple_freshness_requires_missing_cutoff(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")

    result = validate_child_handoff(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        _gate(
            expected_artifacts=(ChildGateArtifact(path="GPD/phases/01-test/01-01-PLAN.md"),),
            allowed_roots=("GPD/phases/01-test",),
            freshness=ChildGateFreshness(
                marker="$PLANNER_HANDOFF_STARTED_AT",
                require_mtime_at_or_after_marker=True,
            ),
        ),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.read_only_passed is False
    assert result.acceptance_complete is False
    assert result.acceptance_state == "failed"
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_STALE
    assert result.failures[0].code == "freshness_requires_fresh_after"
    assert result.selected_route == "retry_once"


def test_child_handoff_classifies_outside_root_artifact_without_mutation(tmp_path: Path) -> None:
    outside_path = tmp_path / "GPD" / "other" / "01-01-PLAN.md"
    outside_path.parent.mkdir(parents=True)
    outside_path.write_text("plan\n", encoding="utf-8")

    result = validate_child_handoff(
        tmp_path,
        _return_block(["GPD/other/01-01-PLAN.md"]),
        _gate(allowed_roots=("GPD/phases/01-test",)),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_ROOT_BLOCKED
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_ROOT_BLOCKED]
    assert result.acceptance_state == "failed"


def test_child_handoff_rejects_files_written_outside_write_allowlist(tmp_path: Path) -> None:
    artifact_path = tmp_path / "GPD" / "artifact.md"
    extra_path = tmp_path / "GPD" / "extra.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("artifact\n", encoding="utf-8")
    extra_path.write_text("extra\n", encoding="utf-8")

    result = validate_child_handoff(
        tmp_path,
        _return_block(["GPD/artifact.md", "GPD/extra.md"]),
        _gate(
            expected_artifacts=(ChildGateArtifact(path="GPD/artifact.md"),),
            allowed_roots=("GPD",),
            write_allowlist=("GPD/artifact.md",),
        ),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_ROOT_BLOCKED
    assert result.failures[0].code == "outside_write_allowlist"
    assert result.failures[0].path == "GPD/extra.md"
    assert result.acceptance_state == "failed"
    assert result.selected_route == "fail_closed"


def test_child_handoff_classifies_absolute_project_path_as_repairable_without_mutation(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")

    result = validate_child_handoff(
        tmp_path,
        _return_block([plan_path.as_posix()]),
        _gate(allowed_roots=("GPD/phases/01-test",)),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_PATH_REPAIRABLE
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_PATH_REPAIRABLE]
    assert result.acceptance_state == "failed"
    assert result.selected_route == "repair_path_once"


def test_child_handoff_classifies_validator_failure_without_mutation(tmp_path: Path) -> None:
    section_path = tmp_path / "paper" / "intro.tex"
    section_path.parent.mkdir(parents=True)
    section_path.write_text("", encoding="utf-8")

    result = validate_child_handoff(
        tmp_path,
        _return_block(["paper/intro.tex"]),
        _gate(allowed_roots=("paper",), validators=("paper-section-readable",)),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class == HandoffFailureClass.VALIDATOR_FAILED
    assert result.failure_classes == [HandoffFailureClass.VALIDATOR_FAILED]
    assert result.validator_results[0].passed is False
    assert result.acceptance_state == "failed"
    assert result.selected_route == "revision_loop"


def test_child_handoff_rejects_unknown_validator_text_without_execution(tmp_path: Path) -> None:
    artifact_path = tmp_path / "GPD" / "artifact.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("artifact\n", encoding="utf-8")
    marker = tmp_path / "SHOULD_NOT_EXIST"

    result = validate_child_handoff(
        tmp_path,
        _return_block(["GPD/artifact.md"]),
        _gate(validators=(f"sh -c 'touch {marker.as_posix()}'",)),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert marker.exists() is False
    assert result.primary_failure_class == HandoffFailureClass.VALIDATOR_FAILED
    assert result.failures[0].code == "unsupported_validator"
    assert result.acceptance_state == "failed"


def test_child_handoff_routes_valid_non_required_statuses_without_artifact_acceptance(tmp_path: Path) -> None:
    gate = _gate(
        expected_artifacts=(ChildGateArtifact(path="GPD/phases/01-test/01-01-PLAN.md"),),
        allowed_roots=("GPD/phases/01-test",),
        status_route={
            "completed": "accept_success",
            "checkpoint": "present_checkpoint",
            "blocked": "surface_blocker",
            "failed": "surface_failure",
        },
    )

    for status, route in (
        ("checkpoint", "present_checkpoint"),
        ("blocked", "surface_blocker"),
        ("failed", "surface_failure"),
    ):
        result = validate_child_handoff(
            tmp_path,
            _return_block(["GPD/phases/01-test/01-01-PLAN.md"], status=status),
            gate,
        )

        assert result.passed is False
        assert result.mutated is False
        assert result.mutates is False
        assert result.read_only_passed is False
        assert result.acceptance_complete is False
        assert result.primary_failure_class is None
        assert result.failure_classes == []
        assert result.failures == []
        assert result.checked_files == []
        assert result.status == status
        assert result.acceptance_state == "status_routed"
        assert result.status_route_used is True
        assert result.status_route_reason is not None
        assert "valid but does not satisfy required success status 'completed'" in result.status_route_reason
        assert "Artifact, validator, and applicator acceptance were not run" in result.status_route_reason
        assert result.selected_route == route
        assert result.next_action_class == route


def test_child_handoff_profile_payload_routes_checkpoint_before_artifact_or_applicator(tmp_path: Path) -> None:
    gate_payload = {
        "child_gate": {
            "id": "wave_executor_plan_result",
            "profile": "execute.executor_summary.v1",
            "artifact": "GPD/phases/01-test/01-01-SUMMARY.md",
            "allowed_root": "GPD/phases/01-test",
            "freshness_marker": "$EXECUTOR_HANDOFF_STARTED_AT",
        }
    }

    result = validate_child_handoff(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-SUMMARY.md"], status="checkpoint"),
        gate_payload,
    )

    assert result.passed is False
    assert result.acceptance_state == "status_routed"
    assert result.status_route_used is True
    assert result.selected_route == "checkpoint_resume"
    assert result.checked_files == []
    assert result.validator_results == []
    assert result.requires_applicator_pass is True
    assert result.applicator_command == "gpd --raw apply-return-updates GPD/phases/01-test/01-01-SUMMARY.md"
    assert result.applicator_ran is False


def test_child_handoff_reports_applicator_required_read_only_acceptance_gap(tmp_path: Path) -> None:
    summary_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-SUMMARY.md"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text("summary\n", encoding="utf-8")

    result = validate_child_handoff(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-SUMMARY.md"]),
        _gate(
            expected_artifacts=(ChildGateArtifact(path="GPD/phases/01-test/01-01-SUMMARY.md"),),
            allowed_roots=("GPD/phases/01-test",),
            applicator=ChildGateApplicator(
                command="gpd --raw apply-return-updates GPD/phases/01-test/01-01-SUMMARY.md",
                require_passed_true=True,
            ),
        ),
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.read_only_passed is True
    assert result.requires_applicator_pass is True
    assert result.acceptance_complete is False
    assert result.acceptance_state == "read_only_passed_needs_applicator"
    assert result.acceptance_state != "accepted"
    assert result.applicator_required_unrun is True
    assert result.applicator_ran is False
    assert result.primary_failure_class == HandoffFailureClass.APPLICATOR_FAILED
    assert result.failure_classes == [HandoffFailureClass.APPLICATOR_FAILED]
    assert result.failures[0].code == "applicator_required_unrun"
    assert result.selected_route == "fail_closed"
    assert any("child-handoff validation is read-only; applicator" in warning for warning in result.warnings)


def test_validate_child_handoff_cli_accepts_combined_stdin(tmp_path: Path) -> None:
    artifact_path = tmp_path / "GPD" / "artifact.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("artifact\n", encoding="utf-8")
    gate = _gate(
        expected_artifacts=(ChildGateArtifact(path="GPD/artifact.md"),),
        allowed_roots=("GPD",),
        validators=("readable",),
    )

    result = CliRunner().invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "validate",
            "child-handoff",
            "--gate",
            "-",
            "--return-file",
            "-",
        ],
        input=_gate_markdown(gate) + "\n" + _return_block(["GPD/artifact.md"]),
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["passed"] is True
    assert payload["mutated"] is False
    assert payload["mutates"] is False
    assert payload["read_only_passed"] is True
    assert payload["acceptance_complete"] is True
    assert payload["acceptance_state"] == "accepted"
    assert payload["validator_results"][0]["passed"] is True
    assert payload["selected_route"] == "accept_success"


def test_validate_child_handoff_cli_exits_nonzero_when_applicator_required(tmp_path: Path) -> None:
    artifact_path = tmp_path / "GPD" / "artifact.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("artifact\n", encoding="utf-8")
    gate = _gate(
        expected_artifacts=(ChildGateArtifact(path="GPD/artifact.md"),),
        allowed_roots=("GPD",),
        applicator=ChildGateApplicator(
            command="gpd --raw apply-return-updates GPD/artifact.md",
            require_passed_true=True,
        ),
    )

    result = CliRunner().invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "validate",
            "child-handoff",
            "--gate",
            "-",
            "--return-file",
            "-",
        ],
        input=_gate_markdown(gate) + "\n" + _return_block(["GPD/artifact.md"]),
        catch_exceptions=False,
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["passed"] is False
    assert payload["read_only_passed"] is True
    assert payload["acceptance_complete"] is False
    assert payload["acceptance_state"] == "read_only_passed_needs_applicator"
    assert payload["applicator_required_unrun"] is True
    assert payload["primary_failure_class"] == "applicator_failed"
