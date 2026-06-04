"""Dependency-injected runtime permissions helpers for CLI wrappers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NoReturn

from gpd.core.public_surface_contract import local_cli_permissions_sync_command
from gpd.core.runtime_targeting import format_target_for_display, resolve_cli_target_dir


class PermissionsResolutionError(RuntimeError):
    """Raised when a permissions command cannot resolve its runtime target."""


def _raise_permissions_resolution_error(
    message: str,
    *,
    strict: bool,
    error: Callable[[str], NoReturn] | None = None,
) -> NoReturn:
    if strict and error is not None:
        error(message)
    raise PermissionsResolutionError(message)


def resolve_permissions_runtime_name(
    runtime: str | None,
    *,
    cwd: Path,
    strict: bool = True,
    prefer_installed_runtime: bool = False,
    supported_runtime_names: Callable[[], Iterable[str]] | None = None,
    normalize_runtime_name: Callable[[str | None], str | None] | None = None,
    detect_active_runtime: Callable[..., str] | None = None,
    detect_runtime_for_gpd_use: Callable[..., str] | None = None,
    error: Callable[[str], NoReturn] | None = None,
) -> str:
    """Resolve the runtime to use for permissions status/sync commands."""

    from gpd.adapters import list_runtimes
    from gpd.adapters.runtime_catalog import normalize_runtime_name as default_normalize_runtime_name
    from gpd.hooks.runtime_detect import (
        RUNTIME_UNKNOWN,
    )
    from gpd.hooks.runtime_detect import (
        detect_active_runtime as default_detect_active_runtime,
    )
    from gpd.hooks.runtime_detect import (
        detect_runtime_for_gpd_use as default_detect_runtime_for_gpd_use,
    )

    supported = list(supported_runtime_names() if supported_runtime_names is not None else list_runtimes())
    normalize = normalize_runtime_name or default_normalize_runtime_name
    if runtime is not None:
        normalized = normalize(runtime)
        if normalized is None or normalized not in supported:
            _raise_permissions_resolution_error(
                f"Unknown runtime {runtime!r}. Supported: {', '.join(supported)}",
                strict=strict,
                error=error,
            )
        return normalized

    active_detector = detect_runtime_for_gpd_use if prefer_installed_runtime else detect_active_runtime
    detector = active_detector or (
        default_detect_runtime_for_gpd_use if prefer_installed_runtime else default_detect_active_runtime
    )
    detected = detector(cwd=cwd)
    if detected == RUNTIME_UNKNOWN:
        _raise_permissions_resolution_error(
            "No active runtime was detected. Pass --runtime explicitly.",
            strict=strict,
            error=error,
        )
    return detected


def resolve_permissions_autonomy(
    autonomy: str | None,
    *,
    cwd: Path,
    strict: bool = True,
    load_config: Callable[[Path], object] | None = None,
    autonomy_values: Iterable[str] | None = None,
    error: Callable[[str], NoReturn] | None = None,
) -> str:
    """Resolve the autonomy value used for runtime-permission sync."""

    from gpd.core.config import AutonomyMode
    from gpd.core.config import load_config as default_load_config

    if autonomy is None:
        config_loader = load_config or default_load_config
        return config_loader(cwd).autonomy.value

    normalized = autonomy.strip().lower()
    valid_values = set(autonomy_values or (mode.value for mode in AutonomyMode))
    if normalized not in valid_values:
        _raise_permissions_resolution_error(
            f"Unknown autonomy {autonomy!r}. Supported: {', '.join(sorted(valid_values))}",
            strict=strict,
            error=error,
        )
    return normalized


def permissions_install_target_assessment(
    runtime_name: str,
    target_dir: Path,
    *,
    assess_install_target: Callable[..., object] | None = None,
) -> object:
    """Return the shared install-state assessment for a permissions target."""

    from gpd.hooks.install_metadata import assess_install_target as default_assess_install_target

    assessment_func = assess_install_target or default_assess_install_target
    return assessment_func(target_dir, expected_runtime=runtime_name)


def permissions_install_target_error_message(
    runtime_name: str,
    assessment: object,
    *,
    action: str,
    cwd: Path | None = None,
) -> str:
    """Return a user-facing error message for a non-complete permissions target."""

    config_dir = Path(str(assessment.config_dir))
    target = format_target_for_display(config_dir, cwd=cwd or Path.cwd())
    state = getattr(assessment, "state", None)
    if state == "owned_incomplete":
        missing_paths = getattr(assessment, "missing_install_artifacts", ()) or ()
        missing = ", ".join(f"`{relpath}`" for relpath in missing_paths)
        missing_message = f" Missing artifacts: {missing}." if missing else ""
        return (
            f"Found an incomplete GPD install for runtime {runtime_name!r} at {target}.{missing_message} "
            f"Repair the install before you {action}."
        )
    if state == "foreign_runtime":
        other_runtime = getattr(assessment, "manifest_runtime", None) or "unknown"
        return (
            f"Found a GPD install at {target}, but its manifest belongs to runtime {other_runtime!r}, "
            f"not {runtime_name!r}."
        )
    if state == "untrusted_manifest":
        manifest_state = getattr(assessment, "manifest_state", None)
        return (
            f"Found a managed GPD surface at {target}, but its manifest state is {manifest_state!r}. "
            "Repair or reinstall it before using permissions."
        )
    return f"No GPD install found for runtime {runtime_name!r}. Run `gpd install {runtime_name}` first."


def resolve_permissions_target_dir(
    runtime_name: str,
    *,
    target_dir: str | None,
    cwd: Path,
    strict: bool = True,
    action: str = "inspect runtime permissions on",
    adapter_lookup: Callable[[str], object] | None = None,
    detect_runtime_install_target: Callable[..., object | None] | None = None,
    detect_install_scope: Callable[..., str | None] | None = None,
    target_assessment_resolver: Callable[[str, Path], object] | None = None,
    error: Callable[[str], NoReturn] | None = None,
) -> Path:
    """Resolve the installed config directory targeted by a permissions command."""

    from gpd.adapters import get_adapter
    from gpd.hooks.runtime_detect import (
        detect_install_scope as default_detect_install_scope,
    )
    from gpd.hooks.runtime_detect import (
        detect_runtime_install_target as default_detect_runtime_install_target,
    )

    lookup = adapter_lookup or get_adapter
    runtime_install_target_detector = detect_runtime_install_target or default_detect_runtime_install_target
    scope_detector = detect_install_scope or default_detect_install_scope
    assessment_func = target_assessment_resolver or permissions_install_target_assessment
    adapter = lookup(runtime_name)
    assessment = None

    if target_dir:
        resolved = resolve_cli_target_dir(target_dir, cwd=cwd)
        try:
            adapter.validate_target_runtime(resolved, action=action)
        except RuntimeError as exc:
            _raise_permissions_resolution_error(str(exc), strict=strict, error=error)
        assessment = assessment_func(runtime_name, resolved)
    else:
        install_target = runtime_install_target_detector(runtime_name, cwd=cwd)
        if install_target is not None:
            resolved = install_target.config_dir
            assessment = assessment_func(runtime_name, resolved)
        else:
            install_scope = scope_detector(runtime_name, cwd=cwd)
            if install_scope == "global":
                resolved = adapter.resolve_target_dir(True, cwd)
                assessment = assessment_func(runtime_name, resolved)
            elif install_scope == "local":
                resolved = adapter.resolve_target_dir(False, cwd)
                assessment = assessment_func(runtime_name, resolved)
            else:
                local_target = adapter.resolve_target_dir(False, cwd)
                global_target = adapter.resolve_target_dir(True, cwd)
                local_assessment = assessment_func(runtime_name, local_target)
                global_assessment = assessment_func(runtime_name, global_target)
                candidate_assessments = (local_assessment, global_assessment)
                complete_assessment = next(
                    (
                        candidate
                        for candidate in candidate_assessments
                        if getattr(candidate, "state", None) == "owned_complete"
                    ),
                    None,
                )
                if complete_assessment is not None:
                    resolved = complete_assessment.config_dir
                    assessment = complete_assessment
                else:
                    informative_assessment = next(
                        (
                            candidate
                            for candidate in candidate_assessments
                            if getattr(candidate, "state", None) not in {"absent", "clean"}
                        ),
                        None,
                    )
                    if informative_assessment is None:
                        _raise_permissions_resolution_error(
                            f"No GPD install found for runtime {runtime_name!r}. "
                            f"Run `gpd install {runtime_name}` first.",
                            strict=strict,
                            error=error,
                        )
                    resolved = informative_assessment.config_dir
                    assessment = informative_assessment

    if assessment is None:
        assessment = assessment_func(runtime_name, resolved)

    if getattr(assessment, "state", None) in {"absent", "clean"} and adapter.has_complete_install(resolved):
        return resolved

    if getattr(assessment, "state", None) != "owned_complete":
        _raise_permissions_resolution_error(
            permissions_install_target_error_message(runtime_name, assessment, action=action, cwd=cwd),
            strict=strict,
            error=error,
        )
    return resolved


def annotate_permissions_payload(
    payload: dict[str, object],
    *,
    requested_runtime: str | None = None,
) -> dict[str, object]:
    """Attach structured capability and evidence metadata to a permissions payload."""

    from gpd.core.health import annotate_permissions_payload as default_annotate_permissions_payload

    return default_annotate_permissions_payload(payload, requested_runtime=requested_runtime)


def runtime_permissions_payload(
    *,
    runtime: str | None,
    autonomy: str | None,
    target_dir: str | None,
    apply_sync: bool,
    strict: bool,
    cwd: Path,
    prefer_installed_runtime: bool = False,
    adapter_lookup: Callable[[str], object] | None = None,
    runtime_name_resolver: Callable[..., str] = resolve_permissions_runtime_name,
    target_dir_resolver: Callable[..., Path] = resolve_permissions_target_dir,
    autonomy_resolver: Callable[..., str] = resolve_permissions_autonomy,
    payload_annotator: Callable[..., dict[str, object]] = annotate_permissions_payload,
    error: Callable[[str], NoReturn] | None = None,
) -> dict[str, object]:
    """Return runtime-permissions status or sync payload for the selected runtime."""

    from gpd.adapters import get_adapter
    from gpd.hooks.runtime_detect import RUNTIME_UNKNOWN

    lookup = adapter_lookup or get_adapter
    try:
        runtime_name = runtime_name_resolver(
            runtime,
            cwd=cwd,
            strict=strict,
            prefer_installed_runtime=prefer_installed_runtime,
            error=error,
        )
    except PermissionsResolutionError as exc:
        if strict:
            raise
        return payload_annotator(
            {
                "runtime": None,
                "target": None,
                "sync_applied": False,
                "changed": False,
                "message": str(exc),
            },
            requested_runtime=runtime,
        )

    if runtime is None and runtime_name == RUNTIME_UNKNOWN:
        message = (
            "No active runtime was detected. "
            f"Run `{local_cli_permissions_sync_command()}` after installing GPD into a runtime."
        )
        if strict:
            _raise_permissions_resolution_error(
                "No active runtime was detected. Pass --runtime explicitly.",
                strict=True,
                error=error,
            )
        return payload_annotator(
            {
                "runtime": None,
                "target": None,
                "sync_applied": False,
                "changed": False,
                "message": message,
            },
            requested_runtime=runtime,
        )

    try:
        resolved_target_dir = target_dir_resolver(
            runtime_name,
            target_dir=target_dir,
            cwd=cwd,
            strict=strict,
            action=("sync" if apply_sync else "inspect") + " runtime permissions on",
            error=error,
        )
    except PermissionsResolutionError as exc:
        if strict:
            raise
        return payload_annotator(
            {
                "runtime": runtime_name,
                "target": None if target_dir is None else str(resolve_cli_target_dir(target_dir, cwd=cwd)),
                "sync_applied": False,
                "changed": False,
                "message": str(exc),
            },
            requested_runtime=runtime,
        )

    adapter = lookup(runtime_name)
    autonomy_value = autonomy_resolver(autonomy, cwd=cwd, strict=strict, error=error)
    payload = (
        adapter.sync_runtime_permissions(resolved_target_dir, autonomy=autonomy_value)
        if apply_sync
        else adapter.runtime_permissions_status(resolved_target_dir, autonomy=autonomy_value)
    )
    return payload_annotator(
        {
            "runtime": runtime_name,
            "target": str(resolved_target_dir),
            "autonomy": autonomy_value,
            **payload,
        },
        requested_runtime=runtime,
    )


def permissions_status_payload(
    *,
    runtime: str | None,
    autonomy: str | None,
    target_dir: str | None,
    cwd: Path,
    runtime_permissions_payload_func: Callable[..., dict[str, object]] = runtime_permissions_payload,
) -> dict[str, object]:
    """Return a status payload normalized for unattended-readiness checks."""

    from gpd.core.health import normalize_permissions_readiness_payload

    payload = runtime_permissions_payload_func(
        runtime=runtime,
        autonomy=autonomy,
        target_dir=target_dir,
        apply_sync=False,
        strict=True,
        cwd=cwd,
        prefer_installed_runtime=True,
    )
    return normalize_permissions_readiness_payload(payload, requested_runtime=runtime)
