"""Prompt budget assertions for the `plan-phase` startup surface."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.workflow_staging import validate_workflow_stage_manifest_payload
from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_anchor
from tests.prompt_metrics_support import expanded_prompt_text, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"


def test_plan_phase_command_stays_thin_and_only_eagerly_loads_the_workflow() -> None:
    command_text = (COMMANDS_DIR / "plan-phase.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        COMMANDS_DIR / "plan-phase.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase/phase-bootstrap.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/ui/ui-brand.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/planner-subagent-prompt.md" not in command_text
    assert_prompt_contracts(
        command_text,
        semantic_anchor(
            "plan-phase command delegates later stage loading",
            ("Later stage loading is manifest-owned", "do not duplicate the stage manifest here"),
        ),
    )

    expanded = expanded_prompt_text(
        COMMANDS_DIR / "plan-phase.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    for late_fragment in (
        "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md",
        "Planner prompt:",
        "Checker prompt:",
        "Revision prompt:",
        "Use `templates/planner-subagent-prompt.md` here as the stage-local planner template",
    ):
        assert late_fragment not in expanded


def test_plan_phase_root_is_index_not_lifecycle_authority() -> None:
    root_text = (WORKFLOWS_DIR / "plan-phase.md").read_text(encoding="utf-8")
    manifest_payload = json.loads((WORKFLOWS_DIR / "plan-phase-stage-manifest.json").read_text(encoding="utf-8"))

    assert_prompt_contracts(
        root_text,
        semantic_anchor("plan-phase root is only the stage index", "This root is only the stage map."),
    )
    for stage in manifest_payload["stages"]:
        assert f"`{stage['id']}`" in root_text
        assert stage["mode_paths"][0] in root_text

    for stage_owned_fragment in (
        "Dirty worktree safety gate",
        "gpd --raw stage field-access",
        "Adaptive mode reuses research",
        "checker-disabled",
        "`--skip-verify`",
        "Required 4-way tangent decision model",
        "state/scope conflicts stop before research",
    ):
        assert stage_owned_fragment not in root_text


def test_plan_phase_workflow_defers_stage_authorities_until_the_manifest_stages_need_them() -> None:
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "plan-phase-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="plan-phase",
    )

    assert manifest.stage_ids() == (
        "phase_bootstrap",
        "research_routing",
        "planner_authoring",
        "checker_revision",
    )

    bootstrap = manifest.stages[0]
    research_routing = manifest.stages[1]
    planner_authoring = manifest.stages[2]
    checker_revision = manifest.stages[3]

    assert bootstrap.loaded_authorities == ("workflows/plan-phase/phase-bootstrap.md",)
    assert bootstrap.mode_paths == ("workflows/plan-phase/phase-bootstrap.md",)
    assert "workflows/plan-phase.md" in bootstrap.must_not_eager_load
    assert "workflows/plan-phase/research-routing.md" in bootstrap.must_not_eager_load
    assert "workflows/plan-phase/planner-authoring.md" in bootstrap.must_not_eager_load
    assert "workflows/plan-phase/checker-revision.md" in bootstrap.must_not_eager_load
    assert "references/orchestration/runtime-delegation-note.md" in bootstrap.must_not_eager_load
    assert "templates/plan-contract-schema.md" in bootstrap.must_not_eager_load
    assert "templates/planner-subagent-prompt.md" in bootstrap.must_not_eager_load
    assert "references/ui/ui-brand.md" in bootstrap.must_not_eager_load

    assert research_routing.loaded_authorities == (
        "workflows/plan-phase/research-routing.md",
        "references/orchestration/runtime-delegation-note.md",
    )
    assert planner_authoring.loaded_authorities == (
        "workflows/plan-phase/planner-authoring.md",
        "templates/planner-subagent-prompt.md",
    )
    assert checker_revision.loaded_authorities == ("workflows/plan-phase/checker-revision.md",)
    checker_conditionals = {
        conditional.when: conditional.authorities for conditional in checker_revision.conditional_authorities
    }
    assert checker_conditionals["revision_template_rendering"] == ("templates/planner-subagent-prompt.md",)
    assert checker_conditionals["checker_return_routing"] == ("workflows/plan-phase/checker-return-routing.md",)
    assert checker_conditionals["blocked_plan_revision"] == ("workflows/plan-phase/blocked-plan-revision.md",)
    assert checker_conditionals["revision_planner_handoff"] == ("workflows/plan-phase/revision-planner-handoff.md",)
    assert checker_conditionals["planning_final_offer"] == ("workflows/plan-phase/planning-final-offer.md",)
    assert "templates/planner-subagent-prompt.md" in checker_revision.must_not_eager_load
    assert "workflows/plan-phase/checker-return-routing.md" in checker_revision.must_not_eager_load
    assert "workflows/plan-phase/blocked-plan-revision.md" in checker_revision.must_not_eager_load
    assert "workflows/plan-phase/revision-planner-handoff.md" in checker_revision.must_not_eager_load
    assert "workflows/plan-phase/planning-final-offer.md" in checker_revision.must_not_eager_load
    assert "checker_model" not in bootstrap.required_init_fields
    assert "plan_checker_enabled" not in bootstrap.required_init_fields
    assert "checker_model" not in research_routing.required_init_fields
    assert "plan_checker_enabled" not in research_routing.required_init_fields
    assert "checker_model" in planner_authoring.required_init_fields
    assert "plan_checker_enabled" in planner_authoring.required_init_fields
    assert "checker_model" in checker_revision.required_init_fields
    assert "plan_checker_enabled" in checker_revision.required_init_fields
    assert "active_reference_context" in planner_authoring.required_init_fields
    assert "reference_artifact_files" in planner_authoring.required_init_fields
    assert "reference_artifacts_content" not in planner_authoring.required_init_fields
    assert "active_reference_context" not in checker_revision.required_init_fields
    assert "reference_artifact_files" in checker_revision.required_init_fields
    assert "reference_artifacts_content" not in checker_revision.required_init_fields
    assert {
        "state_content",
        "roadmap_content",
        "requirements_content",
        "context_content",
        "research_content",
    } <= set(planner_authoring.required_init_fields)
    assert {
        "experiment_design_content",
        "verification_content",
        "validation_content",
    }.isdisjoint(planner_authoring.required_init_fields)
    assert {
        "state_content",
        "roadmap_content",
        "requirements_content",
        "context_content",
        "research_content",
        "experiment_design_content",
        "verification_content",
        "validation_content",
    }.isdisjoint(checker_revision.required_init_fields)


def test_plan_phase_clean_non_autonomous_planning_reports_green_with_no_checkpoint() -> None:
    workflow_text = (WORKFLOWS_DIR / "plan-phase" / "planning-final-offer.md").read_text(encoding="utf-8")

    assert "Structured final status convention" in workflow_text
    assert "clean bounded non-autonomous planning" in workflow_text
    assert "has `checkpoint: none`" in workflow_text
    assert "report `status: green`" in workflow_text
    assert_prompt_contracts(
        workflow_text,
        semantic_anchor(
            "plan-phase clean status does not warn only because execution remains",
            "Execution remaining as the next command is not by itself a yellow condition.",
        ),
    )
