"""Artifact handoff validation for spawned-agent returns."""

from __future__ import annotations

import json
import os
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.handoff_artifacts import HandoffFailureClass, validate_handoff_artifacts_markdown
from tests.return_skeleton_support import render_gpd_return_block as _return_block


def _files_only_return_block(files_written: list[str]) -> str:
    files_written_yaml = (
        "  files_written: []\n"
        if not files_written
        else "  files_written:\n" + "\n".join(f"    - {json.dumps(path)}" for path in files_written) + "\n"
    )
    return f"```yaml\ngpd_return:\n{files_written_yaml}```\n"


def _blocked_return_with_state_updates() -> str:
    return (
        "```yaml\n"
        "gpd_return:\n"
        "  status: blocked\n"
        "  files_written: []\n"
        "  issues: []\n"
        "  next_actions: []\n"
        "  state_updates:\n"
        "    phase: 1\n"
        "```\n"
    )


def _raw_checkpoint_return_with_extra_yaml(extra_yaml: str) -> str:
    indented_extra_yaml = textwrap.indent(textwrap.dedent(extra_yaml).lstrip("\n"), "  ")
    return (
        "```yaml\n"
        "gpd_return:\n"
        "  status: checkpoint\n"
        "  files_written: []\n"
        "  issues: []\n"
        "  next_actions: []\n"
        f"{indented_extra_yaml}"
        "```\n"
    )


