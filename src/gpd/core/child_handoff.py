"""Read-only validation for child return/artifact handoff tuples."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gpd.core.handoff_artifacts import (
    HandoffArtifactValidationResult,
    HandoffFailure,
    HandoffFailureClass,
    validate_handoff_artifacts_markdown,
)
from gpd.core.return_contract import RETURN_STATUS_ORDER, normalize_return_status, validate_gpd_return_markdown
from gpd.core.return_skeleton import list_gpd_return_profiles, normalize_return_profile_id

SafeChildHandoffValidatorId = Literal[
    "readable",
    "plan-contract",
    "plan-preflight",
    "proof-redteam",
    "summary-contract",
    "verification-contract",
    "verification-report",
    "paper-section-readable",
]

AcceptanceState = Literal[
    "failed",
    "status_routed",
    "read_only_passed_needs_applicator",
    "accepted",
]

SAFE_CHILD_HANDOFF_VALIDATORS: frozenset[str] = frozenset(
    (
        "readable",
        "plan-contract",
        "plan-preflight",
        "proof-redteam",
        "summary-contract",
        "verification-contract",
        "verification-report",
        "paper-section-readable",
    )
)
"""Validator ids this wrapper may dispatch without evaluating shell text."""

_YAML_FENCE_RE = re.compile(r"```ya?ml\s*\n([\s\S]*?)```")


class ChildGateArtifact(BaseModel):
    """One callsite-owned child artifact expectation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    kind: Literal["path", "glob"] = "path"
    required: bool = True
    must_be_named_in_files_written: bool = True

    @field_validator("path", mode="before")
    @classmethod
    def _normalize_path(cls, value: object) -> str:
        return _normalize_text(value, field_name="path")

    def to_payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "required": self.required,
            "must_be_named_in_files_written": self.must_be_named_in_files_written,
        }


class ChildGateFreshness(BaseModel):
    """Tuple field for freshness checks owned by the callsite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    marker: str | None = None
    require_mtime_at_or_after_marker: bool = False
    preexisting_artifacts: Literal["recovery_evidence_only", "allowed", "blocked", "not_applicable"] = (
        "recovery_evidence_only"
    )

    @field_validator("marker", mode="before")
    @classmethod
    def _normalize_marker(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="marker")

    @model_validator(mode="after")
    def _require_marker_when_mtime_gate_is_enabled(self) -> Self:
        if self.require_mtime_at_or_after_marker and self.marker is None:
            raise ValueError("freshness marker is required when mtime freshness is enabled")
        return self

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "require_mtime_at_or_after_marker": self.require_mtime_at_or_after_marker,
            "preexisting_artifacts": self.preexisting_artifacts,
        }
        if self.marker is not None:
            payload = {"marker": self.marker, **payload}
        return payload


class ChildGateApplicator(BaseModel):
    """Tuple field for callsite-owned durable effects."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command: str = "none"
    require_passed_true: bool = False

    @model_validator(mode="before")
    @classmethod
    def _normalize_compact_applicator(cls, value: object) -> object:
        if isinstance(value, str):
            return {"command": value}
        return value

    @field_validator("command", mode="before")
    @classmethod
    def _normalize_command(cls, value: object) -> str:
        return _normalize_text(value, field_name="command")

    @model_validator(mode="after")
    def _reject_passed_gate_without_applicator(self) -> Self:
        if self.command == "none" and self.require_passed_true:
            raise ValueError("applicator require_passed_true requires a command")
        return self

    def to_payload(self) -> dict[str, object]:
        return {
            "command": self.command,
            "require_passed_true": self.require_passed_true,
        }


