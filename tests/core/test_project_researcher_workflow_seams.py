"""Workflow seam assertions for the project-researcher vertical."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from gpd.core.child_handoff import ChildGateTuple, child_gate_tuple_from_payload
from tests.assertion_taxonomy_support import assert_prompt_contracts, fragment_count, machine_exact, semantic_concept
from tests.core.test_spawn_contracts import _assert_spawn_contract, _extract_output_paths, _task_blocks_by_agent
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
_YAML_BLOCK_RE = re.compile(r"```ya?ml\n(?P<body>.*?)\n```", re.DOTALL)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _child_gate(source: str, gate_id: str) -> ChildGateTuple:
    for match in _YAML_BLOCK_RE.finditer(source):
        payload = yaml.safe_load(match.group("body"))
        if not isinstance(payload, dict):
            continue
        child_gate = payload.get("child_gate")
        if isinstance(child_gate, dict) and child_gate.get("id") == gate_id:
            return child_gate_tuple_from_payload(payload)
    raise AssertionError(f"missing child gate {gate_id}")


def _artifact_paths(gate: ChildGateTuple) -> tuple[str, ...]:
    return tuple(artifact.path for artifact in gate.expected_artifacts)


def test_new_project_project_researcher_scouts_route_on_typed_return_and_reject_stale_results() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "new-project")
    path = WORKFLOWS_DIR / "new-project.md"
    tasks = _task_blocks_by_agent(path, "gpd-project-researcher")
    gate = _child_gate(workflow, "literature_scouts")

    expected = (
        "GPD/literature/PRIOR-WORK.md",
        "GPD/literature/METHODS.md",
        "GPD/literature/COMPUTATIONAL.md",
        "GPD/literature/PITFALLS.md",
    )
    assert len(tasks) == 4
    outputs = tuple(output for task in tasks for output in _extract_output_paths(task))
    assert set(outputs) == set(expected)
    assert len(outputs) == len(set(outputs))
    for task in tasks:
        task_outputs = tuple(_extract_output_paths(task))
        assert len(task_outputs) == 1
        _assert_spawn_contract(task, task_outputs)
        assert "shared_state_policy: return_only" in task.text
    assert gate.role == "gpd-project-researcher"
    assert gate.return_profile == "researcher"
    assert _artifact_paths(gate) == expected
    assert gate.allowed_roots == ("GPD/literature",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$SCOUT_HANDOFF_STARTED_AT per scout"
    assert any("--require-status completed --require-files-written" in validator for validator in gate.validators)
    assert any("stop this scout path" in route for route in gate.failure_route.values())
    assert_prompt_contracts(
        workflow,
        *semantic_concept(
            "project researcher scouts reject partial literature surveys",
            required=("Do not proceed with a partial literature survey",),
        ),
    )
    assert "references/orchestration/child-artifact-gate.md" in workflow


def test_new_milestone_project_researcher_scouts_require_fresh_continuations_and_stale_file_rejection() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "new-milestone")

    assert_prompt_contracts(
        workflow,
        fragment_count(
            "new milestone scout common structure appears once",
            "Common structure for all 4 scouts:",
            expected_count=1,
        ),
    )
    assert 'id: "milestone_literature_scouts"' in workflow
    assert 'role: "gpd-project-researcher"' in workflow
    assert "GPD/literature/PRIOR-WORK.md" in workflow
    assert "GPD/literature/METHODS.md" in workflow
    assert "GPD/literature/COMPUTATIONAL.md" in workflow
    assert "GPD/literature/PITFALLS.md" in workflow
    assert_prompt_contracts(
        workflow,
        machine_exact(
            "new milestone scout failure route",
            'failure_route: "retry missing scout once | repair prompt once | stop survey path',
        ),
        *semantic_concept(
            "new milestone scout fresh completion gate",
            required=("Do not count a\nscout as complete until the tuple passes.",),
        ),
    )
    assert "Route `checkpoint`, `blocked`, or final `failed` through" in workflow
    assert "references/orchestration/continuation-boundary.md" in workflow
