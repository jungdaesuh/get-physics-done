"""Shared scaffolding for flat markdown command surfaces.

The helpers in this module own traversal and manifest bookkeeping mechanics
only. Runtime adapters pass runtime-specific names, renderers, and policies in.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, MutableSet
from dataclasses import dataclass
from pathlib import Path

from gpd.adapters.install_utils import (
    MANIFEST_NAME,
    compact_staged_command_shim_for_runtime,
    compile_markdown_for_runtime,
)


@dataclass(frozen=True, slots=True)
class FlatCommandSurfacePolicy:
    """Policy for a runtime that stores commands in one flat markdown directory."""

    runtime: str
    command_dir_name: str = "command"
    source_prefix: str = "gpd"
    file_prefix: str = "gpd-"
    file_suffix: str = ".md"
    manifest_metadata_key: str | None = None

    @property
    def command_glob_label(self) -> str:
        """Return the required command-surface label used in missing-artifact reports."""
        return f"{self.command_dir_name}/{self.file_prefix}*{self.file_suffix}"

    def is_generated_file_name(self, name: str) -> bool:
        """Return whether *name* is a managed flat command path segment."""
        return (
            "/" not in name
            and "\\" not in name
            and name.startswith(self.file_prefix)
            and name.endswith(self.file_suffix)
            and len(name) > len(self.file_prefix) + len(self.file_suffix)
        )

    def destination_file_name(self, prefix: str, source_stem: str) -> str:
        """Return the destination flat command filename for a source command stem."""
        return f"{prefix}-{source_stem}{self.file_suffix}"

    def command_name_from_file_name(self, name: str) -> str:
        """Return the public command stem represented by a flat command filename."""
        without_suffix = name.removesuffix(self.file_suffix)
        return without_suffix.removeprefix(self.file_prefix)


@dataclass(frozen=True, slots=True)
class FlatCommandRenderContext:
    """Context passed to flat command projection callbacks."""

    policy: FlatCommandSurfacePolicy
    source_path: Path
    dest_path: Path
    dest_name: str
    command_name: str
    path_prefix: str
    workflow_target_dir: Path | None
    gpd_src_root: Path | None
    install_scope: str | None
    bridge_command: str | None
    explicit_target: bool

    @property
    def runtime(self) -> str:
        """Return the runtime id from the surface policy."""
        return self.policy.runtime


CommandTransform = Callable[[str, FlatCommandRenderContext], str | None]
CommandRenderer = Callable[[str, FlatCommandRenderContext], str]


def load_tracked_generated_command_files(
    target_dir: Path,
    policy: FlatCommandSurfacePolicy,
    *,
    manifest_metadata_key: str | None = None,
    include_manifest_files_fallback: bool = True,
) -> tuple[str, ...]:
    """Return trusted generated flat command filenames from a local manifest.

    The metadata key is runtime-owned policy data. The optional ``files``
    fallback mirrors legacy flat-command manifests that only tracked
    ``command/gpd-*.md`` entries in the manifest file map.
    """
    manifest = _load_manifest_mapping(target_dir)
    if manifest is None:
        return ()

    tracked: list[str] = []
    metadata_key = manifest_metadata_key or policy.manifest_metadata_key
    if metadata_key:
        command_files = manifest.get(metadata_key)
        if isinstance(command_files, list):
            tracked.extend(_valid_generated_file_names(command_files, policy))

    if include_manifest_files_fallback:
        manifest_files = manifest.get("files")
        if isinstance(manifest_files, dict):
            prefix = f"{policy.command_dir_name}/"
            for rel_path in manifest_files:
                if not isinstance(rel_path, str) or not rel_path.startswith(prefix):
                    continue
                tracked.extend(_valid_generated_file_names((rel_path.removeprefix(prefix),), policy))

    return tuple(dict.fromkeys(tracked))


def remove_stale_generated_commands(
    command_dir: Path,
    tracked_command_files: Iterable[str],
    policy: FlatCommandSurfacePolicy,
    *,
    keep_command_files: Iterable[str] = (),
) -> tuple[str, ...]:
    """Remove tracked generated command files that are not in *keep_command_files*."""
    keep = {name for name in keep_command_files if policy.is_generated_file_name(name)}
    removed: list[str] = []

    for name in dict.fromkeys(tracked_command_files):
        if not policy.is_generated_file_name(name) or name in keep:
            continue
        command_path = command_dir / name
        try:
            if command_path.is_file():
                command_path.unlink()
                removed.append(name)
        except OSError:
            continue

    return tuple(removed)


def missing_flat_command_artifacts(
    target_dir: Path,
    policy: FlatCommandSurfacePolicy,
    *,
    tracked_command_files: Iterable[str] | None = None,
    manifest_metadata_key: str | None = None,
    include_manifest_files_fallback: bool = True,
) -> tuple[str, ...]:
    """Return missing flat command artifacts for a trusted runtime-owned manifest."""
    command_dir = target_dir / policy.command_dir_name
    tracked = tuple(
        tracked_command_files
        if tracked_command_files is not None
        else load_tracked_generated_command_files(
            target_dir,
            policy,
            manifest_metadata_key=manifest_metadata_key,
            include_manifest_files_fallback=include_manifest_files_fallback,
        )
    )

    if not tracked:
        return (policy.command_glob_label,)

    missing: list[str] = []
    for name in tracked:
        if not policy.is_generated_file_name(name):
            continue
        command_path = command_dir / name
        try:
            if not command_path.is_file():
                missing.append(f"{policy.command_dir_name}/{name}")
        except OSError:
            missing.append(f"{policy.command_dir_name}/{name}")

    if not command_dir.is_dir():
        missing.append(policy.command_glob_label)

    if missing and policy.command_glob_label not in missing:
        missing.append(policy.command_glob_label)

    return tuple(dict.fromkeys(missing))


def copy_flattened_commands(
    src_dir: Path,
    dest_dir: Path,
    policy: FlatCommandSurfacePolicy,
    *,
    path_prefix: str,
    workflow_target_dir: Path | None = None,
    gpd_src_root: Path | None = None,
    install_scope: str | None = None,
    bridge_command: str | None = None,
    explicit_target: bool = False,
    managed_command_files: MutableSet[str] | None = None,
    prefix: str | None = None,
    render_command: CommandRenderer,
    compact_command: CommandTransform | None = None,
    compile_command: CommandRenderer | None = None,
    tracked_command_files: Iterable[str] | None = None,
    cleanup_stale: bool = True,
) -> int:
    """Copy a nested command tree into one flat runtime command directory."""
    if not src_dir.exists():
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    active_prefix = prefix or policy.source_prefix

    if cleanup_stale:
        manifest_root = workflow_target_dir or dest_dir.parent
        tracked = tuple(
            tracked_command_files
            if tracked_command_files is not None
            else load_tracked_generated_command_files(manifest_root, policy)
        )
        remove_stale_generated_commands(dest_dir, tracked, policy)

    return _copy_flattened_command_tree(
        src_dir,
        dest_dir,
        policy,
        current_prefix=active_prefix,
        path_prefix=path_prefix,
        workflow_target_dir=workflow_target_dir,
        gpd_src_root=gpd_src_root,
        install_scope=install_scope,
        bridge_command=bridge_command,
        explicit_target=explicit_target,
        managed_command_files=managed_command_files,
        render_command=render_command,
        compact_command=compact_command or _default_compact_command,
        compile_command=compile_command or _default_compile_command,
    )


def _copy_flattened_command_tree(
    src_dir: Path,
    dest_dir: Path,
    policy: FlatCommandSurfacePolicy,
    *,
    current_prefix: str,
    path_prefix: str,
    workflow_target_dir: Path | None,
    gpd_src_root: Path | None,
    install_scope: str | None,
    bridge_command: str | None,
    explicit_target: bool,
    managed_command_files: MutableSet[str] | None,
    render_command: CommandRenderer,
    compact_command: CommandTransform,
    compile_command: CommandRenderer,
) -> int:
    count = 0
    for entry in sorted(src_dir.iterdir()):
        if entry.is_dir():
            count += _copy_flattened_command_tree(
                entry,
                dest_dir,
                policy,
                current_prefix=f"{current_prefix}-{entry.name}",
                path_prefix=path_prefix,
                workflow_target_dir=workflow_target_dir,
                gpd_src_root=gpd_src_root,
                install_scope=install_scope,
                bridge_command=bridge_command,
                explicit_target=explicit_target,
                managed_command_files=managed_command_files,
                render_command=render_command,
                compact_command=compact_command,
                compile_command=compile_command,
            )
            continue

        if not entry.is_file() or entry.suffix != ".md":
            continue

        dest_name = policy.destination_file_name(current_prefix, entry.stem)
        dest_path = dest_dir / dest_name
        context = FlatCommandRenderContext(
            policy=policy,
            source_path=entry,
            dest_path=dest_path,
            dest_name=dest_name,
            command_name=policy.command_name_from_file_name(dest_name),
            path_prefix=path_prefix,
            workflow_target_dir=workflow_target_dir,
            gpd_src_root=gpd_src_root,
            install_scope=install_scope,
            bridge_command=bridge_command,
            explicit_target=explicit_target,
        )

        source_content = entry.read_text(encoding="utf-8")
        compacted = compact_command(source_content, context)
        content = compacted or source_content
        content = compile_command(content, context)
        content = render_command(content, context)

        dest_path.write_text(content, encoding="utf-8")
        if managed_command_files is not None and policy.is_generated_file_name(dest_name):
            managed_command_files.add(dest_name)
        count += 1

    return count


def _load_manifest_mapping(target_dir: Path) -> dict[str, object] | None:
    manifest_path = target_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return manifest if isinstance(manifest, dict) else None


def _valid_generated_file_names(entries: Iterable[object], policy: FlatCommandSurfacePolicy) -> tuple[str, ...]:
    return tuple(entry for entry in entries if isinstance(entry, str) and policy.is_generated_file_name(entry))


def _default_compact_command(content: str, context: FlatCommandRenderContext) -> str | None:
    return compact_staged_command_shim_for_runtime(
        content,
        runtime=context.runtime,
        command_name=context.command_name,
        src_root=context.gpd_src_root,
        path_prefix=context.path_prefix,
        bridge_command=context.bridge_command,
    )


def _default_compile_command(content: str, context: FlatCommandRenderContext) -> str:
    return compile_markdown_for_runtime(
        content,
        runtime=context.runtime,
        path_prefix=context.path_prefix,
        install_scope=context.install_scope,
        src_root=context.gpd_src_root,
        workflow_target_dir=context.workflow_target_dir,
        explicit_target=context.explicit_target,
    )
