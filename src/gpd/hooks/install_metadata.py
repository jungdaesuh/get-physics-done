"""Shared helpers for installed-hook metadata."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from gpd.adapters.runtime_catalog import (
    ManifestMetadataListPolicy,
    get_managed_install_surface_policy,
    get_manifest_metadata_list_policies,
    get_runtime_descriptor,
    get_shared_install_metadata,
    list_runtime_names,
    managed_install_globs_have_files,
    normalize_manifest_file_entries,
    normalize_manifest_relpath,
    normalize_runtime_name,
)

_SHARED_INSTALL_METADATA = get_shared_install_metadata()
GPD_INSTALL_DIR_NAME = _SHARED_INSTALL_METADATA.install_root_dir_name
MANIFEST_NAME = _SHARED_INSTALL_METADATA.manifest_name
_MANIFEST_RUNTIME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def get_adapter(runtime: str):
    """Lazily resolve the runtime adapter to keep manifest parsing lightweight."""
    from gpd.adapters import get_adapter as resolve_adapter

    return resolve_adapter(runtime)


def build_runtime_install_repair_command(
    runtime: str,
    *,
    install_scope: str | None,
    target_dir: Path,
    explicit_target: bool = False,
) -> str:
    """Lazily resolve the public repair-command helper."""
    from gpd.adapters import install_utils

    return install_utils.build_runtime_install_repair_command(
        runtime,
        install_scope=install_scope,
        target_dir=target_dir,
        explicit_target=explicit_target,
    )


def _canonical_manifest_runtime_name(value: str) -> str | None:
    """Return the exact canonical runtime id stored in trusted install manifests."""

    normalized = value.strip()
    if not normalized:
        return None

    return normalized if normalized in list_runtime_names() else None


def _unsupported_manifest_runtime_name(value: str) -> str | None:
    """Return a well-formed unsupported runtime id, or ``None`` for malformed drift."""

    normalized = value.strip()
    if not normalized or _MANIFEST_RUNTIME_ID_RE.fullmatch(normalized) is None:
        return None
    if normalize_runtime_name(normalized) is not None:
        return None
    return normalized


@dataclass(frozen=True, slots=True)
class InstallTargetAssessment:
    """Shared classification of a runtime config dir's GPD install state."""

    config_dir: Path
    expected_runtime: str | None
    state: str
    manifest_state: str
    manifest_runtime: str | None
    has_managed_markers: bool
    missing_install_artifacts: tuple[str, ...] = ()
    manifest_scope_state: str = "missing"
    manifest_scope: str | None = None
    manifest_explicit_target_state: str = "missing"
    manifest_explicit_target: bool | None = None

    @property
    def readiness_state(self) -> str:
        """Return the coarse readiness state derived from the install assessment."""
        return "ready" if self.state in {"absent", "clean", "owned_complete"} else "blocked"

    def readiness_message(self, runtime: str | None = None) -> str:
        """Return a human-readable summary for the current install assessment."""
        if self.state == "owned_incomplete":
            missing = ", ".join(f"`{item}`" for item in self.missing_install_artifacts) or "required install artifacts"
            return f"{self.config_dir} has an incomplete GPD install; missing artifacts: {missing}."
        if self.state == "foreign_runtime":
            owner = f"`{self.manifest_runtime}`" if self.manifest_runtime else "another runtime"
            runtime_label = f"`{runtime}`" if runtime else "the selected runtime"
            return f"{self.config_dir} belongs to {owner}, not {runtime_label}."
        if self.state == "untrusted_manifest":
            return f"{self.config_dir} has an untrusted GPD manifest and cannot be treated as a ready install target."
        if self.state == "unsupported_runtime":
            owner = f"`{self.manifest_runtime}`" if self.manifest_runtime else "an unsupported runtime"
            return f"{self.config_dir} belongs to {owner}, which is not supported by this GPD version."
        if self.state == "owned_complete":
            owner = f"`{self.manifest_runtime}`" if self.manifest_runtime else "the selected runtime"
            return f"{self.config_dir} already contains a complete GPD install for {owner}."
        if self.state == "clean":
            return f"{self.config_dir} is ready for a new GPD install."
        return f"{self.config_dir} is ready for installation."


