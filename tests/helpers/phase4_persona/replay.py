"""Provider-free replay API for Phase 4 persona lifecycle rows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Protocol

from tests.helpers.phase4_persona.matrix import (
    PHASE4_PERSONA_SCHEMA_VERSION,
    SURFACES,
    PersonaMatrixRow,
    fixture_path_for_surface,
)
from tests.helpers.phase4_persona.matrix import (
    load_phase4_rows as load_phase4_matrix_rows,
)
from tests.helpers.phase4_persona.scorers import (
    SCORERS,
    PersonaOutcome,
)
from tests.helpers.phase4_persona.scorers import (
    registered_phase4_scenarios as registered_phase4_scorer_scenarios,
)

SCHEMA_VERSION = PHASE4_PERSONA_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class PersonaRow:
    """Class-only replay row with no provider transcript or raw artifact payload."""

    row_id: str
    surface: str
    scenario: str
    expected_finding: str
    expected_result_class: str
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    mutation_allowed: bool = False
    expected_state_status_class: str | None = None
    expected_next_action_class: str | None = None
    fixture_family: str = "phase4_persona_replay"
    runtime_scope: tuple[str, ...] = ("provider_free",)
    schema_version: str = SCHEMA_VERSION


class _MonkeyPatchLike(Protocol):
    def setenv(self, name: str, value: str) -> None: ...


def _validate_rows(rows: tuple[PersonaRow, ...]) -> None:
    row_ids = [row.row_id for row in rows]
    if len(row_ids) != len(set(row_ids)):
        raise AssertionError("Phase 4 persona replay row ids must be unique")
    for row in rows:
        if row.schema_version != SCHEMA_VERSION:
            raise AssertionError(f"{row.row_id} has unsupported schema version {row.schema_version!r}")
        if row.provider_launch_allowed or row.network_allowed or row.raw_artifacts_allowed:
            raise AssertionError(f"{row.row_id} must stay provider-free and class-only")
        if row.scenario not in SCORERS:
            raise AssertionError(f"{row.row_id} has no registered scorer for scenario {row.scenario!r}")


def load_phase4_rows(surface: str | None = None) -> tuple[PersonaRow, ...]:
    """Return executable provider-free replay rows from the canonical fixture matrix."""

    return load_phase4_replay_rows(surface)


def load_phase4_replay_rows(surface: str | None = None) -> tuple[PersonaRow, ...]:
    """Load canonical matrix rows that have executable shared scorers."""

    rows = tuple(persona_row_from_matrix_row(row) for row in executable_phase4_matrix_rows(surface))
    _validate_rows(rows)
    return rows


def executable_phase4_matrix_rows(surface: str | None = None) -> tuple[PersonaMatrixRow | PersonaRow, ...]:
    """Return canonical matrix rows covered by the shared replay scorer registry."""

    scenarios = registered_phase4_scorer_scenarios()
    return tuple(row for row in _load_matrix_like_rows(surface) if persona_row_from_matrix_row(row).scenario in scenarios)


def registered_phase4_scenarios(surface: str | None = None) -> frozenset[str]:
    """Return executable scenario ids present in the currently loadable matrix rows."""

    return frozenset(persona_row_from_matrix_row(row).scenario for row in executable_phase4_matrix_rows(surface))


def persona_row_from_matrix_row(row: PersonaRow | PersonaMatrixRow | Mapping[str, object] | object) -> PersonaRow:
    """Coerce a canonical matrix row into the shared executable row model."""

    if isinstance(row, PersonaRow):
        return row
    if isinstance(row, Mapping):
        return persona_row_from_mapping(row)
    if is_dataclass(row):
        return persona_row_from_mapping(asdict(row))
    return persona_row_from_mapping(
        {
            "row_id": _required_attr(row, "row_id"),
            "surface": _required_attr(row, "surface"),
            "scenario": _required_attr(row, "scenario"),
            "expected_finding": _required_attr(row, "expected_finding"),
            "expected_result_class": _required_attr(row, "expected_result_class"),
            "provider_launch_allowed": _optional_attr(row, "provider_launch_allowed", False),
            "network_allowed": _optional_attr(row, "network_allowed", False),
            "raw_artifacts_allowed": _optional_attr(row, "raw_artifacts_allowed", False),
            "mutation_allowed": _optional_attr(row, "mutation_allowed", False),
            "expected_state_status_class": _optional_attr(row, "expected_state_status_class", None),
            "expected_next_action_class": _optional_attr(row, "expected_next_action_class", None),
            "fixture_family": _optional_attr(row, "fixture_family", "phase4_persona_replay"),
            "runtime_scope": _optional_attr(row, "runtime_scope", ("provider_free",)),
            "schema_version": _optional_attr(row, "schema_version", SCHEMA_VERSION),
        }
    )


def _load_matrix_like_rows(surface: str | None = None) -> tuple[PersonaMatrixRow | PersonaRow, ...]:
    try:
        return load_phase4_matrix_rows(surface)
    except (TypeError, ValueError) as exc:
        if not _can_fallback_to_fixture_rows(exc):
            raise
        return _load_fixture_replay_rows(surface)


def _can_fallback_to_fixture_rows(exc: Exception) -> bool:
    message = str(exc)
    return (
        "behavior_contract_id" in message
        or "expected_metric_bounds" in message
        or "unknown scenario" in message
    )


def _load_fixture_replay_rows(surface: str | None = None) -> tuple[PersonaRow, ...]:
    surfaces = (surface,) if surface is not None else SURFACES
    rows: list[PersonaRow] = []
    for selected_surface in surfaces:
        payload = json.loads(fixture_path_for_surface(selected_surface).read_text(encoding="utf-8"))
        if payload.get("surface") != selected_surface:
            raise ValueError(f"{selected_surface!r} fixture declares surface {payload.get('surface')!r}")
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list):
            raise TypeError(f"{selected_surface!r} fixture rows must be a list")
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                raise TypeError(f"{selected_surface!r} fixture contains a non-object row: {raw_row!r}")
            rows.append(persona_row_from_mapping(raw_row))
    return tuple(rows)


def persona_row_from_mapping(data: Mapping[str, object]) -> PersonaRow:
    """Coerce a future class-only fixture mapping into the current row model."""

    raw_runtime_scope = data.get("runtime_scope", ("provider_free",))
    if isinstance(raw_runtime_scope, str):
        runtime_scope = (raw_runtime_scope,)
    elif isinstance(raw_runtime_scope, (list, tuple, set)):
        runtime_scope = tuple(str(item) for item in raw_runtime_scope)
    else:
        runtime_scope = (str(raw_runtime_scope),)

    return PersonaRow(
        row_id=str(data["row_id"]),
        surface=str(data["surface"]),
        scenario=str(data["scenario"]),
        expected_finding=str(data["expected_finding"]),
        expected_result_class=str(data["expected_result_class"]),
        provider_launch_allowed=bool(data.get("provider_launch_allowed", False)),
        network_allowed=bool(data.get("network_allowed", False)),
        raw_artifacts_allowed=bool(data.get("raw_artifacts_allowed", False)),
        mutation_allowed=bool(data.get("mutation_allowed") or False),
        expected_state_status_class=(
            None if data.get("expected_state_status_class") is None else str(data["expected_state_status_class"])
        ),
        expected_next_action_class=(
            None if data.get("expected_next_action_class") is None else str(data["expected_next_action_class"])
        ),
        fixture_family=str(data.get("fixture_family", "phase4_persona_replay")),
        runtime_scope=runtime_scope,
        schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
    )


def _coerce_row(row: PersonaRow | Mapping[str, object] | object) -> PersonaRow:
    if isinstance(row, PersonaRow):
        return row
    if isinstance(row, Mapping):
        return persona_row_from_mapping(row)
    if is_dataclass(row):
        return persona_row_from_mapping(asdict(row))
    return persona_row_from_mapping(
        {
            "row_id": _required_attr(row, "row_id"),
            "surface": _required_attr(row, "surface"),
            "scenario": _required_attr(row, "scenario"),
            "expected_finding": _required_attr(row, "expected_finding"),
            "expected_result_class": _required_attr(row, "expected_result_class"),
            "provider_launch_allowed": _optional_attr(row, "provider_launch_allowed", False),
            "network_allowed": _optional_attr(row, "network_allowed", False),
            "raw_artifacts_allowed": _optional_attr(row, "raw_artifacts_allowed", False),
            "mutation_allowed": _optional_attr(row, "mutation_allowed", False),
            "expected_state_status_class": _optional_attr(row, "expected_state_status_class", None),
            "expected_next_action_class": _optional_attr(row, "expected_next_action_class", None),
            "fixture_family": _optional_attr(row, "fixture_family", "phase4_persona_replay"),
            "runtime_scope": _optional_attr(row, "runtime_scope", ("provider_free",)),
            "schema_version": _optional_attr(row, "schema_version", SCHEMA_VERSION),
        }
    )


def _required_attr(row: object, name: str) -> object:
    return getattr(row, name)


def _optional_attr(row: object, name: str, default: object) -> object:
    return getattr(row, name, default)


def score_phase4_row(
    row: PersonaRow | Mapping[str, object] | object,
    tmp_path: Path,
    monkeypatch: _MonkeyPatchLike | None = None,
) -> PersonaOutcome:
    """Replay one row through core lifecycle APIs without launching providers."""

    replay_row = _coerce_row(row)
    _validate_rows((replay_row,))
    if monkeypatch is not None:
        monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / ".gpd-data"))
    return SCORERS[replay_row.scenario](replay_row, tmp_path)


__all__ = [
    "PersonaOutcome",
    "PersonaRow",
    "SCHEMA_VERSION",
    "executable_phase4_matrix_rows",
    "load_phase4_rows",
    "load_phase4_replay_rows",
    "persona_row_from_mapping",
    "persona_row_from_matrix_row",
    "registered_phase4_scenarios",
    "score_phase4_row",
]
