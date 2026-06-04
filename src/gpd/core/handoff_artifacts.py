"""Filesystem validation for spawned-agent artifact handoffs."""

from __future__ import annotations

import fnmatch
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from gpd.core.return_contract import VALID_RETURN_STATUSES, validate_gpd_return_markdown
from gpd.core.return_repair_classifier import (
    REPAIRABLE_RETURN_CLASSES,
    ReturnRepairClass,
    return_failure_class_from_repair_class,
    return_repair_class_from_validation_error,
)


class HandoffFailureClass(StrEnum):
    """Stable failure classes for child return/artifact handoff routing."""

    RETURN_MISSING = "return_missing"
    RETURN_MALFORMED_REPAIRABLE = "return_malformed_repairable"
    RETURN_MALFORMED_BLOCKING = "return_malformed_blocking"
    RETURN_STATUS_ROUTE = "return_status_route"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_STALE = "artifact_stale"
    ARTIFACT_PATH_REPAIRABLE = "artifact_path_repairable"
    ARTIFACT_ROOT_BLOCKED = "artifact_root_blocked"
    VALIDATOR_FAILED = "validator_failed"
    APPLICATOR_FAILED = "applicator_failed"


class HandoffFailure(BaseModel):
    """Structured detail for one handoff validation failure."""

    failure_class: HandoffFailureClass
    code: str
    message: str
    path: str | None = None
    command: str | None = None
    repairable: bool = False


class HandoffArtifactValidationResult(BaseModel):
    """Result for reconciling a child ``gpd_return`` with on-disk artifacts."""

    passed: bool
    mutated: bool = False
    mutates: bool = False
    primary_failure_class: HandoffFailureClass | None = None
    failure_classes: list[HandoffFailureClass] = Field(default_factory=list)
    failures: list[HandoffFailure] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    status: str | None = None
    files_written: list[str] = Field(default_factory=list)
    checked_files: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    expected_globs: list[str] = Field(default_factory=list)
    allowed_roots: list[str] = Field(default_factory=list)


def parse_fresh_after(value: str | None) -> datetime | None:
    """Parse a CLI freshness timestamp."""
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"--fresh-after must be an ISO 8601 timestamp, got {value!r}") from exc


