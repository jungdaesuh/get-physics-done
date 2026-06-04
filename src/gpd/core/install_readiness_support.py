"""Install-readiness helpers shared by CLI wrappers and core tests."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NoReturn

from gpd.core.health import UnattendedReadinessResult
from gpd.core.permissions_cli_support import permissions_status_payload
from gpd.core.runtime_targeting import (
    RuntimeInstallScope,
    RuntimeTargetingError,
    permissions_target_for_runtime_choice,
    resolve_unattended_runtime_target,
)


class InstallReadinessError(RuntimeError):
    """Raised when install/readiness arguments are inconsistent."""


def _raise_readiness_error(
    message: str,
    *,
    error: Callable[[str], NoReturn] | None = None,
) -> NoReturn:
    if error is not None:
        error(message)
    raise InstallReadinessError(message)


def doctor_blocker_messages(report: object) -> list[str]:
    """Extract blocking doctor messages from a report-like object."""

    messages: list[str] = []
    seen: set[str] = set()

    for check in getattr(report, "checks", []) or []:
        status = getattr(check, "status", None)
        issues = [str(issue) for issue in getattr(check, "issues", []) or [] if str(issue).strip()]
        if str(status) != "fail":
            continue
        if not issues:
            label = str(getattr(check, "label", "Runtime readiness")).strip() or "Runtime readiness"
            issues = [f"{label}: readiness check failed."]
        for issue in issues:
            if issue not in seen:
                seen.add(issue)
                messages.append(issue)

    return messages


def doctor_advisory_messages(report: object) -> list[str]:
    """Extract advisory doctor warnings from a report-like object."""

    messages: list[str] = []
    seen: set[str] = set()

    for check in getattr(report, "checks", []) or []:
        warnings = [str(item) for item in getattr(check, "warnings", []) or [] if str(item).strip()]
        for warning in warnings:
            if warning not in seen:
                seen.add(warning)
                messages.append(warning)

    return messages


def install_repairable_runtime_target_messages(
    report: object,
    runtime_name: str,
    *,
    normalize_runtime_name: Callable[[str | None], str | None] | None = None,
) -> list[str]:
    """Return install-preflight messages for same-runtime incomplete targets."""

    from gpd.adapters.runtime_catalog import normalize_runtime_name as default_normalize_runtime_name

    normalize = normalize_runtime_name or default_normalize_runtime_name
    messages: list[str] = []
    canonical_runtime = normalize(runtime_name) or runtime_name

    for check in getattr(report, "checks", []) or []:
        if str(getattr(check, "status", None)) != "fail":
            continue
        if str(getattr(check, "label", "")).strip() != "Runtime Config Target":
            continue
        details = getattr(check, "details", {}) or {}
        if not isinstance(details, dict) or details.get("install_state") != "owned_incomplete":
            continue
        target_assessment = details.get("target_assessment")
        assessment_payload = target_assessment if isinstance(target_assessment, dict) else details
        manifest_runtime = normalize(str(assessment_payload.get("manifest_runtime") or "")) or None
        expected_runtime = normalize(str(assessment_payload.get("expected_runtime") or "")) or canonical_runtime
        if manifest_runtime not in {None, canonical_runtime} or expected_runtime != canonical_runtime:
            continue
        issues = [str(issue) for issue in getattr(check, "issues", []) or [] if str(issue).strip()]
        messages.extend(issues or ["Incomplete same-runtime GPD install will be repaired during install."])

    return messages


def build_unattended_readiness(
    *,
    runtime: str,
    autonomy: str | None,
    global_install: bool,
    local_install: bool,
    target_dir: str | None,
    live_executable_probes: bool,
    cwd: Path,
    normalize_runtime_selection: Callable[..., list[str]],
    validated_surface: str,
    specs_dir: Path,
    adapter_lookup: Callable[[str], object] | None = None,
    target_dir_matches_global_func: Callable[..., bool] | None = None,
    resolve_detected_runtime_target_func: Callable[..., tuple[Path | None, RuntimeInstallScope | None]] | None = None,
    run_doctor: Callable[..., object] | None = None,
    permissions_status_payload_func: Callable[..., dict[str, object]] = permissions_status_payload,
    build_unattended_readiness_result: Callable[..., UnattendedReadinessResult] | None = None,
    error: Callable[[str], NoReturn] | None = None,
) -> UnattendedReadinessResult:
    """Compose doctor and permissions status into one unattended-readiness verdict."""

    from gpd.core.health import (
        build_unattended_readiness_result as default_build_unattended_readiness_result,
    )
    from gpd.core.health import run_doctor as default_run_doctor

    if global_install and local_install:
        _raise_readiness_error("Cannot specify both --global and --local", error=error)

    normalized_runtime = normalize_runtime_selection([runtime], action="validate unattended-readiness")[0]
    try:
        target_choice = resolve_unattended_runtime_target(
            normalized_runtime,
            cwd=cwd,
            global_install=global_install,
            local_install=local_install,
            target_dir=target_dir,
            **(
                {"target_dir_matches_global_func": target_dir_matches_global_func}
                if target_dir_matches_global_func is not None
                else {}
            ),
            **(
                {"resolve_detected_runtime_target_func": resolve_detected_runtime_target_func}
                if resolve_detected_runtime_target_func is not None
                else {}
            ),
        )
    except RuntimeTargetingError as exc:
        _raise_readiness_error(str(exc), error=error)

    permissions_target = permissions_target_for_runtime_choice(
        normalized_runtime,
        target_choice,
        cwd=cwd,
        adapter_lookup=adapter_lookup,
    )
    doctor_runner = run_doctor or default_run_doctor
    doctor_report = doctor_runner(
        specs_dir=specs_dir,
        runtime=normalized_runtime,
        install_scope=target_choice.install_scope,
        target_dir=target_choice.target_dir,
        cwd=cwd,
        live_executable_probes=live_executable_probes,
    )
    permissions_payload = permissions_status_payload_func(
        runtime=normalized_runtime,
        autonomy=autonomy,
        target_dir=permissions_target,
        cwd=cwd,
    )
    readiness_builder = build_unattended_readiness_result or default_build_unattended_readiness_result
    return readiness_builder(
        runtime=normalized_runtime,
        autonomy=autonomy,
        install_scope=target_choice.install_scope,
        target_dir=target_choice.target_dir,
        doctor_report=doctor_report,
        permissions_payload=permissions_payload,
        live_executable_probes=live_executable_probes,
        validated_surface=validated_surface,
    )


def run_install_readiness_preflight(
    runtimes: Sequence[str],
    *,
    install_scope: str,
    target_dir: Path | None,
    cwd: Path,
    specs_dir: Path,
    run_doctor: Callable[..., object] | None = None,
) -> tuple[list[tuple[str, list[str]]], dict[str, list[str]]]:
    """Run doctor-led readiness checks before mutating runtime install targets."""

    from gpd.core.health import CheckStatus
    from gpd.core.health import run_doctor as default_run_doctor

    doctor_runner = run_doctor or default_run_doctor
    failures: list[tuple[str, list[str]]] = []
    advisories: dict[str, list[str]] = {}

    for runtime_name in runtimes:
        try:
            report = doctor_runner(
                specs_dir=specs_dir,
                runtime=runtime_name,
                install_scope=install_scope,
                target_dir=target_dir,
                cwd=cwd,
            )
        except Exception as exc:
            failures.append((runtime_name, [str(exc)]))
            continue

        blocker_messages = doctor_blocker_messages(report)
        repairable_messages = install_repairable_runtime_target_messages(report, runtime_name)
        if repairable_messages:
            repairable_set = set(repairable_messages)
            blocker_messages = [message for message in blocker_messages if message not in repairable_set]
        if getattr(report, "overall", None) == CheckStatus.FAIL and not blocker_messages and not repairable_messages:
            blocker_messages = ["Runtime readiness reported a failure without blocking details."]

        if blocker_messages:
            failures.append((runtime_name, blocker_messages))
            continue

        advisory_messages = doctor_advisory_messages(report)
        advisory_messages.extend(repairable_messages)
        if advisory_messages:
            advisories[runtime_name] = list(dict.fromkeys(advisory_messages))

    return failures, advisories
