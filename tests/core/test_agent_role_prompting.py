"""Prompt assertions for agent taxonomy and execution routing."""

from __future__ import annotations

import re
from pathlib import Path

from gpd import registry
from gpd.core.agent_role_kits import get_agent_role_kit, role_kit_authority_paths
from gpd.core.model_visible_text import (
    INTERNAL_AGENT_BOUNDARY_POINTER,
    READ_ONLY_INTERNAL_AGENT_BOUNDARY_POINTER,
)
from tests.agent_policy_test_support import (
    assert_agent_role_kit_policy,
    assert_agent_role_kit_section,
    expected_agent_policy_subset,
)
from tests.assertion_taxonomy_support import (
    FragmentMode,
    MatchMode,
    assert_prompt_contracts,
    machine_exact,
    semantic_anchor,
    semantic_concept,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
REFERENCES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "references"

PHASE5_TARGET_AGENT_ROLE_KITS = {
    "gpd-research-mapper": (
        "status-routing",
        "fresh-continuation",
        "files-written-freshness",
        "context-pressure",
    ),
    "gpd-notation-coordinator": (
        "status-routing",
        "fresh-continuation",
        "files-written-freshness",
        "context-pressure",
    ),
    "gpd-planner": (
        "status-routing",
        "fresh-continuation",
        "files-written-freshness",
        "context-pressure",
    ),
    "gpd-verifier": (
        "status-routing",
        "fresh-continuation",
        "files-written-freshness",
    ),
    "gpd-plan-checker": (
        "status-routing",
        "fresh-continuation",
        "read-only-return",
        "context-pressure",
    ),
}


def _read_agent(name: str) -> str:
    return (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _agent_body(name: str) -> str:
    source = _read_agent(name)
    if source.startswith("---"):
        return source.split("---", 2)[2]
    return source


def _tag_blocks(text: str, tag: str) -> list[str]:
    return re.findall(rf"<{tag}>\n?(.*?)\n?</{tag}>", text, flags=re.DOTALL)


def _fenced_yaml_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:yaml|yml)\n(.*?)```", text, flags=re.DOTALL)


def test_phase5_target_agents_declare_expected_role_kits() -> None:
    for agent_name, expected_role_kits in PHASE5_TARGET_AGENT_ROLE_KITS.items():
        agent = registry.get_agent(agent_name)

        assert_agent_role_kit_policy(agent, expected_role_kits)
        assert_agent_role_kit_section(agent, before="## Scientific Rigor Guardrails")


def test_phase5_target_agents_delegate_generic_lifecycle_rules_to_role_kits() -> None:
    for agent_name, expected_role_kits in PHASE5_TARGET_AGENT_ROLE_KITS.items():
        body = _agent_body(agent_name)
        duplicated_rules = [
            f"{role_kit_id}: {rule}"
            for role_kit_id in expected_role_kits
            for rule in get_agent_role_kit(role_kit_id).rules
            if rule in body
        ]

        assert "## Agent Role Kits" not in body, agent_name
        assert duplicated_rules == [], agent_name


def test_all_role_kit_agents_use_generated_policy_and_section() -> None:
    agent_names = [
        agent_name for agent_name in sorted(registry.list_agents()) if registry.get_agent(agent_name).role_kits
    ]

    assert agent_names
    for agent_name in agent_names:
        agent = registry.get_agent(agent_name)
        policy = expected_agent_policy_subset(agent)
        body = _agent_body(agent_name)
        duplicated_rules = [
            rule for role_kit_id in agent.role_kits for rule in get_agent_role_kit(role_kit_id).rules if rule in body
        ]

        assert policy["role_kits"] == list(agent.role_kits), agent_name
        assert policy["role_kit_authorities"] == list(role_kit_authority_paths(agent.role_kits)), agent_name
        assert_agent_role_kit_section(agent, before="## Scientific Rigor Guardrails")
        assert "## Agent Role Kits" not in body, agent_name
        assert duplicated_rules == [], agent_name


def test_executor_prompt_describes_default_writable_scoped_task_role() -> None:
    executor = _read_agent("gpd-executor")

    assert_prompt_contracts(
        executor,
        semantic_anchor(
            "executor writable scoped-task identity",
            (
                "default writable implementation agent",
                "Scoped-task mode",
                "the prompt itself is the execution contract",
            ),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        machine_exact(
            "executor specialist routing names",
            ("route it to gpd-paper-writer", "route it to gpd-notation-coordinator"),
        ),
    )


def test_planner_debugger_and_explainer_route_work_to_specialized_agents() -> None:
    planner = _read_agent("gpd-planner")
    debugger = _read_agent("gpd-debugger")
    explainer = _read_agent("gpd-explainer")

    assert_prompt_contracts(
        planner,
        machine_exact(
            "planner specialist routing names",
            ("go to `gpd-executor`", "goes to `gpd-paper-writer`", "goes to `gpd-notation-coordinator`"),
        ),
    )
    assert_prompt_contracts(
        debugger,
        machine_exact(
            "debugger specialist routing names",
            (
                "hand it to `gpd-executor`",
                "hand it to `gpd-paper-writer`",
                "hand it to `gpd-notation-coordinator`",
            ),
        ),
    )
    assert_prompt_contracts(
        explainer,
        semantic_anchor(
            "explainer is not writable default",
            "not the default writable implementation agent",
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        machine_exact(
            "explainer specialist routing names",
            (
                "route that work to `gpd-executor`",
                "route it to `gpd-paper-writer`",
                "route it to `gpd-notation-coordinator`",
            ),
        ),
    )


def test_public_worker_prompts_identify_writable_production_surface() -> None:
    executor = _read_agent("gpd-executor")
    debugger = _read_agent("gpd-debugger")
    paper_writer = _read_agent("gpd-paper-writer")

    assert_prompt_contracts(
        executor,
        semantic_anchor(
            "executor public writable production boundary",
            ("Public production boundary:", "writable production agent", "bounded implementation work"),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )
    assert_prompt_contracts(
        debugger,
        semantic_anchor(
            "debugger public writable production boundary",
            (
                "Public production boundary:",
                "writable production agent",
                "discrepancy investigation",
                "On demand only:",
                "shared protocols",
                "agent infrastructure",
            ),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        machine_exact(
            "debugger shared references stay on demand",
            (
                "@{GPD_INSTALL_DIR}/references/shared/shared-protocols.md",
                "@{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md",
            ),
            mode=FragmentMode.ABSENT,
        ),
    )
    assert_prompt_contracts(
        paper_writer,
        semantic_anchor(
            "paper writer public writable production boundary",
            ("Public production boundary:", "writable production agent", "manuscript sections"),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )


def test_internal_agents_explicitly_identify_internal_specialist_surface() -> None:
    for name in registry.list_agents():
        agent = registry.get_agent(name)
        if agent.surface != "internal":
            continue
        content = _read_agent(name)
        expected = (
            READ_ONLY_INTERNAL_AGENT_BOUNDARY_POINTER
            if agent.artifact_write_authority == "read_only"
            else INTERNAL_AGENT_BOUNDARY_POINTER
        )
        assert content.count(expected) == 1, name
        assert f"surface: {agent.surface}" in agent.system_prompt, name


def test_source_agent_surface_boilerplate_does_not_conflict_with_frontmatter() -> None:
    for name in registry.list_agents():
        agent = registry.get_agent(name)
        content = _read_agent(name)
        assert_prompt_contracts(
            content,
            semantic_anchor(
                "legacy source surface boilerplate absent",
                "Agent surface:",
                mode=FragmentMode.ABSENT,
                context=name,
            ),
        )
        if agent.surface == "internal":
            assert_prompt_contracts(
                content,
                semantic_anchor(
                    "internal agents avoid public production boundary",
                    "Public production boundary:",
                    mode=FragmentMode.ABSENT,
                    context=name,
                ),
            )
        if agent.surface == "public":
            assert_prompt_contracts(
                content,
                semantic_anchor(
                    "public agents avoid internal boundary prose",
                    (INTERNAL_AGENT_BOUNDARY_POINTER, READ_ONLY_INTERNAL_AGENT_BOUNDARY_POINTER),
                    mode=FragmentMode.ABSENT,
                    context=name,
                ),
            )


def test_consistency_checker_stays_one_shot_and_does_not_claim_resolution_work() -> None:
    source = _read_agent("gpd-consistency-checker")

    assert_prompt_contracts(
        source,
        semantic_anchor(
            "consistency checker one-shot semantics",
            ("one-shot handoff", "inspect once, write once, return once"),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        semantic_anchor(
            "consistency checker report is not return authority",
            ("Do not embed", "gpd_return", "CONSISTENCY-CHECK.md", "separate runtime return"),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        machine_exact(
            "consistency checker return fields",
            (
                "Use `status: checkpoint`",
                "status: completed",
                "files_written:\n    - GPD/phases/03-conventions/CONSISTENCY-CHECK.md",
            ),
        ),
    )
    assert INTERNAL_AGENT_BOUNDARY_POINTER in source
    assert_prompt_contracts(
        source,
        *semantic_concept(
            "consistency checker resolution boundary",
            required="Do not claim ownership of code fixes, commits, convention-authoring, or pattern-library updates.",
            forbidden="Create it from the template",
        ),
        machine_exact("consistency checker does not author patterns", "gpd pattern add", mode=FragmentMode.ABSENT),
    )


def test_executor_checkpoint_frequency_guidance_is_consistent() -> None:
    source = _read_agent("gpd-executor")

    assert_prompt_contracts(
        source,
        machine_exact(
            "executor checkpoint frequency guidance",
            (
                "**checkpoint:human-verify (90% of checkpoints)**",
                "**checkpoint:decision (9% of checkpoints)**",
                "**checkpoint:human-action (1% -- rare)**",
            ),
        ),
        machine_exact(
            "executor stale checkpoint frequency guidance",
            ("**checkpoint:decision (25%)**", "**checkpoint:human-action (5%)**"),
            mode=FragmentMode.ABSENT,
        ),
    )


def test_roadmapper_shallow_mode_keeps_contract_identity_visible() -> None:
    source = _read_agent("gpd-roadmapper")

    assert_prompt_contracts(
        source,
        machine_exact("roadmapper shallow mode flag", "shallow_mode=true"),
        *semantic_concept(
            "roadmapper shallow-mode contract anchors",
            required=(
                "objective IDs",
                "decisive contract items",
                "required anchors/baselines",
                "forbidden proxies",
                "Phase 1 only under `shallow_mode=true`",
                "Phase 2+ stubs defer detailed success criteria",
            ),
            forbidden=(
                "Phases 2+ may defer contract-coverage detail",
                "only their one-line Goal and phase title",
            ),
        ),
    )


def test_public_agent_prompts_avoid_legacy_ai_assistant_role_labels() -> None:
    for name in registry.list_agents():
        agent = registry.get_agent(name)
        if agent.surface != "public":
            continue
        content = _read_agent(name)
        assert_prompt_contracts(
            content,
            semantic_anchor("legacy AI assistant role label absent", "AI assistant", mode=FragmentMode.ABSENT),
        )


def test_planner_backtracks_guidance_is_capped_before_injection() -> None:
    source = _read_agent("gpd-planner")
    execution_procedure = (REFERENCES_DIR / "planning" / "planner-execution-procedure.md").read_text(encoding="utf-8")

    assert_prompt_contracts(
        execution_procedure,
        machine_exact("planner backtrack artifacts", ("GPD/BACKTRACKS.md", "patterns_consulted:", "backtracks: []")),
        semantic_anchor(
            "planner backtrack source selection",
            ("same planning stage", "overlapping technique", "last 10 matching rows", "cap the rendered block"),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )
    assert_prompt_contracts(
        source,
        machine_exact(
            "planner prompt avoids inline backtrack shell loop",
            (
                "for f in GPD/INSIGHTS.md GPD/ERROR-PATTERNS.md GPD/BACKTRACKS.md; do",
                "tail -n 30 GPD/BACKTRACKS.md",
            ),
            mode=FragmentMode.ABSENT,
        ),
    )


def test_owned_agent_structured_return_examples_include_complete_base_fields() -> None:
    required_fields = ("status:", "files_written:", "issues:", "next_actions:")

    for agent_name in ("gpd-planner", "gpd-executor", "gpd-experiment-designer"):
        structured_blocks = _tag_blocks(_read_agent(agent_name), "structured_returns")
        assert structured_blocks, agent_name

        for structured_block in structured_blocks:
            for yaml_block in _fenced_yaml_blocks(structured_block):
                if "gpd_return:" not in yaml_block:
                    continue
                has_explicit_base_fields = all(field in yaml_block for field in required_fields)
                assert has_explicit_base_fields, (agent_name, yaml_block)
