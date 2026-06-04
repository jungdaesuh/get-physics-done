"""Aggregate provider-free persona canary acceptance."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.persona_summary import (
    assert_persona_summary_valid,
    make_phase7_live_canary_summary,
    phase7_live_canary_policy,
)
from tests.helpers.phase4_persona.behavior_metrics import BehaviorScore, assert_behavior_contract
from tests.helpers.phase4_persona.completion import completion_replay_rows, score_completion_replay_row
from tests.helpers.phase4_persona.execution import execution_replay_rows, score_execution_replay_row
from tests.helpers.phase4_persona.matrix import load_phase4_rows
from tests.helpers.phase4_persona.planning import load_planning_replay_rows, score_planning_replay_row
from tests.helpers.phase4_persona.user_steering import (
    replay_event_for_row,
    score_user_steering_row,
    user_steering_rows,
)
from tests.helpers.phase7_live_like import (
    REQUIRED_JIT_ROW_IDS,
    assert_phase7_live_like_scores_contract,
    load_phase7_live_like_rows,
    score_phase7_live_like_rows,
)

STOP_BEHAVIOR_ROW_IDS = frozenset({"P4-USER-02", "P4-USER-03"})
EXPECTED_UNSUPPORTED_COMPLETION_DETECTION_ROW_IDS = frozenset({"P4-EXEC-13", "P4-EXEC-14"})

HARD_ZERO_METRIC_KEYS = (
    "invalid_command_suggestion_count",
    "post_stop_activity_count",
    "unexpected_write_count",
    "unsupported_completion_claim_count",
)


def test_provider_free_persona_canary_scores_obey_hard_budgets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase4_scores = _phase4_behavior_scores(tmp_path, monkeypatch)
    phase7_scores = score_phase7_live_like_rows(load_phase7_live_like_rows())

    assert phase4_scores

    for score in phase4_scores:
        _assert_score_hard_budgets(score)

    assert_phase7_live_like_scores_contract(phase7_scores)


def test_phase7_public_persona_oracle_projects_scored_jit_rows() -> None:
    phase7_scores = score_phase7_live_like_rows(load_phase7_live_like_rows())
    summary = make_phase7_live_canary_summary()
    summary_rows = summary["rows"]
    assert isinstance(summary_rows, list)
    summary_rows_by_id = {row["row_id"]: row for row in summary_rows if isinstance(row, dict)}
    scored_ids = {score.row.row_id for score in phase7_scores}

    assert_persona_summary_valid(summary, phase7_live_canary_policy())
    assert summary["jit_canary_row_count"] == len(scored_ids)
    assert scored_ids <= set(summary_rows_by_id)
    assert REQUIRED_JIT_ROW_IDS <= set(summary_rows_by_id)
    hard_zero_metric_counts = summary["hard_zero_metric_counts"]
    assert isinstance(hard_zero_metric_counts, dict)
    assert {
        "content_hydration_before_selection_count",
        "missing_runtime_command_label_count",
        "malformed_child_return_trust_count",
    } <= set(hard_zero_metric_counts)
    assert all(count == 0 for count in hard_zero_metric_counts.values())

    for score in phase7_scores:
        row = summary_rows_by_id[score.row.row_id]
        assert row["oracle_result_class"] == "pass"
        assert row["hard_budget_failure_classes"] == []
        assert row["hard_zero_failure_count"] == 0
        assert row["smoothness_class"] == score.behavior_score.metric_classes["smoothness_class"]
        assert row["ergonomic_score_class"] == score.phase7_metric_classes["ergonomic_score_class"]
        for metric_key in (*HARD_ZERO_METRIC_KEYS, "raw_reload_leakage_count"):
            assert row[metric_key] == 0


def _phase4_behavior_scores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[BehaviorScore, ...]:
    monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / ".gpd-data"))

    scores: list[BehaviorScore] = []

    for row in load_planning_replay_rows():
        outcome = score_planning_replay_row(row, tmp_path / row.row_id)
        scores.append(assert_behavior_contract(row, outcome))

    for row in execution_replay_rows():
        outcome = score_execution_replay_row(row, tmp_path / row.row_id)
        scores.append(assert_behavior_contract(row, outcome))

    for row in completion_replay_rows():
        outcome = score_completion_replay_row(row, tmp_path / row.row_id, monkeypatch)
        scores.append(assert_behavior_contract(row, outcome))

    user_steering_contract_rows = {(row.row_id, row.scenario): row for row in load_phase4_rows("user_steering")}
    for row in user_steering_rows():
        event = replay_event_for_row(row)
        outcome = score_user_steering_row(row, event)
        contract_row = user_steering_contract_rows[(row.row_id, row.scenario)]
        scores.append(assert_behavior_contract(contract_row, outcome, event=event))

    return tuple(scores)


def _assert_score_hard_budgets(score: BehaviorScore) -> None:
    for metric_key in HARD_ZERO_METRIC_KEYS:
        if metric_key == "unsupported_completion_claim_count" and _is_expected_unsupported_completion_detection(score):
            assert score.metric_counts[metric_key] == 1
            continue
        assert score.metric_counts[metric_key] == 0

    assert score.metric_classes["schema_wrestling_class"] != "danger"
    assert score.metric_classes["smoothness_class"] != "regressed"

    if _is_stale_artifact_score(score):
        assert score.metric_counts["stale_artifact_trust_count"] == 0

    if score.row_id in STOP_BEHAVIOR_ROW_IDS:
        assert score.metric_counts["post_stop_activity_count"] == 0
        assert score.metric_classes["stop_integrity_class"] == "stopped_cleanly"

    if score.row_id == "P4-COMP-08":
        assert score.metric_counts["invalid_command_suggestion_count"] == 0
        assert score.metric_classes["next_up_specificity_class"] == "runtime_verify_work"

    assert score.metric_counts["schema_surface_count"] <= score.metric_counts["physics_progress_count"] + 1


def _score_search_text(score: BehaviorScore) -> str:
    return " ".join((score.row_id, score.surface, score.scenario, *score.finding_classes)).lower()


def _is_stale_artifact_score(score: BehaviorScore) -> bool:
    text = _score_search_text(score)
    return "stale" in text or "wrong_sibling" in text


def _is_expected_unsupported_completion_detection(score: BehaviorScore) -> bool:
    return score.row_id in EXPECTED_UNSUPPORTED_COMPLETION_DETECTION_ROW_IDS and score.surface == "execution"
