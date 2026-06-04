"""Class-only behavior metrics for provider-free Phase 4 persona rows."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from types import MappingProxyType

import tests.helpers.phase4_persona.interaction_events as trace_events
from gpd.command_labels import parse_command_label, runtime_public_command_prefixes
from gpd.core.command_run_hints import (
    KIND_LOCAL_CLI_FINALIZER_COMMAND,
    KIND_LOCAL_CLI_VALIDATION_COMMAND,
    KIND_RUNTIME_COMMAND_LABEL,
    KIND_UNKNOWN_DISPLAY_ONLY,
    NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME,
    NEXT_COMMAND_SURFACE_CONTEXT_SHARED_NEXT_UP,
    build_command_run_hint,
)
from gpd.core.return_repair_classifier import REPAIRABLE_RETURN_CLASSES, classify_gpd_return_repair

BEHAVIOR_METRIC_COUNT_KEYS: tuple[str, ...] = (
    "invalid_command_suggestion_count",
    "schema_repair_loop_count",
    "structured_authority_coverage",
    "prose_claim_mismatch_count",
    "stale_artifact_trust_count",
    "duplicate_question_bucket_count",
    "question_before_action_count",
    "post_stop_activity_count",
    "unexpected_write_count",
    "unsupported_completion_claim_count",
    "physics_progress_count",
    "schema_surface_count",
    "conversation_turn_count",
    "raw_reload_leakage_count",
    "content_hydration_before_selection_count",
)

BEHAVIOR_METRIC_CLASS_KEYS: tuple[str, ...] = (
    "schema_wrestling_class",
    "smoothness_class",
    "next_up_specificity_class",
    "mutation_guard_class",
    "first_useful_action_class",
    "stop_integrity_class",
    "physics_to_schema_ratio_class",
    "artifact_handle_first_class",
)

BEHAVIOR_METRIC_COUNT_MAP_KEYS: tuple[str, ...] = (
    "question_bucket_counts",
    "event_class_counts",
)

STRUCTURED_AUTHORITY_CLASSES: tuple[str, ...] = (
    "command_hint",
    "return_envelope",
    "return_repair_classifier",
    "artifact_gate",
    "child_return_applicator",
    "state_json",
    "verification_status",
    "phase_closeout_readiness",
    "bounded_continuation",
    "workflow_stage_manifest",
    "resume_surface",
    "prompt_diagnostics",
)

_SCHEMA_NONE_CLASSES = frozenset({"valid", "valid_non_completed", "required_status_mismatch", "return_status_route"})
_SCHEMA_MINOR_CLASSES = frozenset(
    {
        "return_missing",
        "missing_block",
        "unfenced_candidate",
        "wrong_fence_language",
        "yaml_parse_error",
        "top_level_shape_error",
        "invalid_status",
        "scalar_list_drift",
        "field_shape_error",
        "return_malformed_repairable",
        *REPAIRABLE_RETURN_CLASSES,
    }
)
_SCHEMA_HIGH_CLASSES = frozenset(
    {
        "ambiguous_multiple_returns",
        "applicator_output_only",
        "applicator_owned_metadata",
        "continuation_schema_error",
        "missing_required_fields",
        "return_malformed_blocking",
        "status_field_forbidden",
        "transport_payload_in_return",
        "unknown_field",
    }
)
_SCHEMA_DANGER_CLASSES = frozenset(
    {
        "closeout_bypass",
        "provider_raw_exposure",
        "prose_state_mismatch",
        "stale_artifact_trust",
        "state_mutated_on_reject",
        "unexpected_write",
        "unsupported_completion_claim",
    }
)
_ARTIFACT_STALE_OR_MISSING_CLASSES = frozenset(
    {
        "artifact_missing",
        "artifact_stale",
        "expected_artifact_omitted",
        "files_written_empty",
        "missing_required_field",
        "wrong_sibling",
    }
)
_UNSUPPORTED_COMPLETION_CLASSES = frozenset(
    {
        "applicator_output_only",
        "canonical_verification_missing",
        "closeout_authority_blocks_premature_completion",
        "missing_verification",
        "non_passing_verification",
        "proof_redteam_not_passed",
        "prose_success_no_return",
        "return_missing",
        "verification_missing",
        "verification_non_passing",
    }
)
_PREMATURE_COMPLETION_ATTEMPT_CLASSES = frozenset(
    {
        "applicator_output_only",
        "closeout_bypass",
        "closeout_authority_blocks_premature_completion",
        "intermediate_plan_completion_blocked",
        "unsupported_completion_claim",
    }
)
_PROSE_CLAIM_ATTEMPT_CLASSES = frozenset(
    {
        "ambiguous_multiple_returns",
        "applicator_output_only",
        "prose_success_no_return",
        "return_malformed_blocking",
        "return_missing",
    }
)
_QUESTION_CLASSES = frozenset(
    {
        "alignment_answer_required",
        "ask_user",
        "ask_user_answer_missing",
        "ask_user_alignment",
        "closeout_offer_next",
        "schema_repair_request",
    }
)
_STOP_CLASSES = frozenset({"abort", "review_stop", "stop", "stopped_before_dispatch", "user_abort_stops_dispatch"})
_VAGUE_NEXT_ACTION_CLASSES = frozenset(
    {"class_only", "continue", "continue_work", "ready", "ready_to_continue", "vague"}
)
_NONE_NEXT_ACTION_CLASSES = frozenset({"", "none", "no_action", "unknown"})
_RUNTIME_VERIFY_NEXT_ACTION_CLASSES = frozenset(
    {
        "active_runtime_verify_work",
        "run_verify_work",
        "runtime_verify_work",
        "verify_work",
    }
)
_BOUNDED_RESUME_NEXT_ACTION_CLASSES = frozenset(
    {
        "bounded_segment_resume",
        "create_bounded_resume_context",
        "gpd_resume_work",
        "resume_work",
    }
)


@dataclass(frozen=True, slots=True)
class BehaviorMetricBounds:
    """Optional class-only expectation for a behavior metric."""

    metric_key: str
    min_count: int | None = None
    max_count: int | None = None
    exact_count: int | None = None
    allowed_classes: tuple[str, ...] = ()

    def allows_count(self, count: int) -> bool:
        if self.exact_count is not None and count != self.exact_count:
            return False
        if self.min_count is not None and count < self.min_count:
            return False
        if self.max_count is not None and count > self.max_count:
            return False
        return True

    def allows_class(self, metric_class: str | None) -> bool:
        return not self.allowed_classes or metric_class in self.allowed_classes


@dataclass(frozen=True, slots=True)
class BehaviorScore:
    """Sanitized behavior score; values are class tokens, counts, and booleans."""

    row_id: str
    surface: str
    scenario: str
    finding_classes: tuple[str, ...]
    metric_counts: Mapping[str, int]
    metric_classes: Mapping[str, str]
    structured_authority_sources: tuple[str, ...]
    passed: bool
    metric_count_maps: Mapping[str, Mapping[str, int]] | None = None

    def __post_init__(self) -> None:
        counts = {key: int(self.metric_counts.get(key, 0)) for key in BEHAVIOR_METRIC_COUNT_KEYS}
        classes = {
            key: str(self.metric_classes.get(key, _default_metric_class(key))) for key in BEHAVIOR_METRIC_CLASS_KEYS
        }
        raw_count_maps = self.metric_count_maps or {}
        count_maps = {
            key: MappingProxyType(_sanitized_count_map(raw_count_maps.get(key, {})))
            for key in BEHAVIOR_METRIC_COUNT_MAP_KEYS
        }
        object.__setattr__(self, "finding_classes", _unique_tokens(self.finding_classes))
        object.__setattr__(self, "metric_counts", MappingProxyType(counts))
        object.__setattr__(self, "metric_classes", MappingProxyType(classes))
        object.__setattr__(self, "metric_count_maps", MappingProxyType(count_maps))
        object.__setattr__(
            self,
            "structured_authority_sources",
            tuple(
                source
                for source in _unique_tokens(self.structured_authority_sources)
                if source in STRUCTURED_AUTHORITY_CLASSES
            ),
        )


def score_behavior_metrics(
    row: object,
    outcome: object,
    *,
    event: object | None = None,
    source_text: str | None = None,
) -> BehaviorScore:
    """Score provider-free behavior using only sanitized classes and core classifiers."""

    row_view = _ObjectView(row)
    outcome_view = _ObjectView(outcome)
    event_view = _ObjectView(event)

    failure_classes = _unique_tokens(
        (
            _string_or_none(outcome_view.get("finding_id")),
            *_tokens(outcome_view.get("failure_classes")),
            *_tokens(outcome_view.get("evidence_classes")),
            *_tokens(outcome_view.get("checked_artifact_classes")),
        )
    )
    source_repair_classes = _source_repair_classes(source_text)
    schema_classes = _unique_tokens((*failure_classes, *source_repair_classes))

    commands = _command_strings(outcome_view.get("commands"))
    next_action_class = _string_or_none(outcome_view.get("next_action_class")) or _string_or_none(
        row_view.get("expected_next_action_class")
    )
    result_class = (
        _string_or_none(outcome_view.get("result_class"))
        or _string_or_none(row_view.get("expected_result_class"))
        or ""
    )
    accepted = _bool_or_none(outcome_view.get("accepted"))
    ready = _bool_or_none(outcome_view.get("ready"))
    mutated = bool(outcome_view.get("mutated", False))
    mutation_allowed = bool(
        row_view.get("mutation_allowed", False)
        or outcome_view.get("mutation_allowed", False)
        or (row_view.get("expect_no_mutation") is False)
    )

    mutation_guard_class = classify_mutation_guard(
        mutated,
        mutation_allowed,
        accepted=accepted,
        ready=ready,
        result_class=result_class,
    )
    invalid_command_count = _invalid_command_suggestion_count(commands, failure_classes, next_action_class)
    schema_loop_count = _schema_repair_loop_count(
        schema_classes,
        accepted=accepted,
        ready=ready,
        mutated=mutated,
    )
    stale_trust_count = _stale_artifact_trust_count(failure_classes, accepted=accepted, ready=ready, mutated=mutated)
    prose_mismatch_count = _prose_state_mismatch_count(
        failure_classes,
        result_class=result_class,
        accepted=accepted,
        ready=ready,
        state_status_class=_string_or_none(outcome_view.get("state_status_class")),
    )
    unsupported_completion_count = _unsupported_completion_claim_count(
        failure_classes,
        scenario=str(row_view.get("scenario", "")),
        result_class=result_class,
        accepted=accepted,
        ready=ready,
    )
    question_bucket_count_map = dict(trace_events.question_bucket_counts(event))
    event_class_count_map = dict(trace_events.event_class_counts(event))
    first_useful_action_class = trace_events.first_useful_action_class(event)
    duplicate_question_count = _duplicate_question_bucket_count(
        event_view,
        question_bucket_counts=question_bucket_count_map,
        event_class_counts=event_class_count_map,
    )
    question_before_action_count = _question_before_action_count(
        failure_classes,
        event_view,
        first_useful_action_class=first_useful_action_class,
    )
    trace_stop_integrity = trace_events.stop_integrity_class(event)
    post_stop_activity_count = _post_stop_activity_count(
        failure_classes,
        result_class=result_class,
        next_action_class=next_action_class,
        mutated=mutated,
        accepted=accepted,
        applied_operations=_tokens(outcome_view.get("applied_operations")),
    )
    if trace_stop_integrity == "post_stop_activity":
        post_stop_activity_count = max(1, post_stop_activity_count)
    physics_progress_count = trace_events.physics_progress_count(event)
    schema_surface_count = trace_events.schema_surface_count(event)
    conversation_turn_count = trace_events.conversation_turn_count(event)
    raw_reload_leakage_count = trace_events.raw_reload_leakage_count(event) + _source_raw_reload_leakage_count(
        source_text
    )
    content_hydration_before_selection_count = trace_events.content_hydration_before_selection_count(event)
    unexpected_write_count = 1 if mutation_guard_class in {"unexpected_write", "state_mutated_on_reject"} else 0
    authority_sources = _structured_authority_sources(
        outcome_view,
        event_view,
        failure_classes=failure_classes,
        commands=commands,
        next_action_class=next_action_class,
        source_repair_classes=source_repair_classes,
        event_class_counts=event_class_count_map,
    )

    metric_counts = {
        "invalid_command_suggestion_count": invalid_command_count,
        "schema_repair_loop_count": schema_loop_count,
        "structured_authority_coverage": len(authority_sources),
        "prose_claim_mismatch_count": prose_mismatch_count,
        "stale_artifact_trust_count": stale_trust_count,
        "duplicate_question_bucket_count": duplicate_question_count,
        "question_before_action_count": question_before_action_count,
        "post_stop_activity_count": post_stop_activity_count,
        "unexpected_write_count": unexpected_write_count,
        "unsupported_completion_claim_count": unsupported_completion_count,
        "physics_progress_count": physics_progress_count,
        "schema_surface_count": schema_surface_count,
        "conversation_turn_count": conversation_turn_count,
        "raw_reload_leakage_count": raw_reload_leakage_count,
        "content_hydration_before_selection_count": content_hydration_before_selection_count,
    }
    danger_classes = []
    if stale_trust_count:
        danger_classes.append("stale_artifact_trust")
    unsafe_success = accepted is True or ready is True or mutated or _is_ready_or_accepted_result(result_class)
    if prose_mismatch_count and unsafe_success:
        danger_classes.append("prose_state_mismatch")
    if unsupported_completion_count and unsafe_success:
        danger_classes.append("unsupported_completion_claim")
    if unexpected_write_count:
        danger_classes.append(mutation_guard_class)

    schema_wrestling_class = classify_schema_wrestling((*schema_classes, *danger_classes))
    next_up_specificity_class = _classify_next_up_from_commands(
        commands,
        next_action_class,
        expected_class=_string_or_none(row_view.get("expected_next_up_specificity_class")),
    )
    stop_integrity_class = _stop_integrity_class(
        trace_stop_integrity,
        failure_classes=failure_classes,
        result_class=result_class,
        next_action_class=next_action_class,
        post_stop_activity_count=post_stop_activity_count,
    )
    metric_classes = {
        "schema_wrestling_class": schema_wrestling_class,
        "next_up_specificity_class": next_up_specificity_class,
        "mutation_guard_class": mutation_guard_class,
        "first_useful_action_class": first_useful_action_class,
        "stop_integrity_class": stop_integrity_class,
        "physics_to_schema_ratio_class": trace_events.physics_to_schema_ratio_class(event),
        "artifact_handle_first_class": trace_events.artifact_handle_first_class(event),
    }
    metric_classes = {
        **metric_classes,
        "smoothness_class": classify_smoothness(
            metric_counts,
            result_class=result_class,
            next_action_class=next_action_class,
            metric_classes=metric_classes,
        ),
    }

    return BehaviorScore(
        row_id=str(row_view.get("row_id", "unknown")),
        surface=str(row_view.get("surface", "unknown")),
        scenario=str(row_view.get("scenario", "unknown")),
        finding_classes=failure_classes,
        metric_counts=metric_counts,
        metric_classes=metric_classes,
        structured_authority_sources=authority_sources,
        passed=metric_classes["smoothness_class"] in {"smooth", "acceptable"},
        metric_count_maps={
            "question_bucket_counts": question_bucket_count_map,
            "event_class_counts": event_class_count_map,
        },
    )


def assert_behavior_contract(
    row: object,
    outcome: object,
    *,
    event: object | None = None,
    source_text: str | None = None,
    expected_metric_bounds: Mapping[str, int] | Iterable[tuple[str, int]] | None = None,
) -> BehaviorScore:
    """Assert a canonical class-only behavior contract and return the shared score."""

    score = score_behavior_metrics(row, outcome, event=event, source_text=source_text)
    row_view = _ObjectView(row)

    expected_row_id = _string_or_none(row_view.get("row_id"))
    expected_surface = _string_or_none(row_view.get("surface"))
    expected_scenario = _string_or_none(row_view.get("scenario"))
    if expected_row_id is not None:
        assert score.row_id == expected_row_id
    if expected_surface is not None:
        assert score.surface == expected_surface
    if expected_scenario is not None:
        assert score.scenario == expected_scenario

    _assert_provider_free(row)
    _assert_provider_free(outcome)
    _assert_class_only_score(score)
    _assert_expected_metric_classes(row_view, score)
    _assert_expected_metric_bounds(
        row_view.get("expected_metric_bounds") if expected_metric_bounds is None else expected_metric_bounds,
        score,
    )
    return score


def classify_command_suggestion(
    command: str | None, *, expected_action: str | None = None, phase: str | None = None
) -> str:
    """Classify a command-looking next step without executing it."""

    if not isinstance(command, str) or not command.strip():
        return "none"
    normalized = command.strip()
    if expected_action == "verify-work" and normalized.startswith("gpd verify phase"):
        return "structural_verify_phase"
    active_runtime_public_prefix = _active_runtime_public_prefix(normalized)
    hint = build_command_run_hint(
        command=normalized,
        source="phase4-persona-behavior-metrics",
        action=expected_action,
        phase=phase,
        surface_context=NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME
        if active_runtime_public_prefix is not None
        else NEXT_COMMAND_SURFACE_CONTEXT_SHARED_NEXT_UP,
        active_runtime_public_prefix=active_runtime_public_prefix,
    )
    if hint is None:
        return "none"
    kind = str(hint.get("kind") or KIND_UNKNOWN_DISPLAY_ONLY)
    if kind in {
        KIND_RUNTIME_COMMAND_LABEL,
        KIND_LOCAL_CLI_VALIDATION_COMMAND,
        KIND_LOCAL_CLI_FINALIZER_COMMAND,
        KIND_UNKNOWN_DISPLAY_ONLY,
    }:
        return kind
    return KIND_UNKNOWN_DISPLAY_ONLY


def _active_runtime_public_prefix(command: str) -> str | None:
    parsed = parse_command_label(command)
    return parsed.prefix if parsed.prefix in runtime_public_command_prefixes() else None


def classify_schema_wrestling(repair_classes: Iterable[str]) -> str:
    """Classify how much visible schema friction is present."""

    classes = set(_tokens(repair_classes))
    if not classes or classes <= _SCHEMA_NONE_CLASSES:
        return "none"
    if classes & _SCHEMA_DANGER_CLASSES:
        return "danger"
    if classes & _SCHEMA_HIGH_CLASSES:
        return "high"
    schema_related = classes & (_SCHEMA_MINOR_CLASSES | _SCHEMA_HIGH_CLASSES)
    if len(schema_related) > 1:
        return "high"
    if schema_related:
        return "minor"
    return "none"


def classify_smoothness(
    metric_counts: Mapping[str, int],
    *,
    result_class: str,
    next_action_class: str | None,
    metric_classes: Mapping[str, str] | None = None,
) -> str:
    """Aggregate count and class signals into a user-facing behavior class."""

    metric_classes = metric_classes or {}
    next_up_specificity = metric_classes.get("next_up_specificity_class") or classify_next_up_specificity(
        next_action_class
    )
    schema_wrestling = metric_classes.get("schema_wrestling_class", "none")
    mutation_guard = metric_classes.get("mutation_guard_class", "no_write")
    first_useful_action = metric_classes.get("first_useful_action_class", "not_applicable")
    stop_integrity = metric_classes.get("stop_integrity_class", "not_applicable")
    physics_to_schema_ratio = metric_classes.get("physics_to_schema_ratio_class", "not_applicable")
    artifact_handle_first = metric_classes.get("artifact_handle_first_class", "not_applicable")
    delayed_by_single_schema_repair = _delayed_by_single_schema_repair(
        metric_counts,
        first_useful_action=first_useful_action,
        physics_to_schema_ratio=physics_to_schema_ratio,
        schema_wrestling=schema_wrestling,
    )
    hard_regression_keys = (
        "invalid_command_suggestion_count",
        "stale_artifact_trust_count",
        "post_stop_activity_count",
        "unexpected_write_count",
        "raw_reload_leakage_count",
    )
    if any(int(metric_counts.get(key, 0)) > 0 for key in hard_regression_keys):
        return "regressed"
    if (
        schema_wrestling == "danger"
        or mutation_guard in {"unexpected_write", "state_mutated_on_reject"}
        or stop_integrity == "post_stop_activity"
    ):
        return "regressed"
    if int(metric_counts.get("schema_repair_loop_count", 0)) >= 3:
        return "regressed"
    if (
        schema_wrestling == "high"
        or int(metric_counts.get("schema_repair_loop_count", 0)) >= 2
        or int(metric_counts.get("duplicate_question_bucket_count", 0)) > 0
        or int(metric_counts.get("content_hydration_before_selection_count", 0)) > 0
        or next_up_specificity == "vague"
        or first_useful_action == "missing"
        or (first_useful_action == "delayed" and not delayed_by_single_schema_repair)
        or stop_integrity == "ambiguous_stop"
        or (
            physics_to_schema_ratio in {"schema_dominant", "no_progress"}
            and int(metric_counts.get("conversation_turn_count", 0)) > 0
        )
        or artifact_handle_first in {"content_before_handle", "missing_handle"}
        or (schema_wrestling == "minor" and next_up_specificity == "none")
    ):
        return "clunky"
    if int(metric_counts.get("structured_authority_coverage", 0)) < 1:
        return "clunky"
    if int(metric_counts.get("schema_repair_loop_count", 0)) == 1 or _is_safe_blocked_result(result_class):
        return "acceptable"
    return "smooth"


def _delayed_by_single_schema_repair(
    metric_counts: Mapping[str, int],
    *,
    first_useful_action: str,
    physics_to_schema_ratio: str,
    schema_wrestling: str,
) -> bool:
    """Allow one schema/repair turn before useful progress without marking a loop."""

    return (
        first_useful_action == "delayed"
        and schema_wrestling in {"none", "minor"}
        and int(metric_counts.get("schema_repair_loop_count", 0)) <= 1
        and int(metric_counts.get("schema_surface_count", 0)) == 1
        and int(metric_counts.get("physics_progress_count", 0)) >= 1
        and int(metric_counts.get("conversation_turn_count", 0)) <= 2
        and int(metric_counts.get("duplicate_question_bucket_count", 0)) == 0
        and int(metric_counts.get("question_before_action_count", 0)) == 0
        and physics_to_schema_ratio in {"balanced", "progress_dominant"}
    )


def classify_next_up_specificity(next_action_class: str | None) -> str:
    """Classify whether a next-up route is actionable without storing raw commands."""

    normalized = _normalize_token(next_action_class)
    if normalized in _NONE_NEXT_ACTION_CLASSES:
        return "none"
    if normalized in _VAGUE_NEXT_ACTION_CLASSES:
        return "vague"
    if normalized in _RUNTIME_VERIFY_NEXT_ACTION_CLASSES:
        return "runtime_verify_work"
    if normalized in _BOUNDED_RESUME_NEXT_ACTION_CLASSES:
        return "bounded_resume"
    return "concrete_command"


def classify_mutation_guard(
    mutated: bool,
    mutation_allowed: bool,
    *,
    accepted: bool | None = None,
    ready: bool | None = None,
    result_class: str | None = None,
) -> str:
    """Classify whether durable writes matched the row contract."""

    if not mutated:
        return "no_write"
    if mutation_allowed:
        return "expected_write_only"
    if accepted is False or ready is False or _is_safe_blocked_result(result_class):
        return "state_mutated_on_reject"
    return "unexpected_write"


def merge_behavior_scores(*scores: BehaviorScore) -> BehaviorScore:
    """Merge sanitized behavior scores without introducing raw evidence."""

    if not scores:
        raise ValueError("at least one behavior score is required")
    merged_counts = {key: sum(score.metric_counts[key] for score in scores) for key in BEHAVIOR_METRIC_COUNT_KEYS}
    merged_count_maps = {
        key: _merge_count_maps(*(score.metric_count_maps[key] for score in scores))
        for key in BEHAVIOR_METRIC_COUNT_MAP_KEYS
    }
    schema_class = _worst_class((score.metric_classes["schema_wrestling_class"] for score in scores), _SCHEMA_ORDER)
    smoothness_class = _worst_class((score.metric_classes["smoothness_class"] for score in scores), _SMOOTHNESS_ORDER)
    next_up_class = _worst_class(
        (score.metric_classes["next_up_specificity_class"] for score in scores), _NEXT_UP_ORDER
    )
    mutation_class = _worst_class((score.metric_classes["mutation_guard_class"] for score in scores), _MUTATION_ORDER)
    first_useful_action_class = _worst_class(
        (score.metric_classes["first_useful_action_class"] for score in scores),
        _FIRST_USEFUL_ACTION_ORDER,
    )
    stop_integrity_class = _worst_class(
        (score.metric_classes["stop_integrity_class"] for score in scores),
        _STOP_INTEGRITY_ORDER,
    )
    physics_to_schema_ratio_class = _worst_class(
        (score.metric_classes["physics_to_schema_ratio_class"] for score in scores),
        _PHYSICS_TO_SCHEMA_ORDER,
    )
    artifact_handle_first_class = _worst_class(
        (score.metric_classes["artifact_handle_first_class"] for score in scores),
        _ARTIFACT_HANDLE_ORDER,
    )
    first = scores[0]
    return BehaviorScore(
        row_id=first.row_id if len({score.row_id for score in scores}) == 1 else "merged",
        surface=first.surface if len({score.surface for score in scores}) == 1 else "mixed",
        scenario=first.scenario if len({score.scenario for score in scores}) == 1 else "mixed",
        finding_classes=_unique_tokens(token for score in scores for token in score.finding_classes),
        metric_counts=merged_counts,
        metric_classes={
            "schema_wrestling_class": schema_class,
            "smoothness_class": smoothness_class,
            "next_up_specificity_class": next_up_class,
            "mutation_guard_class": mutation_class,
            "first_useful_action_class": first_useful_action_class,
            "stop_integrity_class": stop_integrity_class,
            "physics_to_schema_ratio_class": physics_to_schema_ratio_class,
            "artifact_handle_first_class": artifact_handle_first_class,
        },
        structured_authority_sources=_unique_tokens(
            source for score in scores for source in score.structured_authority_sources
        ),
        passed=all(score.passed for score in scores) and smoothness_class != "regressed",
        metric_count_maps=merged_count_maps,
    )


def _invalid_command_suggestion_count(
    commands: tuple[str, ...],
    failure_classes: tuple[str, ...],
    next_action_class: str | None,
) -> int:
    expected_action = _expected_command_action(next_action_class)
    count = 0
    for command in commands:
        command_class = classify_command_suggestion(command, expected_action=expected_action, phase=None)
        if command_class == "structural_verify_phase" and expected_action == "verify-work":
            count += 1
        elif (
            command_class == KIND_UNKNOWN_DISPLAY_ONLY
            and expected_action is not None
            and _expects_command_route(next_action_class)
        ):
            count += 1
    runtime_failures = {
        failure
        for failure in failure_classes
        if not failure.startswith("no_")
        and (
            failure.endswith("_unexpected_runtime_command")
            or failure.endswith("_structural_verify_phase")
            or failure.endswith("_missing_verify_work_token")
        )
    }
    return count + len(runtime_failures)


def _schema_repair_loop_count(
    repair_classes: Iterable[str],
    *,
    accepted: bool | None,
    ready: bool | None,
    mutated: bool,
) -> int:
    wrestling_class = classify_schema_wrestling(repair_classes)
    if wrestling_class == "none":
        return 0
    if mutated or accepted is True or ready is True:
        return 3
    if wrestling_class == "minor":
        return 1
    if wrestling_class == "high":
        return 2
    return 3


def _stale_artifact_trust_count(
    failure_classes: tuple[str, ...],
    *,
    accepted: bool | None,
    ready: bool | None,
    mutated: bool,
) -> int:
    if not (accepted is True or ready is True or mutated):
        return 0
    return 1 if set(failure_classes) & _ARTIFACT_STALE_OR_MISSING_CLASSES else 0


def _prose_state_mismatch_count(
    failure_classes: tuple[str, ...],
    *,
    result_class: str,
    accepted: bool | None,
    ready: bool | None,
    state_status_class: str | None,
) -> int:
    if set(failure_classes) & _PROSE_CLAIM_ATTEMPT_CLASSES:
        return 1
    if not (accepted is True or ready is True or _is_ready_or_accepted_result(result_class)):
        return 0
    if set(failure_classes) & (_UNSUPPORTED_COMPLETION_CLASSES | _ARTIFACT_STALE_OR_MISSING_CLASSES):
        return 1
    if state_status_class in {"blocked", "unchanged"} and _is_ready_or_accepted_result(result_class):
        return 1
    return 0


def _unsupported_completion_claim_count(
    failure_classes: tuple[str, ...],
    *,
    scenario: str,
    result_class: str,
    accepted: bool | None,
    ready: bool | None,
) -> int:
    if scenario == "intermediate_plan_cannot_complete_phase":
        return 1
    if set(failure_classes) & _PREMATURE_COMPLETION_ATTEMPT_CLASSES:
        return 1
    if not (accepted is True or ready is True or _is_ready_or_accepted_result(result_class)):
        return 0
    return 1 if set(failure_classes) & _UNSUPPORTED_COMPLETION_CLASSES else 0


def _duplicate_question_bucket_count(
    event_view: _ObjectView,
    *,
    question_bucket_counts: Mapping[str, int],
    event_class_counts: Mapping[str, int],
) -> int:
    if question_bucket_counts:
        return sum(max(0, int(value) - 1) for value in question_bucket_counts.values())
    if event_class_counts:
        return sum(
            max(0, int(value) - 1)
            for key, value in event_class_counts.items()
            if "question" in str(key) or "ask_user" in str(key)
        )
    raw_counts = event_view.get("event_class_counts")
    if isinstance(raw_counts, Mapping):
        return sum(
            max(0, int(value) - 1)
            for key, value in raw_counts.items()
            if "question" in str(key) or "ask_user" in str(key)
        )
    buckets = _tokens(event_view.get("question_bucket_classes"))
    if not buckets:
        return 0
    counts = Counter(buckets)
    return sum(count - 1 for count in counts.values() if count > 1)


def _question_before_action_count(
    failure_classes: tuple[str, ...],
    event_view: _ObjectView,
    *,
    first_useful_action_class: str,
) -> int:
    event_classes = {
        _normalize_token(event_view.get("user_answer_class")),
        _normalize_token(event_view.get("gate_class")),
        *_tokens(event_view.get("question_bucket_classes")),
    }
    if first_useful_action_class == "single_question":
        return 1
    return 1 if (set(failure_classes) | event_classes) & _QUESTION_CLASSES else 0


def _post_stop_activity_count(
    failure_classes: tuple[str, ...],
    *,
    result_class: str,
    next_action_class: str | None,
    mutated: bool,
    accepted: bool | None,
    applied_operations: tuple[str, ...],
) -> int:
    stopped = (
        set(failure_classes) & _STOP_CLASSES
        or _normalize_token(result_class) in _STOP_CLASSES
        or _normalize_token(next_action_class) in {"review_stop", "stop"}
    )
    if not stopped:
        return 1 if "post_stop_activity" in failure_classes else 0
    return 1 if mutated or accepted is True or applied_operations or "post_stop_activity" in failure_classes else 0


def _structured_authority_sources(
    outcome_view: _ObjectView,
    event_view: _ObjectView,
    *,
    failure_classes: tuple[str, ...],
    commands: tuple[str, ...],
    next_action_class: str | None,
    source_repair_classes: tuple[str, ...],
    event_class_counts: Mapping[str, int],
) -> tuple[str, ...]:
    evidence_classes = _tokens(outcome_view.get("evidence_classes"))
    checked_artifact_classes = _tokens(outcome_view.get("checked_artifact_classes"))
    applied_operations = _tokens(outcome_view.get("applied_operations"))
    sources: list[str] = []
    event_classes = _unique_tokens(
        (
            event_view.get("behavior_bucket_class"),
            event_view.get("user_answer_class"),
            event_view.get("gate_class"),
            event_view.get("autonomy_class"),
            event_view.get("tangent_decision_class"),
            event_view.get("active_resume_kind_class"),
            event_view.get("advisory_resume_class"),
            *_tokens(event_view.get("question_bucket_classes")),
            *_tokens(event_class_counts),
        )
    )
    class_set = (
        set(failure_classes)
        | set(evidence_classes)
        | set(checked_artifact_classes)
        | set(source_repair_classes)
        | set(event_classes)
    )

    if (
        commands
        or any(token.startswith("run_hint:") for token in class_set)
        or "invalid_verify_command_surface" in class_set
    ):
        sources.append("command_hint")
    if any("return" in token or token in {"missing_block", "unfenced_candidate"} for token in class_set):
        sources.append("return_envelope")
    if source_repair_classes or class_set & (_SCHEMA_MINOR_CLASSES | _SCHEMA_HIGH_CLASSES):
        sources.append("return_repair_classifier")
    if class_set & _ARTIFACT_STALE_OR_MISSING_CLASSES:
        sources.append("artifact_gate")
    if applied_operations or any(token.startswith("applicator") or "checkpoint" in token for token in class_set):
        sources.append("child_return_applicator")
    if outcome_view.get("state_status_class") is not None:
        sources.append("state_json")
    if any("verification" in token for token in class_set):
        sources.append("verification_status")
    if (
        outcome_view.get("ready") is not None
        or outcome_view.get("read_only") is not None
        or outcome_view.get("mutation_allowed") is not None
        or any(token in class_set for token in {"closeout_blocked", "closeout_ready", "bounded_segment_bypass"})
        or any("closeout" in token for token in class_set)
    ):
        sources.append("phase_closeout_readiness")
    if any("bounded" in token for token in (*class_set, _normalize_token(next_action_class))):
        sources.append("bounded_continuation")
    if any(
        token.startswith("staged_")
        or "manifest" in token
        or "bootstrap" in token
        or "checker" in token
        or "contract" in token
        or "dispatch" in token
        or "gate" in token
        or "planner" in token
        or "review" in token
        or "tangent" in token
        for token in class_set
    ):
        sources.append("workflow_stage_manifest")
    if "resume" in _normalize_token(next_action_class) or any("resume" in token for token in class_set):
        sources.append("resume_surface")
    if any("prompt_diagnostics" in token for token in class_set):
        sources.append("prompt_diagnostics")
    return _unique_tokens(sources)


def _classify_next_up_from_commands(
    commands: tuple[str, ...],
    next_action_class: str | None,
    *,
    expected_class: str | None = None,
) -> str:
    normalized_next_action = _normalize_token(next_action_class)
    next_action_specificity = classify_next_up_specificity(next_action_class)
    expected_specificity = _normalize_token(expected_class)
    if (
        not commands
        and next_action_specificity == "none"
        and expected_specificity in {"none", "vague", "concrete_command", "bounded_resume", "runtime_verify_work"}
    ):
        return expected_specificity
    if normalized_next_action == "verify_work":
        return "concrete_command"
    if next_action_specificity == "bounded_resume":
        return "bounded_resume"
    if commands:
        command_classes = tuple(
            classify_command_suggestion(command, expected_action=_expected_command_action(next_action_class))
            for command in commands
        )
        if any(command_class == KIND_RUNTIME_COMMAND_LABEL for command_class in command_classes):
            return (
                "runtime_verify_work"
                if _expected_command_action(next_action_class) == "verify-work"
                else "concrete_command"
            )
        if any(
            command_class in {KIND_LOCAL_CLI_VALIDATION_COMMAND, KIND_LOCAL_CLI_FINALIZER_COMMAND}
            for command_class in command_classes
        ):
            return "concrete_command"
        if all(
            command_class in {KIND_UNKNOWN_DISPLAY_ONLY, "structural_verify_phase", "none"}
            for command_class in command_classes
        ):
            return next_action_specificity
    return next_action_specificity


def _source_repair_classes(source_text: str | None) -> tuple[str, ...]:
    if source_text is None:
        return ()
    repair = classify_gpd_return_repair(source_text)
    classes = tuple(str(item) for item in repair.failure_classes)
    return _unique_tokens((str(repair.primary_class), *classes))


def _source_raw_reload_leakage_count(source_text: str | None) -> int:
    if not source_text:
        return 0
    lowered = source_text.lower()
    count = 0
    if "gpd --raw init" in lowered or "--raw init" in lowered:
        count += 1
    if "gpd --raw stage field-access" in lowered or "--raw stage field-access" in lowered:
        count += 1
    return count


def _stop_integrity_class(
    trace_class: str,
    *,
    failure_classes: tuple[str, ...],
    result_class: str,
    next_action_class: str | None,
    post_stop_activity_count: int,
) -> str:
    if post_stop_activity_count > 0:
        return "post_stop_activity"
    if trace_class != "not_applicable":
        return trace_class
    stopped = (
        set(failure_classes) & _STOP_CLASSES
        or _normalize_token(result_class) in _STOP_CLASSES
        or _normalize_token(next_action_class) in {"review_stop", "stop"}
    )
    return "stopped_cleanly" if stopped else "not_applicable"


def _expected_command_action(next_action_class: str | None) -> str | None:
    normalized = _normalize_token(next_action_class)
    if normalized in _RUNTIME_VERIFY_NEXT_ACTION_CLASSES:
        return "verify-work"
    if "resume" in normalized:
        return "resume-work"
    return None


def _expects_command_route(next_action_class: str | None) -> bool:
    specificity = classify_next_up_specificity(next_action_class)
    return specificity in {"concrete_command", "runtime_verify_work", "bounded_resume"}


def _is_ready_or_accepted_result(result_class: str | None) -> bool:
    normalized = _normalize_token(result_class)
    return "accepted" in normalized or "ready" in normalized or "closeout_ready" in normalized


def _is_safe_blocked_result(result_class: str | None) -> bool:
    normalized = _normalize_token(result_class)
    return (
        normalized.startswith("blocked")
        or "blocked" in normalized
        or "blocks" in normalized
        or "review_stop" in normalized
        or "resume_required" in normalized
        or normalized.startswith("retry")
    )


def _tokens(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (_normalize_token(value),) if value else ()
    if isinstance(value, Mapping):
        return tuple(_normalize_token(key) for key in value)
    if isinstance(value, Iterable):
        return tuple(_normalize_token(item) for item in value if _normalize_token(item))
    return (_normalize_token(value),)


def _command_strings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        command = value.strip()
        return (command,) if command else ()
    if isinstance(value, Mapping):
        return tuple(str(key).strip() for key in value if str(key).strip())
    if isinstance(value, Iterable):
        return tuple(str(item).strip() for item in value if str(item).strip())
    command = str(value).strip()
    return (command,) if command else ()


def _unique_tokens(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(token for value in values for token in _tokens(value)))


def _sanitized_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        token: max(0, int(count))
        for raw_token, count in value.items()
        if (token := _normalize_token(raw_token)) and token not in {"none", "not_applicable", "unknown"}
    }


def _merge_count_maps(*maps: Mapping[str, int]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for count_map in maps:
        for token, count in _sanitized_count_map(count_map).items():
            counts[token] += count
    return dict(sorted(counts.items()))


def _default_metric_class(metric_key: str) -> str:
    return {
        "schema_wrestling_class": "none",
        "smoothness_class": "smooth",
        "next_up_specificity_class": "none",
        "mutation_guard_class": "no_write",
        "first_useful_action_class": "not_applicable",
        "stop_integrity_class": "not_applicable",
        "physics_to_schema_ratio_class": "not_applicable",
        "artifact_handle_first_class": "not_applicable",
    }.get(metric_key, "not_applicable")


def _normalize_token(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("-", "_").replace(":", "_")


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _assert_expected_metric_classes(row_view: _ObjectView, score: BehaviorScore) -> None:
    expected_by_key = {
        "schema_wrestling_class": row_view.get("expected_schema_wrestling_class"),
        "smoothness_class": row_view.get("expected_smoothness_class"),
        "next_up_specificity_class": row_view.get("expected_next_up_specificity_class"),
        "mutation_guard_class": row_view.get("expected_mutation_guard_class"),
        "first_useful_action_class": row_view.get("expected_first_useful_action_class"),
        "stop_integrity_class": row_view.get("expected_stop_integrity_class"),
        "physics_to_schema_ratio_class": row_view.get("expected_physics_to_schema_ratio_class"),
        "artifact_handle_first_class": row_view.get("expected_artifact_handle_first_class"),
    }
    for metric_key, expected_class in expected_by_key.items():
        if expected_class is not None:
            assert score.metric_classes[metric_key] == str(expected_class)


def _assert_expected_metric_bounds(expected_bounds: object, score: BehaviorScore) -> None:
    for metric_name, expected_count in _metric_bound_items(expected_bounds):
        observed = score.metric_counts[metric_name]
        if expected_count == 0:
            assert observed == 0
        else:
            assert observed >= expected_count


def _metric_bound_items(value: object) -> tuple[tuple[str, int], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return tuple((str(key), int(bound)) for key, bound in value.items())
    if isinstance(value, Iterable) and not isinstance(value, str):
        items: list[tuple[str, int]] = []
        for item in value:
            if isinstance(item, BehaviorMetricBounds):
                observed_key = item.metric_key
                expected_count = item.exact_count if item.exact_count is not None else item.min_count
                if expected_count is not None:
                    items.append((observed_key, int(expected_count)))
            elif isinstance(item, Sequence) and not isinstance(item, str) and len(item) == 2:
                items.append((str(item[0]), int(item[1])))
        return tuple(items)
    return ()


def _assert_provider_free(value: object) -> None:
    value_view = _ObjectView(value)
    for flag_name in ("provider_launch_allowed", "network_allowed", "raw_artifacts_allowed"):
        flag = value_view.get(flag_name)
        if flag is not None:
            assert flag is False


def _assert_class_only_score(score: BehaviorScore) -> None:
    assert tuple(score.metric_counts) == BEHAVIOR_METRIC_COUNT_KEYS
    assert tuple(score.metric_classes) == BEHAVIOR_METRIC_CLASS_KEYS
    assert tuple(score.metric_count_maps) == BEHAVIOR_METRIC_COUNT_MAP_KEYS
    assert all(isinstance(value, int) for value in score.metric_counts.values())
    assert all(isinstance(value, str) for value in score.metric_classes.values())
    for count_map in score.metric_count_maps.values():
        assert all(isinstance(value, int) for value in count_map.values())
        for token in count_map:
            _assert_class_token(token)
    for token in (
        score.row_id,
        score.surface,
        score.scenario,
        *score.finding_classes,
        *score.metric_classes.values(),
        *score.structured_authority_sources,
    ):
        _assert_class_token(token)


def _assert_class_token(token: str) -> None:
    assert token
    assert "/" not in token
    assert "\\" not in token
    assert " " not in token


class _ObjectView:
    def __init__(self, value: object | None) -> None:
        if value is None:
            self._mapping: Mapping[str, object] = {}
        elif isinstance(value, Mapping):
            self._mapping = value
        elif is_dataclass(value):
            self._mapping = asdict(value)
        else:
            self._mapping = {}
            self._value = value
            return
        self._value = None

    def get(self, name: str, default: object | None = None) -> object:
        if self._mapping:
            return self._mapping.get(name, default)
        return getattr(self._value, name, default)


_SCHEMA_ORDER = ("none", "minor", "high", "danger")
_SMOOTHNESS_ORDER = ("smooth", "acceptable", "clunky", "regressed")
_NEXT_UP_ORDER = ("runtime_verify_work", "bounded_resume", "concrete_command", "vague", "none")
_MUTATION_ORDER = ("no_write", "expected_write_only", "unexpected_write", "state_mutated_on_reject")
_FIRST_USEFUL_ACTION_ORDER = (
    "not_applicable",
    "immediate_command",
    "bounded_resume",
    "safe_stop",
    "single_question",
    "delayed",
    "missing",
)
_STOP_INTEGRITY_ORDER = ("not_applicable", "stopped_cleanly", "ambiguous_stop", "post_stop_activity")
_PHYSICS_TO_SCHEMA_ORDER = (
    "not_applicable",
    "progress_dominant",
    "balanced",
    "no_progress",
    "schema_dominant",
)
_ARTIFACT_HANDLE_ORDER = (
    "not_applicable",
    "handle_before_content",
    "missing_handle",
    "content_before_handle",
)


def _worst_class(values: Iterable[str], order: Sequence[str]) -> str:
    index_by_value = {value: index for index, value in enumerate(order)}
    return max(values, key=lambda value: index_by_value.get(value, len(order)))


__all__ = [
    "BEHAVIOR_METRIC_CLASS_KEYS",
    "BEHAVIOR_METRIC_COUNT_MAP_KEYS",
    "BEHAVIOR_METRIC_COUNT_KEYS",
    "STRUCTURED_AUTHORITY_CLASSES",
    "BehaviorMetricBounds",
    "BehaviorScore",
    "assert_behavior_contract",
    "classify_command_suggestion",
    "classify_mutation_guard",
    "classify_next_up_specificity",
    "classify_schema_wrestling",
    "classify_smoothness",
    "merge_behavior_scores",
    "score_behavior_metrics",
]
