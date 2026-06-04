"""Focused debugger vertical contract assertions."""

from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from tests.assertion_taxonomy_support import (
    FragmentMode,
    MatchMode,
    assert_prompt_contracts,
    machine_exact,
    semantic_anchor,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / "src/gpd/commands/debug.md"
WORKFLOW_PATH = REPO_ROOT / "src/gpd/specs/workflows/debug.md"
AGENT_PATH = REPO_ROOT / "src/gpd/agents/gpd-debugger.md"
AGENT_DELEGATION_REFERENCE = REPO_ROOT / "src/gpd/specs/references/orchestration/agent-delegation.md"
RUNTIME_DELEGATION_NOTE = REPO_ROOT / "src/gpd/specs/references/orchestration/runtime-delegation-note.md"


def _m(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(text, machine_exact(label, fragments, context=label))


def _f(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(text, machine_exact(label, fragments, mode=FragmentMode.ABSENT, context=label))


def _s(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(text, semantic_anchor(label, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label))


def test_debugger_vertical_spawn_contract_is_one_shot_and_file_producing() -> None:
    command = COMMAND_PATH.read_text(encoding="utf-8")
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    runtime_note = RUNTIME_DELEGATION_NOTE.read_text(encoding="utf-8")
    delegation = AGENT_DELEGATION_REFERENCE.read_text(encoding="utf-8")
    expanded_workflow = expand_at_includes(workflow, REPO_ROOT / "src/gpd", "/runtime/")

    _m(delegation, "debugger shared delegation anchors", "One-shot handoff", "Child artifact gate")
    _s(
        delegation,
        "debugger file-producing delegation policy",
        "Always set `readonly=false` for file-producing agents.",
    )
    _s(
        runtime_note,
        "debugger runtime delegation note",
        "Spawn a fresh subagent for the task below.",
        "one-shot handoff",
        "Always pass `readonly=false` for file-producing agents.",
    )

    assert workflow.count('subagent_type="gpd-debugger"') == 1
    assert workflow.count("readonly=false") == 1
    _s(
        expanded_workflow,
        "debugger expanded workflow handoff",
        "Spawn a fresh subagent for the task below.",
        "one-shot handoff",
        "Always pass `readonly=false` for file-producing agents.",
    )

    assert command.count('subagent_type="gpd-debugger"') == 1
    _m(
        command,
        "debugger command artifact handoff",
        "Debug session artifact: `GPD/debug/{slug}.md`",
        "read `{GPD_AGENTS_DIR}/gpd-debugger.md` for its role and instructions",
    )
    _f(
        command,
        "debugger command stale delegation fields",
        "readonly=false",
        'description="Debug {slug}"',
        'description="Continue debug {slug}"',
    )


def test_debugger_vertical_artifact_paths_keep_active_and_resolved_session_state_separate() -> None:
    command = COMMAND_PATH.read_text(encoding="utf-8")
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    agent = AGENT_PATH.read_text(encoding="utf-8")

    _m(command, "debugger command active session artifact", "Debug session artifact: `GPD/debug/{slug}.md`")
    _s(
        command,
        "debugger command session verification",
        "verifies the debug session artifact before treating a root cause as confirmed",
    )
    _m(workflow, "debugger workflow active session state", "GPD/debug/{slug}.md", "session_status: diagnosed")
    _m(
        agent,
        "debugger agent resolved session artifact",
        "files_written:\n    - GPD/debug/root-cause.md",
        "session_file: GPD/debug/root-cause.md",
        "**Troubleshooting Session:** GPD/debug/resolved/{slug}.md",
    )
    _s(
        agent,
        "debugger checkpoint one-shot state",
        "A checkpoint is a one-shot handoff for the current run.",
        "You are not resumed in the same run.",
    )


def test_debugger_vertical_seam_routes_on_typed_status_instead_of_headings() -> None:
    command = COMMAND_PATH.read_text(encoding="utf-8")
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    agent = AGENT_PATH.read_text(encoding="utf-8")

    _m(command, "debugger command typed status route", "typed `gpd_return.status` envelope")
    _s(command, "debugger command typed status route", "routes only on the typed `gpd_return.status` envelope")
    _m(
        workflow,
        "debugger workflow typed status routes",
        "gpd_return.status: completed",
        "gpd_return.status: checkpoint",
        "gpd_return.status: blocked",
        "session_status: diagnosed",
    )
    _s(
        workflow,
        "debugger workflow typed route authority",
        "Do not route on heading markers in the returned text",
        "typed `gpd_return` envelope and the session file instead",
    )
    _s(
        agent,
        "debugger agent checkpoint route",
        "A checkpoint is a one-shot handoff for the current run.",
        "The orchestrator presents the checkpoint to the user",
    )
