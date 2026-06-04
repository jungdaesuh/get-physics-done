"""Assertions for the shared continuation-boundary reference."""

from __future__ import annotations

from pathlib import Path

from gpd import registry

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "src/gpd/specs/references/orchestration/continuation-boundary.md"
OWNED_SURFACES = [
    REPO_ROOT / "src/gpd/specs/templates/continuation-prompt.md",
    REPO_ROOT / "src/gpd/specs/references/execution/execute-plan-checkpoints.md",
    REPO_ROOT / "src/gpd/agents/gpd-roadmapper.md",
    REPO_ROOT / "src/gpd/agents/gpd-notation-coordinator.md",
    REPO_ROOT / "src/gpd/agents/gpd-literature-reviewer.md",
    REPO_ROOT / "src/gpd/agents/gpd-paper-writer.md",
    REPO_ROOT / "src/gpd/agents/gpd-debugger.md",
    REPO_ROOT / "src/gpd/agents/gpd-project-researcher.md",
    REPO_ROOT / "src/gpd/agents/gpd-plan-checker.md",
    REPO_ROOT / "src/gpd/agents/gpd-consistency-checker.md",
]


def test_continuation_boundary_reference_defines_the_one_shot_contract() -> None:
    content = REFERENCE.read_text(encoding="utf-8")

    required_terms = (
        "one-shot",
        "`gpd_return.status: checkpoint`",
        "must not wait for the user",
        "fresh continuation handoff",
        "`files_written` only after they exist",
        "`files_written: []`",
        "`checkpoint_intent` is child-owned",
        "not durable authority",
        "parent/applicator supplies parent-owned resume context",
        "result/session identifiers",
        "timestamps",
        "resolved bounded-segment state",
        "references/orchestration/child-artifact-gate.md",
        "fresh typed `gpd_return` envelope",
    )

    for term in required_terms:
        assert term in content

    assert "Agent prompts should not duplicate these generic lifecycle rules." in content


def test_owned_continuation_surfaces_reference_the_boundary_without_eager_include() -> None:
    token = "references/orchestration/continuation-boundary.md"
    eager_include = f"@{{GPD_INSTALL_DIR}}/{token}"

    for path in OWNED_SURFACES:
        content = (
            registry.get_agent(path.stem).system_prompt
            if path.parent == REPO_ROOT / "src/gpd/agents"
            else path.read_text(encoding="utf-8")
        )
        assert token in content, path.relative_to(REPO_ROOT)
        assert eager_include not in content, path.relative_to(REPO_ROOT)
