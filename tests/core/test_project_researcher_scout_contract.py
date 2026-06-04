"""Assertions for the new-project scout contract."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from gpd.core.child_handoff import ChildGateTuple, child_gate_tuple_from_payload
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
_YAML_BLOCK_RE = re.compile(r"```ya?ml\n(?P<body>.*?)\n```", re.DOTALL)


def _read_workflow(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def _read_agent(name: str) -> str:
    return (AGENTS_DIR / name).read_text(encoding="utf-8")


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


def test_project_researcher_uses_staged_mode_and_one_shot_checkpoint_language() -> None:
    source = _read_agent("gpd-project-researcher.md")

    assert "role_kits:" in source
    assert "  - fresh-continuation" in source
    assert "return the typed checkpoint and stop" in source
    assert "{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md" in source
    assert "@{GPD_INSTALL_DIR}/references/shared/shared-protocols.md" not in source
    assert "@{GPD_INSTALL_DIR}/references/research/researcher-shared.md" not in source
    assert "Do not wait inside the same spawned run." not in source
    assert "Do not query config or reread init JSON inside this agent." in source
    assert "Write only the assigned `write_scope.allowed_paths`" in source
    assert "Execute all 4 parallel research threads independently" not in source


def test_new_project_scout_returns_route_on_typed_status_and_files_written() -> None:
    workflow = _read_workflow("new-project")
    gate = _child_gate(workflow, "literature_scouts")

    assert "Use the staged `research_mode` from `LITERATURE_SURVEY_INIT`" in workflow
    assert "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md" in workflow
    assert gate.role == "gpd-project-researcher"
    assert gate.return_profile == "researcher"
    assert gate.required_status == "completed"
    assert _artifact_paths(gate) == (
        "GPD/literature/PRIOR-WORK.md",
        "GPD/literature/METHODS.md",
        "GPD/literature/COMPUTATIONAL.md",
        "GPD/literature/PITFALLS.md",
    )
    assert gate.allowed_roots == ("GPD/literature",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$SCOUT_HANDOFF_STARTED_AT per scout"
    assert gate.freshness.require_mtime_at_or_after_marker is True
    assert any("GPD/literature/{FILE}" in validator for validator in gate.validators)
    assert any("--require-status completed --require-files-written" in validator for validator in gate.validators)
    assert "references/orchestration/child-artifact-gate.md" in workflow
    assert "references/orchestration/continuation-boundary.md" in workflow
    assert "Do not proceed with a partial literature survey" in workflow
    assert "synthesize from incomplete scout output" in workflow


def test_new_project_synthesizer_return_stays_typed_and_file_backed() -> None:
    workflow = _read_workflow("new-project")
    gate = _child_gate(workflow, "literature_synthesizer")

    assert gate.role == "gpd-research-synthesizer"
    assert gate.return_profile == "synthesizer"
    assert gate.required_status == "completed"
    assert _artifact_paths(gate) == ("GPD/literature/SUMMARY.md",)
    assert gate.allowed_roots == ("GPD/literature",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$SYNTHESIZER_HANDOFF_STARTED_AT"
    assert any("GPD/literature/SUMMARY.md" in validator for validator in gate.validators)
    assert any("--require-status completed --require-files-written" in validator for validator in gate.validators)
    assert any("stop synth path" in route for route in gate.failure_route.values())
    assert "creating a fallback" in workflow
    assert "summary in the main context" in workflow