def test_handoff_artifact_validator_rejects_multiple_return_blocks_before_artifact_checks(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")
    content = (
        _return_block(["GPD/phases/01-test/01-01-PLAN.md"]) + "\n" + _return_block(["GPD/phases/01-test/01-02-PLAN.md"])
    )

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        content,
        expected_artifacts=["GPD/phases/01-test/01-01-PLAN.md"],
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
        require_files_written=True,
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.status is None
    assert result.files_written == []
    assert result.checked_files == []
    assert result.primary_failure_class == HandoffFailureClass.RETURN_MALFORMED_BLOCKING
    assert result.failure_classes == [HandoffFailureClass.RETURN_MALFORMED_BLOCKING]
    assert result.failures[0].code == "ambiguous_multiple_returns"
    assert result.failures[0].repairable is False
    assert result.errors == ["Multiple gpd_return YAML blocks found: expected exactly one, got 2"]


def test_handoff_artifact_validator_rejects_raw_files_only_json_envelope(tmp_path: Path) -> None:
    result = validate_handoff_artifacts_markdown(
        tmp_path,
        json.dumps({"gpd_return": {"files_written": ["GPD/phases/01-test/01-01-PLAN.md"]}}),
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
        require_files_written=True,
    )

    assert result.passed is False
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class == HandoffFailureClass.RETURN_MISSING
    assert result.failure_classes == [HandoffFailureClass.RETURN_MISSING]
    assert result.failures[0].code == "missing_gpd_return_block"
    assert "No gpd_return YAML block found" in result.errors


def test_handoff_artifact_validator_classifies_prose_only_success_as_missing_return(tmp_path: Path) -> None:
    result = validate_handoff_artifacts_markdown(
        tmp_path,
        "# Result\n\nCompleted successfully. The requested artifact is ready.\n",
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
        require_files_written=True,
    )

    assert result.passed is False
    assert result.status is None
    assert result.files_written == []
    assert result.checked_files == []
    assert result.primary_failure_class == HandoffFailureClass.RETURN_MISSING
    assert result.failure_classes == [HandoffFailureClass.RETURN_MISSING]
    assert result.failures[0].code == "missing_gpd_return_block"
    assert "No gpd_return YAML block found" in result.errors


def test_handoff_artifact_validator_preserves_missing_route_for_unfenced_return_candidate(tmp_path: Path) -> None:
    result = validate_handoff_artifacts_markdown(
        tmp_path,
        (
            "gpd_return:\n"
            "  status: completed\n"
            "  files_written: [GPD/phases/01-test/01-01-PLAN.md]\n"
            "  issues: []\n"
            "  next_actions: []\n"
        ),
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
        require_files_written=True,
    )

    assert result.passed is False
    assert result.status is None
    assert result.files_written == []
    assert result.checked_files == []
    assert result.primary_failure_class == HandoffFailureClass.RETURN_MISSING
    assert result.failure_classes == [HandoffFailureClass.RETURN_MISSING]
    assert result.failures[0].code == "missing_gpd_return_block"
    assert "No gpd_return YAML block found" in result.errors


def test_handoff_artifact_validator_rejects_fenced_files_only_envelope(tmp_path: Path) -> None:
    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _files_only_return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
        require_files_written=True,
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.RETURN_MALFORMED_REPAIRABLE
    assert result.failure_classes == [HandoffFailureClass.RETURN_MALFORMED_REPAIRABLE]
    assert {failure.code for failure in result.failures} == {"missing_required_field"}
    assert all(failure.repairable for failure in result.failures)
    assert "Missing required field: status" in result.errors
    assert "Missing required field: issues" in result.errors
    assert "Missing required field: next_actions" in result.errors


def test_handoff_artifact_validator_classifies_status_disallowed_update_as_malformed_blocking(
    tmp_path: Path,
) -> None:
    result = validate_handoff_artifacts_markdown(tmp_path, _blocked_return_with_state_updates())

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.RETURN_MALFORMED_BLOCKING
    assert result.failure_classes == [HandoffFailureClass.RETURN_MALFORMED_BLOCKING]
    assert result.failures[0].code == "status_disallowed_field"
    assert "status 'blocked' does not allow gpd_return field(s): state_updates" in result.errors


@pytest.mark.parametrize(
    ("extra_yaml", "expected_fragments"),
    [
        (
            """
            continuation_update:
              handoff:
                resume_file: GPD/phases/01-test/.continue-here.md
                stopped_at: Paused for review
                recorded_by: execute-plan
            """,
            ("recorded_by", "applicator-owned"),
        ),
        (
            """
            continuation_update:
              bounded_segment:
                resume_file: GPD/phases/01-test/.continue-here.md
                segment_status: paused
                updated_at: 2026-05-08T12:00:00Z
            """,
            ("updated_at", "applicator-owned"),
        ),
    ],
)
def test_handoff_artifact_validator_classifies_applicator_owned_metadata_as_blocking(
    tmp_path: Path,
    extra_yaml: str,
    expected_fragments: tuple[str, str],
) -> None:
    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _raw_checkpoint_return_with_extra_yaml(extra_yaml),
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.RETURN_MALFORMED_BLOCKING
    assert result.failure_classes == [HandoffFailureClass.RETURN_MALFORMED_BLOCKING]
    assert result.failures[0].code == "applicator_owned_metadata"
    assert result.failures[0].repairable is False
    assert all(fragment in result.errors[0] for fragment in expected_fragments)


def test_handoff_artifact_validator_leaves_direct_complete_phase_state_update_to_applicator(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "GPD" / "phases" / "02-analysis" / "02-01-SUMMARY.md"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text("# Summary\n", encoding="utf-8")

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block(
            ["GPD/phases/02-analysis/02-01-SUMMARY.md"],
            extra_fields={
                "phase": "02",
                "plan": "01",
                "state_updates": {"complete_phase": True},
            },
        ),
        expected_artifacts=["GPD/phases/02-analysis/02-01-SUMMARY.md"],
        allowed_roots=["GPD/phases/02-analysis"],
        required_suffixes=["-SUMMARY.md"],
        require_files_written=True,
        require_status="completed",
    )

    assert result.passed is True
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class is None
    assert result.failure_classes == []
    assert result.errors == []
    assert result.checked_files == ["GPD/phases/02-analysis/02-01-SUMMARY.md"]


def test_handoff_artifact_validator_accepts_fresh_in_scope_expected_plan(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("---\nplan_id: 01-01\n---\n", encoding="utf-8")

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        expected_artifacts=["GPD/phases/01-test/01-01-PLAN.md"],
        expected_globs=["GPD/phases/01-test/*-PLAN.md"],
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
        require_files_written=True,
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )

    assert result.passed is True
    assert result.mutated is False
    assert result.mutates is False
    assert result.primary_failure_class is None
    assert result.failure_classes == []
    assert result.failures == []
    assert result.checked_files == ["GPD/phases/01-test/01-01-PLAN.md"]


def test_handoff_artifact_validator_require_completed_rejects_non_completed_status(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("---\nplan_id: 01-01\n---\n", encoding="utf-8")

    for status in ("checkpoint", "blocked", "failed"):
        result = validate_handoff_artifacts_markdown(
            tmp_path,
            _return_block(["GPD/phases/01-test/01-01-PLAN.md"], status=status),
            expected_artifacts=["GPD/phases/01-test/01-01-PLAN.md"],
            allowed_roots=["GPD/phases/01-test"],
            required_suffixes=["-PLAN.md"],
            require_files_written=True,
            require_status="completed",
        )

        assert result.passed is False
        assert result.mutates is False
        assert result.status == status
        assert result.primary_failure_class == HandoffFailureClass.RETURN_STATUS_ROUTE
        assert result.failure_classes == [HandoffFailureClass.RETURN_STATUS_ROUTE]
        assert result.failures[0].code == "required_status_mismatch"
        assert f"gpd_return.status must be 'completed' for this artifact gate, got '{status}'" in result.errors


def test_handoff_artifact_validator_rejects_missing_claimed_artifact(tmp_path: Path) -> None:
    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
        require_files_written=True,
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_MISSING
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_MISSING]
    assert result.failures[0].code == "artifact_missing_or_not_file"
    assert "artifact is missing or not a file: GPD/phases/01-test/01-01-PLAN.md" in result.errors


def test_handoff_artifact_validator_rejects_out_of_scope_and_absolute_paths(tmp_path: Path) -> None:
    out_of_scope = tmp_path / "GPD" / "other" / "01-01-PLAN.md"
    out_of_scope.parent.mkdir(parents=True)
    out_of_scope.write_text("plan\n", encoding="utf-8")

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block(["GPD/other/01-01-PLAN.md", str(out_of_scope)]),
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_ROOT_BLOCKED
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_ROOT_BLOCKED]
    assert {failure.code for failure in result.failures} == {"outside_allowed_roots", "absolute_outside_allowed_roots"}
    assert "artifact path is outside allowed roots: GPD/other/01-01-PLAN.md" in result.errors
    assert any("artifact path must be project-local, not absolute" in error for error in result.errors)


