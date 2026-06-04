"""Focused assertions for the quick command wrapper contract."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUICK_COMMAND = REPO_ROOT / "src" / "gpd" / "commands" / "quick.md"
QUICK_STAGE_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "quick"
QUICK_REFERENCES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "references" / "quick"


def test_quick_command_wrapper_surfaces_staged_handoff_and_preserves_workflow_gates() -> None:
    command = QUICK_COMMAND.read_text(encoding="utf-8")
    bootstrap = (QUICK_STAGE_DIR / "task-bootstrap.md").read_text(encoding="utf-8")
    authoring = (QUICK_STAGE_DIR / "task-authoring.md").read_text(encoding="utf-8")
    mode_boundary = (QUICK_REFERENCES_DIR / "quick-mode-boundary.md").read_text(encoding="utf-8")

    assert "workflow owns the staged quick planner handoff" in " ".join(command.split())
    assert "staged planner loading" in command
    assert "@{GPD_INSTALL_DIR}/workflows/quick/task-bootstrap.md" in command
    assert "@{GPD_INSTALL_DIR}/workflows/quick.md" not in command
    assert "active stage authority" in command
    assert "Typical quick tasks in physics research" not in command
    assert "When to Use Quick vs Full Workflow" not in command
    assert "Rigor Expectations in Quick Mode" not in command

    assert "Ask ONE inline freeform question (NOT ask_user):" in bootstrap
    assert "project_exists" in bootstrap
    assert "Run this `child_gate`" in authoring
    assert "Structured state updated via `gpd state` commands" in authoring
    assert "Promote out of quick" in mode_boundary
    assert "gpd:add-phase" in mode_boundary
    assert "gpd:insert-phase" in mode_boundary
