"""Focused assertions for coordinator-routing contracts."""

from __future__ import annotations

from pathlib import Path

from tests.lifecycle_contract_test_support import (
    artifact_paths,
    assert_machine_contract,
    assert_semantic_contract,
    child_gate_from_text,
)
from tests.markdown_test_support import has_line_with_terms, tag_blocks
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _read(name: str) -> str:
    if name in {"new-project.md", "new-milestone.md"}:
        return workflow_authority_text(WORKFLOWS_DIR, name)
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def test_debug_workflow_routes_on_typed_status_and_file_backed_diagnosis() -> None:
    workflow = _read("debug.md")

    assert_machine_contract(
        workflow,
        "debug typed status and session-file machine anchors",
        "gpd_return.status: completed",
        "gpd_return.status: checkpoint",
        "gpd_return.status: blocked",
        "GPD/debug/{slug}.md",
        "session_status: diagnosed",
    )
    assert_semantic_contract(
        workflow,
        "debug session file owns debug status lifecycle",
        "debug session file",
        "debug-session",
        "status",
        "lifecycle",
        "does not use",
        "session_status",
    )
    assert_semantic_contract(
        workflow,
        "debug routes typed returns instead of headings",
        "heading",
        "route",
        "typed",
        "gpd_return",
        "session file",
    )
    assert_semantic_contract(
        workflow,
        "debug checkpoint continuation ownership",
        "checkpoint",
        "present",
        "fresh continuation",
    )
    assert "## ROOT CAUSE FOUND" not in workflow
    assert "## INVESTIGATION INCONCLUSIVE" not in workflow


def test_new_project_and_new_milestone_route_roadmaps_on_typed_status() -> None:
    new_project = _read("new-project.md")
    new_milestone = _read("new-milestone.md")
    project_gate = child_gate_from_text(new_project, "project_roadmapper")
    milestone_gate = child_gate_from_text(new_milestone, "milestone_roadmapper")

    for workflow in (new_project, new_milestone):
        assert_machine_contract(
            workflow,
            "roadmapper status route and validator anchors",
            "gpd_return.status: completed",
            "failure_route:",
            "--require-status completed --require-files-written",
            "GPD/REQUIREMENTS.md",
        )
        assert_semantic_contract(workflow, "roadmapper child gate before acceptance", "child gate", "before")

    assert project_gate.id == "project_roadmapper"
    assert project_gate.role == "gpd-roadmapper"
    assert project_gate.return_profile == "roadmapper"
    assert project_gate.required_status == "completed"
    assert artifact_paths(project_gate) == ("GPD/ROADMAP.md", "GPD/STATE.md", "GPD/REQUIREMENTS.md")
    assert project_gate.allowed_roots == ("GPD",)
    assert project_gate.applicator.command == "shared_state_policy=direct for this legacy init handoff"
    assert project_gate.applicator.require_passed_true is False
    assert any(
        "--require-status completed --require-files-written" in validator for validator in project_gate.validators
    )
    assert_semantic_contract(
        new_project,
        "new-project roadmapper path is not invented from prose",
        "alternate",
        "roadmap path",
    )
    assert_semantic_contract(
        new_project,
        "new-project headings are not roadmap authority",
        "headings",
        "ROADMAP CREATED",
        "ROADMAP BLOCKED",
        "not authority",
    )

    assert milestone_gate.id == "milestone_roadmapper"
    assert milestone_gate.role == "gpd-roadmapper"
    assert milestone_gate.return_profile == "roadmapper"
    assert milestone_gate.required_status == "completed"
    assert artifact_paths(milestone_gate) == ("GPD/ROADMAP.md", "GPD/REQUIREMENTS.md")
    assert milestone_gate.allowed_roots == ("GPD",)
    assert milestone_gate.applicator.command == (
        "main workflow applies accepted state changes with gpd state patch / gpd state add-decision after the artifact gate"
    )
    assert milestone_gate.applicator.require_passed_true is False
    assert any(
        "--require-status completed --require-files-written" in validator for validator in milestone_gate.validators
    )
    assert "shared_state_policy: return_only" in new_milestone
    assert_semantic_contract(
        new_milestone,
        "new-milestone state edits require main workflow artifact gate",
        "direct roadmapper edit",
        "GPD/STATE.md",
        "not success proof",
    )
    contract_blocks = tag_blocks(new_milestone, "contract_context")
    assert len(contract_blocks) == 1
    assert_machine_contract(
        contract_blocks[0],
        "new-milestone project contract context placeholders",
        "Project contract gate: {project_contract_gate}",
        "Project contract load info: {project_contract_load_info}",
        "Project contract validation: {project_contract_validation}",
    )
    assert_semantic_contract(
        " ".join(milestone_gate.failure_route.values()),
        "new-milestone roadmapper blocked route uses continuation boundary",
        "request",
        "fresh continuation",
    )


def test_parameter_sweep_balanced_mode_is_not_unconditionally_paused() -> None:
    workflow = _read("parameter-sweep.md")

    assert_machine_contract(
        workflow,
        "parameter sweep autonomy mode anchors",
        "autonomy=supervised",
        "autonomy=balanced",
    )
    assert has_line_with_terms(workflow, "autonomy=supervised", "ask", "generating plans")
    assert_semantic_contract(
        workflow,
        "parameter sweep balanced mode pauses only for conditional gates",
        "autonomy=balanced",
        "pause only",
        "material scope",
        "user approval",
    )
    assert has_line_with_terms(workflow, "approval", "only then pause")
    assert "Proceed? (y/n)" not in workflow


def test_audit_milestone_consumes_a_typed_consistency_checker_return_without_routing_convention_ownership() -> None:
    workflow = _read("audit-milestone.md")
    checker = (AGENTS_DIR / "gpd-consistency-checker.md").read_text(encoding="utf-8")

    assert workflow.count('subagent_type="gpd-consistency-checker"') == 1
    assert "gpd-notation-coordinator" not in workflow
    assert_semantic_contract(
        workflow,
        "audit milestone surfaces checker report or skipped marker",
        "consistency checker",
        "report",
        "parameter mismatches",
        "skipped",
        "agent failed",
    )
    assert_semantic_contract(
        workflow,
        "audit milestone checker spawn failure is skipped not rerouted",
        "consistency checker agent",
        "fails to spawn",
        "skipped",
        "gpd:validate-conventions",
    )
    assert_machine_contract(
        checker,
        "consistency checker return artifact anchors",
        "status: completed",
        "files_written:\n    - GPD/phases/03-conventions/CONSISTENCY-CHECK.md",
    )
    assert_semantic_contract(
        checker,
        "consistency checker one-shot return lifecycle",
        "one-shot",
        "inspect",
        "write",
        "return",
        "checkpoint",
    )
    assert_semantic_contract(
        checker,
        "consistency checker headings are presentation only",
        "headings",
        "presentation only",
        "gpd_return.status",
    )
