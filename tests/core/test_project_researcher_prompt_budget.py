"""Prompt budget assertions for the `gpd-project-researcher` agent surface."""

from __future__ import annotations

from pathlib import Path

from gpd import registry
from tests.agent_policy_test_support import assert_agent_role_kit_policy, assert_agent_role_kit_section
from tests.assertion_taxonomy_support import (
    FragmentMode,
    MatchMode,
    assert_prompt_contracts,
    machine_exact,
    semantic_anchor,
    semantic_concept,
)
from tests.prompt_metrics_support import expanded_prompt_text, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"


def test_gpd_project_researcher_prompt_stays_within_expected_budget_and_keeps_one_shot_checkpoint_language() -> None:
    path = AGENTS_DIR / "gpd-project-researcher.md"
    source = path.read_text(encoding="utf-8")
    metrics = measure_prompt_surface(path, src_root=SOURCE_ROOT, path_prefix=PATH_PREFIX)
    expanded = expanded_prompt_text(path, src_root=SOURCE_ROOT, path_prefix=PATH_PREFIX)

    assert metrics.raw_include_count == 0
    assert metrics.expanded_line_count < 500
    assert metrics.expanded_char_count < 50_000

    assert_prompt_contracts(
        source,
        machine_exact(
            "project researcher role-kit and return markers",
            (
                "role_kits:",
                "  - fresh-continuation",
                "{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md",
                "fresh-continuation",
                "status: completed",
                "files_written:\n    - GPD/literature/SUMMARY.md",
                "confidence: HIGH",
            ),
        ),
        semantic_anchor(
            "project researcher checkpoint stop semantics",
            "return the typed checkpoint and stop",
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        *semantic_concept(
            "project researcher orchestration boundary",
            required="Structured return provided to orchestrator",
            forbidden=(
                "Do not wait inside the same spawned run.",
                "Authority: use the frontmatter-derived Agent Requirements block",
            ),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        machine_exact(
            "project researcher avoids eager shared includes",
            (
                "@{GPD_INSTALL_DIR}/references/shared/shared-protocols.md",
                "@{GPD_INSTALL_DIR}/references/research/researcher-shared.md",
            ),
            mode=FragmentMode.ABSENT,
        ),
    )

    agent = registry.get_agent("gpd-project-researcher")
    generated_prompt = agent.system_prompt
    assert_agent_role_kit_policy(
        agent,
        (
            "status-routing",
            "fresh-continuation",
            "files-written-freshness",
            "context-pressure",
        ),
    )
    assert_agent_role_kit_section(agent)
    assert_prompt_contracts(
        generated_prompt,
        machine_exact(
            "project researcher generated authority fields",
            (
                "artifact_write_authority: scoped_write",
                "shared_state_authority: return_only",
                "### Fresh Continuation (`fresh-continuation`)",
            ),
        ),
    )

    for phrase in (
        "wait for user confirmation",
        "ask the user then continue",
        "pause here for approval",
        "wait inside the same run",
    ):
        assert phrase not in expanded