class ChildGateTuple(BaseModel):
    """Callsite-owned child gate tuple consumed by the read-only handoff validator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    role: str
    return_profile: str
    required_status: str = "completed"
    expected_artifacts: tuple[ChildGateArtifact, ...] = ()
    allowed_roots: tuple[str, ...] = ()
    freshness: ChildGateFreshness | None = None
    validators: tuple[str, ...] = ()
    applicator: ChildGateApplicator = Field(default_factory=ChildGateApplicator)
    failure_route: dict[HandoffFailureClass, str] = Field(default_factory=lambda: dict(_DEFAULT_FAILURE_ROUTE))
    status_route: dict[str, str] = Field(default_factory=dict)
    write_allowlist: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _infer_return_profile(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        payload = dict(value)
        if "freshness" not in payload and "freshness_marker" in payload:
            payload["freshness"] = {
                "marker": _normalize_freshness_marker(payload.pop("freshness_marker")),
                "require_mtime_at_or_after_marker": True,
                "preexisting_artifacts": "recovery_evidence_only",
            }
        if "write_allowlist" not in payload and "allowed_write_paths" in payload:
            payload["write_allowlist"] = payload.pop("allowed_write_paths")
        raw_failure_route = payload.get("failure_route")
        if isinstance(raw_failure_route, Mapping):
            failure_route: dict[str, object] = {}
            status_route = (
                dict(payload.get("status_route", {})) if isinstance(payload.get("status_route"), Mapping) else {}
            )
            for key, route in raw_failure_route.items():
                key_text = str(key)
                if key_text in {failure_class.value for failure_class in HandoffFailureClass}:
                    failure_route[key_text] = route
                elif key_text.strip().lower() in RETURN_STATUS_ORDER:
                    status_route[key_text] = route
                else:
                    failure_route[key_text] = route
            payload["failure_route"] = failure_route
            if status_route:
                payload["status_route"] = status_route
        raw_profile = payload.get("return_profile")
        if isinstance(raw_profile, str) and raw_profile.strip():
            payload["return_profile"] = _profile_id_for_role_or_profile(raw_profile)
            return payload
        raw_role = payload.get("role")
        if not isinstance(raw_role, str) or not raw_role.strip():
            return payload
        payload["return_profile"] = _profile_id_for_role_or_profile(raw_role)
        return payload

    @field_validator("id", "role", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: object, info) -> str:
        return _normalize_text(value, field_name=info.field_name)

    @field_validator("return_profile", mode="before")
    @classmethod
    def _normalize_return_profile(cls, value: object) -> str:
        return _profile_id_for_role_or_profile(_normalize_text(value, field_name="return_profile"))

    @field_validator("required_status", mode="before")
    @classmethod
    def _normalize_required_status(cls, value: object) -> str:
        return normalize_return_status(value, field_name="required_status")

    @field_validator("allowed_roots", "validators", mode="before")
    @classmethod
    def _normalize_text_tuple(cls, value: object, info) -> tuple[str, ...]:
        return _normalize_text_sequence(value, field_name=info.field_name)

    @field_validator("expected_artifacts", mode="before")
    @classmethod
    def _normalize_expected_artifacts(cls, value: object) -> object:
        if value is None:
            return ()
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
            return value
        return [{"path": item} if isinstance(item, str) else item for item in value]

    @field_validator("write_allowlist", mode="before")
    @classmethod
    def _normalize_write_allowlist(cls, value: object) -> tuple[str, ...]:
        return _normalize_text_sequence(value, field_name="write_allowlist")

    @field_validator("failure_route", mode="before")
    @classmethod
    def _normalize_failure_route(cls, value: object) -> dict[HandoffFailureClass, str]:
        if value is None:
            return dict(_DEFAULT_FAILURE_ROUTE)
        if isinstance(value, str):
            route = _normalize_text(value, field_name="failure_route")
            return dict.fromkeys(HandoffFailureClass, route)
        if not isinstance(value, Mapping):
            raise ValueError("failure_route must be a mapping")
        normalized: dict[HandoffFailureClass, str] = {}
        for raw_failure_class, raw_action in value.items():
            try:
                failure_class = HandoffFailureClass(str(raw_failure_class))
            except ValueError as exc:
                known = ", ".join(failure.value for failure in HandoffFailureClass)
                raise ValueError(
                    f"unknown handoff failure class '{raw_failure_class}'. Must be one of: {known}"
                ) from exc
            normalized[failure_class] = _normalize_text(raw_action, field_name=f"failure_route.{failure_class.value}")
        return normalized or dict(_DEFAULT_FAILURE_ROUTE)

    @field_validator("status_route", mode="before")
    @classmethod
    def _normalize_status_route(cls, value: object) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("status_route must be a mapping")
        normalized: dict[str, str] = {}
        for raw_key, raw_value in value.items():
            status = normalize_return_status(raw_key, field_name="status_route key")
            normalized[status] = _normalize_text(raw_value, field_name=f"status_route.{raw_key}")
        return normalized

    @model_validator(mode="after")
    def _ensure_return_profile_supports_status(self) -> Self:
        profiles = list_gpd_return_profiles(role=self.return_profile, status=self.required_status)
        if not profiles["profiles"]:
            raise ValueError(
                f"return profile '{self.return_profile}' has no status metadata for '{self.required_status}'"
            )
        return self

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "role": self.role,
            "return_profile": self.return_profile,
            "required_status": self.required_status,
        }
        if self.expected_artifacts:
            payload["expected_artifacts"] = [artifact.to_payload() for artifact in self.expected_artifacts]
        if self.allowed_roots:
            payload["allowed_roots"] = list(self.allowed_roots)
        if self.freshness is not None:
            payload["freshness"] = self.freshness.to_payload()
        if self.validators:
            payload["validators"] = list(self.validators)
        if self.write_allowlist:
            payload["write_allowlist"] = list(self.write_allowlist)
        payload["applicator"] = self.applicator.to_payload()
        payload["failure_route"] = {
            failure_class.value: self.failure_route[failure_class]
            for failure_class in HandoffFailureClass
            if failure_class in self.failure_route
        }
        if self.status_route:
            payload["status_route"] = dict(self.status_route)
        return payload


class AggregateChildGateTuple(BaseModel):
    """Callsite-owned aggregate gate that reconciles multiple child gate results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    required_child_gates: tuple[str, ...]
    expected_artifacts: tuple[str, ...]
    validators: tuple[str, ...] = ()
    failure_route: str

    @field_validator("id", "failure_route", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: object, info) -> str:
        return _normalize_text(value, field_name=info.field_name)

    @field_validator("required_child_gates", "expected_artifacts", mode="before")
    @classmethod
    def _normalize_required_text_tuple(cls, value: object, info) -> tuple[str, ...]:
        return _normalize_non_empty_text_sequence(value, field_name=info.field_name)

    @field_validator("validators", mode="before")
    @classmethod
    def _normalize_validators(cls, value: object) -> tuple[str, ...]:
        return _normalize_text_sequence(value, field_name="validators")

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "required_child_gates": list(self.required_child_gates),
            "expected_artifacts": list(self.expected_artifacts),
            "validators": list(self.validators),
            "failure_route": self.failure_route,
        }


