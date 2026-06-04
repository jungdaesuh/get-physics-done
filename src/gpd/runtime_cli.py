"""Shared bridge for installed runtime shell invocations.

Installed prompt sources author plain ``gpd`` commands. During install, runtime
adapters rewrite those shell invocations to this bridge so one runtime-agnostic
entrypoint can:

1. validate the install contract for the target runtime config dir
2. pin the active runtime deterministically
3. dispatch into the real GPD CLI without depending on runtime-private
   launcher files
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from gpd.adapters import get_adapter
from gpd.adapters.runtime_catalog import (
    get_runtime_descriptor,
    get_shared_install_metadata,  # noqa: F401 - compatibility re-export for bridge tests
    normalize_runtime_name,
    resolve_global_config_dir_candidates,
)
from gpd.core.cli_args import (
    resolve_root_global_cli_cwd_from_argv as _resolve_cli_cwd_from_argv,
)
from gpd.core.cli_args import (
    validate_root_global_cli_passthrough as _validate_root_global_cli_passthrough,
)
from gpd.core.constants import ENV_GPD_ACTIVE_RUNTIME, ENV_GPD_DISABLE_CHECKOUT_REEXEC
from gpd.core.runtime_bridge_failures import (
    RuntimeBridgeFailure,
    RuntimeBridgeFailureKind,
    build_runtime_bridge_repair_command,
    classify_runtime_bridge_failure,
    runtime_bridge_failure,
    uses_effective_explicit_target,
)
from gpd.hooks.install_metadata import (
    assess_install_target,
    config_dir_has_managed_install_markers,
    load_install_manifest_snapshot,
)

_BridgeFailure = RuntimeBridgeFailure
_BridgeFailureKind = RuntimeBridgeFailureKind
_build_repair_command = build_runtime_bridge_repair_command
_classify_bridge_failure = classify_runtime_bridge_failure
_bridge_failure = runtime_bridge_failure
_uses_effective_explicit_target = uses_effective_explicit_target


class _BridgeArgumentError(ValueError):
    """Raised when the runtime bridge arguments are malformed."""


class _BridgeArgumentParser(argparse.ArgumentParser):
    """Argument parser that raises instead of exiting on malformed bridge input."""

    def error(self, message: str) -> None:
        raise _BridgeArgumentError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise _BridgeArgumentError(message or "malformed bridge invocation")


def _parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """Parse bridge arguments and return the remaining GPD CLI args."""
    parser = _BridgeArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--config-dir", required=True)
    parser.add_argument("--install-scope", choices=("local", "global"), required=True)
    parser.add_argument("--explicit-target", action="store_true")
    bridge_args: list[str] = []
    index = 0
    while index < len(argv):
        arg = str(argv[index])
        if arg == "--explicit-target":
            bridge_args.append(arg)
            index += 1
            continue
        if any(arg.startswith(prefix) for prefix in ("--runtime=", "--config-dir=", "--install-scope=")):
            bridge_args.append(arg)
            index += 1
            continue
        if arg in {"--runtime", "--config-dir", "--install-scope"}:
            bridge_args.append(arg)
            if index + 1 < len(argv):
                bridge_args.append(str(argv[index + 1]))
            index += 2
            continue
        break

    options = parser.parse_args(bridge_args)
    gpd_args = argv[index:]
    if gpd_args[:1] == ["--"]:
        gpd_args = gpd_args[1:]
    try:
        _validate_root_global_cli_passthrough(gpd_args)
    except ValueError as exc:
        raise _BridgeArgumentError(str(exc)) from exc
    return options, gpd_args


def _bridge_argument_error_message(message: str) -> str:
    """Return a stable user-facing message for malformed bridge invocations."""
    return f"GPD runtime bridge rejected malformed bridge invocation.\n{message}"


def _format_unknown_runtime_error(exc: KeyError) -> str:
    """Return the stable user-facing message for an unknown runtime."""
    if len(exc.args) == 1 and isinstance(exc.args[0], str):
        return exc.args[0]
    return str(exc)


def _emit_bridge_failure(failure: _BridgeFailure) -> int:
    """Write a structured bridge failure to stderr and return its exit code."""

    sys.stderr.write(failure.message)
    if not failure.message.endswith("\n"):
        sys.stderr.write("\n")
    return failure.exit_code


def _canonical_runtime_name(runtime: str) -> str:
    """Return the canonical runtime id for aliases and display names."""
    normalized = normalize_runtime_name(runtime)
    if normalized is not None:
        return normalized
    return runtime.strip()


def _paths_equal(left: Path, right: Path) -> bool:
    """Return whether two paths resolve to the same location when comparable."""
    try:
        return left.expanduser().resolve() == right.expanduser().resolve()
    except OSError:
        return left.expanduser() == right.expanduser()


def _is_matching_local_install_candidate(candidate: Path, *, runtime: str) -> bool:
    """Return whether *candidate* should satisfy a local bridge config-dir lookup."""
    return _local_install_candidate_status(candidate, runtime=runtime) == "matching"


def _is_global_config_candidate(candidate: Path, *, runtime: str) -> bool:
    adapter = get_adapter(runtime)
    return any(
        _paths_equal(candidate, global_dir)
        for global_dir in resolve_global_config_dir_candidates(adapter.runtime_descriptor)
    )


def _local_install_candidate_status(candidate: Path, *, runtime: str) -> str:
    """Classify local config-dir candidates for ancestor resolution."""
    if not candidate.is_dir():
        return "none"

    manifest = load_install_manifest_snapshot(candidate)
    manifest_status = manifest.runtime_state
    manifest_runtime = manifest.runtime
    manifest_scope = manifest.payload.get("install_scope")
    if manifest_status == "ok":
        if manifest_runtime != runtime:
            return "diagnostic"
        if manifest_scope == "local":
            return "matching"
        if manifest_scope == "global":
            return "none"
        return "diagnostic"

    if manifest_status != "ok":
        if manifest_scope == "global":
            return "none"
        if manifest_scope != "local" and _is_global_config_candidate(candidate, runtime=runtime):
            return "none"
        if manifest_status != "missing" or config_dir_has_managed_install_markers(candidate):
            return "diagnostic"
        return "none"
    return "none"


def _resolve_local_config_dir(raw_value: str, *, runtime: str, cli_cwd: Path) -> Path:
    """Resolve a local config dir reference against the nearest matching ancestor."""
    relative = Path(raw_value).expanduser()
    resolved_cwd = cli_cwd.resolve(strict=False)
    for base in (resolved_cwd, *resolved_cwd.parents):
        candidate = (base / relative).resolve(strict=False)
        if _local_install_candidate_status(candidate, runtime=runtime) != "none":
            return candidate
    return (resolved_cwd / relative).resolve(strict=False)


def _resolve_config_dir(
    raw_value: str,
    *,
    runtime: str,
    install_scope: str,
    explicit_target: bool,
    cli_cwd: Path,
) -> Path:
    """Resolve the configured runtime dir from an absolute or local-workspace reference."""
    candidate = Path(raw_value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    if install_scope == "local" and not explicit_target:
        return _resolve_local_config_dir(raw_value, runtime=runtime, cli_cwd=cli_cwd)
    return (cli_cwd / candidate).resolve(strict=False)


def _maybe_reexec_from_checkout(raw_argv: list[str], *, cli_cwd: Path) -> None:
    """Re-exec through a checkout when the active package does not match it."""
    from gpd.version import checkout_root, current_python_executable, resolve_checkout_python

    if os.environ.get(ENV_GPD_DISABLE_CHECKOUT_REEXEC) == "1":
        return

    root = checkout_root(cli_cwd)
    if root is None:
        return

    checkout_gpd = (root / "src" / "gpd").resolve(strict=False)
    active_gpd = Path(__file__).resolve().parent
    if active_gpd == checkout_gpd:
        return

    env = os.environ.copy()
    checkout_src = str((root / "src").resolve(strict=False))
    existing_pythonpath = [entry for entry in env.get("PYTHONPATH", "").split(os.pathsep) if entry]
    if checkout_src not in existing_pythonpath:
        env["PYTHONPATH"] = (
            os.pathsep.join([checkout_src, *existing_pythonpath]) if existing_pythonpath else checkout_src
        )
    env[ENV_GPD_DISABLE_CHECKOUT_REEXEC] = "1"
    active_python = current_python_executable()
    checkout_python = resolve_checkout_python(root, fallback=active_python) or active_python
    if checkout_python is None:
        return
    os.execve(checkout_python, [checkout_python, "-m", "gpd.runtime_cli", *raw_argv], env)


def _runtime_config_env_names(runtime: str) -> tuple[str, ...]:
    """Return runtime config env vars that should point at the bridge target."""
    try:
        descriptor = get_runtime_descriptor(runtime)
    except KeyError:
        return ()
    global_config = descriptor.global_config
    return tuple(
        env_var
        for env_var in (global_config.env_var, global_config.env_dir_var)
        if isinstance(env_var, str) and env_var
    )


def main(argv: list[str] | None = None) -> int:
    """Validate the install contract, then dispatch into ``gpd.cli``."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        options, gpd_args = _parse_args(raw_argv)
    except _BridgeArgumentError as exc:
        return _emit_bridge_failure(
            _bridge_failure(
                _BridgeFailureKind.MALFORMED_INVOCATION,
                _bridge_argument_error_message(str(exc)),
            )
        )
    runtime = _canonical_runtime_name(options.runtime)
    cli_cwd = _resolve_cli_cwd_from_argv(gpd_args)
    _maybe_reexec_from_checkout(raw_argv, cli_cwd=cli_cwd)
    try:
        adapter = get_adapter(runtime)
    except KeyError as exc:
        return _emit_bridge_failure(
            _bridge_failure(_BridgeFailureKind.UNKNOWN_RUNTIME, _format_unknown_runtime_error(exc))
        )
    config_dir = _resolve_config_dir(
        options.config_dir,
        runtime=runtime,
        install_scope=options.install_scope,
        explicit_target=bool(options.explicit_target),
        cli_cwd=cli_cwd,
    )
    manifest = load_install_manifest_snapshot(config_dir)
    assessment = assess_install_target(config_dir, expected_runtime=runtime, manifest=manifest)
    repair_explicit_target = _uses_effective_explicit_target(
        runtime=runtime,
        config_dir=config_dir,
        install_scope=manifest.install_scope if isinstance(manifest.install_scope, str) else options.install_scope,
        explicit_target=bool(
            options.explicit_target or (manifest.explicit_target if manifest.explicit_target_state == "ok" else False)
        ),
        cli_cwd=cli_cwd,
    )
    if assessment.state == "owned_incomplete":
        missing_install_artifacts = assessment.missing_install_artifacts
    elif assessment.state in {"absent", "clean"}:
        missing_install_artifacts = adapter.missing_install_artifacts(config_dir)
    else:
        missing_install_artifacts = None
    failure = _classify_bridge_failure(
        runtime=runtime,
        config_dir=config_dir,
        install_scope=options.install_scope,
        explicit_target=repair_explicit_target,
        cli_cwd=cli_cwd,
        manifest=manifest,
        assessment=assessment,
        missing=missing_install_artifacts,
    )
    if failure is not None:
        return _emit_bridge_failure(failure)

    prior_active_runtime = os.environ.get(ENV_GPD_ACTIVE_RUNTIME)
    prior_disable_checkout_reexec = os.environ.get(ENV_GPD_DISABLE_CHECKOUT_REEXEC)
    runtime_config_env_names = _runtime_config_env_names(adapter.runtime_name)
    prior_runtime_config_env = {name: os.environ.get(name) for name in runtime_config_env_names}
    os.environ[ENV_GPD_ACTIVE_RUNTIME] = adapter.runtime_name
    os.environ[ENV_GPD_DISABLE_CHECKOUT_REEXEC] = "1"
    for env_name in runtime_config_env_names:
        os.environ[env_name] = str(config_dir)

    from gpd.cli import entrypoint

    original_argv = list(sys.argv)
    try:
        sys.argv = ["gpd", *gpd_args]
        result = entrypoint()
    finally:
        sys.argv = original_argv
        if prior_active_runtime is None:
            os.environ.pop(ENV_GPD_ACTIVE_RUNTIME, None)
        else:
            os.environ[ENV_GPD_ACTIVE_RUNTIME] = prior_active_runtime
        if prior_disable_checkout_reexec is None:
            os.environ.pop(ENV_GPD_DISABLE_CHECKOUT_REEXEC, None)
        else:
            os.environ[ENV_GPD_DISABLE_CHECKOUT_REEXEC] = prior_disable_checkout_reexec
        for env_name, prior_value in prior_runtime_config_env.items():
            if prior_value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = prior_value

    if result is None:
        return 0
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
