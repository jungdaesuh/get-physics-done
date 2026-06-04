"""Stage-authority assertions for the staged `plan-phase` workflow."""

from __future__ import annotations

from pathlib import Path

from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_anchor

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / "src" / "gpd" / "commands" / "plan-phase.md"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
PLAN_PHASE_STAGE_DIR = WORKFLOWS_DIR / "plan-phase"

STAGE_AUTHORITY_BY_ID = {
    "phase_bootstrap": "workflows/plan-phase/phase-bootstrap.md",
    "research_routing": "workflows/plan-phase/research-routing.md",
    "planner_authoring": "workflows/plan-phase/planner-authoring.md",
    "checker_revision": "workflows/plan-phase/checker-revision.md",
}


def _stage_text(stage_file: str) -> str:
    return (PLAN_PHASE_STAGE_DIR / stage_file).read_text(encoding="utf-8")


def test_plan_phase_manifest_uses_stage_authorities_without_root_eager_loads() -> None:
    manifest = load_workflow_stage_manifest("plan-phase")

    assert manifest.stage_ids() == tuple(STAGE_AUTHORITY_BY_ID)
    for stage_id, authority in STAGE_AUTHORITY_BY_ID.items():
        stage = manifest.stage(stage_id)
        assert stage.mode_paths == (authority,)
        assert stage.loaded_authorities[0] == authority
        assert "workflows/plan-phase.md" not in stage.mode_paths
        assert "workflows/plan-phase.md" not in stage.loaded_authorities
        assert (WORKFLOWS_DIR / authority.removeprefix("workflows/")).is_file()

    checker_conditionals = {
        conditional.when: conditional.authorities
        for conditional in manifest.stage("checker_revision").conditional_authorities
    }
    assert checker_conditionals["checker_return_routing"] == ("workflows/plan-phase/checker-return-routing.md",)
    assert checker_conditionals["blocked_plan_revision"] == ("workflows/plan-phase/blocked-plan-revision.md",)
    assert checker_conditionals["revision_planner_handoff"] == ("workflows/plan-phase/revision-planner-handoff.md",)
    assert checker_conditionals["planning_final_offer"] == ("workflows/plan-phase/planning-final-offer.md",)


def test_plan_phase_command_bootstraps_only_first_stage_authority() -> None:
    command = COMMAND_PATH.read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase/phase-bootstrap.md" in command
    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase.md" not in command
    assert_prompt_contracts(
        command,
        semantic_anchor(
            "plan-phase command delegates later stage loading",
            ("Later stage loading is manifest-owned", "do not duplicate the stage manifest here"),
        ),
    )


def test_plan_phase_bootstrap_defers_late_authorities() -> None:
    manifest = load_workflow_stage_manifest("plan-phase")
    bootstrap = manifest.stage("phase_bootstrap")
    bootstrap_text = _stage_text("phase-bootstrap.md")

    deferred = set(bootstrap.must_not_eager_load)
    for authority in (
        "workflows/plan-phase.md",
        "workflows/plan-phase/research-routing.md",
        "workflows/plan-phase/planner-authoring.md",
        "workflows/plan-phase/checker-revision.md",
        "references/orchestration/runtime-delegation-note.md",
        "templates/planner-subagent-prompt.md",
        "templates/plan-contract-schema.md",
        "templates/phase-prompt.md",
        "references/ui/ui-brand.md",
    ):
        assert authority in deferred

    for late_fragment in (
        "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md",
        "Planner prompt:",
        "Checker prompt:",
        "Revision prompt:",
        "Use `templates/planner-subagent-prompt.md` here as the stage-local planner template",
    ):
        assert late_fragment not in bootstrap_text

    assert bootstrap_text.index('<event name="phase_target_selected">') < bootstrap_text.index(
        "**Dirty worktree safety gate:**"
    )
    assert "Bootstrap proof invariant: `--skip-verify` never waives proof-bearing plan" in bootstrap_text
    assert_prompt_contracts(
        bootstrap_text,
        semantic_anchor(
            "plan-phase bootstrap omits late tangent decision model",
            "Required 4-way tangent decision model",
            mode="absent",
        ),
    )


def test_plan_phase_research_routing_defers_phase_file_content_to_authoring() -> None:
    manifest = load_workflow_stage_manifest("plan-phase")
    research_routing = manifest.stage("research_routing")
    planner_authoring = manifest.stage("planner_authoring")

    core_phase_file_content_fields = {
        "state_content",
        "roadmap_content",
        "requirements_content",
        "context_content",
        "research_content",
    }
    target_specific_phase_file_content_fields = {
        "experiment_design_content",
        "verification_content",
        "validation_content",
    }

    assert {field for field in research_routing.required_init_fields if field.endswith("_content")} == set()
    assert core_phase_file_content_fields.isdisjoint(research_routing.required_init_fields)
    assert target_specific_phase_file_content_fields.isdisjoint(research_routing.required_init_fields)
    assert core_phase_file_content_fields.issubset(planner_authoring.required_init_fields)
    assert target_specific_phase_file_content_fields.isdisjoint(planner_authoring.required_init_fields)
    assert "platform" in research_routing.required_init_fields


def test_plan_phase_checker_controls_start_after_research_routing() -> None:
    manifest = load_workflow_stage_manifest("plan-phase")
    checker_fields = {"checker_model", "plan_checker_enabled"}

    assert checker_fields.isdisjoint(manifest.stage("phase_bootstrap").required_init_fields)
    assert checker_fields.isdisjoint(manifest.stage("research_routing").required_init_fields)
    assert checker_fields.issubset(manifest.stage("planner_authoring").required_init_fields)
    assert checker_fields.issubset(manifest.stage("checker_revision").required_init_fields)


def test_research_routing_uses_routing_slice_until_route_or_handoff_requires_authoring() -> None:
    research = _stage_text("research-routing.md")

    routing_reload = 'INIT=$(gpd --raw init plan-phase "$PHASE" --stage research_routing)'
    authoring_reload = 'INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)'
    route_decision = '<event name="research_route_decision">'
    handoff_context = '<event name="research_handoff_context_needed">'

    assert routing_reload in research
    assert "INIT.staged_loading.field_access_instruction" in research
    assert research.index(routing_reload) < research.index(route_decision)
    assert research.index(route_decision) < research.index(handoff_context)
    assert research.index(handoff_context) < research.index(authoring_reload)
    assert "--stage planner_authoring" not in research[: research.index(handoff_context)]
    assert "reference_artifacts_content" not in research
    assert "protocol_bundle_context" not in research


def test_plan_phase_late_authorities_live_in_owning_stages() -> None:
    research = _stage_text("research-routing.md")
    planner = _stage_text("planner-authoring.md")
    checker = _stage_text("checker-revision.md")
    checker_return = _stage_text("checker-return-routing.md")
    blocked_revision = _stage_text("blocked-plan-revision.md")
    revision_handoff = _stage_text("revision-planner-handoff.md")
    final_offer = _stage_text("planning-final-offer.md")

    assert "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md" in research
    assert "Planner prompt:" in planner
    assert "## 9b. Handle Planner Checkpoint" in planner
    assert "Checker prompt:" in checker
    assert "## 11. Event: checker_return_routing" not in checker
    assert "Revision prompt:" not in checker
    assert "Structured final status convention" not in checker
    assert "## 11. Event: checker_return_routing" in checker_return
    assert "## 12. Event: blocked_plan_revision_branch" in blocked_revision
    assert "Revision prompt:" in revision_handoff
    assert "Structured final status convention" in final_offer
