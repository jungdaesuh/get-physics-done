"""Planner ownership contract assertions."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_concept

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANNER_PATH = REPO_ROOT / "src" / "gpd" / "agents" / "gpd-planner.md"


def _read_planner_prompt() -> str:
    return PLANNER_PATH.read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    _, start_marker, tail = text.partition(start)
    assert start_marker, f"Missing marker: {start}"
    body, end_marker, _ = tail.partition(end)
    assert end_marker, f"Missing marker: {end}"
    return body


def test_planner_keeps_schema_template_file_read_gate_visible_before_plan_examples() -> None:
    planner = _read_planner_prompt()
    role = _between(planner, "<role>", "</role>")

    file_read_idx = role.index("use `file_read`")
    phase_prompt_idx = role.index("{GPD_INSTALL_DIR}/templates/phase-prompt.md")
    schema_idx = role.index("{GPD_INSTALL_DIR}/templates/plan-contract-schema.md")
    frontmatter_idx = role.index("before plan frontmatter")

    assert file_read_idx < phase_prompt_idx < schema_idx < frontmatter_idx
    assert "@{GPD_INSTALL_DIR}/templates/phase-prompt.md" not in role
    assert "@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md" not in role
    assert "Before emitting or revising any `PLAN.md`" in role
    assert_prompt_contracts(
        role,
        *semantic_concept(
            "planner schema template file-read gate fails closed",
            required=(
                "If the template cannot be loaded",
                "do not reconstruct the schema from memory",
                "Return structured results to the orchestrator.",
            ),
        ),
    )
