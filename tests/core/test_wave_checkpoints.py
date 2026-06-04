"""Rollback checkpoint tag helpers for phase wave execution."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from gpd.cli import app
from gpd.core import wave_checkpoints as wave_module
from gpd.core.wave_checkpoints import (
    cleanup_wave_checkpoints,
    create_wave_checkpoint,
    list_wave_checkpoints,
)


class _StableCliRunner(CliRunner):
    def invoke(self, *args, **kwargs):
        kwargs.setdefault("color", False)
        return super().invoke(*args, **kwargs)


RUNNER = _StableCliRunner()


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _write_phase_project(root: Path, *, with_verification: bool = False) -> Path:
    phase_dir = root / "GPD" / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)
    (root / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (root / "GPD" / "ROADMAP.md").write_text("# Roadmap\n\n## Phase 2: Analysis\n", encoding="utf-8")
    for index in range(1, 3):
        (phase_dir / f"02-{index:02d}-PLAN.md").write_text(
            f"---\nwave: {index}\n---\n\n# Plan {index}\n",
            encoding="utf-8",
        )
        (phase_dir / f"02-{index:02d}-SUMMARY.md").write_text(
            f"# Summary {index}\n",
            encoding="utf-8",
        )
    if with_verification:
        (phase_dir / "02-VERIFICATION.md").write_text(
            "---\n"
            "status: passed\n"
            "score: all phase checks passed\n"
            "---\n\n"
            "# Verification\n",
            encoding="utf-8",
        )
    return phase_dir


def _init_git_project(root: Path) -> str:
    _run_git(root, "init")
    _run_git(root, "config", "user.email", "test@example.com")
    _run_git(root, "config", "user.name", "Test User")
    _run_git(root, "add", "GPD")
    _run_git(root, "commit", "-m", "initial project")
    return _run_git(root, "rev-parse", "--short=12", "HEAD").stdout.strip()


def test_create_wave_checkpoint_creates_helper_owned_tag(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)
    commit = _init_git_project(tmp_path)

    result = create_wave_checkpoint(tmp_path, phase="2", wave="1")

    assert result.created is True
    assert result.mutated is True
    assert result.safe_to_execute_wave is True
    assert result.commit == commit
    assert result.tag is not None
    assert result.tag.startswith("gpd-checkpoint-phase-02-wave-1-")
    assert result.tag.endswith(commit)
    assert result.errors == []
    assert result.tag in _run_git(tmp_path, "tag", "-l").stdout.splitlines()


def test_create_wave_checkpoint_refuses_project_without_git_root(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)

    result = create_wave_checkpoint(tmp_path, phase="02", wave="1")

    assert result.created is False
    assert result.mutated is False
    assert result.safe_to_execute_wave is False
    assert any("project-local git root" in error for error in result.errors)


def test_create_wave_checkpoint_refuses_ambient_parent_git_root(tmp_path: Path) -> None:
    _run_git(tmp_path, "init")
    project_root = tmp_path / "nested-project"
    _write_phase_project(project_root)

    result = create_wave_checkpoint(project_root, phase="02", wave="1")

    assert result.created is False
    assert result.safe_to_execute_wave is False
    assert any("git root to equal project root" in error for error in result.errors)


def test_create_wave_checkpoint_retries_canonical_tag_collision(tmp_path: Path, monkeypatch) -> None:
    _write_phase_project(tmp_path)
    commit = _init_git_project(tmp_path)

    class FrozenDateTime:
        @staticmethod
        def now(_tz):
            return datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)

    monkeypatch.setattr(wave_module, "datetime", FrozenDateTime)
    colliding = f"gpd-checkpoint-phase-02-wave-1-20260508120000-{commit}"
    _run_git(tmp_path, "tag", colliding)

    result = create_wave_checkpoint(tmp_path, phase="02", wave="1")

    assert result.created is True
    assert result.tag == f"{colliding}-retry-1"
    tags = _run_git(tmp_path, "tag", "-l", "gpd-checkpoint-phase-02-*").stdout.splitlines()
    assert colliding in tags
    assert result.tag in tags


def test_list_wave_checkpoints_filters_to_helper_owned_tags(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)
    commit = _init_git_project(tmp_path)
    helper_tag = f"gpd-checkpoint-phase-02-wave-1-20260508120000-{commit}"
    _run_git(tmp_path, "tag", helper_tag)
    _run_git(tmp_path, "tag", "gpd-checkpoint-phase-02-user")

    result = list_wave_checkpoints(tmp_path, phase="02")

    assert result.tags == [helper_tag]
    assert result.mutated is False


def test_cleanup_successful_closeout_deletes_only_helper_owned_tags(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, with_verification=True)
    commit = _init_git_project(tmp_path)
    helper_tag = f"gpd-checkpoint-phase-02-wave-1-20260508120000-{commit}"
    helper_tag_2 = f"gpd-checkpoint-phase-02-wave-2-20260508120001-{commit}"
    user_tag = "gpd-checkpoint-phase-02-user"
    other_phase_tag = f"gpd-checkpoint-phase-03-wave-1-20260508120000-{commit}"
    for tag in (helper_tag, helper_tag_2, user_tag, other_phase_tag):
        _run_git(tmp_path, "tag", tag)

    result = cleanup_wave_checkpoints(tmp_path, phase="02", policy="successful-closeout")

    assert result.cleanup_allowed is True
    assert result.mutated is True
    assert result.deleted_tags == [helper_tag, helper_tag_2]
    assert result.errors == []
    remaining = set(_run_git(tmp_path, "tag", "-l").stdout.splitlines())
    assert helper_tag not in remaining
    assert helper_tag_2 not in remaining
    assert user_tag in remaining
    assert other_phase_tag in remaining


def test_cleanup_preserve_on_failure_never_deletes_tags(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)
    commit = _init_git_project(tmp_path)
    helper_tag = f"gpd-checkpoint-phase-02-wave-1-20260508120000-{commit}"
    _run_git(tmp_path, "tag", helper_tag)

    result = cleanup_wave_checkpoints(tmp_path, phase="02", policy="preserve-on-failure")

    assert result.cleanup_allowed is False
    assert result.mutated is False
    assert result.preserved_tags == [helper_tag]
    assert helper_tag in _run_git(tmp_path, "tag", "-l").stdout.splitlines()


def test_phase_checkpoint_create_cli_emits_raw_json_and_nonzero_on_unsafe_root(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "checkpoint",
            "create",
            "--phase",
            "02",
            "--wave",
            "1",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["created"] is False
    assert payload["safe_to_execute_wave"] is False
    assert payload["mutation_boundary"] == "mutating"
