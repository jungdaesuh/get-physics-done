"""Provider-free Phase 4 user-steering replay helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from tests.helpers.phase4_persona.interaction_events import FakePersonaTurn

REPO_ROOT = Path(__file__).resolve().parents[3]

WAVE_PLANNING = Path("src/gpd/specs/workflows/execute-phase/wave-planning.md")
WAVE_DISPATCH = Path("src/gpd/specs/workflows/execute-phase/wave-dispatch.md")
RESUME_BOOTSTRAP = Path("src/gpd/specs/workflows/resume-work/resume-bootstrap.md")
RESUME_ROUTING = Path("src/gpd/specs/workflows/resume-work/resume-routing.md")
CLOSEOUT = Path("src/gpd/specs/workflows/execute-phase/closeout.md")


@dataclass(frozen=True)
class UserSteeringRow:
    row_id: str
    scenario: str
    source_files: tuple[Path, ...]
    expected_finding: str
    expected_behavior_bucket_class: str
    expected_result_class: str
    expected_next_action_class: str
    expected_dispatch_class: str = "not_applicable"
    expected_resume_target_class: str = "not_applicable"
    expected_next_up_specificity_class: str = "not_applicable"
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    mutation_allowed: bool = False


UserSteeringReplayTurn = FakePersonaTurn


@dataclass(frozen=True)
class UserSteeringReplayEvent:
    scenario: str
    behavior_bucket_class: str
    user_answer_class: str = "not_applicable"
    gate_class: str = "not_applicable"
    autonomy_class: str = "not_applicable"
    tangent_decision_class: str = "not_applicable"
    active_resume_kind_class: str = "not_applicable"
    advisory_resume_class: str = "not_applicable"
    turns: tuple[UserSteeringReplayTurn, ...] = ()
    event_class_counts: dict[str, int] | None = None
    question_bucket_classes: tuple[str, ...] = ()
    physics_progress_count: int = 0
    schema_surface_count: int = 0
    first_useful_action_class: str = "missing"
    stop_integrity_class: str = "not_applicable"
    physics_to_schema_ratio_class: str = "no_progress"
    artifact_handle_first_class: str = "not_applicable"
    raw_reload_leakage_count: int = 0
    content_hydration_before_selection_count: int = 0


@dataclass(frozen=True)
class UserSteeringOutcome:
    finding_id: str
    behavior_bucket_class: str
    result_class: str
    next_action_class: str
    dispatch_class: str
    resume_target_class: str
    next_up_specificity_class: str
    failure_classes: tuple[str, ...]
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    mutated: bool = False


USER_STEERING_ROWS: tuple[UserSteeringRow, ...] = (
    UserSteeringRow(
        row_id="P4-USER-01",
        scenario="alignment_requires_explicit_ask_user_answer",
        source_files=(WAVE_PLANNING,),
        expected_finding="alignment_answer_required",
        expected_behavior_bucket_class="ask_user_required",
        expected_result_class="blocked_before_execution",
        expected_next_action_class="gpd:execute-phase",
        expected_dispatch_class="blocked_missing_user_answer",
    ),
    UserSteeringRow(
        row_id="P4-USER-02",
        scenario="user_abort_stops_before_dispatch",
        source_files=(WAVE_PLANNING,),
        expected_finding="user_abort_stops_dispatch",
        expected_behavior_bucket_class="abort_blocks_dispatch",
        expected_result_class="stopped_before_dispatch",
        expected_next_action_class="gpd:execute-phase",
        expected_dispatch_class="blocked_user_abort",
    ),
    UserSteeringRow(
        row_id="P4-USER-03",
        scenario="tangent_proposal_uses_existing_review_stop",
        source_files=(WAVE_PLANNING, WAVE_DISPATCH),
        expected_finding="tangent_proposal_not_silent_work",
        expected_behavior_bucket_class="tangent_review_stop",
        expected_result_class="classified_at_existing_review_stop",
        expected_next_action_class="review_stop",
        expected_dispatch_class="blocked_executor_initiative",
    ),
    UserSteeringRow(
        row_id="P4-USER-04",
        scenario="first_result_or_pre_fanout_routes_bounded_resume",
        source_files=(WAVE_PLANNING, WAVE_DISPATCH, RESUME_BOOTSTRAP, RESUME_ROUTING),
        expected_finding="pre_fanout_lock_routes_resume",
        expected_behavior_bucket_class="bounded_resume_primary",
        expected_result_class="bounded_segment_resume_required",
        expected_next_action_class="gpd:resume-work",
        expected_resume_target_class="primary_bounded_segment",
    ),
    UserSteeringRow(
        row_id="P4-USER-05",
        scenario="supervised_closeout_requires_concrete_next_up",
        source_files=(CLOSEOUT,),
        expected_finding="supervised_closeout_requires_next_up",
        expected_behavior_bucket_class="supervised_closeout_concrete_next_up",
        expected_result_class="paused_with_concrete_next_up",
        expected_next_action_class="concrete_next_command",
        expected_next_up_specificity_class="concrete_command",
    ),
    UserSteeringRow(
        row_id="P4-USER-06",
        scenario="resume_prefers_canonical_bounded_segment",
        source_files=(RESUME_BOOTSTRAP, RESUME_ROUTING),
        expected_finding="canonical_bounded_segment_wins",
        expected_behavior_bucket_class="canonical_bounded_segment_preference",
        expected_result_class="canonical_bounded_segment_preferred",
        expected_next_action_class="bounded_segment_resume",
        expected_resume_target_class="canonical_bounded_segment",
    ),
)


def user_steering_rows() -> tuple[UserSteeringRow, ...]:
    return USER_STEERING_ROWS


def replay_event_for_row(row: UserSteeringRow) -> UserSteeringReplayEvent:
    match row.scenario:
        case "alignment_requires_explicit_ask_user_answer":
            return _replay_event(
                row,
                behavior_bucket_class="ask_user_required",
                user_answer_class="missing",
                gate_class="claim_deliverable_alignment",
                autonomy_class="supervised",
                first_useful_action_class="immediate_command",
                physics_to_schema_ratio_class="progress_dominant",
                turns=(
                    UserSteeringReplayTurn(
                        1,
                        "assistant",
                        "alignment_gate",
                        "ask_user_before_dispatch",
                        question_bucket_class="ask_user_alignment",
                        physics_progress_class="scope_preserved",
                    ),
                ),
            )
        case "user_abort_stops_before_dispatch":
            return _replay_event(
                row,
                behavior_bucket_class="abort_blocks_dispatch",
                user_answer_class="abort",
                gate_class="claim_deliverable_alignment",
                autonomy_class="supervised",
                first_useful_action_class="safe_stop",
                stop_integrity_class="stopped_cleanly",
                physics_to_schema_ratio_class="progress_dominant",
                turns=(
                    UserSteeringReplayTurn(
                        1,
                        "user",
                        "abort_request",
                        "stop_requested",
                        physics_progress_class="scope_preserved",
                        stop_class="abort",
                    ),
                ),
            )
        case "tangent_proposal_uses_existing_review_stop":
            return _replay_event(
                row,
                behavior_bucket_class="tangent_review_stop",
                gate_class="pre_fanout_review",
                tangent_decision_class="branch_later",
                autonomy_class="balanced",
                first_useful_action_class="safe_stop",
                stop_integrity_class="stopped_cleanly",
                physics_to_schema_ratio_class="progress_dominant",
                turns=(
                    UserSteeringReplayTurn(
                        1,
                        "assistant",
                        "executor_tangent_detected",
                        "route_existing_review_stop",
                        physics_progress_class="scope_preserved",
                        stop_class="review_stop",
                    ),
                ),
            )
        case "first_result_or_pre_fanout_routes_bounded_resume":
            return _replay_event(
                row,
                behavior_bucket_class="bounded_resume_primary",
                gate_class="pre_fanout_review_pending",
                active_resume_kind_class="bounded_segment",
                first_useful_action_class="bounded_resume",
                physics_to_schema_ratio_class="progress_dominant",
                turns=(
                    UserSteeringReplayTurn(
                        1,
                        "assistant",
                        "pre_fanout_lock_detected",
                        "route_bounded_resume",
                        physics_progress_class="continuation_preserved",
                    ),
                ),
            )
        case "supervised_closeout_requires_concrete_next_up":
            return _replay_event(
                row,
                behavior_bucket_class="supervised_closeout_concrete_next_up",
                autonomy_class="supervised",
                gate_class="closeout_offer_next",
                first_useful_action_class="immediate_command",
                physics_to_schema_ratio_class="progress_dominant",
                turns=(
                    UserSteeringReplayTurn(
                        1,
                        "assistant",
                        "supervised_closeout_pause",
                        "surface_concrete_next_up",
                        physics_progress_class="closeout_gap_identified",
                    ),
                ),
            )
        case "resume_prefers_canonical_bounded_segment":
            return _replay_event(
                row,
                behavior_bucket_class="canonical_bounded_segment_preference",
                active_resume_kind_class="bounded_segment",
                advisory_resume_class="live_snapshot_and_recorded_handoff",
                first_useful_action_class="bounded_resume",
                physics_to_schema_ratio_class="progress_dominant",
                turns=(
                    UserSteeringReplayTurn(
                        1,
                        "assistant",
                        "resume_surface_selection",
                        "choose_canonical_bounded_segment",
                        physics_progress_class="continuation_preserved",
                    ),
                ),
            )
    raise AssertionError(f"unhandled user-steering scenario: {row.scenario}")


def _replay_event(
    row: UserSteeringRow,
    *,
    behavior_bucket_class: str,
    turns: tuple[UserSteeringReplayTurn, ...],
    user_answer_class: str = "not_applicable",
    gate_class: str = "not_applicable",
    autonomy_class: str = "not_applicable",
    tangent_decision_class: str = "not_applicable",
    active_resume_kind_class: str = "not_applicable",
    advisory_resume_class: str = "not_applicable",
    first_useful_action_class: str,
    stop_integrity_class: str = "not_applicable",
    physics_to_schema_ratio_class: str,
    artifact_handle_first_class: str = "not_applicable",
) -> UserSteeringReplayEvent:
    counts = _event_counts(turns)
    question_buckets = tuple(
        turn.question_bucket_class for turn in turns if turn.question_bucket_class not in {"", "none"}
    )
    physics_progress_count = sum(
        1 for turn in turns if turn.physics_progress_class not in {"", "none", "not_applicable"}
    )
    schema_surface_count = sum(1 for turn in turns if turn.schema_surface_class not in {"", "none"})
    return UserSteeringReplayEvent(
        scenario=row.scenario,
        behavior_bucket_class=behavior_bucket_class,
        user_answer_class=user_answer_class,
        gate_class=gate_class,
        autonomy_class=autonomy_class,
        tangent_decision_class=tangent_decision_class,
        active_resume_kind_class=active_resume_kind_class,
        advisory_resume_class=advisory_resume_class,
        turns=turns,
        event_class_counts=dict(sorted(counts.items())),
        question_bucket_classes=question_buckets,
        physics_progress_count=physics_progress_count,
        schema_surface_count=schema_surface_count,
        first_useful_action_class=first_useful_action_class,
        stop_integrity_class=stop_integrity_class,
        physics_to_schema_ratio_class=physics_to_schema_ratio_class,
        artifact_handle_first_class=artifact_handle_first_class,
    )


def _event_counts(turns: tuple[UserSteeringReplayTurn, ...]) -> Counter[str]:
    counts: Counter[str] = Counter({"conversation_turn": len(turns)})
    for turn in turns:
        counts[f"speaker:{turn.speaker_class}"] += 1
        counts[f"intent:{turn.intent_class}"] += 1
        counts[f"action:{turn.action_class}"] += 1
        if turn.question_bucket_class not in {"", "none"}:
            counts[f"question_bucket:{turn.question_bucket_class}"] += 1
        if turn.schema_surface_class not in {"", "none"}:
            counts[f"schema_surface:{turn.schema_surface_class}"] += 1
        if turn.physics_progress_class not in {"", "none", "not_applicable"}:
            counts[f"physics_progress:{turn.physics_progress_class}"] += 1
        if turn.stop_class not in {"", "not_applicable"}:
            counts[f"stop:{turn.stop_class}"] += 1
        if turn.reload_surface_class not in {"", "none"}:
            counts[f"reload_surface:{turn.reload_surface_class}"] += 1
        if turn.artifact_handle_class not in {"", "none", "not_applicable"}:
            counts[f"artifact_handle:{turn.artifact_handle_class}"] += 1
    return counts


def _assert_behavior_bucket(row: UserSteeringRow, event: UserSteeringReplayEvent) -> None:
    assert event.behavior_bucket_class == row.expected_behavior_bucket_class


def _outcome(
    row: UserSteeringRow,
    *,
    failure_classes: tuple[str, ...],
) -> UserSteeringOutcome:
    return UserSteeringOutcome(
        finding_id=row.expected_finding,
        behavior_bucket_class=row.expected_behavior_bucket_class,
        result_class=row.expected_result_class,
        next_action_class=row.expected_next_action_class,
        dispatch_class=row.expected_dispatch_class,
        resume_target_class=row.expected_resume_target_class,
        next_up_specificity_class=row.expected_next_up_specificity_class,
        failure_classes=failure_classes,
    )


def _score_alignment_requires_answer(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    _assert_behavior_bucket(row, event)
    assert event.user_answer_class == "missing"
    assert event.gate_class == "claim_deliverable_alignment"
    return _outcome(
        row,
        failure_classes=("alignment_answer_required", "ask_user_answer_missing", "dispatch_not_authorized"),
    )


def _score_user_abort(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    _assert_behavior_bucket(row, event)
    assert event.user_answer_class == "abort"
    assert event.gate_class == "claim_deliverable_alignment"
    return _outcome(
        row,
        failure_classes=("user_abort_stops_dispatch", "executor_dispatch_blocked"),
    )


def _score_tangent_proposal(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    _assert_behavior_bucket(row, event)
    assert event.gate_class == "pre_fanout_review"
    assert event.tangent_decision_class == "branch_later"
    return _outcome(
        row,
        failure_classes=("tangent_proposal_not_silent_work", "review_stop_required"),
    )


def _score_bounded_resume(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    _assert_behavior_bucket(row, event)
    assert event.gate_class == "pre_fanout_review_pending"
    assert event.active_resume_kind_class == "bounded_segment"
    return _outcome(
        row,
        failure_classes=("pre_fanout_lock_routes_resume", "bounded_segment_required"),
    )


def _score_supervised_closeout(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    _assert_behavior_bucket(row, event)
    assert event.autonomy_class == "supervised"
    assert event.gate_class == "closeout_offer_next"
    return _outcome(
        row,
        failure_classes=("supervised_closeout_requires_next_up", "next_up_required"),
    )


def _score_canonical_resume(row: UserSteeringRow, event: UserSteeringReplayEvent) -> UserSteeringOutcome:
    _assert_behavior_bucket(row, event)
    assert event.active_resume_kind_class == "bounded_segment"
    assert event.advisory_resume_class == "live_snapshot_and_recorded_handoff"
    return _outcome(
        row,
        failure_classes=("canonical_bounded_segment_wins", "advisory_resume_not_primary"),
    )


def score_user_steering_row(row: UserSteeringRow, event: UserSteeringReplayEvent | None = None) -> UserSteeringOutcome:
    event = event or replay_event_for_row(row)
    match row.scenario:
        case "alignment_requires_explicit_ask_user_answer":
            return _score_alignment_requires_answer(row, event)
        case "user_abort_stops_before_dispatch":
            return _score_user_abort(row, event)
        case "tangent_proposal_uses_existing_review_stop":
            return _score_tangent_proposal(row, event)
        case "first_result_or_pre_fanout_routes_bounded_resume":
            return _score_bounded_resume(row, event)
        case "supervised_closeout_requires_concrete_next_up":
            return _score_supervised_closeout(row, event)
        case "resume_prefers_canonical_bounded_segment":
            return _score_canonical_resume(row, event)
    raise AssertionError(f"unhandled user-steering scenario: {row.scenario}")
