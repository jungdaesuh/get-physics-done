"""Loader and contract constants for the provider-free Phase 4 persona matrix."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PHASE4_PERSONA_SCHEMA_VERSION = "phase4.persona_lifecycle_matrix.v1"

SURFACES = ("planning", "execution", "completion", "user_steering")
BEHAVIOR_METRIC_KEYS = (
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
)
MUTATION_GUARD_CLASSES = (
    "no_write",
    "expected_write_only",
    "unexpected_write",
    "state_mutated_on_reject",
)
NEXT_UP_SPECIFICITY_CLASSES = (
    "none",
    "vague",
    "concrete_command",
    "bounded_resume",
    "runtime_verify_work",
)
PERSONA_CLASSES = ("planner", "executor", "closer", "user_steering")
SCHEMA_WRESTLING_CLASSES = ("none", "minor", "high", "danger")
SMOOTHNESS_CLASSES = ("smooth", "acceptable", "clunky", "regressed")

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "phase4_persona"

SURFACE_FIXTURE_FILENAMES = {
    "planning": "planning_rows.json",
    "execution": "execution_rows.json",
    "completion": "completion_rows.json",
    "user_steering": "user_steering_rows.json",
}

SURFACE_SCENARIOS = {
    "planning": frozenset(
        {
            "plan_phase_bootstrap_lazy_loading",
            "missing_phase_no_target_invention",
            "project_contract_authority_block",
            "dirty_worktree_hard_stop",
            "proof_bearing_checker_audit_visibility",
        }
    ),
    "execution": frozenset(
        {
            "valid_final_plan_ready_to_execute",
            "invalid_gpd_verify_work_surface",
            "invalid_gpd_verify_phase_surface",
            "prose_success_no_return",
            "multiple_gpd_returns",
            "unfenced_raw_return_candidate",
            "empty_files_written_required_artifact",
            "omitted_files_written_field",
            "stale_artifact",
            "wrong_sibling_artifact",
            "checkpoint_missing_bounded_context",
            "checkpoint_with_bounded_context",
            "intermediate_plan_cannot_complete_phase",
            "applicator_result_prose_only",
        }
    ),
    "completion": frozenset(
        {
            "missing_verification_blocks_required_closeout",
            "gaps_found_verification_blocks",
            "human_needed_verification_blocks",
            "expert_needed_verification_blocks",
            "passed_verification_closeout_ready",
            "bounded_segment_blocks_closeout",
            "proof_bearing_without_passed_proof_redteam_blocks_closeout",
            "completed_phase_suggests_runtime_verify_work",
            "closeout_readiness_read_only_no_mutation",
        }
    ),
    "user_steering": frozenset(
        {
            "alignment_requires_explicit_ask_user_answer",
            "user_abort_stops_before_dispatch",
            "tangent_proposal_uses_existing_review_stop",
            "first_result_or_pre_fanout_routes_bounded_resume",
            "supervised_closeout_requires_concrete_next_up",
            "resume_prefers_canonical_bounded_segment",
        }
    ),
}

SCENARIO_SCORER_REGISTRY = {
    **dict.fromkeys(SURFACE_SCENARIOS["planning"], "score_planning_replay_row"),
    **dict.fromkeys(SURFACE_SCENARIOS["execution"], "score_execution_replay_row"),
    **dict.fromkeys(SURFACE_SCENARIOS["completion"], "score_completion_replay_row"),
    **dict.fromkeys(SURFACE_SCENARIOS["user_steering"], "score_user_steering_row"),
}


@dataclass(frozen=True)
class PersonaMatrixRow:
    schema_version: str
    row_id: str
    surface: str
    scenario: str
    fixture_family: str
    runtime_scope: tuple[str, ...]
    source_owners: tuple[str, ...]
    test_owners: tuple[str, ...]
    expected_finding: str
    expected_result_class: str
    behavior_contract_id: str
    persona_class: str
    prompt_variant_class: str
    expected_smoothness_class: str
    expected_schema_wrestling_class: str
    expected_next_up_specificity_class: str
    expected_mutation_guard_class: str
    expected_metric_bounds: tuple[tuple[str, int], ...]
    provider_launch_allowed: bool
    network_allowed: bool
    raw_artifacts_allowed: bool
    expected_state_status_class: str | None = None
    expected_next_action_class: str | None = None
    mutation_allowed: bool | None = None

    @property
    def scorer_name(self) -> str | None:
        return SCENARIO_SCORER_REGISTRY.get(self.scenario)


def fixture_path_for_surface(surface: str) -> Path:
    if surface not in SURFACE_FIXTURE_FILENAMES:
        valid = ", ".join(SURFACES)
        raise ValueError(f"unknown Phase 4 persona surface {surface!r}; expected one of: {valid}")
    return FIXTURE_DIR / SURFACE_FIXTURE_FILENAMES[surface]


def load_phase4_rows(surface: str | None = None) -> tuple[PersonaMatrixRow, ...]:
    surfaces = (surface,) if surface is not None else SURFACES
    rows: list[PersonaMatrixRow] = []
    for selected_surface in surfaces:
        fixture_path = fixture_path_for_surface(selected_surface)
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture_surface = _required_str(payload, "surface")
        if fixture_surface != selected_surface:
            raise ValueError(f"{fixture_path} declares surface {fixture_surface!r}, expected {selected_surface!r}")
        for raw_row in _required_list(payload, "rows"):
            if not isinstance(raw_row, dict):
                raise TypeError(f"{fixture_path} contains a non-object row: {raw_row!r}")
            row = _row_from_mapping(raw_row)
            if row.surface != selected_surface:
                raise ValueError(f"{fixture_path} row {row.row_id} declares surface {row.surface!r}")
            rows.append(row)
    return tuple(rows)


def _row_from_mapping(row: dict[str, object]) -> PersonaMatrixRow:
    matrix_row = PersonaMatrixRow(
        schema_version=_required_str(row, "schema_version"),
        row_id=_required_str(row, "row_id"),
        surface=_required_str(row, "surface"),
        scenario=_required_str(row, "scenario"),
        fixture_family=_required_str(row, "fixture_family"),
        runtime_scope=_required_str_tuple(row, "runtime_scope"),
        source_owners=_required_str_tuple(row, "source_owners"),
        test_owners=_required_str_tuple(row, "test_owners"),
        expected_finding=_required_str(row, "expected_finding"),
        expected_result_class=_required_str(row, "expected_result_class"),
        behavior_contract_id=_required_str(row, "behavior_contract_id"),
        persona_class=_required_known_str(row, "persona_class", PERSONA_CLASSES),
        prompt_variant_class=_required_str(row, "prompt_variant_class"),
        expected_smoothness_class=_required_known_str(row, "expected_smoothness_class", SMOOTHNESS_CLASSES),
        expected_schema_wrestling_class=_required_known_str(
            row,
            "expected_schema_wrestling_class",
            SCHEMA_WRESTLING_CLASSES,
        ),
        expected_next_up_specificity_class=_required_known_str(
            row,
            "expected_next_up_specificity_class",
            NEXT_UP_SPECIFICITY_CLASSES,
        ),
        expected_mutation_guard_class=_required_known_str(
            row,
            "expected_mutation_guard_class",
            MUTATION_GUARD_CLASSES,
        ),
        expected_metric_bounds=_required_metric_bounds(row, "expected_metric_bounds"),
        provider_launch_allowed=_required_bool(row, "provider_launch_allowed"),
        network_allowed=_required_bool(row, "network_allowed"),
        raw_artifacts_allowed=_required_bool(row, "raw_artifacts_allowed"),
        expected_state_status_class=_optional_str(row, "expected_state_status_class"),
        expected_next_action_class=_optional_str(row, "expected_next_action_class"),
        mutation_allowed=_optional_bool(row, "mutation_allowed"),
    )
    _validate_row_contract(matrix_row)
    return matrix_row


def persona_row_from_matrix_row(row: PersonaMatrixRow):
    """Coerce a canonical matrix row into the current shared replay row model."""

    from tests.helpers.phase4_persona.replay import PersonaRow

    return PersonaRow(
        row_id=row.row_id,
        surface=row.surface,
        scenario=row.scenario,
        expected_finding=row.expected_finding,
        expected_result_class=row.expected_result_class,
        provider_launch_allowed=row.provider_launch_allowed,
        network_allowed=row.network_allowed,
        raw_artifacts_allowed=row.raw_artifacts_allowed,
        mutation_allowed=bool(row.mutation_allowed),
        expected_state_status_class=row.expected_state_status_class,
        expected_next_action_class=row.expected_next_action_class,
        fixture_family=row.fixture_family,
        runtime_scope=row.runtime_scope,
        schema_version=row.schema_version,
    )


def _required_str(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _required_known_str(mapping: dict[str, object], key: str, choices: tuple[str, ...]) -> str:
    value = _required_str(mapping, key)
    if value not in choices:
        valid = ", ".join(choices)
        raise ValueError(f"{key} must be one of: {valid}")
    return value


def _optional_str(mapping: dict[str, object], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string when set")
    return value


def _required_bool(mapping: dict[str, object], key: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


def _optional_bool(mapping: dict[str, object], key: str) -> bool | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean when set")
    return value


def _required_list(mapping: dict[str, object], key: str) -> list[object]:
    value = mapping.get(key)
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    return value


def _required_str_tuple(mapping: dict[str, object], key: str) -> tuple[str, ...]:
    value = _required_list(mapping, key)
    if not value or not all(isinstance(item, str) and item for item in value):
        raise TypeError(f"{key} must be a non-empty list of strings")
    return tuple(value)


def _required_metric_bounds(mapping: dict[str, object], key: str) -> tuple[tuple[str, int], ...]:
    value = mapping.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object of behavior metric integer bounds")
    if not value:
        raise TypeError(f"{key} must name at least one behavior metric bound")

    bounds: list[tuple[str, int]] = []
    for metric_name, metric_bound in value.items():
        if not isinstance(metric_name, str) or metric_name not in BEHAVIOR_METRIC_KEYS:
            valid = ", ".join(BEHAVIOR_METRIC_KEYS)
            raise ValueError(f"{key} has unknown behavior metric {metric_name!r}; expected one of: {valid}")
        if type(metric_bound) is not int or metric_bound < 0:
            raise TypeError(f"{key}.{metric_name} must be a non-negative integer")
        bounds.append((metric_name, metric_bound))
    return tuple(sorted(bounds))


def _validate_row_contract(row: PersonaMatrixRow) -> None:
    expected_contract_id = f"{row.surface}.{row.scenario}"
    if row.behavior_contract_id != expected_contract_id:
        raise ValueError(
            f"{row.row_id} behavior_contract_id {row.behavior_contract_id!r} "
            f"must be {expected_contract_id!r}"
        )
    if row.surface not in SURFACE_SCENARIOS:
        raise ValueError(f"{row.row_id} declares unknown surface {row.surface!r}")
    if row.scenario not in SURFACE_SCENARIOS[row.surface]:
        raise ValueError(f"{row.row_id} has unknown scenario {row.scenario!r} for {row.surface!r}")
    if row.runtime_scope != ("provider_free",):
        raise ValueError(f"{row.row_id} must stay in the provider_free runtime scope")
    if row.provider_launch_allowed or row.network_allowed or row.raw_artifacts_allowed:
        raise ValueError(f"{row.row_id} must stay provider-free and class-only")
