"""Focused assertions for the canonical ``gpd_return`` contract."""

from __future__ import annotations

from dataclasses import fields

from gpd.core.return_contract import (
    REQUIRED_RETURN_FIELDS,
    GpdReturnEnvelope,
    GpdReturnStatusContract,
    validate_gpd_return_markdown,
)
from tests.return_skeleton_support import render_gpd_return_block


def _wrap_return_block(yaml_body: str) -> str:
    return f"```yaml\ngpd_return:\n{yaml_body}```\n"


def test_status_contract_does_not_carry_dead_required_fields() -> None:
    assert [field.name for field in fields(GpdReturnStatusContract)] == ["structured_fields"]


def test_required_return_fields_derive_from_envelope_model() -> None:
    assert REQUIRED_RETURN_FIELDS == tuple(
        field_name for field_name, field_info in GpdReturnEnvelope.model_fields.items() if field_info.is_required()
    )


def test_accepts_nested_state_and_continuation_payloads() -> None:
    content = render_gpd_return_block(
        ["src/main.py"],
        status="checkpoint",
        next_actions=["gpd:resume-work"],
        extra_fields={
            "state_updates": {
                "advance_plan": True,
                "update_progress": True,
            },
            "continuation_update": {
                "handoff": {
                    "stopped_at": "Completed phase 01",
                    "resume_file": "GPD/phases/01-test-phase/.continue-here.md",
                },
                "bounded_segment": {
                    "resume_file": "GPD/phases/01-test-phase/.continue-here.md",
                    "phase": "01",
                    "plan": "01",
                    "segment_id": "seg-01",
                    "segment_status": "paused",
                    "checkpoint_reason": "segment_boundary",
                },
            },
        },
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is True
    assert result.fields["state_updates"]["advance_plan"] is True
    assert result.fields["state_updates"]["update_progress"] is True
    assert result.fields["continuation_update"]["handoff"]["stopped_at"] == "Completed phase 01"
    assert result.fields["continuation_update"]["bounded_segment"]["segment_id"] == "seg-01"


def test_accepts_checkpoint_intent_as_child_authored_pause_intent() -> None:
    content = render_gpd_return_block(
        [],
        status="checkpoint",
        next_actions=["gpd:resume-work"],
        extra_fields={
            "phase": "01",
            "plan": "02",
            "checkpoint_intent": {
                "checkpoint_reason": "pre_fanout",
                "waiting_reason": "Review the first result before dependent fanout.",
                "waiting_for_review": True,
            },
        },
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is True
    assert result.fields["checkpoint_intent"] == {
        "checkpoint_reason": "pre_fanout",
        "waiting_reason": "Review the first result before dependent fanout.",
        "waiting_for_review": True,
    }
    assert "continuation_update" not in result.fields
    assert "resume_file" not in str(result.fields["checkpoint_intent"])


def test_accepts_typed_checker_plan_lists() -> None:
    content = render_gpd_return_block(
        [],
        status="checkpoint",
        next_actions=["gpd:plan-phase"],
        extra_fields={
            "approved_plans": ["plan-01", "plan-03"],
            "blocked_plans": ["plan-02"],
        },
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is True
    assert result.fields["approved_plans"] == ["plan-01", "plan-03"]
    assert result.fields["blocked_plans"] == ["plan-02"]


def test_rejects_scalar_where_list_field_is_required() -> None:
    content = _wrap_return_block(
        "  status: completed\n  files_written: src/main.py\n  issues: []\n  next_actions: [gpd:verify-work]\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any("files_written" in error and "list" in error for error in result.errors)


def test_rejects_uppercase_status_instead_of_propagating_case_drift() -> None:
    content = _wrap_return_block("  status: COMPLETED\n  files_written: []\n  issues: []\n  next_actions: []\n")

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert result.envelope is None
    assert any("canonical lowercase" in error for error in result.errors)


def test_rejects_malformed_checker_plan_lists() -> None:
    content = _wrap_return_block(
        "  status: checkpoint\n"
        "  files_written: []\n"
        "  issues: []\n"
        "  next_actions: [gpd:plan-phase]\n"
        "  approved_plans: plan-01\n"
        "  blocked_plans:\n"
        "    - plan-02\n"
        "    - 3\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any("approved_plans" in error and "list" in error for error in result.errors)
    assert any("blocked_plans" in error and "string" in error for error in result.errors)


def test_rejects_state_updates_when_not_a_mapping() -> None:
    content = _wrap_return_block(
        "  status: checkpoint\n"
        "  files_written: [src/main.py]\n"
        "  issues: []\n"
        "  next_actions: [gpd:resume-work]\n"
        "  state_updates:\n"
        "    - advance_plan: true\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any("state_updates" in error and "mapping" in error for error in result.errors)


def test_rejects_unknown_top_level_typo_fields() -> None:
    content = _wrap_return_block(
        "  status: completed\n"
        "  file_written: [src/main.py]\n"
        "  files_written: [src/main.py]\n"
        "  issues: []\n"
        "  next_actions: []\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any("Unknown gpd_return top-level field" in error and "file_written" in error for error in result.errors)


def test_rejects_multiple_canonical_return_blocks_as_ambiguous() -> None:
    content = (
        render_gpd_return_block(["GPD/phases/02-analysis/02-02-SUMMARY.md"])
        + "\n"
        + render_gpd_return_block(
            [],
            status="blocked",
            issues=["conflicting return"],
            next_actions=["gpd:resume-work"],
            extra_fields={"blockers": ["conflicting return"]},
        )
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert result.envelope is None
    assert result.fields == {}
    assert result.errors == ["Multiple gpd_return YAML blocks found: expected exactly one, got 2"]


def test_rejects_child_reports_as_callsite_evidence_not_return_field() -> None:
    content = _wrap_return_block(
        "  status: completed\n"
        "  files_written: [GPD/phases/02-analysis/02-02-SUMMARY.md]\n"
        "  issues: []\n"
        "  next_actions: []\n"
        "  child_reports:\n"
        "    - GPD/phases/02-analysis/02-02-SUMMARY.md\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any("Unknown gpd_return top-level field" in error and "child_reports" in error for error in result.errors)


def test_accepts_child_reports_omitted_from_applicator_envelope() -> None:
    content = render_gpd_return_block(["GPD/phases/02-analysis/02-02-SUMMARY.md"])

    result = validate_gpd_return_markdown(content)

    assert result.passed is True
    assert "child_reports" not in result.fields


def test_rejects_peer_review_stage_as_callsite_metadata_not_return_field() -> None:
    content = _wrap_return_block(
        "  status: completed\n"
        "  files_written: [GPD/publication/review/STAGE-reader.json]\n"
        "  issues: []\n"
        "  next_actions: []\n"
        "  peer_review_stage: reader\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any(
        "Unknown gpd_return top-level field" in error and "peer_review_stage" in error for error in result.errors
    )


def test_rejects_status_disallowed_structured_fields() -> None:
    content = _wrap_return_block(
        "  status: blocked\n"
        "  files_written: []\n"
        "  issues: [missing checkpoint]\n"
        "  next_actions: [gpd:resume-work]\n"
        "  state_updates:\n"
        "    advance_plan: true\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any("status 'blocked'" in error and "state_updates" in error for error in result.errors)


def test_rejects_transport_execution_segment_inside_durable_continuation_update() -> None:
    content = _wrap_return_block(
        "  status: checkpoint\n"
        "  files_written: [src/main.py]\n"
        "  issues: []\n"
        "  next_actions: [gpd:resume-work]\n"
        "  continuation_update:\n"
        "    execution_segment:\n"
        "      current_cursor: 3\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any("continuation_update" in error and "execution_segment" in error for error in result.errors)


def test_rejects_unknown_fields_inside_durable_continuation_update_payloads() -> None:
    nested_payloads = {
        "handoff": (
            "    handoff:\n"
            "      resume_file: GPD/phases/01-test-phase/.continue-here.md\n"
            "      stopped_at: Completed phase 01\n"
            "      extra_durable_owner: child\n"
        ),
        "bounded_segment": (
            "    bounded_segment:\n"
            "      resume_file: GPD/phases/01-test-phase/.continue-here.md\n"
            '      phase: "01"\n'
            '      plan: "01"\n'
            "      segment_id: seg-01\n"
            "      segment_status: paused\n"
            "      extra_durable_owner: child\n"
        ),
    }

    for nested_field, nested_yaml in nested_payloads.items():
        content = _wrap_return_block(
            "  status: checkpoint\n"
            "  files_written: [src/main.py]\n"
            "  issues: []\n"
            "  next_actions: [gpd:resume-work]\n"
            "  continuation_update:\n"
            f"{nested_yaml}"
        )

        result = validate_gpd_return_markdown(content)

        assert result.passed is False
        assert any(
            "continuation_update" in error and nested_field in error and "extra_durable_owner" in error
            for error in result.errors
        )


def test_rejects_applicator_owned_handoff_metadata_inside_child_return() -> None:
    content = _wrap_return_block(
        "  status: checkpoint\n"
        "  files_written: [src/main.py]\n"
        "  issues: []\n"
        "  next_actions: [gpd:resume-work]\n"
        "  continuation_update:\n"
        "    handoff:\n"
        "      recorded_at: 2026-04-08T12:00:00Z\n"
        "      recorded_by: execute-plan\n"
        "      stopped_at: Completed phase 01\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any(
        "recorded_at" in error and "recorded_by" in error and "applicator-owned" in error for error in result.errors
    )


def test_rejects_applicator_owned_bounded_segment_metadata_inside_child_return() -> None:
    content = _wrap_return_block(
        "  status: checkpoint\n"
        "  files_written: [src/main.py]\n"
        "  issues: []\n"
        "  next_actions: [gpd:resume-work]\n"
        "  continuation_update:\n"
        "    bounded_segment:\n"
        "      resume_file: GPD/phases/01-test-phase/.continue-here.md\n"
        '      phase: "01"\n'
        '      plan: "01"\n'
        "      segment_id: seg-01\n"
        "      segment_status: paused\n"
        "      updated_at: 2026-04-08T12:00:00Z\n"
        "      recorded_by: execute-plan\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any(
        "updated_at" in error and "recorded_by" in error and "applicator-owned" in error for error in result.errors
    )


def test_rejects_applicator_owned_checkpoint_intent_metadata_inside_child_return() -> None:
    applicator_owned_fields = {
        "last_result_id": "result-01",
        "recorded_by": "execute-plan",
        "resume_file": "GPD/phases/01-test-phase/.continue-here.md",
        "source_session_id": "session-01",
        "updated_at": "2026-04-08T12:00:00Z",
    }

    for field_name, field_value in applicator_owned_fields.items():
        content = _wrap_return_block(
            "  status: checkpoint\n"
            "  files_written: []\n"
            "  issues: []\n"
            "  next_actions: [gpd:resume-work]\n"
            "  checkpoint_intent:\n"
            "    checkpoint_reason: pre_fanout\n"
            "    waiting_reason: Review the first result before dependent fanout.\n"
            f'    {field_name}: "{field_value}"\n'
        )

        result = validate_gpd_return_markdown(content)

        assert result.passed is False
        assert any(field_name in error and "applicator-owned checkpoint_intent" in error for error in result.errors)


def test_rejects_scalar_where_continuation_update_requires_mapping() -> None:
    content = _wrap_return_block(
        "  status: blocked\n"
        "  files_written: []\n"
        "  issues: []\n"
        "  next_actions: []\n"
        "  blockers:\n"
        "    - missing input data\n"
        "  continuation_update: checkpoint\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any("continuation_update" in error for error in result.errors)


def test_accepts_synthesizer_style_completed_return_with_summary_only_file_list() -> None:
    content = render_gpd_return_block(["GPD/literature/SUMMARY.md"])

    result = validate_gpd_return_markdown(content)

    assert result.passed is True
    assert result.fields["status"] == "completed"
    assert result.fields["files_written"] == ["GPD/literature/SUMMARY.md"]
    assert result.fields["issues"] == []
    assert result.fields["next_actions"] == []
