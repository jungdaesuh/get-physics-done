"""Canonical typed ``gpd_return`` envelope parsing and validation.

This module is the shared source of truth for the machine-readable return
contract used by command/CLI validation.  It keeps the top-level required
fields explicit, validates nested YAML payloads recursively, and rejects
scalar/list mismatches before callers interpret the envelope.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)

from gpd.core.checkpoint_intent import GpdReturnCheckpointIntent
from gpd.core.continuation import ContinuationBoundedSegment, ContinuationHandoff
from gpd.core.return_fields import (
    allowed_return_extension_fields,
    known_return_field_names,
    return_field_source,
    return_field_status_allowed,
    status_restricted_return_fields,
)
from gpd.core.return_fields import (
    return_fields_allowed_for_status as registry_return_fields_allowed_for_status,
)

__all__ = [
    "GPD_RETURN_BLOCK_RE",
    "GpdReturnCheckpointIntent",
    "GpdReturnContinuationBoundedSegment",
    "GpdReturnContinuationHandoff",
    "GpdReturnContinuationUpdate",
    "GpdReturnEnvelope",
    "GpdReturnStatusContract",
    "GpdReturnValidationResult",
    "ALLOWED_RETURN_EXTENSION_FIELDS",
    "KNOWN_RETURN_FIELD_NAMES",
    "REQUIRED_RETURN_FIELDS",
    "RETURN_ENVELOPE_STATUS_CONTRACTS",
    "RETURN_STATUS_ORDER",
    "VALID_RETURN_STATUSES",
    "extract_gpd_return_block",
    "normalize_return_status",
    "return_field_allowed_for_status",
    "return_field_allowed_source",
    "return_fields_allowed_for_status",
    "validate_gpd_return_markdown",
]

VALID_RETURN_STATUSES: frozenset[str] = frozenset({"completed", "checkpoint", "blocked", "failed"})
"""Allowed values for ``gpd_return.status``."""

_RETURN_STATUS_ORDER_SEED = ("completed", "checkpoint", "blocked", "failed")
RETURN_STATUS_ORDER: tuple[str, ...] = tuple(
    status for status in _RETURN_STATUS_ORDER_SEED if status in VALID_RETURN_STATUSES
) + tuple(sorted(VALID_RETURN_STATUSES - set(_RETURN_STATUS_ORDER_SEED)))
"""Stable display/test order for statuses, derived from the canonical status set."""

ALLOWED_RETURN_EXTENSION_FIELDS: frozenset[str] = allowed_return_extension_fields()
"""Known workflow/agent-specific top-level extensions allowed in ``gpd_return``."""

GPD_RETURN_BLOCK_RE = re.compile(r"```ya?ml\s*\n(gpd_return:\s*\n[\s\S]*?)```")
"""Fence matcher for the canonical ``gpd_return`` YAML block."""


_RETURN_HANDOFF_TEXT_FIELDS = frozenset({"resume_file", "stopped_at", "last_result_id"})
_RETURN_BOUNDED_SEGMENT_TEXT_FIELDS = frozenset(
    {
        "resume_file",
        "phase",
        "plan",
        "segment_id",
        "segment_status",
        "checkpoint_reason",
        "waiting_reason",
        "blocked_reason",
        "skeptical_requestioning_summary",
        "weakest_unchecked_anchor",
        "disconfirming_observation",
        "transition_id",
        "last_result_id",
        "source_session_id",
    }
)
_RETURN_BOUNDED_SEGMENT_BOOL_FIELDS = frozenset(
    {
        "waiting_for_review",
        "first_result_gate_pending",
        "pre_fanout_review_pending",
        "pre_fanout_review_cleared",
        "skeptical_requestioning_required",
        "downstream_locked",
    }
)


def _reject_non_string_continuation_fields(
    value: Mapping[str, object],
    *,
    fields: frozenset[str],
    label: str,
) -> None:
    for field_name in sorted(fields.intersection(value)):
        field_value = value[field_name]
        if field_value is not None and not isinstance(field_value, str):
            raise ValueError(f"{label}.{field_name} must be a string or null")


def _reject_non_bool_continuation_fields(
    value: Mapping[str, object],
    *,
    fields: frozenset[str],
    label: str,
) -> None:
    for field_name in sorted(fields.intersection(value)):
        if type(value[field_name]) is not bool:
            raise ValueError(f"{label}.{field_name} must be a boolean when provided")


@dataclass(frozen=True)
class GpdReturnStatusContract:
    """Status-specific top-level contract shape."""

    structured_fields: tuple[str, ...]


class GpdReturnContinuationHandoff(ContinuationHandoff):
    """Durable handoff payload visible in ``gpd_return``."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def _reject_applicator_owned_metadata(cls, value: object) -> object:
        if isinstance(value, Mapping):
            forbidden = sorted({"recorded_at", "recorded_by"}.intersection(value))
            if forbidden:
                fields = ", ".join(forbidden)
                raise ValueError(f"{fields} are applicator-owned handoff fields; omit them from child returns")
            _reject_non_string_continuation_fields(
                value,
                fields=_RETURN_HANDOFF_TEXT_FIELDS,
                label="continuation_update.handoff",
            )
        return value