_DEFAULT_FAILURE_ROUTE: dict[HandoffFailureClass, str] = {
    HandoffFailureClass.RETURN_MISSING: "retry_once",
    HandoffFailureClass.RETURN_MALFORMED_REPAIRABLE: "repair_prompt_once",
    HandoffFailureClass.RETURN_MALFORMED_BLOCKING: "fail_closed",
    HandoffFailureClass.RETURN_STATUS_ROUTE: "route_by_status",
    HandoffFailureClass.ARTIFACT_MISSING: "retry_once_or_main_context_fallback",
    HandoffFailureClass.ARTIFACT_STALE: "retry_once",
    HandoffFailureClass.ARTIFACT_PATH_REPAIRABLE: "repair_path_once",
    HandoffFailureClass.ARTIFACT_ROOT_BLOCKED: "fail_closed",
    HandoffFailureClass.VALIDATOR_FAILED: "revision_loop",
    HandoffFailureClass.APPLICATOR_FAILED: "fail_closed_with_mutation_report",
}


class ChildHandoffValidatorResult(BaseModel):
    """Result for one whitelisted child-handoff validator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    validator_id: str
    passed: bool
    checked_files: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChildHandoffValidationRequest(BaseModel):
    """Typed input for read-only child handoff validation."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    project_root: Path
    return_markdown: str
    gate: ChildGateTuple
    fresh_after: datetime | None = None


