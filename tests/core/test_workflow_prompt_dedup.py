"""Assertions for planner workflow prompt deduplication."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.core.return_contract import validate_gpd_return_markdown
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.assertion_taxonomy_support import (
    assert_prompt_contracts,
    forbidden_duplicate,
    semantic_anchor,
    semantic_concept,
)
from tests.markdown_test_support import has_line_with_terms, tag_blocks, yaml_fence_bodies
from tests.workflow_authority_support import (
    STAGED_WORKFLOW_AUTHORITY_NAMES,
    workflow_authority_paths,
    workflow_authority_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"
RESULT_LOOKUP_WORKFLOWS = ("explain.md", "compare-experiment.md", "limiting-cases.md")


def _read(name: str) -> str:
    if name.removesuffix(".md") in STAGED_WORKFLOW_AUTHORITY_NAMES:
        return workflow_authority_text(WORKFLOWS_DIR, name)
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _read_authority(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def _expand(name: str) -> str:
    return expand_at_includes(_read(name), REPO_ROOT / "src/gpd", "/runtime/")


def _expand_authority(name: str) -> str:
    return expand_at_includes(_read_authority(name), REPO_ROOT / "src/gpd", "/runtime/")


def _between(text: str, start: str, end: str) -> str:
    _, marker, tail = text.partition(start)
    assert marker, f"missing marker: {start}"
    body, end_marker, _ = tail.partition(end)
    assert end_marker, f"missing marker: {end}"
    return body


def _assert_prompt_concept(
    text: str,
    label: str,
    *,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> None:
    assert_prompt_contracts(
        text,
        *semantic_concept(
            label,
            required=required or None,
            forbidden=forbidden or None,
        ),
    )


def test_installed_prompt_paths_do_not_reference_source_specs_segment() -> None:
    for directory in (WORKFLOWS_DIR, TEMPLATES_DIR, AGENTS_DIR, REFERENCES_DIR):
        for path in sorted(directory.rglob("*.md")):
            content = path.read_text(encoding="utf-8")
            assert "{GPD_INSTALL_DIR}/specs/" not in content, path.relative_to(REPO_ROOT)
            assert "src/gpd/specs/" not in content, path.relative_to(REPO_ROOT)


def test_shipped_templates_do_not_contain_runtime_installer_comments() -> None:
    for path in sorted(TEMPLATES_DIR.rglob("*.md")):
        content = path.read_text(encoding="utf-8")
        assert "installer adapts" not in content, path.relative_to(REPO_ROOT)
        assert not any(line.lstrip().startswith("#") and "<!--" in line for line in content.splitlines()), (
            path.relative_to(REPO_ROOT)
        )


def test_command_wrappers_do_not_duplicate_workflow_routing_boilerplate() -> None:
    forbidden_phrases = (
        "Routes to the",
        "workflow which handles:",
        "The workflow handles all logic including:",
    )
    for path in sorted(COMMANDS_DIR.rglob("*.md")):
        content = path.read_text(encoding="utf-8")
        for phrase in forbidden_phrases:
            assert phrase not in content, path.relative_to(REPO_ROOT)


def test_command_wrappers_do_not_repeat_self_workflow_reference_after_include() -> None:
    for path in sorted(COMMANDS_DIR.rglob("*.md")):
        command_slug = path.stem
        workflow_reference = re.compile(
            rf"(?<!@)\{{GPD_INSTALL_DIR\}}/workflows/{re.escape(command_slug)}\.md"
            rf"|@\{{GPD_INSTALL_DIR\}}/workflows/{re.escape(command_slug)}\.md"
        )
        content = path.read_text(encoding="utf-8")
        assert len(workflow_reference.findall(content)) <= 1, path.relative_to(REPO_ROOT)


def test_non_publication_staged_roots_are_indexes_not_authority_catalogs() -> None:
    allowed_root_references = {
        "new-project": {"@{GPD_INSTALL_DIR}/references/shared/interactive-choice-fallback.md"},
    }

    for workflow_id in ("autonomous", "plan-phase", "quick", "new-project", "verify-work"):
        root = (WORKFLOWS_DIR / f"{workflow_id}.md").read_text(encoding="utf-8")
        manifest = load_workflow_stage_manifest(workflow_id)

        assert "<canonical_references>" not in root
        assert "only the stage map" in root or "Do not load this index as a stage authority" in root
        for stage in manifest.stages:
            assert f"`{stage.id}`" in root
            assert stage.mode_paths[0] in root
            for authority in stage.loaded_authorities:
                if authority.startswith(f"workflows/{workflow_id}/"):
                    continue
                allowed = allowed_root_references.get(workflow_id, set())
                assert authority not in root or authority in allowed

        for wrapper_or_stage_owned_fragment in (
            "Full mode output",
            "Minimal mode output",
            "Typical quick tasks in physics research",
            "lifecycle-contract-gate",
            "gpd --raw init verify-work",
            "Load `templates/",
        ):
            assert wrapper_or_stage_owned_fragment not in root


def test_set_profile_updates_only_model_profile_through_config_cli() -> None:
    set_profile = _read("set-profile.md")

    assert 'PROFILE="$(printf' in set_profile
    assert 'gpd config set model_profile "$PROFILE"' in set_profile
    _assert_prompt_concept(set_profile, "set-profile stays action-oriented", required=("action workflow",))
    assert "preserving all other `GPD/config.json` keys" in set_profile
    assert "gpd --raw init progress --include state,config" not in set_profile
    assert "$ARGUMENTS.profile" not in set_profile
    assert '"model_profile": "$ARGUMENTS.profile"' not in set_profile
    assert "Write updated config back to `GPD/config.json`" not in set_profile


def test_planner_workflows_expand_the_shared_planner_template_once_per_route() -> None:
    plan_phase_raw = _read("plan-phase.md")
    quick_raw = _read("quick.md")
    verify_work_raw = _read_authority("verify-work")
    planner_agent_raw = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")

    quick = _expand("quick.md")
    verify_work = _expand_authority("verify-work")
    planner_template = (TEMPLATES_DIR / "planner-subagent-prompt.md").read_text(encoding="utf-8")

    assert "templates/planner-subagent-prompt.md" in plan_phase_raw
    assert "# Planner Subagent Prompt Template" not in plan_phase_raw
    assert "templates/planner-subagent-prompt.md" in verify_work_raw
    assert "# Planner Subagent Prompt Template" not in verify_work_raw

    assert plan_phase_raw.count("templates/planner-subagent-prompt.md") == 2
    assert verify_work_raw.count("templates/planner-subagent-prompt.md") == 2
    assert "templates/planner-subagent-prompt.md" not in quick_raw
    assert_prompt_contracts(
        planner_agent_raw,
        forbidden_duplicate(
            "planner defers the plan template instead of eagerly including it",
            "@{GPD_INSTALL_DIR}/templates/phase-prompt.md",
            max_count=0,
        ),
        forbidden_duplicate(
            "planner defers the plan schema instead of eagerly including it",
            "@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md",
            max_count=0,
        ),
        semantic_anchor(
            "planner keeps the late-loaded template and schema visible",
            (
                "{GPD_INSTALL_DIR}/templates/phase-prompt.md",
                "{GPD_INSTALL_DIR}/templates/plan-contract-schema.md",
                "before plan frontmatter",
            ),
        ),
    )

    assert planner_template.count("## Standard Planning Template") == 1
    assert planner_template.count("## Revision Template") == 1
    assert planner_template.count("@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md") == 1
    assert "project_contract_gate.authoritative" in quick
    assert "# Planner Subagent Prompt Template" not in verify_work
    assert "## Standard Planning Template" not in verify_work
    assert "## Revision Template" not in verify_work
    assert "project_contract_load_info" in verify_work
    assert "project_contract_load_info" in verify_work_raw

    assert "project_contract_gate.authoritative" in planner_template
    plan_phase_prompt = _between(plan_phase_raw, "Planner prompt:", "task(")
    assert "project_contract_gate.authoritative" not in plan_phase_prompt
    assert "{GPD_INSTALL_DIR}/templates/phase-prompt.md" not in plan_phase_prompt
    assert "{GPD_INSTALL_DIR}/templates/plan-contract-schema.md" not in plan_phase_prompt
    assert "<physics_planning_requirements>" not in plan_phase_prompt
    assert "<downstream_consumer>" not in plan_phase_prompt
    assert "<quality_gate>" not in plan_phase_prompt


def test_planner_workflows_do_not_embed_the_removed_long_policy_blocks() -> None:
    plan_phase = _read("plan-phase.md")
    quick = _read("quick.md")
    verify_work = _read_authority("verify-work")

    for removed_phrase in (
        "Each plan has a complete contract block (claims, deliverables, acceptance tests, forbidden proxies, uncertainty markers, and `references[]` whenever grounding is not already explicit elsewhere in the contract)",
        "Non-scoping plans keep `claims[]`, `deliverables[]`, `acceptance_tests[]`, and `forbidden_proxies[]` non-empty.",
        "Include `references[]` only when the plan relies on external grounding",
        "Keep the full canonical frontmatter, including `wave`, `depends_on`, `files_modified`, `interactive`, `conventions`, and `contract`.",
        "If the downstream fix plan will need specialized tooling or any other machine-checkable hard validation requirement, surface it in PLAN frontmatter `tool_requirements` before drafting task prose.",
        "If the revised fix plan still needs specialized tooling or any other machine-checkable hard validation requirement, keep it in PLAN frontmatter `tool_requirements` before rewriting task prose.",
    ):
        assert removed_phrase not in plan_phase
        assert removed_phrase not in verify_work

    assert has_line_with_terms(plan_phase, "## Standard Planning Template", "filled_prompt")
    assert has_line_with_terms(plan_phase, "## Revision Template", "revision_prompt")
    assert has_line_with_terms(plan_phase, "template-owned", "contract gates")
    assert not has_line_with_terms(
        plan_phase,
        "shared planner template",
        "phase template",
        "templates/plan-contract-schema.md",
    )
    assert not has_line_with_terms(
        quick,
        "before planning",
        "shared planner template",
        "canonical contract schema",
        casefold=True,
    )
    assert not has_line_with_terms(
        verify_work,
        "shared planner template",
        "canonical planning",
        "contract gate",
        casefold=True,
    )
    assert not has_line_with_terms(
        verify_work,
        "shared planner template",
        "canonical planning",
        "revision policy",
        casefold=True,
    )


def test_lifecycle_workflow_prompts_reference_every_real_stage_id() -> None:
    for workflow_id, workflow_name in (
        ("plan-phase", "plan-phase.md"),
        ("execute-phase", "execute-phase.md"),
    ):
        workflow = _read_authority(workflow_id) if workflow_id == "execute-phase" else _read(workflow_name)
        manifest = load_workflow_stage_manifest(workflow_id)

        missing = [
            stage_id
            for stage_id in manifest.stage_ids()
            if f"--stage {stage_id}" not in workflow and f"load_execute_phase_stage {stage_id}" not in workflow
        ]

        assert missing == []


def test_planner_agent_does_not_duplicate_canonical_plan_template_blocks() -> None:
    planner_agent = (AGENTS_DIR / "gpd-planner.md").read_text(encoding="utf-8")
    phase_template = (TEMPLATES_DIR / "phase-prompt.md").read_text(encoding="utf-8")
    gap_policy = (REFERENCES_DIR / "planning" / "planner-gap-and-revision-policy.md").read_text(encoding="utf-8")

    canonical_only_markers = (
        "# Phase Plan Prompt Template",
        "## File Template",
        "phase: XX-name",
        "type: execute | tdd",
        "## Required Frontmatter",
        "## Light Plan Variant",
        "## Contract Shape Classifier",
    )

    for marker in canonical_only_markers:
        assert marker in phase_template
        assert marker not in planner_agent

    assert "## PLAN.md Source Of Truth" in planner_agent
    assert "## Gap-Specific Contract Fields" in gap_policy


def test_new_project_workflow_keeps_contract_preservation_rules_single_sourced() -> None:
    scope_intake = (WORKFLOWS_DIR / "new-project" / "scope-intake.md").read_text(encoding="utf-8")
    scope_approval = (WORKFLOWS_DIR / "new-project" / "scope-approval.md").read_text(encoding="utf-8")
    contract_schema = expand_at_includes(
        (TEMPLATES_DIR / "project-contract-schema.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd/specs",
        "/runtime/",
    )

    for fragment in (
        "`project_contract`",
        "`project_contract_load_info`",
        "`project_contract_validation`",
        "preserve that state",
        "fresh work or a continuation",
        "visible-but-blocked contract",
    ):
        assert fragment in scope_intake
    assert has_line_with_terms(scope_approval, "approval", "contract", "schema")
    assert not has_line_with_terms(
        scope_intake + scope_approval, "preserve any init-surfaced", "fresh work", "continuation"
    )
    for fragment in (
        "`schema_version` must be the integer `1`",
        "`references[]`",
        "`must_surface` is a boolean scalar",
    ):
        assert fragment in contract_schema
    for fragment in ("`context_intake`", "`uncertainty_markers`", "`project_contract`"):
        assert fragment in scope_approval
    assert not has_line_with_terms(contract_schema, "schema_version", "references[].must_surface", "not a synonym")


def test_new_project_workflow_references_late_artifact_templates_without_inlining_skeletons() -> None:
    new_project = _read("new-project.md")
    project_template = (TEMPLATES_DIR / "project.md").read_text(encoding="utf-8")
    state_template = (TEMPLATES_DIR / "state.md").read_text(encoding="utf-8")

    assert "templates/project.md" in new_project
    assert "templates/state.md" in new_project
    assert "@{GPD_INSTALL_DIR}/templates/project.md" not in new_project
    assert "@{GPD_INSTALL_DIR}/templates/state.md" not in new_project

    assert "# {project_title}" in project_template
    assert "## Scoping Contract Summary" in project_template
    assert "## Current Position" in state_template
    assert has_line_with_terms(state_template, "Current Phase Name", "[Phase name]")

    assert new_project.count("## Scoping Contract Summary") <= 1
    for removed_project_skeleton_marker in (
        "# [Extracted Research Title]",
        "[Extracted research question]",
        "- **User-stated observables:** [Specific quantity, curve, figure, or smoking-gun signal]",
        "| Parameter | Symbol | Regime | Notes |",
        "_Last updated: [today's date] after initialization (minimal)_",
    ):
        assert removed_project_skeleton_marker not in new_project

    for removed_state_skeleton_marker in (
        "# Research State",
        "See: GPD/PROJECT.md (updated [today's date])",
        "**Current Phase:** 1",
        "**Current Phase Name:** [Phase 1 name]",
        "**Stopped at:** Project initialized (minimal)",
    ):
        assert removed_state_skeleton_marker not in new_project


def test_notation_coordinator_references_subfield_defaults_without_inlining_table() -> None:
    notation_coordinator = (AGENTS_DIR / "gpd-notation-coordinator.md").read_text(encoding="utf-8")
    subfield_defaults = (REFERENCES_DIR / "conventions" / "subfield-convention-defaults.md").read_text(encoding="utf-8")
    canonical_reference = "{GPD_INSTALL_DIR}/references/conventions/subfield-convention-defaults.md"

    assert canonical_reference in notation_coordinator
    assert f"@{canonical_reference}" not in notation_coordinator
    assert has_line_with_terms(notation_coordinator, "subfield defaults reference", "matching subfield")
    assert has_line_with_terms(notation_coordinator, "CONVENTIONS.md", "default choices")

    assert "## Convention Defaults by Subfield" in subfield_defaults
    assert "## Convention Defaults by Subfield" not in notation_coordinator
    for canonical_row in (
        "| Units | Natural: ℏ = c = 1 | Universal in particle physics |",
        "| Metric signature | (+,−,−,−) (West Coast) | Peskin & Schroeder, Weinberg |",
        "| Brillouin zone | First BZ; high-symmetry points (Γ, X, M, K) | Setyawan & Curtarolo notation |",
    ):
        assert canonical_row in subfield_defaults
        assert canonical_row not in notation_coordinator


def test_planner_workflows_keep_tangent_policy_single_sourced() -> None:
    plan_phase = _read("plan-phase.md")

    assert plan_phase.count("Tangent invariant:") == 1
    assert plan_phase.count("gpd:tangent") == 1
    assert plan_phase.count("gpd:branch-hypothesis") == 2
    assert not has_line_with_terms(plan_phase, "required", "4-way", "tangent", "decision model", casefold=True)


def test_context_pressure_default_threshold_table_is_single_sourced() -> None:
    infra = (REPO_ROOT / "src/gpd/specs/references/orchestration/agent-infrastructure.md").read_text(encoding="utf-8")
    thresholds = (REPO_ROOT / "src/gpd/specs/references/orchestration/context-pressure-thresholds.md").read_text(
        encoding="utf-8"
    )

    assert infra.count("| GREEN | < 40% | Proceed normally |") == 1
    assert "| GREEN | < 40% | Proceed normally |" not in thresholds
    assert has_line_with_terms(thresholds, "per-agent overrides", "calibration notes")


def test_result_lookup_policy_is_single_sourced_for_high_level_workflows() -> None:
    policy = (REFERENCES_DIR / "results" / "result-lookup-policy.md").read_text(encoding="utf-8")

    assert policy.count("# Result Lookup Policy") == 1
    assert policy.count("gpd result search") == 2
    assert policy.count("gpd result show") == 1
    assert policy.count("gpd result deps") == 1
    assert policy.count("gpd result downstream") == 1
    assert has_line_with_terms(policy, "gpd query search", "SUMMARY/frontmatter")

    for workflow_name in RESULT_LOOKUP_WORKFLOWS:
        raw = _read(workflow_name)
        expanded = _expand(workflow_name)

        assert raw.count("references/results/result-lookup-policy.md") == 1, workflow_name
        assert expanded.count("references/results/result-lookup-policy.md") == 1, workflow_name
        assert "# Result Lookup Policy" not in expanded, workflow_name

        for command in (
            "gpd result search",
            "gpd result show",
            "gpd result deps",
            "gpd result downstream",
        ):
            assert command not in raw, workflow_name
            assert command not in expanded, workflow_name
        assert "direct stored-result view before" not in raw, workflow_name
        assert not has_line_with_terms(raw, "reverse dependency tree", "direct", "transitive", casefold=True), (
            workflow_name
        )


def test_state_portability_uses_canonical_continuation_prose() -> None:
    state_portability = (REPO_ROOT / "src/gpd/specs/references/orchestration/state-portability.md").read_text(
        encoding="utf-8"
    )

    assert has_line_with_terms(state_portability, "state.json.continuation", "wins first")
    assert has_line_with_terms(state_portability, "gpd --raw resume", "top-level list")
    assert not has_line_with_terms(state_portability, "derived head", "advisory continuity")


def test_execute_phase_runtime_delegation_rules_are_single_sourced() -> None:
    execute_phase = _read_authority("execute-phase")

    assert execute_phase.count("references/orchestration/runtime-delegation-note.md") == 1
    assert has_line_with_terms(execute_phase, "runtime-neutral", "handoff gates")
    assert not has_line_with_terms(execute_phase, "shared note", "empty-model omission", casefold=True)
    assert not has_line_with_terms(
        execute_phase,
        "empty-model omission",
        "readonly=false",
        "artifact-gated completion",
        casefold=True,
    )
    assert execute_phase.count("runtime delegation convention") <= 8


def test_runtime_delegation_note_is_loaded_once_per_workflow() -> None:
    include = "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md"
    workflows_using_short_references = {
        "audit-milestone.md",
        "explain.md",
        "new-milestone.md",
        "quick.md",
    }
    workflows_using_manifest_conditional_references = {
        "write-paper.md": "{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md",
    }

    for path in sorted(WORKFLOWS_DIR.glob("*.md")):
        authority_paths = workflow_authority_paths(WORKFLOWS_DIR, path.stem)
        for authority_path in authority_paths:
            text = authority_path.read_text(encoding="utf-8")
            assert text.count(include) <= 1, authority_path.relative_to(WORKFLOWS_DIR)
        if path.name in workflows_using_short_references:
            text = _read_authority(path.stem)
            expected_count = 2 if path.name == "quick.md" else 1
            assert text.count(include) == expected_count, path.name
            assert has_line_with_terms(text, "runtime delegation convention", "loaded above"), path.name
        if path.name in workflows_using_manifest_conditional_references:
            text = _read_authority(path.stem)
            assert include not in text, path.name
            assert workflows_using_manifest_conditional_references[path.name] in text, path.name

    new_project_authority_paths = workflow_authority_paths(WORKFLOWS_DIR, "new-project")
    new_project_task_stage_names = {
        authority_path.name
        for authority_path in new_project_authority_paths
        if include in authority_path.read_text(encoding="utf-8")
    }
    assert new_project_task_stage_names == {
        "literature-survey.md",
        "roadmap-authoring.md",
        "conventions-handoff.md",
    }


def test_experiment_designer_uses_external_ising_example_as_single_source() -> None:
    designer = (AGENTS_DIR / "gpd-experiment-designer.md").read_text(encoding="utf-8")
    example = (REPO_ROOT / "src/gpd/specs/references/examples/ising-experiment-design-example.md").read_text(
        encoding="utf-8"
    )

    for inline_fragment in (
        "## Worked Example: 2D Ising Model Phase Diagram via Monte Carlo",
        "#### Worked Examples of Physics-Informed Grids",
        "log-spaced: t = [",
        "T_above = T_c * (1 + t)",
        "T_below = T_c * (1 - t)",
        "Response Surface Methodology",
        "Bayesian Optimization for Expensive Simulations",
    ):
        assert inline_fragment not in designer

    for lazy_reference in (
        "{GPD_INSTALL_DIR}/references/examples/ising-experiment-design-example.md",
        "{GPD_INSTALL_DIR}/references/protocols/monte-carlo.md",
        "{GPD_INSTALL_DIR}/references/protocols/statistical-inference.md",
        "{GPD_INSTALL_DIR}/references/protocols/numerical-computation.md",
        "{GPD_INSTALL_DIR}/references/protocols/reproducibility.md",
        "{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md",
    ):
        assert lazy_reference in designer
        assert f"@{lazy_reference}" not in designer

    assert "This gives 15 critical-region temperatures" in example
    assert "This gives 14 temperatures" not in example


def test_numeric_context_budget_guidance_is_single_sourced() -> None:
    context_budget = (REFERENCES_DIR / "orchestration" / "context-budget.md").read_text(encoding="utf-8")
    infra = (REFERENCES_DIR / "orchestration" / "agent-infrastructure.md").read_text(encoding="utf-8")
    meta = (REFERENCES_DIR / "orchestration" / "meta-orchestration.md").read_text(encoding="utf-8")
    execute_phase = _read_authority("execute-phase")

    assert "## Phase-Class Budget Targets" in context_budget
    assert "Summary aggregation heuristic" in context_budget
    assert "estimated_tokens = plan_count * tasks_per_plan * 6000" not in infra
    assert not has_line_with_terms(
        meta,
        "Phase Type",
        "Orchestrator Budget",
        "Agent Budget",
        "Total per Phase",
    )
    assert has_line_with_terms(meta, "strategic routing", "budget table")
    assert "references/orchestration/context-budget.md` as the canonical numeric source" in infra
    assert "references/orchestration/context-budget.md" in execute_phase


def test_executor_uses_plain_paths_for_inline_references_and_at_includes_only_for_real_includes() -> None:
    executor = (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")

    inline_at_lines = [
        line
        for line in executor.splitlines()
        if "@{GPD_INSTALL_DIR}" in line and not line.strip().startswith("@{GPD_INSTALL_DIR}/")
    ]
    assert inline_at_lines == []
    assert "`{GPD_INSTALL_DIR}/references/orchestration/checkpoints.md`" in executor
    assert "`{GPD_INSTALL_DIR}/templates/summary.md`" in executor


def test_agent_specific_return_examples_include_complete_valid_base_envelope_fields() -> None:
    agent_examples = (
        "gpd-experiment-designer.md",
        "gpd-notation-coordinator.md",
        "gpd-project-researcher.md",
        "gpd-phase-researcher.md",
        "gpd-plan-checker.md",
        "gpd-research-mapper.md",
        "gpd-research-synthesizer.md",
        "gpd-roadmapper.md",
        "gpd-paper-writer.md",
        "gpd-verifier.md",
        "gpd-executor.md",
        "gpd-referee.md",
        "gpd-bibliographer.md",
        "gpd-debugger.md",
        "gpd-literature-reviewer.md",
        "gpd-planner.md",
    )

    required_fields = ("status:", "files_written:", "issues:", "next_actions:")

    for agent_name in agent_examples:
        text = (AGENTS_DIR / agent_name).read_text(encoding="utf-8")
        gpd_blocks = [block for block in yaml_fence_bodies(text) if "gpd_return:" in block]
        assert gpd_blocks, agent_name
        for yaml_block in gpd_blocks:
            assert all(field in yaml_block for field in required_fields), (agent_name, yaml_block)
            result = validate_gpd_return_markdown(f"```yaml\n{yaml_block}\n```")
            assert result.passed, (agent_name, result.errors, yaml_block)
        assert "The four base fields (`status`, `files_written`, `issues`, `next_actions`)" not in text, agent_name


def test_bibliographer_delegates_return_boilerplate_to_agent_infrastructure() -> None:
    text = (AGENTS_DIR / "gpd-bibliographer.md").read_text(encoding="utf-8")

    assert has_line_with_terms(text, "agent-infrastructure.md", "return-envelope")
    assert "status: completed" in text
    assert "files_written:\n    - paper/references.bib\n    - GPD/references-status.json" in text

    for removed_phrase in (
        "Checkpoint ownership is orchestrator-side",
        "Runtime delegation rule:",
        "The headings in this section are presentation only.",
        "Use `gpd_return.status: checkpoint` as the control surface.",
        "Return `gpd_return.status: completed`, `checkpoint`, `blocked`, or `failed`.",
    ):
        assert removed_phrase not in text


def test_research_agents_delegate_file_templates_to_canonical_templates() -> None:
    project_researcher = (AGENTS_DIR / "gpd-project-researcher.md").read_text(encoding="utf-8")
    phase_researcher = (AGENTS_DIR / "gpd-phase-researcher.md").read_text(encoding="utf-8")
    synthesizer = (AGENTS_DIR / "gpd-research-synthesizer.md").read_text(encoding="utf-8")
    summary_template = (TEMPLATES_DIR / "research-project" / "SUMMARY.md").read_text(encoding="utf-8")

    for template_name in (
        "SUMMARY.md",
        "PRIOR-WORK.md",
        "METHODS.md",
        "COMPUTATIONAL.md",
        "PITFALLS.md",
    ):
        assert f"{{GPD_INSTALL_DIR}}/templates/research-project/{template_name}" in project_researcher

    assert has_line_with_terms(project_researcher, "project-literature skeletons", "canonical template")
    assert "# Research Summary: [Project Name]" not in project_researcher
    assert "### Governing Theory" not in project_researcher
    assert "## FEASIBILITY.md (feasibility mode only)" not in project_researcher

    assert "{GPD_INSTALL_DIR}/templates/research.md" in phase_researcher
    assert has_line_with_terms(phase_researcher, "templates/research.md", "RESEARCH.md")
    assert "# Phase [X]: [Name] - Research" not in phase_researcher
    assert "### Package / Framework Reuse Decision" in phase_researcher

    assert "{GPD_INSTALL_DIR}/templates/research-project/SUMMARY.md" in synthesizer
    assert "# Research Summary Template" in summary_template
    assert has_line_with_terms(synthesizer, "canonical template", "synthesizer-specific")
    assert not has_line_with_terms(synthesizer, "Research Summary", "[Project Title]")
    assert not has_line_with_terms(synthesizer, "Aggregated references", "research files", "organized by topic")


def test_roadmapper_keeps_project_type_template_catalog_single_sourced() -> None:
    roadmapper = (AGENTS_DIR / "gpd-roadmapper.md").read_text(encoding="utf-8")
    project_type_templates = sorted((TEMPLATES_DIR / "project-types").glob("*.md"))
    downstream_consumer = tag_blocks(roadmapper, "downstream_consumer")[0]
    phase_identification = tag_blocks(roadmapper, "phase_identification")[0]

    assert project_type_templates
    assert "{GPD_INSTALL_DIR}/templates/project-types/" in downstream_consumer
    assert "Use the matching file under `{GPD_INSTALL_DIR}/templates/project-types/`" in downstream_consumer
    assert "qft-calculation.md" not in downstream_consumer
    assert "stat-mech-simulation.md" not in downstream_consumer
    assert "qft-calculation.md" in phase_identification
