"""Focused plan-phase spawned handoff contract assertions."""

from __future__ import annotations

import re

from gpd.core.child_handoff import ChildGateTuple, parse_child_gate_markdown
from tests.core.test_spawn_contracts import (
    WORKFLOWS_DIR,
    _assert_spawn_contract,
    _find_single_task,
    _task_blocks_by_agent,
)

_YAML_BLOCK_RE = re.compile(r"```ya?ml\n(?P<body>.*?)\n```", re.DOTALL)


def _child_gates_by_id(text: str) -> dict[str, ChildGateTuple]:
    gates: dict[str, ChildGateTuple] = {}
    for match in _YAML_BLOCK_RE.finditer(text):
        body = match.group("body")
        if "child_gate:" not in body:
            continue
        gate = parse_child_gate_markdown(f"```yaml\n{body}\n```")
        gates[gate.id] = gate
    return gates


def test_plan_phase_planner_and_checker_handoffs_carry_inline_spawn_contracts() -> None:
    research_path = WORKFLOWS_DIR / "plan-phase" / "research-routing.md"
    planner_path = WORKFLOWS_DIR / "plan-phase" / "planner-authoring.md"
    checker_path = WORKFLOWS_DIR / "plan-phase" / "checker-revision.md"
    revision_handoff_path = WORKFLOWS_DIR / "plan-phase" / "revision-planner-handoff.md"
    workflow = "\n\n".join(
        path.read_text(encoding="utf-8") for path in (research_path, planner_path, checker_path, revision_handoff_path)
    )
    planner_tasks = _task_blocks_by_agent(planner_path, "gpd-planner") + _task_blocks_by_agent(
        revision_handoff_path,
        "gpd-planner",
    )
    assert len(planner_tasks) >= 2
    for task in planner_tasks:
        _assert_spawn_contract(
            task,
            ("{phase_dir}/*-PLAN.md",),
            expected_write_paths=("{phase_dir}/*-PLAN.md",),
        )
        assert "artifact_gate:" not in task.text

    gates = _child_gates_by_id(workflow)
    researcher = gates["phase_researcher_context_refresh"]
    assert researcher.role == "gpd-phase-researcher"
    assert [artifact.path for artifact in researcher.expected_artifacts] == ["${PHASE_DIR}/${PHASE_NUMBER}-RESEARCH.md"]
    assert researcher.allowed_roots == ("${PHASE_DIR}",)
    assert researcher.freshness is not None
    assert researcher.freshness.marker == "$RESEARCH_HANDOFF_STARTED_AT"
    assert researcher.status_route == {
        "checkpoint": "fresh researcher continuation after user response",
        "blocked": "ask for context, skip, or abort",
        "failed": "ask for context, skip, or abort",
    }

    for gate_id in ("planner_initial_plan", "planner_revision"):
        gate = gates[gate_id]
        assert gate.role == "gpd-planner"
        assert [(artifact.path, artifact.kind) for artifact in gate.expected_artifacts] == [
            ("${PHASE_DIR}/*-PLAN.md", "glob")
        ]
        assert gate.allowed_roots == ("${PHASE_DIR}",)
        assert gate.freshness is not None
        assert gate.freshness.marker == "$PLANNER_HANDOFF_STARTED_AT"
        assert "gpd validate plan-contract <each fresh plan>" in gate.validators
        assert "gpd validate plan-preflight <each fresh plan>" in gate.validators
        assert "checkpoint" in gate.status_route
        assert set(gate.status_route) == {"checkpoint", "blocked", "failed"}

    assert "child artifact gate: apply" not in workflow.lower()

    checker = _find_single_task(checker_path, "gpd-plan-checker")
    _assert_spawn_contract(checker, ())
    assert "mode: read_only" in checker.text
    assert "artifact_gate:" not in checker.text
    checker_gate = gates["plan_checker_review"]
    assert checker_gate.role == "gpd-plan-checker"
    assert checker_gate.expected_artifacts == ()
    assert checker_gate.allowed_roots == ()
    assert "files_written: []" in checker_gate.validators
    assert "approved/blocked plan-ID reconciliation against FRESH_PLAN_FILES" in checker_gate.validators
    assert checker_gate.status_route == {
        "checkpoint": "record partial approval then revision loop or fresh continuation",
        "blocked": "revision loop or manual review",
        "failed": "revision loop or manual review",
    }
