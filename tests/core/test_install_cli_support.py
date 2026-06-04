"""Tests for Typer-free install presentation helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from gpd.core.install_cli_support import (
    InstallSelectionError,
    format_install_header_lines,
    location_example,
    print_install_summary,
    render_install_option_line,
    resolve_runtime_choice,
)


class _InstallAdapter:
    display_name = "Alpha Runtime"
    selection_aliases = ("alpha cli", "alpha runtime")

    def __init__(self, *, local_target: Path | None = None, global_target: Path | None = None) -> None:
        self._local_target = local_target
        self._global_target = global_target

    def resolve_target_dir(self, is_global: bool, cwd: Path) -> Path:
        if is_global:
            return self._global_target or (Path.home() / ".alpha")
        return self._local_target or (cwd / ".alpha")

    def format_command(self, command: str) -> str:
        return f"/alpha:{command}"


def test_format_install_header_lines_uses_psi_branding() -> None:
    assert format_install_header_lines("1.0.0") == (
        "GPD v1.0.0 - Get Physics Done",
        "© 2026 Physical Superintelligence PBC (PSI)",
    )


def test_render_install_option_line_uses_single_line_bracketed_layout() -> None:
    runtime_line = render_install_option_line(1, "Alpha Runtime", "alpha", label_width=13)

    assert runtime_line.plain.startswith("  [1] Alpha Runtime")
    assert runtime_line.plain.endswith("· alpha")
    assert render_install_option_line(1, "Local", "current project only", "./.alpha", label_width=6).plain == (
        "  [1] Local   · current project only · ./.alpha"
    )


def test_resolve_runtime_choice_accepts_numeric_all_and_aliases() -> None:
    adapters = {
        "alpha": _InstallAdapter(),
        "beta": SimpleNamespace(display_name="Beta Runtime", selection_aliases=("beta cli",)),
    }

    def normalize(value: str | None) -> str | None:
        aliases = {"alpha cli": "alpha", "beta cli": "beta"}
        return aliases.get((value or "").strip().casefold())

    assert resolve_runtime_choice(
        "3",
        runtime_names=("alpha", "beta"),
        adapter_lookup=adapters.__getitem__,
        normalize_runtime_name=normalize,
    ) == ["alpha", "beta"]
    assert resolve_runtime_choice(
        "alpha runtime",
        runtime_names=("alpha", "beta"),
        adapter_lookup=adapters.__getitem__,
        normalize_runtime_name=normalize,
    ) == ["alpha"]


def test_resolve_runtime_choice_reports_ambiguous_fuzzy_matches() -> None:
    adapters = {
        "alpha": SimpleNamespace(display_name="Alpha Runtime", selection_aliases=("shared alpha",)),
        "beta": SimpleNamespace(display_name="Beta Runtime", selection_aliases=("shared beta",)),
    }

    with pytest.raises(InstallSelectionError, match="Ambiguous selection"):
        resolve_runtime_choice(
            "shared",
            runtime_names=("alpha", "beta"),
            adapter_lookup=adapters.__getitem__,
            normalize_runtime_name=lambda value: None,
        )


def test_location_example_formats_single_runtime_target_relative_to_cwd(tmp_path: Path) -> None:
    adapter = _InstallAdapter(local_target=tmp_path / ".alpha")

    assert (
        location_example(
            ("alpha",),
            is_global=False,
            action="install",
            cwd=tmp_path,
            adapter_lookup=lambda runtime: adapter,
        )
        == "./.alpha"
    )
    assert (
        location_example(
            ("alpha", "beta"),
            is_global=False,
            action="install",
            cwd=tmp_path,
            adapter_lookup=lambda runtime: adapter,
        )
        == "one config dir per runtime"
    )


def test_print_install_summary_uses_compact_target_and_next_step(tmp_path: Path) -> None:
    console = Console(record=True, width=120)
    adapter = _InstallAdapter(local_target=tmp_path / ".alpha")

    print_install_summary(
        [("alpha", {"target": str(tmp_path / ".alpha"), "agents": 2, "commands": 3})],
        cwd=tmp_path,
        console=console,
        adapter_lookup=lambda runtime: adapter,
        docs_hub_url="https://docs.example.test",
        diagnostics_line="Diagnostics: injected.",
    )

    output = console.export_text()
    assert "Install Summary" in output
    assert "./.alpha" in output
    assert str(tmp_path / ".alpha") not in output
    assert "Docs hub: https://docs.example.test" in output
    assert "Next: open Alpha Runtime in this folder, then run /alpha:start." in output
    assert "Diagnostics: injected." in output
