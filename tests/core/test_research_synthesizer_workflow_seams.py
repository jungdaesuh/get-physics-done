"""Workflow seam assertions for the research-synthesizer vertical."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from gpd.core.child_handoff import ChildGateTuple, child_gate_tuple_from_payload
from tests.core.test_spawn_contracts import _assert_spawn_contract, _task_blocks_by_agent
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


def test_new_project_synthesizer_seam_routes_on_typed_returns_and_rejects_stale_summary_files() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "new-project")
    path = WORKFLOWS_DIR / "new-project.md"
    synth_tasks = _task_blocks_by_agent(path, "gpd-research-synthesizer")
    assert len(synth_tasks) == 1
    synth = synth_tasks[0]
    gate = _child_gate(workflow, "literature_synthesizer")

    assert workflow.index('id: "literature_scouts"') < synth.start
    assert synth.start < workflow.index('id: "literature_synthesizer"')
    for research_file in (
        "GPD/PROJECT.md",
        "GPD/config.json",
        "GPD/literature/PRIOR-WORK.md",
        "GPD/literature/METHODS.md",
        "GPD/literature/COMPUTATIONAL.md",
        "GPD/literature/PITFALLS.md",
        "GPD/literature/SUMMARY.md (if re-synthesizing an existing survey)",
    ):
        assert research_file in synth.text
    _assert_spawn_contract(synth, ("GPD/literature/SUMMARY.md",))
    assert gate.role == "gpd-research-synthesizer"
    assert gate.return_profile == "synthesizer"
    assert _artifact_paths(gate) == ("GPD/literature/SUMMARY.md",)
    assert gate.allowed_roots == ("GPD/literature",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$SYNTHESIZER_HANDOFF_STARTED_AT"
    assert any("gpd validate handoff-artifacts - --expected GPD/literature/SUMMARY.md" in validator for validator in gate.validators)
    assert any("--require-status completed --require-files-written" in validator for validator in gate.validators)
    assert any("stop synth path" in route for route in gate.failure_route.values())
    assert "surface the blocker" in workflow
    assert "creating a fallback" in workflow
    assert "summary in the main context" in workflow


def test_new_milestone_synthesizer_seam_keeps_child_contract_visible_and_task_local() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "new-milestone")

    assert "Route `checkpoint`, `blocked`, or final `failed` through\n`references/orchestration/child-artifact-gate.md`" in workflow
    assert "After all 4 complete and required artifacts are present, spawn synthesizer:" in workflow
    assert "task(prompt=\"First, read {GPD_AGENTS_DIR}/gpd-research-synthesizer.md for your role and instructions." in workflow
    assert "<files_to_read>" in workflow
    assert "- GPD/literature/PRIOR-WORK.md" in workflow
    assert "- GPD/literature/METHODS.md" in workflow
    assert "- GPD/literature/COMPUTATIONAL.md" in workflow
    assert "- GPD/literature/PITFALLS.md" in workflow
    assert "Write to: GPD/literature/SUMMARY.md" in workflow
    assert "Use template: {GPD_INSTALL_DIR}/templates/research-project/SUMMARY.md" in workflow
    assert "<spawn_contract>" in workflow
    assert "allowed_paths:" in workflow
    assert "    - GPD/literature/SUMMARY.md" in workflow
    assert "shared_state_policy: return_only" in workflow
    assert "This synthesizer contract is task-local. Do not reuse survey write scopes or widen the summary handoff." in workflow
    assert "Synthesizer child gate:" in workflow
    assert "gpd validate handoff-artifacts - --expected GPD/literature/SUMMARY.md" in workflow
    assert "Do not display or commit `SUMMARY.md`, create it in the\nmain context" in workflow
