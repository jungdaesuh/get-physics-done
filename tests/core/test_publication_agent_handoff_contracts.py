from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _read_agent(name: str) -> str:
    return (AGENTS_DIR / name).read_text(encoding="utf-8")


def test_paper_writer_balanced_mode_avoids_in_run_approval_language() -> None:
    source = _read_agent("gpd-paper-writer.md")

    assert "proceed unless objected" not in source
    assert (
        "Balanced mode follows the publication-pipeline matrix: draft the manuscript, self-review it, "
        "and pause only when the narrative or claim decision needs user judgment." in source
    )
    assert "Balanced mode follows the publication-pipeline matrix" in source
    assert "Checkpoint ownership is orchestrator-side" in source
    assert "continuation-boundary.md" in source
    assert "fresh continuation handoff" not in source


def test_bibliographer_balanced_mode_adds_verified_citations_without_approval_loop() -> None:
    source = _read_agent("gpd-bibliographer.md")

    assert "Present a batch for approval" not in source
    assert (
        "Add verified citations automatically; pause only for uncertain matches, borderline relevance, or citation-scope changes."
        in source
    )
    assert "| Citation addition |" in source
    assert (
        "Use agent-infrastructure.md for checkpoint ownership, return-envelope base fields, and one-shot handoff semantics."
        in source
    )
    assert "Checkpoint ownership is orchestrator-side" not in source


def test_referee_checkpoint_ownership_and_mode_routing_are_explicit() -> None:
    source = _read_agent("gpd-referee.md")

    assert "fresh-continuation" in source
    assert "continuation-boundary.md" in source
    assert "gpd return skeleton --role referee --status <status>" in source
    assert "Checkpoint ownership is orchestrator-side" not in source
    assert "fresh continuation handoff" not in source
    assert "publication-pipeline-modes.md" in source


def test_publication_child_agents_keep_return_only_shared_state_boundary() -> None:
    for agent_name in ("gpd-paper-writer.md", "gpd-bibliographer.md", "gpd-referee.md"):
        source = _read_agent(agent_name)
        frontmatter = source.split("---", 2)[1]

        assert "shared_state_authority: return_only" in frontmatter
        assert "shared_state_authority: direct" not in source
        assert "shared_state_policy: direct" not in source
        assert "success proof" not in source.casefold()


def test_peer_review_and_referee_skill_surfaces_keep_lifecycle_cleanup_boundary() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    peer_review = get_skill("gpd-peer-review")
    referee = get_skill("gpd-referee")
    peer_review_references = {Path(entry["path"]).name for entry in peer_review["referenced_files"]}
    referee_content = referee["content"]

    assert "error" not in peer_review
    assert "error" not in referee
    assert "stage-recovery-gate.md" in peer_review_references
    assert "panel-stages.md" in peer_review_references
    assert "final-adjudication.md" in peer_review_references
    assert peer_review["staged_loading"]["workflow_id"] == "peer-review"
    assert "fresh-continuation" in referee_content
    assert "files-written-freshness" in referee_content
    assert "gpd return skeleton --role referee --status <status>" in referee_content
    assert "return file list may name only paths produced in this Stage 6 run" in referee_content
    assert "Checkpoint ownership is orchestrator-side" not in referee_content
    assert "Preexisting files are stale and do not count." not in referee_content
