"""Typer-free runtime target resolution helpers for CLI surfaces."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuntimeInstallScope = Literal["local", "global"]


class RuntimeTargetingError(ValueError):
    """Raised when runtime target arguments are inconsistent."""


@dataclass(frozen=True, slots=True)
class RuntimeTargetChoice:
    """Resolved runtime install scope and optional explicit target directory."""

    install_scope: RuntimeInstallScope
    target_dir: Path | None


def resolve_cli_target_dir(target_dir: str, *, cwd: Path) -> Path:
    """Resolve a CLI target-dir argument relative to the effective command cwd."""

    resolved = Path(target_dir).expanduser()
    if resolved.is_absolute():
        return resolved.resolve(strict=False)
    return (cwd.expanduser().resolve(strict=False) / resolved).resolve(strict=False)


def format_target_for_display(target: str | Path | None, *, cwd: Path, home: Path | None = None) -> str:
    """Format a target path relative to cwd first, then home."""

    if target is None:
        return ""

    raw_target = str(target)
    if not raw_target:
        return ""

    target_path = Path(raw_target).expanduser()
    if not target_path.is_absolute():
        target_path = cwd.expanduser() / target_path

    try:
        resolved_target = target_path.resolve(strict=False)
    except OSError:
        return target_path.as_posix()
    try:
        resolved_cwd = cwd.expanduser().resolve(strict=False)
    except OSError:
        resolved_cwd = cwd.expanduser()
    try:
        resolved_home = (home or Path.home()).expanduser().resolve(strict=False)
    except OSError:
        return resolved_target.as_posix()

    try:
        relative_to_cwd = resolved_target.relative_to(resolved_cwd)
    except ValueError:
        pass
    else:
        relative_text = relative_to_cwd.as_posix()
        return "." if relative_text in ("", ".") else f"./{relative_text}"

    try:
        relative_to_home = resolved_target.relative_to(resolved_home)
    except ValueError:
        return resolved_target.as_posix()

    relative_text = relative_to_home.as_posix()
    return "~" if relative_text in ("", ".") else f"~/{relative_text}"


def validate_target_dir_runtime_selection(action: str, runtimes: list[str], target_dir: str | None) -> None:
    """Reject explicit target-dir usage when multiple runtimes are selected."""

    if target_dir and len(runtimes) != 1:
        raise RuntimeTargetingError(f"--target-dir requires exactly one runtime for {action}")


def target_dir_matches_global(
    runtime_name: str,
    target_dir: str,
    *,
    cwd: Path,
    action: str,
    adapter_lookup: Callable[[str], object] | None = None,
) -> bool:
    """Return whether an explicit target-dir names the runtime's global config dir."""

    from gpd.adapters import get_adapter
    from gpd.adapters.runtime_catalog import resolve_global_config_dir_candidates

    lookup = adapter_lookup or get_adapter
    adapter = lookup(runtime_name)
    resolved_target = resolve_cli_target_dir(target_dir, cwd=cwd)
    descriptor = getattr(adapter, "runtime_descriptor", None)
    if descriptor is not None:
        try:
            return any(
                resolved_target == candidate.expanduser().resolve(strict=False)
                for candidate in resolve_global_config_dir_candidates(descriptor)
            )
        except (AttributeError, TypeError, ValueError):
            return False

    resolve_target_dir = getattr(adapter, "resolve_target_dir", None)
    if not callable(resolve_target_dir):
        return False
    try:
        canonical_global_target = resolve_target_dir(True, cwd)
    except (AttributeError, TypeError, ValueError):
        return False
    return resolved_target == canonical_global_target.expanduser().resolve(strict=False)


