"""Tests for runtime target resolution helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gpd.core.runtime_targeting import (
    RuntimeTargetingError,
    format_target_for_display,
    permissions_target_for_runtime_choice,
    resolve_cli_target_dir,
    resolve_doctor_runtime_target,
    resolve_unattended_runtime_target,
    target_dir_matches_global,
    validate_target_dir_runtime_selection,
)


class _RuntimeAdapter:
    def __init__(self, *, local_target: Path, global_target: Path) -> None:
        self._local_target = local_target
        self._global_target = global_target

    def resolve_target_dir(self, is_global: bool, cwd: Path) -> Path:
        return self._global_target if is_global else self._local_target


def test_resolve_cli_target_dir_resolves_relative_to_cwd(tmp_path: Path) -> None:
    assert resolve_cli_target_dir(".runtime", cwd=tmp_path) == (tmp_path / ".runtime").resolve(strict=False)
    assert resolve_cli_target_dir(str(tmp_path / "absolute"), cwd=Path("/ignored")) == (tmp_path / "absolute").resolve(
        strict=False
    )


def test_format_target_for_display_prefers_cwd_then_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"

    assert format_target_for_display(workspace / ".runtime", cwd=workspace, home=home) == "./.runtime"
    assert format_target_for_display(home / ".runtime", cwd=workspace, home=home) == "~/.runtime"


def test_target_dir_matches_global_uses_adapter_fallback(tmp_path: Path) -> None:
    adapter = _RuntimeAdapter(local_target=tmp_path / ".runtime", global_target=tmp_path / "global-runtime")

    assert target_dir_matches_global(
        "alpha",
        str(tmp_path / "global-runtime"),
        cwd=tmp_path,
        action="install",
        adapter_lookup=lambda runtime: adapter,
    )
    assert not target_dir_matches_global(
        "alpha",
        ".runtime",
        cwd=tmp_path,
        action="install",
        adapter_lookup=lambda runtime: adapter,
    )


def test_validate_target_dir_runtime_selection_rejects_multi_runtime_target() -> None:
    with pytest.raises(RuntimeTargetingError, match="exactly one runtime"):
        validate_target_dir_runtime_selection("install", ["alpha", "beta"], ".runtime")


def test_doctor_target_resolution_defaults_to_local_target_without_detection(tmp_path: Path) -> None:
    adapter = _RuntimeAdapter(local_target=tmp_path / ".runtime", global_target=tmp_path / "global-runtime")

    choice = resolve_doctor_runtime_target(
        "alpha",
        cwd=tmp_path,
        global_install=False,
        local_install=False,
        target_dir=None,
        adapter_lookup=lambda runtime: adapter,
    )

    assert choice.install_scope == "local"
    assert choice.target_dir == tmp_path / ".runtime"


def test_unattended_target_resolution_prefers_detected_install(tmp_path: Path) -> None:
    detected_target = tmp_path / "detected-global"

    choice = resolve_unattended_runtime_target(
        "alpha",
        cwd=tmp_path,
        global_install=False,
        local_install=False,
        target_dir=None,
        resolve_detected_runtime_target_func=lambda runtime, cwd: (detected_target, "global"),
    )

    assert choice.install_scope == "global"
    assert choice.target_dir == detected_target


def test_permissions_target_for_runtime_choice_uses_adapter_when_target_is_implicit(tmp_path: Path) -> None:
    adapter = _RuntimeAdapter(local_target=tmp_path / ".runtime", global_target=tmp_path / "global-runtime")
    choice = SimpleNamespace(install_scope="global", target_dir=None)

    assert permissions_target_for_runtime_choice(
        "alpha",
        choice,
        cwd=tmp_path,
        adapter_lookup=lambda runtime: adapter,
    ) == str(tmp_path / "global-runtime")
