"""Assertions for one-shot delegation cleanup."""

from __future__ import annotations

from pathlib import Path

from gpd import registry
from tests.agent_policy_test_support import assert_agent_role_kit_policy, assert_agent_role_kit_section
from tests.assertion_taxonomy_support import (
    MatchMode,
    assert_prompt_contracts,
    machine_exact,
    semantic_anchor,
    semantic_concept,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _read_agent(name: str) -> str:
    return (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def test_notation_coordinator_requires_checkpoint_and_fresh_continuation_for_write_approval() -> None:
    content = _read_agent("gpd-notation-coordinator")

    assert_prompt_contracts(
        content,
        machine_exact(
            "notation coordinator continuation path and empty write list",
            ("references/orchestration/continuation-boundary.md", "files_written: []"),
        ),
        *semantic_concept(
            "notation coordinator checkpoint stop semantics",
            required="Return a checkpoint with the options and stop",
            forbidden=("Wait for user decision", "Wait for user decision before proceeding"),
        ),
    )


def test_debugger_uses_one_shot_checkpoint_handoff_instead_of_in_run_waiting() -> None:
    content = _read_agent("gpd-debugger")

    assert_prompt_contracts(
        content,
        machine_exact(
            "debugger continuation path and heading",
            ("references/orchestration/continuation-boundary.md", "### Fresh Continuation"),
        ),
        *semantic_concept(
            "debugger one-shot checkpoint semantics",
            required=("one-shot handoff", "You are not resumed in the same run."),
            forbidden="active sessions",
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )


def test_roadmapper_makes_checkpoint_revision_flow_explicit() -> None:
    content = _read_agent("gpd-roadmapper")
    agent = registry.get_agent("gpd-roadmapper")

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
        content,
        *semantic_concept(
            "roadmapper checkpoint revision flow",
            required=(
                "revision prompt",
                "re-invokes the roadmapper for any follow-up write pass",
                "fresh-continuation",
            ),
            forbidden="same-run wait",
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )


def test_experiment_designer_supervised_mode_mentions_fresh_continuation() -> None:
    content = _read_agent("gpd-experiment-designer")
    agent = registry.get_agent("gpd-experiment-designer")

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
        content,
        machine_exact(
            "experiment designer checkpoint handoff and empty files list",
            ("{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md", "files_written: []"),
        ),
        semantic_anchor(
            "experiment designer fresh-continuation approval flow",
            (
                "fresh continuation",
                "Return a checkpoint with the cost estimate for user approval before writing",
                "spawns a fresh continuation for the write pass",
            ),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        semantic_anchor(
            "experiment designer checkpoint does not claim unwritten design",
            ("status: checkpoint", "no `design_file` until the continuation pass writes the artifact"),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        semantic_anchor(
            "experiment designer design_file stays coupled to files_written",
            (
                "design_file",
                "must be returned in `files_written`",
                "must match the EXPERIMENT-DESIGN.md path in `files_written`",
            ),
        ),
    )
