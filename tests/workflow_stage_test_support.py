"""Shared assertions and fixtures for staged workflow init payload tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

STAGED_LOADING_KEY = "staged_loading"

PLAN_PHASE_STAGE_BOOTSTRAP_FIELDS = (
    "researcher_model",
    "planner_model",
    "checker_model",
    "research_enabled",
    "plan_checker_enabled",
    "commit_docs",
    "autonomy",
    "research_mode",
    "phase_found",
    "phase_dir",
    "phase_number",
    "phase_name",
    "phase_slug",
    "padded_phase",
    "has_research",
    "has_context",
    "has_plans",
    "plan_count",
    "planning_exists",
    "roadmap_exists",
    "project_contract",
    "project_contract_gate",
    "project_contract_load_info",
    "project_contract_validation",
    "platform",
)

PLAN_PHASE_STAGE_AUTHORING_FIELDS = (
    *PLAN_PHASE_STAGE_BOOTSTRAP_FIELDS,
    "contract_intake",
    "effective_reference_intake",
    "selected_protocol_bundle_ids",
    "protocol_bundle_count",
    "protocol_bundle_load_manifest",
    "protocol_bundle_context",
    "protocol_bundle_verifier_extensions",
    "active_reference_context",
    "reference_artifact_files",
    "reference_artifacts_content",
    "literature_review_files",
    "literature_review_count",
    "research_map_reference_files",
    "research_map_reference_count",
    "derived_manuscript_proof_review_status",
    "state_content",
    "roadmap_content",
    "requirements_content",
    "context_content",
    "research_content",
    "experiment_design_content",
    "verification_content",
    "validation_content",
)

PLAN_PHASE_STAGE_CHECKER_AUDIT_FIELDS = (
    "checker_model",
    "research_enabled",
    "plan_checker_enabled",
    "commit_docs",
    "autonomy",
    "research_mode",
    "phase_found",
    "phase_dir",
    "phase_number",
    "phase_name",
    "phase_slug",
    "padded_phase",
    "has_research",
    "has_context",
    "has_plans",
    "plan_count",
    "planning_exists",
    "roadmap_exists",
    "project_contract",
    "project_contract_gate",
    "project_contract_load_info",
    "project_contract_validation",
    "contract_intake",
    "effective_reference_intake",
    "selected_protocol_bundle_ids",
    "protocol_bundle_count",
    "protocol_bundle_load_manifest",
    "protocol_bundle_context",
    "protocol_bundle_verifier_extensions",
    "active_reference_context",
    "reference_artifact_files",
    "reference_artifacts_content",
    "literature_review_files",
    "literature_review_count",
    "research_map_reference_files",
    "research_map_reference_count",
    "derived_manuscript_proof_review_status",
    "requirements_content",
    "context_content",
    "research_content",
    "verification_content",
    "validation_content",
    "platform",
)


class FakeWorkflowStage:
    def __init__(self, stage_id: str, required_init_fields: Sequence[str]) -> None:
        self.id = stage_id
        self.required_init_fields = tuple(required_init_fields)
        self.init_spec_id: str | None = None


class FakeWorkflowStageManifest:
    def __init__(self, workflow_id: str, stages: Mapping[str, Sequence[str]]) -> None:
        self.workflow_id = workflow_id
        self._stages = {stage_id: FakeWorkflowStage(stage_id, fields) for stage_id, fields in stages.items()}

    def stage_by_id(self, stage_id: str) -> FakeWorkflowStage:
        return self._stages[stage_id]

    def stage_ids(self) -> list[str]:
        return list(self._stages)

    def staged_loading_payload(self, stage_id: str) -> dict[str, object]:
        return {"workflow_id": self.workflow_id, "stage_id": stage_id}


def install_fake_plan_phase_manifest(monkeypatch: object) -> FakeWorkflowStageManifest:
    return install_fake_stage_manifest(
        monkeypatch,
        workflow_id="plan-phase",
        stages={
            "phase_bootstrap": PLAN_PHASE_STAGE_BOOTSTRAP_FIELDS,
            "research_routing": PLAN_PHASE_STAGE_BOOTSTRAP_FIELDS,
            "planner_authoring": PLAN_PHASE_STAGE_AUTHORING_FIELDS,
            "checker_revision": PLAN_PHASE_STAGE_CHECKER_AUDIT_FIELDS,
        },
    )


def install_fake_stage_manifest(
    monkeypatch: object,
    *,
    workflow_id: str,
    stages: Mapping[str, Sequence[str]],
) -> FakeWorkflowStageManifest:
    manifest = FakeWorkflowStageManifest(workflow_id, stages)

    def fake_load_workflow_stage_manifest(
        requested_workflow_id: str,
        allowed_tools: set[str] | None = None,
        known_init_fields: set[str] | None = None,
    ) -> FakeWorkflowStageManifest:
        assert requested_workflow_id == workflow_id
        return manifest

    monkeypatch.setattr("gpd.core.workflow_staging.load_workflow_stage_manifest", fake_load_workflow_stage_manifest)
    return manifest


def assert_staged_payload_matches_manifest(
    payload: Mapping[str, object],
    manifest: object,
    *,
    workflow_id: str,
    stage_id: str,
) -> None:
    stage = manifest.stage_by_id(stage_id)
    staged_loading = payload[STAGED_LOADING_KEY]
    required_fields = tuple(stage.required_init_fields)

    assert tuple(field for field in payload if field != STAGED_LOADING_KEY) == required_fields
    assert set(payload) == set(required_fields) | {STAGED_LOADING_KEY}
    assert isinstance(staged_loading, dict)
    assert staged_loading["workflow_id"] == workflow_id
    assert staged_loading["stage_id"] == stage_id
    assert staged_loading == manifest.staged_loading_payload(stage_id)

    _assert_staged_loading_metadata_matches_stage(staged_loading, stage)


def _assert_staged_loading_metadata_matches_stage(staged_loading: Mapping[str, object], stage: object) -> None:
    metadata_expectations = {
        "required_init_fields": list(stage.required_init_fields),
        "mode_paths": list(getattr(stage, "mode_paths", ())),
        "loaded_authorities": list(getattr(stage, "loaded_authorities", ())),
        "allowed_tools": list(getattr(stage, "allowed_tools", ())),
        "writes_allowed": list(getattr(stage, "writes_allowed", ())),
        "produced_state": list(getattr(stage, "produced_state", ())),
        "next_stages": list(getattr(stage, "next_stages", ())),
        "checkpoints": list(getattr(stage, "checkpoints", ())),
    }
    eager_authorities = getattr(stage, "eager_authorities", None)
    if callable(eager_authorities):
        metadata_expectations["eager_authorities"] = list(eager_authorities())

    for key, expected in metadata_expectations.items():
        if key in staged_loading:
            assert staged_loading[key] == expected
