"""Assertions for explicit planner schema visibility."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_concept
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANNER_ROLE = REPO_ROOT / "src" / "gpd" / "agents" / "gpd-planner.md"
PLAN_PHASE = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "plan-phase.md"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
VERIFY_WORK = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "verify-work.md"
QUICK = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "quick.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_planner_role_owns_schema_visibility_and_workflows_use_the_short_role_preamble() -> None:
    planner_role = _read(PLANNER_ROLE)
    plan_phase = workflow_authority_text(WORKFLOWS_DIR, PLAN_PHASE.name)
    verify_work = workflow_authority_text(WORKFLOWS_DIR, VERIFY_WORK.name)
    quick = workflow_authority_text(WORKFLOWS_DIR, QUICK.name)

    required_markers = (
        "{GPD_INSTALL_DIR}/templates/phase-prompt.md",
        "{GPD_INSTALL_DIR}/templates/plan-contract-schema.md",
    )

    for marker in required_markers:
        assert marker in planner_role

    bootstrap = planner_role.partition("</role>")[0]

    assert "@{GPD_INSTALL_DIR}/templates/phase-prompt.md" not in bootstrap
    assert "@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md" not in bootstrap
    assert "use `file_read` to load `{GPD_INSTALL_DIR}/templates/phase-prompt.md`" in bootstrap
    assert_prompt_contracts(
        bootstrap,
        *semantic_concept(
            "planner role fails closed when schema template cannot load",
            required=(
                "If the template cannot be loaded",
                "do not reconstruct the schema from memory",
            ),
        ),
    )
    assert_prompt_contracts(
        planner_role,
        *semantic_concept(
            "planner prompt keeps schema guidance lean",
            required=(
                "Keep this agent prompt lean.",
                "use this file for planner role, routing, and plan-shape guidance only.",
            ),
        ),
    )
    assert "@{GPD_INSTALL_DIR}/workflows/execute-plan.md" not in bootstrap
    assert "@{GPD_INSTALL_DIR}/templates/summary.md" not in bootstrap
    assert "@{GPD_INSTALL_DIR}/references/protocols/order-of-limits.md" not in bootstrap
    short_instruction = "First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions."
    long_instruction = (
        "First, read {GPD_AGENTS_DIR}/gpd-planner.md, {GPD_INSTALL_DIR}/templates/phase-prompt.md, "
        "and {GPD_INSTALL_DIR}/templates/plan-contract-schema.md for your role and instructions."
    )
    assert plan_phase.count(short_instruction) == 2
    assert verify_work.count(short_instruction) == 1
    assert quick.count(short_instruction) == 2
    assert long_instruction not in plan_phase
    assert long_instruction not in verify_work
    assert long_instruction not in quick
