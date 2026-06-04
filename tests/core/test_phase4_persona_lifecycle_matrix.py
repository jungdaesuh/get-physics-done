"""Provider-free Phase 4 persona lifecycle replay smoke."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.phase4_persona.behavior_metrics import assert_behavior_contract
from tests.helpers.phase4_persona.replay import (
    PersonaRow,
    load_phase4_rows,
    registered_phase4_scenarios,
    score_phase4_row,
)


def test_phase4_persona_lifecycle_matrix_rows_are_provider_free_and_class_only() -> None:
    rows = load_phase4_rows()

    assert rows
    assert {row.scenario for row in rows} == registered_phase4_scenarios()
    assert all(not row.row_id.startswith("P4-S-") for row in rows)
    assert {row.surface for row in rows} == {"execution", "completion"}
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert all(row.fixture_family.endswith("_class") for row in rows)
    assert all(row.runtime_scope == ("provider_free",) for row in rows)


@pytest.mark.parametrize("row", load_phase4_rows(), ids=lambda row: f"{row.row_id}-{row.scenario}")
def test_phase4_persona_lifecycle_matrix(row: PersonaRow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outcome = score_phase4_row(row, tmp_path, monkeypatch)

    assert outcome.provider_launch_allowed is False
    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    assert row.expected_finding in outcome.failure_classes
    assert isinstance(outcome.accepted, bool)
    if not row.mutation_allowed:
        assert outcome.mutated is False
    if row.expected_state_status_class is not None:
        assert outcome.state_status_class == row.expected_state_status_class
    if row.expected_next_action_class is not None:
        assert outcome.next_action_class == row.expected_next_action_class

    score = assert_behavior_contract(row, outcome)
    assert score.row_id == row.row_id
    assert score.surface == row.surface
    assert score.scenario == row.scenario
    assert score.metric_counts["unexpected_write_count"] == 0
    if row.expected_next_action_class == "runtime_verify_work":
        assert score.metric_counts["invalid_command_suggestion_count"] == 0
        assert score.metric_classes["next_up_specificity_class"] == "runtime_verify_work"
