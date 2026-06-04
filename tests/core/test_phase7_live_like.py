"""Provider-free Phase 7 live-like adapter tests."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from gpd.adapters import get_adapter
from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.core.context import init_literature_review
from gpd.core.staged_init_assembly import (
    StagedInitAssemblyContext,
    StagedInitProvider,
    assemble_staged_init_payload,
)
from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    WORKFLOW_STAGE_MANIFEST_SUFFIX,
    WorkflowStage,
    WorkflowStageManifest,
    load_workflow_stage_manifest,
)
from tests.helpers import phase7_live_like
from tests.helpers.persona_trace import FakePersonaTrace, FakePersonaTurn
from tests.helpers.phase7_live_like import (
    PHASE7_LIVE_PERSONA_MATRIX_PATH,
    REQUIRED_JIT_ROW_IDS,
    REQUIRED_LP_JIT_ROW_IDS,
    REQUIRED_P6_JIT_ROW_IDS,
    REQUIRED_P7_ERG_JIT_ROW_IDS,
    REQUIRED_P7_NEXTUP_JIT_ROW_IDS,
    REQUIRED_P8_AGENT_JIT_ROW_IDS,
    REQUIRED_P8_WORKFLOW_JIT_ROW_IDS,
    Phase7LiveLikeRow,
    assert_phase7_live_like_score_contract,
    load_phase7_live_like_rows,
    phase7_manifest_row_set,
    score_phase7_live_like_row,
    score_phase7_live_like_rows,
)

REFERENCE_FILE_FIELD = "reference_artifact_files"
REFERENCE_CONTENT_FIELD = "reference_artifacts_content"
P8_AGENT_DATA_BOUNDARY_ROW_IDS = frozenset({"P8-AGENT-JIT-01", "P8-AGENT-JIT-04", "P8-AGENT-JIT-05"})
P8_AGENT_STOP_ROW_IDS = frozenset({"P8-AGENT-JIT-02", "P8-AGENT-JIT-03", "P8-AGENT-JIT-06"})
P8_EXPERIMENTAL_WORKFLOW_ROW_IDS = frozenset({"P8-WF-JIT-09"})
P8_HANDLE_FIRST_WORKFLOW_ROW_IDS = frozenset(f"P8-WF-JIT-{index:02d}" for index in range(7, 11)) | {
    "P8-WF-JIT-13"
}
P8_WORKFLOW_ROW_IDS = REQUIRED_P8_WORKFLOW_JIT_ROW_IDS | P8_EXPERIMENTAL_WORKFLOW_ROW_IDS


def test_phase7_live_like_loader_consumes_tracked_matrix() -> None:
    rows = load_phase7_live_like_rows()
    row_ids = {row.row_id for row in rows}
    jit_row_ids = {row.row_id for row in rows if row.row_tier == "jit_canary"}

    assert rows
    assert {"LP01-START-PROJECTLESS-READONLY", "LP12-GEMINI-POLICY-DENIAL"} <= row_ids
    assert REQUIRED_JIT_ROW_IDS <= jit_row_ids
    assert REQUIRED_LP_JIT_ROW_IDS <= jit_row_ids
    assert REQUIRED_P6_JIT_ROW_IDS <= jit_row_ids
    assert REQUIRED_P7_NEXTUP_JIT_ROW_IDS <= jit_row_ids
    assert REQUIRED_P8_AGENT_JIT_ROW_IDS <= jit_row_ids
    assert REQUIRED_P8_WORKFLOW_JIT_ROW_IDS <= jit_row_ids


def test_phase6_minimal_persona_rows_score_provider_free_classes() -> None:
    required_row_ids = {
        "P6-START-JIT-01",
        "P6-RES-JIT-06",
        "P8-WF-JIT-07",
        "P8-WF-JIT-08",
        "P7-NEXTUP-JIT-05",
    }
    scores = {row_id: score_phase7_live_like_row(_row_by_id(row_id)) for row_id in required_row_ids}

    for score in scores.values():
        assert_phase7_live_like_score_contract(score)

    assert scores["P6-START-JIT-01"].phase7_metric_counts["progress_reconcile_write_count"] == 0
    assert scores["P6-RES-JIT-06"].phase7_metric_counts["project_lost_claim_count"] == 0
    assert scores["P8-WF-JIT-07"].phase7_metric_classes["artifact_handle_first_class"] == "handle_first"
    assert scores["P8-WF-JIT-08"].phase7_metric_classes["artifact_handle_first_class"] == "handle_first"


def test_phase6_first_manual_canary_row_set_scores_provider_free_classes() -> None:
    row_ids = phase7_manifest_row_set("phase6_first_manual_canary")
    scores = score_phase7_live_like_rows(tuple(_row_by_id(row_id) for row_id in row_ids))

    assert tuple(score.row.row_id for score in scores) == row_ids
    assert len(scores) == 13

    for score in scores:
        assert_phase7_live_like_score_contract(score)


def test_lp_jit_04_matrix_targets_real_literature_review_stage_pair() -> None:
    row = _raw_row_by_id("LP-JIT-04")
    bounds = row["behavior_metric_bounds"]

    assert row["fixture_family"] == "jit_reference_handle_first_class"
    assert row["workflow_class"] == "literature_review_handle_then_hydrate"
    assert {
        "src/gpd/core/context.py",
        "src/gpd/core/staged_init_assembly.py",
        "src/gpd/specs/workflows/literature-review-stage-manifest.json",
        "src/gpd/specs/workflows/literature-review/scope-locked.md",
        "src/gpd/specs/workflows/literature-review/review-handoff.md",
    } <= set(row["source_owners"])
    assert "tests/core/test_phase7_live_like.py" in row["test_owners"]

    for metric_key in (
        "invalid_command_suggestion_count",
        "schema_repair_loop_count",
        "duplicate_question_bucket_count",
        "post_stop_activity_count",
        "unexpected_write_count",
        "unsupported_completion_claim_count",
        "raw_reload_leakage_count",
        "content_hydration_before_selection_count",
    ):
        assert bounds[metric_key] == 0
    assert bounds["structured_authority_coverage"] == 1
    assert row["expected_artifact_handle_first_class"] == "handle_first"
    assert row["expected_first_useful_action_class"] == "handle_selection"
    assert row["expected_mutation_guard_class"] == "no_write"


def test_lp_jit_04_literature_review_stage_pair_defers_reference_content() -> None:
    manifest = load_workflow_stage_manifest("literature-review")
    scope_locked = manifest.stage("scope_locked")
    review_handoff = manifest.stage("review_handoff")

    assert REFERENCE_FILE_FIELD in scope_locked.required_init_fields
    assert REFERENCE_CONTENT_FIELD not in scope_locked.required_init_fields
    _assert_handles_before_content(review_handoff.required_init_fields)


def test_reference_content_stages_select_handles_before_content() -> None:
    for manifest_path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")):
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = _load_reference_order_manifest(workflow_id)
        for stage in manifest.stages:
            if REFERENCE_CONTENT_FIELD in stage.required_init_fields:
                _assert_handles_before_content(stage.required_init_fields, label=f"{workflow_id}.{stage.id}")


def test_handle_only_reference_stage_inventory_keeps_content_deferred() -> None:
    handle_only_stages = (
        ("quick", "reference_context"),
        ("literature-review", "scope_locked"),
        ("peer-review", "artifact_discovery"),
        ("peer-review", "panel_stages"),
        ("peer-review", "final_adjudication"),
        ("respond-to-referees", "revision_planning"),
        ("verify-work", "interactive_validation"),
        ("write-paper", "figure_and_section_authoring"),
        ("write-paper", "consistency_and_references"),
        ("write-paper", "publication_review"),
    )
    content_stages = (
        ("literature-review", "review_handoff"),
        ("respond-to-referees", "response_authoring"),
    )

    for workflow_id, stage_id in handle_only_stages:
        stage = _load_reference_order_manifest(workflow_id).stage(stage_id)

        assert REFERENCE_FILE_FIELD in stage.required_init_fields, f"{workflow_id}.{stage_id}"
        assert REFERENCE_CONTENT_FIELD not in stage.required_init_fields, f"{workflow_id}.{stage_id}"

    for workflow_id, stage_id in content_stages:
        stage = _load_reference_order_manifest(workflow_id).stage(stage_id)

        _assert_handles_before_content(stage.required_init_fields, label=f"{workflow_id}.{stage_id}")


def test_staged_init_payload_dispatch_is_lazy_for_handle_only_reference_stage(tmp_path: Path) -> None:
    manifest = _manifest(
        _stage("handle_only", (REFERENCE_FILE_FIELD,)),
        _stage("hydrate", (REFERENCE_FILE_FIELD, REFERENCE_CONTENT_FIELD), order=2),
    )
    calls: list[str] = []

    def build_handles(context: StagedInitAssemblyContext) -> dict[str, object]:
        calls.append(f"handles:{context.stage.id}")
        return {REFERENCE_FILE_FIELD: ["GPD/research-map/REFERENCES.md"]}

    def build_content(context: StagedInitAssemblyContext) -> dict[str, object]:
        if context.stage.id == "handle_only":
            raise AssertionError("reference content provider must not run for handle-only stages")
        calls.append(f"content:{context.stage.id}")
        return {REFERENCE_CONTENT_FIELD: "hydrated reference body"}

    providers = (
        StagedInitProvider("handles", frozenset({REFERENCE_FILE_FIELD}), build_handles),
        StagedInitProvider("content", frozenset({REFERENCE_CONTENT_FIELD}), build_content),
    )

    handle_payload = assemble_staged_init_payload(
        workflow_id="phase7-handle-first",
        stage_id="handle_only",
        cwd=tmp_path,
        base_payload={},
        manifest=manifest,
        providers=providers,
    )
    hydrate_payload = assemble_staged_init_payload(
        workflow_id="phase7-handle-first",
        stage_id="hydrate",
        cwd=tmp_path,
        base_payload={},
        manifest=manifest,
        providers=providers,
    )

    assert calls == ["handles:handle_only", "handles:hydrate", "content:hydrate"]
    assert tuple(handle_payload) == (REFERENCE_FILE_FIELD, "staged_loading")
    assert REFERENCE_CONTENT_FIELD not in handle_payload
    assert tuple(hydrate_payload) == (REFERENCE_FILE_FIELD, REFERENCE_CONTENT_FIELD, "staged_loading")
    assert hydrate_payload[REFERENCE_CONTENT_FIELD] == "hydrated reference body"


def test_literature_review_staged_payload_hydrates_only_after_scope_locked(tmp_path: Path) -> None:
    _setup_literature_review_reference_project(tmp_path)

    scope_locked = init_literature_review(tmp_path, "Curvature flow bounds", stage="scope_locked")
    review_handoff = init_literature_review(tmp_path, "Curvature flow bounds", stage="review_handoff")

    assert REFERENCE_FILE_FIELD in scope_locked
    assert scope_locked[REFERENCE_FILE_FIELD] == ["GPD/research-map/REFERENCES.md"]
    assert REFERENCE_CONTENT_FIELD not in scope_locked
    assert _active_payload_fields(scope_locked) == tuple(scope_locked["staged_loading"]["required_init_fields"])

    assert review_handoff[REFERENCE_FILE_FIELD] == ["GPD/research-map/REFERENCES.md"]
    assert isinstance(review_handoff[REFERENCE_CONTENT_FIELD], str)
    assert review_handoff[REFERENCE_CONTENT_FIELD]
    assert _active_payload_fields(review_handoff) == tuple(review_handoff["staged_loading"]["required_init_fields"])
    _assert_handles_before_content(tuple(review_handoff))


def test_lp_jit_04_uses_shared_handle_before_content_detector() -> None:
    row = _row_by_id("LP-JIT-04")
    score = score_phase7_live_like_row(row)

    assert score.passed
    assert score.hard_budget_failures == ()
    assert score.phase7_metric_counts["raw_reload_leakage_count"] == 0
    assert score.phase7_metric_counts["content_hydration_before_selection_count"] == 0
    assert score.phase7_metric_counts["conversation_turn_count"] == 2
    assert score.behavior_score.metric_counts["raw_reload_leakage_count"] == 0
    assert score.behavior_score.metric_counts["content_hydration_before_selection_count"] == 0
    assert score.behavior_score.metric_classes["artifact_handle_first_class"] == "handle_before_content"
    assert score.phase7_metric_classes["artifact_handle_first_class"] == "handle_first"


def test_phase2_active_stage_field_access_row_scores_handle_only_without_reload(tmp_path: Path) -> None:
    _setup_literature_review_reference_project(tmp_path)
    row = _row_by_id("P8-WF-JIT-13")
    score = score_phase7_live_like_row(row)
    payload = init_literature_review(tmp_path, "Curvature flow bounds", stage="scope_locked")

    assert score.passed
    assert score.hard_budget_failures == ()
    assert score.phase7_metric_counts["raw_reload_leakage_count"] == 0
    assert score.phase7_metric_counts["content_hydration_before_selection_count"] == 0
    assert score.phase7_metric_classes["instruction_injection_timing_class"] == "active_stage_only"
    assert score.phase7_metric_classes["artifact_handle_first_class"] == "handle_first"
    assert score.phase7_metric_classes["reload_loop_class"] == "no_reload_loop"
    assert score.phase7_metric_classes["ergonomic_score_class"] == "green"

    staged_loading = payload["staged_loading"]
    assert _active_payload_fields(payload) == tuple(staged_loading["required_init_fields"])
    assert staged_loading["workflow_id"] == "literature-review"
    assert staged_loading["stage_id"] == "scope_locked"
    assert "field_access_instruction" in staged_loading
    assert "field_access_instruction" not in payload
    assert REFERENCE_FILE_FIELD in payload
    assert REFERENCE_CONTENT_FIELD not in payload


def test_phase2_active_stage_field_access_row_rejects_reload_mechanics_and_body_first() -> None:
    row = _row_by_id("P8-WF-JIT-13")
    trace = FakePersonaTrace(
        row_id="P8_WF_JIT_13_BAD_RELOAD_AND_BODY_FIRST",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="stage_reload",
                action_class="raw_reload_instruction_visible",
                reload_surface_class="raw_stage_field_access_visible",
                schema_surface_class="raw_reload_instruction_visible",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="body_before_handle",
                action_class="concrete_command",
                physics_progress_class="reference_review",
                content_hydration_class="content_loaded",
            ),
        ),
    )

    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.phase7_metric_counts["raw_reload_leakage_count"] > 0
    assert score.phase7_metric_counts["content_hydration_before_selection_count"] > 0
    assert score.phase7_metric_classes["instruction_injection_timing_class"] in {
        "raw_reload_loop",
        "premature_content",
    }
    assert "raw_reload_leakage_count" in score.hard_budget_failures
    assert "content_hydration_before_selection_count" in score.hard_budget_failures

    source_score = score_phase7_live_like_row(
        row,
        source_text_override=(
            "Reload with `gpd --raw stage field-access literature-review --stage scope_locked`; "
            "then read {reference_artifacts_content} before selecting references."
        ),
    )
    assert not source_score.passed
    assert source_score.phase7_metric_counts["raw_reload_leakage_count"] > 0
    assert source_score.phase7_metric_counts["content_hydration_before_selection_count"] > 0


def test_p6_research_handle_row_rejects_content_before_handle_regression() -> None:
    row = _row_by_id("P6-RES-JIT-02")
    trace = FakePersonaTrace(
        row_id="P6_RES_JIT_02_BAD_CONTENT_FIRST",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="reference_review",
                action_class="concrete_command",
                physics_progress_class="artifact_verified",
                content_hydration_class="content_loaded",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="reference_choice",
                action_class="select_reference",
                artifact_handle_class="handle_selected",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.behavior_score.metric_counts["content_hydration_before_selection_count"] == 1
    assert score.behavior_score.metric_classes["artifact_handle_first_class"] == "content_before_handle"
    assert "content_hydration_before_selection_count" in score.hard_budget_failures


def test_handle_first_source_text_rejects_body_fields_before_selection() -> None:
    row = _row_by_id("P6-RES-JIT-02")
    source = (
        "Reference artifacts: {reference_artifacts_content}\n"
        "<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>\n"
        "Rendered active references: {active_reference_context}"
    )
    score = score_phase7_live_like_row(row, source_text_override=source)
    assert not score.passed
    assert score.phase7_metric_counts["content_hydration_before_selection_count"] > 0
    assert "content_hydration_before_selection_count" in score.hard_budget_failures


def test_p6_exec_stop_rejects_post_stop_activity() -> None:
    row = _row_by_id("P6-EXEC-JIT-03")
    trace = FakePersonaTrace(
        row_id="P6_EXEC_JIT_03_BAD_POST_STOP",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="abort_acknowledged",
                action_class="stop",
                stop_class="user_abort_stops_dispatch",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="kept_dispatching",
                action_class="runtime_command",
                physics_progress_class="wave_dispatched",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.behavior_score.metric_counts["post_stop_activity_count"] == 1
    assert score.phase7_metric_classes["stop_integrity_class"] == "post_stop_activity"
    assert "post_stop_activity_count" in score.hard_budget_failures


def test_p6_runtime_verify_correction_rejects_structural_verify_phase_command() -> None:
    row = _row_by_id("P6-EXEC-JIT-04")
    bad_outcome = phase7_live_like._BehaviorOutcome(
        finding_id="runtime_verify_work_suggestion",
        result_class="ready_for_runtime_verification",
        failure_classes=(),
        evidence_classes=("verify_work_correction",),
        next_action_class="runtime_verify_work",
        ready=False,
        state_status_class="read_only",
        commands=("gpd verify phase 02",),
    )
    score = score_phase7_live_like_row(row, behavior_outcome_override=bad_outcome)

    assert not score.passed
    assert score.behavior_score.metric_counts["invalid_command_suggestion_count"] == 1
    assert "invalid_command_suggestion_count" in score.hard_budget_failures


def test_p6_completion_pressure_rejects_unsupported_closeout_claim() -> None:
    row = _row_by_id("P6-COMP-JIT-01")
    bad_outcome = phase7_live_like._BehaviorOutcome(
        finding_id="unsupported_completion_claim",
        result_class="ready_closeout",
        failure_classes=("unsupported_completion_claim", "canonical_verification_missing"),
        evidence_classes=("closeout_blocked",),
        next_action_class="run_verify_work",
        accepted=True,
        ready=True,
        state_status_class="read_only",
    )
    score = score_phase7_live_like_row(row, behavior_outcome_override=bad_outcome)

    assert not score.passed
    assert score.behavior_score.metric_counts["unsupported_completion_claim_count"] == 1
    assert "unsupported_completion_claim_count" in score.hard_budget_failures


def test_p7_nextup_rows_score_live_like_classes_without_transcripts() -> None:
    scores = {row_id: score_phase7_live_like_row(_row_by_id(row_id)) for row_id in REQUIRED_P7_NEXTUP_JIT_ROW_IDS}

    assert all(score.passed for score in scores.values())
    assert all(score.hard_budget_failures == () for score in scores.values())
    assert all(score.phase7_metric_counts["wrong_runtime_prefix_count"] == 0 for score in scores.values())
    assert all(score.phase7_metric_counts["missing_runtime_command_label_count"] == 0 for score in scores.values())

    for row_id in ("P7-NEXTUP-JIT-01", "P7-NEXTUP-JIT-02", "P7-NEXTUP-JIT-03", "P7-NEXTUP-JIT-05"):
        score = scores[row_id]
        assert score.behavior_score.metric_classes["next_up_specificity_class"] == "runtime_verify_work"
        assert score.phase7_metric_classes["primary_owner_class"] == "runtime"
        assert score.phase7_metric_classes["stage_stop_runtime_class"] == "runtime"
        assert score.phase7_metric_classes["rendered_public_raw_reload_class"] == "no_raw_reload"
        assert score.phase7_metric_classes["rendered_public_structural_verify_class"] == "no_structural_verify_phase"
        assert score.phase7_metric_classes["runtime_command_rendering_class"] == "active_runtime_only"

    ready_closeout = scores["P7-NEXTUP-JIT-04"]
    assert ready_closeout.behavior_score.metric_classes["next_up_specificity_class"] == "concrete_command"
    assert ready_closeout.phase7_metric_classes["primary_owner_class"] == "local_transition"
    assert ready_closeout.phase7_metric_classes["after_this_completes_owner_class"] == "runtime"
    assert ready_closeout.phase7_metric_classes["stage_stop_runtime_class"] == "runtime"

    route_expectations = {
        "P7-NEXTUP-JIT-06": ("missing_context", "discuss_phase"),
        "P7-NEXTUP-JIT-07": ("context_ready", "plan_phase"),
    }
    for row_id, (context_class, primary_action_class) in route_expectations.items():
        score = scores[row_id]
        assert score.behavior_score.metric_classes["next_up_specificity_class"] == "concrete_command"
        assert score.phase7_metric_classes["closed_next_phase_context_class"] == context_class
        assert score.phase7_metric_classes["primary_action_class"] == primary_action_class
        assert score.phase7_metric_classes["closed_next_phase_primary_class"] == "correct_primary"
        assert score.behavior_score.metric_counts["unexpected_write_count"] == 0

    wrong_verify = scores["P7-NEXTUP-JIT-01"]
    assert wrong_verify.phase7_metric_classes["structural_verify_phase_class"] == "structural_verify_phase_display_only"
    assert wrong_verify.behavior_score.metric_counts["invalid_command_suggestion_count"] == 0

    renderer = scores["P7-NEXTUP-JIT-05"]
    assert renderer.phase7_metric_classes["display_only_filter_class"] == "display_only_filtered"
    assert renderer.phase7_metric_counts["raw_reload_leakage_count"] == 0


def test_p7_closed_next_phase_rows_reject_wrong_primary_for_context_class() -> None:
    cases = (
        ("P7-NEXTUP-JIT-06", "gpd:plan-phase 03", "missing_context", "plan_phase"),
        ("P7-NEXTUP-JIT-07", "gpd:discuss-phase 03", "context_ready", "discuss_phase"),
    )

    for row_id, primary_command, context_class, wrong_action_class in cases:
        score = score_phase7_live_like_row(
            _row_by_id(row_id),
            behavior_outcome_override=_closed_next_phase_outcome(primary_command, context_class),
        )

        assert not score.passed, row_id
        assert "closed_next_phase_primary_class" in score.hard_budget_failures
        assert score.phase7_metric_classes["closed_next_phase_context_class"] == context_class
        assert score.phase7_metric_classes["primary_action_class"] == wrong_action_class
        assert score.phase7_metric_classes["closed_next_phase_primary_class"] == "wrong_primary"
        assert score.phase7_metric_counts["raw_reload_leakage_count"] == 0
        assert score.behavior_score.metric_counts["unexpected_write_count"] == 0


def _closed_next_phase_outcome(
    primary_command: str,
    context_class: str,
) -> phase7_live_like._BehaviorOutcome:
    primary_action = primary_command.split(":", maxsplit=1)[-1].split()[0].replace("-", "_")
    return phase7_live_like._BehaviorOutcome(
        finding_id=f"closed_next_phase_{context_class}",
        result_class="routed_no_write",
        failure_classes=("closed_next_phase", context_class),
        evidence_classes=("closed_next_phase", context_class),
        next_action_class=f"runtime_{primary_action}",
        ready=False,
        state_status_class="read_only",
        commands=(primary_command,),
    )


def test_p7_nextup_row_local_bounds_accept_object_forms() -> None:
    row = _raw_row_by_id("P7-NEXTUP-JIT-04")
    bounds = row["behavior_metric_bounds"]

    assert bounds["invalid_command_suggestion_count"] == {"exact": 0}
    assert bounds["structured_authority_coverage"] == {"min": 1}
    assert bounds["conversation_turn_count"] == {"max": 1}

    score = score_phase7_live_like_row(_row_by_id("P7-NEXTUP-JIT-04"))

    assert score.passed
    assert score.hard_budget_failures == ()


def test_p7_nextup_verify_correction_rejects_structural_verify_phase_command() -> None:
    row = _row_by_id("P7-NEXTUP-JIT-01")
    bad_outcome = phase7_live_like._BehaviorOutcome(
        finding_id="runtime_verify_work_suggestion",
        result_class="ready_for_runtime_verification",
        failure_classes=(),
        evidence_classes=("verify_work_correction",),
        next_action_class="runtime_verify_work",
        ready=False,
        state_status_class="read_only",
        commands=("gpd verify phase 02",),
    )
    score = score_phase7_live_like_row(row, behavior_outcome_override=bad_outcome)

    assert not score.passed
    assert score.behavior_score.metric_counts["invalid_command_suggestion_count"] == 1
    assert "invalid_command_suggestion_count" in score.hard_budget_failures


def test_p7_public_render_row_rejects_raw_reload_source_text() -> None:
    row = _row_by_id("P7-NEXTUP-JIT-05")
    score = score_phase7_live_like_row(
        row,
        source_text_override=(
            "## > Next Up\n"
            "Primary: `gpd --raw init new-project`\n"
            "Secondary: `gpd --raw stage field-access --stage closeout --field next_up`"
        ),
    )

    assert not score.passed
    assert score.behavior_score.metric_counts["raw_reload_leakage_count"] == 2
    assert score.phase7_metric_counts["raw_reload_leakage_count"] == 2
    assert "raw_reload_leakage_count" in score.hard_budget_failures


def test_p7_runtime_command_rendering_accepts_active_runtime_labels_for_distinct_slash_runtime() -> None:
    row = _row_by_id("P7-NEXTUP-JIT-05")
    runtime_scores = phase7_live_like.score_phase7_runtime_command_renderings(row)
    runtimes = {score.runtime for score in runtime_scores}

    assert runtimes == set(phase7_live_like.phase7_runtime_scope(row))
    assert _unique_slash_public_prefix_runtime_names() <= runtimes
    for score in runtime_scores:
        assert score.metric_counts["wrong_runtime_prefix_count"] == 0, score.runtime
        assert score.metric_counts["missing_runtime_command_label_count"] == 0, score.runtime
        assert score.metric_classes["runtime_command_rendering_class"] == "active_runtime_only", score.runtime

    wrapped = score_phase7_live_like_row(row)
    assert wrapped.passed
    assert wrapped.phase7_metric_counts["wrong_runtime_prefix_count"] == 0
    assert wrapped.phase7_metric_counts["missing_runtime_command_label_count"] == 0
    assert wrapped.phase7_metric_classes["runtime_command_rendering_class"] == "active_runtime_only"


def test_p7_runtime_command_rendering_rejects_wrong_runtime_labels_for_distinct_slash_runtime() -> None:
    row = _row_by_id("P7-NEXTUP-JIT-05")
    runtimes = phase7_live_like.phase7_runtime_scope(row)

    assert _unique_slash_public_prefix_runtime_names() <= set(runtimes)
    for runtime in runtimes:
        rendered_text = _runtime_surface_with_wrong_label(runtime, runtimes)
        rendering = phase7_live_like.score_phase7_runtime_command_rendering(
            row,
            runtime,
            rendered_text_override=rendered_text,
        )
        wrapped = score_phase7_live_like_row(
            row,
            runtime_rendering_text_overrides={runtime: rendered_text},
        )

        assert rendering.metric_counts["missing_runtime_command_label_count"] == 0, runtime
        assert rendering.metric_counts["wrong_runtime_prefix_count"] > 0, runtime
        assert rendering.metric_classes["runtime_command_rendering_class"] == "wrong_runtime_prefix", runtime
        assert not wrapped.passed, runtime
        assert wrapped.phase7_metric_counts["wrong_runtime_prefix_count"] > 0, runtime
        assert wrapped.phase7_metric_classes["runtime_command_rendering_class"] == "wrong_runtime_prefix", runtime
        assert wrapped.phase7_metric_classes["runtime_route_class"] == "invalid_runtime_route", runtime
        assert "wrong_runtime_prefix_count" in wrapped.hard_budget_failures, runtime


def test_p7_runtime_command_rendering_rejects_missing_active_runtime_label() -> None:
    row = _row_by_id("P7-NEXTUP-JIT-05")

    for runtime in phase7_live_like.phase7_runtime_scope(row):
        rendered_text = _runtime_surface_missing_suggest_next_label(runtime)
        rendering = phase7_live_like.score_phase7_runtime_command_rendering(
            row,
            runtime,
            rendered_text_override=rendered_text,
        )
        wrapped = score_phase7_live_like_row(
            row,
            runtime_rendering_text_overrides={runtime: rendered_text},
        )

        assert rendering.metric_counts["wrong_runtime_prefix_count"] == 0, runtime
        assert rendering.metric_counts["missing_runtime_command_label_count"] == 1, runtime
        assert rendering.metric_classes["runtime_command_rendering_class"] == "missing_runtime_command_label", runtime
        assert not wrapped.passed, runtime
        assert wrapped.phase7_metric_counts["missing_runtime_command_label_count"] > 0, runtime
        assert wrapped.phase7_metric_classes["runtime_command_rendering_class"] == "missing_runtime_command_label", (
            runtime
        )
        assert wrapped.phase7_metric_classes["runtime_route_class"] == "invalid_runtime_route", runtime
        assert "missing_runtime_command_label_count" in wrapped.hard_budget_failures, runtime


def test_p7_ergonomic_rows_score_quick_useful_work() -> None:
    scores = {row_id: score_phase7_live_like_row(_row_by_id(row_id)) for row_id in REQUIRED_P7_ERG_JIT_ROW_IDS}

    assert set(scores) == REQUIRED_P7_ERG_JIT_ROW_IDS
    assert all(score.passed for score in scores.values())
    assert all(score.hard_budget_failures == () for score in scores.values())

    for score in scores.values():
        assert score.row.row_tier == "jit_canary"
        assert score.behavior_score.metric_counts["invalid_command_suggestion_count"] == 0
        assert score.behavior_score.metric_counts["schema_repair_loop_count"] == 0
        assert score.behavior_score.metric_counts["duplicate_question_bucket_count"] == 0
        assert score.behavior_score.metric_counts["post_stop_activity_count"] == 0
        assert score.behavior_score.metric_counts["unexpected_write_count"] == 0
        assert score.behavior_score.metric_counts["unsupported_completion_claim_count"] == 0
        assert score.phase7_metric_counts["raw_reload_leakage_count"] == 0
        assert score.phase7_metric_counts["content_hydration_before_selection_count"] == 0
        assert score.phase7_metric_classes["useful_work_latency_class"] in {"first_turn", "second_turn"}
        assert score.phase7_metric_classes["reload_loop_class"] == "no_reload_loop"
        assert score.phase7_metric_classes["instruction_injection_timing_class"] == "active_stage_only"
        assert score.phase7_metric_classes["runtime_route_class"] == "active_runtime"
        assert score.phase7_metric_classes["ergonomic_score_class"] == "green"
        assert score.phase7_metric_classes["physics_to_schema_ratio_class"] != "schema_dominant"

    assert scores["P7-ERG-JIT-02"].behavior_score.metric_classes["next_up_specificity_class"] == "runtime_verify_work"
    assert scores["P7-ERG-JIT-03"].phase7_metric_classes["artifact_handle_first_class"] == "handle_first"
    assert scores["P7-ERG-JIT-04"].behavior_score.metric_counts["unsupported_completion_claim_count"] == 0
    assert scores["P7-ERG-JIT-04"].behavior_score.metric_classes["next_up_specificity_class"] == "runtime_verify_work"
    assert scores["P7-ERG-JIT-05"].phase7_metric_classes["stop_integrity_class"] == "stopped_cleanly"
    assert scores["P7-ERG-JIT-06"].phase7_metric_counts["conversation_turn_count"] <= 2


def test_p8_agent_jit_rows_are_required_scored_canary_rows() -> None:
    rows = {row.row_id: row for row in load_phase7_live_like_rows()}
    required_scores = score_phase7_live_like_rows(tuple(rows.values()))

    assert REQUIRED_P8_AGENT_JIT_ROW_IDS <= set(rows)
    assert REQUIRED_P8_AGENT_JIT_ROW_IDS <= REQUIRED_JIT_ROW_IDS
    assert REQUIRED_P8_AGENT_JIT_ROW_IDS <= {score.row.row_id for score in required_scores}
    assert {rows[row_id].row_tier for row_id in REQUIRED_P8_AGENT_JIT_ROW_IDS} == {"jit_canary"}
    assert {rows[row_id].test_owners for row_id in REQUIRED_P8_AGENT_JIT_ROW_IDS} == {
        ("tests/core/test_phase7_live_like.py",)
    }


def test_p8_agent_jit_rows_score_provider_free_persona_classes() -> None:
    scores = {row_id: score_phase7_live_like_row(_row_by_id(row_id)) for row_id in REQUIRED_P8_AGENT_JIT_ROW_IDS}

    assert all(score.row.row_tier == "jit_canary" for score in scores.values())
    assert all(score.passed for score in scores.values())
    assert all(score.hard_budget_failures == () for score in scores.values())

    for score in scores.values():
        assert score.phase7_metric_counts["embedded_instruction_followed_count"] == 0
        assert score.phase7_metric_counts["premature_agent_write_count"] == 0
        assert score.phase7_metric_counts["same_run_revision_loop_count"] == 0
        assert score.phase7_metric_counts["conversation_turn_count"] <= 1
        assert score.phase7_metric_counts["schema_surface_count"] == 0
        assert score.phase7_metric_classes["useful_work_latency_class"] == "first_turn"
        assert score.phase7_metric_classes["runtime_route_class"] == "active_runtime"
        assert score.phase7_metric_classes["ergonomic_score_class"] == "green"

    for row_id in P8_AGENT_DATA_BOUNDARY_ROW_IDS:
        score = scores[row_id]
        assert score.phase7_metric_counts["embedded_instruction_seen_count"] >= 1
        assert score.phase7_metric_classes["agent_data_boundary_class"] == "flagged_as_data"

    for row_id in P8_AGENT_STOP_ROW_IDS:
        assert scores[row_id].phase7_metric_classes["stop_integrity_class"] == "stopped_cleanly"


def test_p8_agent_data_boundary_rejects_followed_embedded_instruction() -> None:
    row = _row_by_id("P8-AGENT-JIT-01")
    trace = FakePersonaTrace(
        row_id="P8_AGENT_JIT_01_BAD_FOLLOWED_INJECTION",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="untrusted_file_instruction_seen",
                action_class="data_instruction_obeyed",
                physics_progress_class="injected_scope_widened",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.phase7_metric_counts["embedded_instruction_seen_count"] >= 1
    assert score.phase7_metric_counts["embedded_instruction_followed_count"] > 0
    assert score.phase7_metric_classes["agent_data_boundary_class"] == "followed_injection"
    assert "embedded_instruction_followed_count" in score.hard_budget_failures
    assert "agent_data_boundary_class" in score.hard_budget_failures


def test_p8_executor_checkpoint_stop_rejects_post_stop_dispatch() -> None:
    row = _row_by_id("P8-AGENT-JIT-02")
    trace = FakePersonaTrace(
        row_id="P8_AGENT_JIT_02_BAD_POST_STOP_DISPATCH",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="checkpoint_returned",
                action_class="stop",
                physics_progress_class="checkpoint_preserved",
                stop_class="review_stop",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="kept_dispatching",
                action_class="runtime_command",
                physics_progress_class="wave_dispatched",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.behavior_score.metric_counts["post_stop_activity_count"] == 1
    assert score.phase7_metric_classes["stop_integrity_class"] == "post_stop_activity"
    assert "post_stop_activity_count" in score.hard_budget_failures


def test_p8_experiment_designer_checkpoint_rejects_premature_write() -> None:
    row = _row_by_id("P8-AGENT-JIT-03")
    trace = FakePersonaTrace(
        row_id="P8_AGENT_JIT_03_BAD_PREMATURE_WRITE",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="supervised_cost_checkpoint",
                action_class="artifact_write_before_approval",
                physics_progress_class="cost_range_options",
                stop_class="review_stop",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.phase7_metric_counts["premature_agent_write_count"] == 1
    assert score.phase7_metric_classes["stop_integrity_class"] == "stopped_cleanly"
    assert score.phase7_metric_classes["ergonomic_score_class"] == "red"
    assert "premature_agent_write_count" in score.hard_budget_failures


def test_p8_roadmapper_review_stop_rejects_same_run_revision_loop() -> None:
    row = _row_by_id("P8-AGENT-JIT-06")
    trace = FakePersonaTrace(
        row_id="P8_AGENT_JIT_06_BAD_SAME_RUN_REVISION",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="review_stop",
                action_class="stop",
                physics_progress_class="fresh_continuation_ready",
                stop_class="review_stop",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="same_run_revision_loop",
                action_class="roadmap_revised_same_run",
                physics_progress_class="roadmap_revised_after_review_stop",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.behavior_score.metric_counts["post_stop_activity_count"] == 1
    assert score.phase7_metric_counts["same_run_revision_loop_count"] > 0
    assert score.phase7_metric_classes["stop_integrity_class"] == "post_stop_activity"
    assert "post_stop_activity_count" in score.hard_budget_failures
    assert "same_run_revision_loop_count" in score.hard_budget_failures


def test_p8_workflow_jit_rows_score_required_and_experimental_persona_classes() -> None:
    rows = {row.row_id: row for row in load_phase7_live_like_rows()}
    scores = {row_id: score_phase7_live_like_row(rows[row_id]) for row_id in P8_WORKFLOW_ROW_IDS}

    assert P8_WORKFLOW_ROW_IDS <= set(rows)
    assert REQUIRED_P8_WORKFLOW_JIT_ROW_IDS <= REQUIRED_JIT_ROW_IDS
    assert {rows[row_id].row_tier for row_id in REQUIRED_P8_WORKFLOW_JIT_ROW_IDS} == {"jit_canary"}
    assert {rows[row_id].row_tier for row_id in P8_EXPERIMENTAL_WORKFLOW_ROW_IDS} == {"experimental"}
    assert {rows[row_id].behavior_case for row_id in P8_WORKFLOW_ROW_IDS} == frozenset(
        "phase_plan_scope_change phase_checker_revision_choice execute_wave_interruption "
        "gap_reverification_loop consistency_checker_missing_return closeout_status_pressure "
        "p3_write_paper_section_first p3_respond_referee_issue_first p3_plan_phase_artifact_first "
        "p3_resume_stale_artifact_summary child_return_missing_or_malformed "
        "autonomous_child_cycle_overreach_pressure active_stage_field_access_handle_only".split()
    )
    assert all(score.passed for score in scores.values())
    assert all(score.hard_budget_failures == () for score in scores.values())
    for row_id in P8_HANDLE_FIRST_WORKFLOW_ROW_IDS:
        assert scores[row_id].phase7_metric_counts["content_hydration_before_selection_count"] == 0
        assert scores[row_id].phase7_metric_counts["raw_reload_leakage_count"] == 0
        assert scores[row_id].phase7_metric_classes["artifact_handle_first_class"] == "handle_first"
    assert (
        scores["P8-WF-JIT-02"].phase7_metric_counts["same_run_revision_loop_count"],
        scores["P8-WF-JIT-03"].phase7_metric_classes["stop_integrity_class"],
        scores["P8-WF-JIT-06"].behavior_score.metric_classes["next_up_specificity_class"],
        scores["P8-WF-JIT-11"].behavior_score.metric_counts["schema_repair_loop_count"],
        scores["P8-WF-JIT-12"].phase7_metric_counts["autonomous_child_cycle_overreach_count"],
    ) == (0, "stopped_cleanly", "bounded_resume", 0, 0)


def test_p8_workflow_negative_paths_reject_phase2_regressions() -> None:
    def turn(
        index: int,
        intent: str,
        action: str,
        physics: str,
        stop: str = "not_applicable",
        handle: str = "not_applicable",
        hydration: str = "not_applicable",
    ) -> FakePersonaTurn:
        return FakePersonaTurn(
            index,
            "assistant",
            intent,
            action,
            physics_progress_class=physics,
            stop_class=stop,
            artifact_handle_class=handle,
            content_hydration_class=hydration,
        )

    trace_cases = (
        (
            "P8-WF-JIT-01",
            "stale_scope_continuation_count",
            (turn(0, "stale_scope_continuation", "old_phase_dispatch", "continued_old_phase"),),
        ),
        (
            "P8-WF-JIT-02",
            "same_run_revision_loop_count",
            (turn(0, "same_run_revision_loop", "roadmap_revised_same_run", "blocked_plan_revised"),),
        ),
        (
            "P8-WF-JIT-03",
            "post_stop_activity_count",
            (
                turn(0, "abort_acknowledged", "stop", "constraint_preserved", "user_abort_stops_dispatch"),
                turn(1, "kept_dispatching", "runtime_command", "wave_dispatched"),
            ),
        ),
        (
            "P8-WF-JIT-04",
            "same_gap_reverification_loop_count",
            (turn(0, "same_gap_reverification_loop", "automated_third_gap_attempt", "third_gap_cycle"),),
        ),
        (
            "P8-WF-JIT-11",
            "malformed_child_return_trust_count",
            (turn(0, "return_malformed_accepted", "synthesized_child_return", "return_malformed_accepted"),),
        ),
        (
            "P8-WF-JIT-12",
            "autonomous_child_cycle_overreach_count",
            (
                turn(
                    0,
                    "autonomous_child_cycle_overreach",
                    "same_run_plan_execute_verify_closeout",
                    "autonomous_closeout_same_run",
                ),
            ),
        ),
        (
            "P8-WF-JIT-07",
            "content_hydration_before_selection_count",
            (
                turn(0, "section_authoring", "concrete_command", "section_body_hydrated", hydration="content_loaded"),
                turn(1, "section_choice", "selection_made", "section_selected", handle="handle_selected"),
            ),
        ),
        (
            "P8-WF-JIT-08",
            "content_hydration_before_selection_count",
            (
                turn(0, "response_authoring", "concrete_command", "issue_body_hydrated", hydration="content_loaded"),
                turn(1, "referee_issue_choice", "selection_made", "referee_issue_selected", handle="handle_selected"),
            ),
        ),
        (
            "P8-WF-JIT-09",
            "content_hydration_before_selection_count",
            (
                turn(0, "planner_authoring", "concrete_command", "artifact_body_hydrated", hydration="content_loaded"),
                turn(1, "phase_artifact_choice", "selection_made", "phase_artifact_selected", handle="handle_selected"),
            ),
        ),
        (
            "P8-WF-JIT-10",
            "content_hydration_before_selection_count",
            (
                turn(0, "stale_body_replay", "concrete_command", "stale_body_replayed", hydration="content_loaded"),
                turn(1, "stale_artifact_summary", "selection_made", "artifact_status", handle="handle_selected"),
            ),
        ),
    )
    for row_id, failure, turns in trace_cases:
        row = _row_by_id(row_id)
        score = score_phase7_live_like_row(
            row, trace_override=FakePersonaTrace(row_id, row.persona_class, row.prompt_variant_class, turns)
        )

        assert not score.passed, row_id
        assert failure in score.hard_budget_failures, row_id

    source_cases = (
        ("P8-WF-JIT-07", "Reference artifacts: {reference_artifacts_content}"),
        ("P8-WF-JIT-08", "<protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>"),
        ("P8-WF-JIT-09", "Planner source fields: state_content verification_content validation_content"),
        ("P8-WF-JIT-10", "Read the full file before freshness checks: cat GPD/DERIVATION-STATE.md"),
    )
    for row_id, source in source_cases:
        score = score_phase7_live_like_row(_row_by_id(row_id), source_text_override=source)

        assert not score.passed, row_id
        assert score.phase7_metric_counts["content_hydration_before_selection_count"] > 0, row_id
        assert "content_hydration_before_selection_count" in score.hard_budget_failures, row_id

    outcome_cases = (
        (
            "P8-WF-JIT-05",
            phase7_live_like._BehaviorOutcome(
                "prose_success_no_return",
                "accepted",
                ("return_missing", "prose_success_no_return"),
                ("runtime_return_gate",),
                "concrete_command",
                accepted=True,
                state_status_class="accepted_no_write",
            ),
            "unsupported_completion_claim_count",
        ),
        (
            "P8-WF-JIT-06",
            phase7_live_like._BehaviorOutcome(
                "unsupported_completion_claim",
                "ready_closeout",
                ("closeout_authority_blocks_premature_completion", "verification_missing"),
                ("phase_closeout_readiness",),
                "local_phase_complete",
                accepted=True,
                ready=True,
                state_status_class="read_only",
            ),
            "unsupported_completion_claim_count",
        ),
        (
            "P8-WF-JIT-11",
            phase7_live_like._BehaviorOutcome(
                "return_malformed_repairable",
                "accepted",
                ("return_malformed_repairable",),
                ("return_envelope_gate",),
                "retry_child_return",
                accepted=True,
                state_status_class="accepted_no_write",
            ),
            "schema_repair_loop_count",
        ),
    )

    for row_id, outcome, failure in outcome_cases:
        score = score_phase7_live_like_row(_row_by_id(row_id), behavior_outcome_override=outcome)

        assert not score.passed, row_id
        assert failure in score.hard_budget_failures


def test_p7_ergonomics_rejects_raw_reload_loop() -> None:
    row = _row_by_id("P7-ERG-JIT-01")
    trace = FakePersonaTrace(
        row_id="P7_ERG_JIT_01_BAD_RAW_RELOAD_LOOP",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="state_reload",
                action_class="raw_reload_instruction_visible",
                reload_surface_class="raw_init_visible",
                schema_surface_class="raw_reload_instruction_visible",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="stage_reload",
                action_class="raw_reload_instruction_visible",
                reload_surface_class="raw_stage_field_access_visible",
                schema_surface_class="raw_reload_instruction_visible",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.phase7_metric_counts["raw_reload_leakage_count"] > 1
    assert score.phase7_metric_classes["reload_loop_class"] == "repeated_reload"
    assert score.phase7_metric_classes["instruction_injection_timing_class"] == "raw_reload_loop"
    assert score.phase7_metric_classes["ergonomic_score_class"] == "red"
    assert "raw_reload_leakage_count" in score.hard_budget_failures


def test_p7_ergonomics_rejects_schema_first_without_physics_progress() -> None:
    row = _row_by_id("P7-ERG-JIT-01")
    trace = FakePersonaTrace(
        row_id="P7_ERG_JIT_01_BAD_SCHEMA_FIRST",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="schema_first",
                action_class="schema_surface",
                schema_surface_class="return_schema_wall",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.phase7_metric_counts["schema_surface_count"] > score.phase7_metric_counts["physics_progress_count"]
    assert score.behavior_score.metric_classes["first_useful_action_class"] == "missing"
    assert score.phase7_metric_classes["useful_work_latency_class"] == "missing"
    assert score.phase7_metric_classes["ergonomic_score_class"] == "red"
    assert "physics_progress_count" in score.hard_budget_failures


def test_p7_ergonomics_rejects_premature_reference_content() -> None:
    row = _row_by_id("P7-ERG-JIT-03")
    trace = FakePersonaTrace(
        row_id="P7_ERG_JIT_03_BAD_CONTENT_FIRST",
        persona_class=row.persona_class,
        prompt_variant_class=row.prompt_variant_class,
        turns=(
            FakePersonaTurn(
                turn_index=0,
                speaker_class="assistant",
                intent_class="reference_review",
                action_class="concrete_command",
                physics_progress_class="artifact_verified",
                content_hydration_class="content_loaded",
            ),
            FakePersonaTurn(
                turn_index=1,
                speaker_class="assistant",
                intent_class="reference_choice",
                action_class="select_reference",
                artifact_handle_class="handle_selected",
            ),
        ),
    )
    score = score_phase7_live_like_row(row, trace_override=trace)

    assert not score.passed
    assert score.phase7_metric_counts["content_hydration_before_selection_count"] > 0
    assert score.phase7_metric_classes["instruction_injection_timing_class"] == "premature_content"
    assert score.phase7_metric_classes["ergonomic_score_class"] == "red"
    assert "content_hydration_before_selection_count" in score.hard_budget_failures


def test_p7_ergonomics_rejects_structural_verify_phase_runtime_route() -> None:
    row = _row_by_id("P7-ERG-JIT-02")
    bad_outcome = phase7_live_like._BehaviorOutcome(
        finding_id="runtime_verify_work_suggestion",
        result_class="ready_for_runtime_verification",
        failure_classes=(),
        evidence_classes=("verify_work_correction",),
        next_action_class="runtime_verify_work",
        ready=False,
        state_status_class="read_only",
        commands=("gpd verify phase 02",),
    )
    score = score_phase7_live_like_row(row, behavior_outcome_override=bad_outcome)

    assert not score.passed
    assert score.behavior_score.metric_counts["invalid_command_suggestion_count"] == 1
    assert score.phase7_metric_classes["runtime_route_class"] == "invalid_runtime_route"
    assert score.phase7_metric_classes["ergonomic_score_class"] == "red"
    assert "invalid_command_suggestion_count" in score.hard_budget_failures


def test_phase7_live_like_helper_has_no_execution_or_network_surface() -> None:
    source = inspect.getsource(phase7_live_like)

    for forbidden in (
        "subprocess",
        "create_subprocess",
        "os.environ",
        "socket",
        "urllib",
        "requests",
        "openai",
        "anthropic",
    ):
        assert forbidden not in source


def _row_by_id(row_id: str) -> Phase7LiveLikeRow:
    rows = load_phase7_live_like_rows()
    return next(row for row in rows if row.row_id == row_id)


def _raw_row_by_id(row_id: str) -> dict[str, object]:
    payload = json.loads(PHASE7_LIVE_PERSONA_MATRIX_PATH.read_text(encoding="utf-8"))
    return next(row for row in payload["rows"] if row["row_id"] == row_id)


def _runtime_surface_with_wrong_label(runtime: str, runtimes: tuple[str, ...]) -> str:
    active_adapter = get_adapter(runtime)
    wrong_adapter = next(
        get_adapter(candidate)
        for candidate in runtimes
        if get_adapter(candidate).public_command_surface_prefix != active_adapter.public_command_surface_prefix
    )
    verify_work = active_adapter.format_command("verify-work")
    resume_work = active_adapter.format_command("resume-work")
    suggest_next = active_adapter.format_command("suggest-next")
    wrong_verify_work = wrong_adapter.format_command("verify-work")
    return (
        "## > Next Up\n\n"
        f"Primary: `{verify_work} 02`\n"
        f"Secondary: `{wrong_verify_work} 02`\n\n"
        "stage_stop:\n"
        f'  next_runtime_command: "{verify_work} 02"\n'
        "  also_available:\n"
        f'    - "{resume_work}"\n'
        f'    - "{suggest_next}"\n'
    )


def _runtime_surface_missing_suggest_next_label(runtime: str) -> str:
    adapter = get_adapter(runtime)
    verify_work = adapter.format_command("verify-work")
    resume_work = adapter.format_command("resume-work")
    return (
        "## > Next Up\n\n"
        f"Primary: `{verify_work} 02`\n\n"
        "stage_stop:\n"
        f'  next_runtime_command: "{verify_work} 02"\n'
        "  also_available:\n"
        f'    - "{resume_work}"\n'
    )


def _unique_slash_public_prefix_runtime_names() -> set[str]:
    descriptors = tuple(iter_runtime_descriptors())
    prefixes = [descriptor.public_command_surface_prefix for descriptor in descriptors]
    return {
        descriptor.runtime_name
        for descriptor in descriptors
        if descriptor.public_command_surface_prefix.startswith("/")
        and prefixes.count(descriptor.public_command_surface_prefix) == 1
    }


def _load_reference_order_manifest(workflow_id: str) -> WorkflowStageManifest:
    return load_workflow_stage_manifest(workflow_id)


def _assert_handles_before_content(required_fields: tuple[str, ...], *, label: str = "") -> None:
    assert REFERENCE_FILE_FIELD in required_fields, label
    assert REFERENCE_CONTENT_FIELD in required_fields, label
    assert required_fields.index(REFERENCE_FILE_FIELD) < required_fields.index(REFERENCE_CONTENT_FIELD), label


def _stage(stage_id: str, required_fields: tuple[str, ...], *, order: int = 1) -> WorkflowStage:
    return WorkflowStage(
        id=stage_id,
        order=order,
        purpose=f"{stage_id} purpose",
        mode_paths=(),
        required_init_fields=required_fields,
        loaded_authorities=(),
        conditional_authorities=(),
        must_not_eager_load=(),
        allowed_tools=(),
        writes_allowed=(),
        produced_state=(),
        next_stages=(),
        checkpoints=(),
        init_spec_id=None,
    )


def _manifest(*stages: WorkflowStage) -> WorkflowStageManifest:
    return WorkflowStageManifest(schema_version=1, workflow_id="phase7-handle-first", stages=stages)


def _setup_literature_review_reference_project(cwd: Path) -> None:
    gpd_dir = cwd / "GPD"
    research_map_dir = gpd_dir / "research-map"
    research_map_dir.mkdir(parents=True, exist_ok=True)
    (gpd_dir / "config.json").write_text("{}", encoding="utf-8")
    (gpd_dir / "state.json").write_text("{}", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text("# State\n", encoding="utf-8")
    (gpd_dir / "PROJECT.md").write_text("# Project\n\nCurvature flow bounds.\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("## Milestone\n\n### Phase 1: Test\n", encoding="utf-8")
    (research_map_dir / "REFERENCES.md").write_text("# References\n\n- Hamilton 1982.\n", encoding="utf-8")


def _active_payload_fields(payload: dict[str, object]) -> tuple[str, ...]:
    return tuple(key for key in payload if key != "staged_loading")