def resolve_detected_runtime_target(
    runtime_name: str,
    *,
    cwd: Path,
    adapter_lookup: Callable[[str], object] | None = None,
    detect_runtime_install_target: Callable[..., object | None] | None = None,
    detect_install_scope: Callable[..., str | None] | None = None,
) -> tuple[Path | None, RuntimeInstallScope | None]:
    """Return a concrete installed runtime target when runtime detection finds one."""

    from gpd.adapters import get_adapter
    from gpd.hooks.runtime_detect import (
        detect_install_scope as default_detect_install_scope,
    )
    from gpd.hooks.runtime_detect import (
        detect_runtime_install_target as default_detect_runtime_install_target,
    )

    install_target_detector = detect_runtime_install_target or default_detect_runtime_install_target
    scope_detector = detect_install_scope or default_detect_install_scope
    lookup = adapter_lookup or get_adapter

    install_target = install_target_detector(runtime_name, cwd=cwd)
    if install_target is not None:
        install_scope = getattr(install_target, "install_scope", None)
        scope = install_scope if install_scope in {"local", "global"} else None
        return getattr(install_target, "config_dir", None), scope

    install_scope = scope_detector(runtime_name, cwd=cwd)
    if install_scope == "global":
        adapter = lookup(runtime_name)
        return adapter.resolve_target_dir(True, cwd), "global"
    if install_scope == "local":
        adapter = lookup(runtime_name)
        return adapter.resolve_target_dir(False, cwd), "local"
    return None, None


def resolve_doctor_runtime_target(
    runtime_name: str,
    *,
    cwd: Path,
    global_install: bool,
    local_install: bool,
    target_dir: str | None,
    adapter_lookup: Callable[[str], object] | None = None,
    target_dir_matches_global_func: Callable[..., bool] = target_dir_matches_global,
) -> RuntimeTargetChoice:
    """Resolve doctor runtime targets, preserving the local-first default."""

    if global_install and local_install:
        raise RuntimeTargetingError("Cannot specify both --global and --local")

    resolved_target = resolve_cli_target_dir(target_dir, cwd=cwd) if target_dir is not None else None
    install_scope: RuntimeInstallScope = (
        "global"
        if global_install
        else "local"
        if local_install
        else "global"
        if target_dir and target_dir_matches_global_func(runtime_name, target_dir, cwd=cwd, action="doctor")
        else "local"
    )
    if target_dir is None and not global_install and not local_install:
        from gpd.adapters import get_adapter

        lookup = adapter_lookup or get_adapter
        resolved_target = lookup(runtime_name).resolve_target_dir(False, cwd)
    return RuntimeTargetChoice(install_scope=install_scope, target_dir=resolved_target)


def resolve_unattended_runtime_target(
    runtime_name: str,
    *,
    cwd: Path,
    global_install: bool,
    local_install: bool,
    target_dir: str | None,
    target_dir_matches_global_func: Callable[..., bool] = target_dir_matches_global,
    resolve_detected_runtime_target_func: Callable[
        ..., tuple[Path | None, RuntimeInstallScope | None]
    ] = resolve_detected_runtime_target,
) -> RuntimeTargetChoice:
    """Resolve unattended-readiness targets, preferring detected installs by default."""

    if global_install and local_install:
        raise RuntimeTargetingError("Cannot specify both --global and --local")

    resolved_target = resolve_cli_target_dir(target_dir, cwd=cwd) if target_dir is not None else None
    install_scope: RuntimeInstallScope = (
        "global"
        if global_install
        else "local"
        if local_install
        else "global"
        if target_dir
        and target_dir_matches_global_func(
            runtime_name,
            target_dir,
            cwd=cwd,
            action="validate unattended-readiness",
        )
        else "local"
    )
    if target_dir is None and not global_install and not local_install:
        detected_target, detected_scope = resolve_detected_runtime_target_func(runtime_name, cwd=cwd)
        if detected_target is not None and detected_scope is not None:
            resolved_target = detected_target
            install_scope = detected_scope
    return RuntimeTargetChoice(install_scope=install_scope, target_dir=resolved_target)


def permissions_target_for_runtime_choice(
    runtime_name: str,
    choice: RuntimeTargetChoice,
    *,
    cwd: Path,
    adapter_lookup: Callable[[str], object] | None = None,
) -> str:
    """Return the concrete target string used by permissions readiness checks."""

    if choice.target_dir is not None:
        return str(choice.target_dir)

    from gpd.adapters import get_adapter

    lookup = adapter_lookup or get_adapter
    adapter = lookup(runtime_name)
    return str(adapter.resolve_target_dir(choice.install_scope == "global", cwd))
