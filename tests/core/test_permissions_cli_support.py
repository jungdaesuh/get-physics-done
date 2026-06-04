"""Tests for Typer-free permissions CLI support helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from gpd.core.permissions_cli_support import (
    PermissionsResolutionError,
    permissions_install_target_error_message,
    permissions_status_payload,
    resolve_permissions_runtime_name,
    resolve_permissions_target_dir,
    runtime_permissions_payload,
)


@dataclass(frozen=True)
class _Assessment:
    config_dir: Path
    state: str
    manifest_state: str = "valid"
    manifest_runtime: str | None = None
    missing_install_artifacts: tuple[str, ...] = ()


class _PermissionsAdapter:
    def __init__(self, *, local_target: Path, global_target: Path) -> None:
        self._local_target = local_target
        self._global_target = global_target

    def validate_target_runtime(self, target_dir: Path, *, action: str) -> None:
        return None

    def resolve_target_dir(self, is_global: bool, cwd: Path) -> Path:
        return self._global_target if is_global else self._local_target

    def has_complete_install(self, target_dir: Path) -> bool:
        return False

    def runtime_permissions_status(self, target_dir: Path, *, autonomy: str) -> dict[str, object]:
        return {
            "desired_mode": "default",
            "configured_mode": "default",
            "config_aligned": True,
            "requires_relaunch": False,
            "managed_by_gpd": False,
        }

    def sync_runtime_permissions(self, target_dir: Path, *, autonomy: str) -> dict[str, object]:
        return {"sync_applied": True, "changed": False}


def test_resolve_permissions_runtime_name_prefers_installed_runtime_selector(tmp_path: Path) -> None:
    def detect_active_runtime(*, cwd: Path) -> str:
        raise AssertionError("active runtime selector should not be used")

    resolved = resolve_permissions_runtime_name(
        None,
        cwd=tmp_path,
        prefer_installed_runtime=True,
        supported_runtime_names=lambda: ("alpha",),
        normalize_runtime_name=lambda value: value,
        detect_active_runtime=detect_active_runtime,
        detect_runtime_for_gpd_use=lambda cwd: "alpha",
    )

    assert resolved == "alpha"


@pytest.mark.parametrize(
    ("assessment", "expected_fragment"),
    [
        (
            _Assessment(
                config_dir=Path("/runtime"),
                state="owned_incomplete",
                missing_install_artifacts=("agents/gpd-help/SKILL.md",),
            ),
            "incomplete GPD install",
        ),
        (
            _Assessment(config_dir=Path("/runtime"), state="foreign_runtime", manifest_runtime="beta"),
            "belongs to runtime 'beta'",
        ),
        (
            _Assessment(config_dir=Path("/runtime"), state="untrusted_manifest", manifest_state="corrupt"),
            "manifest state is 'corrupt'",
        ),
    ],
)
def test_permissions_install_target_error_message_preserves_specific_install_states(
    assessment: _Assessment,
    expected_fragment: str,
    tmp_path: Path,
) -> None:
    message = permissions_install_target_error_message("alpha", assessment, action="inspect", cwd=tmp_path)

    assert expected_fragment in message
    assert "Run `gpd install alpha` first" not in message


def test_resolve_permissions_target_dir_reports_incomplete_candidate_before_generic_missing(tmp_path: Path) -> None:
    local_target = tmp_path / ".alpha"
    global_target = tmp_path / "global-alpha"
    adapter = _PermissionsAdapter(local_target=local_target, global_target=global_target)

    def assessment(runtime_name: str, target_dir: Path) -> _Assessment:
        if target_dir == local_target:
            return _Assessment(
                config_dir=target_dir,
                state="owned_incomplete",
                missing_install_artifacts=("agents/gpd-help/SKILL.md",),
            )
        return _Assessment(config_dir=target_dir, state="absent")

    with pytest.raises(PermissionsResolutionError, match="incomplete GPD install"):
        resolve_permissions_target_dir(
            "alpha",
            target_dir=None,
            cwd=tmp_path,
            adapter_lookup=lambda runtime: adapter,
            detect_runtime_install_target=lambda runtime, cwd: None,
            detect_install_scope=lambda runtime, cwd: None,
            target_assessment_resolver=assessment,
        )


def test_runtime_permissions_payload_returns_diagnostic_payload_when_non_strict_resolution_fails(
    tmp_path: Path,
) -> None:
    payload = runtime_permissions_payload(
        runtime=None,
        autonomy=None,
        target_dir=None,
        apply_sync=False,
        strict=False,
        cwd=tmp_path,
        runtime_name_resolver=lambda *args, **kwargs: (_ for _ in ()).throw(
            PermissionsResolutionError("No active runtime was detected.")
        ),
    )

    assert payload["runtime"] is None
    assert "No active runtime" in str(payload["message"])
    assert isinstance(payload["capabilities"], dict)
    assert payload["current_session_verified"] is False


def test_runtime_permissions_payload_uses_injected_resolvers_and_adapter(tmp_path: Path) -> None:
    target = tmp_path / ".alpha"
    adapter = _PermissionsAdapter(local_target=target, global_target=tmp_path / "global-alpha")

    payload = runtime_permissions_payload(
        runtime="alpha",
        autonomy="balanced",
        target_dir=None,
        apply_sync=False,
        strict=True,
        cwd=tmp_path,
        adapter_lookup=lambda runtime: adapter,
        runtime_name_resolver=lambda runtime, **kwargs: "alpha",
        target_dir_resolver=lambda runtime, **kwargs: target,
        autonomy_resolver=lambda autonomy, **kwargs: "balanced",
    )

    assert payload["runtime"] == "alpha"
    assert payload["target"] == str(target)
    assert payload["autonomy"] == "balanced"
    assert payload["config_aligned"] is True
    assert payload["requested_surface"] == "ordinary-unattended"


def test_permissions_status_payload_normalizes_readiness_fields(tmp_path: Path) -> None:
    payload = permissions_status_payload(
        runtime="alpha",
        autonomy="balanced",
        target_dir=str(tmp_path / ".alpha"),
        cwd=tmp_path,
        runtime_permissions_payload_func=lambda **kwargs: {
            "runtime": "alpha",
            "target": str(tmp_path / ".alpha"),
            "autonomy": "balanced",
            "config_aligned": True,
            "requires_relaunch": False,
        },
    )

    assert payload["ready"] is True
    assert payload["readiness"] == "ready"