def validate_handoff_artifacts_markdown(
    project_root: Path,
    return_markdown: str,
    *,
    expected_artifacts: list[str] | tuple[str, ...] = (),
    expected_globs: list[str] | tuple[str, ...] = (),
    allowed_roots: list[str] | tuple[str, ...] = (),
    required_suffixes: list[str] | tuple[str, ...] = (),
    require_files_written: bool = False,
    require_status: str | None = None,
    fresh_after: datetime | None = None,
) -> HandoffArtifactValidationResult:
    """Validate that a spawned return names real, in-scope artifacts.

    This deliberately validates filesystem truth separately from the base
    ``gpd_return`` schema so workflow prompts can share one artifact gate.
    """
    root = project_root.expanduser().resolve(strict=False)
    errors: list[str] = []
    warnings: list[str] = []
    failures: list[HandoffFailure] = []

    normalized_required_status = _normalize_required_status(require_status)
    if require_status is not None and normalized_required_status is None:
        allowed = ", ".join(sorted(VALID_RETURN_STATUSES))
        message = f"required status must be one of: {allowed}"
        return _build_result(
            passed=False,
            errors=[message],
            failures=[
                _failure(
                    HandoffFailureClass.VALIDATOR_FAILED,
                    "invalid_required_status",
                    message,
                    repairable=True,
                )
            ],
            expected_artifacts=list(expected_artifacts),
            expected_globs=list(expected_globs),
            allowed_roots=list(allowed_roots),
        )

    return_validation = validate_gpd_return_markdown(return_markdown)
    if not return_validation.passed or return_validation.envelope is None:
        return _build_result(
            passed=False,
            errors=list(return_validation.errors),
            warnings=list(return_validation.warnings),
            failures=_classify_return_validation_errors(return_validation.errors),
            expected_artifacts=list(expected_artifacts),
            expected_globs=list(expected_globs),
            allowed_roots=list(allowed_roots),
        )

    envelope = return_validation.envelope
    if normalized_required_status is not None and envelope.status != normalized_required_status:
        message = (
            f"gpd_return.status must be {normalized_required_status!r} for this artifact gate, got {envelope.status!r}"
        )
        errors.append(message)
        failures.append(
            _failure(
                HandoffFailureClass.RETURN_STATUS_ROUTE,
                "required_status_mismatch",
                message,
                repairable=False,
            )
        )

    files_written = [_normalize_project_local_path(path) for path in envelope.files_written]
    expected = [_normalize_project_local_path(path) for path in expected_artifacts]
    globs = [_normalize_project_local_path(pattern) for pattern in expected_globs]
    suffixes = tuple(suffix for suffix in required_suffixes if suffix)

    allowed_resolved, allowed_display, allowed_errors, allowed_failures = _normalize_allowed_roots(root, allowed_roots)
    errors.extend(allowed_errors)
    failures.extend(allowed_failures)

    if require_files_written and not files_written:
        message = "gpd_return.files_written is empty"
        errors.append(message)
        failures.append(_failure(HandoffFailureClass.ARTIFACT_MISSING, "files_written_empty", message))

    checked_files: list[str] = []
    seen_files: set[str] = set()
    for relpath in files_written:
        if relpath in seen_files:
            warnings.append(f"duplicate files_written entry: {relpath}")
            continue
        seen_files.add(relpath)
        _validate_one_artifact(
            root,
            relpath,
            errors=errors,
            failures=failures,
            checked_files=checked_files,
            allowed_roots=allowed_resolved,
            required_suffixes=suffixes,
            fresh_after=fresh_after,
        )

    files_written_set = set(files_written)
    for relpath in expected:
        if relpath not in files_written_set:
            message = f"expected artifact not named in gpd_return.files_written: {relpath}"
            errors.append(message)
            failures.append(
                _failure(
                    HandoffFailureClass.ARTIFACT_MISSING,
                    "expected_artifact_omitted",
                    message,
                    path=relpath,
                )
            )
        if relpath not in seen_files:
            _validate_one_artifact(
                root,
                relpath,
                errors=errors,
                failures=failures,
                checked_files=checked_files,
                allowed_roots=allowed_resolved,
                required_suffixes=suffixes,
                fresh_after=fresh_after,
            )

    for pattern in globs:
        if not any(fnmatch.fnmatch(relpath, pattern) for relpath in files_written):
            message = f"no files_written artifact matched expected glob: {pattern}"
            errors.append(message)
            failures.append(
                _failure(
                    HandoffFailureClass.ARTIFACT_MISSING,
                    "expected_glob_unmatched",
                    message,
                    path=pattern,
                )
            )

    return _build_result(
        passed=not errors,
        errors=errors,
        failures=failures,
        warnings=warnings + list(return_validation.warnings),
        status=envelope.status,
        files_written=files_written,
        checked_files=checked_files,
        expected_artifacts=expected,
        expected_globs=globs,
        allowed_roots=allowed_display,
    )


def _normalize_required_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip()
    if normalized not in VALID_RETURN_STATUSES:
        return None
    return normalized


def _normalize_project_local_path(path_text: str) -> str:
    raw = path_text.strip()
    if not raw:
        return raw
    return Path(raw).as_posix()


def _normalize_allowed_roots(
    root: Path,
    allowed_roots: list[str] | tuple[str, ...],
) -> tuple[list[Path], list[str], list[str], list[HandoffFailure]]:
    if not allowed_roots:
        return [root], ["."], [], []

    resolved_roots: list[Path] = []
    display_roots: list[str] = []
    errors: list[str] = []
    failures: list[HandoffFailure] = []
    for raw_root in allowed_roots:
        normalized = _normalize_project_local_path(raw_root)
        candidate = Path(normalized).expanduser()
        resolved = (
            candidate.resolve(strict=False) if candidate.is_absolute() else (root / candidate).resolve(strict=False)
        )
        if not resolved.is_relative_to(root):
            message = f"allowed root is outside project root: {raw_root}"
            errors.append(message)
            failures.append(
                _failure(
                    HandoffFailureClass.ARTIFACT_ROOT_BLOCKED,
                    "allowed_root_outside_project",
                    message,
                    path=raw_root,
                )
            )
            continue
        resolved_roots.append(resolved)
        display_roots.append(_display_project_path(root, resolved))
    return resolved_roots, display_roots, errors, failures


