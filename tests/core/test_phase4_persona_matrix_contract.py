"""Contract checks for the provider-free Phase 4 persona row matrix."""

from __future__ import annotations

import re
from typing import Protocol

from tests.helpers.phase4_persona.completion import completion_replay_rows, score_completion_replay_row
from tests.helpers.phase4_persona.execution import execution_replay_rows, score_execution_replay_row
from tests.helpers.phase4_persona.matrix import (
    BEHAVIOR_METRIC_KEYS,
    MUTATION_GUARD_CLASSES,
    NEXT_UP_SPECIFICITY_CLASSES,
    PERSONA_CLASSES,
    PHASE4_PERSONA_SCHEMA_VERSION,
    REPO_ROOT,
    SCENARIO_SCORER_REGISTRY,
    SCHEMA_WRESTLING_CLASSES,
    SMOOTHNESS_CLASSES,
    SURFACE_SCENARIOS,
    SURFACES,
    fixture_path_for_surface,
    load_phase4_rows,
)
from tests.helpers.phase4_persona.planning import load_planning_replay_rows, score_planning_replay_row
from tests.helpers.phase4_persona.user_steering import score_user_steering_row, user_steering_rows

_ROW_ID_RE = re.compile(r"^P4-(PLAN|EXEC|COMP|USER)-[0-9]{2}$")
_SCORER_NAME_RE = re.compile(r"^score_[a-z0-9_]+$")
_EXPECTED_ROW_IDS_BY_SURFACE = {
    "planning": tuple(f"P4-PLAN-{index:02d}" for index in range(1, 6)),
    "execution": tuple(f"P4-EXEC-{index:02d}" for index in range(1, 15)),
    "completion": tuple(f"P4-COMP-{index:02d}" for index in range(1, 10)),
    "user_steering": tuple(f"P4-USER-{index:02d}" for index in range(1, 7)),
}
_SCORER_FUNCTIONS = {
    "score_completion_replay_row": score_completion_replay_row,
    "score_execution_replay_row": score_execution_replay_row,
    "score_planning_replay_row": score_planning_replay_row,
    "score_user_steering_row": score_user_steering_row,
}
_FORBIDDEN_RAW_ARTIFACT_NAMES = frozenset(
    {
        "argv.json",
        "command.json",
        "command.txt",
        "env.json",
        "prompt.enveloped.txt",
        "prompt.txt",
        "provider-output.txt",
        "provider-reply.txt",
        "provider_output.txt",
        "provider_reply.txt",
        "raw-transcript.md",
        "raw_transcript.md",
        "stderr.txt",
        "stdout.jsonl",
        "stdout.txt",
        "transcript.md",
    }
)
_RAW_FIELD_NAMES = frozenset(
    {
        "argv",
        "command",
        "env",
        "prompt",
        "provider_output",
        "provider_reply",
        "raw_artifact",
        "raw_output",
        "raw_transcript",
        "stderr",
        "stdout",
        "transcript",
    }
)


class _ReplayRow(Protocol):
    row_id: str
    scenario: str
    expected_finding: str
    expected_result_class: str
    provider_launch_allowed: bool
    network_allowed: bool
    raw_artifacts_allowed: bool


def test_phase4_persona_fixture_files_load_for_every_surface() -> None:
    rows = load_phase4_rows()

    assert {row.surface for row in rows} == set(SURFACES)
    assert len(rows) == 34
    assert {fixture_path_for_surface(surface).name for surface in SURFACES} == {
        "planning_rows.json",
        "execution_rows.json",
        "completion_rows.json",
        "user_steering_rows.json",
    }


def test_phase4_persona_row_ids_are_unique_and_well_formed() -> None:
    rows = load_phase4_rows()
    row_ids = [row.row_id for row in rows]

    assert len(row_ids) == len(set(row_ids))
    assert all(_ROW_ID_RE.match(row_id) for row_id in row_ids)
    assert {
        surface: tuple(row.row_id for row in rows if row.surface == surface)
        for surface in SURFACES
    } == _EXPECTED_ROW_IDS_BY_SURFACE


def test_phase4_persona_rows_name_existing_owner_files() -> None:
    for row in load_phase4_rows():
        for owner in (*row.source_owners, *row.test_owners):
            owner_file = REPO_ROOT / owner
            assert owner_file.is_file(), f"{row.row_id} references missing owner {owner}"


def test_phase4_persona_rows_are_provider_free_and_class_only() -> None:
    for row in load_phase4_rows():
        assert row.schema_version == PHASE4_PERSONA_SCHEMA_VERSION
        assert row.provider_launch_allowed is False
        assert row.network_allowed is False
        assert row.raw_artifacts_allowed is False

        row_values = vars(row)
        assert _RAW_FIELD_NAMES.isdisjoint(row_values)
        assert all(isinstance(value, (str, bool, tuple, type(None))) for value in row_values.values())
        assert row.fixture_family.endswith("_class")
        assert "transcript" not in row.fixture_family
        assert all(type(metric_bound) is int for _, metric_bound in row.expected_metric_bounds)


