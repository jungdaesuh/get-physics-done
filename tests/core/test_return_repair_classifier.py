"""Focused tests for read-only ``gpd_return`` repair classification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpd.core.return_repair_classifier import (
    REPAIRABLE_RETURN_CLASSES,
    classify_gpd_return_repair,
    return_failure_class_from_repair_class,
    return_repair_class_from_validation_error,
    return_repair_hint,
)
from gpd.core.state import default_state_dict, generate_state_markdown
from tests.return_skeleton_support import render_gpd_return_block

REPO_ROOT = Path(__file__).resolve().parents[2]


def _wrap_return_block(yaml_body: str) -> str:
    return f"# Child output\n\n```yaml\ngpd_return:\n{yaml_body}```\n"


def _valid_completed_return() -> str:
    return "# Child output\n\n" + render_gpd_return_block(
        ["GPD/phases/01-test/SUMMARY.md"],
        extra_fields={"duration_seconds": 1},
    )


def test_classifies_valid_completed_return_as_accepted_without_mutation() -> None:
    result = classify_gpd_return_repair(_valid_completed_return())

    assert result.valid is True
    assert result.accepted_for_success is True
    assert result.primary_class == "valid"
    assert result.primary_failure_class == "valid"
    assert result.failure_classes == []
    assert result.recovery_route == "accept"
    assert result.status == "completed"
    assert result.original_errors == []
    assert result.original_warnings == []
    assert result.mutated is False
    assert result.mutates is False
    assert result.may_patch_child_return is False


def test_classifies_plain_prose_without_candidate_as_missing_block() -> None:
    result = classify_gpd_return_repair("# Summary\n\nNo machine-readable return here.\n")

    assert result.primary_class == "missing_block"
    assert result.recovery_route == "retry_child"
    assert result.original_errors == ["No gpd_return YAML block found"]
    assert result.safe_to_apply is False
    assert result.mutated is False
    assert result.mutates is False


def test_classifies_prose_only_success_claim_as_missing_block() -> None:
    result = classify_gpd_return_repair("# Result\n\nCompleted successfully; no further action needed.\n")

    assert result.primary_class == "missing_block"
    assert result.recovery_route == "retry_child"
    assert result.original_errors == ["No gpd_return YAML block found"]
    assert result.safe_to_apply is False
    assert result.mutated is False


@pytest.mark.parametrize(
    "content",
    [
        ("gpd_return:\n  status: completed\n  files_written: []\n  issues: []\n  next_actions: []\n"),
        ("status: completed\nfiles_written: []\nissues: []\nnext_actions: []\n"),
        json.dumps(
            {
                "gpd_return": {
                    "status": "completed",
                    "files_written": [],
                    "issues": [],
                    "next_actions": [],
                }
            }
        ),
    ],
)
def test_classifies_unfenced_raw_yaml_or_json_candidate(content: str) -> None:
    result = classify_gpd_return_repair(content)

    assert result.primary_class == "unfenced_candidate"
    assert result.repair_hint.startswith("Retry with the candidate return wrapped")


def test_classifies_wrong_language_fenced_json_candidate() -> None:
    result = classify_gpd_return_repair(
        '```json\n{"gpd_return": {"status": "completed", "files_written": [], "issues": [], "next_actions": []}}\n```'
    )

    assert result.primary_class == "wrong_fence_language"
    assert result.recovery_route == "retry_child"


def test_classifies_yaml_parse_error_inside_canonical_block() -> None:
    result = classify_gpd_return_repair("```yaml\ngpd_return:\n  status: [completed\n```\n")

    assert result.primary_class == "yaml_parse_error"
    assert any("YAML parse error" in error for error in result.original_errors)


@pytest.mark.parametrize(
    "content",
    [
        "```yaml\nstatus: completed\nfiles_written: []\nissues: []\nnext_actions: []\n```\n",
        "```yaml\ngpd_return:\n  - status: completed\n```\n",
    ],
)
def test_classifies_top_level_shape_errors(content: str) -> None:
    result = classify_gpd_return_repair(content)

    assert result.primary_class == "top_level_shape_error"


def test_classifies_missing_required_fields() -> None:
    result = classify_gpd_return_repair(_wrap_return_block("  status: completed\n"))

    assert result.primary_class == "missing_required_fields"
    assert set(result.original_errors) >= {
        "Missing required field: files_written",
        "Missing required field: issues",
        "Missing required field: next_actions",
    }


@pytest.mark.parametrize("status", ["COMPLETED", "done"])
def test_classifies_invalid_and_uppercase_status(status: str) -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(f"  status: {status}\n  files_written: []\n  issues: []\n  next_actions: []\n")
    )

    assert result.primary_class == "invalid_status"


def test_classifies_scalar_list_drift() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: completed\n  files_written: GPD/phases/01-test/SUMMARY.md\n  issues: []\n  next_actions: []\n"
        )
    )

    assert result.primary_class == "scalar_list_drift"
    assert "list" in result.original_errors[0]
    assert result.safe_to_apply is False
    assert result.mutated is False
    assert result.mutates is False


def test_classifies_unknown_typo_field() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: completed\n"
            "  file_written: [GPD/phases/01-test/SUMMARY.md]\n"
            "  files_written: [GPD/phases/01-test/SUMMARY.md]\n"
            "  issues: []\n"
            "  next_actions: []\n"
        )
    )

    assert result.primary_class == "unknown_field"
    assert "file_written" in result.original_errors[0]


def test_classifies_status_forbidden_fields_as_blocking() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: blocked\n"
            "  files_written: []\n"
            "  issues: [waiting]\n"
            "  next_actions: []\n"
            "  state_updates:\n"
            "    advance_plan: true\n"
        )
    )

    assert result.primary_class == "status_field_forbidden"
    assert result.recovery_route == "block_and_surface_errors"


def test_classifies_transport_payload_inside_continuation_update() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: checkpoint\n"
            "  files_written: []\n"
            "  issues: []\n"
            "  next_actions: []\n"
            "  continuation_update:\n"
            "    execution_segment:\n"
            "      current_cursor: 3\n"
        )
    )

    assert result.primary_class == "transport_payload_in_return"
    assert result.recovery_route == "block_and_surface_errors"


def test_classifies_applicator_owned_metadata_inside_child_return() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: checkpoint\n"
            "  files_written: []\n"
            "  issues: []\n"
            "  next_actions: []\n"
            "  continuation_update:\n"
            "    bounded_segment:\n"
            "      resume_file: GPD/phases/01-test/.continue-here.md\n"
            "      segment_status: paused\n"
            "      updated_at: 2026-05-08T12:00:00Z\n"
            "      recorded_by: execute-plan\n"
        )
    )

    assert result.primary_class == "applicator_owned_metadata"
    assert result.recovery_route == "block_and_surface_errors"


def test_classifies_continuation_schema_error() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: checkpoint\n"
            "  files_written: []\n"
            "  issues: []\n"
            "  next_actions: []\n"
            "  continuation_update: checkpoint\n"
        )
    )

    assert result.primary_class == "continuation_schema_error"
    assert result.recovery_route == "block_and_surface_errors"


def test_classifies_valid_non_completed_return_without_treating_it_as_malformed() -> None:
    result = classify_gpd_return_repair(
        render_gpd_return_block([], status="checkpoint", next_actions=["gpd resume-work"])
    )

    assert result.valid is True
    assert result.accepted_for_success is False
    assert result.primary_class == "required_status_mismatch"
    assert result.recovery_route == "route_by_status"
    assert result.status == "checkpoint"
    assert return_failure_class_from_repair_class(result.primary_class) == "return_status_route"
    assert result.original_errors == []
    assert result.safe_to_apply is False
    assert result.mutated is False
    assert result.mutates is False


def test_can_accept_non_completed_status_when_required() -> None:
    result = classify_gpd_return_repair(
        render_gpd_return_block([], status="checkpoint", next_actions=["gpd resume-work"]),
        require_status="checkpoint",
    )

    assert result.primary_class == "valid"
    assert result.accepted_for_success is True


def test_classifies_multiple_canonical_blocks_as_ambiguous() -> None:
    result = classify_gpd_return_repair(_valid_completed_return() + "\n" + _valid_completed_return())

    assert result.primary_class == "ambiguous_multiple_returns"
    assert result.valid is False
    assert result.accepted_for_success is False


def test_direct_complete_phase_state_update_is_valid_schema_but_read_only_classification() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: completed\n"
            "  files_written: [GPD/phases/02-analysis/02-01-SUMMARY.md]\n"
            "  issues: []\n"
            "  next_actions: [gpd:verify-work 02]\n"
            '  phase: "02"\n'
            '  plan: "01"\n'
            "  state_updates:\n"
            "    complete_phase: true\n"
        )
    )

    assert result.primary_class == "valid"
    assert result.valid is True
    assert result.accepted_for_success is True
    assert result.fields["state_updates"] == {"complete_phase": True}
    assert result.original_errors == []
    assert result.mutated is False
    assert result.mutates is False


@pytest.mark.parametrize(
    ("error", "content", "repair_class", "failure_class", "repairable"),
    [
        (
            "No gpd_return YAML block found",
            "# Summary\n\nNo machine-readable return here.\n",
            "missing_block",
            "return_missing",
            True,
        ),
        (
            "Missing required field: status",
            None,
            "missing_required_fields",
            "return_malformed_repairable",
            True,
        ),
        (
            "files_written: Input should be a valid list",
            None,
            "scalar_list_drift",
            "return_malformed_repairable",
            True,
        ),
        (
            "Multiple gpd_return YAML blocks found: expected exactly one, got 2",
            None,
            "ambiguous_multiple_returns",
            "return_malformed_blocking",
            False,
        ),
        (
            "status 'blocked' does not allow gpd_return field 'state_updates'",
            None,
            "status_field_forbidden",
            "return_malformed_blocking",
            False,
        ),
        (
            "continuation_update.bounded_segment: updated_at and recorded_by are applicator-owned bounded_segment fields; omit them from child returns",
            None,
            "applicator_owned_metadata",
            "return_malformed_blocking",
            False,
        ),
    ],
)
def test_validation_error_helper_preserves_apply_return_failure_classes(
    error: str,
    content: str | None,
    repair_class: str,
    failure_class: str,
    repairable: bool,
) -> None:
    classified = return_repair_class_from_validation_error(error, content=content)

    assert classified == repair_class
    assert return_failure_class_from_repair_class(classified) == failure_class
    assert (classified in REPAIRABLE_RETURN_CLASSES) is repairable
    assert return_repair_hint(classified)


def test_valid_repair_class_has_no_failure_class() -> None:
    with pytest.raises(ValueError, match="valid returns"):
        return_failure_class_from_repair_class("valid")


def test_classifier_does_not_write_state_files(tmp_path: Path) -> None:
    gpd_dir = tmp_path / "GPD"
    gpd_dir.mkdir()
    state_path = gpd_dir / "state.json"
    state_md_path = gpd_dir / "STATE.md"
    state = default_state_dict()
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    state_md_path.write_text(generate_state_markdown(state), encoding="utf-8")
    before_json = state_path.read_text(encoding="utf-8")
    before_md = state_md_path.read_text(encoding="utf-8")

    result = classify_gpd_return_repair(_valid_completed_return())

    assert result.mutated is False
    assert result.mutates is False
    assert state_path.read_text(encoding="utf-8") == before_json
    assert state_md_path.read_text(encoding="utf-8") == before_md


def test_invalid_required_status_is_rejected_before_classification() -> None:
    with pytest.raises(ValueError, match="required status"):
        classify_gpd_return_repair(_valid_completed_return(), require_status="done")


def test_repairable_return_route_is_single_fenced_yaml_retry_with_no_mutation() -> None:
    result = classify_gpd_return_repair(
        "gpd_return:\n  status: completed\n  files_written: []\n  issues: []\n  next_actions: []\n"
    )

    assert result.primary_class == "unfenced_candidate"
    assert result.recovery_route == "retry_child"
    assert result.repair_hint.count("Retry") == 1
    assert "canonical ```yaml gpd_return block" in result.repair_hint
    assert result.safe_to_apply is False
    assert result.mutated is False
    assert result.may_patch_child_return is False


def test_blocking_return_route_stops_instead_of_repair_loop_or_state_patch() -> None:
    result = classify_gpd_return_repair(
        _wrap_return_block(
            "  status: checkpoint\n"
            "  files_written: []\n"
            "  issues: []\n"
            "  next_actions: []\n"
            "  continuation_update:\n"
            "    bounded_segment:\n"
            "      resume_file: GPD/phases/01-test/.continue-here.md\n"
            "      segment_status: paused\n"
            "      recorded_by: execute-plan\n"
        )
    )

    assert result.primary_class == "applicator_owned_metadata"
    assert result.recovery_route == "block_and_surface_errors"
    assert result.repair_hint.startswith("Stop and surface")
    assert "Retry" not in result.repair_hint
    assert result.safe_to_apply is False
    assert result.mutated is False


def test_executor_completion_routes_shared_state_through_applicator_only() -> None:
    section = _executor_completion_state_update_section()

    assert 'gpd apply-return-updates "${SUMMARY_FILE}"' in section
    assert "retry once only" in section
    assert "fenced `gpd_return` YAML" in section
    assert "do not patch `STATE.md` or `state.json` manually" in section
    assert "gpd state advance" not in section
    assert "state add-decision" not in section
    assert "gpd state add-blocker" not in section
    assert "cat GPD/STATE.md" not in section


def _executor_completion_state_update_section() -> str:
    text = (REPO_ROOT / "src/gpd/specs/references/execution/executor-completion.md").read_text(encoding="utf-8")
    return text.split("## State Updates", maxsplit=1)[1].split("## Completion Format", maxsplit=1)[0]
