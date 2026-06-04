"""Refresh or check generated GPD help workflow marker regions."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from gpd.core.help_renderer import (
    render_command_index_markdown,
    render_default_help_markdown,
    render_detailed_command_reference_markdown,
    render_quick_start_markdown,
    render_root_detailed_command_reference_markdown,
)
from scripts.generated_region_support import (
    GeneratedRegionDiff,
    GeneratedRegionSpec,
    check_region_inventory,
    marker_pair,
    render_region,
    replace_regions,
    unified_diff_text,
    write_stale_check_result,
)

HelpSurfaceDiff = GeneratedRegionDiff

REPO_ROOT = Path(__file__).resolve().parent.parent
HELP_WORKFLOW_PATH = Path("src/gpd/specs/workflows/help.md")
HELP_DETAIL_REFERENCE_PATH = Path("src/gpd/specs/references/help/detailed-command-reference.md")
MARKER_PREFIX = "gpd-help"


_ROOT_HELP_BLOCK_RENDERERS: dict[str, Callable[[], str]] = {
    "quick-start": render_quick_start_markdown,
    "command-index": render_command_index_markdown,
    "detailed-command-reference": render_root_detailed_command_reference_markdown,
    "default": render_default_help_markdown,
}

_DETAIL_HELP_BLOCK_RENDERERS: dict[str, Callable[[], str]] = {
    "detailed-command-reference": render_detailed_command_reference_markdown,
}


def help_surface_block_ids() -> tuple[str, ...]:
    return tuple(_ROOT_HELP_BLOCK_RENDERERS)


def help_detail_surface_block_ids() -> tuple[str, ...]:
    return tuple(_DETAIL_HELP_BLOCK_RENDERERS)


_HELP_REGION_SPEC = GeneratedRegionSpec(
    marker_prefix=MARKER_PREFIX,
    known_block_ids=help_surface_block_ids,
    block_label="help surface block",
)


def help_surface_markers(block_id: str) -> tuple[str, str]:
    if block_id not in help_surface_block_ids():
        raise ValueError(f"Unknown help surface block {block_id!r}")
    return marker_pair(_HELP_REGION_SPEC, block_id)


def extract_help_surface_region(text: str, block_id: str) -> str:
    start_marker, end_marker = help_surface_markers(block_id)
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def render_help_surface_region(block_id: str) -> str:
    if block_id not in _ROOT_HELP_BLOCK_RENDERERS:
        raise ValueError(f"Unknown help surface block {block_id!r}")
    return render_region(_HELP_REGION_SPEC, block_id, _ROOT_HELP_BLOCK_RENDERERS[block_id]())


def _renderers_for_path(path: Path | None) -> dict[str, Callable[[], str]]:
    if path is None:
        return _ROOT_HELP_BLOCK_RENDERERS
    absolute_path = path if path.is_absolute() else REPO_ROOT / path
    if absolute_path.resolve() == (REPO_ROOT / HELP_DETAIL_REFERENCE_PATH).resolve():
        return _DETAIL_HELP_BLOCK_RENDERERS
    return _ROOT_HELP_BLOCK_RENDERERS


def _region_spec_for_renderers(block_renderers: dict[str, Callable[[], str]]) -> GeneratedRegionSpec:
    return GeneratedRegionSpec(
        marker_prefix=MARKER_PREFIX,
        known_block_ids=lambda: tuple(block_renderers),
        block_label="help surface block",
    )


def _check_help_surface_inventory(text: str, *, path: Path | None = None) -> tuple[HelpSurfaceDiff, ...]:
    block_renderers = _renderers_for_path(path)
    return check_region_inventory(
        text,
        spec=_region_spec_for_renderers(block_renderers),
        required_blocks=tuple(block_renderers),
        path=path,
        label="help surface marker inventory",
    )


def _assert_help_surface_inventory_valid(text: str, *, path: Path | None = None) -> None:
    inventory_diffs = _check_help_surface_inventory(text, path=path)
    if inventory_diffs:
        details = "\n".join(diff.diff.rstrip() for diff in inventory_diffs)
        raise ValueError(
            "Cannot update help surface generated regions because marker inventory is invalid.\n" + details
        )


def _replace_help_surface_regions_in_text(text: str, *, path: Path | None = None) -> tuple[str, tuple[str, ...]]:
    block_renderers = _renderers_for_path(path)
    region_spec = _region_spec_for_renderers(block_renderers)
    return replace_regions(
        text,
        spec=region_spec,
        render_body=lambda block_id: block_renderers[block_id](),
        path=path,
    )


def replace_help_surface_text(text: str) -> str:
    updated, _block_ids = _replace_help_surface_regions_in_text(text)
    return updated


def check_help_surface_text(text: str, *, path: Path | None = None) -> tuple[HelpSurfaceDiff, ...]:
    inventory_diffs = _check_help_surface_inventory(text, path=path)
    if inventory_diffs:
        return inventory_diffs

    updated, block_ids = _replace_help_surface_regions_in_text(text, path=path)
    if updated == text:
        return ()
    return (
        HelpSurfaceDiff(
            path=path,
            block_id=", ".join(dict.fromkeys(block_ids)),
            diff=unified_diff_text(updated, text, path=path, block_id="help-surface-regions"),
        ),
    )


def check_help_surface_file(
    path: Path = REPO_ROOT / HELP_WORKFLOW_PATH,
) -> tuple[HelpSurfaceDiff, ...]:
    return check_help_surface_text(path.read_text(encoding="utf-8"), path=path)


def check_help_surface_files() -> tuple[HelpSurfaceDiff, ...]:
    diffs: list[HelpSurfaceDiff] = []
    for relative_path in (HELP_WORKFLOW_PATH, HELP_DETAIL_REFERENCE_PATH):
        diffs.extend(check_help_surface_file(REPO_ROOT / relative_path))
    return tuple(diffs)


def update_help_surface_file(
    path: Path = REPO_ROOT / HELP_WORKFLOW_PATH,
) -> bool:
    original = path.read_text(encoding="utf-8")
    _assert_help_surface_inventory_valid(original, path=path)
    updated, _block_ids = _replace_help_surface_regions_in_text(original, path=path)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def update_help_surface_files() -> tuple[Path, ...]:
    changed: list[Path] = []
    for relative_path in (HELP_WORKFLOW_PATH, HELP_DETAIL_REFERENCE_PATH):
        path = REPO_ROOT / relative_path
        if update_help_surface_file(path):
            changed.append(path)
    return tuple(changed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="specific help surface file to check or update; omit to process all generated help targets",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated help marker regions without modifying the file",
    )
    parser.add_argument(
        "--list-blocks",
        action="store_true",
        help="print supported help generated block ids",
    )
    args = parser.parse_args(argv)

    if args.list_blocks:
        for block_id in help_surface_block_ids():
            print(block_id)
        return 0

    try:
        if args.check:
            diffs = check_help_surface_file(args.path) if args.path is not None else check_help_surface_files()
            if diffs:
                return write_stale_check_result(
                    diffs,
                    heading="Help surface generated regions are stale.",
                    regenerate_command="uv run python scripts/render_help_surface.py",
                )
            return 0

        changed_paths = (
            (REPO_ROOT / args.path,) if args.path is not None and update_help_surface_file(args.path) else ()
        )
        if args.path is None:
            changed_paths = update_help_surface_files()
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    for path in changed_paths:
        print(path.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