def test_phase4_persona_rows_have_behavior_metric_contracts() -> None:
    behavior_contract_ids: list[str] = []

    for row in load_phase4_rows():
        behavior_contract_ids.append(row.behavior_contract_id)
        assert row.behavior_contract_id == f"{row.surface}.{row.scenario}"
        assert row.persona_class in PERSONA_CLASSES
        assert row.expected_smoothness_class in SMOOTHNESS_CLASSES
        assert row.expected_schema_wrestling_class in SCHEMA_WRESTLING_CLASSES
        assert row.expected_next_up_specificity_class in NEXT_UP_SPECIFICITY_CLASSES
        assert row.expected_mutation_guard_class in MUTATION_GUARD_CLASSES

        metric_bounds = dict(row.expected_metric_bounds)
        assert metric_bounds
        assert set(metric_bounds) <= set(BEHAVIOR_METRIC_KEYS)
        assert "structured_authority_coverage" in metric_bounds
        assert all(type(metric_bound) is int and metric_bound >= 0 for metric_bound in metric_bounds.values())

    assert len(behavior_contract_ids) == len(set(behavior_contract_ids))


def test_phase4_persona_rows_use_valid_surface_scenario_pairs() -> None:
    for row in load_phase4_rows():
        assert row.surface in SURFACES
        assert row.scenario in SURFACE_SCENARIOS[row.surface]


def test_phase4_persona_scenarios_have_registered_scorer_names() -> None:
    registered_scenarios = set(SCENARIO_SCORER_REGISTRY)
    fixture_scenarios = {row.scenario for row in load_phase4_rows()}

    assert fixture_scenarios <= registered_scenarios
    for row in load_phase4_rows():
        scorer_name = row.scorer_name
        assert scorer_name is not None
        assert _SCORER_NAME_RE.match(scorer_name)
        assert scorer_name in _SCORER_FUNCTIONS


def test_phase4_persona_matrix_rows_match_read_only_replay_row_contracts() -> None:
    replay_rows: dict[str, dict[tuple[str, str], _ReplayRow]] = {
        "planning": _rows_by_contract(load_planning_replay_rows()),
        "execution": _rows_by_contract(execution_replay_rows()),
        "completion": _rows_by_contract(completion_replay_rows()),
        "user_steering": _rows_by_contract(user_steering_rows()),
    }
    matrix_rows = load_phase4_rows()

    assert {
        surface: set(rows_by_contract)
        for surface, rows_by_contract in replay_rows.items()
    } == {
        surface: {(row.row_id, row.scenario) for row in matrix_rows if row.surface == surface}
        for surface in SURFACES
    }

    for row in matrix_rows:
        replay_row = replay_rows[row.surface][(row.row_id, row.scenario)]
        assert row.expected_finding == replay_row.expected_finding
        assert row.expected_result_class == replay_row.expected_result_class
        assert row.provider_launch_allowed is replay_row.provider_launch_allowed
        assert row.network_allowed is replay_row.network_allowed
        assert row.raw_artifacts_allowed is replay_row.raw_artifacts_allowed
        assert row.expected_state_status_class == getattr(replay_row, "expected_state_status_class", None)
        assert row.expected_next_action_class == getattr(replay_row, "expected_next_action_class", None)

        if row.surface == "completion":
            assert row.mutation_allowed is (not replay_row.expect_no_mutation)
        else:
            assert row.mutation_allowed is getattr(replay_row, "mutation_allowed", False)

        if row.surface == "user_steering":
            assert row.source_owners == tuple(path.as_posix() for path in replay_row.source_files)


def test_phase4_persona_fixture_text_has_no_raw_artifact_names() -> None:
    offenders: list[str] = []
    for surface in SURFACES:
        fixture_path = fixture_path_for_surface(surface)
        for line_number, line in enumerate(fixture_path.read_text(encoding="utf-8").splitlines(), start=1):
            for forbidden_name in _FORBIDDEN_RAW_ARTIFACT_NAMES:
                if forbidden_name in line:
                    relpath = fixture_path.relative_to(REPO_ROOT)
                    offenders.append(f"{relpath}:{line_number}:{forbidden_name}")

    assert not offenders, offenders


def _rows_by_contract(rows: tuple[_ReplayRow, ...]) -> dict[tuple[str, str], _ReplayRow]:
    return {(row.row_id, row.scenario): row for row in rows}
