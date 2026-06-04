"""Tests for context root-policy helpers."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core import context as context_module
from gpd.core.context import init_new_project
from gpd.core.context_roots import (
    InitRootPolicy,
    _resolve_project_scoped_cwd,
    _resolve_workspace_locked_cwd,
    _start_folder_state,
    _workspace_start_classifier_context,
)


def test_context_reexports_root_policy_helpers() -> None:
    assert context_module.InitRootPolicy is InitRootPolicy
    assert context_module._resolve_project_scoped_cwd is _resolve_project_scoped_cwd
    assert context_module._resolve_workspace_locked_cwd is _resolve_workspace_locked_cwd
    assert context_module._workspace_start_classifier_context is _workspace_start_classifier_context


def test_root_policy_distinguishes_project_scoped_from_workspace_locked(tmp_path: Path) -> None:
    planning = tmp_path / "GPD"
    planning.mkdir()
    (planning / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (planning / "state.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    nested = tmp_path / "notes" / "scratch"
    nested.mkdir(parents=True)

    assert _resolve_project_scoped_cwd(nested) == tmp_path
    assert _resolve_workspace_locked_cwd(nested) == nested


def test_start_folder_state_prioritizes_recoverable_project_states() -> None:
    assert _start_folder_state({"project_exists": True, "needs_research_map": True}) == "initialized_project"
    assert _start_folder_state({"partial_project_exists": True, "has_research_map": True}) == "partial_project"
    assert _start_folder_state({"has_research_map": True, "needs_research_map": True}) == "research_map"
    assert _start_folder_state({"needs_research_map": True}) == "existing_research"
    assert _start_folder_state({}) == "fresh"


def test_new_project_is_workspace_bound_from_nested_workspace(tmp_path: Path) -> None:
    planning = tmp_path / "GPD"
    planning.mkdir()
    (planning / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (planning / "state.json").write_text("{}", encoding="utf-8")
    nested = tmp_path / "notes" / "scratch"
    nested.mkdir(parents=True)
    (nested / "calc.py").write_text("print('local research')\n", encoding="utf-8")

    ctx = init_new_project(nested, stage="scope_intake")

    assert ctx["project_exists"] is False
    assert ctx["state_exists"] is False
    assert ctx["recoverable_project_exists"] is False
    assert ctx["planning_exists"] is False
    assert ctx["has_research_map"] is False
    assert ctx["has_research_files"] is True
    assert ctx["research_file_samples"] == ["calc.py"]
    assert ctx["needs_research_map"] is True
    assert not (planning / "state.json.lock").exists()
