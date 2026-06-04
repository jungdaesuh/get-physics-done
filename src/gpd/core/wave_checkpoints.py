"""Helper-owned rollback checkpoint tags for phase wave execution."""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gpd.core.constants import ProjectLayout
from gpd.core.utils import phase_normalize

CheckpointNamespace = Literal["phase", "sweep"]
CleanupPolicy = Literal["preserve-on-failure", "successful-closeout"]

_VALID_NAMESPACES: frozenset[str] = frozenset({"phase", "sweep"})
_VALID_CLEANUP_POLICIES: frozenset[str] = frozenset({"preserve-on-failure", "successful-closeout"})


class WaveCheckpointCreateResult(BaseModel):
    """Result of creating a rollback checkpoint tag before a wave starts."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    operation: str = "create"
    mutation_boundary: str = "mutating"
    mutated: bool = False
    created: bool = False
    phase: str
    wave: str
    namespace: str = "phase"
    tag: str | None = None
    commit: str | None = None
    project_root: str
    git_root: str | None = None
    safe_to_execute_wave: bool = False
    preservation_policy: str = "preserve-until-successful-closeout"
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WaveCheckpointListResult(BaseModel):
    """Read-only inventory of helper-owned rollback checkpoint tags."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    operation: str = "list"
    mutation_boundary: str = "read_only"
    mutated: bool = False
    phase: str
    namespace: str = "phase"
    project_root: str
    git_root: str | None = None
    tags: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WaveCheckpointCleanupResult(BaseModel):
    """Result of deleting helper-owned rollback checkpoint tags."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    operation: str = "cleanup"
    mutation_boundary: str = "mutating"
    mutated: bool = False
    phase: str
    namespace: str = "phase"
    project_root: str
    git_root: str | None = None
    policy: str
    cleanup_allowed: bool = False
    deleted_tags: list[str] = Field(default_factory=list)
    preserved_tags: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _normalize_namespace(namespace: str) -> str:
    normalized = str(namespace).strip().lower().replace("_", "-")
    if normalized not in _VALID_NAMESPACES:
        expected = ", ".join(sorted(_VALID_NAMESPACES))
        raise ValueError(f"checkpoint namespace must be one of: {expected}")
    return normalized


def _normalize_cleanup_policy(policy: str) -> str:
    normalized = str(policy).strip().lower().replace("_", "-")
    if normalized not in _VALID_CLEANUP_POLICIES:
        expected = ", ".join(sorted(_VALID_CLEANUP_POLICIES))
        raise ValueError(f"checkpoint cleanup policy must be one of: {expected}")
    return normalized


def _project_root(cwd: Path) -> Path:
    return cwd.expanduser().resolve(strict=False)


def _helper_owned_tag_pattern(*, phase: str, namespace: str) -> re.Pattern[str]:
    escaped_phase = re.escape(phase)
    escaped_namespace = re.escape(namespace)
    return re.compile(
        rf"^gpd-checkpoint-{escaped_namespace}-{escaped_phase}-wave-"
        r"(?P<wave>\d+(?:\.\d+)*)-\d{14}-[0-9a-fA-F]{4,}(?:-retry-\d+)?$"
    )


def _tag_glob(*, phase: str, namespace: str) -> str:
    return f"gpd-checkpoint-{namespace}-{phase}-*"


def _run_git(project_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_root(project_root: Path) -> tuple[Path | None, list[str]]:
    result = _run_git(project_root, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip() or "git root not found"
        return None, [message]
    raw_root = result.stdout.strip()
    if not raw_root:
        return None, ["git rev-parse returned an empty root"]
    return Path(raw_root).expanduser().resolve(strict=False), []


def _short_head(project_root: Path) -> tuple[str | None, list[str]]:
    result = _run_git(project_root, ["rev-parse", "--short=12", "HEAD"])
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip() or "git HEAD is not available"
        return None, [message]
    short = result.stdout.strip()
    if not short:
        return None, ["git HEAD resolved to an empty commit id"]
    return short, []


def _safety_errors(project_root: Path, git_root: Path | None, git_errors: list[str]) -> list[str]:
    errors: list[str] = []
    if not ProjectLayout(project_root).gpd.is_dir():
        errors.append("rollback checkpoint requires a visible GPD/ project root")
    if git_root is None:
        errors.append("rollback checkpoint requires a project-local git root")
        errors.extend(git_errors)
    elif git_root.resolve(strict=False) != project_root.resolve(strict=False):
        errors.append(
            "rollback checkpoint requires git root to equal project root; "
            f"project_root={project_root.as_posix()} git_root={git_root.as_posix()}"
        )
    return list(dict.fromkeys(error for error in errors if error))


def _git_tag_exists(project_root: Path, tag: str) -> bool:
    result = _run_git(project_root, ["rev-parse", "--verify", f"refs/tags/{tag}"])
    return result.returncode == 0


def _list_helper_owned_tags(project_root: Path, *, phase: str, namespace: str) -> tuple[list[str], list[str]]:
    result = _run_git(project_root, ["tag", "-l", _tag_glob(phase=phase, namespace=namespace)])
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip() or "git tag inventory failed"
        return [], [message]
    pattern = _helper_owned_tag_pattern(phase=phase, namespace=namespace)
    tags = [tag for tag in result.stdout.splitlines() if pattern.match(tag.strip())]
    return sorted(tags), []


def create_wave_checkpoint(
    cwd: Path,
    *,
    phase: str,
    wave: str | int,
    namespace: CheckpointNamespace = "phase",
) -> WaveCheckpointCreateResult:
    """Create a helper-owned rollback checkpoint tag before wave execution."""

    project_root = _project_root(cwd)
    normalized_phase = phase_normalize(str(phase).strip())
    normalized_wave = str(wave).strip()
    normalized_namespace = _normalize_namespace(namespace)
    git_root, git_errors = _git_root(project_root)
    safety_errors = _safety_errors(project_root, git_root, git_errors)

    base_payload = {
        "phase": normalized_phase,
        "wave": normalized_wave,
        "namespace": normalized_namespace,
        "project_root": project_root.as_posix(),
        "git_root": git_root.as_posix() if git_root is not None else None,
    }
    if safety_errors:
        return WaveCheckpointCreateResult(errors=safety_errors, **base_payload)

    commit, commit_errors = _short_head(project_root)
    if commit is None:
        return WaveCheckpointCreateResult(errors=commit_errors, **base_payload)

    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    base_tag = f"gpd-checkpoint-{normalized_namespace}-{normalized_phase}-wave-{normalized_wave}-{timestamp}-{commit}"
    last_error: str | None = None
    for attempt in range(0, 25):
        tag = base_tag if attempt == 0 else f"{base_tag}-retry-{attempt}"
        if _git_tag_exists(project_root, tag):
            last_error = f"checkpoint tag already exists: {tag}"
            continue
        result = _run_git(project_root, ["tag", tag])
        if result.returncode == 0:
            return WaveCheckpointCreateResult(
                mutated=True,
                created=True,
                tag=tag,
                commit=commit,
                safe_to_execute_wave=True,
                **base_payload,
            )
        message = (result.stderr or result.stdout).strip() or f"failed to create checkpoint tag {tag}"
        last_error = message
        if "already exists" not in message:
            break

    return WaveCheckpointCreateResult(errors=[last_error or "failed to create checkpoint tag"], **base_payload)


def list_wave_checkpoints(
    cwd: Path,
    *,
    phase: str,
    namespace: CheckpointNamespace = "phase",
) -> WaveCheckpointListResult:
    """List helper-owned rollback checkpoint tags for a phase."""

    project_root = _project_root(cwd)
    normalized_phase = phase_normalize(str(phase).strip())
    normalized_namespace = _normalize_namespace(namespace)
    git_root, git_errors = _git_root(project_root)
    safety_errors = _safety_errors(project_root, git_root, git_errors)
    base_payload = {
        "phase": normalized_phase,
        "namespace": normalized_namespace,
        "project_root": project_root.as_posix(),
        "git_root": git_root.as_posix() if git_root is not None else None,
    }
    if safety_errors:
        return WaveCheckpointListResult(errors=safety_errors, **base_payload)
    tags, errors = _list_helper_owned_tags(project_root, phase=normalized_phase, namespace=normalized_namespace)
    return WaveCheckpointListResult(tags=tags, errors=errors, **base_payload)


def cleanup_wave_checkpoints(
    cwd: Path,
    *,
    phase: str,
    namespace: CheckpointNamespace = "phase",
    policy: CleanupPolicy = "preserve-on-failure",
) -> WaveCheckpointCleanupResult:
    """Delete helper-owned rollback checkpoint tags when closeout policy allows it."""

    project_root = _project_root(cwd)
    normalized_phase = phase_normalize(str(phase).strip())
    normalized_namespace = _normalize_namespace(namespace)
    normalized_policy = _normalize_cleanup_policy(policy)
    git_root, git_errors = _git_root(project_root)
    safety_errors = _safety_errors(project_root, git_root, git_errors)
    base_payload = {
        "phase": normalized_phase,
        "namespace": normalized_namespace,
        "project_root": project_root.as_posix(),
        "git_root": git_root.as_posix() if git_root is not None else None,
        "policy": normalized_policy,
    }
    if safety_errors:
        return WaveCheckpointCleanupResult(errors=safety_errors, **base_payload)

    tags, list_errors = _list_helper_owned_tags(project_root, phase=normalized_phase, namespace=normalized_namespace)
    if list_errors:
        return WaveCheckpointCleanupResult(errors=list_errors, **base_payload)

    if normalized_policy == "preserve-on-failure":
        return WaveCheckpointCleanupResult(
            preserved_tags=tags,
            warnings=["checkpoint cleanup policy preserved tags for failure/recovery auditability"],
            **base_payload,
        )

    try:
        from gpd.core.phase_closeout import phase_closeout_readiness

        readiness = phase_closeout_readiness(project_root, normalized_phase, require_verification=True)
    except Exception as exc:  # noqa: BLE001 - fail closed at a mutation boundary
        return WaveCheckpointCleanupResult(
            preserved_tags=tags,
            errors=[f"closeout readiness check failed before checkpoint cleanup: {exc}"],
            **base_payload,
        )

    if not readiness.ready:
        return WaveCheckpointCleanupResult(
            preserved_tags=tags,
            errors=["checkpoint cleanup refused because closeout readiness is not satisfied", *readiness.blockers],
            **base_payload,
        )
    if readiness.preserve_checkpoint_tags:
        return WaveCheckpointCleanupResult(
            cleanup_allowed=False,
            preserved_tags=tags,
            warnings=[
                "checkpoint tags preserved by closeout readiness policy",
                *readiness.warnings,
            ],
            **base_payload,
        )

    deleted: list[str] = []
    errors: list[str] = []
    for tag in tags:
        result = _run_git(project_root, ["tag", "-d", tag])
        if result.returncode == 0:
            deleted.append(tag)
            continue
        message = (result.stderr or result.stdout).strip() or f"failed to delete checkpoint tag {tag}"
        errors.append(message)

    return WaveCheckpointCleanupResult(
        mutated=bool(deleted),
        cleanup_allowed=not errors,
        deleted_tags=deleted,
        preserved_tags=[tag for tag in tags if tag not in deleted],
        errors=errors,
        **base_payload,
    )


__all__ = [
    "CleanupPolicy",
    "CheckpointNamespace",
    "WaveCheckpointCleanupResult",
    "WaveCheckpointCreateResult",
    "WaveCheckpointListResult",
    "cleanup_wave_checkpoints",
    "create_wave_checkpoint",
    "list_wave_checkpoints",
]