def test_handoff_artifact_validator_classifies_absolute_project_path_as_path_repairable(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block([plan_path.as_posix()]),
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_PATH_REPAIRABLE
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_PATH_REPAIRABLE]
    assert result.failures[0].code == "absolute_project_local"
    assert result.failures[0].repairable is True
    assert any("artifact path must be project-local, not absolute" in error for error in result.errors)


def test_handoff_artifact_validator_classifies_absolute_outside_project_as_root_blocked(tmp_path: Path) -> None:
    outside_path = tmp_path.parent / f"{tmp_path.name}-outside-PLAN.md"

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block([outside_path.as_posix()]),
        allowed_roots=["."],
        required_suffixes=["-PLAN.md"],
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_ROOT_BLOCKED
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_ROOT_BLOCKED]
    assert result.failures[0].code == "absolute_outside_project"
    assert any("artifact path must be project-local, not absolute" in error for error in result.errors)


def test_handoff_artifact_validator_classifies_traversal_as_root_blocked(tmp_path: Path) -> None:
    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block(["GPD/phases/01-test/../outside/01-01-PLAN.md"]),
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_ROOT_BLOCKED
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_ROOT_BLOCKED]
    assert result.failures[0].code == "path_traversal"
    assert "artifact path must not traverse outside the project: GPD/phases/01-test/../outside/01-01-PLAN.md" in (
        result.errors
    )


