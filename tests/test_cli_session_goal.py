"""End-to-end CLI tests for `gpd goal` (RES-932)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.state import default_state_dict, generate_state_markdown

runner = CliRunner()


def _bootstrap_project(tmp_path: Path) -> Path:
    """Create a minimal GPD project tree so state-aware commands can find it."""
    planning = tmp_path / "GPD"
    planning.mkdir(parents=True, exist_ok=True)
    (planning / "phases").mkdir(exist_ok=True)
    (planning / "PROJECT.md").write_text("# Project\nTest project.\n", encoding="utf-8")
    (planning / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")

    state = default_state_dict()
    position = state.setdefault("position", {})
    position.setdefault("current_phase", "01")
    position.setdefault("status", "Executing")
    position.setdefault("current_plan", "1")
    position.setdefault("total_plans_in_phase", 1)
    position.setdefault("progress_percent", 0)

    (planning / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    (planning / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return tmp_path


def test_goal_root_with_no_args_prints_unset_goal(tmp_path: Path) -> None:
    cwd = _bootstrap_project(tmp_path)
    result = runner.invoke(app, ["--cwd", str(cwd), "--raw", "goal"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {"session_goal": None}


def test_goal_set_persists_text_budget_and_time(tmp_path: Path) -> None:
    cwd = _bootstrap_project(tmp_path)
    set_result = runner.invoke(
        app,
        [
            "--cwd",
            str(cwd),
            "--raw",
            "goal",
            "set",
            "Ship the paper",
            "--budget",
            "$50",
            "--time",
            "2h",
        ],
    )
    assert set_result.exit_code == 0, set_result.output

    show_result = runner.invoke(app, ["--cwd", str(cwd), "--raw", "goal", "show"])
    assert show_result.exit_code == 0, show_result.output
    payload = json.loads(show_result.output)
    assert payload["session_goal"]["text"] == "Ship the paper"
    assert payload["session_goal"]["budget"] == "$50"
    assert payload["session_goal"]["deadline"] == "2h"


def test_goal_set_idempotent_on_repeated_invocation(tmp_path: Path) -> None:
    cwd = _bootstrap_project(tmp_path)
    first = runner.invoke(
        app, ["--cwd", str(cwd), "--raw", "goal", "set", "Find quantum gravity"]
    )
    assert first.exit_code == 0, first.output

    second = runner.invoke(
        app, ["--cwd", str(cwd), "--raw", "goal", "set", "Find quantum gravity"]
    )
    # Re-setting the same goal exits 0 (unchanged), not as an error.
    assert second.exit_code == 0, second.output
    payload = json.loads(second.output)
    assert payload["updated"] is False
    # The `unchanged` field is excluded from JSON serialization, so verify via
    # the reason string instead.
    assert "already matches" in (payload.get("reason") or "")


def test_goal_clear_removes_persisted_goal(tmp_path: Path) -> None:
    cwd = _bootstrap_project(tmp_path)
    set_result = runner.invoke(
        app, ["--cwd", str(cwd), "--raw", "goal", "set", "Ship the paper"]
    )
    assert set_result.exit_code == 0, set_result.output

    clear_result = runner.invoke(app, ["--cwd", str(cwd), "--raw", "goal", "clear"])
    assert clear_result.exit_code == 0, clear_result.output

    show_result = runner.invoke(app, ["--cwd", str(cwd), "--raw", "goal", "show"])
    assert show_result.exit_code == 0, show_result.output
    payload = json.loads(show_result.output)
    assert payload == {"session_goal": None}


def test_goal_init_execute_phase_surfaces_derived_goal(tmp_path: Path) -> None:
    """Once set, the goal must surface in `gpd init execute-phase` bundles so
    downstream agent prompts can read a single, stable key."""
    cwd = _bootstrap_project(tmp_path)
    # Provide a phase directory so `init execute-phase 01` resolves.
    phase_dir = cwd / "GPD" / "phases" / "01-bootstrap"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "PLAN.md").write_text("# Plan\n", encoding="utf-8")

    set_result = runner.invoke(
        app,
        [
            "--cwd",
            str(cwd),
            "--raw",
            "goal",
            "set",
            "Find quantum gravity",
            "--budget",
            "$50",
            "--time",
            "2h",
        ],
    )
    assert set_result.exit_code == 0, set_result.output

    init_result = runner.invoke(
        app,
        ["--cwd", str(cwd), "--raw", "init", "execute-phase", "01"],
    )
    assert init_result.exit_code == 0, init_result.output
    payload = json.loads(init_result.output)
    assert payload["derived_session_goal"] == {
        "text": "Find quantum gravity",
        "budget": "$50",
        "deadline": "2h",
    }
    assert payload["derived_session_goal_text"] == "Find quantum gravity"
    assert payload["derived_session_goal_budget"] == "$50"
    assert payload["derived_session_goal_deadline"] == "2h"