@dataclass(frozen=True, slots=True)
class ManagedInstallSurface:
    """Observed managed install surfaces under a runtime config directory."""

    has_gpd_content: bool
    has_nested_commands: bool
    has_flat_commands: bool
    has_managed_agents: bool

    @property
    def has_managed_markers(self) -> bool:
        return any(
            (
                self.has_gpd_content,
                self.has_nested_commands,
                self.has_flat_commands,
                self.has_managed_agents,
            )
        )


@dataclass(frozen=True, slots=True)
class InstallManifestSnapshot:
    """Parsed install-manifest identity facts for a runtime config directory."""

    config_dir: Path
    parse_state: str
    payload: dict[str, object]
    runtime_state: str
    runtime: str | None
    scope_state: str
    install_scope: str | None
    explicit_target_state: str
    explicit_target: bool | None

    @property
    def manifest_path(self) -> Path:
        """Return the manifest path represented by this snapshot."""
        return self.config_dir / MANIFEST_NAME

    @property
    def exists_as_object(self) -> bool:
        """Return whether the manifest exists and parsed as a JSON object."""
        return self.parse_state == "ok"

    def matches_candidate(self, *, runtime: str | None = None, scope: str | None = None) -> bool:
        """Return whether this snapshot proves the requested runtime and scope facts."""
        if runtime is not None and (self.runtime_state != "ok" or self.runtime != runtime):
            return False
        if scope is not None and (self.scope_state != "ok" or self.install_scope != scope):
            return False
        return True


def inspect_managed_install_surface(config_dir: Path, *, runtime: str | None = None) -> ManagedInstallSurface:
    """Return the managed install surfaces currently materialized in *config_dir*."""
    policy = get_managed_install_surface_policy(runtime)

    return ManagedInstallSurface(
        has_gpd_content=managed_install_globs_have_files(config_dir, policy.gpd_content_globs, on_error=True),
        has_nested_commands=managed_install_globs_have_files(config_dir, policy.nested_command_globs, on_error=True),
        has_flat_commands=managed_install_globs_have_files(config_dir, policy.flat_command_globs, on_error=True),
        has_managed_agents=managed_install_globs_have_files(config_dir, policy.managed_agent_globs, on_error=True),
    )


def config_dir_has_managed_install_markers(config_dir: Path, *, runtime: str | None = None) -> bool:
    """Return whether *config_dir* carries any managed GPD install markers."""
    return inspect_managed_install_surface(config_dir, runtime=runtime).has_managed_markers


def _load_install_manifest_payload(config_dir: Path) -> tuple[str, dict[str, object]]:
    manifest_path = config_dir / MANIFEST_NAME
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", {}
    except (OSError, UnicodeDecodeError):
        return "corrupt", {}

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return "corrupt", {}

    if not isinstance(payload, dict):
        return "invalid", {}
    return "ok", payload


def _classify_manifest_runtime(payload: dict[str, object]) -> tuple[str, str | None]:
    if "runtime" not in payload:
        return "missing_runtime", None

    runtime = payload.get("runtime")
    if not isinstance(runtime, str):
        return "malformed_runtime", None

    normalized_runtime = runtime.strip()
    if not normalized_runtime:
        return "malformed_runtime", None

    canonical_runtime = _canonical_manifest_runtime_name(normalized_runtime)
    if canonical_runtime is not None:
        return "ok", canonical_runtime

    unsupported_runtime = _unsupported_manifest_runtime_name(normalized_runtime)
    if unsupported_runtime is not None:
        return "unsupported_runtime", unsupported_runtime
    return "malformed_runtime", None


def _classify_manifest_scope(payload: dict[str, object]) -> tuple[str, str | None]:
    if "install_scope" not in payload:
        return "missing_install_scope", None

    scope = payload.get("install_scope")
    if not isinstance(scope, str):
        return "malformed_install_scope", None

    normalized_scope = scope.strip()
    if normalized_scope not in {"local", "global"}:
        return "malformed_install_scope", None
    return "ok", normalized_scope


