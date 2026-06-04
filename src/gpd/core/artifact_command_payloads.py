"""Small payload helpers shared by artifact-facing CLI commands."""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable, Mapping, Sequence

from gpd.core.errors import GPDError

_KEYWORD_KINDS = {
    inspect.Parameter.POSITIONAL_OR_KEYWORD,
    inspect.Parameter.KEYWORD_ONLY,
}


def callable_accepts_kwarg(callable_obj: Callable[..., object], name: str) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == name and parameter.kind in _KEYWORD_KINDS:
            return True
    return False


def callable_has_explicit_kwarg(callable_obj: Callable[..., object], name: str) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == name and parameter.kind in _KEYWORD_KINDS for parameter in signature.parameters.values()
    )


def call_verification_report_skeleton_builder(builder: Callable[..., object], **kwargs: object) -> object:
    verified = kwargs.pop("verified")
    score = kwargs.pop("score")
    if verified is not None and callable_accepts_kwarg(builder, "verified"):
        kwargs["verified"] = verified
    if score is not None and callable_accepts_kwarg(builder, "score"):
        kwargs["score"] = score
    return builder(**kwargs)


def call_verification_report_finalizer(finalizer: Callable[..., object], **kwargs: object) -> object:
    outcome_patch = kwargs.pop("outcome_patch")
    call_kwargs: dict[str, object] = {
        "contract": kwargs.pop("contract"),
        "body_markdown": kwargs.pop("body_markdown"),
    }
    for patch_name in ("outcome", "outcome_patch", "patch"):
        if callable_has_explicit_kwarg(finalizer, patch_name):
            call_kwargs[patch_name] = coerce_verification_report_outcome_patch(outcome_patch)
            break
    else:
        call_kwargs["outcome_patch"] = outcome_patch
    for name, value in kwargs.items():
        if callable_accepts_kwarg(finalizer, name):
            call_kwargs[name] = value
    return finalizer(**call_kwargs)


def coerce_verification_report_outcome_patch(outcome_patch: Mapping[str, object]) -> object:
    from gpd.core.verification_report import VerificationReportOutcomePatch

    return VerificationReportOutcomePatch.model_validate(outcome_patch)


def call_proof_redteam_skeleton_builder(builder: Callable[..., object], **kwargs: object) -> object:
    claim_text = kwargs.pop("claim_text")
    proof_artifact_paths = kwargs.pop("proof_artifact_paths")
    if claim_text is not None or callable_accepts_kwarg(builder, "claim_text"):
        kwargs["claim_text"] = claim_text
    if proof_artifact_paths or callable_accepts_kwarg(builder, "proof_artifact_paths"):
        kwargs["proof_artifact_paths"] = proof_artifact_paths
    return builder(**kwargs)


def call_proof_redteam_finalizer(finalizer: Callable[..., object], **kwargs: object) -> object:
    claim_text = kwargs.pop("claim_text")
    reviewed_at = kwargs.pop("reviewed_at")
    output_path = kwargs.pop("output_path")
    claim_key = (
        "claim_statement"
        if callable_accepts_kwarg(finalizer, "claim_statement") or not callable_accepts_kwarg(finalizer, "claim_text")
        else "claim_text"
    )
    kwargs[claim_key] = claim_text
    if reviewed_at is not None or callable_accepts_kwarg(finalizer, "reviewed_at"):
        kwargs["reviewed_at"] = reviewed_at
    if callable_accepts_kwarg(finalizer, "output_path"):
        kwargs["output_path"] = output_path
    if callable_accepts_kwarg(finalizer, "write"):
        kwargs["write"] = False
    return finalizer(**kwargs)


def jsonable_value(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return value


def mapping_payload(raw_payload: object, *, label: str) -> dict[str, object]:
    payload = jsonable_value(raw_payload)
    if not isinstance(payload, Mapping):
        raise GPDError(f"{label} must return a mapping")
    return dict(payload)


def validation_result_is_valid(result: object) -> bool:
    for field_name in ("valid", "passed"):
        if isinstance(result, Mapping) and isinstance(result.get(field_name), bool):
            return bool(result[field_name])
        value = getattr(result, field_name, None)
        if isinstance(value, bool):
            return value
    if isinstance(result, Mapping) and isinstance(result.get("errors"), list):
        return len(result["errors"]) == 0
    errors = getattr(result, "errors", None)
    if isinstance(errors, list | tuple):
        return len(errors) == 0
    return True


def markdown_payload_value(
    payload: Mapping[str, object],
    *,
    keys: Sequence[str],
    label: str,
    required: bool,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.rstrip() + "\n"
    if required:
        raise GPDError(f"{label} payload is missing markdown")
    return None
