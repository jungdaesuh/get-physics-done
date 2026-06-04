"""Target registry for checked-in generated surface artifacts."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from gpd.core.public_surface_renderer import (
    public_surface_block_ids,
    public_surface_context,
    render_public_surface_block,
    runtime_doc_filename,
    runtime_quickstart_block_id,
)
from scripts.generated_region_support import (
    GeneratedRegionDiff,
    GeneratedRegionSpec,
    check_region_inventory,
    replace_regions,
    unified_diff_text,
)


@dataclass(frozen=True, slots=True)
class GeneratedRegionTarget:
    surface_id: str
    path: Path
    spec: GeneratedRegionSpec
    render_body: Callable[[str], str]
    required_blocks: tuple[str, ...]
    allowed_duplicate_blocks: tuple[str, ...] = ()
    inventory_label: str = "generated marker inventory"
    diff_block_id: str = "generated-regions"


@dataclass(frozen=True, slots=True)
class GeneratedTextTarget:
    surface_id: str
    path: Path
    render_text: Callable[[], str]
    diff_block_id: str


PUBLIC_SURFACE_MARKER_PREFIX = "gpd-public-surface"
PUBLIC_SURFACE_REGION_SPEC = GeneratedRegionSpec(
    marker_prefix=PUBLIC_SURFACE_MARKER_PREFIX,
    known_block_ids=lambda: frozenset(public_surface_block_ids()),
    block_label="public surface generated block",
    invalid_block_id_message="Generated public surface block ids must be kebab-case: {block_id!r}",
)

HELP_SURFACE_MARKER_PREFIX = "gpd-help"
HELP_WORKFLOW_PATH = Path("src/gpd/specs/workflows/help.md")
HELP_DETAIL_REFERENCE_PATH = Path("src/gpd/specs/references/help/detailed-command-reference.md")


def _resolve_path(path: Path, *, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def check_region_target(target: GeneratedRegionTarget, *, repo_root: Path) -> tuple[GeneratedRegionDiff, ...]:
    path = _resolve_path(target.path, repo_root=repo_root)
    text = path.read_text(encoding="utf-8")
    updated, block_ids = replace_regions(text, spec=target.spec, render_body=target.render_body, path=path)
    diffs: list[GeneratedRegionDiff] = []
    if updated != text:
        diffs.append(
            GeneratedRegionDiff(
                path=path,
                block_id=", ".join(dict.fromkeys(block_ids)) or target.diff_block_id,
                diff=unified_diff_text(updated, text, path=path, block_id=target.diff_block_id),
            )
        )
    diffs.extend(
        check_region_inventory(
            text,
            spec=target.spec,
            required_blocks=target.required_blocks,
            allowed_duplicate_blocks=target.allowed_duplicate_blocks,
            path=path,
            label=target.inventory_label,
        )
    )
    return tuple(diffs)


def update_region_target(target: GeneratedRegionTarget, *, repo_root: Path) -> bool:
    path = _resolve_path(target.path, repo_root=repo_root)
    original = path.read_text(encoding="utf-8")
    updated, _block_ids = replace_regions(original, spec=target.spec, render_body=target.render_body, path=path)
    inventory_diffs = check_region_inventory(
        updated,
        spec=target.spec,
        required_blocks=target.required_blocks,
        allowed_duplicate_blocks=target.allowed_duplicate_blocks,
        path=path,
        label=target.inventory_label,
    )
    if inventory_diffs:
        raise ValueError(inventory_diffs[0].diff.strip())
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def check_text_target(target: GeneratedTextTarget, *, repo_root: Path) -> tuple[GeneratedRegionDiff, ...]:
    path = _resolve_path(target.path, repo_root=repo_root)
    expected = target.render_text()
    current = path.read_text(encoding="utf-8")
    if current == expected:
        return ()
    return (
        GeneratedRegionDiff(
            path=path,
            block_id=target.diff_block_id,
            diff=unified_diff_text(expected, current, path=path, block_id=target.diff_block_id),
        ),
    )


def update_text_target(target: GeneratedTextTarget, *, repo_root: Path) -> bool:
    path = _resolve_path(target.path, repo_root=repo_root)
    expected = target.render_text()
    if path.read_text(encoding="utf-8") == expected:
        return False
    path.write_text(expected, encoding="utf-8")
    return True


def resolve_target_paths(
    targets: Sequence[GeneratedRegionTarget | GeneratedTextTarget],
    *,
    repo_root: Path,
) -> tuple[Path, ...]:
    return tuple(_resolve_path(target.path, repo_root=repo_root) for target in targets)


def public_surface_region_targets() -> tuple[GeneratedRegionTarget, ...]:
    runtime_doc_targets = tuple(
        GeneratedRegionTarget(
            surface_id=f"public-runtime-doc:{surface.runtime_name}",
            path=Path("docs") / runtime_doc_filename(surface),
            spec=PUBLIC_SURFACE_REGION_SPEC,
            render_body=render_public_surface_block,
            required_blocks=(runtime_quickstart_block_id(surface),),
            inventory_label="public surface marker inventory",
        )
        for surface in public_surface_context().runtime_surfaces
    )
    os_doc_blocks = (
        "runtime-doc-links",
        "os-install-matrix",
        "supported-runtimes-table",
        "os-next-steps-table",
        "recovery-note",
    )
    os_doc_targets = tuple(
        GeneratedRegionTarget(
            surface_id=f"public-os-doc:{os_name}",
            path=Path(f"docs/{os_name}.md"),
            spec=PUBLIC_SURFACE_REGION_SPEC,
            render_body=render_public_surface_block,
            required_blocks=os_doc_blocks,
            inventory_label="public surface marker inventory",
        )
        for os_name in ("macos", "linux", "windows")
    )
    return (
        GeneratedRegionTarget(
            surface_id="public-readme",
            path=Path("README.md"),
            spec=PUBLIC_SURFACE_REGION_SPEC,
            render_body=render_public_surface_block,
            required_blocks=(
                "terminal-runtime-bridge",
                "beginner-startup-ladder",
                "recovery-note",
                "local-cli-bridge-summary",
                "supported-runtimes-table",
                "recovery-note",
                "local-cli-bridge-summary",
            ),
            allowed_duplicate_blocks=("recovery-note", "local-cli-bridge-summary"),
            inventory_label="public surface marker inventory",
        ),
        GeneratedRegionTarget(
            surface_id="public-docs-readme",
            path=Path("docs/README.md"),
            spec=PUBLIC_SURFACE_REGION_SPEC,
            render_body=render_public_surface_block,
            required_blocks=(
                "beginner-preflight",
                "beginner-caveats",
                "beginner-startup-ladder",
                "recovery-note",
                "terminal-runtime-bridge",
                "post-start-settings",
            ),
            inventory_label="public surface marker inventory",
        ),
        *os_doc_targets,
        *runtime_doc_targets,
        GeneratedRegionTarget(
            surface_id="public-help-workflow",
            path=HELP_WORKFLOW_PATH,
            spec=PUBLIC_SURFACE_REGION_SPEC,
            render_body=render_public_surface_block,
            required_blocks=("local-cli-bridge-summary", "recovery-note"),
            inventory_label="public surface marker inventory",
        ),
    )


def _help_region_spec(block_ids: tuple[str, ...]) -> GeneratedRegionSpec:
    return GeneratedRegionSpec(
        marker_prefix=HELP_SURFACE_MARKER_PREFIX,
        known_block_ids=lambda: block_ids,
        block_label="help surface block",
    )


def help_surface_region_targets() -> tuple[GeneratedRegionTarget, ...]:
    from gpd.core.help_renderer import (  # noqa: PLC0415
        render_command_index_markdown,
        render_default_help_markdown,
        render_detailed_command_reference_markdown,
        render_quick_start_markdown,
        render_root_detailed_command_reference_markdown,
    )

    root_renderers: dict[str, Callable[[], str]] = {
        "quick-start": render_quick_start_markdown,
        "command-index": render_command_index_markdown,
        "detailed-command-reference": render_root_detailed_command_reference_markdown,
        "default": render_default_help_markdown,
    }
    detail_renderers: dict[str, Callable[[], str]] = {
        "detailed-command-reference": render_detailed_command_reference_markdown,
    }
    root_block_ids = tuple(root_renderers)
    detail_block_ids = tuple(detail_renderers)
    return (
        GeneratedRegionTarget(
            surface_id="help-workflow",
            path=HELP_WORKFLOW_PATH,
            spec=_help_region_spec(root_block_ids),
            render_body=lambda block_id: root_renderers[block_id](),
            required_blocks=root_block_ids,
            inventory_label="help surface marker inventory",
            diff_block_id="help-surface-regions",
        ),
        GeneratedRegionTarget(
            surface_id="help-detailed-reference",
            path=HELP_DETAIL_REFERENCE_PATH,
            spec=_help_region_spec(detail_block_ids),
            render_body=lambda block_id: detail_renderers[block_id](),
            required_blocks=detail_block_ids,
            inventory_label="help surface marker inventory",
            diff_block_id="help-surface-regions",
        ),
    )


def repo_graph_region_targets(contract: dict[str, object]) -> tuple[GeneratedRegionTarget, ...]:
    from scripts.repo_graph_contract import (  # noqa: PLC0415
        GRAPH_PATH,
        REPO_GRAPH_BLOCK_IDS,
        REPO_GRAPH_REGION_SPEC,
        _render_repo_graph_region_body,
    )

    return (
        GeneratedRegionTarget(
            surface_id="repo-graph-readme",
            path=GRAPH_PATH,
            spec=REPO_GRAPH_REGION_SPEC,
            render_body=lambda block_id: _render_repo_graph_region_body(block_id, contract),
            required_blocks=REPO_GRAPH_BLOCK_IDS,
            inventory_label="repo graph marker inventory",
            diff_block_id="readme",
        ),
    )


def repo_graph_text_targets(contract: dict[str, object]) -> tuple[GeneratedTextTarget, ...]:
    from scripts.repo_graph_contract import CONTRACT_PATH  # noqa: PLC0415

    return (
        GeneratedTextTarget(
            surface_id="repo-graph-contract",
            path=CONTRACT_PATH,
            render_text=lambda: json.dumps(contract, indent=2) + "\n",
            diff_block_id="contract",
        ),
    )


__all__ = [
    "GeneratedRegionTarget",
    "GeneratedTextTarget",
    "HELP_DETAIL_REFERENCE_PATH",
    "HELP_SURFACE_MARKER_PREFIX",
    "HELP_WORKFLOW_PATH",
    "PUBLIC_SURFACE_MARKER_PREFIX",
    "PUBLIC_SURFACE_REGION_SPEC",
    "check_region_target",
    "check_text_target",
    "help_surface_region_targets",
    "public_surface_region_targets",
    "repo_graph_region_targets",
    "repo_graph_text_targets",
    "resolve_target_paths",
    "update_region_target",
    "update_text_target",
]
