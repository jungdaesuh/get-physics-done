"""Acceptance checks for read-only public runtime bridge surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from gpd.cli import app
from tests.helpers.cli import StableCliRunner, invoke_raw_json
from tests.tree_snapshot_support import assert_tree_unchanged, snapshot_tree

runner = StableCliRunner()


def _write_workspace(root: Path, kind: str) -> Path:
    workspace = root / kind
    workspace.mkdir()
    if kind == "existing-research":
        (workspace / "notes.tex").write_text("\\section{Current calculation}\n", encoding="utf-8")
    elif kind == "partial-project":
        gpd_dir = workspace / "GPD"
        gpd_dir.mkdir()
        (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    elif kind == "initialized-project":
        gpd_dir = workspace / "GPD"
        gpd_dir.mkdir()
        (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    return workspace


@pytest.fixture(
    params=("fresh", "existing-research", "partial-project", "initialized-project"),
    ids=("fresh", "existing-research", "partial-project", "initialized-project"),
)
def read_only_workspace(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    return _write_workspace(tmp_path, str(request.param))


def _raw_payload_preserving_tree(
    workspace: Path,
    argv: list[str],
    *,
    expect_exit: int = 0,
) -> dict[str, object]:
    before = snapshot_tree(workspace)
    payload = invoke_raw_json(
        runner,
        app,
        ["--raw", "--cwd", str(workspace), *argv],
        expect_exit=expect_exit,
        catch_exceptions=False,
    )
    assert_tree_unchanged(workspace, before, context=f"gpd {' '.join(argv)}")
    return payload


def test_raw_start_context_preserves_workspace_tree(read_only_workspace: Path) -> None:
    payload = _raw_payload_preserving_tree(read_only_workspace, ["init", "start-context"])

    assert payload["schema_version"] == "start_context.v1"
    assert payload["workspace_root"] == str(read_only_workspace.resolve())


@pytest.mark.parametrize(
    ("argv", "expect_exit"),
    (
        (["help"], 0),
        (["help", "--all"], 0),
        (["help", "--command", "progress"], 0),
        (["help", "--command", "does-not-exist"], 1),
    ),
    ids=("help-default", "help-all", "help-command", "help-unknown-command"),
)
def test_raw_help_bridge_preserves_workspace_tree(
    read_only_workspace: Path,
    argv: list[str],
    expect_exit: int,
) -> None:
    payload = _raw_payload_preserving_tree(read_only_workspace, argv, expect_exit=expect_exit)

    assert payload["command"] == "gpd:help"
    assert payload["read_only"] is True
    if payload.get("error") == "unknown_command":
        assert payload["canonical_recommended_commands"] == ["gpd:help --all"]
        recommended = payload.get("recommended_commands")
        assert isinstance(recommended, list)
        assert len(recommended) == 1
        _assert_single_primary_remediation_if_exposed(payload)


def _assert_single_primary_remediation_if_exposed(payload: dict[str, object]) -> None:
    primary_values = [payload[key] for key in ("primary_remediation_action", "primary_action") if payload.get(key)]
    if primary_values:
        assert len(primary_values) == 1

    for key in ("primary_remediation_actions", "remediation_actions"):
        actions = payload.get(key)
        if actions is None:
            continue
        assert isinstance(actions, list)
        assert len(actions) == 1
