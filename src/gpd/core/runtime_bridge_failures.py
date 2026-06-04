"""Shared runtime bridge failure contract.

The runtime bridge is a Python-only boundary: installed runtime commands enter
through ``gpd.runtime_cli``, which validates the target install before invoking
the real CLI. This module owns the structured failure kinds and repair-command
projection so runtime-facing diagnostics can share stable data without importing
the runtime CLI entrypoint.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

from gpd.adapters import get_adapter
from gpd.adapters.install_utils import build_runtime_install_repair_command
from gpd.adapters.runtime_catalog import get_shared_install_metadata, resolve_global_config_dir_candidates
from gpd.hooks.install_metadata import (
    InstallManifestSnapshot,
    InstallTargetAssessment,
    config_dir_has_managed_install_markers,
)

RuntimeInstallScope = Literal["local", "global"]


class RuntimeBridgeFailureKind(StrEnum):
    """Stable failure kinds for runtime bridge rejection paths."""

    MALFORMED_INVOCATION = "malformed_invocation"
    UNKNOWN_RUNTIME = "unknown_runtime"
    MISSING_INSTALL_SCOPE = "missing_install_scope"
    MALFORMED_INSTALL_SCOPE = "malformed_install_scope"
    MISSING_MANIFEST = "missing_manifest"
    CORRUPT_MANIFEST = "corrupt_manifest"
    INVALID_MANIFEST = "invalid_manifest"
    MISSING_RUNTIME = "missing_runtime"
    MALFORMED_RUNTIME = "malformed_runtime"
    UNSUPPORTED_RUNTIME = "unsupported_runtime"
    RUNTIME_MISMATCH = "runtime_mismatch"
    INSTALL_SCOPE_MISMATCH = "install_scope_mismatch"
    UNTRUSTED_MANIFEST = "untrusted_manifest"
    MALFORMED_EXPLICIT_TARGET = "malformed_explicit_target"
    MISSING_INSTALL_ARTIFACTS = "missing_install_artifacts"


@dataclass(frozen=True, slots=True)
class RuntimeBridgeRepairContext:
    """Inputs needed to render catalog-backed runtime install repair commands."""

    runtime: str
    config_dir: Path
    install_scope: RuntimeInstallScope
    explicit_target: bool
    cli_cwd: Path


@dataclass(frozen=True, slots=True)
class RuntimeBridgeFailure:
    """Structured representation of a runtime bridge rejection."""

    kind: RuntimeBridgeFailureKind
    message: str
    exit_code: int = 127
    install_state: str | None = None
    manifest_state: str | None = None
    manifest_runtime: str | None = None
    manifest_install_scope: str | None = None
    expected_runtime: str | None = None
    owning_runtime: str | None = None
    expected_install_scope: str | None = None
    owning_install_scope: str | None = None
    missing_install_artifacts: tuple[str, ...] = ()
    repair_command: str | None = None
    repairable_by_install: bool = False
    readiness_state: Literal["blocked"] = "blocked"
    details: Mapping[str, object] = field(default_factory=dict)


def _runtime_display_name(runtime: str) -> str:
    """Return a human-readable runtime label when the runtime is known."""
    try:
        return get_adapter(runtime).display_name
    except KeyError:
        return runtime


def _paths_equal(left: Path, right: Path) -> bool:
    """Return whether two paths resolve to the same location when comparable."""
    try:
        return left.expanduser().resolve() == right.expanduser().resolve()
    except OSError:
        return left.expanduser() == right.expanduser()


def uses_effective_explicit_target(
    *,
    runtime: str,
    config_dir: Path,
    install_scope: str,
    explicit_target: bool,
    cli_cwd: Path,
) -> bool:
    """Return whether repair guidance must emit ``--target-dir``."""
    if explicit_target:
        return True

    adapter = get_adapter(runtime)
    if install_scope == "global":
        global_config_candidates = resolve_global_config_dir_candidates(
            adapter.runtime_descriptor,
            home=Path.home(),
        )
        return not any(_paths_equal(config_dir, candidate) for candidate in global_config_candidates)

    default_local_config_dir = adapter.resolve_local_config_dir(cli_cwd).resolve(strict=False)
    return not _paths_equal(config_dir, default_local_config_dir)


def build_runtime_bridge_repair_command(
    *,
    runtime: str,
    config_dir: Path,
    install_scope: str,
    explicit_target: bool,
    cli_cwd: Path,
) -> str:
    """Return the reinstall command with the effective target-dir projection."""

    return build_runtime_install_repair_command(
        runtime,
        install_scope=install_scope,
        target_dir=config_dir,
        explicit_target=uses_effective_explicit_target(
            runtime=runtime,
            config_dir=config_dir,
            install_scope=install_scope,
            explicit_target=explicit_target,
            cli_cwd=cli_cwd,
        ),
    )


def runtime_bridge_failure(
    kind: RuntimeBridgeFailureKind,
    message: str,
    *,
    exit_code: int = 127,
    install_state: str | None = None,
    manifest_state: str | None = None,
    manifest_runtime: str | None = None,
    manifest_install_scope: str | None = None,
    expected_runtime: str | None = None,
    owning_runtime: str | None = None,
    expected_install_scope: str | None = None,
    owning_install_scope: str | None = None,
    missing_install_artifacts: tuple[str, ...] = (),
    repair_command: str | None = None,
    repairable_by_install: bool = False,
    details: Mapping[str, object] | None = None,
) -> RuntimeBridgeFailure:
    """Build a structured failure record for bridge rejection paths."""

    detail_payload: dict[str, object] = {
        "kind": kind.value,
        "exit_code": exit_code,
        "readiness_state": "blocked",
        "repairable_by_install": repairable_by_install,
    }
    if install_state is not None:
        detail_payload["install_state"] = install_state
    if manifest_state is not None:
        detail_payload["manifest_state"] = manifest_state
    if manifest_runtime is not None:
        detail_payload["manifest_runtime"] = manifest_runtime
    if manifest_install_scope is not None:
        detail_payload["manifest_install_scope"] = manifest_install_scope
    if expected_runtime is not None:
        detail_payload["expected_runtime"] = expected_runtime
    if owning_runtime is not None:
        detail_payload["owning_runtime"] = owning_runtime
    if expected_install_scope is not None:
        detail_payload["expected_install_scope"] = expected_install_scope
    if owning_install_scope is not None:
        detail_payload["owning_install_scope"] = owning_install_scope
    if missing_install_artifacts:
        detail_payload["missing_install_artifacts"] = list(missing_install_artifacts)
    if repair_command is not None:
        detail_payload["repair_command"] = repair_command
    if details:
        detail_payload.update(details)

    return RuntimeBridgeFailure(
        kind=kind,
        message=message,
        exit_code=exit_code,
        install_state=install_state,
        manifest_state=manifest_state,
        manifest_runtime=manifest_runtime,
        manifest_install_scope=manifest_install_scope,
        expected_runtime=expected_runtime,
        owning_runtime=owning_runtime,
        expected_install_scope=expected_install_scope,
        owning_install_scope=owning_install_scope,
        missing_install_artifacts=missing_install_artifacts,
        repair_command=repair_command,
        repairable_by_install=repairable_by_install,
        details=detail_payload,
    )


def _repair_command(
    context: RuntimeBridgeRepairContext,
    *,
    runtime: str | None = None,
    install_scope: str | None = None,
) -> str:
    return build_runtime_bridge_repair_command(
        runtime=runtime or context.runtime,
        config_dir=context.config_dir,
        install_scope=install_scope or context.install_scope,
        explicit_target=context.explicit_target,
        cli_cwd=context.cli_cwd,
    )


def _install_error_message(
    *,
    runtime: str,
    config_dir: Path,
    missing: tuple[str, ...],
    repair_command: str,
) -> str:
    """Return a deterministic repair message for an incomplete runtime install."""
    adapter = get_adapter(runtime)
    missing_list = ", ".join(f"`{relpath}`" for relpath in missing)
    return (
        f"GPD runtime install incomplete for {adapter.display_name} at `{config_dir}`.\n"
        f"Missing required install artifacts: {missing_list}\n"
        f"Repair the install with: `{repair_command}`"
    )


def _runtime_mismatch_error_message(
    *,
    runtime: str,
    manifest_runtime: str,
    config_dir: Path,
    repair_command: str,
) -> str:
    """Return repair guidance when the resolved config dir belongs to another runtime."""
    return (
        f"GPD runtime bridge mismatch for {_runtime_display_name(runtime)} at `{config_dir}`.\n"
        f"Resolved install manifest pins {_runtime_display_name(manifest_runtime)} (`{manifest_runtime}`), "
        "so this bridge cannot safely continue.\n"
        f"Repair or reinstall with the owning runtime: `{repair_command}`"
    )


def _install_scope_mismatch_error_message(
    *,
    runtime: str,
    manifest_install_scope: str,
    config_dir: Path,
    install_scope: str,
    repair_command: str,
) -> str:
    """Return repair guidance when the manifest scope disagrees with the bridge scope."""
    return (
        f"GPD runtime bridge scope mismatch for {_runtime_display_name(runtime)} at `{config_dir}`.\n"
        f"Resolved install manifest pins `{manifest_install_scope}`, but this bridge was launched as `{install_scope}`.\n"
        f"Repair or reinstall with the owning scope: `{repair_command}`"
    )


def _malformed_manifest_runtime_error_message(
    *,
    config_dir: Path,
    repair_command: str,
) -> str:
    """Return repair guidance when the install manifest runtime field is malformed."""
    return (
        f"GPD runtime bridge rejected malformed install manifest at `{config_dir}`.\n"
        "The manifest `runtime` field must be a recognized non-empty runtime string.\n"
        f"Repair or reinstall with: `{repair_command}`"
    )


def _unsupported_manifest_runtime_error_message(
    *,
    runtime: str,
    manifest_runtime: str,
    config_dir: Path,
    repair_command: str,
) -> str:
    """Return repair guidance for an unsupported runtime id in the install manifest."""
    return (
        f"GPD runtime bridge found unsupported runtime `{manifest_runtime}` at `{config_dir}`.\n"
        "The manifest `runtime` field is well formed, but this GPD version has no adapter for it.\n"
        f"Repair or reinstall with {_runtime_display_name(runtime)}: `{repair_command}`"
    )


def _missing_manifest_runtime_error_message(
    *,
    config_dir: Path,
    repair_command: str,
) -> str:
    """Return repair guidance when the install manifest omits ``runtime``."""
    return (
        f"GPD runtime bridge rejected incomplete install manifest at `{config_dir}`.\n"
        "The manifest must declare a non-empty `runtime` field.\n"
        f"Repair or reinstall with: `{repair_command}`"
    )


def _install_scope_status_error_message(
    *,
    config_dir: Path,
    state: str,
    repair_command: str,
) -> str:
    """Return repair guidance when the manifest install_scope field is missing or malformed."""
    if state == "missing_install_scope":
        scope_issue = "The manifest must declare a non-empty `install_scope` field."
    else:
        scope_issue = "The manifest `install_scope` field must be exactly `local` or `global`."
    return (
        f"GPD runtime bridge rejected incomplete install manifest at `{config_dir}`.\n"
        f"{scope_issue}\n"
        f"Repair or reinstall with: `{repair_command}`"
    )


def _missing_manifest_error_message(
    *,
    config_dir: Path,
    repair_command: str,
) -> str:
    """Return repair guidance when a managed install surface has no manifest."""
    shared_install = get_shared_install_metadata()
    return (
        f"GPD runtime bridge rejected missing install manifest at `{config_dir}`.\n"
        f"Managed installs must include `{shared_install.manifest_name}` so runtime identity stays authoritative.\n"
        f"Repair or reinstall with: `{repair_command}`"
    )


def _untrusted_manifest_error_message(
    *,
    config_dir: Path,
    repair_command: str,
) -> str:
    """Return repair guidance when the install manifest cannot be trusted."""
    return (
        f"GPD runtime bridge rejected unreadable install manifest at `{config_dir}`.\n"
        "The manifest must be a JSON object with a non-empty `runtime` field.\n"
        f"Repair or reinstall with: `{repair_command}`"
    )


def _untrusted_manifest_metadata_error_message(
    *,
    config_dir: Path,
    manifest_state: str,
    repair_command: str,
) -> str:
    """Return repair guidance when manifest ownership metadata fails validation."""
    return (
        f"GPD runtime bridge rejected untrusted install manifest at `{config_dir}`.\n"
        f"The manifest ownership metadata failed validation (`{manifest_state}`).\n"
        f"Repair or reinstall with: `{repair_command}`"
    )


def _failure_context_details(
    *,
    runtime: str,
    install_scope: str,
    manifest: InstallManifestSnapshot,
    assessment: InstallTargetAssessment | None,
) -> dict[str, object]:
    details: dict[str, object] = {
        "manifest_parse_state": manifest.parse_state,
        "manifest_scope_state": manifest.scope_state,
        "manifest_explicit_target_state": manifest.explicit_target_state,
    }
    if assessment is not None:
        details.update(
            {
                "install_state": assessment.state,
                "has_managed_markers": assessment.has_managed_markers,
            }
        )
    if manifest.install_scope is not None:
        details["manifest_install_scope"] = manifest.install_scope
    if manifest.runtime is not None:
        details["manifest_runtime"] = manifest.runtime
    details["expected_runtime"] = runtime
    details["expected_install_scope"] = install_scope
    return details


def classify_runtime_bridge_failure(
    *,
    runtime: str,
    config_dir: Path,
    install_scope: RuntimeInstallScope,
    explicit_target: bool,
    cli_cwd: Path,
    manifest: InstallManifestSnapshot,
    assessment: InstallTargetAssessment | None = None,
    missing: tuple[str, ...] | None,
) -> RuntimeBridgeFailure | None:
    """Return the first structured bridge failure for the current install state."""

    manifest_status = manifest.runtime_state
    manifest_runtime = manifest.runtime
    manifest_scope_status = manifest.scope_state
    manifest_install_scope = manifest.install_scope
    manifest_explicit_target_status = manifest.explicit_target_state
    install_state = assessment.state if assessment is not None else None
    has_managed_install_markers = (
        assessment.has_managed_markers if assessment is not None else config_dir_has_managed_install_markers(config_dir)
    )
    context = RuntimeBridgeRepairContext(
        runtime=runtime,
        config_dir=config_dir,
        install_scope=install_scope,
        explicit_target=explicit_target,
        cli_cwd=cli_cwd,
    )
    common_details = _failure_context_details(
        runtime=runtime,
        install_scope=install_scope,
        manifest=manifest,
        assessment=assessment,
    )

    def failure(
        kind: RuntimeBridgeFailureKind,
        message: str,
        *,
        repair_command: str | None = None,
        owning_runtime: str | None = None,
        owning_install_scope: str | None = None,
        missing_install_artifacts: tuple[str, ...] = (),
        repairable_by_install: bool = False,
        manifest_state: str | None = None,
    ) -> RuntimeBridgeFailure:
        return runtime_bridge_failure(
            kind,
            message,
            install_state=install_state,
            manifest_state=manifest_state or manifest_status,
            manifest_runtime=manifest_runtime,
            manifest_install_scope=manifest_install_scope,
            expected_runtime=runtime,
            owning_runtime=owning_runtime,
            expected_install_scope=install_scope,
            owning_install_scope=owning_install_scope,
            missing_install_artifacts=missing_install_artifacts,
            repair_command=repair_command,
            repairable_by_install=repairable_by_install,
            details=common_details,
        )

    if manifest_status == "missing" and has_managed_install_markers:
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.MISSING_MANIFEST,
            _missing_manifest_error_message(config_dir=config_dir, repair_command=repair_command),
            repair_command=repair_command,
        )
    if manifest_status == "corrupt":
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.CORRUPT_MANIFEST,
            _untrusted_manifest_error_message(config_dir=config_dir, repair_command=repair_command),
            repair_command=repair_command,
        )
    if manifest_status == "invalid":
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.INVALID_MANIFEST,
            _untrusted_manifest_error_message(config_dir=config_dir, repair_command=repair_command),
            repair_command=repair_command,
        )
    if manifest_status == "missing_runtime":
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.MISSING_RUNTIME,
            _missing_manifest_runtime_error_message(config_dir=config_dir, repair_command=repair_command),
            repair_command=repair_command,
        )
    if manifest_status == "malformed_runtime":
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.MALFORMED_RUNTIME,
            _malformed_manifest_runtime_error_message(config_dir=config_dir, repair_command=repair_command),
            repair_command=repair_command,
        )
    if manifest_status == "unsupported_runtime" and manifest_runtime is not None:
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.UNSUPPORTED_RUNTIME,
            _unsupported_manifest_runtime_error_message(
                runtime=runtime,
                manifest_runtime=manifest_runtime,
                config_dir=config_dir,
                repair_command=repair_command,
            ),
            repair_command=repair_command,
            owning_runtime=manifest_runtime,
        )
    if manifest_status == "ok" and manifest_explicit_target_status == "malformed_explicit_target":
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.MALFORMED_EXPLICIT_TARGET,
            _untrusted_manifest_metadata_error_message(
                config_dir=config_dir,
                manifest_state=manifest_explicit_target_status,
                repair_command=repair_command,
            ),
            repair_command=repair_command,
            manifest_state=manifest_explicit_target_status,
        )
    if manifest_runtime is not None and manifest_runtime != runtime:
        owning_install_scope = manifest_install_scope if manifest_install_scope in {"local", "global"} else install_scope
        repair_command = _repair_command(context, runtime=manifest_runtime, install_scope=owning_install_scope)
        return failure(
            RuntimeBridgeFailureKind.RUNTIME_MISMATCH,
            _runtime_mismatch_error_message(
                runtime=runtime,
                manifest_runtime=manifest_runtime,
                config_dir=config_dir,
                repair_command=repair_command,
            ),
            repair_command=repair_command,
            owning_runtime=manifest_runtime,
            owning_install_scope=owning_install_scope,
        )
    if manifest_scope_status == "missing_install_scope":
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.MISSING_INSTALL_SCOPE,
            _install_scope_status_error_message(
                config_dir=config_dir,
                state=manifest_scope_status,
                repair_command=repair_command,
            ),
            repair_command=repair_command,
            manifest_state=manifest_scope_status,
        )
    if manifest_scope_status == "malformed_install_scope":
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.MALFORMED_INSTALL_SCOPE,
            _install_scope_status_error_message(
                config_dir=config_dir,
                state=manifest_scope_status,
                repair_command=repair_command,
            ),
            repair_command=repair_command,
            manifest_state=manifest_scope_status,
        )
    if isinstance(manifest_install_scope, str) and manifest_install_scope in {"local", "global"}:
        if manifest_install_scope != install_scope:
            repair_command = _repair_command(context, install_scope=manifest_install_scope)
            return failure(
                RuntimeBridgeFailureKind.INSTALL_SCOPE_MISMATCH,
                _install_scope_mismatch_error_message(
                    runtime=runtime,
                    manifest_install_scope=manifest_install_scope,
                    config_dir=config_dir,
                    install_scope=install_scope,
                    repair_command=repair_command,
                ),
                repair_command=repair_command,
                owning_install_scope=manifest_install_scope,
            )
    if assessment is not None and assessment.state == "untrusted_manifest":
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.UNTRUSTED_MANIFEST,
            _untrusted_manifest_metadata_error_message(
                config_dir=config_dir,
                manifest_state=assessment.manifest_state,
                repair_command=repair_command,
            ),
            repair_command=repair_command,
            manifest_state=assessment.manifest_state,
        )
    if missing is None and assessment is not None and assessment.state == "owned_incomplete":
        missing = assessment.missing_install_artifacts
    if missing:
        repair_command = _repair_command(context)
        return failure(
            RuntimeBridgeFailureKind.MISSING_INSTALL_ARTIFACTS,
            _install_error_message(
                runtime=runtime,
                config_dir=config_dir,
                missing=missing,
                repair_command=repair_command,
            ),
            repair_command=repair_command,
            missing_install_artifacts=missing,
            repairable_by_install=True,
        )
    return None


def _kind_from_assessment(assessment: InstallTargetAssessment) -> RuntimeBridgeFailureKind:
    if assessment.state == "owned_incomplete":
        return RuntimeBridgeFailureKind.MISSING_INSTALL_ARTIFACTS
    if assessment.state == "foreign_runtime":
        if assessment.manifest_state == "unsupported_runtime":
            return RuntimeBridgeFailureKind.UNSUPPORTED_RUNTIME
        return RuntimeBridgeFailureKind.RUNTIME_MISMATCH
    if assessment.state == "unsupported_runtime":
        return RuntimeBridgeFailureKind.UNSUPPORTED_RUNTIME
    if assessment.state == "untrusted_manifest":
        if assessment.manifest_state == "missing":
            return RuntimeBridgeFailureKind.MISSING_MANIFEST
        if assessment.manifest_state == "corrupt":
            return RuntimeBridgeFailureKind.CORRUPT_MANIFEST
        if assessment.manifest_state == "invalid":
            return RuntimeBridgeFailureKind.INVALID_MANIFEST
        if assessment.manifest_state == "missing_runtime":
            return RuntimeBridgeFailureKind.MISSING_RUNTIME
        if assessment.manifest_state == "malformed_runtime":
            return RuntimeBridgeFailureKind.MALFORMED_RUNTIME
        if assessment.manifest_state == "missing_install_scope":
            return RuntimeBridgeFailureKind.MISSING_INSTALL_SCOPE
        if assessment.manifest_state == "malformed_install_scope":
            return RuntimeBridgeFailureKind.MALFORMED_INSTALL_SCOPE
        if assessment.manifest_state == "malformed_explicit_target":
            return RuntimeBridgeFailureKind.MALFORMED_EXPLICIT_TARGET
    return RuntimeBridgeFailureKind.UNTRUSTED_MANIFEST


def runtime_bridge_failure_from_assessment(
    assessment: InstallTargetAssessment,
    *,
    runtime: str | None,
) -> RuntimeBridgeFailure | None:
    """Return stable bridge failure details derivable from an install assessment."""

    if assessment.readiness_state == "ready":
        return None

    kind = _kind_from_assessment(assessment)
    repairable_by_install = kind is RuntimeBridgeFailureKind.MISSING_INSTALL_ARTIFACTS
    return runtime_bridge_failure(
        kind,
        assessment.readiness_message(runtime),
        install_state=assessment.state,
        manifest_state=assessment.manifest_state,
        manifest_runtime=assessment.manifest_runtime,
        manifest_install_scope=assessment.manifest_scope,
        expected_runtime=runtime,
        owning_runtime=assessment.manifest_runtime,
        missing_install_artifacts=assessment.missing_install_artifacts,
        repairable_by_install=repairable_by_install,
        details={
            "has_managed_markers": assessment.has_managed_markers,
            "manifest_scope_state": assessment.manifest_scope_state,
            "manifest_explicit_target_state": assessment.manifest_explicit_target_state,
        },
    )


def runtime_bridge_failure_details(failure: RuntimeBridgeFailure | None) -> dict[str, object]:
    """Return health/doctor-safe structured details for a bridge failure."""

    if failure is None:
        return {}

    details: dict[str, object] = {
        "runtime_bridge_failure_kind": failure.kind.value,
        "runtime_bridge_exit_code": failure.exit_code,
        "runtime_bridge_readiness_state": failure.readiness_state,
        "runtime_bridge_repairable_by_install": failure.repairable_by_install,
    }
    if failure.repair_command is not None:
        details["runtime_bridge_repair_command"] = failure.repair_command
    if failure.expected_runtime is not None:
        details["runtime_bridge_expected_runtime"] = failure.expected_runtime
    if failure.owning_runtime is not None:
        details["runtime_bridge_owning_runtime"] = failure.owning_runtime
    if failure.expected_install_scope is not None:
        details["runtime_bridge_expected_install_scope"] = failure.expected_install_scope
    if failure.owning_install_scope is not None:
        details["runtime_bridge_owning_install_scope"] = failure.owning_install_scope
    return details