def _classify_manifest_explicit_target(payload: dict[str, object]) -> tuple[str, bool | None]:
    if "explicit_target" not in payload:
        return "missing_explicit_target", None

    explicit_target = payload.get("explicit_target")
    if not isinstance(explicit_target, bool):
        return "malformed_explicit_target", None
    return "ok", explicit_target


def load_install_manifest_snapshot(config_dir: Path) -> InstallManifestSnapshot:
    """Return the parsed manifest payload and derived identity facts for *config_dir*."""

    parse_state, payload = _load_install_manifest_payload(config_dir)
    if parse_state != "ok":
        return InstallManifestSnapshot(
            config_dir=config_dir,
            parse_state=parse_state,
            payload=payload,
            runtime_state=parse_state,
            runtime=None,
            scope_state=parse_state,
            install_scope=None,
            explicit_target_state=parse_state,
            explicit_target=None,
        )

    runtime_state, runtime = _classify_manifest_runtime(payload)
    scope_state, install_scope = _classify_manifest_scope(payload)
    explicit_target_state, explicit_target = _classify_manifest_explicit_target(payload)
    return InstallManifestSnapshot(
        config_dir=config_dir,
        parse_state=parse_state,
        payload=payload,
        runtime_state=runtime_state,
        runtime=runtime,
        scope_state=scope_state,
        install_scope=install_scope,
        explicit_target_state=explicit_target_state,
        explicit_target=explicit_target,
    )


def load_install_manifest_state(config_dir: Path) -> tuple[str, dict[str, object]]:
    """Return the manifest parse state and payload for *config_dir*.

    The state is one of ``missing``, ``corrupt``, ``invalid``, or ``ok``.
    ``ok`` means the manifest parsed as a mapping; the payload is the parsed
    dict in that case and ``{}`` otherwise.
    """

    snapshot = load_install_manifest_snapshot(config_dir)
    return snapshot.parse_state, snapshot.payload


def load_install_manifest_runtime_status(config_dir: Path) -> tuple[str, dict[str, object], str | None]:
    """Return the manifest parse state, payload, and runtime id when available."""

    snapshot = load_install_manifest_snapshot(config_dir)
    return snapshot.runtime_state, snapshot.payload, snapshot.runtime


def load_install_manifest_scope_status(config_dir: Path) -> tuple[str, dict[str, object], str | None]:
    """Return the manifest parse state, payload, and canonical install scope when available."""

    snapshot = load_install_manifest_snapshot(config_dir)
    return snapshot.scope_state, snapshot.payload, snapshot.install_scope


def load_install_manifest_explicit_target_status(config_dir: Path) -> tuple[str, dict[str, object], bool | None]:
    """Return the manifest parse state, payload, and explicit-target flag when available."""

    snapshot = load_install_manifest_snapshot(config_dir)
    return snapshot.explicit_target_state, snapshot.payload, snapshot.explicit_target


def _safe_manifest_path_segment(value: object) -> str | None:
    relpath = normalize_manifest_relpath(value)
    if relpath is None or "/" in relpath:
        return None
    return relpath


def _manifest_metadata_list_policy_is_satisfied(
    payload: dict[str, object],
    policy: ManifestMetadataListPolicy,
) -> bool:
    raw_values = payload.get(policy.key)
    if raw_values is None:
        return True
    if not isinstance(raw_values, list):
        return False
    for raw_value in raw_values:
        if policy.value_kind == "path_segment":
            value = _safe_manifest_path_segment(raw_value)
        elif policy.value_kind == "relpath":
            value = normalize_manifest_relpath(raw_value)
        else:
            return False
        if value is None:
            return False
        prefix = policy.item_prefix
        suffix = policy.item_suffix
        if prefix is not None and not value.startswith(prefix):
            return False
        if suffix is not None and not value.endswith(suffix):
            return False
    return True


