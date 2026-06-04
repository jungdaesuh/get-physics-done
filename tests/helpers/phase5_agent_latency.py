"""Provider-free Phase 5 useful-action latency rows for agent prompts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from tests.helpers.persona_trace import (
    FakePersonaTrace,
    FakePersonaTurn,
    content_hydration_before_selection_count,
    conversation_turn_count,
    first_useful_action_class,
    physics_progress_count,
    physics_to_schema_ratio_class,
    raw_reload_leakage_count,
    schema_surface_count,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE5_AGENT_LATENCY_MATRIX_PATH = REPO_ROOT / "tests" / "fixtures" / "phase5_agent_latency_matrix.json"
REQUIRED_PHASE5_AGENT_LATENCY_ROW_IDS = frozenset(f"P5-AGENT-LAT-{index:02d}" for index in range(1, 5))
ROW_TIERS = frozenset({"jit_canary"})

_ZERO_COUNT_KEYS = (
    "invalid_command_suggestion_count",
    "schema_repair_loop_count",
    "duplicate_question_bucket_count",
    "question_before_action_count",
    "stale_artifact_trust_count",
    "post_stop_activity_count",
    "unexpected_write_count",
    "unsupported_completion_claim_count",
)


@dataclass(frozen=True, slots=True)
class Phase5AgentLatencyRow:
    row_id: str
    agent_name: str
    fixture_family: str
    source_owners: tuple[str, ...]
    test_owners: tuple[str, ...]
    row_tier: str = "jit_canary"
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    persona_class: str = "phase5_agent_latency"
    prompt_variant_class: str = "class_only"
    expected_turn0_intent_class: str = ""
    expected_turn0_physics_progress_class: str = ""
    behavior_metric_bounds: Mapping[str, object] = field(default_factory=dict)
    expected_metric_classes: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = "phase5.agent_latency_matrix.v1"


@dataclass(frozen=True, slots=True)
class Phase5AgentLatencyScore:
    row: Phase5AgentLatencyRow
    trace: FakePersonaTrace
    metric_counts: Mapping[str, int]
    metric_classes: Mapping[str, str]
    hard_budget_failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.hard_budget_failures


def load_phase5_agent_latency_rows(
    path: Path = PHASE5_AGENT_LATENCY_MATRIX_PATH,
    *,
    repo_root: Path = REPO_ROOT,
    validate_owners: bool = True,
) -> tuple[Phase5AgentLatencyRow, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version", ""))
    rows = tuple(_row_from_mapping(row, schema_version) for row in payload["rows"])
    for row in rows:
        _validate_row(row, repo_root=repo_root, validate_owners=validate_owners)
    return rows


def build_phase5_agent_latency_trace(row: Phase5AgentLatencyRow) -> FakePersonaTrace:
    return FakePersonaTrace(
        row_id=row.row_id,
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class=row.expected_turn0_intent_class,
                action_class="concrete_command",
                physics_progress_class=row.expected_turn0_physics_progress_class,
            ),
        ),
    )


def score_phase5_agent_latency_row(
    row: Phase5AgentLatencyRow,
    *,
    trace_override: FakePersonaTrace | None = None,
) -> Phase5AgentLatencyScore:
    trace = trace_override or build_phase5_agent_latency_trace(row)
    counts = _trace_counts(trace)
    classes = _trace_classes(trace, counts)
    failures = _hard_budget_failures(row, trace, counts, classes)
    return Phase5AgentLatencyScore(row, trace, counts, classes, failures)


def score_phase5_agent_latency_rows(rows: Sequence[Phase5AgentLatencyRow]) -> tuple[Phase5AgentLatencyScore, ...]:
    return tuple(score_phase5_agent_latency_row(row) for row in rows if row.row_tier == "jit_canary")


def _row_from_mapping(row: Mapping[str, object], schema_version: str) -> Phase5AgentLatencyRow:
    expected_metric_classes = row.get("expected_metric_classes", {})
    if not isinstance(expected_metric_classes, Mapping):
        raise AssertionError(f"{row['row_id']} expected_metric_classes must be a mapping")
    return Phase5AgentLatencyRow(
        row_id=str(row["row_id"]),
        agent_name=str(row["agent_name"]),
        fixture_family=str(row["fixture_family"]),
        source_owners=_str_tuple(row["source_owners"]),
        test_owners=_str_tuple(row["test_owners"]),
        row_tier=str(row.get("row_tier", "jit_canary")),
        provider_launch_allowed=bool(row.get("provider_launch_allowed", False)),
        network_allowed=bool(row.get("network_allowed", False)),
        raw_artifacts_allowed=bool(row.get("raw_artifacts_allowed", False)),
        persona_class=str(row.get("persona_class", "phase5_agent_latency")),
        prompt_variant_class=str(row.get("prompt_variant_class", "class_only")),
        expected_turn0_intent_class=str(row["expected_turn0_intent_class"]),
        expected_turn0_physics_progress_class=str(row["expected_turn0_physics_progress_class"]),
        behavior_metric_bounds=dict(row.get("behavior_metric_bounds", {})),
        expected_metric_classes={str(key): str(value) for key, value in expected_metric_classes.items()},
        schema_version=schema_version,
    )


def _validate_row(
    row: Phase5AgentLatencyRow,
    *,
    repo_root: Path,
    validate_owners: bool,
) -> None:
    if row.row_tier not in ROW_TIERS:
        raise AssertionError(f"{row.row_id} has invalid row_tier {row.row_tier}")
    if row.provider_launch_allowed or row.network_allowed or row.raw_artifacts_allowed:
        raise AssertionError(f"{row.row_id} must stay provider-free and class-only")
    for field_name in (
        "row_id",
        "agent_name",
        "persona_class",
        "prompt_variant_class",
        "expected_turn0_intent_class",
        "expected_turn0_physics_progress_class",
    ):
        _assert_classish_token(getattr(row, field_name), f"{row.row_id}.{field_name}")
    if not validate_owners:
        return
    for owner in (*row.source_owners, *row.test_owners):
        if not (repo_root / owner).exists():
            raise AssertionError(f"{row.row_id} references missing owner {owner}")


def _trace_counts(trace: FakePersonaTrace) -> dict[str, int]:
    counts = dict.fromkeys(_ZERO_COUNT_KEYS, 0)
    counts.update(
        {
            "structured_authority_coverage": 1,
            "conversation_turn_count": conversation_turn_count(trace),
            "physics_progress_count": physics_progress_count(trace),
            "schema_surface_count": schema_surface_count(trace),
            "raw_reload_leakage_count": raw_reload_leakage_count(trace),
            "content_hydration_before_selection_count": content_hydration_before_selection_count(trace),
        }
    )
    return counts


def _trace_classes(trace: FakePersonaTrace, counts: Mapping[str, int]) -> dict[str, str]:
    first_action = first_useful_action_class(trace)
    return {
        "first_useful_action_class": first_action,
        "useful_work_latency_class": _useful_work_latency_class(first_action, counts),
        "physics_to_schema_ratio_class": physics_to_schema_ratio_class(trace),
    }


def _useful_work_latency_class(first_action_class: str, counts: Mapping[str, int]) -> str:
    if first_action_class in {"missing", "not_applicable"}:
        return "missing"
    if first_action_class == "delayed":
        return "second_turn" if counts["conversation_turn_count"] == 2 else "delayed"
    return "first_turn"


def _hard_budget_failures(
    row: Phase5AgentLatencyRow,
    trace: FakePersonaTrace,
    counts: Mapping[str, int],
    classes: Mapping[str, str],
) -> tuple[str, ...]:
    failures = list(_metric_bound_failures(row.behavior_metric_bounds, counts))
    failures.extend(
        metric_key
        for metric_key, expected_class in row.expected_metric_classes.items()
        if classes.get(metric_key) != expected_class
    )
    turns = tuple(sorted(trace.turns, key=lambda turn: turn.turn_index))
    if not turns:
        failures.append("conversation_turn_count")
        return tuple(dict.fromkeys(failures))

    first = turns[0]
    if first.turn_index != 0:
        failures.append("turn0_index")
    if first.intent_class != row.expected_turn0_intent_class:
        failures.append("turn0_intent_class")
    if first.physics_progress_class != row.expected_turn0_physics_progress_class:
        failures.append("turn0_physics_progress_class")
    if first.schema_surface_class != "none":
        failures.append("turn0_schema_surface_class")
    return tuple(dict.fromkeys(failures))


def _metric_bound_failures(bounds: Mapping[str, object], counts: Mapping[str, int]) -> tuple[str, ...]:
    failures: list[str] = []
    for metric_key, raw_bound in bounds.items():
        if metric_key not in counts:
            failures.append(metric_key)
            continue
        bound = _metric_bound(raw_bound)
        if not _metric_bound_allows(bound, counts[metric_key]):
            failures.append(metric_key)
    return tuple(failures)


def _metric_bound(raw_bound: object) -> dict[str, int | None]:
    if isinstance(raw_bound, Mapping):
        return {
            "exact": _optional_int(raw_bound.get("exact")),
            "min": _optional_int(raw_bound.get("min")),
            "max": _optional_int(raw_bound.get("max")),
        }
    count = int(raw_bound)
    if count == 0:
        return {"exact": 0, "min": None, "max": None}
    return {"exact": None, "min": count, "max": None}


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _metric_bound_allows(bound: Mapping[str, int | None], observed: int) -> bool:
    exact = bound.get("exact")
    minimum = bound.get("min")
    maximum = bound.get("max")
    if exact is not None and observed != exact:
        return False
    if minimum is not None and observed < minimum:
        return False
    if maximum is not None and observed > maximum:
        return False
    return True


def _assert_classish_token(value: str, field_name: str) -> None:
    if not value:
        raise AssertionError(f"{field_name} must be non-empty")
    if value != value.strip() or any(character.isspace() for character in value) or "/" in value or "\\" in value:
        raise AssertionError(f"{field_name} must be a class token, not raw text or a path")


def _str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


__all__ = [
    "PHASE5_AGENT_LATENCY_MATRIX_PATH",
    "REQUIRED_PHASE5_AGENT_LATENCY_ROW_IDS",
    "ROW_TIERS",
    "Phase5AgentLatencyRow",
    "Phase5AgentLatencyScore",
    "build_phase5_agent_latency_trace",
    "load_phase5_agent_latency_rows",
    "score_phase5_agent_latency_row",
    "score_phase5_agent_latency_rows",
]
