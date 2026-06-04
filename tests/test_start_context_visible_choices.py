"""Focused coverage for structured `gpd:start` visible choices."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpd.cli import app
from gpd.core.state import default_state_dict
from tests.helpers.cli import StableCliRunner, invoke_raw_json

runner = StableCliRunner()

_CHOICE_KEYS = {
    "option_id",
    "label",
    "command",
    "recommended",
    "route_write_policy_id",
}


def _raw_start_context(workspace: Path) -> dict[str, object]:
    return invoke_raw_json(
        runner,
        app,
        ["--raw", "--cwd", str(workspace), "init", "start-context"],
        catch_exceptions=False,
    )


def _choice_signatures(payload: dict[str, object]) -> list[tuple[object, ...]]:
    choices = payload["visible_choices"]
    assert isinstance(choices, list)
    for choice in choices:
        assert isinstance(choice, dict)
        assert set(choice) == _CHOICE_KEYS
        assert isinstance(choice["option_id"], str)
        assert isinstance(choice["label"], str)
        assert isinstance(choice["command"], str)
        assert isinstance(choice["recommended"], bool)
        assert isinstance(choice["route_write_policy_id"], str)
    return [
        (
            choice["option_id"],
            choice["label"],
            choice["command"],
            choice["recommended"],
            choice["route_write_policy_id"],
        )
        for choice in choices
    ]


def _workspace(tmp_path: Path, name: str) -> Path:
    workspace = tmp_path / name
    workspace.mkdir()
    return workspace


@pytest.mark.parametrize(
    ("state_name", "setup", "expected_choices"),
    (
        (
            "fresh",
            lambda root: None,
            [
                ("new_project_minimal", "Fast start", "gpd:new-project --minimal", True),
                ("new_project_full", "Full guided setup", "gpd:new-project", False),
                ("tour", "Take a guided tour first", "gpd:tour", False),
            ],
        ),
        (
            "existing-research",
            lambda root: (root / "analysis.py").write_text("print('result')\n", encoding="utf-8"),
            [
                ("map_research", "Map this folder first", "gpd:map-research", True),
                ("tour", "Take a guided tour first", "gpd:tour", False),
                (
                    "new_project_minimal",
                    "Start a brand-new GPD project anyway",
                    "gpd:new-project --minimal",
                    False,
                ),
            ],
        ),
        (
            "research-map",
            lambda root: (root / "GPD" / "research-map").mkdir(parents=True),
            [
                ("new_project_full", "Turn this into a full GPD project", "gpd:new-project", True),
                ("map_research", "Refresh the research map", "gpd:map-research", False),
                ("tour", "Take a guided tour first", "gpd:tour", False),
            ],
        ),
        (
            "initialized-project",
            lambda root: _write_project_marker(root),
            [
                ("resume_work", "Resume this project", "gpd:resume-work", True),
                ("progress", "Review the project status first", "gpd:progress", False),
                ("tour", "Take a guided tour first", "gpd:tour", False),
            ],
        ),
    ),
)
def test_start_context_visible_choices_match_folder_state_routes(
    tmp_path: Path,
    state_name: str,
    setup: object,
    expected_choices: list[tuple[str, str, str, bool]],
) -> None:
    workspace = _workspace(tmp_path, state_name)
    assert callable(setup)
    setup(workspace)

    payload = _raw_start_context(workspace)
    signatures = _choice_signatures(payload)

    assert [signature[:4] for signature in signatures] == expected_choices
    assert all(str(signature[4]).startswith("start_route_") for signature in signatures)
    assert len(payload["visible_choices"]) <= 3


@pytest.mark.parametrize(
    ("name", "setup", "expected_option_ids"),
    (
        ("roadmap-only", lambda root: _write_gpd_file(root, "ROADMAP.md", "# Roadmap\n"), ["resume_work"]),
        (
            "state-only",
            lambda root: _write_gpd_file(root, "state.json", json.dumps(default_state_dict())),
            ["sync_state"],
        ),
        (
            "roadmap-and-state",
            lambda root: (
                _write_gpd_file(root, "ROADMAP.md", "# Roadmap\n"),
                _write_gpd_file(root, "state.json", json.dumps(default_state_dict())),
            ),
            ["resume_work", "sync_state"],
        ),
    ),
)
def test_start_context_visible_choices_for_partial_state_are_filtered(
    tmp_path: Path,
    name: str,
    setup: object,
    expected_option_ids: list[str],
) -> None:
    workspace = _workspace(tmp_path, name)
    assert callable(setup)
    setup(workspace)

    payload = _raw_start_context(workspace)
    option_ids = [choice[0] for choice in _choice_signatures(payload)]

    assert payload["folder_state"] == "partial_project"
    assert option_ids == expected_option_ids
    assert "progress" not in option_ids
    assert "new_project_full" not in option_ids


def test_start_context_visible_choices_for_init_progress_only(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "init-progress-only")
    _write_gpd_file(
        workspace,
        "init-progress.json",
        json.dumps({"status": "scope_intake", "step": "scope_intake"}),
    )

    payload = _raw_start_context(workspace)

    assert _choice_signatures(payload)[0][:4] == (
        "new_project_minimal",
        "Inspect interrupted setup",
        "gpd:new-project --minimal",
        True,
    )


def _write_project_marker(root: Path) -> None:
    _write_gpd_file(root, "PROJECT.md", "# Project\n")


def _write_gpd_file(root: Path, relpath: str, content: str) -> None:
    path = root / "GPD" / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
