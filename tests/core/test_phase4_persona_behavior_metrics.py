"""Provider-free behavior metric tests for Phase 4 persona rows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.command_labels import runtime_public_command_prefixes
from gpd.core.command_run_hints import KIND_RUNTIME_COMMAND_LABEL, KIND_UNKNOWN_DISPLAY_ONLY
from gpd.core.handoff_artifacts import validate_handoff_artifacts_markdown
from tests.helpers.persona_trace import FakePersonaTrace, FakePersonaTurn
from tests.helpers.phase4_persona.behavior_metrics import (
    BEHAVIOR_METRIC_CLASS_KEYS,
    BEHAVIOR_METRIC_COUNT_KEYS,
    BEHAVIOR_METRIC_COUNT_MAP_KEYS,
    BehaviorMetricBounds,
    classify_command_suggestion,
    classify_mutation_guard,
    classify_next_up_specificity,
    classify_schema_wrestling,
    merge_behavior_scores,
    score_behavior_metrics,
)


@dataclass(frozen=True, slots=True)
class SyntheticRow:
    row_id: str = "SYN-BEH-01"
    surface: str = "execution"
    scenario: str = "synthetic_behavior_metric"
    expected_result_class: str = "blocked"
    expected_next_action_class: str = "retry_child_return"
    mutation_allowed: bool = False


@dataclass(frozen=True, slots=True)
class SyntheticOutcome:
    finding_id: str
    result_class: str
    accepted: bool = False
    ready: bool | None = None
    mutated: bool = False
    state_status_class: str | None = None
    next_action_class: str | None = None
    failure_classes: tuple[str, ...] = ()
    evidence_classes: tuple[str, ...] = ()
    checked_artifact_classes: tuple[str, ...] = ()
    applied_operations: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SyntheticEvent:
    question_bucket_classes: tuple[str, ...] = ()
    event_class_counts: dict[str, int] | None = None
    user_answer_class: str = "not_applicable"
    gate_class: str = "not_applicable"


def _assert_metric_counts(score: object, expected: dict[str, int]) -> None:
    assert {key: score.metric_counts[key] for key in expected} == expected


def _assert_metric_classes(score: object, expected: dict[str, str]) -> None:
    assert {key: score.metric_classes[key] for key in expected} == expected


def _runtime_command(slug: str, *args: str) -> str:
    prefix = runtime_public_command_prefixes()[0]
    suffix = f" {' '.join(args)}" if args else ""
    return f"{prefix}{slug}{suffix}"


def _valid_return_block() -> str:
    return (
        "```yaml\n"
        "gpd_return:\n"
        "  status: completed\n"
        "  files_written: [GPD/phases/02-analysis/02-02-SUMMARY.md]\n"
        "  issues: []\n"
        "  next_actions: []\n"
        "```\n"
    )


def test_behavior_score_shape_is_class_only_with_expected_keys() -> None:
    score = score_behavior_metrics(
        SyntheticRow(),
        SyntheticOutcome(
            finding_id="return_missing",
            result_class="retry_child",
            failure_classes=("return_missing",),
            next_action_class="retry_child_return",
        ),
    )

    assert tuple(score.metric_counts) == BEHAVIOR_METRIC_COUNT_KEYS
    assert tuple(score.metric_classes) == BEHAVIOR_METRIC_CLASS_KEYS
    assert tuple(score.metric_count_maps) == BEHAVIOR_METRIC_COUNT_MAP_KEYS
    assert score.metric_counts["schema_repair_loop_count"] == 1
    _assert_metric_counts(
        score,
        {
            "physics_progress_count": 0,
            "schema_surface_count": 0,
            "conversation_turn_count": 0,
        },
    )
    assert score.metric_classes["schema_wrestling_class"] == "minor"
    assert score.metric_classes["smoothness_class"] == "acceptable"
    assert score.metric_classes["next_up_specificity_class"] == "concrete_command"
    _assert_metric_classes(
        score,
        {
            "first_useful_action_class": "not_applicable",
            "stop_integrity_class": "not_applicable",
            "physics_to_schema_ratio_class": "not_applicable",
            "artifact_handle_first_class": "not_applicable",
        },
    )
    assert set(score.structured_authority_sources) >= {"return_envelope", "return_repair_classifier"}
    assert all(isinstance(value, int) for value in score.metric_counts.values())
    assert all(isinstance(value, str) for value in score.metric_classes.values())
    assert all(isinstance(value, int) for count_map in score.metric_count_maps.values() for value in count_map.values())


def test_command_suggestion_classifier_uses_core_hint_classes() -> None:
    assert classify_command_suggestion(_runtime_command("verify-work", "02"), expected_action="verify-work") == (
        KIND_RUNTIME_COMMAND_LABEL
    )
    assert (
        classify_command_suggestion("gpd verify phase 02", expected_action="verify-work", phase="02")
        == "structural_verify_phase"
    )
    assert classify_command_suggestion("python -m gpd.cli suggest | tee out.txt") == KIND_UNKNOWN_DISPLAY_ONLY


@pytest.mark.parametrize("descriptor", iter_runtime_descriptors(), ids=lambda descriptor: descriptor.runtime_name)
def test_command_suggestion_classifier_accepts_each_active_runtime_verify_work_label(descriptor) -> None:
    command = f"{descriptor.public_command_surface_prefix}verify-work 02"

    assert (
        classify_command_suggestion(command, expected_action="verify-work", phase="02") == KIND_RUNTIME_COMMAND_LABEL
    )


def test_verify_work_session_router_no_phase_routes_are_runtime_only() -> None:
    router = (Path(__file__).resolve().parents[2] / "src/gpd/specs/workflows/verify-work/session-router.md").read_text(
        encoding="utf-8"
    )

    assert "No-phase routing is choice-only:" in router
    assert "active sessions present: ask the user to choose one numbered session" in router
    assert "no active sessions present: ask for a phase and show the runtime route `gpd:verify-work <phase>`" in router
    assert "replaces shell loops over `GPD/phases`" in router
    assert "never render `gpd verify phase` or bare `gpd-verify-work`" in router
    assert 'PHASE_INFO=$(gpd --raw roadmap get-phase "${PHASE_ARG}")' in router
    assert '"${phase_number}"' not in router
    for forbidden_discovery in ("ls GPD/phases", "find GPD/phases", "for phase in GPD/phases"):
        assert forbidden_discovery not in router


def test_invalid_final_command_counts_regression_but_corrected_block_does_not() -> None:
    bad_final = score_behavior_metrics(
        SyntheticRow(expected_next_action_class="runtime_verify_work"),
        SyntheticOutcome(
            finding_id="runtime_verify_work_suggestion",
            result_class="ready_for_runtime_verification",
            next_action_class="runtime_verify_work",
            commands=("gpd verify phase 02",),
        ),
    )
    corrected_block = score_behavior_metrics(
        SyntheticRow(expected_next_action_class="active_runtime_verify_work"),
        SyntheticOutcome(
            finding_id="invalid_verify_command_surface",
            result_class="blocked",
            failure_classes=("invalid_verify_command_surface", "unknown_display_only"),
            next_action_class="active_runtime_verify_work",
        ),
    )

    assert bad_final.metric_counts["invalid_command_suggestion_count"] == 1
    assert bad_final.metric_classes["smoothness_class"] == "regressed"
    assert corrected_block.metric_counts["invalid_command_suggestion_count"] == 0
    assert corrected_block.metric_classes["next_up_specificity_class"] == "runtime_verify_work"


def test_schema_repair_source_text_classes_use_return_classifier() -> None:
    unfenced = score_behavior_metrics(
        SyntheticRow(),
        SyntheticOutcome("unfenced_candidate", "retry_child", next_action_class="retry_child_return"),
        source_text=("gpd_return:\n  status: completed\n  files_written: []\n  issues: []\n  next_actions: []\n"),
    )
    ambiguous = score_behavior_metrics(
        SyntheticRow(),
        SyntheticOutcome("ambiguous_multiple_returns", "blocked", next_action_class="retry_child_return"),
        source_text=f"{_valid_return_block()}\n{_valid_return_block()}",
    )

    assert unfenced.metric_counts["schema_repair_loop_count"] == 1
    assert unfenced.metric_classes["schema_wrestling_class"] == "minor"
    assert ambiguous.metric_counts["schema_repair_loop_count"] == 2
    assert ambiguous.metric_classes["schema_wrestling_class"] == "high"
    assert classify_schema_wrestling(("valid",)) == "none"


def test_stale_artifact_blocks_trust_with_real_artifact_gate(tmp_path: Path) -> None:
    artifact_rel = "GPD/phases/02-analysis/02-02-SUMMARY.md"
    phase_dir = tmp_path / "GPD" / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)
    artifact = phase_dir / "02-02-SUMMARY.md"
    artifact.write_text("# Stale summary\n", encoding="utf-8")
    stale_time = datetime.now(tz=UTC) - timedelta(hours=2)
    os.utime(artifact, (stale_time.timestamp(), stale_time.timestamp()))
    result = validate_handoff_artifacts_markdown(
        tmp_path,
        (
            "```yaml\n"
            "gpd_return:\n"
            "  status: completed\n"
            f"  files_written: [{artifact_rel}]\n"
            "  issues: []\n"
            "  next_actions: []\n"
            "```\n"
        ),
        expected_artifacts=[artifact_rel],
        allowed_roots=["GPD/phases/02-analysis"],
        required_suffixes=["-SUMMARY.md"],
        require_files_written=True,
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )
    row = SyntheticRow(
        row_id="P4-S-03", scenario="stale_files_written", expected_next_action_class="retry_fresh_artifact"
    )
    outcome = SyntheticOutcome(
        finding_id=str(result.primary_failure_class),
        result_class="blocked",
        accepted=result.passed,
        mutated=result.mutated,
        failure_classes=tuple(str(failure_class) for failure_class in result.failure_classes)
        + tuple(failure.code for failure in result.failures),
        state_status_class="unchanged",
        next_action_class="retry_fresh_artifact",
    )

    score = score_behavior_metrics(row, outcome)

    assert result.passed is False
    assert score.metric_counts["stale_artifact_trust_count"] == 0
    assert score.metric_counts["prose_claim_mismatch_count"] == 0
    assert "artifact_gate" in score.structured_authority_sources
    assert score.metric_classes["smoothness_class"] == "acceptable"


def test_unsafe_stale_artifact_acceptance_counts_mismatch_and_danger() -> None:
    score = score_behavior_metrics(
        SyntheticRow(surface="completion", expected_result_class="ready_closeout"),
        SyntheticOutcome(
            finding_id="artifact_stale",
            result_class="ready_closeout",
            accepted=True,
            ready=True,
            state_status_class="unchanged",
            failure_classes=("artifact_stale",),
            next_action_class="phase_complete",
        ),
    )

    assert score.metric_counts["stale_artifact_trust_count"] == 1
    assert score.metric_counts["prose_claim_mismatch_count"] == 1
    assert score.metric_classes["schema_wrestling_class"] == "danger"
    assert score.metric_classes["smoothness_class"] == "regressed"


def test_duplicate_questions_and_mutation_guard_are_counted_from_classes() -> None:
    duplicate_question = score_behavior_metrics(
        SyntheticRow(surface="user_steering", expected_next_action_class="gpd_execute_phase"),
        SyntheticOutcome(
            finding_id="alignment_answer_required",
            result_class="blocked_before_execution",
            failure_classes=("alignment_answer_required", "ask_user_answer_missing"),
            next_action_class="gpd_execute_phase",
        ),
        event=SyntheticEvent(
            question_bucket_classes=("ask_user_alignment", "ask_user_alignment", "closeout_next_up"),
            user_answer_class="missing",
        ),
    )
    rejected_write = score_behavior_metrics(
        SyntheticRow(expected_next_action_class="retry_child_return"),
        SyntheticOutcome(
            finding_id="return_missing",
            result_class="blocked",
            accepted=False,
            mutated=True,
            failure_classes=("return_missing",),
            next_action_class="retry_child_return",
        ),
    )

    assert duplicate_question.metric_counts["duplicate_question_bucket_count"] == 1
    assert duplicate_question.metric_counts["question_before_action_count"] == 1
    assert duplicate_question.metric_classes["mutation_guard_class"] == "no_write"
    assert rejected_write.metric_counts["unexpected_write_count"] == 1
    assert rejected_write.metric_classes["mutation_guard_class"] == "state_mutated_on_reject"
    assert rejected_write.metric_classes["smoothness_class"] == "regressed"


def test_next_up_specificity_and_mutation_guard_classes() -> None:
    assert classify_next_up_specificity(None) == "none"
    assert classify_next_up_specificity("ready_to_continue") == "vague"
    assert classify_next_up_specificity("runtime_verify_work") == "runtime_verify_work"
    assert classify_next_up_specificity("bounded_segment_resume") == "bounded_resume"
    assert classify_next_up_specificity("local_phase_complete") == "concrete_command"
    assert classify_next_up_specificity("review_stop") == "concrete_command"
    assert classify_mutation_guard(False, False) == "no_write"
    assert classify_mutation_guard(True, True) == "expected_write_only"
    assert classify_mutation_guard(True, False, accepted=False, result_class="blocked") == "state_mutated_on_reject"
    assert classify_mutation_guard(True, False, accepted=True, result_class="accepted") == "unexpected_write"


def test_metric_bounds_and_score_merge_are_class_only() -> None:
    bounds = BehaviorMetricBounds(
        "schema_repair_loop_count",
        min_count=1,
        max_count=2,
        allowed_classes=("minor", "high"),
    )
    score_a = score_behavior_metrics(
        SyntheticRow(row_id="SYN-A"),
        SyntheticOutcome(
            "return_missing", "retry_child", failure_classes=("return_missing",), next_action_class="retry_child"
        ),
    )
    score_b = score_behavior_metrics(
        SyntheticRow(row_id="SYN-B", expected_next_action_class="runtime_verify_work"),
        SyntheticOutcome(
            "runtime_verify_work_suggestion",
            "ready_for_runtime_verification",
            next_action_class="runtime_verify_work",
            commands=("gpd verify phase 02",),
        ),
    )

    merged = merge_behavior_scores(score_a, score_b)

    assert bounds.allows_count(score_a.metric_counts["schema_repair_loop_count"]) is True
    assert bounds.allows_class(score_a.metric_classes["schema_wrestling_class"]) is True
    assert merged.row_id == "merged"
    assert merged.metric_counts["invalid_command_suggestion_count"] == 1
    assert merged.metric_classes["smoothness_class"] == "regressed"
    assert merged.passed is False


def test_fake_persona_trace_counts_progress_schema_turns_and_event_maps() -> None:
    trace = FakePersonaTrace(
        row_id="SYN_TRACE_01",
        persona_class="executor",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="phase_scoping",
                action_class="runtime_command",
                physics_progress_class="phase_scoped",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="contract_check",
                action_class="concrete_command",
                schema_surface_class="yaml_return_requested",
            ),
            FakePersonaTurn(
                turn_index=2,
                speaker_class="assistant",
                intent_class="artifact_check",
                action_class="runtime_command",
                physics_progress_class="artifact_verified",
            ),
        ),
    )

    score = score_behavior_metrics(
        SyntheticRow(expected_next_action_class="runtime_verify_work"),
        SyntheticOutcome(
            finding_id="phase_scoped",
            result_class="ready_for_runtime_verification",
            next_action_class="runtime_verify_work",
            evidence_classes=("workflow_stage_manifest",),
            commands=(_runtime_command("verify-work", "02"),),
        ),
        event=trace,
    )
    merged = merge_behavior_scores(score, score)

    _assert_metric_counts(
        score,
        {
            "physics_progress_count": 2,
            "schema_surface_count": 1,
            "conversation_turn_count": 3,
        },
    )
    _assert_metric_classes(
        score,
        {
            "first_useful_action_class": "immediate_command",
            "physics_to_schema_ratio_class": "progress_dominant",
        },
    )
    assert score.metric_count_maps["event_class_counts"]["phase_scoped"] == 1
    assert score.metric_count_maps["event_class_counts"]["yaml_return_requested"] == 1
    assert score.metric_count_maps["question_bucket_counts"] == {}
    assert score.metric_classes["smoothness_class"] == "smooth"
    assert merged.metric_counts["physics_progress_count"] == 4
    assert merged.metric_count_maps["event_class_counts"]["phase_scoped"] == 2


def test_format_thrash_schema_first_without_progress_is_clunky() -> None:
    trace = FakePersonaTrace(
        row_id="SYN_TRACE_FORMAT_THRASH",
        persona_class="schema_averse_researcher",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="contract_check",
                action_class="format_contract",
                schema_surface_class="yaml_return_requested",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="contract_check",
                action_class="format_contract",
                schema_surface_class="return_envelope_requested",
            ),
        ),
    )

    score = score_behavior_metrics(
        SyntheticRow(expected_next_action_class="retry_child_return"),
        SyntheticOutcome(
            finding_id="schema_surface_only",
            result_class="blocked",
            next_action_class="retry_child_return",
            evidence_classes=("workflow_stage_manifest",),
        ),
        event=trace,
    )

    _assert_metric_counts(
        score,
        {
            "schema_surface_count": 2,
            "physics_progress_count": 0,
            "conversation_turn_count": 2,
        },
    )
    _assert_metric_classes(
        score,
        {
            "first_useful_action_class": "missing",
            "physics_to_schema_ratio_class": "schema_dominant",
            "smoothness_class": "clunky",
        },
    )
    assert score.passed is False


def test_single_schema_repair_followed_by_useful_action_remains_acceptable() -> None:
    trace = FakePersonaTrace(
        row_id="SYN_TRACE_SINGLE_REPAIR",
        persona_class="executor",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="return_repair",
                action_class="format_repair",
                schema_surface_class="return_envelope_repair",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="phase_scoping",
                action_class="runtime_command",
                physics_progress_class="phase_scoped",
            ),
        ),
    )

    score = score_behavior_metrics(
        SyntheticRow(expected_next_action_class="runtime_verify_work"),
        SyntheticOutcome(
            finding_id="return_missing",
            result_class="progress_recorded",
            failure_classes=("return_missing",),
            next_action_class="runtime_verify_work",
            evidence_classes=("workflow_stage_manifest",),
            commands=(_runtime_command("verify-work", "02"),),
        ),
        event=trace,
    )

    _assert_metric_counts(
        score,
        {
            "schema_repair_loop_count": 1,
            "schema_surface_count": 1,
            "physics_progress_count": 1,
            "conversation_turn_count": 2,
        },
    )
    _assert_metric_classes(
        score,
        {
            "schema_wrestling_class": "minor",
            "first_useful_action_class": "delayed",
            "physics_to_schema_ratio_class": "balanced",
            "smoothness_class": "acceptable",
        },
    )
    assert score.passed is True


def test_format_thrash_repeated_questions_use_existing_duplicate_counter() -> None:
    trace = FakePersonaTrace(
        row_id="SYN_TRACE_DUPLICATE_QUESTION_FORMAT",
        persona_class="planner",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="alignment_check",
                action_class="ask_user",
                question_bucket_class="ask_user_alignment",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="alignment_check",
                action_class="ask_user",
                question_bucket_class="ask_user_alignment",
            ),
            FakePersonaTurn(
                turn_index=2,
                speaker_class="assistant",
                intent_class="phase_scoping",
                action_class="runtime_command",
                physics_progress_class="phase_scoped",
            ),
        ),
    )

    score = score_behavior_metrics(
        SyntheticRow(expected_next_action_class="gpd_execute_phase"),
        SyntheticOutcome(
            finding_id="duplicate_alignment_question",
            result_class="progress_recorded",
            next_action_class="gpd_execute_phase",
            evidence_classes=("workflow_stage_manifest",),
        ),
        event=trace,
    )

    assert score.metric_count_maps["question_bucket_counts"] == {"ask_user_alignment": 2}
    _assert_metric_counts(score, {"duplicate_question_bucket_count": 1, "physics_progress_count": 1})
    _assert_metric_classes(
        score,
        {
            "first_useful_action_class": "delayed",
            "physics_to_schema_ratio_class": "progress_dominant",
            "smoothness_class": "clunky",
        },
    )


def test_fake_persona_trace_question_buckets_remain_class_only() -> None:
    trace = FakePersonaTrace(
        row_id="SYN_TRACE_QUESTION",
        persona_class="user_steering",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="alignment_check",
                action_class="ask_user",
                question_bucket_class="ask_user_alignment",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="alignment_check",
                action_class="ask_user",
                question_bucket_class="ask_user_alignment",
            ),
        ),
    )

    score = score_behavior_metrics(
        SyntheticRow(surface="user_steering", expected_next_action_class="gpd_execute_phase"),
        SyntheticOutcome(
            finding_id="alignment_answer_required",
            result_class="blocked_before_execution",
            failure_classes=("alignment_answer_required", "ask_user_answer_missing"),
            next_action_class="gpd_execute_phase",
        ),
        event=trace,
    )

    assert score.metric_count_maps["question_bucket_counts"] == {"ask_user_alignment": 2}
    _assert_metric_counts(score, {"duplicate_question_bucket_count": 1, "question_before_action_count": 1})
    _assert_metric_classes(score, {"first_useful_action_class": "missing", "smoothness_class": "clunky"})


def test_fake_persona_trace_stop_integrity_scores_clean_and_post_stop_activity() -> None:
    clean_stop = FakePersonaTrace(
        row_id="SYN_TRACE_STOP",
        persona_class="user_steering",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="abort_acknowledged",
                action_class="stop",
                stop_class="user_abort_stops_dispatch",
            ),
        ),
    )
    post_stop = FakePersonaTrace(
        row_id="SYN_TRACE_STOP_BAD",
        persona_class="user_steering",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="abort_acknowledged",
                action_class="stop",
                stop_class="user_abort_stops_dispatch",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="kept_working",
                action_class="runtime_command",
                physics_progress_class="phase_scoped",
            ),
        ),
    )
    outcome = SyntheticOutcome(
        finding_id="user_abort_stops_dispatch",
        result_class="stopped_before_dispatch",
        failure_classes=("user_abort_stops_dispatch", "executor_dispatch_blocked"),
        next_action_class="stop",
    )

    clean_score = score_behavior_metrics(SyntheticRow(surface="user_steering"), outcome, event=clean_stop)
    post_stop_score = score_behavior_metrics(SyntheticRow(surface="user_steering"), outcome, event=post_stop)

    _assert_metric_counts(clean_score, {"post_stop_activity_count": 0})
    _assert_metric_classes(
        clean_score,
        {"stop_integrity_class": "stopped_cleanly", "first_useful_action_class": "safe_stop"},
    )
    _assert_metric_counts(post_stop_score, {"post_stop_activity_count": 1})
    _assert_metric_classes(
        post_stop_score,
        {"stop_integrity_class": "post_stop_activity", "smoothness_class": "regressed"},
    )


def test_fake_persona_trace_scores_reload_hydration_and_handle_first_behavior() -> None:
    base_row = SyntheticRow(expected_next_action_class="runtime_verify_work")
    base_outcome = SyntheticOutcome(
        finding_id="workflow_stage_manifest",
        result_class="ready_for_runtime_verification",
        next_action_class="runtime_verify_work",
        evidence_classes=("workflow_stage_manifest",),
        commands=(_runtime_command("verify-work", "02"),),
    )
    raw_reload_trace = FakePersonaTrace(
        row_id="SYN_TRACE_RAW_RELOAD",
        persona_class="planner",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="reload_guidance",
                action_class="next_up_command",
                reload_surface_class="raw_reload_instruction_visible",
            ),
        ),
    )
    content_first_trace = FakePersonaTrace(
        row_id="SYN_TRACE_CONTENT_FIRST",
        persona_class="planner",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="reference_review",
                action_class="concrete_command",
                physics_progress_class="artifact_verified",
                content_hydration_class="content_loaded",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="reference_choice",
                action_class="select_reference",
                artifact_handle_class="handle_selected",
            ),
        ),
    )
    handle_first_trace = FakePersonaTrace(
        row_id="SYN_TRACE_HANDLE_FIRST",
        persona_class="planner",
        prompt_variant_class="provider_free_canary",
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="reference_choice",
                action_class="select_reference",
                artifact_handle_class="handle_selected",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="reference_review",
                action_class="concrete_command",
                physics_progress_class="artifact_verified",
                content_hydration_class="content_loaded",
            ),
        ),
    )

    raw_reload_score = score_behavior_metrics(base_row, base_outcome, event=raw_reload_trace)
    content_first_score = score_behavior_metrics(base_row, base_outcome, event=content_first_trace)
    handle_first_score = score_behavior_metrics(base_row, base_outcome, event=handle_first_trace)

    _assert_metric_counts(raw_reload_score, {"raw_reload_leakage_count": 1})
    _assert_metric_classes(raw_reload_score, {"smoothness_class": "regressed"})
    _assert_metric_counts(content_first_score, {"content_hydration_before_selection_count": 1})
    _assert_metric_classes(
        content_first_score,
        {"artifact_handle_first_class": "content_before_handle", "smoothness_class": "clunky"},
    )
    _assert_metric_counts(handle_first_score, {"content_hydration_before_selection_count": 0})
    _assert_metric_classes(handle_first_score, {"artifact_handle_first_class": "handle_before_content"})


def test_fake_persona_turn_rejects_raw_text_and_paths() -> None:
    with pytest.raises(ValueError):
        FakePersonaTurn(
            turn_index=0,
            speaker_class="assistant",
            intent_class="bad token",
            action_class="runtime_command",
        )
    with pytest.raises(ValueError):
        FakePersonaTrace(
            row_id="tmp/not-class-token.txt",
            persona_class="planner",
            prompt_variant_class="provider_free_canary",
            turns=(),
        )
