"""Refresh or check generated public onboarding surface regions."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(repo_root), str(repo_root / "src")]

from gpd.core.public_surface_renderer import (
    public_surface_block_ids,
    render_public_surface_block,
)
from scripts.generated_region_support import (
    GeneratedRegionDiff,
    check_region_inventory,
    marker_pair,
    render_region,
    replace_regions,
    unified_diff_text,
    write_stale_check_result,
)
from scripts.generated_surface_targets import (
    PUBLIC_SURFACE_MARKER_PREFIX,
    PUBLIC_SURFACE_REGION_SPEC,
    public_surface_region_targets,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKER_PREFIX = PUBLIC_SURFACE_MARKER_PREFIX


@dataclass(frozen=True, slots=True)
class PublicSurfaceTarget:
    path: Path
    required_blocks: tuple[str, ...]
    allowed_duplicate_blocks: tuple[str, ...] = ()


_PUBLIC_REGION_SPEC = PUBLIC_SURFACE_REGION_SPEC


def generated_region_markers(block_id: str) -> tuple[str, str]:
    return marker_pair(_PUBLIC_REGION_SPEC, block_id)


def render_generated_region(block_id: str, body: str) -> str:
    return render_region(_PUBLIC_REGION_SPEC, block_id, body)


def default_target_paths() -> tuple[Path, ...]:
    return tuple(target.path for target in default_target_contracts())


def default_target_contracts() -> tuple[PublicSurfaceTarget, ...]:
    return tuple(
        PublicSurfaceTarget(
            path=target.path,
            required_blocks=target.required_blocks,
            allowed_duplicate_blocks=target.allowed_duplicate_blocks,
        )
        for target in public_surface_region_targets()
    )


def _replace_generated_regions_in_text(text: str, *, path: Path | None = None) -> tuple[str, tuple[str, ...]]:
    return replace_regions(
        text,
        spec=_PUBLIC_REGION_SPEC,
        render_body=render_public_surface_block,
        path=path,
    )


def check_generated_region_inventory(
    text: str,
    *,
    required_blocks: Sequence[str],
    allowed_duplicate_blocks: Sequence[str] = (),
    path: Path | None = None,
) -> tuple[GeneratedRegionDiff, ...]:
    """Check that a default target still carries its declared generated regions."""

    return check_region_inventory(
        text,
        spec=_PUBLIC_REGION_SPEC,
        required_blocks=required_blocks,
        allowed_duplicate_blocks=allowed_duplicate_blocks,
        path=path,
        label="public surface marker inventory",
    )


def replace_generated_regions(text: str) -> str:
    updated, _block_ids = _replace_generated_regions_in_text(text)
    return updated


def check_generated_regions(text: str, *, path: Path | None = None) -> tuple[GeneratedRegionDiff, ...]:
    updated, block_ids = _replace_generated_regions_in_text(text, path=path)
    if updated == text:
        return ()
    return (
        GeneratedRegionDiff(
            path=path,
            block_id=", ".join(dict.fromkeys(block_ids)),
            diff=unified_diff_text(updated, text, path=path, block_id="generated-regions"),
        ),
    )


def _resolve_paths(paths: Sequence[Path] | None, *, repo_root: Path) -> tuple[Path, ...]:
    selected_paths = tuple(paths) if paths else default_target_paths()
    return tuple(path if path.is_absolute() else repo_root / path for path in selected_paths)


def _default_target_contract_map(*, repo_root: Path) -> dict[Path, PublicSurfaceTarget]:
    return {(repo_root / target.path).resolve(): target for target in default_target_contracts()}


def check_generated_files(
    paths: Sequence[Path] | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[GeneratedRegionDiff, ...]:
    diffs: list[GeneratedRegionDiff] = []
    target_contracts = _default_target_contract_map(repo_root=repo_root)
    for path in _resolve_paths(paths, repo_root=repo_root):
        content = path.read_text(encoding="utf-8")
        diffs.extend(check_generated_regions(content, path=path))
        target = target_contracts.get(path.resolve())
        if target is not None:
            diffs.extend(
                check_generated_region_inventory(
                    content,
                    required_blocks=target.required_blocks,
                    allowed_duplicate_blocks=target.allowed_duplicate_blocks,
                    path=path,
                )
            )
    return tuple(diffs)


def update_generated_files(
    paths: Sequence[Path] | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[Path, ...]:
    updated_paths: list[Path] = []
    target_contracts = _default_target_contract_map(repo_root=repo_root)
    for path in _resolve_paths(paths, repo_root=repo_root):
        original = path.read_text(encoding="utf-8")
        updated = replace_generated_regions(original)
        target = target_contracts.get(path.resolve())
        if target is not None:
            diffs = check_generated_region_inventory(
                updated,
                required_blocks=target.required_blocks,
                allowed_duplicate_blocks=target.allowed_duplicate_blocks,
                path=path,
            )
            if diffs:
                raise ValueError(diffs[0].diff.strip())
        if updated == original:
            continue
        path.write_text(updated, encoding="utf-8")
        updated_paths.append(path)
    return tuple(updated_paths)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="specific files to check or update")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated public surface regions without modifying files",
    )
    parser.add_argument(
        "--list-blocks",
        action="store_true",
        help="print supported public surface generated block ids",
    )
    args = parser.parse_args(argv)

    if args.list_blocks:
        for block_id in public_surface_block_ids():
            print(block_id)
        return 0

    if args.check:
        diffs = check_generated_files(args.paths)
        if diffs:
            return write_stale_check_result(
                diffs,
                heading="Public surface generated regions are stale.",
                regenerate_command="uv run python scripts/render_public_surface.py",
            )
        return 0

    updated_paths = update_generated_files(args.paths)
    for path in updated_paths:
        print(path.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