class GpdReturnContinuationBoundedSegment(ContinuationBoundedSegment):
    """Durable bounded-segment payload visible in ``gpd_return``."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def _reject_applicator_owned_metadata(cls, value: object) -> object:
        if isinstance(value, Mapping):
            forbidden = sorted({"recorded_by", "updated_at"}.intersection(value))
            if forbidden:
                fields = ", ".join(forbidden)
                raise ValueError(f"{fields} are applicator-owned bounded_segment fields; omit them from child returns")
            _reject_non_string_continuation_fields(
                value,
                fields=_RETURN_BOUNDED_SEGMENT_TEXT_FIELDS,
                label="continuation_update.bounded_segment",
            )
            _reject_non_bool_continuation_fields(
                value,
                fields=_RETURN_BOUNDED_SEGMENT_BOOL_FIELDS,
                label="continuation_update.bounded_segment",
            )
        return value


class GpdReturnContinuationUpdate(BaseModel):
    """Typed durable continuation update nested inside ``gpd_return``."""

    model_config = ConfigDict(extra="forbid", strict=True)

    handoff: GpdReturnContinuationHandoff | None = None
    bounded_segment: GpdReturnContinuationBoundedSegment | None = None


RETURN_ENVELOPE_STATUS_CONTRACTS: dict[str, GpdReturnStatusContract] = {
    "completed": GpdReturnStatusContract(
        structured_fields=(
            "state_updates",
            "contract_updates",
            "decisions",
            "approved_plans",
            "blocked_plans",
            "continuation_update",
            "conventions_used",
            "checkpoint_hashes",
        ),
    ),
    "checkpoint": GpdReturnStatusContract(
        structured_fields=(
            "state_updates",
            "contract_updates",
            "decisions",
            "approved_plans",
            "blocked_plans",
            "blockers",
            "continuation_update",
            "checkpoint_intent",
            "checkpoint_hashes",
        ),
    ),
    "blocked": GpdReturnStatusContract(
        structured_fields=("approved_plans", "blocked_plans", "blockers", "continuation_update"),
    ),
    "failed": GpdReturnStatusContract(
        structured_fields=("approved_plans", "blocked_plans", "blockers", "continuation_update"),
    ),
}
"""Explicit status-dependent contract structure for supported envelopes."""

_STATUS_RESTRICTED_FIELDS: frozenset[str] = status_restricted_return_fields(RETURN_ENVELOPE_STATUS_CONTRACTS)


def normalize_return_status(value: object, *, field_name: str = "status") -> str:
    """Normalize a callsite status selector against the canonical vocabulary."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    if normalized not in VALID_RETURN_STATUSES:
        statuses = ", ".join(RETURN_STATUS_ORDER)
        raise ValueError(f"unknown gpd_return status '{value}'. Must be one of: {statuses}")
    return normalized


