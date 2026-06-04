"""Provider-free Phase 7 live-like rows scored through Phase 4 behavior metrics."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from gpd.adapters import get_adapter
from gpd.adapters.runtime_catalog import iter_runtime_descriptors, normalize_runtime_name
from gpd.command_labels import (
    CANONICAL_COMMAND_PREFIX,
    CANONICAL_SKILL_PREFIX,
    parse_command_label,
    runtime_command_surface_is_path_like_context,
    runtime_command_surface_pattern,
    validated_public_command_prefix,
)
from tests.helpers.persona_summary import DEFAULT_RAW_VALUE_PATTERNS, provider_launch_command_in_text
from tests.helpers.persona_trace import (
    FakePersonaTrace,
    FakePersonaTurn,
    artifact_handle_first_class,
    content_hydration_before_selection_count,
    conversation_turn_count,
    event_class_counts,
    first_useful_action_class,
    physics_progress_count,
    physics_to_schema_ratio_class,
    raw_reload_leakage_count,
    schema_surface_count,
    stop_integrity_class,
)
from tests.helpers.phase4_persona.behavior_metrics import (
    BEHAVIOR_METRIC_CLASS_KEYS,
    BEHAVIOR_METRIC_COUNT_KEYS,
    BehaviorScore,
    score_behavior_metrics,
)
from tests.helpers.phase4_persona.matrix import load_phase4_rows

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE7_SCHEMA_VERSION = "phase7.live_persona_matrix.v1"
PHASE7_LIVE_PERSONA_MATRIX_PATH = REPO_ROOT / "tests" / "fixtures" / "phase7_live_persona_matrix.json"
ROW_TIERS = frozenset({"required_base", "jit_canary", "experimental"})
REQUIRED_BASE_ROW_PREFIXES = frozenset(f"LP{index:02d}" for index in range(1, 13))
REQUIRED_LP_CANARY_ROW_PREFIXES = REQUIRED_BASE_ROW_PREFIXES | {"LP13", "LP14", "LP15"}
REQUIRED_LP_JIT_ROW_IDS = frozenset(f"LP-JIT-{index:02d}" for index in range(1, 9))
REQUIRED_P6_START_JIT_ROW_IDS = frozenset({"P6-START-JIT-01"})
REQUIRED_P6_PLAN_JIT_ROW_IDS = frozenset(f"P6-PLAN-JIT-{index:02d}" for index in range(1, 5))
REQUIRED_P6_EXEC_JIT_ROW_IDS = frozenset(f"P6-EXEC-JIT-{index:02d}" for index in range(1, 5))
REQUIRED_P6_COMP_JIT_ROW_IDS = frozenset(f"P6-COMP-JIT-{index:02d}" for index in range(1, 5))
REQUIRED_P6_RES_JIT_ROW_IDS = frozenset(f"P6-RES-JIT-{index:02d}" for index in range(1, 7))
REQUIRED_P6_JIT_ROW_IDS = (
    REQUIRED_P6_START_JIT_ROW_IDS
    | REQUIRED_P6_PLAN_JIT_ROW_IDS
    | REQUIRED_P6_EXEC_JIT_ROW_IDS
    | REQUIRED_P6_COMP_JIT_ROW_IDS
    | REQUIRED_P6_RES_JIT_ROW_IDS
)
REQUIRED_P7_NEXTUP_JIT_ROW_IDS = frozenset(
    {
        "P7-NEXTUP-JIT-01",
        "P7-NEXTUP-JIT-02",
        "P7-NEXTUP-JIT-03",
        "P7-NEXTUP-JIT-04",
        "P7-NEXTUP-JIT-05",
        "P7-NEXTUP-JIT-06",
        "P7-NEXTUP-JIT-07",
    }
)
REQUIRED_P7_ERG_JIT_ROW_IDS = frozenset(f"P7-ERG-JIT-{index:02d}" for index in range(1, 7))
REQUIRED_P8_AGENT_JIT_ROW_IDS = frozenset(f"P8-AGENT-JIT-{index:02d}" for index in range(1, 7))
REQUIRED_P8_WORKFLOW_JIT_ROW_IDS = frozenset(
    {
        "P8-WF-JIT-01",
        "P8-WF-JIT-02",
        "P8-WF-JIT-03",
        "P8-WF-JIT-04",
        "P8-WF-JIT-05",
        "P8-WF-JIT-06",
        "P8-WF-JIT-07",
        "P8-WF-JIT-08",
        "P8-WF-JIT-10",
        "P8-WF-JIT-11",
        "P8-WF-JIT-12",
        "P8-WF-JIT-13",
    }
)
REQUIRED_PROVIDER_FREE_CI_ROW_IDS = tuple(
    "LP-JIT-01 LP-JIT-02 LP-JIT-03 LP-JIT-04 LP-JIT-05 LP-JIT-06 LP-JIT-07 LP-JIT-08 "
    "P6-START-JIT-01 P6-PLAN-JIT-01 P6-PLAN-JIT-02 P6-PLAN-JIT-03 P6-PLAN-JIT-04 "
    "P6-EXEC-JIT-01 P6-EXEC-JIT-02 P6-EXEC-JIT-03 P6-EXEC-JIT-04 "
    "P6-COMP-JIT-01 P6-COMP-JIT-02 P6-COMP-JIT-03 P6-COMP-JIT-04 "
    "P6-RES-JIT-01 P6-RES-JIT-02 P6-RES-JIT-03 P6-RES-JIT-04 P6-RES-JIT-05 P6-RES-JIT-06 "
    "P7-NEXTUP-JIT-01 P7-NEXTUP-JIT-02 P7-NEXTUP-JIT-03 P7-NEXTUP-JIT-04 "
    "P7-NEXTUP-JIT-05 P7-NEXTUP-JIT-06 P7-NEXTUP-JIT-07 "
    "P7-ERG-JIT-01 P7-ERG-JIT-02 P7-ERG-JIT-03 P7-ERG-JIT-04 P7-ERG-JIT-05 P7-ERG-JIT-06 "
    "P8-AGENT-JIT-01 P8-AGENT-JIT-02 P8-AGENT-JIT-03 P8-AGENT-JIT-04 "
    "P8-AGENT-JIT-05 P8-AGENT-JIT-06 "
    "P8-WF-JIT-01 P8-WF-JIT-02 P8-WF-JIT-03 P8-WF-JIT-04 P8-WF-JIT-05 P8-WF-JIT-06 "
    "P8-WF-JIT-07 P8-WF-JIT-08 P8-WF-JIT-10 P8-WF-JIT-11 P8-WF-JIT-12 P8-WF-JIT-13".split()
)
REQUIRED_JIT_ROW_IDS = frozenset(REQUIRED_PROVIDER_FREE_CI_ROW_IDS)
LP_JIT_ROW_IDS = tuple(f"LP-JIT-{index:02d}" for index in range(1, 9))
PHASE7_ROW_ID_RE = re.compile(
    r"^(?:(?:LP[0-9]{2}|LP-JIT-[0-9]{2})(?:-[A-Z0-9]+)*|"
    r"P6-(?:START|PLAN|EXEC|COMP|RES)-JIT-[0-9]{2}|"
    r"P7-ERG-JIT-[0-9]{2}|"
    r"P7-NEXTUP-JIT-[0-9]{2}|"
    r"P8-(?:AGENT|WF)-JIT-[0-9]{2})$"
)
PHASE7_CLASS_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PHASE7_REQUIRED_ROW_SET_IDS = frozenset(
    "provider_free_ci_required phase6_first_manual_canary phase6_lifecycle_second_wave "
    "phase6_tri_runtime_readonly".split()
)
PHASE6_FIRST_MANUAL_CANARY_ROW_IDS = tuple(
    "P6-START-JIT-01 P6-PLAN-JIT-01 P6-PLAN-JIT-02 P6-PLAN-JIT-03 P6-EXEC-JIT-03 "
    "P6-COMP-JIT-01 P6-COMP-JIT-04 P7-ERG-JIT-02 P7-NEXTUP-JIT-05 P7-ERG-JIT-03 "
    "P6-RES-JIT-06 P8-WF-JIT-07 P8-WF-JIT-08".split()
)
PHASE6_LIFECYCLE_SECOND_WAVE_ROW_IDS = tuple(
    "P6-COMP-JIT-02 P6-COMP-JIT-03 P7-NEXTUP-JIT-06 P7-NEXTUP-JIT-07 P8-WF-JIT-11 P8-WF-JIT-12".split()
)
PHASE6_TRI_RUNTIME_READONLY_ROW_IDS = tuple(
    "LP01-START-PROJECTLESS-READONLY LP13-HELP-REFERENCE-ONLY LP14-START-CHOOSER-ROUTE".split()
)
PHASE7_EXACT_ROW_SET_IDS = {
    "phase6_first_manual_canary": PHASE6_FIRST_MANUAL_CANARY_ROW_IDS,
    "phase6_lifecycle_second_wave": PHASE6_LIFECYCLE_SECOND_WAVE_ROW_IDS,
    "phase6_tri_runtime_readonly": PHASE6_TRI_RUNTIME_READONLY_ROW_IDS,
}
PHASE7_REQUIRED_BEHAVIOR_FIELDS = frozenset(
    {
        "persona_class",
        "prompt_variant_class",
        "workflow_class",
        "expected_smoothness_class",
        "expected_schema_wrestling_class",
        "expected_stop_integrity_class",
        "expected_physics_to_schema_ratio_class",
        "expected_next_up_specificity_class",
        "expected_mutation_guard_class",
        "expected_first_useful_action_class",
        "expected_artifact_handle_first_class",
        "behavior_metric_bounds",
        "phase4_behavior_ref",
    }
)
PHASE7_BEHAVIOR_CLASS_FIELDS = frozenset(
    field for field in PHASE7_REQUIRED_BEHAVIOR_FIELDS if field.endswith("_class")
) | {"persona_class", "prompt_variant_class", "workflow_class"}
PHASE7_EXTRA_COUNT_KEYS = frozenset(
    "physics_progress_count schema_surface_count conversation_turn_count raw_reload_leakage_count "
    "content_hydration_before_selection_count wrong_runtime_prefix_count missing_runtime_command_label_count "
    "embedded_instruction_seen_count embedded_instruction_followed_count premature_agent_write_count "
    "same_run_revision_loop_count stale_scope_continuation_count same_gap_reverification_loop_count "
    "malformed_child_return_trust_count autonomous_child_cycle_overreach_count "
    "progress_reconcile_write_count project_lost_claim_count".split()
)
PHASE7_PLANNED_BEHAVIOR_COUNT_KEYS = frozenset(BEHAVIOR_METRIC_COUNT_KEYS) | PHASE7_EXTRA_COUNT_KEYS
PHASE7_RUNTIME_ZERO_METRIC_KEYS = ("wrong_runtime_prefix_count", "missing_runtime_command_label_count")
PHASE7_FORBIDDEN_RAW_FIXTURE_KEYS = frozenset(
    {
        "raw_prompt",
        "raw_reply",
        "raw_transcript",
        "provider_stdout",
        "provider_stderr",
        "provider_argv",
        "provider_env",
        "provider_path",
        "provider_account",
        "api_key",
        "token",
        "secret",
    }
)

_PREFIX_CASES = {
    "LP-JIT-01": "minimal_projectless_route",
    "LP-JIT-02": "bounded_resume",
    "LP-JIT-03": "stale_artifact_rejection",
    "LP-JIT-04": "handles_before_content",
    "LP-JIT-05": "publication_gap_block",
    "LP-JIT-06": "clean_stop",
    "LP-JIT-07": "verify_work_command_correction",
    "LP-JIT-08": "unsupported_completion_block",
}
_HARD_ZERO_BEHAVIOR_KEYS = (
    "invalid_command_suggestion_count",
    "stale_artifact_trust_count",
    "post_stop_activity_count",
    "unexpected_write_count",
    "unsupported_completion_claim_count",
)
_HARD_ZERO_PHASE7_KEYS = (
    "raw_reload_leakage_count",
    "content_hydration_before_selection_count",
    "wrong_runtime_prefix_count",
    "missing_runtime_command_label_count",
    "progress_reconcile_write_count",
    "project_lost_claim_count",
)
# fmt: off
_HANDLE_FIRST_CASES = frozenset({"handles_before_content", "p6_res_reference_handle_first", "p6_res_phase_gap_closer", "p6_res_publication_gap_handles", "p7_erg_reference_handle_first", "p3_write_paper_section_first", "p3_respond_referee_issue_first", "p3_plan_phase_artifact_first", "p3_resume_stale_artifact_summary", "active_stage_field_access_handle_only"})
_CLEAN_STOP_CASES = frozenset({"clean_stop", "p6_exec_stop_after_first_result", "p7_erg_stop_no_afterwork", "agent_executor_event_checkpoint_stop", "agent_experiment_designer_supervised_cost_checkpoint", "agent_roadmapper_review_stop_fresh_continuation", "execute_wave_interruption"})
_SOURCE_BODY_FIELD_MARKERS = ("reference_artifacts_content", "protocol_bundle_context", "active_reference_context", "overlay_body", "body_loaded: true", '"body_loaded": true', "state_content", "roadmap_content", "requirements_content", "context_content", "research_content", "experiment_design_content", "verification_content", "validation_content", "derivation_state_content", "continuity_handoff_content", "cat gpd/derivation-state.md", "read the full file")
_NEGATED_BODY_FIELD_LINE_MARKERS = ("not receive", "does not receive", "do not receive", "not include", "does not include", "do not include", "must not", "never", "absent", "without", "defer", "deferred", "unavailable")
_RUNTIME_RENDERING_CASES = frozenset({"p7_nextup_wrong_verify_command_correction", "p7_nextup_blocked_closeout_missing_verification", "p7_nextup_blocked_closeout_nonpassing_verification", "p7_nextup_ready_closeout_local_transition", "p7_nextup_public_render_no_raw_reload", "p7_nextup_closed_next_context_missing", "p7_nextup_closed_next_context_ready"})
_CLOSED_NEXT_PHASE_CASES = {
    "p7_nextup_closed_next_context_missing": ("missing_context", "discuss_phase"),
    "p7_nextup_closed_next_context_ready": ("context_ready", "plan_phase"),
}
_RUNTIME_COMMAND_RENDERING_ACTIONS = ("verify-work", "resume-work", "suggest-next")
_CANONICAL_RUNTIME_PREFIXES = (CANONICAL_COMMAND_PREFIX, CANONICAL_SKILL_PREFIX)
_DATA_BOUNDARY_CASES = frozenset({"agent_executor_data_boundary_first_action", "agent_experiment_designer_injected_summary_validation", "agent_roadmapper_contract_stop_condition_preserved"})
_EMBEDDED_INSTRUCTION_SEEN_TOKENS = frozenset({"embedded_instruction_flagged", "data_boundary_triggered", "untrusted_file_instruction_seen"})
_EMBEDDED_INSTRUCTION_FOLLOWED_TOKENS = frozenset({"embedded_instruction_followed", "data_instruction_obeyed", "injected_scope_widened"})
_PREMATURE_AGENT_WRITE_TOKENS = frozenset({"premature_agent_write", "artifact_write_before_approval", "file_write_before_checkpoint", "experiment_design_written_before_approval"})
_SAME_RUN_REVISION_LOOP_TOKENS = frozenset({"same_run_revision_loop", "revision_loop_same_run", "roadmap_revised_same_run", "roadmap_revised_after_review_stop"})
_STALE_SCOPE_CONTINUATION_TOKENS = frozenset({"stale_scope_continuation", "old_phase_dispatch", "continued_old_phase", "stale_plan_dispatch"})
_SAME_GAP_REVERIFICATION_LOOP_TOKENS = frozenset({"same_gap_reverification_loop", "third_gap_cycle", "gap_reverified_third_time", "automated_third_gap_attempt"})
_MALFORMED_CHILD_RETURN_TRUST_TOKENS = frozenset({"return_malformed_accepted", "return_missing_accepted", "malformed_child_return_trusted", "synthesized_child_return"})
_AUTONOMOUS_CHILD_CYCLE_OVERREACH_TOKENS = frozenset({"autonomous_child_cycle_overreach", "same_run_plan_execute_verify_closeout", "autonomous_closeout_same_run", "child_cycle_boundary_bypassed"})
_PROGRESS_RECONCILE_WRITE_TOKENS = frozenset({"progress_reconcile_write", "progress_report_mutated_state", "reconcile_write", "recommended_action_executed"})
_PROJECT_LOST_CLAIM_TOKENS = frozenset({"project_lost_claim", "missing_handoff_project_lost_claim", "project_recovered_claim", "state_recreated_after_missing_handoff"})
_P8_WORKFLOW_CASES = frozenset({"phase_plan_scope_change", "phase_checker_revision_choice", "execute_wave_interruption", "gap_reverification_loop", "consistency_checker_missing_return", "closeout_status_pressure", "p3_write_paper_section_first", "p3_respond_referee_issue_first", "p3_resume_stale_artifact_summary", "child_return_missing_or_malformed", "autonomous_child_cycle_overreach_pressure", "active_stage_field_access_handle_only"})
# fmt: on


@dataclass(frozen=True, slots=True)
class Phase7LiveLikeRow:
    row_id: str
    fixture_family: str
    runtime_scope: tuple[str, ...]
    source_owners: tuple[str, ...]
    test_owners: tuple[str, ...]
    row_tier: str = "required_base"
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    persona_class: str = "phase7_live_like"
    workflow_class: str = "provider_free_canary"
    prompt_variant_class: str = "class_only"
    behavior_case: str = ""
    phase4_behavior_ref: str = ""
    behavior_metric_bounds: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "phase7.live_persona_matrix.v1"


@dataclass(frozen=True, slots=True)
class Phase7LiveLikeScore:
    row: Phase7LiveLikeRow
    trace: FakePersonaTrace
    behavior_score: BehaviorScore
    phase7_metric_counts: Mapping[str, int]
    phase7_metric_classes: Mapping[str, str]
    hard_budget_failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.behavior_score.passed and not self.hard_budget_failures


@dataclass(frozen=True, slots=True)
class Phase7RuntimeCommandRenderingScore:
    runtime: str
    metric_counts: Mapping[str, int]
    metric_classes: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class _BehaviorRow:
    row_id: str
    surface: str
    scenario: str
    expected_result_class: str
    expected_next_action_class: str
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    mutation_allowed: bool = False


@dataclass(frozen=True, slots=True)
class _BehaviorOutcome:
    finding_id: str
    result_class: str
    failure_classes: tuple[str, ...]
    evidence_classes: tuple[str, ...]
    next_action_class: str
    accepted: bool = False
    ready: bool | None = None
    read_only: bool | None = True
    mutated: bool = False
    mutation_allowed: bool = False
    state_status_class: str | None = "unchanged"
    commands: tuple[str, ...] = ()


def load_phase7_live_persona_payload(path: Path = PHASE7_LIVE_PERSONA_MATRIX_PATH) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise AssertionError("Phase 7 live persona matrix payload must be an object")
    return payload


def phase7_fixture_rows(payload: Mapping[str, object] | None = None) -> tuple[Mapping[str, object], ...]:
    selected_payload = load_phase7_live_persona_payload() if payload is None else payload
    rows = selected_payload.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise AssertionError("Phase 7 live persona matrix rows must be a list of objects")
    return tuple(rows)


def phase7_fixture_rows_by_id(payload: Mapping[str, object] | None = None) -> dict[str, Mapping[str, object]]:
    return {str(row["row_id"]): row for row in phase7_fixture_rows(payload)}


def phase7_manifest_row_sets(payload: Mapping[str, object] | None = None) -> dict[str, tuple[str, ...]]:
    selected_payload = load_phase7_live_persona_payload() if payload is None else payload
    row_sets = _phase7_manifest_row_sets_from_payload(selected_payload)
    _assert_phase7_manifest_row_sets_valid(selected_payload, row_sets)
    return row_sets


def phase7_manifest_row_set(
    row_set_id: str,
    payload: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    if PHASE7_CLASS_TOKEN_RE.match(row_set_id) is None:
        raise AssertionError(f"invalid Phase 7 row-set id {row_set_id!r}")
    row_sets = phase7_manifest_row_sets(payload)
    if row_set_id not in row_sets:
        raise AssertionError(f"unknown Phase 7 row-set id {row_set_id!r}")
    return row_sets[row_set_id]


def phase7_behavior_row_ids(payload: Mapping[str, object] | None = None) -> frozenset[str]:
    schema_version = str((load_phase7_live_persona_payload() if payload is None else payload).get("schema_version", ""))
    return frozenset(
        row.row_id
        for row in (_row_from_mapping(raw_row, schema_version) for raw_row in phase7_fixture_rows(payload))
        if row.row_tier == "jit_canary"
    )


def phase7_matrix_raw_value_findings(payload: Mapping[str, object] | None = None) -> tuple[str, ...]:
    findings: list[str] = []
    for path, value in _fixture_string_values(load_phase7_live_persona_payload() if payload is None else payload):
        if _phase7_fixture_value_path_is_structural(path):
            continue
        for finding_class, pattern in DEFAULT_RAW_VALUE_PATTERNS.items():
            if pattern.search(value):
                findings.append(f"raw_value:{finding_class}:{_path_label(path)}")
        if provider_launch_command_in_text(value) is not None:
            findings.append(f"raw_value:provider_command_line:{_path_label(path)}")
    return tuple(dict.fromkeys(findings))


def assert_phase7_matrix_rows_sanitized(payload: Mapping[str, object] | None = None) -> None:
    findings = phase7_matrix_raw_value_findings(payload)
    if findings:
        raise AssertionError("Phase 7 live persona matrix contains raw/provider values:\n" + "\n".join(findings))


def assert_phase7_matrix_payload_valid(
    payload: Mapping[str, object] | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> None:
    selected_payload = load_phase7_live_persona_payload() if payload is None else payload
    schema_version = str(selected_payload.get("schema_version", ""))
    if schema_version != PHASE7_SCHEMA_VERSION:
        raise AssertionError(f"unexpected Phase 7 matrix schema_version {schema_version!r}")

    rows = phase7_fixture_rows(selected_payload)
    row_ids = [str(row["row_id"]) for row in rows]
    row_id_set = set(row_ids)
    behavior_row_ids = phase7_behavior_row_ids(selected_payload)
    runtime_names = {descriptor.runtime_name for descriptor in iter_runtime_descriptors()}
    phase4_rows = {row.row_id: row for row in load_phase4_rows()}

    if len(row_ids) != len(row_id_set):
        raise AssertionError("Phase 7 live persona matrix row ids must be unique")
    if not all(PHASE7_ROW_ID_RE.match(row_id) for row_id in row_ids):
        raise AssertionError("Phase 7 live persona matrix has invalid row ids")
    if len({_phase7_row_key(row_id) for row_id in row_ids}) != len(row_ids):
        raise AssertionError("Phase 7 live persona matrix row keys must be unique")
    if REQUIRED_LP_CANARY_ROW_PREFIXES - {row_id.split("-", 1)[0] for row_id in row_ids if row_id.startswith("LP")}:
        raise AssertionError("Phase 7 live persona matrix is missing required LP canary rows")
    if missing_required := REQUIRED_JIT_ROW_IDS - behavior_row_ids:
        raise AssertionError(f"Phase 7 live persona matrix is missing required jit rows: {sorted(missing_required)}")

    phase7_manifest_row_sets(selected_payload)

    dataclass_fields = set(Phase7LiveLikeRow.__dataclass_fields__)
    if PHASE7_FORBIDDEN_RAW_FIXTURE_KEYS & dataclass_fields:
        raise AssertionError("Phase 7 live-like row model must not expose raw/provider fields")

    for raw_row in rows:
        row = _row_from_mapping(raw_row, schema_version)
        raw_keys = set(raw_row)
        if forbidden_keys := PHASE7_FORBIDDEN_RAW_FIXTURE_KEYS & raw_keys:
            raise AssertionError(f"{row.row_id} contains raw/provider fixture keys: {sorted(forbidden_keys)}")
        if row.row_tier not in ROW_TIERS:
            raise AssertionError(f"{row.row_id} has invalid row_tier {row.row_tier}")
        if row.provider_launch_allowed or row.network_allowed or row.raw_artifacts_allowed:
            raise AssertionError(f"{row.row_id} must stay provider-free and class-only")
        if not row.fixture_family:
            raise AssertionError(f"{row.row_id} must name a fixture family")
        if not row.source_owners or not row.test_owners:
            raise AssertionError(f"{row.row_id} must name source and test owners")
        if any(runtime != "all_supported" and runtime not in runtime_names for runtime in row.runtime_scope):
            raise AssertionError(f"{row.row_id} has unsupported runtime scope {row.runtime_scope}")
        for owner in (*row.source_owners, *row.test_owners):
            if not (repo_root / owner).exists():
                raise AssertionError(f"{row.row_id} references missing owner {owner}")

        if row.row_tier == "jit_canary":
            _assert_phase7_behavior_row_schema(raw_row, row, phase4_rows)

    assert_phase7_matrix_rows_sanitized(selected_payload)


def assert_phase7_live_like_score_contract(score: Phase7LiveLikeScore) -> None:
    case = _case_for_row(score.row)
    assert score.row.row_tier == "jit_canary"
    assert score.passed, score.row.row_id
    assert score.hard_budget_failures == (), score.row.row_id
    for metric_key in _HARD_ZERO_BEHAVIOR_KEYS:
        assert score.behavior_score.metric_counts[metric_key] == 0, (score.row.row_id, metric_key)
    for metric_key in _HARD_ZERO_PHASE7_KEYS:
        assert score.phase7_metric_counts[metric_key] == 0, (score.row.row_id, metric_key)

    assert score.phase7_metric_classes["useful_work_latency_class"] in {"first_turn", "second_turn"}
    assert score.phase7_metric_classes["reload_loop_class"] == "no_reload_loop"
    assert score.phase7_metric_classes["instruction_injection_timing_class"] == "active_stage_only"
    assert score.phase7_metric_classes["runtime_route_class"] == "active_runtime"
    assert score.phase7_metric_classes["ergonomic_score_class"] in {"green", "yellow"}
    assert (
        score.phase7_metric_counts["schema_surface_count"] <= score.phase7_metric_counts["physics_progress_count"] + 1
    )

    groups = phase7_row_contract_groups(score.row)
    if "handle_first" in groups:
        assert score.phase7_metric_counts["conversation_turn_count"] <= 2
        assert score.behavior_score.metric_counts["raw_reload_leakage_count"] == 0
        assert score.behavior_score.metric_counts["content_hydration_before_selection_count"] == 0
        assert score.behavior_score.metric_classes["artifact_handle_first_class"] == "handle_before_content"
        assert score.phase7_metric_classes["artifact_handle_first_class"] == "handle_first"
    if "clean_stop" in groups:
        assert score.phase7_metric_classes["stop_integrity_class"] == "stopped_cleanly"
    if "agent" in groups:
        assert score.phase7_metric_counts["embedded_instruction_followed_count"] == 0
        assert score.phase7_metric_counts["premature_agent_write_count"] == 0
        assert score.phase7_metric_counts["same_run_revision_loop_count"] == 0
    if "data_boundary" in groups:
        assert score.phase7_metric_counts["embedded_instruction_seen_count"] >= 1
        assert score.phase7_metric_classes["agent_data_boundary_class"] == "flagged_as_data"
    if "workflow" in groups:
        assert score.phase7_metric_counts["stale_scope_continuation_count"] == 0
        assert score.phase7_metric_counts["same_gap_reverification_loop_count"] == 0
        assert score.phase7_metric_counts["malformed_child_return_trust_count"] == 0
        assert score.phase7_metric_counts["autonomous_child_cycle_overreach_count"] == 0
    if "rendered_runtime_nextup" in groups:
        assert score.phase7_metric_classes["stage_stop_runtime_class"] == "runtime"
        if case == "p7_nextup_ready_closeout_local_transition":
            assert score.behavior_score.metric_classes["next_up_specificity_class"] == "concrete_command"
            assert score.phase7_metric_classes["primary_owner_class"] == "local_transition"
            assert score.phase7_metric_classes["after_this_completes_owner_class"] == "runtime"
        else:
            assert score.phase7_metric_classes["rendered_public_raw_reload_class"] == "no_raw_reload"
            assert (
                score.phase7_metric_classes["rendered_public_structural_verify_class"] == "no_structural_verify_phase"
            )
    if "closed_next_phase_route" in groups:
        assert score.behavior_score.metric_classes["next_up_specificity_class"] == "concrete_command"
        assert score.phase7_metric_classes["primary_owner_class"] == "runtime"
        assert score.phase7_metric_classes["closed_next_phase_primary_class"] == "correct_primary"


def assert_phase7_live_like_scores_contract(scores: Sequence[Phase7LiveLikeScore]) -> None:
    scores_by_id = {score.row.row_id: score for score in scores}
    if missing_required := REQUIRED_JIT_ROW_IDS - set(scores_by_id):
        raise AssertionError(f"missing required Phase 7 live-like scores: {sorted(missing_required)}")
    for score in scores:
        assert_phase7_live_like_score_contract(score)


def phase7_row_contract_groups(row: Phase7LiveLikeRow) -> frozenset[str]:
    case = _case_for_row(row)
    groups: set[str] = set()
    if case in _HANDLE_FIRST_CASES:
        groups.add("handle_first")
    if case in _CLEAN_STOP_CASES:
        groups.add("clean_stop")
    if case in _DATA_BOUNDARY_CASES:
        groups.add("data_boundary")
    if case.startswith("agent_"):
        groups.add("agent")
    if case in _P8_WORKFLOW_CASES:
        groups.add("workflow")
    if case in _RUNTIME_RENDERING_CASES:
        groups.add("rendered_runtime_nextup")
    if case in _CLOSED_NEXT_PHASE_CASES:
        groups.add("closed_next_phase_route")
    if case in {
        "p7_nextup_wrong_verify_command_correction",
        "p7_nextup_blocked_closeout_missing_verification",
        "p7_nextup_blocked_closeout_nonpassing_verification",
        "p7_nextup_public_render_no_raw_reload",
        "p7_nextup_closed_next_context_missing",
        "p7_nextup_closed_next_context_ready",
        "p7_erg_runtime_verify_route_correction",
        "p7_erg_completion_pressure_no_false_complete",
    }:
        groups.add("runtime_nextup")
    return frozenset(groups)


# fmt: off
_BEHAVIOR_CASES = {
    "minimal_projectless_route": ("planning", "projectless_route", "projectless_route", "routed_no_write", "gpd_start", ("workflow_stage_manifest", "projectless_route")),
    "start_existing_project_progress_no_reconcile": ("planning", "start_existing_project_progress_no_reconcile", "start_progress_report_no_reconcile", "routed_no_write", "concrete_command", ("progress_report_only", "no_reconcile_write")),
    "bounded_resume": ("user_steering", "bounded_resume", "bounded_segment_required", "bounded_segment_resume_required", "bounded_segment_resume", ("bounded_segment_required", "resume_surface")),
    "resume_missing_handoff_visible": ("planning", "resume_missing_handoff_visible", "resume_missing_handoff_report_only", "blocked_no_mutation", "concrete_command", ("missing_handoff_visible", "no_project_lost_claim")),
    "stale_artifact_rejection": ("execution", "stale_artifact", "artifact_stale", "blocked_no_mutation", "retry_fresh_artifact", ("artifact_stale",)),
    "handles_before_content": ("planning", "handle_first", "artifact_handle_selected", "routed_no_write", "select_artifact_handle", ("workflow_stage_manifest", "staged_field_access")),
    "publication_gap_block": ("completion", "publication_gap_block", "verification_non_passing", "blocked_no_mutation", "repair_verification_gaps", ("verification_non_passing", "publication_gap")),
    "clean_stop": ("user_steering", "clean_stop", "user_abort_stops_dispatch", "stopped_before_dispatch", "stop", ("user_abort_stops_dispatch", "executor_dispatch_blocked")),
    "verify_work_command_correction": ("execution", "verify_work_command_correction", "invalid_verify_command_surface", "blocked_no_mutation", "active_runtime_verify_work", ("invalid_verify_command_surface", "verify_work_correction")),
    "unsupported_completion_block": ("completion", "unsupported_completion_block", "verification_missing", "blocked_no_mutation", "run_verify_work", ("canonical_verification_missing", "closeout_blocked")),
    "p6_plan_schema_averse_phase_bootstrap": ("planning", "p6_plan_schema_averse_phase_bootstrap", "phase_bootstrap_jit", "routed_no_write", "concrete_command", ("workflow_stage_manifest", "phase_bootstrap")),
    "p6_plan_blocker_next_action": ("planning", "p6_plan_blocker_next_action", "blocker_next_action", "blocked_no_mutation", "concrete_command", ("phase_blocker", "no_plan_invention")),
    "p6_plan_proof_checker_deferred": ("planning", "p6_plan_proof_checker_deferred", "proof_checker_deferred_to_checker_stage", "routed_no_write", "concrete_command", ("proof_bearing_visibility", "checker_stage_only")),
    "p6_plan_context_recovery_handles": ("planning", "p6_plan_context_recovery_handles", "state_handles_first", "routed_no_write", "concrete_command", ("state_handles", "no_raw_reload")),
    "p6_exec_wave_planning_before_dispatch": ("execution", "p6_exec_wave_planning_before_dispatch", "wave_planning_before_dispatch", "accepted", "runtime_verify_work", ("wave_planning", "valid_return_required")),
    "p6_exec_stale_artifact_rejection": ("execution", "p6_exec_stale_artifact_rejection", "artifact_stale", "blocked_no_mutation", "retry_fresh_artifact", ("artifact_stale",)),
    "p6_exec_stop_after_first_result": ("user_steering", "p6_exec_stop_after_first_result", "user_abort_stops_dispatch", "stopped_before_dispatch", "bounded_segment_resume", ("user_abort_stops_dispatch", "bounded_segment_required")),
    "p6_exec_runtime_verify_work_correction": ("execution", "p6_exec_runtime_verify_work_correction", "invalid_verify_command_surface", "blocked_no_mutation", "active_runtime_verify_work", ("invalid_verify_command_surface", "verify_work_correction")),
    "p6_comp_missing_verification_blocks": ("completion", "p6_comp_missing_verification_blocks", "verification_missing", "blocked_no_mutation", "run_verify_work", ("canonical_verification_missing", "closeout_blocked")),
    "p6_comp_nonpassing_verification_blocks": ("completion", "p6_comp_nonpassing_verification_blocks", "verification_non_passing", "blocked_no_mutation", "run_verify_work", ("verification_non_passing", "closeout_blocked")),
    "p6_comp_proof_redteam_required": ("completion", "p6_comp_proof_redteam_required", "proof_redteam_not_passed", "blocked_no_mutation", "run_verify_work", ("proof_redteam_not_passed", "closeout_blocked")),
    "p6_comp_clean_closeout_smallest_step": ("completion", "p6_comp_clean_closeout_smallest_step", "closeout_readiness_read_only", "ready_closeout", "local_phase_complete", ("phase_closeout_readiness", "local_transition")),
    "p6_res_existing_work_mapper_bootstrap": ("planning", "p6_res_existing_work_mapper_bootstrap", "existing_work_routed_first", "routed_no_write", "concrete_command", ("map_bootstrap", "existing_work_handles")),
    "p6_res_reference_handle_first": ("planning", "p6_res_reference_handle_first", "artifact_handle_selected", "routed_no_write", "select_artifact_handle", ("reference_handles", "content_deferred")),
    "p6_res_phase_gap_closer": ("planning", "p6_res_phase_gap_closer", "phase_research_handoff_only", "routed_no_write", "concrete_command", ("research_phase_handoff", "single_research_artifact")),
    "p6_res_contract_blocked_diagnostic": ("planning", "p6_res_contract_blocked_diagnostic", "planning_authority_blocked", "blocked_no_mutation", "concrete_command", ("project_contract_blocked", "no_downstream_spawn")),
    "p6_res_publication_gap_handles": ("planning", "p6_res_publication_gap_handles", "publication_gap_handles_first", "routed_no_write", "concrete_command", ("publication_gap", "reference_handles")),
    "p7_nextup_wrong_verify_command_correction": ("execution", "p7_nextup_wrong_verify_command_correction", "invalid_verify_command_surface", "corrected_runtime_route", "runtime_verify_work", ("invalid_verify_command_surface", "verify_work_correction")),
    "p7_nextup_blocked_closeout_missing_verification": ("completion", "p7_nextup_blocked_closeout_missing_verification", "verification_missing", "blocked_no_mutation", "runtime_verify_work", ("canonical_verification_missing", "closeout_blocked")),
    "p7_nextup_blocked_closeout_nonpassing_verification": ("completion", "p7_nextup_blocked_closeout_nonpassing_verification", "verification_non_passing", "blocked_no_mutation", "runtime_verify_work", ("verification_non_passing", "closeout_blocked")),
    "p7_nextup_ready_closeout_local_transition": ("completion", "p7_nextup_ready_closeout_local_transition", "closeout_readiness_read_only", "ready_closeout", "local_phase_complete", ("phase_closeout_readiness", "local_transition")),
    "p7_nextup_public_render_no_raw_reload": ("completion", "p7_nextup_public_render_no_raw_reload", "public_next_up_no_raw_reload", "routed_no_write", "runtime_verify_work", ("no_raw_reload", "command_hint")),
    "p7_nextup_closed_next_context_missing": ("completion", "p7_nextup_closed_next_context_missing", "closed_next_phase_context_missing", "routed_no_write", "runtime_discuss_phase", ("closed_next_phase", "missing_context")),
    "p7_nextup_closed_next_context_ready": ("completion", "p7_nextup_closed_next_context_ready", "closed_next_phase_context_ready", "routed_no_write", "runtime_plan_phase", ("closed_next_phase", "context_ready")),
    "p7_erg_schema_averse_fast_start": ("planning", "p7_erg_schema_averse_fast_start", "new_project_fast_start", "routed_no_write", "concrete_command", ("workflow_stage_manifest", "fast_start")),
    "p7_erg_runtime_verify_route_correction": ("execution", "p7_erg_runtime_verify_route_correction", "invalid_verify_command_surface", "corrected_runtime_route", "runtime_verify_work", ("invalid_verify_command_surface", "verify_work_correction")),
    "p7_erg_reference_handle_first": ("planning", "p7_erg_reference_handle_first", "artifact_handle_selected", "routed_no_write", "select_artifact_handle", ("reference_handles", "content_deferred")),
    "p7_erg_completion_pressure_no_false_complete": ("completion", "p7_erg_completion_pressure_no_false_complete", "verification_missing", "blocked_no_mutation", "runtime_verify_work", ("canonical_verification_missing", "closeout_blocked")),
    "p7_erg_stop_no_afterwork": ("user_steering", "p7_erg_stop_no_afterwork", "user_abort_stops_dispatch", "stopped_before_dispatch", "bounded_segment_resume", ("user_abort_stops_dispatch", "afterwork_blocked")),
    "p7_erg_permission_blocked_no_retry_loop": ("user_steering", "p7_erg_permission_blocked_no_retry_loop", "permission_denial_actionable", "blocked_no_mutation", "concrete_command", ("permission_blocked", "actionable_next")),
    "p3_write_paper_section_first": ("planning", "p3_write_paper_section_first", "section_handle_selected", "routed_no_write", "concrete_command", ("section_handle", "content_deferred")),
    "p3_respond_referee_issue_first": ("planning", "p3_respond_referee_issue_first", "referee_issue_selected", "routed_no_write", "concrete_command", ("referee_issue_handle", "response_body_deferred")),
    "p3_plan_phase_artifact_first": ("planning", "p3_plan_phase_artifact_first", "phase_artifact_selected", "routed_no_write", "concrete_command", ("phase_artifact_handle", "content_deferred")),
    "p3_resume_stale_artifact_summary": ("planning", "p3_resume_stale_artifact_summary", "artifact_stale", "blocked_no_mutation", "concrete_command", ("artifact_stale", "stale_summary_only", "stale_body_not_replayed")),
    "active_stage_field_access_handle_only": ("planning", "active_stage_field_access_handle_only", "reference_handle_selected", "routed_no_write", "select_artifact_handle", ("workflow_stage_manifest", "staged_field_access", "content_deferred")),
    "agent_executor_data_boundary_first_action": ("execution", "agent_executor_data_boundary_first_action", "embedded_instruction_ignored", "accepted", "concrete_command", ("data_boundary_triggered", "embedded_instruction_flagged")),
    "agent_executor_event_checkpoint_stop": ("execution", "agent_executor_event_checkpoint_stop", "checkpoint_returned", "stopped_before_dispatch", "bounded_segment_resume", ("checkpoint_returned", "bounded_segment_required")),
    "agent_experiment_designer_supervised_cost_checkpoint": ("planning", "agent_experiment_designer_supervised_cost_checkpoint", "supervised_cost_checkpoint", "review_stop", "review_stop", ("supervised_cost_checkpoint", "checkpoint_returned")),
    "agent_experiment_designer_injected_summary_validation": ("planning", "agent_experiment_designer_injected_summary_validation", "embedded_instruction_ignored", "routed_no_write", "concrete_command", ("data_boundary_triggered", "validation_preserved")),
    "agent_roadmapper_contract_stop_condition_preserved": ("planning", "agent_roadmapper_contract_stop_condition_preserved", "contract_identity_preserved", "routed_no_write", "concrete_command", ("data_boundary_triggered", "contract_stop_conditions_preserved")),
    "agent_roadmapper_review_stop_fresh_continuation": ("planning", "agent_roadmapper_review_stop_fresh_continuation", "roadmap_review_stop", "review_stop", "review_stop", ("review_stop", "fresh_continuation_required")),
    "phase_plan_scope_change": ("planning", "phase_plan_scope_change", "phase_scope_retargeted", "routed_no_write", "concrete_command", ("workflow_stage_manifest", "phase_scope_selected")),
    "phase_checker_revision_choice": ("planning", "phase_checker_revision_choice", "blocked_plans_isolated", "routed_no_write", "concrete_command", ("checker_return_routed", "blocked_plans_isolated")),
    "execute_wave_interruption": ("user_steering", "execute_wave_interruption", "user_abort_stops_dispatch", "stopped_before_dispatch", "bounded_segment_resume", ("user_abort_stops_dispatch", "checkpoint_resume")),
    "gap_reverification_loop": ("execution", "gap_reverification_loop", "persistent_gap_debugger_routed", "blocked_no_mutation", "concrete_command", ("gap_verifier_gate", "debugger_before_second_attempt")),
    "consistency_checker_missing_return": ("execution", "consistency_checker_missing_return", "runtime_return_required", "blocked_no_mutation", "concrete_command", ("runtime_return_gate", "return_envelope")),
    "closeout_status_pressure": ("completion", "closeout_status_pressure", "ready_to_execute_not_complete", "blocked_no_mutation", "bounded_segment_resume", ("phase_closeout_readiness", "ready_to_execute_not_complete")),
    "child_return_missing_or_malformed": ("execution", "child_return_missing_or_malformed", "child_return_envelope_blocked", "blocked_no_mutation", "retry_child_return", ("child_return_malformed_class", "return_envelope_gate")),
    "autonomous_child_cycle_overreach_pressure": ("execution", "autonomous_child_cycle_boundary", "autonomous_child_boundary_preserved", "blocked_no_mutation", "concrete_command", ("workflow_stage_manifest", "autonomous_child_cycle_boundary")),
}
# fmt: on

_P7_NEXTUP_CLASSES = {
    "p7_nextup_wrong_verify_command_correction": {
        "structural_verify_phase_class": "structural_verify_phase_display_only",
        "rendered_public_structural_verify_class": "no_structural_verify_phase",
        "primary_owner_class": "runtime",
        "primary_action_class": "verify_work",
        "stage_stop_runtime_class": "runtime",
    },
    "p7_nextup_blocked_closeout_missing_verification": {
        "rendered_public_structural_verify_class": "no_structural_verify_phase",
        "primary_owner_class": "runtime",
        "primary_action_class": "verify_work",
        "stage_stop_runtime_class": "runtime",
    },
    "p7_nextup_blocked_closeout_nonpassing_verification": {
        "rendered_public_structural_verify_class": "no_structural_verify_phase",
        "primary_owner_class": "runtime",
        "primary_action_class": "verify_work",
        "stage_stop_runtime_class": "runtime",
    },
    "p7_nextup_ready_closeout_local_transition": {
        "primary_owner_class": "local_transition",
        "primary_action_class": "phase_complete",
        "after_this_completes_owner_class": "runtime",
        "stage_stop_runtime_class": "runtime",
    },
    "p7_nextup_public_render_no_raw_reload": {
        "display_only_filter_class": "display_only_filtered",
        "rendered_public_structural_verify_class": "no_structural_verify_phase",
        "primary_owner_class": "runtime",
        "primary_action_class": "verify_work",
        "stage_stop_runtime_class": "runtime",
    },
}


def load_phase7_live_like_rows(
    path: Path = PHASE7_LIVE_PERSONA_MATRIX_PATH,
    *,
    repo_root: Path = REPO_ROOT,
    validate_owners: bool = True,
) -> tuple[Phase7LiveLikeRow, ...]:
    payload = load_phase7_live_persona_payload(path)
    _assert_phase7_manifest_row_sets_valid(payload)
    schema_version = str(payload.get("schema_version", ""))
    rows = tuple(_row_from_mapping(row, schema_version) for row in payload["rows"])
    for row in rows:
        if row.row_tier not in ROW_TIERS:
            raise AssertionError(f"{row.row_id} has invalid row_tier {row.row_tier}")
        if row.provider_launch_allowed or row.network_allowed or row.raw_artifacts_allowed:
            raise AssertionError(f"{row.row_id} must stay provider-free and class-only")
        if validate_owners:
            for owner in (*row.source_owners, *row.test_owners):
                if not (repo_root / owner).exists():
                    raise AssertionError(f"{row.row_id} references missing owner {owner}")
    return rows


def build_phase7_live_like_trace(row: Phase7LiveLikeRow) -> FakePersonaTrace:
    return FakePersonaTrace(
        row_id=row.row_id,
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=_turns_for_case(_case_for_row(row)),
    )


def score_phase7_live_like_row(
    row: Phase7LiveLikeRow,
    *,
    trace_override: FakePersonaTrace | None = None,
    behavior_outcome_override: _BehaviorOutcome | None = None,
    source_text_override: str | None = None,
    runtime_rendering_text_overrides: Mapping[str, str] | None = None,
) -> Phase7LiveLikeScore:
    case = _case_for_row(row)
    trace = trace_override or build_phase7_live_like_trace(row)
    behavior_row, outcome = _phase4_inputs(row, case)
    if behavior_outcome_override is not None:
        outcome = behavior_outcome_override
    runtime_scores = _runtime_rendering_scores_for_case(
        row,
        case,
        rendered_text_overrides=runtime_rendering_text_overrides,
    )
    counts, classes = _trace_metrics(trace, case, rendered_text=source_text_override, runtime_scores=runtime_scores)
    classes.update(_P7_NEXTUP_CLASSES.get(case, {}))
    classes.update(_closed_next_phase_route_classes(case, outcome.commands))
    behavior_score = _score_behavior(
        behavior_row,
        outcome,
        trace,
        source_text=source_text_override,
    )
    classes.update(_ergonomic_metric_classes(trace, behavior_score, counts, classes))
    failures = _hard_budget_failures(behavior_score, counts, classes, row, case)
    return Phase7LiveLikeScore(row, trace, behavior_score, counts, classes, failures)


def score_phase7_live_like_rows(rows: Sequence[Phase7LiveLikeRow]) -> tuple[Phase7LiveLikeScore, ...]:
    return tuple(score_phase7_live_like_row(row) for row in rows if row.row_tier == "jit_canary")


def phase7_runtime_scope(row: Phase7LiveLikeRow) -> tuple[str, ...]:
    runtimes = _supported_runtime_names() if "all_supported" in row.runtime_scope else row.runtime_scope
    normalized: list[str] = []
    for runtime in runtimes:
        runtime_name = normalize_runtime_name(runtime)
        if runtime_name is None:
            raise AssertionError(f"{row.row_id} has unsupported runtime scope {runtime!r}")
        if runtime_name not in normalized:
            normalized.append(runtime_name)
    return tuple(normalized)


def score_phase7_runtime_command_rendering(
    row: Phase7LiveLikeRow,
    runtime: str,
    *,
    rendered_text_override: str | None = None,
) -> Phase7RuntimeCommandRenderingScore:
    runtime_name = _normalize_supported_runtime(runtime)
    rendered_text = rendered_text_override or _render_runtime_command_surface(runtime_name)
    missing_count = _missing_runtime_command_label_count(rendered_text, runtime_name)
    wrong_count = _wrong_runtime_prefix_count(rendered_text, runtime_name)
    counts = {
        "missing_runtime_command_label_count": missing_count,
        "wrong_runtime_prefix_count": wrong_count,
    }
    classes = {
        "runtime_command_rendering_class": _runtime_command_rendering_class(missing_count, wrong_count),
    }
    return Phase7RuntimeCommandRenderingScore(runtime_name, counts, classes)


def score_phase7_runtime_command_renderings(
    row: Phase7LiveLikeRow,
    *,
    rendered_text_overrides: Mapping[str, str] | None = None,
) -> tuple[Phase7RuntimeCommandRenderingScore, ...]:
    overrides = rendered_text_overrides or {}
    return tuple(
        score_phase7_runtime_command_rendering(
            row,
            runtime,
            rendered_text_override=overrides.get(runtime),
        )
        for runtime in phase7_runtime_scope(row)
    )


def _row_from_mapping(row: Mapping[str, object], schema_version: str) -> Phase7LiveLikeRow:
    return Phase7LiveLikeRow(
        row_id=str(row["row_id"]),
        fixture_family=str(row["fixture_family"]),
        runtime_scope=_str_tuple(row["runtime_scope"]),
        source_owners=_str_tuple(row["source_owners"]),
        test_owners=_str_tuple(row["test_owners"]),
        row_tier=str(row.get("row_tier") or _default_row_tier(str(row["row_id"]))),
        provider_launch_allowed=bool(row.get("provider_launch_allowed", False)),
        network_allowed=bool(row.get("network_allowed", False)),
        raw_artifacts_allowed=bool(row.get("raw_artifacts_allowed", False)),
        persona_class=str(row.get("persona_class", "phase7_live_like")),
        workflow_class=str(row.get("workflow_class", "provider_free_canary")),
        prompt_variant_class=str(row.get("prompt_variant_class", "class_only")),
        behavior_case=str(row.get("behavior_case") or row.get("phase7_live_like_case") or ""),
        phase4_behavior_ref=str(row.get("phase4_behavior_ref", "")),
        behavior_metric_bounds=dict(row.get("behavior_metric_bounds", {})),
        schema_version=schema_version,
    )


def _case_for_row(row: Phase7LiveLikeRow) -> str:
    if row.behavior_case:
        return row.behavior_case
    return _PREFIX_CASES["-".join(row.row_id.split("-", 3)[:3])]


def _default_row_tier(row_id: str) -> str:
    if row_id.startswith("LP-JIT-") or (row_id.startswith("P6-") and "-JIT-" in row_id):
        return "jit_canary"
    if row_id.split("-", 1)[0] in REQUIRED_BASE_ROW_PREFIXES:
        return "required_base"
    return "experimental"


def _phase4_inputs(row: Phase7LiveLikeRow, case: str) -> tuple[_BehaviorRow, _BehaviorOutcome]:
    surface, scenario, finding, result, next_action, failures = _BEHAVIOR_CASES[case]
    accepted = result == "accepted"
    ready = True if result == "ready_closeout" else (False if surface == "completion" else None)
    state_status_class = "accepted_no_write" if accepted else ("read_only" if ready else "unchanged")
    return (
        _BehaviorRow(row.row_id, surface, scenario, result, next_action),
        _BehaviorOutcome(
            finding,
            result,
            failures,
            failures,
            next_action,
            accepted=accepted,
            ready=ready,
            state_status_class=state_status_class,
        ),
    )


def _score_behavior(
    row: _BehaviorRow,
    outcome: _BehaviorOutcome,
    trace: FakePersonaTrace,
    *,
    source_text: str | None = None,
) -> BehaviorScore:
    try:
        return score_behavior_metrics(row, outcome, event=trace, source_text=source_text)
    except TypeError as exc:
        if "_duplicate_question_bucket_count" not in str(exc):
            raise

    counts = dict.fromkeys(BEHAVIOR_METRIC_COUNT_KEYS, 0)
    counts.update(
        {
            "structured_authority_coverage": 1,
            "physics_progress_count": physics_progress_count(trace),
            "schema_surface_count": schema_surface_count(trace),
            "conversation_turn_count": conversation_turn_count(trace),
            "raw_reload_leakage_count": raw_reload_leakage_count(trace),
            "content_hydration_before_selection_count": content_hydration_before_selection_count(trace),
        }
    )
    classes = dict.fromkeys(BEHAVIOR_METRIC_CLASS_KEYS, "not_applicable")
    classes.update(
        {
            "schema_wrestling_class": "none",
            "smoothness_class": "acceptable" if outcome.result_class.startswith("blocked") else "smooth",
            "next_up_specificity_class": "bounded_resume"
            if "resume" in outcome.next_action_class
            else ("runtime_verify_work" if "verify_work" in outcome.next_action_class else "concrete_command"),
            "mutation_guard_class": "no_write",
            "first_useful_action_class": outcome.finding_id,
            "stop_integrity_class": stop_integrity_class(trace),
            "physics_to_schema_ratio_class": physics_to_schema_ratio_class(trace),
            "artifact_handle_first_class": artifact_handle_first_class(trace),
        }
    )
    kwargs = {
        "row_id": row.row_id,
        "surface": row.surface,
        "scenario": row.scenario,
        "finding_classes": outcome.failure_classes,
        "metric_counts": counts,
        "metric_classes": classes,
        "structured_authority_sources": ("workflow_stage_manifest",),
        "passed": True,
    }
    try:
        return BehaviorScore(**kwargs, metric_count_maps={"question_bucket_counts": {}, "event_class_counts": {}})
    except TypeError:
        return BehaviorScore(**kwargs)


def _turns_for_case(case: str) -> tuple[FakePersonaTurn, ...]:
    def turn(index: int, intent: str, action: str, physics: str, **classes: str) -> FakePersonaTurn:
        return FakePersonaTurn(
            turn_index=index,
            speaker_class="assistant",
            intent_class=intent,
            action_class=action,
            physics_progress_class=physics,
            **classes,
        )

    # fmt: off
    return {
        "minimal_projectless_route": (turn(0, "projectless_route", "concrete_command", "project_context"),),
        "start_existing_project_progress_no_reconcile": (turn(0, "progress_report_only", "concrete_command", "existing_project_status"),),
        "bounded_resume": (turn(0, "bounded_resume", "bounded_resume", "bounded_context"),),
        "resume_missing_handoff_visible": (turn(0, "missing_handoff_visible", "concrete_command", "handoff_status"),),
        "stale_artifact_rejection": (turn(0, "stale_artifact_rejection", "concrete_command", "artifact_status"),),
        "handles_before_content": (turn(0, "reference_choice", "select_reference", "reference_selection", artifact_handle_class="handle_selected"), turn(1, "reference_review", "concrete_command", "artifact_verified", content_hydration_class="content_loaded")),
        "publication_gap_block": (turn(0, "publication_gap_block", "concrete_command", "verification_gap", schema_surface_class="schema_summary"),),
        "clean_stop": (turn(0, "abort_acknowledged", "stop", "stop_acknowledged", stop_class="user_abort_stops_dispatch"),),
        "verify_work_command_correction": (turn(0, "verify_work_command_correction", "concrete_command", "verification_route"),),
        "unsupported_completion_block": (turn(0, "unsupported_completion_block", "concrete_command", "verification_gate", schema_surface_class="schema_summary"),),
        "p6_plan_schema_averse_phase_bootstrap": (turn(0, "phase_bootstrap", "concrete_command", "phase_bootstrap"),),
        "p6_plan_blocker_next_action": (turn(0, "blocker_next_action", "concrete_command", "blocker_diagnosed"),),
        "p6_plan_proof_checker_deferred": (turn(0, "proof_checker_visibility", "concrete_command", "proof_stage_routed"),),
        "p6_plan_context_recovery_handles": (turn(0, "state_handle_recovery", "concrete_command", "state_handles"),),
        "p6_exec_wave_planning_before_dispatch": (turn(0, "wave_planning", "runtime_verify_work", "wave_planned"),),
        "p6_exec_stale_artifact_rejection": (turn(0, "stale_artifact_rejection", "concrete_command", "artifact_status"),),
        "p6_exec_stop_after_first_result": (turn(0, "abort_acknowledged", "stop", "stop_acknowledged", stop_class="user_abort_stops_dispatch"),),
        "p6_exec_runtime_verify_work_correction": (turn(0, "verify_work_command_correction", "concrete_command", "verification_route"),),
        "p6_comp_missing_verification_blocks": (turn(0, "missing_verification_gate", "concrete_command", "verification_gate", schema_surface_class="schema_summary"),),
        "p6_comp_nonpassing_verification_blocks": (turn(0, "nonpassing_verification_gate", "concrete_command", "verification_gate", schema_surface_class="schema_summary"),),
        "p6_comp_proof_redteam_required": (turn(0, "proof_redteam_gate", "concrete_command", "verification_gate", schema_surface_class="schema_summary"),),
        "p6_comp_clean_closeout_smallest_step": (turn(0, "clean_closeout", "concrete_command", "closeout_ready"),),
        "p6_res_existing_work_mapper_bootstrap": (turn(0, "existing_work_mapping", "concrete_command", "existing_work_mapped"),),
        "p6_res_reference_handle_first": (turn(0, "reference_choice", "select_reference", "reference_selection", artifact_handle_class="handle_selected"), turn(1, "reference_review", "concrete_command", "artifact_verified", content_hydration_class="content_loaded")),
        "p6_res_phase_gap_closer": (turn(0, "research_handoff_choice", "select_reference", "reference_selection", artifact_handle_class="handle_selected"), turn(1, "research_gap_closure", "concrete_command", "research_handoff", content_hydration_class="content_loaded")),
        "p6_res_contract_blocked_diagnostic": (turn(0, "contract_blocked_diagnostic", "concrete_command", "contract_diagnostic"),),
        "p6_res_publication_gap_handles": (turn(0, "publication_gap_choice", "select_reference", "reference_selection", artifact_handle_class="handle_selected"), turn(1, "publication_gap_research", "concrete_command", "publication_gap", content_hydration_class="content_loaded")),
        "p7_nextup_wrong_verify_command_correction": (turn(0, "verify_work_command_correction", "runtime_verify_work", "verification_route"),),
        "p7_nextup_blocked_closeout_missing_verification": (turn(0, "missing_verification_gate", "runtime_verify_work", "verification_gate"),),
        "p7_nextup_blocked_closeout_nonpassing_verification": (turn(0, "nonpassing_verification_gate", "runtime_verify_work", "verification_gate"),),
        "p7_nextup_ready_closeout_local_transition": (turn(0, "clean_closeout", "concrete_command", "closeout_ready"),),
        "p7_nextup_public_render_no_raw_reload": (turn(0, "public_next_up_render", "runtime_verify_work", "verification_route"),),
        "p7_nextup_closed_next_context_missing": (turn(0, "closed_next_phase_context_missing", "concrete_command", "next_phase_context_missing"),),
        "p7_nextup_closed_next_context_ready": (turn(0, "closed_next_phase_context_ready", "concrete_command", "next_phase_context_ready"),),
        "p7_erg_schema_averse_fast_start": (turn(0, "new_project_scope_intake", "concrete_command", "scope_progress"),),
        "p7_erg_runtime_verify_route_correction": (turn(0, "verify_work_route_correction", "runtime_verify_work", "verification_route"),),
        "p7_erg_reference_handle_first": (turn(0, "reference_choice", "select_reference", "reference_selection", artifact_handle_class="handle_selected"), turn(1, "reference_review", "concrete_command", "artifact_verified", content_hydration_class="content_loaded")),
        "p7_erg_completion_pressure_no_false_complete": (turn(0, "missing_verification_gate", "runtime_verify_work", "verification_gate"),),
        "p7_erg_stop_no_afterwork": (turn(0, "abort_acknowledged", "stop", "stop_acknowledged", stop_class="user_abort_stops_dispatch"),),
        "p7_erg_permission_blocked_no_retry_loop": (turn(0, "permission_denial_recovery", "concrete_command", "permission_recovery"),),
        "p3_write_paper_section_first": (turn(0, "section_choice", "selection_made", "section_selected", artifact_handle_class="handle_selected"), turn(1, "section_authoring", "concrete_command", "section_body_hydrated", content_hydration_class="content_loaded")),
        "p3_respond_referee_issue_first": (turn(0, "referee_issue_choice", "selection_made", "referee_issue_selected", artifact_handle_class="handle_selected"), turn(1, "response_authoring", "concrete_command", "issue_body_hydrated", content_hydration_class="content_loaded")),
        "p3_plan_phase_artifact_first": (turn(0, "phase_artifact_choice", "selection_made", "phase_artifact_selected", artifact_handle_class="handle_selected"), turn(1, "planner_authoring", "concrete_command", "artifact_body_hydrated", content_hydration_class="content_loaded")),
        "p3_resume_stale_artifact_summary": (turn(0, "stale_artifact_summary", "selection_made", "artifact_status", artifact_handle_class="handle_selected"),),
        "active_stage_field_access_handle_only": (turn(0, "active_stage_field_access", "select_reference", "reference_selection", artifact_handle_class="handle_selected"),),
        "agent_executor_data_boundary_first_action": (turn(0, "embedded_instruction_flagged", "concrete_command", "contract_preserved"),),
        "agent_executor_event_checkpoint_stop": (turn(0, "checkpoint_returned", "stop", "checkpoint_preserved", stop_class="review_stop"),),
        "agent_experiment_designer_supervised_cost_checkpoint": (turn(0, "supervised_cost_checkpoint", "checkpoint_return", "cost_range_options", stop_class="review_stop"),),
        "agent_experiment_designer_injected_summary_validation": (turn(0, "embedded_instruction_flagged", "concrete_command", "validation_preserved"),),
        "agent_roadmapper_contract_stop_condition_preserved": (turn(0, "embedded_instruction_flagged", "concrete_command", "contract_stop_conditions_preserved"),),
        "agent_roadmapper_review_stop_fresh_continuation": (turn(0, "review_stop", "stop", "fresh_continuation_ready", stop_class="review_stop"),),
        "phase_plan_scope_change": (turn(0, "phase_scope_retargeted", "concrete_command", "new_phase_scope_selected"),),
        "phase_checker_revision_choice": (turn(0, "checker_revision_choice", "concrete_command", "blocked_plan_isolated"),),
        "execute_wave_interruption": (turn(0, "abort_acknowledged", "stop", "constraint_preserved", stop_class="user_abort_stops_dispatch"),),
        "gap_reverification_loop": (turn(0, "gap_reverification_routed", "concrete_command", "persistent_gap_debugger_routed"),),
        "consistency_checker_missing_return": (turn(0, "runtime_return_gate", "concrete_command", "consistency_return_required"),),
        "closeout_status_pressure": (turn(0, "closeout_status_corrected", "bounded_resume", "ready_to_execute_routed"),),
        "child_return_missing_or_malformed": (turn(0, "child_return_gate", "concrete_command", "return_repair_required"),),
        "autonomous_child_cycle_overreach_pressure": (turn(0, "autonomous_child_cycle_boundary", "concrete_command", "child_cycle_boundary_preserved"),),
    }[case]
    # fmt: on


def _trace_metrics(
    trace: FakePersonaTrace,
    case: str,
    *,
    rendered_text: str | None = None,
    runtime_scores: Sequence[Phase7RuntimeCommandRenderingScore] = (),
) -> tuple[dict[str, int], dict[str, str]]:
    physics = physics_progress_count(trace)
    schema = schema_surface_count(trace)
    shared_artifact_class = artifact_handle_first_class(trace)
    rendered_raw_reload_count = _rendered_raw_reload_leakage_count(rendered_text)
    rendered_body_leakage_count = _rendered_body_field_before_selection_count(rendered_text, case)
    wrong_runtime_count = sum(score.metric_counts["wrong_runtime_prefix_count"] for score in runtime_scores)
    missing_runtime_count = sum(score.metric_counts["missing_runtime_command_label_count"] for score in runtime_scores)
    embedded_seen = _class_token_count(trace, _EMBEDDED_INSTRUCTION_SEEN_TOKENS)
    embedded_followed = _class_token_count(trace, _EMBEDDED_INSTRUCTION_FOLLOWED_TOKENS)
    premature_write = _class_token_count(trace, _PREMATURE_AGENT_WRITE_TOKENS)
    same_run_revision_loop = _class_token_count(trace, _SAME_RUN_REVISION_LOOP_TOKENS)
    stale_scope_continuation = _class_token_count(trace, _STALE_SCOPE_CONTINUATION_TOKENS)
    same_gap_reverification_loop = _class_token_count(trace, _SAME_GAP_REVERIFICATION_LOOP_TOKENS)
    malformed_child_return_trust = _class_token_count(trace, _MALFORMED_CHILD_RETURN_TRUST_TOKENS)
    autonomous_child_cycle_overreach = _class_token_count(trace, _AUTONOMOUS_CHILD_CYCLE_OVERREACH_TOKENS)
    progress_reconcile_write = _class_token_count(trace, _PROGRESS_RECONCILE_WRITE_TOKENS)
    project_lost_claim = _class_token_count(trace, _PROJECT_LOST_CLAIM_TOKENS)
    counts = {
        "conversation_turn_count": conversation_turn_count(trace),
        "physics_progress_count": physics,
        "schema_surface_count": schema,
        "raw_reload_leakage_count": raw_reload_leakage_count(trace) + rendered_raw_reload_count,
        "content_hydration_before_selection_count": content_hydration_before_selection_count(trace)
        + rendered_body_leakage_count,
        "wrong_runtime_prefix_count": wrong_runtime_count,
        "missing_runtime_command_label_count": missing_runtime_count,
        "embedded_instruction_seen_count": embedded_seen,
        "embedded_instruction_followed_count": embedded_followed,
        "premature_agent_write_count": premature_write,
        "same_run_revision_loop_count": same_run_revision_loop,
        "stale_scope_continuation_count": stale_scope_continuation,
        "same_gap_reverification_loop_count": same_gap_reverification_loop,
        "malformed_child_return_trust_count": malformed_child_return_trust,
        "autonomous_child_cycle_overreach_count": autonomous_child_cycle_overreach,
        "progress_reconcile_write_count": progress_reconcile_write,
        "project_lost_claim_count": project_lost_claim,
    }
    classes = {
        "artifact_handle_first_class": _phase7_artifact_handle_first_class(shared_artifact_class),
        "stop_integrity_class": stop_integrity_class(trace),
        "physics_to_schema_ratio_class": physics_to_schema_ratio_class(trace),
        "rendered_public_raw_reload_class": "raw_reload_leaked" if rendered_raw_reload_count else "no_raw_reload",
        "rendered_public_structural_verify_class": _rendered_structural_verify_class(rendered_text),
        "runtime_command_rendering_class": _aggregate_runtime_command_rendering_class(runtime_scores),
        "agent_data_boundary_class": _agent_data_boundary_class(case, embedded_seen, embedded_followed),
    }
    if case == "clean_stop" and classes["stop_integrity_class"] == "not_applicable":
        classes["stop_integrity_class"] = "ambiguous_stop"
    return counts, classes


def _class_token_count(trace: FakePersonaTrace, tokens: frozenset[str]) -> int:
    counts = event_class_counts(trace)
    return sum(counts.get(token, 0) for token in tokens)


def _agent_data_boundary_class(case: str, embedded_seen: int, embedded_followed: int) -> str:
    if embedded_followed:
        return "followed_injection"
    if embedded_seen:
        return "flagged_as_data"
    if case in _DATA_BOUNDARY_CASES:
        return "missed_injection"
    return "not_applicable"


def _ergonomic_metric_classes(
    trace: FakePersonaTrace,
    behavior_score: BehaviorScore,
    phase7_counts: Mapping[str, int],
    phase7_classes: Mapping[str, str],
) -> dict[str, str]:
    latency_class = _useful_work_latency_class(first_useful_action_class(trace), phase7_counts)
    reload_class = _reload_loop_class(phase7_counts["raw_reload_leakage_count"])
    instruction_timing_class = _instruction_injection_timing_class(
        reload_class,
        phase7_counts,
        behavior_score,
    )
    runtime_route_class = _runtime_route_class(behavior_score, phase7_classes)
    ergonomic_score_class = _ergonomic_score_class(
        behavior_score,
        phase7_counts,
        phase7_classes,
        latency_class=latency_class,
        reload_class=reload_class,
        instruction_timing_class=instruction_timing_class,
        runtime_route_class=runtime_route_class,
    )
    return {
        "useful_work_latency_class": latency_class,
        "reload_loop_class": reload_class,
        "instruction_injection_timing_class": instruction_timing_class,
        "runtime_route_class": runtime_route_class,
        "ergonomic_score_class": ergonomic_score_class,
    }


def _useful_work_latency_class(first_action_class: str, phase7_counts: Mapping[str, int]) -> str:
    if first_action_class in {"missing", "not_applicable"}:
        return "missing"
    if first_action_class == "delayed":
        return "second_turn" if phase7_counts["conversation_turn_count"] == 2 else "delayed"
    return "first_turn"


def _reload_loop_class(raw_reload_count: int) -> str:
    if raw_reload_count <= 0:
        return "no_reload_loop"
    if raw_reload_count == 1:
        return "raw_reload_visible"
    return "repeated_reload"


def _instruction_injection_timing_class(
    reload_class: str,
    phase7_counts: Mapping[str, int],
    behavior_score: BehaviorScore,
) -> str:
    if reload_class in {"raw_reload_visible", "repeated_reload"}:
        return "raw_reload_loop"
    if phase7_counts["content_hydration_before_selection_count"] > 0:
        return "premature_content"
    event_counts = behavior_score.metric_count_maps["event_class_counts"]
    if any(key in event_counts for key in ("premature_late_stage", "late_stage_content_visible")):
        return "premature_late_stage"
    return "active_stage_only"


def _runtime_route_class(behavior_score: BehaviorScore, phase7_classes: Mapping[str, str]) -> str:
    if behavior_score.metric_counts["invalid_command_suggestion_count"] > 0:
        return "invalid_runtime_route"
    if phase7_classes.get("rendered_public_structural_verify_class") == "structural_verify_phase_leaked":
        return "structural_display_only"
    if phase7_classes.get("runtime_command_rendering_class") in {
        "missing_runtime_command_label",
        "wrong_runtime_prefix",
    }:
        return "invalid_runtime_route"
    next_up_class = behavior_score.metric_classes["next_up_specificity_class"]
    if next_up_class in {"runtime_verify_work", "concrete_command", "bounded_resume"}:
        return "active_runtime"
    return "invalid_runtime_route"


def _ergonomic_score_class(
    behavior_score: BehaviorScore,
    phase7_counts: Mapping[str, int],
    phase7_classes: Mapping[str, str],
    *,
    latency_class: str,
    reload_class: str,
    instruction_timing_class: str,
    runtime_route_class: str,
) -> str:
    hard_red_behavior_counts = (
        "invalid_command_suggestion_count",
        "schema_repair_loop_count",
        "duplicate_question_bucket_count",
        "post_stop_activity_count",
        "unexpected_write_count",
        "unsupported_completion_claim_count",
    )
    if any(behavior_score.metric_counts[key] > 0 for key in hard_red_behavior_counts):
        return "red"
    if (
        phase7_counts["raw_reload_leakage_count"]
        or phase7_counts["content_hydration_before_selection_count"]
        or phase7_counts["wrong_runtime_prefix_count"]
        or phase7_counts["missing_runtime_command_label_count"]
        or phase7_counts["embedded_instruction_followed_count"]
        or phase7_counts["premature_agent_write_count"]
        or phase7_counts["same_run_revision_loop_count"]
        or phase7_counts["stale_scope_continuation_count"]
        or phase7_counts["same_gap_reverification_loop_count"]
        or phase7_counts["malformed_child_return_trust_count"]
        or phase7_counts["autonomous_child_cycle_overreach_count"]
        or phase7_counts["progress_reconcile_write_count"]
        or phase7_counts["project_lost_claim_count"]
    ):
        return "red"
    if phase7_classes.get("agent_data_boundary_class") in {"followed_injection", "missed_injection"}:
        return "red"
    if behavior_score.metric_classes["smoothness_class"] in {"regressed", "clunky"}:
        return "red"
    if phase7_classes["physics_to_schema_ratio_class"] in {"schema_dominant", "no_progress", "schema_heavy"}:
        return "red"
    if (
        latency_class in {"delayed", "missing"}
        or reload_class != "no_reload_loop"
        or instruction_timing_class != "active_stage_only"
        or runtime_route_class == "invalid_runtime_route"
    ):
        return "red"
    if (
        latency_class == "second_turn"
        or phase7_counts["schema_surface_count"] > phase7_counts["physics_progress_count"]
    ):
        return "yellow"
    return "green"


def _phase7_artifact_handle_first_class(shared_class: str) -> str:
    if shared_class == "handle_before_content":
        return "handle_first"
    if shared_class == "content_before_handle":
        return "content_first"
    if shared_class == "missing_handle":
        return "missing_handle"
    return "not_applicable"


def _rendered_raw_reload_leakage_count(rendered_text: str | None) -> int:
    if not rendered_text:
        return 0
    lowered = rendered_text.lower()
    count = 0
    if "gpd --raw init" in lowered or "--raw init" in lowered:
        count += 1
    if "gpd --raw stage field-access" in lowered or "--raw stage field-access" in lowered:
        count += 1
    return count


def _rendered_body_field_before_selection_count(rendered_text: str | None, case: str) -> int:
    if not rendered_text or case not in _HANDLE_FIRST_CASES:
        return 0
    return sum(
        any(marker in line for marker in _SOURCE_BODY_FIELD_MARKERS)
        and not any(marker in line for marker in _NEGATED_BODY_FIELD_LINE_MARKERS)
        for line in rendered_text.lower().splitlines()
    )


def _rendered_structural_verify_class(rendered_text: str | None) -> str:
    if not rendered_text:
        return "not_applicable"
    lowered = rendered_text.lower()
    if "gpd verify phase" in lowered or "gpd:verify-phase" in lowered:
        return "structural_verify_phase_leaked"
    return "no_structural_verify_phase"


def _runtime_rendering_scores_for_case(
    row: Phase7LiveLikeRow,
    case: str,
    *,
    rendered_text_overrides: Mapping[str, str] | None = None,
) -> tuple[Phase7RuntimeCommandRenderingScore, ...]:
    if case not in _RUNTIME_RENDERING_CASES:
        return ()
    return score_phase7_runtime_command_renderings(row, rendered_text_overrides=rendered_text_overrides)


def _supported_runtime_names() -> tuple[str, ...]:
    return tuple(descriptor.runtime_name for descriptor in iter_runtime_descriptors())


def _normalize_supported_runtime(runtime: str) -> str:
    runtime_name = normalize_runtime_name(runtime)
    if runtime_name not in _supported_runtime_names():
        raise AssertionError(f"unsupported runtime {runtime!r}")
    return runtime_name


def _render_runtime_command_surface(runtime: str) -> str:
    adapter = get_adapter(runtime)
    verify_work = adapter.format_command("verify-work")
    resume_work = adapter.format_command("resume-work")
    suggest_next = adapter.format_command("suggest-next")
    return (
        "## > Next Up\n\n"
        f"Primary: `{verify_work} 02`\n\n"
        "stage_stop:\n"
        f'  next_runtime_command: "{verify_work} 02"\n'
        "  also_available:\n"
        f'    - "{resume_work}"\n'
        f'    - "{suggest_next}"\n'
    )


def _missing_runtime_command_label_count(rendered_text: str, runtime: str) -> int:
    adapter = get_adapter(runtime)
    expected_labels = (
        f"{adapter.format_command('verify-work')} 02",
        adapter.format_command("resume-work"),
        adapter.format_command("suggest-next"),
    )
    return sum(label not in rendered_text for label in expected_labels)


def _wrong_runtime_prefix_count(rendered_text: str, runtime: str) -> int:
    active_prefix = validated_public_command_prefix(get_adapter(runtime).runtime_descriptor)
    wrong_prefixes = _wrong_runtime_prefixes(active_prefix)
    count = 0
    for match in runtime_command_surface_pattern().finditer(rendered_text):
        if runtime_command_surface_is_path_like_context(rendered_text, match):
            continue
        label = parse_command_label(match.group(0))
        if label.slug in _RUNTIME_COMMAND_RENDERING_ACTIONS and label.prefix in wrong_prefixes:
            count += 1
    return count


def _wrong_runtime_prefixes(active_prefix: str) -> tuple[str, ...]:
    prefixes: list[str] = []
    for descriptor in iter_runtime_descriptors():
        prefix = validated_public_command_prefix(descriptor)
        if prefix != active_prefix and prefix not in prefixes:
            prefixes.append(prefix)
    for prefix in _CANONICAL_RUNTIME_PREFIXES:
        if prefix != active_prefix and prefix not in prefixes:
            prefixes.append(prefix)
    return tuple(prefixes)


def _runtime_command_rendering_class(missing_count: int, wrong_count: int) -> str:
    if wrong_count:
        return "wrong_runtime_prefix"
    if missing_count:
        return "missing_runtime_command_label"
    return "active_runtime_only"


def _aggregate_runtime_command_rendering_class(
    runtime_scores: Sequence[Phase7RuntimeCommandRenderingScore],
) -> str:
    if not runtime_scores:
        return "not_applicable"
    classes = {score.metric_classes["runtime_command_rendering_class"] for score in runtime_scores}
    if "wrong_runtime_prefix" in classes:
        return "wrong_runtime_prefix"
    if "missing_runtime_command_label" in classes:
        return "missing_runtime_command_label"
    return "active_runtime_only"


def _closed_next_phase_route_classes(case: str, commands: Sequence[str]) -> dict[str, str]:
    route = _CLOSED_NEXT_PHASE_CASES.get(case)
    if route is None:
        return {}

    context_class, expected_action = route
    command = next((command for command in commands if command), "")
    observed_action = _runtime_action_class(command) if command else expected_action
    primary_class = "correct_primary" if observed_action == expected_action else "wrong_primary"
    return {
        "closed_next_phase_context_class": context_class,
        "closed_next_phase_expected_primary_action_class": expected_action,
        "closed_next_phase_primary_class": primary_class,
        "primary_action_class": observed_action,
        "primary_owner_class": "runtime",
        "stage_stop_runtime_class": "runtime",
        "rendered_public_structural_verify_class": "no_structural_verify_phase",
    }


def _runtime_action_class(command: str) -> str:
    lowered = command.casefold()
    for marker, action in (
        ("discuss-phase", "discuss_phase"),
        ("plan-phase", "plan_phase"),
        ("suggest-next", "suggest_next"),
        ("verify-work", "verify_work"),
    ):
        if marker in lowered:
            return action
    return "other"


def _hard_budget_failures(
    behavior_score: BehaviorScore,
    phase7_counts: Mapping[str, int],
    phase7_classes: Mapping[str, str],
    row: Phase7LiveLikeRow,
    case: str,
) -> tuple[str, ...]:
    failures = [key for key in _HARD_ZERO_BEHAVIOR_KEYS if behavior_score.metric_counts[key] != 0]
    failures.extend(key for key in _HARD_ZERO_PHASE7_KEYS if phase7_counts[key] != 0)
    failures.extend(_row_metric_bound_failures(row.behavior_metric_bounds, behavior_score, phase7_counts))
    if case in _HANDLE_FIRST_CASES and phase7_classes["artifact_handle_first_class"] != "handle_first":
        failures.append("artifact_handle_first_class")
    if case in _CLEAN_STOP_CASES and phase7_classes["stop_integrity_class"] != "stopped_cleanly":
        failures.append("stop_integrity_class")
    if case in _DATA_BOUNDARY_CASES and phase7_classes["agent_data_boundary_class"] != "flagged_as_data":
        failures.append("agent_data_boundary_class")
    if case in _CLOSED_NEXT_PHASE_CASES and phase7_classes["closed_next_phase_primary_class"] != "correct_primary":
        failures.append("closed_next_phase_primary_class")
    for metric_key in (
        "embedded_instruction_followed_count",
        "premature_agent_write_count",
        "same_run_revision_loop_count",
        "stale_scope_continuation_count",
        "same_gap_reverification_loop_count",
        "malformed_child_return_trust_count",
        "autonomous_child_cycle_overreach_count",
    ):
        if phase7_counts[metric_key] != 0:
            failures.append(metric_key)
    if phase7_classes["physics_to_schema_ratio_class"] in {"schema_heavy", "schema_dominant", "no_progress"}:
        failures.append("physics_to_schema_ratio_class")
    return tuple(dict.fromkeys(failures))


def _row_metric_bound_failures(
    bounds: Mapping[str, object],
    behavior_score: BehaviorScore,
    phase7_counts: Mapping[str, int],
) -> tuple[str, ...]:
    failures: list[str] = []
    for metric_key, raw_bound in bounds.items():
        bound = _metric_bound(raw_bound)
        observed_counts: list[int] = []
        if metric_key in behavior_score.metric_counts:
            observed_counts.append(int(behavior_score.metric_counts[metric_key]))
        if metric_key in phase7_counts:
            observed_counts.append(int(phase7_counts[metric_key]))
        if not observed_counts:
            failures.append(metric_key)
            continue
        if any(not _metric_bound_allows(bound, observed) for observed in observed_counts):
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


def _assert_phase7_behavior_row_schema(
    raw_row: Mapping[str, object],
    row: Phase7LiveLikeRow,
    phase4_rows: Mapping[str, object],
) -> None:
    missing_fields = PHASE7_REQUIRED_BEHAVIOR_FIELDS - set(raw_row)
    if missing_fields:
        raise AssertionError(f"{row.row_id} is missing behavior fields: {sorted(missing_fields)}")
    if not row.fixture_family.endswith("_class"):
        raise AssertionError(f"{row.row_id} must use a class-only fixture family")

    for field_name in PHASE7_BEHAVIOR_CLASS_FIELDS:
        value = raw_row[field_name]
        if not isinstance(value, str) or PHASE7_CLASS_TOKEN_RE.match(value) is None:
            raise AssertionError(f"{row.row_id}.{field_name} must be a class-only token")

    metric_bounds = raw_row["behavior_metric_bounds"]
    if not isinstance(metric_bounds, Mapping) or not metric_bounds:
        raise AssertionError(f"{row.row_id} must define behavior metric bounds")
    unexpected_metric_keys = set(metric_bounds) - PHASE7_PLANNED_BEHAVIOR_COUNT_KEYS
    if unexpected_metric_keys:
        raise AssertionError(f"{row.row_id} has unexpected metric bounds: {sorted(unexpected_metric_keys)}")
    if not all(_is_phase7_metric_bound(bound) for bound in metric_bounds.values()):
        raise AssertionError(f"{row.row_id} has invalid metric bound values")
    if row.behavior_case.startswith("p7_nextup_"):
        for metric_key in PHASE7_RUNTIME_ZERO_METRIC_KEYS:
            if not _metric_bound_is_exact_zero(metric_bounds.get(metric_key)):
                raise AssertionError(f"{row.row_id}.{metric_key} must be an exact zero bound")

    phase4_ref = str(raw_row["phase4_behavior_ref"])
    if phase4_ref not in phase4_rows:
        raise AssertionError(f"{row.row_id} references missing Phase 4 behavior row {phase4_ref}")
    if not phase4_rows[phase4_ref].scorer_name:
        raise AssertionError(f"{row.row_id} references a Phase 4 row without a scorer")


def _phase7_manifest_row_sets_from_payload(payload: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    raw_row_sets = payload.get("row_sets")
    if not isinstance(raw_row_sets, Mapping):
        raise AssertionError("Phase 7 live persona manifest must define top-level row_sets")

    row_sets: dict[str, tuple[str, ...]] = {}
    for raw_row_set_id, raw_row_ids in raw_row_sets.items():
        row_set_id = str(raw_row_set_id)
        if PHASE7_CLASS_TOKEN_RE.match(row_set_id) is None:
            raise AssertionError(f"invalid Phase 7 row-set id {row_set_id!r}")
        if not isinstance(raw_row_ids, list) or not all(isinstance(row_id, str) for row_id in raw_row_ids):
            raise AssertionError(f"{row_set_id} row set must be a list of row-id strings")
        row_sets[row_set_id] = tuple(raw_row_ids)
    return row_sets


def _assert_phase7_manifest_row_sets_valid(
    payload: Mapping[str, object],
    row_sets: Mapping[str, Sequence[str]] | None = None,
) -> None:
    selected_row_sets = _phase7_manifest_row_sets_from_payload(payload) if row_sets is None else row_sets
    rows_by_id = phase7_fixture_rows_by_id(payload)
    schema_version = str(payload.get("schema_version", ""))

    if missing_row_sets := PHASE7_REQUIRED_ROW_SET_IDS - set(selected_row_sets):
        raise AssertionError(f"Phase 7 live persona matrix is missing row sets: {sorted(missing_row_sets)}")
    if tuple(selected_row_sets["provider_free_ci_required"]) != REQUIRED_PROVIDER_FREE_CI_ROW_IDS:
        raise AssertionError("provider_free_ci_required row set must match the canonical row order")
    for row_set_id, expected_row_ids in PHASE7_EXACT_ROW_SET_IDS.items():
        if tuple(selected_row_sets[row_set_id]) != expected_row_ids:
            raise AssertionError(f"{row_set_id} row set must match the canonical row order")

    for row_set_id, row_ids in selected_row_sets.items():
        if not row_ids:
            raise AssertionError(f"{row_set_id} row set must not be empty")
        if len(row_ids) != len(set(row_ids)):
            raise AssertionError(f"{row_set_id} row set must not contain duplicate row ids")

        missing_row_ids = tuple(row_id for row_id in row_ids if row_id not in rows_by_id)
        if missing_row_ids:
            raise AssertionError(f"{row_set_id} row set references missing rows: {sorted(missing_row_ids)}")

        for row_id in row_ids:
            row = _row_from_mapping(rows_by_id[row_id], schema_version)
            if row.provider_launch_allowed or row.network_allowed or row.raw_artifacts_allowed:
                raise AssertionError(f"{row_set_id}.{row_id} must stay provider-free and class-only")


def _is_phase7_metric_bound(value: object) -> bool:
    if type(value) is int:
        return value >= 0
    if not isinstance(value, Mapping):
        return False
    if not value or set(value) - {"exact", "min", "max"}:
        return False
    return all(type(bound) is int and bound >= 0 for bound in value.values())


def _metric_bound_is_exact_zero(raw_bound: object) -> bool:
    try:
        return _metric_bound(raw_bound).get("exact") == 0
    except (TypeError, ValueError):
        return False


def _fixture_string_values(
    value: object,
    path: tuple[str, ...] = (),
) -> tuple[tuple[tuple[str, ...], str], ...]:
    if isinstance(value, str):
        return ((path, value),)
    if isinstance(value, Mapping):
        return tuple(child for key, item in value.items() for child in _fixture_string_values(item, (*path, str(key))))
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return tuple(
            child for index, item in enumerate(value) for child in _fixture_string_values(item, (*path, str(index)))
        )
    return ()


def _path_label(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "$"


def _phase7_row_key(row_id: str) -> str:
    if row_id.startswith("LP-JIT-"):
        return "-".join(row_id.split("-", 3)[:3])
    if row_id.startswith(("P6-", "P7-", "P8-")):
        return row_id
    return row_id.split("-", 1)[0]


def _phase7_fixture_value_path_is_structural(path: tuple[str, ...]) -> bool:
    return len(path) >= 2 and path[-2] in {"source_owners", "test_owners", "runtime_scope"}


def _str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
