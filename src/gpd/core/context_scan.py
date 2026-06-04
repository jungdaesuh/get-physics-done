"""Research-file scan helpers for context assembly."""

from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import GPD_INSTALL_DIR_NAME
from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.core.constants import PLANNING_DIR_NAME

__all__ = [
    "_discover_research_file_samples",
    "_ignore_dirs",
    "_research_scan_max_depth_for_directory",
    "_runtime_config_dirs",
    "_runtime_ignored_scan_paths",
    "_should_skip_research_scan_entry",
]


_RESEARCH_EXTENSIONS = frozenset(
    {
        ".bib",
        ".c",
        ".cc",
        ".cls",
        ".cpp",
        ".csv",
        ".cu",
        ".cuh",
        ".cxx",
        ".dat",
        ".f",
        ".f03",
        ".f08",
        ".f77",
        ".f90",
        ".f95",
        ".fits",
        ".for",
        ".ftn",
        ".h",
        ".h5",
        ".hdf5",
        ".hh",
        ".hpp",
        ".hxx",
        ".ipynb",
        ".jl",
        ".m",
        ".mat",
        ".nb",
        ".npy",
        ".npz",
        ".pdf",
        ".py",
        ".root",
        ".sty",
        ".tex",
        ".tsv",
    }
)
_RESEARCH_FILE_SAMPLE_LIMIT = 5
_RESEARCH_SCAN_MAX_DEPTH = 3
_RESEARCH_FOCUSED_SCAN_MAX_DEPTH = 6
_RESEARCH_FOCUSED_SCAN_DIR_NAMES = frozenset(
    {
        "analysis",
        "analyses",
        "bibliography",
        "code",
        "data",
        "datasets",
        "notebook",
        "notebooks",
        "paper",
        "papers",
        "refs",
        "references",
        "script",
        "scripts",
        "simulation",
        "simulations",
        "source",
        "src",
    }
)


def _runtime_config_dirs() -> frozenset[str]:
    """Return the live runtime config-dir inventory."""

    return frozenset(descriptor.config_dir_name for descriptor in iter_runtime_descriptors())


def _runtime_ignored_scan_paths() -> frozenset[tuple[str, ...]]:
    """Return runtime-owned path suffixes to skip during research scans."""

    return frozenset((descriptor.config_dir_name,) for descriptor in iter_runtime_descriptors())


def _ignore_dirs() -> frozenset[str]:
    """Return directory names excluded from research-file scans."""

    return frozenset(
        {
            ".git",
            PLANNING_DIR_NAME,
            *_runtime_config_dirs(),
            ".venv",
            ".eggs",
            ".nox",
            ".tox",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".vscode",
            ".idea",
            "build",
            "cmake-build-debug",
            "cmake-build-release",
            "dist",
            "node_modules",
            "target",
            "__pycache__",
            GPD_INSTALL_DIR_NAME,
        }
    )


def _should_skip_research_scan_entry(cwd: Path, entry: Path) -> bool:
    """Return whether *entry* should be skipped during research-file discovery."""

    if entry.name in _ignore_dirs():
        return True

    try:
        relative_parts = entry.relative_to(cwd).parts
    except ValueError:
        return False
    for ignored_parts in _runtime_ignored_scan_paths():
        ignored_length = len(ignored_parts)
        if ignored_length == 0 or len(relative_parts) < ignored_length:
            continue
        for offset in range(len(relative_parts) - ignored_length + 1):
            if relative_parts[offset : offset + ignored_length] == ignored_parts:
                return True
    return False


def _research_scan_max_depth_for_directory(cwd: Path, directory: Path) -> int:
    """Return the depth limit for this bounded research-file scan branch."""

    try:
        relative_parts = directory.relative_to(cwd).parts
    except ValueError:
        return _RESEARCH_SCAN_MAX_DEPTH
    if any(part.casefold() in _RESEARCH_FOCUSED_SCAN_DIR_NAMES for part in relative_parts):
        return _RESEARCH_FOCUSED_SCAN_MAX_DEPTH
    return _RESEARCH_SCAN_MAX_DEPTH


def _discover_research_file_samples(cwd: Path) -> list[str]:
    """Return bounded project-relative research-looking file samples."""

    samples: list[str] = []

    def _walk(directory: Path, depth: int) -> None:
        if (
            depth > _research_scan_max_depth_for_directory(cwd, directory)
            or len(samples) >= _RESEARCH_FILE_SAMPLE_LIMIT
        ):
            return
        try:
            entries = sorted(directory.iterdir())
        except (PermissionError, FileNotFoundError):
            return
        for entry in entries:
            if len(samples) >= _RESEARCH_FILE_SAMPLE_LIMIT:
                return
            if _should_skip_research_scan_entry(cwd, entry):
                continue
            if entry.is_dir():
                _walk(entry, depth + 1)
            elif entry.is_file() and entry.suffix.lower() in _RESEARCH_EXTENSIONS:
                try:
                    sample = entry.relative_to(cwd).as_posix()
                except ValueError:
                    sample = entry.as_posix()
                samples.append(sample)

    _walk(cwd, 0)
    return sorted(samples)