class GpdReturnEnvelope(BaseModel):
    """Typed machine-readable ``gpd_return`` payload."""

    model_config = ConfigDict(extra="allow", strict=True)

    status: StrictStr
    files_written: list[StrictStr]
    issues: list[StrictStr]
    next_actions: list[StrictStr]
    tasks_completed: int | None = None
    tasks_total: int | None = None
    duration_seconds: int | float | None = None
    phase: StrictStr | None = None
    plan: StrictStr | None = None
    design_file: StrictStr | None = None
    field_assessment: StrictStr | None = None
    state_updates: dict[str, object] | None = None
    contract_updates: dict[str, object] | None = None
    decisions: list[object] | None = None
    approved_plans: list[StrictStr] | None = None
    blocked_plans: list[StrictStr] | None = None
    blockers: list[object] | None = None
    continuation_update: GpdReturnContinuationUpdate | None = None
    checkpoint_intent: GpdReturnCheckpointIntent | None = None
    conventions_used: dict[str, object] | None = None
    checkpoint_hashes: list[dict[str, object]] | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("status must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("status must be a non-empty string")
        if normalized.lower() in VALID_RETURN_STATUSES and normalized not in VALID_RETURN_STATUSES:
            raise ValueError(
                f"status must use canonical lowercase spelling: {', '.join(sorted(VALID_RETURN_STATUSES))}"
            )
        if normalized not in VALID_RETURN_STATUSES:
            raise ValueError(f"Invalid status '{value}'. Must be one of: {', '.join(sorted(VALID_RETURN_STATUSES))}")
        return normalized

    @field_validator("files_written", "issues", "next_actions", mode="before")
    @classmethod
    def _validate_string_list(cls, value: object, info) -> list[str]:
        return _validate_string_list(value, field_name=info.field_name)

    @field_validator("decisions", "blockers", mode="before")
    @classmethod
    def _validate_yaml_sequence(cls, value: object, info) -> list[object] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError(f"{info.field_name} must be a list")
        for index, item in enumerate(value):
            _validate_yaml_native(item, f"gpd_return.{info.field_name}[{index}]")
        return value

    @field_validator("approved_plans", "blocked_plans", mode="before")
    @classmethod
    def _validate_plan_id_list(cls, value: object, info) -> list[str] | None:
        return _validate_string_list(value, field_name=info.field_name)

    @field_validator("tasks_completed", "tasks_total", mode="before")
    @classmethod
    def _validate_task_count(cls, value: object, info) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{info.field_name} not a number: {value!r}")
        return value

    @field_validator("state_updates", "contract_updates", "conventions_used", mode="before")
    @classmethod
    def _validate_yaml_mapping(cls, value: object, info) -> dict[str, object] | None:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise ValueError(f"{info.field_name} must be a mapping")
        _validate_yaml_mapping(value, f"gpd_return.{info.field_name}")
        return dict(value)

    @field_validator("checkpoint_hashes", mode="before")
    @classmethod
    def _validate_checkpoint_hashes(cls, value: object) -> list[dict[str, object]] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("checkpoint_hashes must be a list")
        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                raise ValueError(f"gpd_return.checkpoint_hashes[{index}] must be a mapping")
            _validate_yaml_mapping(item, f"gpd_return.checkpoint_hashes[{index}]")
        return [dict(item) for item in value]

    @model_validator(mode="after")
    def _validate_top_level_contract(self) -> GpdReturnEnvelope:
        extras = self.model_extra or {}
        unknown_fields = sorted(set(extras) - ALLOWED_RETURN_EXTENSION_FIELDS)
        if unknown_fields:
            fields = ", ".join(unknown_fields)
            raise ValueError(f"Unknown gpd_return top-level field(s): {fields}")

        for field_name, value in extras.items():
            _validate_yaml_native(value, f"gpd_return.{field_name}")

        provided_fields = set(self.model_fields_set) | set(extras)
        disallowed_fields = sorted(
            field_name
            for field_name in provided_fields.intersection(_STATUS_RESTRICTED_FIELDS)
            if not return_field_allowed_for_status(field_name, self.status)
        )
        if disallowed_fields:
            fields = ", ".join(disallowed_fields)
            raise ValueError(f"status '{self.status}' does not allow gpd_return field(s): {fields}")
        return self


REQUIRED_RETURN_FIELDS: tuple[str, ...] = tuple(
    field_name for field_name, field_info in GpdReturnEnvelope.model_fields.items() if field_info.is_required()
)
"""Fields that must be present in every ``gpd_return`` envelope."""

KNOWN_RETURN_FIELD_NAMES: frozenset[str] = known_return_field_names(GpdReturnEnvelope.model_fields)
"""All top-level fields known to the canonical return contract."""


def return_field_allowed_source(field_name: str) -> Literal["base", "extension", "unknown"]:
    """Classify where a top-level ``gpd_return`` field is allowed from."""

    return return_field_source(field_name, base_fields=GpdReturnEnvelope.model_fields)


def return_field_allowed_for_status(field_name: str, status: object) -> bool:
    """Return whether a known top-level field is legal for a status."""

    if field_name not in KNOWN_RETURN_FIELD_NAMES:
        return False
    normalized_status = normalize_return_status(status)
    return return_field_status_allowed(
        field_name,
        normalized_status,
        base_fields=GpdReturnEnvelope.model_fields,
        status_contracts=RETURN_ENVELOPE_STATUS_CONTRACTS,
    )


def return_fields_allowed_for_status(status: object) -> tuple[str, ...]:
    """List known top-level fields legal for a status in stable render order."""

    normalized_status = normalize_return_status(status)
    return registry_return_fields_allowed_for_status(
        normalized_status,
        base_fields=GpdReturnEnvelope.model_fields,
        status_contracts=RETURN_ENVELOPE_STATUS_CONTRACTS,
    )


class GpdReturnValidationResult(BaseModel):
    """Validation result for a ``gpd_return`` envelope embedded in markdown."""

    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fields: dict[str, object] = Field(default_factory=dict)
    warning_count: int = 0
    envelope: GpdReturnEnvelope | None = None


def extract_gpd_return_block(content: str) -> str | None:
    """Extract the canonical fenced YAML block containing ``gpd_return``."""
    match = GPD_RETURN_BLOCK_RE.search(content)
    return match.group(1) if match else None


def validate_gpd_return_markdown(content: str) -> GpdReturnValidationResult:
    """Parse and validate a markdown file containing a fenced ``gpd_return`` block."""
    yaml_blocks = GPD_RETURN_BLOCK_RE.findall(content)
    if not yaml_blocks:
        return GpdReturnValidationResult(passed=False, errors=["No gpd_return YAML block found"])
    if len(yaml_blocks) > 1:
        return GpdReturnValidationResult(
            passed=False,
            errors=[f"Multiple gpd_return YAML blocks found: expected exactly one, got {len(yaml_blocks)}"],
        )

    try:
        parsed = yaml.safe_load(yaml_blocks[0])
    except yaml.YAMLError as exc:
        return GpdReturnValidationResult(passed=False, errors=[f"gpd_return YAML parse error: {exc}"])

    if not isinstance(parsed, Mapping):
        return GpdReturnValidationResult(passed=False, errors=["gpd_return YAML parse error: expected a mapping"])

    top_level_keys = set(parsed.keys())
    if top_level_keys != {"gpd_return"}:
        unexpected = ", ".join(sorted(top_level_keys - {"gpd_return"}))
        missing = "gpd_return" not in parsed
        if missing and unexpected:
            message = f"gpd_return YAML parse error: missing top-level gpd_return key and unexpected top-level key(s): {unexpected}"
        elif missing:
            message = "gpd_return YAML parse error: missing top-level gpd_return key"
        else:
            message = f"gpd_return YAML parse error: unexpected top-level key(s): {unexpected}"
        return GpdReturnValidationResult(passed=False, errors=[message])

    raw_envelope = parsed.get("gpd_return")
    if not isinstance(raw_envelope, Mapping):
        return GpdReturnValidationResult(
            passed=False,
            errors=["gpd_return YAML parse error: gpd_return must be a mapping"],
        )

    try:
        envelope = GpdReturnEnvelope.model_validate(raw_envelope)
    except PydanticValidationError as exc:
        return GpdReturnValidationResult(
            passed=False,
            errors=_format_pydantic_validation_error(exc),
        )

    warnings = _collect_gpd_return_warnings(envelope)
    return GpdReturnValidationResult(
        passed=True,
        warnings=warnings,
        fields=envelope.model_dump(exclude_none=True),
        warning_count=len(warnings),
        envelope=envelope,
    )


def _format_pydantic_validation_error(exc: PydanticValidationError) -> list[str]:
    errors: list[str] = []
    for item in exc.errors():
        location = tuple(str(part) for part in item.get("loc", ()))
        field_name = location[-1] if location else "gpd_return"
        message = _normalize_validation_message(item.get("msg", "validation error"))
        error_type = item.get("type", "")

        if error_type == "missing" or message == "Field required":
            errors.append(f"Missing required field: {field_name}")
            continue

        if location:
            if len(location) == 1 and (message.startswith(f"{field_name} ") or message.startswith(f"{field_name}:")):
                errors.append(message)
                continue
            errors.append(f"{'.'.join(location)}: {message}")
        else:
            errors.append(message)
    return errors


def _normalize_validation_message(message: str) -> str:
    if message.startswith("Value error, "):
        return message[len("Value error, ") :]
    return message


def _collect_gpd_return_warnings(envelope: GpdReturnEnvelope) -> list[str]:
    warnings: list[str] = []

    if envelope.status == "completed" and envelope.tasks_completed is not None and envelope.tasks_total is not None:
        if envelope.tasks_completed < envelope.tasks_total:
            warnings.append(
                f"Status is 'completed' but tasks_completed ({envelope.tasks_completed}) < tasks_total ({envelope.tasks_total})"
            )

    if "duration_seconds" not in envelope.model_fields_set or envelope.duration_seconds is None:
        warnings.append("Recommended field missing: duration_seconds")

    return warnings


def _validate_string_list(value: object, *, field_name: str) -> list[str]:
    if value is None:
        raise ValueError(f"{field_name} must be a list")
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")

    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"gpd_return.{field_name}[{index}] must be a string")
        stripped = item.strip()
        if not stripped:
            raise ValueError(f"gpd_return.{field_name}[{index}] must be a non-empty string")
        normalized.append(stripped)
    return normalized


def _validate_yaml_native(value: object, path: str) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_yaml_native(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        _validate_yaml_mapping(value, path)
        return
    raise ValueError(f"{path} must be a YAML scalar, list, or mapping, not {type(value).__name__}")


def _validate_yaml_mapping(value: Mapping[str, object], path: str) -> None:
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{path} must use string keys")
        _validate_yaml_native(item, f"{path}.{key}")
