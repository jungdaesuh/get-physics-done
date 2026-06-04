"""Provider-free Phase 4 planning persona replay tests."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from tests.helpers.phase4_persona.behavior_metrics import assert_behavior_contract
from tests.helpers.phase4_persona.matrix import (
    NEXT_UP_SPECIFICITY_CLASSES,
    PERSONA_CLASSES,
    SCHEMA_WRESTLING_CLASSES,
    SMOOTHNESS_CLASSES,
)
from tests.helpers.phase4_persona.planning import (
    PlanningReplayRow,
    PlanningReplayTrace,
    load_planning_replay_rows,
    planning_trace_for_row,
    score_planning_replay_row,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CLASS_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")

PLANNING_TRACE_EXPECTATIONS = {
    "P4-PLAN-01": {
        "first_useful_action_class": "immediate_command",
        "stop_integrity_class": "not_applicable",
        "artifact_handle_first_class": "handle_before_content",
    },
    "P4-PLAN-02": {
        "first_useful_action_class": "immediate_command",
        "stop_integrity_class": "not_applicable",
        "question_before_action_count": 1,
    },
    "P4-PLAN-03": {
        "first_useful_action_class": "safe_stop",
        "stop_integrity_class": "stopped_cleanly",
    },
    "P4-PLAN-04": {
        "first_useful_action_class": "safe_stop",
        "stop_integrity_class": "stopped_cleanly",
    },
    "P4-PLAN-05": {
        "first_useful_action_class": "immediate_command",
        "stop_integrity_class": "not_applicable",
    },
}


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


def _assert_trace_matches_expected_score_keys(trace: PlanningReplayTrace, score: object) -> None:
    if "physics_progress_count" in score.metric_counts:
        assert score.metric_counts["physics_progress_count"] == trace.physics_progress_count
    if "schema_surface_count" in score.metric_counts:
        assert score.metric_counts["schema_surface_count"] == trace.schema_surface_count
    if "first_useful_action_class" in score.metric_classes:
        assert score.metric_classes["first_useful_action_class"] == trace.first_useful_action_class
    if "stop_integrity_class" in score.metric_classes:
        assert score.metric_classes["stop_integrity_class"] == trace.stop_integrity_class
    if "physics_to_schema_ratio_class" in score.metric_classes:
        assert score.metric_classes["physics_to_schema_ratio_class"] == trace.physics_to_schema_ratio_class
    if "artifact_handle_first_class" in score.metric_classes:
        assert score.metric_classes["artifact_handle_first_class"] == trace.artifact_handle_first_class


def test_phase4_planning_persona_rows_are_provider_free_and_class_only() -> None:
    rows = load_planning_replay_rows()

    assert len(rows) == 5
    assert [row.row_id for row in rows] == [f"P4-PLAN-{index:02d}" for index in range(1, 6)]
    assert all(row.surface == "planning" for row in rows)
    assert all(row.fixture_family.endswith("_class") for row in rows)
    assert all(row.runtime_scope == ("provider_free",) for row in rows)
    assert {row.persona_class for row in rows} <= set(PERSONA_CLASSES)
    assert all(row.prompt_variant_class for row in rows)
    assert all(row.metadata_source in {"canonical_fixture", "compatibility_adapter"} for row in rows)
    assert len({row.scenario for row in rows}) == len(rows)
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert all(row.behavior_contract_id for row in rows)
    assert {row.expected_smoothness_class for row in rows} <= set(SMOOTHNESS_CLASSES)
    assert {row.expected_schema_wrestling_class for row in rows} <= set(SCHEMA_WRESTLING_CLASSES)
    assert {row.expected_next_up_specificity_class for row in rows} <= set(NEXT_UP_SPECIFICITY_CLASSES)
    assert all(row.expected_mutation_guard_class == "no_write" for row in rows)
    assert {row.expected_finding for row in rows} == {
        "plan_phase_bootstrap_lazy_loading",
        "missing_phase_no_target_invention",
        "project_contract_authority_block",
        "dirty_worktree_hard_stop",
        "proof_bearing_checker_audit_visibility",
    }
    for row in rows:
        trace = planning_trace_for_row(row)
        expected = PLANNING_TRACE_EXPECTATIONS[row.row_id]
        _assert_class_only(trace)
        assert trace.row_id == row.row_id
        assert trace.persona_class == row.persona_class
        assert trace.prompt_variant_class == row.prompt_variant_class
        assert trace.event_class_counts
        assert trace.event_class_counts["conversation_turn"] == len(trace.turns)
        assert trace.physics_progress_count >= 1
        assert trace.schema_surface_count <= trace.physics_progress_count + 1
        assert trace.first_useful_action_class == expected["first_useful_action_class"]
        assert trace.stop_integrity_class == expected["stop_integrity_class"]
        if "artifact_handle_first_class" in expected:
            assert trace.artifact_handle_first_class == expected["artifact_handle_first_class"]
        assert all((REPO_ROOT / owner).exists() for owner in row.source_owners)
        assert all((REPO_ROOT / owner).exists() for owner in row.test_owners)


@pytest.mark.parametrize(
    "row",
    load_planning_replay_rows(),
    ids=lambda row: f"{row.row_id}-{row.scenario}",
)
def test_phase4_planning_persona_replay_rows(
    row: PlanningReplayRow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / ".gpd-data"))

    outcome = score_planning_replay_row(row, tmp_path)
    trace = planning_trace_for_row(row)

    assert outcome.provider_launch_allowed is False
    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    assert row.expected_finding in outcome.failure_classes
    assert outcome.mutated is row.expected_mutated
    assert outcome.evidence_classes
    assert all("/Users/" not in evidence_class for evidence_class in outcome.evidence_classes)
    score = assert_behavior_contract(row, outcome, event=trace)
    expected = PLANNING_TRACE_EXPECTATIONS[row.row_id]
    assert score.metric_counts["duplicate_question_bucket_count"] == 0
    assert score.metric_counts["unexpected_write_count"] == 0
    assert score.metric_counts["question_before_action_count"] == expected.get("question_before_action_count", 0)
    _assert_trace_matches_expected_score_keys(trace, score)
