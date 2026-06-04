"""Typed staged-init payload specs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias

InitFieldKind: TypeAlias = Literal["scalar", "list", "dict"]

_STAGED_LOADING_KEY = "staged_loading"
_SCALAR_TYPES = (str, int, float, bool)


class StagedInitSpecLookupError(KeyError):
    """Raised when a staged-init spec id is not registered for a workflow stage."""


class StagedInitPayloadValidationError(ValueError):
    """Raised when a staged-init payload does not match its active-field spec."""


@dataclass(frozen=True, slots=True)
class StagedInitFieldSpec:
    name: str
    kind: InitFieldKind
    allow_none: bool = False


@dataclass(frozen=True, slots=True)
class StagedInitSpec:
    workflow_id: str
    stage_id: str
    init_spec_id: str
    fields: tuple[StagedInitFieldSpec, ...]

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    def field_by_name(self, field_name: str) -> StagedInitFieldSpec:
        for field in self.fields:
            if field.name == field_name:
                return field
        raise KeyError(field_name)


def _scalar(name: str, *, allow_none: bool = False) -> StagedInitFieldSpec:
    return StagedInitFieldSpec(name=name, kind="scalar", allow_none=allow_none)


def _list(name: str, *, allow_none: bool = False) -> StagedInitFieldSpec:
    return StagedInitFieldSpec(name=name, kind="list", allow_none=allow_none)


def _dict(name: str, *, allow_none: bool = False) -> StagedInitFieldSpec:
    return StagedInitFieldSpec(name=name, kind="dict", allow_none=allow_none)


_QUICK_TASK_COMMON_FIELDS = (
    _scalar("planner_model", allow_none=True),
    _scalar("executor_model", allow_none=True),
    _scalar("commit_docs"),
    _scalar("autonomy"),
    _scalar("research_mode"),
    _scalar("next_num"),
    _scalar("slug", allow_none=True),
    _scalar("description", allow_none=True),
    _scalar("date"),
    _scalar("timestamp"),
    _scalar("quick_dir"),
    _scalar("task_dir", allow_none=True),
    _scalar("roadmap_exists"),
    _scalar("project_exists"),
    _scalar("planning_exists"),
    _scalar("platform"),
    _dict("project_contract", allow_none=True),
    _dict("project_contract_gate"),
    _dict("project_contract_load_info"),
    _dict("project_contract_validation", allow_none=True),
)

_QUICK_REFERENCE_RUNTIME_FIELDS = (
    _dict("contract_intake", allow_none=True),
    _dict("effective_reference_intake"),
    _list("selected_protocol_bundle_ids"),
    _scalar("protocol_bundle_count"),
    _dict("protocol_bundle_load_manifest"),
    _list("protocol_bundle_verifier_extensions"),
    _list("reference_artifact_files"),
    _list("literature_review_files"),
    _scalar("literature_review_count"),
    _list("research_map_reference_files"),
    _scalar("research_map_reference_count"),
    _dict("derived_manuscript_proof_review_status"),
)


def _quick_spec(stage_id: str, fields: tuple[StagedInitFieldSpec, ...]) -> StagedInitSpec:
    return StagedInitSpec(
        workflow_id="quick",
        stage_id=stage_id,
        init_spec_id=f"quick.{stage_id}.v1",
        fields=fields,
    )


WORKFLOW_INIT_SPECS: tuple[StagedInitSpec, ...] = (
    _quick_spec("task_bootstrap", _QUICK_TASK_COMMON_FIELDS),
    _quick_spec("task_authoring", _QUICK_TASK_COMMON_FIELDS),
    _quick_spec("reference_context", (*_QUICK_TASK_COMMON_FIELDS, *_QUICK_REFERENCE_RUNTIME_FIELDS)),
)

_SPEC_REGISTRY = {(spec.workflow_id, spec.stage_id, spec.init_spec_id): spec for spec in WORKFLOW_INIT_SPECS}


def get_staged_init_spec(workflow_id: str, stage_id: str, init_spec_id: str) -> StagedInitSpec:
    try:
        return _SPEC_REGISTRY[(workflow_id, stage_id, init_spec_id)]
    except KeyError as exc:
        raise StagedInitSpecLookupError(
            f"Unknown staged init spec {init_spec_id!r} for workflow {workflow_id!r} stage {stage_id!r}"
        ) from exc


def validate_staged_init_payload(
    workflow_id: str,
    stage_id: str,
    init_spec_id: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    """Validate active staged-init fields and return the original payload."""
    spec = get_staged_init_spec(workflow_id, stage_id, init_spec_id)
    if not isinstance(payload, Mapping):
        _raise_validation_error(spec, [f"payload expected dict, got {_kind_name(payload)}"])

    expected_fields = spec.field_names
    expected_field_set = set(expected_fields)
    active_fields = {field for field in payload if field != _STAGED_LOADING_KEY}

    missing_fields = [field for field in expected_fields if field not in active_fields]
    extra_fields = sorted(str(field) for field in active_fields - expected_field_set)
    errors: list[str] = []
    if missing_fields:
        errors.append(f"missing field(s): {', '.join(missing_fields)}")
    if extra_fields:
        errors.append(f"extra field(s): {', '.join(extra_fields)}")

    if errors:
        _raise_validation_error(spec, errors)

    for field_spec in spec.fields:
        _validate_field_value(spec, field_spec, payload[field_spec.name])

    return payload


def _validate_field_value(spec: StagedInitSpec, field_spec: StagedInitFieldSpec, value: object) -> None:
    if value is None and field_spec.allow_none:
        return
    if value is None:
        _raise_validation_error(
            spec,
            [f"field {field_spec.name!r} expected {field_spec.kind}, got none"],
        )

    valid = False
    if field_spec.kind == "scalar":
        valid = _is_scalar(value)
    elif field_spec.kind == "list":
        valid = _is_list_like(value)
    elif field_spec.kind == "dict":
        valid = isinstance(value, Mapping)

    if not valid:
        _raise_validation_error(
            spec,
            [f"field {field_spec.name!r} expected {field_spec.kind}, got {_kind_name(value)}"],
        )


def _is_scalar(value: object) -> bool:
    return isinstance(value, _SCALAR_TYPES)


def _is_list_like(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)


def _kind_name(value: object) -> str:
    if isinstance(value, Mapping):
        return "dict"
    if _is_list_like(value):
        return "list"
    if value is None:
        return "none"
    return "scalar"


def _raise_validation_error(spec: StagedInitSpec, errors: list[str]) -> None:
    details = "; ".join(errors)
    raise StagedInitPayloadValidationError(
        f"Invalid staged init payload for workflow {spec.workflow_id!r} stage {spec.stage_id!r} "
        f"spec {spec.init_spec_id!r}: {details}"
    )


__all__ = [
    "InitFieldKind",
    "StagedInitFieldSpec",
    "StagedInitPayloadValidationError",
    "StagedInitSpec",
    "StagedInitSpecLookupError",
    "WORKFLOW_INIT_SPECS",
    "get_staged_init_spec",
    "validate_staged_init_payload",
]