def test_handoff_artifact_validator_classifies_allowed_root_outside_project_as_root_blocked(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        allowed_roots=["../outside"],
        required_suffixes=["-PLAN.md"],
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_ROOT_BLOCKED
    assert HandoffFailureClass.ARTIFACT_ROOT_BLOCKED in result.failure_classes
    assert "allowed_root_outside_project" in {failure.code for failure in result.failures}
    assert "allowed root is outside project root: ../outside" in result.errors


def test_handoff_artifact_validator_rejects_expected_artifact_omitted_from_files_written(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block([]),
        expected_artifacts=["GPD/phases/01-test/01-01-PLAN.md"],
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
        require_files_written=True,
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_MISSING
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_MISSING]
    assert {failure.code for failure in result.failures} == {"files_written_empty", "expected_artifact_omitted"}
    assert "gpd_return.files_written is empty" in result.errors
    assert "expected artifact not named in gpd_return.files_written: GPD/phases/01-test/01-01-PLAN.md" in result.errors


def test_handoff_artifact_validator_rejects_stale_artifact(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")
    stale_time = datetime.now(tz=UTC) - timedelta(hours=2)
    os.utime(plan_path, (stale_time.timestamp(), stale_time.timestamp()))

    result = validate_handoff_artifacts_markdown(
        tmp_path,
        _return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        allowed_roots=["GPD/phases/01-test"],
        required_suffixes=["-PLAN.md"],
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )

    assert result.passed is False
    assert result.primary_failure_class == HandoffFailureClass.ARTIFACT_STALE
    assert result.failure_classes == [HandoffFailureClass.ARTIFACT_STALE]
    assert result.failures[0].code == "artifact_stale"
    assert "artifact is stale relative to --fresh-after: GPD/phases/01-test/01-01-PLAN.md" in result.errors


def test_validate_handoff_artifacts_cli_accepts_stdin_return(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "validate",
            "handoff-artifacts",
            "-",
            "--allowed-root",
            "GPD/phases/01-test",
            "--expected-glob",
            "GPD/phases/01-test/*-PLAN.md",
            "--required-suffix=-PLAN.md",
            "--require-files-written",
        ],
        input=_return_block(["GPD/phases/01-test/01-01-PLAN.md"]),
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["passed"] is True
    assert payload["mutated"] is False
    assert payload["mutates"] is False
    assert payload["primary_failure_class"] is None
    assert payload["failure_classes"] == []
    assert payload["failures"] == []


def test_validate_handoff_artifacts_cli_require_status_completed_rejects_checkpoint(tmp_path: Path) -> None:
    plan_path = tmp_path / "GPD" / "phases" / "01-test" / "01-01-PLAN.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("plan\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "validate",
            "handoff-artifacts",
            "-",
            "--allowed-root",
            "GPD/phases/01-test",
            "--expected-glob",
            "GPD/phases/01-test/*-PLAN.md",
            "--required-suffix=-PLAN.md",
            "--require-files-written",
            "--require-status",
            "completed",
        ],
        input=_return_block(["GPD/phases/01-test/01-01-PLAN.md"], status="checkpoint"),
        catch_exceptions=False,
    )

    payload = json.loads(result.output)
    assert result.exit_code == 1
    assert payload["passed"] is False
    assert payload["mutated"] is False
    assert payload["mutates"] is False
    assert payload["primary_failure_class"] == "return_status_route"
    assert payload["failure_classes"] == ["return_status_route"]
    assert payload["failures"][0]["code"] == "required_status_mismatch"
    assert payload["status"] == "checkpoint"
    assert "gpd_return.status must be 'completed' for this artifact gate, got 'checkpoint'" in payload["errors"]
