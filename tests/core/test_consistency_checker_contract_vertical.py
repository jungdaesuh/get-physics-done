"""Focused consistency-checker vertical contract assertions."""

from __future__ import annotations

from pathlib import Path

from gpd import registry
from gpd.adapters.install_utils import expand_at_includes
from tests.lifecycle_contract_test_support import assert_machine_contract, assert_semantic_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _read_workflow(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _read_agent(name: str) -> str:
    return (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def test_validate_conventions_seam_is_one_shot_and_artifact_gated_before_notation_resolution() -> None:
    workflow = _read_workflow("validate-conventions.md")
    expanded_workflow = expand_at_includes(workflow, REPO_ROOT / "src/gpd", "/runtime/")

    assert_semantic_contract(
        expanded_workflow,
        "expanded validate-conventions delegation note",
        "fresh subagent",
        "one-shot handoff",
        "child wait",
        "child-artifact-gate.md",
        "readonly=false",
    )
    assert_semantic_contract(
        workflow,
        "validate-conventions wrapper delegates policy to checker",
        "thin wrapper",
        "gpd-consistency-checker",
        "convention validation",
        "own convention policy",
    )
    assert_semantic_contract(
        workflow,
        "validate-conventions runtime delegation is one-shot",
        "runtime delegation",
        "one-shot",
        "checker",
        "checkpoint",
        "included delegation note",
    )
    assert workflow.count('subagent_type="gpd-consistency-checker"') == 1
    assert workflow.count('subagent_type="gpd-notation-coordinator"') == 0
    assert "gpd-notation-coordinator" in workflow
    assert_semantic_contract(
        workflow,
        "validate-conventions routes only on checker status",
        "route",
        "gpd_return.status",
        "completed",
        "checkpoint",
        "blocked",
        "failed",
    )
    assert_semantic_contract(
        workflow,
        "validate-conventions ignores checker-local headings",
        "checker-local",
        "headings",
        "presentation only",
    )
    assert_semantic_contract(
        workflow,
        "validate-conventions notation repair handoff stays thin",
        "next_actions",
        "notation repair",
        "gpd-notation-coordinator",
        "same scope",
        "coordinator owns",
    )
    assert_machine_contract(
        workflow,
        "validate-conventions completion artifact gate fields",
        "gpd_return.status: completed",
        "gpd_return.files_written",
    )


def test_consistency_checker_and_notation_coordinator_keep_ownership_boundaries_separate() -> None:
    checker = _read_agent("gpd-consistency-checker")
    notation = _read_agent("gpd-notation-coordinator")

    assert_semantic_contract(
        checker,
        "consistency checker owns between-phase consistency only",
        "gpd-verifier",
        "within-phase correctness",
        "between-phase consistency",
    )
    assert_machine_contract(
        checker,
        "consistency checker return authority and artifact fields",
        "status: completed",
        "files_written:\n    - GPD/phases/03-conventions/CONSISTENCY-CHECK.md",
        "shared_state_authority: return_only",
    )
    assert_semantic_contract(
        checker,
        "consistency checker status meanings",
        "status: checkpoint",
        "missing inputs",
        "status: blocked",
        "hard inconsistencies",
        "status: failed",
        "scope could not be validated",
    )
    assert_semantic_contract(
        checker,
        "consistency checker does not own fixes or convention authoring",
        "do not claim ownership",
        "code fixes",
        "commits",
        "convention-authoring",
    )
    assert_machine_contract(
        notation, "notation coordinator direct shared-state authority", "shared_state_authority: direct"
    )
    assert_semantic_contract(
        notation,
        "notation coordinator owns conventions file writes",
        "OWNS CONVENTIONS.md",
        "only agent",
        "creates",
        "modifies",
        "extends",
    )
    assert_semantic_contract(
        notation,
        "checker detects and delegates convention resolution",
        "gpd-consistency-checker",
        "DETECTS",
        "convention violations",
        "delegates resolution",
    )
    assert "Authority: use the frontmatter-derived Agent Requirements block" not in checker
    assert "shared_state_authority: return_only" in registry.get_agent("gpd-consistency-checker").system_prompt


def test_audit_milestone_consumes_checker_reports_without_spawning_notation_resolution() -> None:
    workflow = _read_workflow("audit-milestone.md")
    checker = _read_agent("gpd-consistency-checker")

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
        "audit milestone checker spawn failure remains skip path",
        "consistency checker agent",
        "fails to spawn",
        "skipped",
        "gpd:validate-conventions",
    )
    assert_machine_contract(checker, "consistency checker completed status anchor", "status: completed")
    assert_semantic_contract(
        checker,
        "consistency checker headings are presentation only",
        "headings",
        "presentation only",
        "gpd_return.status",
    )
