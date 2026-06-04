"""Focused tests for managed install-surface detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpd.adapters.runtime_catalog import ManagedInstallSurfacePolicy
from gpd.hooks.install_metadata import (
    InstallManifestSnapshot,
    inspect_managed_install_surface,
    load_install_manifest_explicit_target_status,
    load_install_manifest_runtime_status,
    load_install_manifest_scope_status,
    load_install_manifest_snapshot,
    load_install_manifest_state,
)


def test_inspect_managed_install_surface_uses_runtime_catalog_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / ".custom-runtime"
    (config_dir / "managed-root" / "VERSION").parent.mkdir(parents=True, exist_ok=True)
    (config_dir / "managed-root" / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (config_dir / "managed-commands" / "gpd" / "update.md").parent.mkdir(parents=True, exist_ok=True)
    (config_dir / "managed-commands" / "gpd" / "update.md").write_text("body\n", encoding="utf-8")
    (config_dir / "managed-flat" / "gpd-update.md").parent.mkdir(parents=True, exist_ok=True)
    (config_dir / "managed-flat" / "gpd-update.md").write_text("body\n", encoding="utf-8")
    (config_dir / "managed-agents" / "gpd-check-proof.toml").parent.mkdir(parents=True, exist_ok=True)
    (config_dir / "managed-agents" / "gpd-check-proof.toml").write_text("prompt = 'ok'\n", encoding="utf-8")

    monkeypatch.setattr(
        "gpd.hooks.install_metadata.get_managed_install_surface_policy",
        lambda runtime=None: ManagedInstallSurfacePolicy(
            gpd_content_globs=("managed-root/**/*",),
            nested_command_globs=("managed-commands/gpd/**/*",),
            flat_command_globs=("managed-flat/gpd-*.md",),
            managed_agent_globs=("managed-agents/gpd-*.toml",),
        ),
    )

    surface = inspect_managed_install_surface(config_dir)

    assert surface.has_gpd_content is True
    assert surface.has_nested_commands is True
    assert surface.has_flat_commands is True
    assert surface.has_managed_agents is True


def test_inspect_managed_install_surface_does_not_fall_back_to_legacy_literal_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / ".custom-runtime"
    (config_dir / "get-physics-done" / "VERSION").parent.mkdir(parents=True, exist_ok=True)
    (config_dir / "get-physics-done" / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (config_dir / "commands" / "gpd" / "update.md").parent.mkdir(parents=True, exist_ok=True)
    (config_dir / "commands" / "gpd" / "update.md").write_text("body\n", encoding="utf-8")
    (config_dir / "command" / "gpd-update.md").parent.mkdir(parents=True, exist_ok=True)
    (config_dir / "command" / "gpd-update.md").write_text("body\n", encoding="utf-8")
    (config_dir / "agents" / "gpd-check-proof.md").parent.mkdir(parents=True, exist_ok=True)
    (config_dir / "agents" / "gpd-check-proof.md").write_text("body\n", encoding="utf-8")

    monkeypatch.setattr(
        "gpd.hooks.install_metadata.get_managed_install_surface_policy",
        lambda runtime=None: ManagedInstallSurfacePolicy(),
    )

    surface = inspect_managed_install_surface(config_dir)

    assert surface.has_gpd_content is False
    assert surface.has_nested_commands is False
    assert surface.has_flat_commands is False
    assert surface.has_managed_agents is False


def test_load_install_manifest_explicit_target_status_rejects_legacy_manifests(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / ".custom-runtime"
    config_dir.mkdir()
    (config_dir / "gpd-file-manifest.json").write_text(
        '{"runtime": "test-runtime", "install_scope": "local"}',
        encoding="utf-8",
    )

    state, payload, explicit_target = load_install_manifest_explicit_target_status(config_dir)

    assert state == "missing_explicit_target"
    assert payload == {"runtime": "test-runtime", "install_scope": "local"}
    assert explicit_target is None


def test_load_install_manifest_snapshot_classifies_identity_metadata(tmp_path: Path) -> None:
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    payload = {"runtime": "codex", "install_scope": " global ", "explicit_target": True}
    (config_dir / "gpd-file-manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    snapshot = load_install_manifest_snapshot(config_dir)

    assert isinstance(snapshot, InstallManifestSnapshot)
    assert snapshot.config_dir == config_dir
    assert snapshot.manifest_path == config_dir / "gpd-file-manifest.json"
    assert snapshot.exists_as_object is True
    assert snapshot.parse_state == "ok"
    assert snapshot.payload == payload
    assert snapshot.runtime_state == "ok"
    assert snapshot.runtime == "codex"
    assert snapshot.scope_state == "ok"
    assert snapshot.install_scope == "global"
    assert snapshot.explicit_target_state == "ok"
    assert snapshot.explicit_target is True
    assert snapshot.matches_candidate(runtime="codex", scope="global") is True
    assert snapshot.matches_candidate(runtime="claude-code", scope="global") is False
    assert snapshot.matches_candidate(runtime="codex", scope="local") is False


def test_manifest_loader_wrappers_preserve_snapshot_statuses(tmp_path: Path) -> None:
    config_dir = tmp_path / ".retired-runtime"
    config_dir.mkdir()
    payload = {"runtime": "retired-runtime", "install_scope": "workspace"}
    (config_dir / "gpd-file-manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    snapshot = load_install_manifest_snapshot(config_dir)

    assert load_install_manifest_state(config_dir) == (snapshot.parse_state, snapshot.payload)
    assert load_install_manifest_runtime_status(config_dir) == (
        snapshot.runtime_state,
        snapshot.payload,
        snapshot.runtime,
    )
    assert load_install_manifest_scope_status(config_dir) == (
        snapshot.scope_state,
        snapshot.payload,
        snapshot.install_scope,
    )
    assert load_install_manifest_explicit_target_status(config_dir) == (
        snapshot.explicit_target_state,
        snapshot.payload,
        snapshot.explicit_target,
    )
