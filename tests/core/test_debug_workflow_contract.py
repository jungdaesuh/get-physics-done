"""Focused assertions for the debug workflow seam."""

from __future__ import annotations

from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
TEMPLATES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "templates"


def _read(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def test_debug_workflow_uses_typed_child_return_and_skips_artifact_inventory() -> None:
    workflow = _read("debug.md")

    assert "typed `gpd_return` envelope" in workflow
    assert "gpd_return.session_file" in workflow
    assert "session_status: diagnosed" in workflow
    assert "The debug session file at `GPD/debug/{slug}.md` keeps the debug-session `status` lifecycle" in workflow
    assert "does not use `session_status`" in workflow
    assert "artifacts:" not in workflow
    assert "src/integrator.py" not in workflow
    assert "src/simulation.py" not in workflow
    assert "mkdir -p GPD/debug" not in workflow


def test_execute_phase_debugger_bypass_uses_explicit_debug_contract() -> None:
    workflow = _read("execute-phase.md")
    debug_template = (TEMPLATES_DIR / "debug-subagent-prompt.md").read_text(encoding="utf-8")

    assert "debug-subagent-prompt.md" in workflow
    assert "one-shot debug contract" in workflow
    assert "goal: find_root_cause_only" in workflow
    assert "symptoms_prefilled: true" in workflow
    assert "Create: GPD/debug/{FAILED_PLAN}.md" in workflow
    assert "status: gathering | investigating | fixing | verifying | resolved" in debug_template
    assert "Investigate why gap closure did not resolve this verification failure." not in workflow
