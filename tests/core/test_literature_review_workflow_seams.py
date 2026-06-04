"""Seam assertions for the `literature-review` workflow vertical."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, semantic_anchor
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_semantic(source: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(
        source,
        semantic_anchor(label, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label),
    )


def test_literature_review_command_stays_thin_and_leaves_routing_to_the_workflow() -> None:
    command = _read(COMMANDS_DIR / "literature-review.md")

    assert "@{GPD_INSTALL_DIR}/workflows/literature-review/review-bootstrap.md" in command
    assert "Read the included literature-review bootstrap authority first." in command
    assert "scope fixing, artifact gating, citation verification" in command
    assert "explicit topic or research question" in command
    assert "under `GPD/literature/` rooted at the current workspace" in command
    assert "Standalone empty invocations should already have failed preflight." in command
    assert "gpd-literature-reviewer" not in command
    assert "gpd-bibliographer" not in command
    assert "gpd commit" not in command


def test_literature_review_workflow_requires_reviewer_and_bibliographer_spawn_contracts() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "literature-review")

    assert 'subagent_type="gpd-literature-reviewer"' in workflow
    assert 'subagent_type="gpd-bibliographer"' in workflow
    assert workflow.count("<spawn_contract>") >= 2
    assert "shared_state_policy: return_only" in workflow
    assert "GPD/literature/{slug}-REVIEW.md" in workflow
    assert "GPD/literature/{slug}-CITATION-SOURCES.json" in workflow
    assert "GPD/literature/{slug}-CITATION-AUDIT.md" in workflow
    _assert_semantic(
        workflow,
        "literature review citation audit handoff names local artifact",
        "typed handoff",
        "completed",
        "GPD/literature/{slug}-CITATION-AUDIT.md",
        "files_written",
    )
    assert "references/orchestration/continuation-boundary.md" in workflow
    assert "checkpoint_response" in workflow
    assert "Keep all durable review artifacts rooted under `GPD/literature/` in the current workspace." in workflow
    assert "If `topic` is empty, do not invent or auto-derive it from project state" in workflow
    assert "The review topic must already be explicit or newly clarified" in workflow
    assert "Proceed without citation audit." not in workflow
    assert "**If BIBLIOGRAPHY UPDATED:**" not in workflow


def test_literature_review_workflow_removes_legacy_commit_ownership_and_keeps_completion_fail_closed() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "literature-review")

    assert "gpd commit" not in workflow
    assert "references/orchestration/child-artifact-gate.md" in workflow
    _assert_semantic(
        workflow,
        "literature review completion gate remains fail closed",
        "Local completion gate",
        "completed",
        "REVIEW.md",
        "CITATION-SOURCES.json",
        "CITATION-AUDIT.md",
        "files_written",
        "blocked/failed",
    )
    _assert_semantic(
        workflow,
        "literature review checkpoint continuation",
        "checkpoint",
        "checkpoint_response",
        "continuation",
    )