def _validate_one_artifact(
    root: Path,
    relpath: str,
    *,
    errors: list[str],
    failures: list[HandoffFailure],
    checked_files: list[str],
    allowed_roots: list[Path],
    required_suffixes: tuple[str, ...],
    fresh_after: datetime | None,
) -> None:
    if not relpath:
        message = "artifact path is empty"
        errors.append(message)
        failures.append(_failure(HandoffFailureClass.ARTIFACT_ROOT_BLOCKED, "empty_artifact_path", message))
        return

    raw_path = Path(relpath)
    if raw_path.is_absolute():
        message = f"artifact path must be project-local, not absolute: {relpath}"
        errors.append(message)
        resolved_absolute = raw_path.expanduser().resolve(strict=False)
        if resolved_absolute.is_relative_to(root) and any(
            resolved_absolute.is_relative_to(allowed_root) for allowed_root in allowed_roots
        ):
            failures.append(
                _failure(
                    HandoffFailureClass.ARTIFACT_PATH_REPAIRABLE,
                    "absolute_project_local",
                    message,
                    path=relpath,
                    repairable=True,
                )
            )
        else:
            code = "absolute_outside_project"
            if resolved_absolute.is_relative_to(root):
                code = "absolute_outside_allowed_roots"
            failures.append(
                _failure(
                    HandoffFailureClass.ARTIFACT_ROOT_BLOCKED,
                    code,
                    message,
                    path=relpath,
                )
            )
        return
    if any(part == ".." for part in raw_path.parts):
        message = f"artifact path must not traverse outside the project: {relpath}"
        errors.append(message)
        failures.append(
            _failure(
                HandoffFailureClass.ARTIFACT_ROOT_BLOCKED,
                "path_traversal",
                message,
                path=relpath,
            )
        )
        return

    resolved = (root / raw_path).resolve(strict=False)
    if not resolved.is_relative_to(root):
        message = f"artifact path resolves outside project root: {relpath}"
        errors.append(message)
        failures.append(
            _failure(
                HandoffFailureClass.ARTIFACT_ROOT_BLOCKED,
                "resolved_outside_project",
                message,
                path=relpath,
            )
        )
        return

    if not any(resolved.is_relative_to(allowed_root) for allowed_root in allowed_roots):
        message = f"artifact path is outside allowed roots: {relpath}"
        errors.append(message)
        failures.append(
            _failure(
                HandoffFailureClass.ARTIFACT_ROOT_BLOCKED,
                "outside_allowed_roots",
                message,
                path=relpath,
            )
        )

    if required_suffixes and not any(relpath.endswith(suffix) for suffix in required_suffixes):
        suffix_text = ", ".join(required_suffixes)
        message = f"artifact path does not end with required suffix ({suffix_text}): {relpath}"
        errors.append(message)
        failures.append(
            _failure(
                HandoffFailureClass.VALIDATOR_FAILED,
                "required_suffix_mismatch",
                message,
                path=relpath,
            )
        )

    if not resolved.is_file():
        message = f"artifact is missing or not a file: {relpath}"
        errors.append(message)
        failures.append(
            _failure(
                HandoffFailureClass.ARTIFACT_MISSING,
                "artifact_missing_or_not_file",
                message,
                path=relpath,
            )
        )
        return

    try:
        with resolved.open("rb"):
            pass
    except OSError as exc:
        message = f"artifact is not readable: {relpath}: {exc}"
        errors.append(message)
        failures.append(
            _failure(
                HandoffFailureClass.ARTIFACT_MISSING,
                "artifact_unreadable",
                message,
                path=relpath,
            )
        )
        return

    if fresh_after is not None:
        file_mtime = datetime.fromtimestamp(resolved.stat().st_mtime, tz=fresh_after.tzinfo)
        if file_mtime < fresh_after:
            message = f"artifact is stale relative to --fresh-after: {relpath}"
            errors.append(message)
            failures.append(
                _failure(
                    HandoffFailureClass.ARTIFACT_STALE,
                    "artifact_stale",
                    message,
                    path=relpath,
                )
            )

    if relpath not in checked_files:
        checked_files.append(relpath)


