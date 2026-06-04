"""Provider-free replay tests for Phase 4 user-steering behavior."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from tests.helpers.phase4_persona.behavior_metrics import assert_behavior_contract
from tests.helpers.phase4_persona.matrix import load_phase4_rows
from tests.helpers.phase4_persona.user_steering import (
    REPO_ROOT,
    UserSteeringOutcome,
    UserSteeringRow,
    replay_event_for_row,
    score_user_steering_row,
    user_steering_rows,
)

CLASS_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")

EXPECTED_BEHAVIOR_BUCKETS = {
    "P4-USER-01": "ask_user_required",
    "P4-USER-02": "abort_blocks_dispatch",
    "P4-USER-03": "tangent_review_stop",
    "P4-USER-04": "bounded_resume_primary",
    "P4-USER-05": "supervised_closeout_concrete_next_up",
    "P4-USER-06": "canonical_bounded_segment_preference",
}

EXPECTED_NEXT_ACTION_ANCHORS = {
    "P4-USER-01": "gpd:execute-phase",
    "P4-USER-02": "gpd:execute-phase",
    "P4-USER-03": "review_stop",
    "P4-USER-04": "gpd:resume-work",
    "P4-USER-05": "concrete_next_command",
    "P4-USER-06": "bounded_segment_resume",
}

EXPECTED_FIRST_USEFUL_ACTIONS = {
    "P4-USER-01": "immediate_command",
    "P4-USER-02": "safe_stop",
    "P4-USER-03": "safe_stop",
    "P4-USER-04": "bounded_resume",
    "P4-USER-05": "immediate_command",
    "P4-USER-06": "bounded_resume",
}

EXPECTED_STOP_INTEGRITY = {
    "P4-USER-01": "not_applicable",
    "P4-USER-02": "stopped_cleanly",
    "P4-USER-03": "stopped_cleanly",
    "P4-USER-04": "not_applicable",
    "P4-USER-05": "not_applicable",
    "P4-USER-06": "not_applicable",
}

USER_STEERING_CONTRACT_ROWS = {(row.row_id, row.scenario): row for row in load_phase4_rows("user_steering")}


def _assert_class_only(value: object) -> None:
    if value is None:
        return
    if isinstance(value, str):
        assert CLASS_TOKEN_RE.fullmatch(value), value
        assert "/" not in value
        assert "\\" not in value
        assert " " not in value
    elif isinstance(value, bool):
        return
    elif isinstance(value, int):
        assert value >= 0
    elif is_dataclass(value):
        for field in fields(value):
            _assert_class_only(getattr(value, field.name))
    elif isinstance(value, tuple):
        for item in value:
            _assert_class_only(item)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _assert_class_only(key)
            _assert_class_only(item)
    else:
        raise AssertionError(f"unexpected non-class value type: {type(value).__name__}")


def _assert_outcome_class_only(outcome: UserSteeringOutcome) -> None:
    for field in fields(outcome):
        _assert_class_only(getattr(outcome, field.name))


def _assert_event_matches_expected_score_keys(event: object, score: object) -> None:
    if "physics_progress_count" in score.metric_counts:
        assert score.metric_counts["physics_progress_count"] == event.physics_progress_count
    if "schema_surface_count" in score.metric_counts:
        assert score.metric_counts["schema_surface_count"] == event.schema_surface_count
    if "first_useful_action_class" in score.metric_classes:
        assert score.metric_classes["first_useful_action_class"] == event.first_useful_action_class
    if "stop_integrity_class" in score.metric_classes:
        assert score.metric_classes["stop_integrity_class"] == event.stop_integrity_class
    if "physics_to_schema_ratio_class" in score.metric_classes:
        assert score.metric_classes["physics_to_schema_ratio_class"] == event.physics_to_schema_ratio_class


def test_phase4_user_steering_rows_are_provider_free_and_owned() -> None:
    rows = user_steering_rows()
    expected_row_ids = {
        "P4-USER-01",
        "P4-USER-02",
        "P4-USER-03",
        "P4-USER-04",
        "P4-USER-05",
        "P4-USER-06",
    }

    assert {row.row_id for row in rows} == expected_row_ids
    assert len(rows) == len(expected_row_ids)
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert all(row.mutation_allowed is False for row in rows)
    assert {row.row_id: row.expected_behavior_bucket_class for row in rows} == EXPECTED_BEHAVIOR_BUCKETS
    assert {row.row_id: row.expected_next_action_class for row in rows} == EXPECTED_NEXT_ACTION_ANCHORS

    source_files = {source_file for row in rows for source_file in row.source_files}
    assert source_files == {
        Path("src/gpd/specs/workflows/execute-phase/wave-planning.md"),
        Path("src/gpd/specs/workflows/execute-phase/wave-dispatch.md"),
        Path("src/gpd/specs/workflows/resume-work/resume-bootstrap.md"),
        Path("src/gpd/specs/workflows/resume-work/resume-routing.md"),
        Path("src/gpd/specs/workflows/execute-phase/closeout.md"),
    }
    assert all((REPO_ROOT / source_file).is_file() for source_file in source_files)


@pytest.mark.parametrize("row", user_steering_rows(), ids=lambda row: f"{row.row_id}-{row.scenario}")
def test_phase4_user_steering_replay_scores_expected_class(row: UserSteeringRow) -> None:
    event = replay_event_for_row(row)

    outcome = score_user_steering_row(row, event)
    contract_row = USER_STEERING_CONTRACT_ROWS[(row.row_id, row.scenario)]
    score = assert_behavior_contract(contract_row, outcome, event=event)

    assert event.behavior_bucket_class == row.expected_behavior_bucket_class
    assert outcome.mutated is False
    assert outcome.finding_id == row.expected_finding
    assert outcome.behavior_bucket_class == row.expected_behavior_bucket_class
    assert outcome.result_class == row.expected_result_class
    assert outcome.next_action_class == row.expected_next_action_class
    assert outcome.dispatch_class == row.expected_dispatch_class
    assert outcome.resume_target_class == row.expected_resume_target_class
    assert score.metric_classes["next_up_specificity_class"] == contract_row.expected_next_up_specificity_class
    assert score.metric_counts["duplicate_question_bucket_count"] == 0
    assert score.metric_counts["post_stop_activity_count"] == 0
    assert event.event_class_counts
    assert event.event_class_counts["conversation_turn"] == len(event.turns)
    assert event.physics_progress_count >= 1
    assert event.schema_surface_count <= event.physics_progress_count + 1
    assert event.first_useful_action_class == EXPECTED_FIRST_USEFUL_ACTIONS[row.row_id]
    assert event.stop_integrity_class == EXPECTED_STOP_INTEGRITY[row.row_id]
    assert event.physics_to_schema_ratio_class == "progress_dominant"
    assert event.raw_reload_leakage_count == 0
    assert event.content_hydration_before_selection_count == 0
    if row.row_id == "P4-USER-01":
        assert score.metric_counts["question_before_action_count"] == 1
    if row.row_id in {"P4-USER-04", "P4-USER-06"}:
        assert score.metric_classes["next_up_specificity_class"] == "bounded_resume"
    if row.row_id == "P4-USER-05":
        assert score.metric_classes["next_up_specificity_class"] == "concrete_command"
    _assert_event_matches_expected_score_keys(event, score)
    assert row.expected_finding in outcome.failure_classes
    _assert_outcome_class_only(outcome)


def test_phase4_user_steering_replay_events_are_class_only() -> None:
    for row in user_steering_rows():
        event = replay_event_for_row(row)
        for field in fields(event):
            _assert_class_only(getattr(event, field.name))
