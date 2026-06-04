"""Regression tests for descriptor-owned public command prefixes in projections."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import gpd.adapters as adapters_module
import gpd.adapters.base as base_module
import gpd.adapters.claude_code as claude_module
import gpd.adapters.codex as codex_module
import gpd.adapters.gemini as gemini_module
import gpd.adapters.install_utils as install_utils_module
import gpd.adapters.opencode as opencode_module
from gpd.adapters.install_utils import (
    COMPACT_HELP_BRIDGE_SHIM_SENTINEL,
    COMPACT_STAGED_COMMAND_SHIM_SENTINEL,
    COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL,
    project_markdown_for_runtime,
)
from gpd.adapters.runtime_catalog import get_runtime_descriptor

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src/gpd"
COMMANDS_DIR = SRC_ROOT / "commands"

NON_NATIVE_RUNTIME_PUBLIC_PREFIXES = (
    ("codex", "$public-"),
    ("gemini", "/public:"),
    ("opencode", "/public-"),
)

COMPACT_SHIM_PROJECTION_CASES = (
    ("new-project", COMPACT_STAGED_COMMAND_SHIM_SENTINEL),
    ("help", COMPACT_HELP_BRIDGE_SHIM_SENTINEL),
    ("settings", COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL),
    ("compare-experiment", COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL),
    ("dimensional-analysis", COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL),
    ("review-knowledge", COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL),
)


def _descriptor_with_public_prefix(runtime: str, public_prefix: str):
    return replace(get_runtime_descriptor(runtime), public_command_surface_prefix=public_prefix)


def _patch_runtime_descriptor_public_prefix(monkeypatch: pytest.MonkeyPatch, runtime: str, public_prefix: str):
    descriptor = _descriptor_with_public_prefix(runtime, public_prefix)

    def fake_get_runtime_descriptor(candidate: str):
        if candidate == runtime:
            return descriptor
        return get_runtime_descriptor(candidate)

    for module in (
        adapters_module,
        base_module,
        codex_module,
        gemini_module,
        install_utils_module,
        opencode_module,
    ):
        monkeypatch.setattr(module, "get_runtime_descriptor", fake_get_runtime_descriptor)

    return descriptor


def _runtime_label_guidance_lines(text: str) -> tuple[str, ...]:
    return tuple(line for line in text.splitlines() if "runtime label" in line.casefold())


@pytest.mark.parametrize(("runtime", "public_prefix"), NON_NATIVE_RUNTIME_PUBLIC_PREFIXES)
@pytest.mark.parametrize(("command_name", "sentinel"), COMPACT_SHIM_PROJECTION_CASES)
def test_compact_shims_use_descriptor_public_prefix_through_runtime_projection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    runtime: str,
    public_prefix: str,
    command_name: str,
    sentinel: str,
) -> None:
    descriptor = _patch_runtime_descriptor_public_prefix(monkeypatch, runtime, public_prefix)
    target_dir = tmp_path / descriptor.config_dir_name

    projected = project_markdown_for_runtime(
        (COMMANDS_DIR / f"{command_name}.md").read_text(encoding="utf-8"),
        runtime=runtime,
        path_prefix=f"./{descriptor.config_dir_name}/",
        surface_kind="command",
        install_scope="--local",
        src_root=SRC_ROOT,
        workflow_target_dir=target_dir,
        command_name=command_name,
    )

    public_label = f"{public_prefix}{command_name}"
    default_prefix = get_runtime_descriptor(runtime).public_command_surface_prefix
    runtime_label_guidance = _runtime_label_guidance_lines(projected)

    assert sentinel in projected
    assert f'command="{public_label}"' in projected
    assert any(public_prefix in line and "native" in line.casefold() for line in runtime_label_guidance)
    assert f'command="{default_prefix}{command_name}"' not in projected
    assert all(default_prefix not in line for line in runtime_label_guidance)


def test_codex_projection_uses_descriptor_public_prefix_for_command_references(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("codex", "$public-")
    monkeypatch.setattr(codex_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = codex_module.CodexAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
Treat `gpd:` as the canonical command family.
Use gpd:help and /gpd:settings when discussing runtime commands.
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "`$public-`" in projected
    assert "$public-help" in projected
    assert "$public-settings" in projected
    assert "$gpd-help" not in projected
    assert "$gpd-settings" not in projected
    assert "$gpd-..." not in projected


def test_gemini_projection_uses_descriptor_public_prefix_for_runtime_note(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("gemini", "/public:")
    monkeypatch.setattr(gemini_module, "get_runtime_descriptor", lambda runtime: descriptor)
    monkeypatch.setattr(base_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = gemini_module.GeminiAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
```bash
gpd status
```
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "/public:..." in projected
    assert "/gpd:..." not in projected
    assert "python -m gpd status" in projected


def test_gemini_projection_uses_descriptor_public_prefix_for_command_references(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("gemini", "/public:")
    monkeypatch.setattr(gemini_module, "get_runtime_descriptor", lambda runtime: descriptor)
    monkeypatch.setattr(base_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = gemini_module.GeminiAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
Treat `gpd:` as the canonical command family.
Use gpd:help and /gpd:settings when discussing runtime commands.
Do not rewrite gpd:not-a-command or /tmp/gpd:help.
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "`/public:`" in projected
    assert "/public:help" in projected
    assert "/public:settings" in projected
    assert "Use gpd:help" not in projected
    assert "/gpd:settings" not in projected
    assert "gpd:not-a-command" in projected
    assert "/tmp/gpd:help" in projected


def test_claude_projection_uses_descriptor_public_prefix_for_command_references(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("claude-code", "/public:")
    monkeypatch.setattr(base_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = claude_module.ClaudeCodeAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
Treat `gpd:` as the canonical command family.
Use gpd:help and /gpd:settings when discussing runtime commands.
Do not rewrite gpd:not-a-command or /tmp/gpd:help.
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "`/public:`" in projected
    assert "/public:help" in projected
    assert "/public:settings" in projected
    assert "Use gpd:help" not in projected
    assert "/gpd:settings" not in projected
    assert "gpd:not-a-command" in projected
    assert "/tmp/gpd:help" in projected


def test_opencode_projection_uses_descriptor_public_prefix_for_command_references(monkeypatch) -> None:
    descriptor = _descriptor_with_public_prefix("opencode", "/public-")
    monkeypatch.setattr(opencode_module, "get_runtime_descriptor", lambda runtime: descriptor)
    monkeypatch.setattr(base_module, "get_runtime_descriptor", lambda runtime: descriptor)

    projected = opencode_module.OpenCodeAdapter().project_markdown_surface(
        """---
description: Prefix drift probe
---
Treat `gpd:` as the canonical command family.
Use gpd:help and /gpd:settings when discussing runtime commands.
""",
        surface_kind="command",
        path_prefix="",
        command_name="prefix-drift-probe",
        bridge_command="python -m gpd",
    )

    assert "`/public-`" in projected
    assert "/public-help" in projected
    assert "/public-settings" in projected
    assert "gpd-help" not in projected
    assert "/gpd-settings" not in projected