def _display_project_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix() or "."
    except ValueError:
        return path.as_posix()


def _failure(
    failure_class: HandoffFailureClass,
    code: str,
    message: str,
    *,
    path: str | None = None,
    command: str | None = None,
    repairable: bool = False,
) -> HandoffFailure:
    return HandoffFailure(
        failure_class=failure_class,
        code=code,
        message=message,
        path=path,
        command=command,
        repairable=repairable,
    )


def _build_result(
    *,
    passed: bool,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    failures: list[HandoffFailure] | None = None,
    status: str | None = None,
    files_written: list[str] | None = None,
    checked_files: list[str] | None = None,
    expected_artifacts: list[str] | None = None,
    expected_globs: list[str] | None = None,
    allowed_roots: list[str] | None = None,
) -> HandoffArtifactValidationResult:
    result_failures = failures or []
    failure_classes: list[HandoffFailureClass] = []
    for failure in result_failures:
        if failure.failure_class not in failure_classes:
            failure_classes.append(failure.failure_class)

    return HandoffArtifactValidationResult(
        passed=passed,
        primary_failure_class=failure_classes[0] if failure_classes else None,
        failure_classes=failure_classes,
        failures=result_failures,
        errors=errors or [],
        warnings=warnings or [],
        status=status,
        files_written=files_written or [],
        checked_files=checked_files or [],
        expected_artifacts=expected_artifacts or [],
        expected_globs=expected_globs or [],
        allowed_roots=allowed_roots or [],
    )


def _classify_return_validation_errors(errors: list[str]) -> list[HandoffFailure]:
    failures: list[HandoffFailure] = []
    for message in errors:
        repair_class = return_repair_class_from_validation_error(message)
        failure_class = HandoffFailureClass(return_failure_class_from_repair_class(repair_class))
        failures.append(
            _failure(
                failure_class,
                _handoff_return_code(repair_class, message),
                message,
                repairable=repair_class in REPAIRABLE_RETURN_CLASSES,
            )
        )

    return failures


_HANDOFF_RETURN_CODE_BY_REPAIR_CLASS: dict[ReturnRepairClass, str] = {
    "missing_block": "missing_gpd_return_block",
    "unfenced_candidate": "missing_gpd_return_block",
    "wrong_fence_language": "malformed_return",
    "yaml_parse_error": "yaml_parse_error",
    "top_level_shape_error": "yaml_parse_error",
    "missing_required_fields": "missing_required_field",
    "invalid_status": "invalid_status",
    "scalar_list_drift": "invalid_list_field",
    "field_shape_error": "malformed_return",
    "unknown_field": "unknown_top_level_field",
    "status_field_forbidden": "status_disallowed_field",
    "transport_payload_in_return": "invalid_continuation_update",
    "applicator_owned_metadata": "applicator_owned_metadata",
    "continuation_schema_error": "invalid_continuation_update",
    "valid_non_completed": "required_status_mismatch",
    "required_status_mismatch": "required_status_mismatch",
    "ambiguous_multiple_returns": "ambiguous_multiple_returns",
}


def _handoff_return_code(repair_class: ReturnRepairClass, message: str) -> str:
    if repair_class == "invalid_status" and "canonical lowercase spelling" in message:
        return "status_case_drift"
    if repair_class == "field_shape_error":
        return _field_shape_handoff_return_code(message)
    return _HANDOFF_RETURN_CODE_BY_REPAIR_CLASS[repair_class]


def _field_shape_handoff_return_code(message: str) -> str:
    if "must be a list" in message or "Input should be a valid list" in message:
        return "invalid_list_field"
    if "must be a string" in message or "Input should be a valid string" in message:
        return "invalid_string_field"
    if "must be a mapping" in message or "Input should be a valid dictionary" in message:
        return "invalid_mapping_field"
    if "not a number" in message or "Input should be a valid integer" in message:
        return "invalid_number_field"
    return "malformed_return"