class ChildHandoffValidationResult(BaseModel):
    """Tuple-aware child handoff validation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    mutated: bool = False
    mutates: bool = False
    read_only_passed: bool = False
    requires_applicator_pass: bool = False
    acceptance_complete: bool = False
    acceptance_state: AcceptanceState
    applicator_required_unrun: bool = False
    gate_id: str
    return_profile: str
    required_status: str
    status: str | None = None
    primary_failure_class: HandoffFailureClass | None = None
    failure_classes: list[HandoffFailureClass] = Field(default_factory=list)
    failures: list[HandoffFailure] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_files: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    expected_globs: list[str] = Field(default_factory=list)
    allowed_roots: list[str] = Field(default_factory=list)
    validator_results: list[ChildHandoffValidatorResult] = Field(default_factory=list)
    status_route: dict[str, str] = Field(default_factory=dict)
    failure_route: dict[str, str] = Field(default_factory=dict)
    status_route_used: bool = False
    status_route_reason: str | None = None
    selected_route: str
    next_action_class: str
    applicator_command: str = "none"
    applicator_ran: bool = False
    artifact_result: HandoffArtifactValidationResult


__all__ = [
    "AcceptanceState",
    "AggregateChildGateTuple",
    "SAFE_CHILD_HANDOFF_VALIDATORS",
    "ChildGateApplicator",
    "ChildGateArtifact",
    "ChildGateFreshness",
    "ChildGateTuple",
    "ChildHandoffValidationRequest",
    "ChildHandoffValidationResult",
    "ChildHandoffValidatorResult",
    "aggregate_child_gate_tuple_from_payload",
    "child_gate_tuple_from_payload",
    "parse_aggregate_child_gate_markdown",
    "parse_child_gate_markdown",
    "render_child_gate_inline_summary",
    "render_child_gate_markdown",
    "validate_child_handoff",
]


def child_gate_tuple_from_payload(payload: Mapping[str, object]) -> ChildGateTuple:
    """Build a tuple from either a raw tuple payload or ``{"child_gate": ...}``."""

    candidate = payload.get("child_gate") if "child_gate" in payload else payload
    if not isinstance(candidate, Mapping):
        raise ValueError("child_gate payload must be a mapping")
    if "profile" in candidate:
        from gpd.core.child_gate_profiles import expand_child_gate_profile_payload

        candidate = expand_child_gate_profile_payload(candidate)
    return ChildGateTuple.model_validate(candidate)


def aggregate_child_gate_tuple_from_payload(payload: Mapping[str, object]) -> AggregateChildGateTuple:
    """Build an aggregate tuple from raw fields or ``{"aggregate_child_gate": ...}``."""

    candidate = payload.get("aggregate_child_gate") if "aggregate_child_gate" in payload else payload
    if not isinstance(candidate, Mapping):
        raise ValueError("aggregate_child_gate payload must be a mapping")
    return AggregateChildGateTuple.model_validate(candidate)


def parse_child_gate_markdown(content: str) -> ChildGateTuple:
    """Parse a raw or fenced YAML ``child_gate`` tuple."""

    for yaml_text in _candidate_yaml_payloads(content):
        try:
            payload = yaml.safe_load(yaml_text)
        except yaml.YAMLError:
            continue
        if not isinstance(payload, Mapping):
            continue
        if "child_gate" in payload or {"id", "role"} <= set(payload) or {"id", "profile"} <= set(payload):
            return child_gate_tuple_from_payload(payload)
    raise ValueError("No child_gate YAML block found")


def parse_aggregate_child_gate_markdown(content: str) -> AggregateChildGateTuple:
    """Parse a raw or fenced YAML ``aggregate_child_gate`` tuple."""

    required_raw_fields = {"id", "required_child_gates", "expected_artifacts"}
    for yaml_text in _candidate_yaml_payloads(content):
        try:
            payload = yaml.safe_load(yaml_text)
        except yaml.YAMLError:
            continue
        if not isinstance(payload, Mapping):
            continue
        if "aggregate_child_gate" in payload or required_raw_fields <= set(payload):
            return aggregate_child_gate_tuple_from_payload(payload)
    raise ValueError("No aggregate_child_gate YAML block found")


def render_child_gate_markdown(gate: ChildGateTuple | Mapping[str, object] | str) -> str:
    """Render a deterministic fenced YAML ``child_gate`` tuple."""

    gate_tuple = _coerce_gate(gate)
    rendered = yaml.safe_dump(
        {"child_gate": gate_tuple.to_payload()},
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=False,
        width=999999,
    ).rstrip()
    return f"```yaml\n{rendered}\n```\n"


def render_child_gate_inline_summary(gate: ChildGateTuple | Mapping[str, object] | str) -> str:
    """Render a compact, deterministic summary of the callsite-owned gate fields."""

    gate_tuple = _coerce_gate(gate)
    return "; ".join(
        (
            f"child_gate={gate_tuple.id}",
            f"role={gate_tuple.role}",
            f"required_status={gate_tuple.required_status}",
            f"artifacts={_artifact_summary(gate_tuple)}",
            f"allowed_roots={_sequence_summary(gate_tuple.allowed_roots)}",
            f"freshness={_freshness_summary(gate_tuple)}",
            f"validators={_sequence_summary(gate_tuple.validators)}",
            f"applicator={_applicator_summary(gate_tuple.applicator)}",
            f"write_allowlist={_sequence_summary(gate_tuple.write_allowlist)}",
            f"status_route={_route_summary(gate_tuple.status_route.items())}",
            f"failure_route={_route_summary((failure.value, route) for failure, route in gate_tuple.failure_route.items())}",
        )
    )


def validate_child_handoff(
    project_root: Path,
    return_markdown: str,
    gate: ChildGateTuple | Mapping[str, object] | str,
    *,
    fresh_after: datetime | None = None,
) -> ChildHandoffValidationResult:
    """Validate one child return against a callsite-owned child gate tuple.

    This helper is read-only. It validates artifacts and dispatches only named
    safe validators; it never evaluates validator strings as shell commands and
    never runs applicators.
    """

    gate_tuple = _coerce_gate(gate)
    request = ChildHandoffValidationRequest(
        project_root=project_root,
        return_markdown=return_markdown,
        gate=gate_tuple,
        fresh_after=fresh_after,
    )

    status_route_result = _valid_non_required_status_route_result(request)
    if status_route_result is not None:
        return status_route_result

    artifact_result = validate_handoff_artifacts_markdown(
        request.project_root,
        request.return_markdown,
        expected_artifacts=_expected_artifact_paths(gate_tuple),
        expected_globs=_expected_artifact_globs(gate_tuple),
        allowed_roots=list(gate_tuple.allowed_roots),
        require_files_written=any(artifact.required for artifact in gate_tuple.expected_artifacts),
        require_status=gate_tuple.required_status,
        fresh_after=request.fresh_after,
    )

    freshness_failures = _freshness_failures(gate_tuple, request.fresh_after)
    write_allowlist_failures = _write_allowlist_failures(
        request.project_root,
        gate_tuple,
        artifact_result.files_written,
    )
    authority_failures = [*freshness_failures, *write_allowlist_failures]

    validator_results: list[ChildHandoffValidatorResult] = []
    validator_failures: list[HandoffFailure] = []
    validator_errors: list[str] = []
    validator_warnings: list[str] = []
    if artifact_result.passed and not authority_failures:
        for raw_validator in gate_tuple.validators:
            normalized_validator = _safe_validator_id(raw_validator)
            if normalized_validator is None:
                continue
            if normalized_validator not in SAFE_CHILD_HANDOFF_VALIDATORS:
                message = f"unsupported child-handoff validator {raw_validator!r}; use a named safe validator id"
                validator_failures.append(
                    _handoff_failure(
                        HandoffFailureClass.VALIDATOR_FAILED,
                        "unsupported_validator",
                        message,
                        command=raw_validator,
                    )
                )
                validator_errors.append(message)
                validator_results.append(
                    ChildHandoffValidatorResult(
                        validator_id=raw_validator,
                        passed=False,
                        errors=[message],
                    )
                )
                continue

            validator_result = _run_safe_validator(
                request.project_root,
                normalized_validator,
                artifact_result.checked_files,
            )
            validator_results.append(validator_result)
            if not validator_result.passed:
                validator_errors.extend(validator_result.errors)
                validator_warnings.extend(validator_result.warnings)
                validator_failures.append(
                    _handoff_failure(
                        HandoffFailureClass.VALIDATOR_FAILED,
                        f"{normalized_validator}_failed",
                        "; ".join(validator_result.errors) or f"{normalized_validator} failed",
                        command=normalized_validator,
                    )
                )

    requires_applicator_pass = _requires_applicator_pass(gate_tuple)
    read_only_passed = artifact_result.passed and not authority_failures and not validator_failures
    applicator_required_unrun = read_only_passed and requires_applicator_pass
    applicator_failures: list[HandoffFailure] = []
    applicator_errors: list[str] = []
    if applicator_required_unrun:
        message = (
            "required child-gate applicator was not run by read-only child-handoff validation: "
            f"{gate_tuple.applicator.command}"
        )
        applicator_failures.append(
            _handoff_failure(
                HandoffFailureClass.APPLICATOR_FAILED,
                "applicator_required_unrun",
                message,
                command=gate_tuple.applicator.command,
            )
        )
        applicator_errors.append(message)
    failures = [*artifact_result.failures, *authority_failures, *validator_failures, *applicator_failures]
    failure_classes = _failure_classes(failures)
    passed = read_only_passed and not applicator_required_unrun
    acceptance_complete = read_only_passed and not applicator_required_unrun
    acceptance_state = _acceptance_state(
        status_routed=False,
        read_only_passed=read_only_passed,
        applicator_required_unrun=applicator_required_unrun,
        passed=passed,
    )
    warnings = [*artifact_result.warnings, *validator_warnings]
    if gate_tuple.applicator.command != "none":
        warnings.append(
            f"child-handoff validation is read-only; applicator {gate_tuple.applicator.command!r} was not run"
        )

    selected_route = _selected_route(gate_tuple, passed=passed, status=artifact_result.status, failures=failures)
    return ChildHandoffValidationResult(
        passed=passed,
        read_only_passed=read_only_passed,
        requires_applicator_pass=requires_applicator_pass,
        acceptance_complete=acceptance_complete,
        acceptance_state=acceptance_state,
        applicator_required_unrun=applicator_required_unrun,
        gate_id=gate_tuple.id,
        return_profile=gate_tuple.return_profile,
        required_status=gate_tuple.required_status,
        status=artifact_result.status,
        primary_failure_class=failure_classes[0] if failure_classes else None,
        failure_classes=failure_classes,
        failures=failures,
        errors=[
            *artifact_result.errors,
            *[failure.message for failure in authority_failures],
            *validator_errors,
            *applicator_errors,
        ],
        warnings=warnings,
        checked_files=list(artifact_result.checked_files),
        expected_artifacts=list(artifact_result.expected_artifacts),
        expected_globs=list(artifact_result.expected_globs),
        allowed_roots=list(artifact_result.allowed_roots),
        validator_results=validator_results,
        status_route=dict(gate_tuple.status_route),
        failure_route={failure_class.value: route for failure_class, route in gate_tuple.failure_route.items()},
        status_route_used=passed and artifact_result.status in gate_tuple.status_route,
        selected_route=selected_route,
        next_action_class=selected_route,
        applicator_command=gate_tuple.applicator.command,
        applicator_ran=False,
        artifact_result=artifact_result,
    )


def _coerce_gate(gate: ChildGateTuple | Mapping[str, object] | str) -> ChildGateTuple:
    if isinstance(gate, ChildGateTuple):
        return gate
    if isinstance(gate, str):
        return parse_child_gate_markdown(gate)
    return child_gate_tuple_from_payload(gate)


def _artifact_summary(gate: ChildGateTuple) -> str:
    if not gate.expected_artifacts:
        return "none"
    return ", ".join(
        (
            f"{artifact.path}"
            f"[kind={artifact.kind}, required={_bool_text(artifact.required)}, "
            f"files_written={_bool_text(artifact.must_be_named_in_files_written)}]"
        )
        for artifact in gate.expected_artifacts
    )


def _freshness_summary(gate: ChildGateTuple) -> str:
    freshness = gate.freshness
    if freshness is None:
        return "none"
    marker = freshness.marker or "none"
    return (
        f"marker={marker}, "
        f"mtime_at_or_after_marker={_bool_text(freshness.require_mtime_at_or_after_marker)}, "
        f"preexisting_artifacts={freshness.preexisting_artifacts}"
    )


def _applicator_summary(applicator: ChildGateApplicator) -> str:
    return f"{applicator.command} require_passed_true={_bool_text(applicator.require_passed_true)}"


def _sequence_summary(values: Iterable[str]) -> str:
    items = tuple(values)
    if not items:
        return "none"
    return ", ".join(items)


def _route_summary(routes: Iterable[tuple[object, object]]) -> str:
    items = tuple(routes)
    if not items:
        return "none"
    return ", ".join(f"{key}->{value}" for key, value in items)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _valid_non_required_status_route_result(
    request: ChildHandoffValidationRequest,
) -> ChildHandoffValidationResult | None:
    """Route valid non-success statuses without running completed-only acceptance gates."""

    return_validation = validate_gpd_return_markdown(request.return_markdown)
    if not return_validation.passed or return_validation.envelope is None:
        return None

    gate = request.gate
    envelope = return_validation.envelope
    if envelope.status == gate.required_status:
        return None

    selected_route = gate.status_route.get(envelope.status)
    if selected_route is None:
        return None

    diagnostic = (
        f"gpd_return.status {envelope.status!r} is valid but does not satisfy required success status "
        f"{gate.required_status!r}; selected status_route[{envelope.status!r}]={selected_route!r}. "
        "Artifact, validator, and applicator acceptance were not run for this non-success route."
    )
    artifact_result = HandoffArtifactValidationResult(
        passed=False,
        errors=[diagnostic],
        warnings=list(return_validation.warnings),
        status=envelope.status,
        files_written=[_normalize_return_path(path) for path in envelope.files_written],
        expected_artifacts=_expected_artifact_paths(gate),
        expected_globs=_expected_artifact_globs(gate),
        allowed_roots=list(gate.allowed_roots),
    )
    requires_applicator_pass = _requires_applicator_pass(gate)

    return ChildHandoffValidationResult(
        passed=False,
        read_only_passed=False,
        requires_applicator_pass=requires_applicator_pass,
        acceptance_complete=False,
        acceptance_state="status_routed",
        applicator_required_unrun=False,
        gate_id=gate.id,
        return_profile=gate.return_profile,
        required_status=gate.required_status,
        status=envelope.status,
        primary_failure_class=None,
        failure_classes=[],
        failures=[],
        errors=[diagnostic],
        warnings=list(return_validation.warnings),
        checked_files=[],
        expected_artifacts=list(artifact_result.expected_artifacts),
        expected_globs=list(artifact_result.expected_globs),
        allowed_roots=list(artifact_result.allowed_roots),
        validator_results=[],
        status_route=dict(gate.status_route),
        failure_route={failure_class.value: route for failure_class, route in gate.failure_route.items()},
        status_route_used=True,
        status_route_reason=diagnostic,
        selected_route=selected_route,
        next_action_class=selected_route,
        applicator_command=gate.applicator.command,
        applicator_ran=False,
        artifact_result=artifact_result,
    )


def _acceptance_state(
    *,
    status_routed: bool,
    read_only_passed: bool,
    applicator_required_unrun: bool,
    passed: bool,
) -> AcceptanceState:
    if status_routed:
        return "status_routed"
    if read_only_passed and applicator_required_unrun:
        return "read_only_passed_needs_applicator"
    if passed:
        return "accepted"
    return "failed"


def _candidate_yaml_payloads(content: str) -> tuple[str, ...]:
    stripped = content.strip()
    candidates: list[str] = []
    if stripped:
        candidates.append(stripped)
    candidates.extend(match.group(1).strip() for match in _YAML_FENCE_RE.finditer(content))
    return tuple(candidates)


def _normalize_return_path(path_text: str) -> str:
    raw = path_text.strip()
    if not raw:
        return raw
    return Path(raw).as_posix()


def _expected_artifact_paths(gate: ChildGateTuple) -> list[str]:
    return [
        artifact.path
        for artifact in gate.expected_artifacts
        if artifact.required and artifact.kind == "path" and artifact.must_be_named_in_files_written
    ]


def _expected_artifact_globs(gate: ChildGateTuple) -> list[str]:
    return [
        artifact.path
        for artifact in gate.expected_artifacts
        if artifact.required and artifact.kind == "glob" and artifact.must_be_named_in_files_written
    ]


def _freshness_failures(gate: ChildGateTuple, fresh_after: datetime | None) -> list[HandoffFailure]:
    freshness = gate.freshness
    if freshness is None or not freshness.require_mtime_at_or_after_marker or fresh_after is not None:
        return []
    marker = freshness.marker or "<missing marker>"
    message = (
        "child_gate freshness requires artifact mtime at or after "
        f"{marker!r}, but no --fresh-after timestamp was provided"
    )
    return [
        _handoff_failure(
            HandoffFailureClass.ARTIFACT_STALE,
            "freshness_requires_fresh_after",
            message,
        )
    ]


def _write_allowlist_failures(
    project_root: Path,
    gate: ChildGateTuple,
    files_written: list[str],
) -> list[HandoffFailure]:
    if not gate.write_allowlist or not files_written:
        return []

    allowed_patterns = _write_allowlist_patterns(gate)
    failures: list[HandoffFailure] = []
    root = project_root.expanduser().resolve(strict=False)
    for relpath in files_written:
        normalized = _normalize_return_path(relpath)
        if not _is_project_local_path(root, normalized):
            continue
        if _matches_any_write_pattern(normalized, allowed_patterns):
            continue
        message = f"files_written entry is outside child_gate write_allowlist: {normalized}"
        failures.append(
            _handoff_failure(
                HandoffFailureClass.ARTIFACT_ROOT_BLOCKED,
                "outside_write_allowlist",
                message,
                path=normalized,
            )
        )
    return failures


def _write_allowlist_patterns(gate: ChildGateTuple) -> tuple[str, ...]:
    patterns: list[str] = []
    patterns.extend(artifact.path for artifact in gate.expected_artifacts if artifact.required)
    patterns.extend(gate.write_allowlist)
    return tuple(dict.fromkeys(_normalize_return_path(pattern) for pattern in patterns))


def _is_project_local_path(project_root: Path, relpath: str) -> bool:
    if not relpath:
        return False
    raw_path = Path(relpath)
    if raw_path.is_absolute() or any(part == ".." for part in raw_path.parts):
        return False
    return (project_root / raw_path).resolve(strict=False).is_relative_to(project_root)


def _matches_any_write_pattern(relpath: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if _matches_write_pattern(relpath, pattern):
            return True
    return False


def _matches_write_pattern(relpath: str, pattern: str) -> bool:
    if any(char in pattern for char in "*?["):
        return fnmatch.fnmatch(relpath, pattern)
    return relpath == pattern


def _safe_validator_id(raw_validator: str) -> str | None:
    normalized = raw_validator.strip()
    lowered = normalized.casefold()
    if not normalized or lowered in {"none", "n/a", "not_applicable"}:
        return None
    if lowered in SAFE_CHILD_HANDOFF_VALIDATORS:
        return lowered
    if lowered.startswith("gpd validate handoff-artifacts"):
        return None
    command_prefixes = {
        "gpd validate plan-contract": "plan-contract",
        "gpd validate plan-preflight": "plan-preflight",
        "gpd validate proof-redteam": "proof-redteam",
        "gpd validate summary-contract": "summary-contract",
        "gpd validate verification-contract": "verification-contract",
    }
    for prefix, validator_id in command_prefixes.items():
        if lowered.startswith(prefix):
            return validator_id
    return normalized


def _run_safe_validator(
    project_root: Path,
    validator_id: str,
    checked_files: list[str],
) -> ChildHandoffValidatorResult:
    root = project_root.expanduser().resolve(strict=False)
    targets = _validator_targets(validator_id, checked_files)
    if not targets:
        return ChildHandoffValidatorResult(
            validator_id=validator_id,
            passed=False,
            errors=[f"{validator_id} validator had no matching checked artifacts"],
        )

    errors: list[str] = []
    warnings: list[str] = []
    for relpath in targets:
        path = (root / relpath).resolve(strict=False)
        try:
            if validator_id in {"readable", "paper-section-readable"}:
                _validate_readable_text(
                    path, relpath=relpath, require_non_empty=validator_id == "paper-section-readable"
                )
            elif validator_id == "plan-contract":
                errors.extend(_frontmatter_errors(path, relpath=relpath, schema="plan"))
            elif validator_id == "plan-preflight":
                item_errors, item_warnings = _plan_preflight_messages(path, relpath=relpath)
                errors.extend(item_errors)
                warnings.extend(item_warnings)
            elif validator_id == "summary-contract":
                errors.extend(_frontmatter_errors(path, relpath=relpath, schema="summary"))
            elif validator_id in {"verification-contract", "verification-report"}:
                errors.extend(_verification_contract_errors(path, relpath=relpath))
            elif validator_id == "proof-redteam":
                errors.extend(_proof_redteam_errors(path, relpath=relpath, project_root=root))
            else:  # pragma: no cover - caller filters unsupported ids.
                errors.append(f"unsupported child-handoff validator {validator_id!r}")
        except OSError as exc:
            errors.append(f"{relpath}: validator read failed: {exc}")
        except ValueError as exc:
            errors.append(f"{relpath}: {exc}")

    return ChildHandoffValidatorResult(
        validator_id=validator_id,
        passed=not errors,
        checked_files=targets,
        errors=errors,
        warnings=warnings,
    )


def _validator_targets(validator_id: str, checked_files: list[str]) -> list[str]:
    if validator_id in {"readable", "paper-section-readable"}:
        return list(checked_files)
    suffixes_by_validator = {
        "plan-contract": ("-PLAN.md",),
        "plan-preflight": ("-PLAN.md",),
        "summary-contract": ("-SUMMARY.md", "SUMMARY.md"),
        "verification-contract": ("-VERIFICATION.md", "VERIFICATION.md"),
        "verification-report": ("-VERIFICATION.md", "VERIFICATION.md"),
        "proof-redteam": ("PROOF-REDTEAM.md",),
    }
    suffixes = suffixes_by_validator.get(validator_id, ())
    return [path for path in checked_files if path.endswith(suffixes)]


def _validate_readable_text(path: Path, *, relpath: str, require_non_empty: bool = False) -> None:
    text = path.read_text(encoding="utf-8")
    if require_non_empty and not text.strip():
        raise ValueError("artifact text is empty")


def _frontmatter_errors(path: Path, *, relpath: str, schema: str) -> list[str]:
    from gpd.core.frontmatter import validate_frontmatter

    validation = validate_frontmatter(path.read_text(encoding="utf-8"), schema, source_path=path)
    errors = [f"{relpath}: {error}" for error in validation.errors]
    errors.extend(f"{relpath}: missing required frontmatter field: {field}" for field in validation.missing)
    return errors


def _plan_preflight_messages(path: Path, *, relpath: str) -> tuple[list[str], list[str]]:
    from gpd.core.tool_preflight import build_plan_tool_preflight

    result = build_plan_tool_preflight(path)
    errors = [f"{relpath}: {error}" for error in result.errors]
    errors.extend(f"{relpath}: {condition}" for condition in result.blocking_conditions)
    warnings = [f"{relpath}: {warning}" for warning in result.warnings]
    if not result.passed and not errors:
        errors.append(f"{relpath}: plan preflight failed")
    return errors, warnings


def _verification_contract_errors(path: Path, *, relpath: str) -> list[str]:
    from gpd.core.correctness_validators import validate_verification_oracle_evidence
    from gpd.core.frontmatter import validate_frontmatter

    content = path.read_text(encoding="utf-8")
    schema_result = validate_frontmatter(content, "verification", source_path=path)
    oracle_result = validate_verification_oracle_evidence(content, source_path=path)
    errors = [f"{relpath}: {error}" for error in schema_result.errors]
    errors.extend(f"{relpath}: missing required frontmatter field: {field}" for field in schema_result.missing)
    errors.extend(f"{relpath}: {error}" for error in oracle_result.errors)
    return errors


def _proof_redteam_errors(path: Path, *, relpath: str, project_root: Path) -> list[str]:
    from gpd.core.proof_redteam import validate_proof_redteam_artifact

    result = validate_proof_redteam_artifact(path, project_root=project_root)
    if _validation_result_is_valid(result):
        return []
    if hasattr(result, "errors"):
        errors = result.errors
        if isinstance(errors, list | tuple):
            return [f"{relpath}: {error}" for error in errors]
    return [f"{relpath}: proof-redteam validator failed"]


def _validation_result_is_valid(result: object) -> bool:
    for field_name in ("valid", "passed"):
        if isinstance(result, Mapping) and isinstance(result.get(field_name), bool):
            return bool(result[field_name])
        value = getattr(result, field_name, None)
        if isinstance(value, bool):
            return value
    errors = result.get("errors") if isinstance(result, Mapping) else getattr(result, "errors", None)
    if isinstance(errors, list | tuple):
        return len(errors) == 0
    return True


def _handoff_failure(
    failure_class: HandoffFailureClass,
    code: str,
    message: str,
    *,
    path: str | None = None,
    command: str | None = None,
) -> HandoffFailure:
    return HandoffFailure(
        failure_class=failure_class,
        code=code,
        message=message,
        path=path,
        command=command,
        repairable=False,
    )


def _failure_classes(failures: list[HandoffFailure]) -> list[HandoffFailureClass]:
    classes: list[HandoffFailureClass] = []
    for failure in failures:
        if failure.failure_class not in classes:
            classes.append(failure.failure_class)
    return classes


def _requires_applicator_pass(gate: ChildGateTuple) -> bool:
    return gate.applicator.command != "none" and gate.applicator.require_passed_true


def _selected_route(
    gate: ChildGateTuple,
    *,
    passed: bool,
    status: str | None,
    failures: list[HandoffFailure],
) -> str:
    if passed:
        return gate.status_route.get(status or "", "accept")
    failure_classes = _failure_classes(failures)
    if failure_classes:
        return gate.failure_route.get(failure_classes[0], "fail_closed")
    return "fail_closed"


def _profile_id_for_role_or_profile(value: str | None) -> str:
    return normalize_return_profile_id(value)


def _normalize_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_freshness_marker(value: object) -> str:
    marker = _normalize_text(value, field_name="freshness_marker")
    if marker.casefold().startswith("after "):
        return marker[6:].strip()
    return marker


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_text(value, field_name=field_name)


def _normalize_text_sequence(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, Iterable):
        raise ValueError(f"{field_name} must be an iterable of strings")

    normalized: list[str] = []
    for index, item in enumerate(value):
        normalized.append(_normalize_text(item, field_name=f"{field_name}[{index}]"))
    return tuple(normalized)


def _normalize_non_empty_text_sequence(value: object, *, field_name: str) -> tuple[str, ...]:
    normalized = _normalize_text_sequence(value, field_name=field_name)
    if not normalized:
        raise ValueError(f"{field_name} must include at least one item")
    return normalized
