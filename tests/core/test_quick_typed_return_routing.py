"""Focused assertions for quick workflow typed return routing."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.core.child_handoff import ChildGateTuple, parse_child_gate_markdown
from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, semantic_anchor
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
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


def test_quick_workflow_routes_on_typed_gpd_return_and_applies_child_returns() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "quick")
    gates = _child_gates_by_id(workflow)
    planner_gate = gates["quick_planner_plan"]
    executor_gate = gates["quick_executor_summary"]

    assert planner_gate.required_status == "completed"
    assert executor_gate.required_status == "completed"
    assert_prompt_contracts(
        workflow,
        semantic_anchor(
            "quick executor completion uses tuple and applicator",
            ("quick_executor_summary", "tuple", "applicator", "decide completion"),
            match=MatchMode.CASEFOLD_NORMALIZED,
            context="quick executor completion gate",
        ),
    )
    assert "loads staged quick init" in workflow
    assert "staged_loading" in workflow
    assert "reference_context" in workflow
    assert "default small-task path" in workflow
    assert 'gpd --raw init quick "$DESCRIPTION" --stage reference_context' in workflow
    assert "workflows/quick/task-bootstrap.md" in workflow
    assert "workflows/quick/task-authoring.md" in workflow
    assert "tool_requirements" in workflow
    assert "gpd validate plan-preflight" in workflow
    assert "gpd apply-return-updates" in workflow
    assert "gpd state add-decision" in workflow
    assert "gpd state update" in workflow
    assert "gpd commit" in workflow
    assert "references/orchestration/child-artifact-gate.md" in workflow
    assert "references/orchestration/continuation-boundary.md" in workflow
    assert planner_gate.role == "gpd-planner"
    assert [artifact.path for artifact in planner_gate.expected_artifacts] == ["${QUICK_DIR}/${next_num}-PLAN.md"]
    assert planner_gate.allowed_roots == ("${QUICK_DIR}",)
    assert planner_gate.freshness is not None
    assert planner_gate.freshness.marker == "$QUICK_PLANNER_HANDOFF_STARTED_AT"
    assert planner_gate.status_route == {
        "checkpoint": "fresh planner continuation after user response",
        "blocked": "retry planner, main-context planning, or abort",
        "failed": "retry planner, main-context planning, or abort",
    }
    assert executor_gate.role == "gpd-executor"
    assert [artifact.path for artifact in executor_gate.expected_artifacts] == ["${QUICK_DIR}/${next_num}-SUMMARY.md"]
    assert executor_gate.allowed_roots == ("${QUICK_DIR}",)
    assert executor_gate.freshness is not None
    assert executor_gate.freshness.marker == "$QUICK_EXECUTOR_HANDOFF_STARTED_AT"
    assert executor_gate.applicator.command == 'gpd apply-return-updates "${QUICK_DIR}/${next_num}-SUMMARY.md"'
    assert executor_gate.applicator.require_passed_true is True
    assert executor_gate.status_route == {
        "checkpoint": "fresh executor continuation after user response",
        "blocked": "retry executor, main-context execution, or abort",
        "failed": "retry executor, main-context execution, or abort",
    }
    assert_prompt_contracts(
        workflow,
        semantic_anchor(
            "quick child-gate fallback separates recovery evidence from success",
            ("recovery evidence only", "explicit main-context fallback with its own return"),
        ),
    )
