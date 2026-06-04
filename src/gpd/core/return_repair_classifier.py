"""Read-only classification for malformed ``gpd_return`` envelopes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, Field

from gpd.core.return_contract import (
    GPD_RETURN_BLOCK_RE,
    VALID_RETURN_STATUSES,
    validate_gpd_return_markdown,
)

__all__ = [
    "REPAIRABLE_RETURN_CLASSES",
    "RETURN_REPAIR_HINTS",
    "ReturnRepairClassification",
    "ReturnRepairClass",
    "ReturnRepairFailureClass",
    "ReturnRepairRecoveryRoute",
    "classify_gpd_return_repair",
    "return_failure_class_from_repair_class",
    "return_repair_class_from_validation_error",
    "return_repair_hint",
]

ReturnRepairClass = Literal[
    "valid",
    "missing_block",
    "unfenced_candidate",
    "wrong_fence_language",
    "yaml_parse_error",
    "top_level_shape_error",
    "missing_required_fields",
    "invalid_status",
    "scalar_list_drift",
    "field_shape_error",
    "unknown_field",
    "status_field_forbidden",
    "transport_payload_in_return",
    "applicator_owned_metadata",
    "continuation_schema_error",
    "valid_non_completed",
    "required_status_mismatch",
    "ambiguous_multiple_returns",
]

ReturnRepairRecoveryRoute = Literal[
    "accept",
    "retry_child",
    "route_by_status",
    "explicit_main_context_fallback_with_own_return",
    "block_and_surface_errors",
]

ReturnRepairFailureClass = Literal[
    "return_missing",
    "return_malformed_repairable",
    "return_malformed_blocking",
    "return_status_route",
]

ReturnRepairConfidence = Literal["high", "medium", "low"]


class ReturnRepairClassification(BaseModel):
    """Stable, non-mutating triage result for one return payload."""

    passed: bool
    valid: bool
    accepted_for_success: bool
    safe_to_apply: bool = False
    primary_class: ReturnRepairClass
    primary_classification: ReturnRepairClass
    primary_failure_class: ReturnRepairClass
    failure_classes: list[ReturnRepairClass] = Field(default_factory=list)
    confidence: ReturnRepairConfidence = "high"
    mutated: Literal[False] = False
    mutates: Literal[False] = False
    may_patch_child_return: Literal[False] = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    original_errors: list[str] = Field(default_factory=list)
    original_warnings: list[str] = Field(default_factory=list)
    recovery_route: ReturnRepairRecoveryRoute
    repair_hint: str
    status: str | None = None
    required_status: str | None = None
    fields: dict[str, object] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


_FENCED_BLOCK_RE = re.compile(r"```(?P<language>[^\n`]*)\n(?P<body>[\s\S]*?)```")
_RAW_GPD_RETURN_YAML_RE = re.compile(r"(?m)^\s*gpd_return\s*:")
_RAW_GPD_RETURN_JSON_RE = re.compile(r"""["']gpd_return["']\s*:""")
_UNWRAPPED_RETURN_YAML_RE = re.compile(r"(?m)^\s*(status|files_written|issues|next_actions)\s*:")

_TOP_LEVEL_SHAPE_MARKERS = (
    "expected a mapping",
    "missing top-level gpd_return key",
    "unexpected top-level key",
    "gpd_return must be a mapping",
)
_LIST_DRIFT_MARKERS = (
    "files_written must be a list",
    "issues must be a list",
    "next_actions must be a list",
    "approved_plans must be a list",
    "blocked_plans must be a list",
    "checkpoint_hashes must be a list",
    "decisions must be a list",
    "blockers must be a list",
    "Input should be a valid list",
)
_FIELD_SHAPE_MARKERS = (
    "must be a list",
    "must be a mapping",
    "must be a string",
    "must be a boolean",
    "must be a non-empty string",
    "not a number",
    "Input should be a valid",
)

RETURN_REPAIR_HINTS: Mapping[ReturnRepairClass, str] = {
    "valid": "The return envelope validates and is acceptable for the requested status.",
    "missing_block": "Retry the child with one fenced ```yaml block whose top-level key is gpd_return.",
    "unfenced_candidate": "Retry with the candidate return wrapped in a canonical ```yaml gpd_return block.",
    "wrong_fence_language": "Retry with the return in a yaml/yml fence, not a JSON or unlabeled fence.",
    "yaml_parse_error": "Retry with parseable YAML inside the fenced gpd_return block.",
    "top_level_shape_error": "Retry with exactly one top-level gpd_return mapping in the YAML block.",
    "missing_required_fields": "Retry with status, files_written, issues, and next_actions present.",
    "invalid_status": "Retry with one canonical lowercase status: completed, checkpoint, blocked, or failed.",
    "scalar_list_drift": "Retry with list-valued return fields encoded as YAML arrays or sequences.",
    "field_shape_error": "Retry with field values matching the return schema shape.",
    "unknown_field": "Retry after removing typo or callsite-owned top-level fields from gpd_return.",
    "status_field_forbidden": "Stop and surface the status/field mismatch; do not patch durable fields in place.",
    "transport_payload_in_return": "Stop and surface the transport payload; child returns must not carry execution segments.",
    "applicator_owned_metadata": "Stop and surface the applicator-owned metadata; the applicator must supply it.",
    "continuation_schema_error": "Stop and surface the continuation schema error before any durable application.",
    "valid_non_completed": "Route by the typed non-completed status instead of treating it as a malformed return.",
    "required_status_mismatch": "Route by the typed status instead of treating the valid return as malformed.",
    "ambiguous_multiple_returns": "Retry with exactly one canonical gpd_return block.",
}

REPAIRABLE_RETURN_CLASSES: frozenset[ReturnRepairClass] = frozenset(
    {
        "missing_block",
        "unfenced_candidate",
        "wrong_fence_language",
        "yaml_parse_error",
        "top_level_shape_error",
        "missing_required_fields",
        "invalid_status",
        "scalar_list_drift",
        "field_shape_error",
        "unknown_field",
    }
)

_RETURN_FAILURE_CLASS_BY_REPAIR_CLASS: Mapping[str, ReturnRepairFailureClass] = {
    "missing_block": "return_missing",
    "unfenced_candidate": "return_malformed_repairable",
    "wrong_fence_language": "return_malformed_repairable",
    "yaml_parse_error": "return_malformed_repairable",
    "top_level_shape_error": "return_malformed_repairable",
    "missing_required_fields": "return_malformed_repairable",
    "invalid_status": "return_malformed_repairable",
    "scalar_list_drift": "return_malformed_repairable",
    "field_shape_error": "return_malformed_repairable",
    "unknown_field": "return_malformed_repairable",
    "status_field_forbidden": "return_malformed_blocking",
    "transport_payload_in_return": "return_malformed_blocking",
    "applicator_owned_metadata": "return_malformed_blocking",
    "continuation_schema_error": "return_malformed_blocking",
    "valid_non_completed": "return_status_route",
    "required_status_mismatch": "return_status_route",
    "ambiguous_multiple_returns": "return_malformed_blocking",
}


def classify_gpd_return_repair(
    content: str,
    *,
    require_status: str | None = "completed",
) -> ReturnRepairClassification:
    """Classify a raw return payload without mutating project state.

    The canonical parser remains ``validate_gpd_return_markdown``.  This helper
    only adds stable routing labels and hints around its errors.
    """
    required_status = _normalize_required_status(require_status)
    validation = validate_gpd_return_markdown(content)
    original_errors = list(validation.errors)
    original_warnings = list(validation.warnings)

    canonical_block_count = len(GPD_RETURN_BLOCK_RE.findall(content))
    if canonical_block_count > 1:
        return _classification(
            "ambiguous_multiple_returns",
            valid=False,
            accepted_for_success=False,
            original_errors=original_errors,
            original_warnings=original_warnings,
            recovery_route="retry_child",
            status=_status_from_validation(validation.fields),
            required_status=required_status,
            fields=dict(validation.fields),
            notes=[f"Found {canonical_block_count} canonical gpd_return blocks."],
        )

    if validation.passed:
        status = _status_from_validation(validation.fields)
        accepted = required_status is None or status == required_status
        if accepted:
            return _classification(
                "valid",
                valid=True,
                accepted_for_success=True,
                original_errors=original_errors,
                original_warnings=original_warnings,
                recovery_route="accept",
                status=status,
                required_status=required_status,
                fields=dict(validation.fields),
            )

        return _classification(
            "required_status_mismatch",
            valid=True,
            accepted_for_success=False,
            original_errors=original_errors,
            original_warnings=original_warnings,
            recovery_route="route_by_status",
            status=status,
            required_status=required_status,
            fields=dict(validation.fields),
            notes=[f"Validated status {status!r} does not match required status {required_status!r}."],
        )

    primary_class = _classify_validation_errors(content, original_errors)
    return _classification(
        primary_class,
        valid=False,
        accepted_for_success=False,
        original_errors=original_errors,
        original_warnings=original_warnings,
        recovery_route=_recovery_route(primary_class),
        required_status=required_status,
    )


def return_repair_hint(repair_class: ReturnRepairClass) -> str:
    """Return the stable user-facing repair hint for a repair class."""

    return RETURN_REPAIR_HINTS[repair_class]


def return_failure_class_from_repair_class(repair_class: ReturnRepairClass) -> ReturnRepairFailureClass:
    """Map rich return-repair classes to stable applicator failure classes."""

    if repair_class == "valid":
        raise ValueError("valid returns do not have a failure class")
    return _RETURN_FAILURE_CLASS_BY_REPAIR_CLASS[repair_class]


def return_repair_class_from_validation_error(
    error: str,
    *,
    content: str | None = None,
) -> ReturnRepairClass:
    """Classify one canonical parser error without mutating child output."""

    if error == "No gpd_return YAML block found":
        return _classify_missing_block(content or "")
    if error.startswith("Multiple gpd_return YAML blocks found:"):
        return "ambiguous_multiple_returns"
    if error.startswith("Missing required field:"):
        return "missing_required_fields"

    if "gpd_return YAML parse error" in error:
        if _contains_any(error, _TOP_LEVEL_SHAPE_MARKERS):
            return "top_level_shape_error"
        return "yaml_parse_error"
    if "canonical lowercase" in error or "Invalid status" in error or "status must be" in error:
        return "invalid_status"
    if "Unknown gpd_return top-level field" in error:
        return "unknown_field"
    if "status '" in error and "does not allow gpd_return field" in error:
        return "status_field_forbidden"
    if "execution_segment" in error:
        return "transport_payload_in_return"
    if "applicator-owned" in error:
        return "applicator_owned_metadata"
    if _is_continuation_schema_error(error):
        return "continuation_schema_error"
    if _contains_any(error, _LIST_DRIFT_MARKERS):
        return "scalar_list_drift"
    if _contains_any(error, _FIELD_SHAPE_MARKERS):
        return "field_shape_error"
    return "field_shape_error"


def _normalize_required_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip()
    if normalized not in VALID_RETURN_STATUSES:
        allowed = ", ".join(sorted(VALID_RETURN_STATUSES))
        raise ValueError(f"required status must be one of: {allowed}")
    return normalized


def _classification(
    primary_class: ReturnRepairClass,
    *,
    valid: bool,
    accepted_for_success: bool,
    original_errors: list[str],
    original_warnings: list[str],
    recovery_route: ReturnRepairRecoveryRoute,
    status: str | None = None,
    required_status: str | None = None,
    fields: dict[str, object] | None = None,
    notes: list[str] | None = None,
) -> ReturnRepairClassification:
    return ReturnRepairClassification(
        passed=valid,
        valid=valid,
        accepted_for_success=accepted_for_success,
        safe_to_apply=valid and accepted_for_success,
        primary_class=primary_class,
        primary_classification=primary_class,
        primary_failure_class=primary_class,
        failure_classes=[] if primary_class == "valid" else [primary_class],
        errors=original_errors,
        warnings=original_warnings,
        original_errors=original_errors,
        original_warnings=original_warnings,
        recovery_route=recovery_route,
        repair_hint=return_repair_hint(primary_class),
        status=status,
        required_status=required_status,
        fields=fields or {},
        notes=notes or [],
    )


def _classify_validation_errors(content: str, errors: list[str]) -> ReturnRepairClass:
    for error in errors:
        repair_class = return_repair_class_from_validation_error(error, content=content)
        if repair_class != "field_shape_error":
            return repair_class
    return "field_shape_error"


def _classify_missing_block(content: str) -> ReturnRepairClass:
    for language, body in _iter_fenced_blocks(content):
        normalized_language = language.strip().lower()
        if normalized_language in {"yaml", "yml"} and _looks_like_unwrapped_return_yaml(body):
            return "top_level_shape_error"
        if normalized_language not in {"yaml", "yml"} and _contains_gpd_return_candidate(body):
            return "wrong_fence_language"

    if _contains_gpd_return_candidate(content) or _looks_like_unwrapped_return_yaml(content):
        return "unfenced_candidate"
    return "missing_block"


def _iter_fenced_blocks(content: str) -> list[tuple[str, str]]:
    return [(match.group("language"), match.group("body")) for match in _FENCED_BLOCK_RE.finditer(content)]


def _contains_gpd_return_candidate(content: str) -> bool:
    return bool(_RAW_GPD_RETURN_YAML_RE.search(content) or _RAW_GPD_RETURN_JSON_RE.search(content))


def _looks_like_unwrapped_return_yaml(content: str) -> bool:
    found_fields = {match.group(1) for match in _UNWRAPPED_RETURN_YAML_RE.finditer(content)}
    return "status" in found_fields and bool(found_fields.intersection({"files_written", "issues", "next_actions"}))


def _contains_any(content: str, markers: tuple[str, ...]) -> bool:
    return any(marker in content for marker in markers)


def _is_continuation_schema_error(error_text: str) -> bool:
    return "continuation_update" in error_text or "bounded_segment" in error_text or "handoff" in error_text


def _recovery_route(primary_class: ReturnRepairClass) -> ReturnRepairRecoveryRoute:
    if primary_class == "valid":
        return "accept"
    if primary_class in {"valid_non_completed", "required_status_mismatch"}:
        return "route_by_status"
    if primary_class in {
        "status_field_forbidden",
        "transport_payload_in_return",
        "applicator_owned_metadata",
        "continuation_schema_error",
    }:
        return "block_and_surface_errors"
    return "retry_child"


def _status_from_validation(fields: dict[str, object]) -> str | None:
    status = fields.get("status")
    return status if isinstance(status, str) else None