def _manifest_scalar_path_metadata_key_suffixes(runtime: str) -> tuple[str, ...]:
    try:
        descriptor = get_runtime_descriptor(runtime)
    except KeyError:
        return ()

    roots: list[str] = []
    seen_roots: set[str] = set()
    for prefix in descriptor.manifest_file_prefixes:
        root = prefix.replace("\\", "/").strip("/").split("/", 1)[0]
        if not root or root in seen_roots:
            continue
        seen_roots.add(root)
        roots.append(root)
    return tuple(f"_{root}_dir" for root in roots)


def _manifest_scalar_path_is_within_install_owner(value: object, *, config_dir: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False

    owner_dir = config_dir.parent
    raw_path = Path(value).expanduser()
    candidate = raw_path if raw_path.is_absolute() else owner_dir / raw_path
    try:
        resolved_owner = owner_dir.resolve(strict=False)
        resolved_candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return False
    return resolved_candidate != resolved_owner and resolved_candidate.is_relative_to(resolved_owner)


def _manifest_scalar_path_metadata_state(payload: dict[str, object], *, config_dir: Path, runtime: str) -> str:
    scalar_path_key_suffixes = _manifest_scalar_path_metadata_key_suffixes(runtime)
    if not scalar_path_key_suffixes:
        return "ok"

    for key, value in payload.items():
        if any(key.endswith(suffix) for suffix in scalar_path_key_suffixes):
            if not _manifest_scalar_path_is_within_install_owner(value, config_dir=config_dir):
                return "malformed_scalar_path_metadata"
    return "ok"


def _manifest_path_metadata_state(payload: dict[str, object], *, config_dir: Path, runtime: str) -> str:
    raw_files = payload.get("files")
    if raw_files is not None and normalize_manifest_file_entries(raw_files) is None:
        return "malformed_files"

    runtime_policies = get_manifest_metadata_list_policies(runtime)
    runtime_policy_keys = {policy.key for policy in runtime_policies}
    known_policy_keys = {policy.key for policy in get_manifest_metadata_list_policies()}
    if any(key in payload and key not in runtime_policy_keys for key in known_policy_keys):
        return "malformed_path_metadata"

    for policy in runtime_policies:
        if not _manifest_metadata_list_policy_is_satisfied(payload, policy):
            return "malformed_path_metadata"

    scalar_path_metadata_state = _manifest_scalar_path_metadata_state(payload, config_dir=config_dir, runtime=runtime)
    if scalar_path_metadata_state != "ok":
        return scalar_path_metadata_state

    return "ok"


def assess_install_target(
    config_dir: Path,
    *,
    expected_runtime: str | None = None,
    manifest: InstallManifestSnapshot | None = None,
) -> InstallTargetAssessment:
    """Classify the GPD install state for *config_dir*.

    States:
    - ``absent``: target path does not exist and has no managed markers
    - ``clean``: target path exists but contains no managed GPD surface
    - ``owned_complete``: valid manifest for the owning runtime and complete install
    - ``owned_incomplete``: valid manifest for the owning runtime but missing install artifacts
    - ``unsupported_runtime``: valid manifest for a runtime that this GPD version does not support
    - ``foreign_runtime``: valid manifest, but ownership belongs to another runtime
    - ``untrusted_manifest``: manifest missing/corrupt/malformed on a managed surface
    """

    resolved = config_dir.expanduser().resolve(strict=False)
    if manifest is None:
        manifest = load_install_manifest_snapshot(resolved)
    elif manifest.config_dir.expanduser().resolve(strict=False) != resolved:
        raise ValueError("install manifest snapshot config_dir does not match assessed config_dir")

    manifest_state = manifest.runtime_state
    manifest_runtime = manifest.runtime
    manifest_scope_state = manifest.scope_state
    has_managed_markers = config_dir_has_managed_install_markers(resolved)
    missing_install_artifacts: tuple[str, ...] = ()

    def _assessment(
        *,
        state: str,
        manifest_state: str,
        has_managed_markers: bool,
        missing_install_artifacts: tuple[str, ...] = (),
    ) -> InstallTargetAssessment:
        return InstallTargetAssessment(
            config_dir=resolved,
            expected_runtime=expected_runtime,
            state=state,
            manifest_state=manifest_state,
            manifest_runtime=manifest_runtime,
            has_managed_markers=has_managed_markers,
            missing_install_artifacts=missing_install_artifacts,
            manifest_scope_state=manifest.scope_state,
            manifest_scope=manifest.install_scope,
            manifest_explicit_target_state=manifest.explicit_target_state,
            manifest_explicit_target=manifest.explicit_target,
        )

    if manifest_state == "ok" and manifest_runtime is not None:
        if expected_runtime is not None and manifest_runtime != expected_runtime:
            return _assessment(
                state="foreign_runtime",
                manifest_state=manifest_state,
                has_managed_markers=True,
            )
        if manifest_scope_state != "ok":
            return _assessment(
                state="untrusted_manifest",
                manifest_state=manifest_scope_state,
                has_managed_markers=True,
            )
        explicit_target_state = manifest.explicit_target_state
        if explicit_target_state in {"missing_explicit_target", "malformed_explicit_target"}:
            return _assessment(
                state="untrusted_manifest",
                manifest_state=explicit_target_state,
                has_managed_markers=True,
            )
        path_metadata_state = _manifest_path_metadata_state(
            manifest.payload,
            config_dir=resolved,
            runtime=manifest_runtime,
        )
        if path_metadata_state != "ok":
            return _assessment(
                state="untrusted_manifest",
                manifest_state=path_metadata_state,
                has_managed_markers=True,
            )
        try:
            adapter = get_adapter(manifest_runtime)
        except KeyError:
            state = "untrusted_manifest"
        else:
            missing_install_artifacts = adapter.missing_install_artifacts(resolved)
            state = "owned_complete" if not missing_install_artifacts else "owned_incomplete"
        return _assessment(
            state=state,
            manifest_state=manifest_state,
            has_managed_markers=True,
            missing_install_artifacts=missing_install_artifacts,
        )

    if manifest_state == "unsupported_runtime" and manifest_runtime is not None:
        state = "foreign_runtime" if expected_runtime is not None else "unsupported_runtime"
        return _assessment(
            state=state,
            manifest_state=manifest_state,
            has_managed_markers=True,
        )

    if manifest_state == "missing" and not has_managed_markers:
        state = "absent" if not resolved.exists() else "clean"
    else:
        state = "untrusted_manifest"

    return _assessment(
        state=state,
        manifest_state=manifest_state,
        has_managed_markers=has_managed_markers,
    )


def install_scope_from_manifest(config_dir: Path) -> str | None:
    """Return the persisted install scope for *config_dir*."""

    manifest = load_install_manifest_snapshot(config_dir)
    return manifest.install_scope if manifest.scope_state == "ok" else None


def _manifest_runtime(config_dir: Path) -> str | None:
    """Return the authoritative runtime declared in *config_dir*'s manifest."""
    manifest = load_install_manifest_snapshot(config_dir)
    return manifest.runtime if manifest.runtime_state == "ok" else None


def installed_runtime(config_dir: Path) -> str | None:
    """Return the authoritative runtime declared by *config_dir*'s manifest."""
    return _manifest_runtime(config_dir)


def config_dir_has_complete_install(config_dir: Path) -> bool:
    """Return whether *config_dir* is a complete install with authoritative runtime identity."""
    return assess_install_target(config_dir).state == "owned_complete"


def installed_update_command(config_dir: Path) -> str | None:
    """Return the bootstrap update command for the install in *config_dir*."""

    manifest = load_install_manifest_snapshot(config_dir)
    if manifest.runtime_state != "ok" or manifest.runtime is None:
        return None

    scope = manifest.payload.get("install_scope")
    if not isinstance(scope, str) or scope not in {"local", "global"}:
        return None

    if manifest.explicit_target_state != "ok" or manifest.explicit_target is None:
        # Fail closed for manifests that do not prove whether the
        # install was explicitly targeted. Update-command synthesis is only
        # trusted when the manifest carries the authoritative flag.
        return None

    try:
        get_adapter(manifest.runtime)
    except KeyError:
        return None

    return build_runtime_install_repair_command(
        manifest.runtime,
        install_scope=scope,
        target_dir=config_dir,
        explicit_target=manifest.explicit_target,
    )
