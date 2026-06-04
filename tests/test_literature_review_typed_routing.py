from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact, semantic_concept
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_literature_review_workflow_routes_on_typed_status_and_artifact_gate() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "literature-review")

    assert "references/orchestration/child-artifact-gate.md" in workflow
    assert "references/orchestration/continuation-boundary.md" in workflow
    assert "GPD/literature/{slug}-REVIEW.md" in workflow
    assert "GPD/literature/{slug}-CITATION-SOURCES.json" in workflow
    assert "GPD/literature/{slug}-CITATION-AUDIT.md" in workflow
    assert "all three paths are named in `files_written` and present/readable on disk" in workflow
    assert_prompt_contracts(
        workflow,
        machine_exact("literature-review checkpoint route", "checkpoint: include the decision question"),
    )
    assert "blocked/failed: list the missing artifact" in workflow


def test_literature_reviewer_shows_base_return_fields_and_one_shot_checkpointing() -> None:
    agent = _read(AGENTS_DIR / "gpd-literature-reviewer.md")

    assert_prompt_contracts(
        agent,
        *semantic_concept(
            "literature reviewer headings are presentation only",
            required=(
                "The markdown `## REVIEW COMPLETE` heading is presentation only.",
                "The `## CHECKPOINT REACHED` heading below is presentation only.",
                "stop at the continuation boundary",
            ),
        ),
    )
    assert "When reaching a checkpoint, return a typed `gpd_return` checkpoint and stop." in agent
    assert "Use `gpd_return.status: completed` for a finished review." in agent

    completed_block = agent.split("Use `gpd_return.status: completed` for a finished review.", 1)[1]
    status_idx = completed_block.index("  status: completed")
    files_idx = completed_block.index("  files_written: [GPD/literature/spectral-form-factor-REVIEW.md]")
    issues_idx = completed_block.index("  issues: []")
    next_actions_idx = completed_block.index('  next_actions: ["gpd:literature-review --synthesize"]')
    papers_idx = completed_block.index("  papers_reviewed: 12")

    assert status_idx < files_idx < issues_idx < next_actions_idx < papers_idx
