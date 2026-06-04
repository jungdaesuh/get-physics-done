"""Tests for context research-file scan helpers."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.core import context as context_module
from gpd.core.context import init_new_project
from gpd.core.context_scan import (
    _ignore_dirs,
    _runtime_config_dirs,
    _should_skip_research_scan_entry,
)

_RUNTIME_DESCRIPTORS = iter_runtime_descriptors()
_XDG_RUNTIME_DESCRIPTOR = next(
    (descriptor for descriptor in _RUNTIME_DESCRIPTORS if descriptor.global_config.xdg_subdir),
    None,
)


def _runtime_owned_local_install_dirs(root: Path) -> tuple[Path, ...]:
    """Return runtime-owned local install roots derived from the catalog."""
    paths: list[Path] = []
    for descriptor in _RUNTIME_DESCRIPTORS:
        paths.append(root / descriptor.config_dir_name)
    return tuple(dict.fromkeys(paths))


def test_context_reexports_runtime_scan_helpers() -> None:
    assert context_module._runtime_config_dirs is _runtime_config_dirs
    assert context_module._ignore_dirs is _ignore_dirs
    assert context_module._should_skip_research_scan_entry is _should_skip_research_scan_entry


def test_context_import_does_not_require_adapter_instantiation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import gpd.adapters as adapters

    def _boom():
        raise AssertionError("iter_adapters should not be needed for gpd.core.context import")

    monkeypatch.setattr(adapters, "iter_adapters", _boom)
    sys.modules.pop("gpd.core.context", None)

    context = importlib.import_module("gpd.core.context")
    payload = context.init_new_project(tmp_path)

    expected_runtime_dirs = {descriptor.config_dir_name for descriptor in iter_runtime_descriptors()}
    assert expected_runtime_dirs <= context._runtime_config_dirs()
    assert expected_runtime_dirs <= context._ignore_dirs()
    assert payload["has_research_files"] is False
    assert payload["research_file_samples"] == []


@pytest.mark.skipif(_XDG_RUNTIME_DESCRIPTOR is None, reason="No runtime advertises an XDG mirror path")
def test_research_scan_skips_only_runtime_owned_install_roots(tmp_path: Path) -> None:
    workspace = tmp_path
    assert _XDG_RUNTIME_DESCRIPTOR is not None
    runtime_root = workspace / _XDG_RUNTIME_DESCRIPTOR.config_dir_name
    runtime_root.mkdir()
    xdg_mirror = workspace / ".config" / _XDG_RUNTIME_DESCRIPTOR.global_config.xdg_subdir
    xdg_mirror.mkdir(parents=True)
    foreign_mirror = xdg_mirror / "notes"
    foreign_mirror.mkdir(parents=True)

    assert _should_skip_research_scan_entry(workspace, runtime_root) is True
    assert _should_skip_research_scan_entry(workspace, xdg_mirror) is False
    assert _should_skip_research_scan_entry(workspace, foreign_mirror) is False


def test_detects_research_files(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("import numpy", encoding="utf-8")
    ctx = init_new_project(tmp_path)
    assert ctx["has_research_files"] is True
    assert ctx["research_file_samples"] == ["calc.py"]
    assert "has_existing_project" not in ctx


def test_collects_bounded_sorted_project_relative_research_file_samples(tmp_path: Path) -> None:
    for filename in ("zeta.ipynb", "alpha.py", "epsilon.pdf", "delta.csv", "beta.tex"):
        (tmp_path / filename).write_text("research artifact\n", encoding="utf-8")
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "gamma.jl").write_text('println("research")\n', encoding="utf-8")

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is True
    assert ctx["research_file_samples"] == [
        "alpha.py",
        "beta.tex",
        "delta.csv",
        "epsilon.pdf",
        "notes/gamma.jl",
    ]


def test_research_file_samples_are_depth_limited(tmp_path: Path) -> None:
    deep_dir = tmp_path / "one" / "two" / "three" / "four"
    deep_dir.mkdir(parents=True)
    (deep_dir / "too_deep.py").write_text("print('outside scan')\n", encoding="utf-8")

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is False
    assert ctx["research_file_samples"] == []


def test_research_file_scan_reaches_bounded_focused_research_directories(tmp_path: Path) -> None:
    deep_analysis_dir = tmp_path / "analysis" / "runs" / "2026" / "notebooks"
    deep_analysis_dir.mkdir(parents=True)
    (deep_analysis_dir / "spectrum.nb").write_text("Notebook[{}]\n", encoding="utf-8")

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is True
    assert ctx["research_file_samples"] == ["analysis/runs/2026/notebooks/spectrum.nb"]


@pytest.mark.parametrize("filename", ("draft.pdf", "measurements.csv"))
def test_detects_documented_research_file_extensions(tmp_path: Path, filename: str) -> None:
    (tmp_path / filename).write_text("research artifact\n", encoding="utf-8")

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is True
    assert ctx["research_file_samples"] == [filename]
    assert ctx["needs_research_map"] is True


@pytest.mark.parametrize(
    "filename",
    (
        "analysis.nb",
        "references.bib",
        "observables.dat",
        "samples.h5",
        "array.npy",
        "arrays.npz",
        "simulation.cpp",
        "include/model.hpp",
        "solver.f95",
        "module.f03",
        "paper/style.sty",
        "table.tsv",
    ),
)
def test_detects_common_physics_research_artifacts(tmp_path: Path, filename: str) -> None:
    target = tmp_path / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("research artifact\n", encoding="utf-8")

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is True
    assert ctx["research_file_samples"] == [filename]
    assert ctx["needs_research_map"] is True


def test_research_file_scan_skips_generated_trees(tmp_path: Path) -> None:
    generated = tmp_path / "build" / "simulation"
    generated.mkdir(parents=True)
    (generated / "observables.dat").write_text("generated data\n", encoding="utf-8")

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is False
    assert ctx["research_file_samples"] == []


def test_ignores_runtime_owned_dirs_when_detecting_research_files(tmp_path: Path) -> None:
    for runtime_dir in _runtime_owned_local_install_dirs(tmp_path):
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "mirror.py").write_text("print('runtime mirror')", encoding="utf-8")

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is False
    assert ctx["research_file_samples"] == []
    assert "has_existing_project" not in ctx


def test_detects_non_runtime_config_research_files(tmp_path: Path) -> None:
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "notes.py").write_text("print('research notes')", encoding="utf-8")

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is True
    assert ctx["research_file_samples"] == [".config/notes.py"]
    assert "has_existing_project" not in ctx


@pytest.mark.parametrize("directory_name", ("agents", "hooks", "command"))
def test_detects_user_owned_research_files_in_generic_tool_named_directories(
    tmp_path: Path, directory_name: str
) -> None:
    owned_dir = tmp_path / directory_name
    owned_dir.mkdir()
    (owned_dir / "notes.py").write_text("print('research notes')", encoding="utf-8")

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is True
    assert "has_existing_project" not in ctx


def test_detects_xdg_config_subdir_research_files_inside_a_project(tmp_path: Path) -> None:
    opencode_descriptor = next(descriptor for descriptor in _RUNTIME_DESCRIPTORS if descriptor.global_config.xdg_subdir)
    (tmp_path / ".config" / opencode_descriptor.global_config.xdg_subdir).mkdir(parents=True)
    (tmp_path / ".config" / opencode_descriptor.global_config.xdg_subdir / "notes.py").write_text(
        "print('research notes')", encoding="utf-8"
    )

    ctx = init_new_project(tmp_path)

    assert ctx["has_research_files"] is True
    assert "has_existing_project" not in ctx
