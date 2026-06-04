"""Checkpoint-intent return payloads and durable bounded-segment resolution."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator

from gpd.core.continuation import ContinuationBoundedSegment

__all__ = [
    "CheckpointIntentResolutionContext",
    "GpdReturnCheckpointIntent",
    "resolve_checkpoint_intent_bounded_segment",
]


_APPLICATOR_OWNED_CHECKPOINT_INTENT_FIELDS = frozenset(
    {
        "last_result_id",
        "recorded_by",
        "resume_file",
        "source_session_id",
        "updated_at",
    }
)
_OPTIONAL_CHECKPOINT_INTENT_TEXT_FIELDS = (
    "awaiting",
    "waiting_reason",
    "phase",
    "plan",
    "segment_status",
    "segment_id",
    "skeptical_requestioning_summary",
    "weakest_unchecked_anchor",
    "disconfirming_observation",
    "transition_id",
)
_CHECKPOINT_INTENT_BOOL_FIELDS = (
    "waiting_for_review",
    "first_result_gate_pending",
    "pre_fanout_review_pending",
    "pre_fanout_review_cleared",
    "skeptical_requestioning_required",
    "downstream_locked",
)


class GpdReturnCheckpointIntent(BaseModel):
    """Compact child-authored checkpoint intent.

    This is not durable continuation authority. The applicator expands it with
    parent-owned context, then validates the resulting bounded segment through
    the canonical continuation normalization path before mutation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    checkpoint_reason: StrictStr
    awaiting: StrictStr | None = None
    waiting_reason: StrictStr | None = None
    phase: StrictStr | None = None
    plan: StrictStr | None = None
    segment_status: StrictStr | None = None
    segment_id: StrictStr | None = None
    waiting_for_review: bool | None = None
    first_result_gate_pending: bool | None = None
    pre_fanout_review_pending: bool | None = None
    pre_fanout_review_cleared: bool | None = None
    skeptical_requestioning_required: bool | None = None
    downstream_locked: bool | None = None
    skeptical_requestioning_summary: StrictStr | None = None
    weakest_unchecked_anchor: StrictStr | None = None
    disconfirming_observation: StrictStr | None = None
    transition_id: StrictStr | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_applicator_owned_metadata(cls, value: object) -> object:
        if isinstance(value, Mapping):
            forbidden = sorted(_APPLICATOR_OWNED_CHECKPOINT_INTENT_FIELDS.intersection(value))
            if forbidden:
                fields = ", ".join(forbidden)
                noun = "field" if len(forbidden) == 1 else "fields"
                verb = "is" if len(forbidden) == 1 else "are"
                raise ValueError(f"{fields} {verb} applicator-owned checkpoint_intent {noun}; omit from child returns")
        return value

    @field_validator("checkpoint_reason", mode="before")
    @classmethod
    def _validate_required_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("checkpoint_intent.checkpoint_reason must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError("checkpoint_intent.checkpoint_reason must be a non-empty string")
        return stripped

    @field_validator(*_OPTIONAL_CHECKPOINT_INTENT_TEXT_FIELDS, mode="before")
    @classmethod
    def _validate_optional_text(cls, value: object, info) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"checkpoint_intent.{info.field_name} must be a string or null")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"checkpoint_intent.{info.field_name} must be a non-empty string when provided")
        return stripped

    @field_validator(*_CHECKPOINT_INTENT_BOOL_FIELDS, mode="before")
    @classmethod
    def _validate_optional_bool(cls, value: object, info) -> bool | None:
        if value is None:
            return None
        if type(value) is not bool:
            raise ValueError(f"checkpoint_intent.{info.field_name} must be a boolean when provided")
        return value

    @model_validator(mode="after")
    def _validate_awaiting_context(self) -> GpdReturnCheckpointIntent:
        if self.awaiting is None and self.waiting_reason is None:
            raise ValueError("checkpoint_intent requires waiting_reason or awaiting")
        return self


@dataclass(frozen=True)
class CheckpointIntentResolutionContext:
    """Parent/applicator-owned context used to resolve checkpoint intent."""

    checkpoint_resume_file: str | Path | None = None
    phase: str | None = None
    plan: str | None = None
    last_result_id: str | None = None
    source_session_id: str | None = None


def resolve_checkpoint_intent_bounded_segment(
    *,
    intent: GpdReturnCheckpointIntent,
    context: CheckpointIntentResolutionContext,
    envelope_phase: str | None = None,
    envelope_plan: str | None = None,
) -> tuple[ContinuationBoundedSegment | None, list[str]]:
    """Resolve child checkpoint intent into one durable bounded segment."""

    resume_file = _optional_context_text(context.checkpoint_resume_file)
    if resume_file is None:
        return None, ["checkpoint_intent: checkpoint_resume_file is required to resolve bounded_segment.resume_file"]

    phase = _first_text(intent.phase, context.phase, envelope_phase)
    plan = _first_text(intent.plan, context.plan, envelope_plan)
    segment_status = intent.segment_status or _default_segment_status(intent)
    payload: dict[str, object] = {
        "resume_file": resume_file,
        "phase": phase,
        "plan": plan,
        "segment_id": intent.segment_id or _generated_segment_id(intent, phase=phase, plan=plan),
        "segment_status": segment_status,
        "checkpoint_reason": intent.checkpoint_reason,
        "waiting_reason": intent.waiting_reason or intent.awaiting,
        "last_result_id": _optional_context_text(context.last_result_id),
        "source_session_id": _optional_context_text(context.source_session_id),
    }

    for field_name in _CHECKPOINT_INTENT_BOOL_FIELDS:
        value = getattr(intent, field_name)
        if value is not None:
            payload[field_name] = value

    for field_name in (
        "skeptical_requestioning_summary",
        "weakest_unchecked_anchor",
        "disconfirming_observation",
        "transition_id",
    ):
        value = getattr(intent, field_name)
        if value is not None:
            payload[field_name] = value

    return ContinuationBoundedSegment.model_validate(payload), []


def _optional_context_text(value: str | Path | None) -> str | None:
    if value is None:
        return None
    text = value.as_posix() if isinstance(value, Path) else str(value)
    stripped = text.strip()
    return stripped or None


def _first_text(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _default_segment_status(intent: GpdReturnCheckpointIntent) -> str:
    awaiting = (intent.awaiting or intent.waiting_reason or "").casefold()
    if intent.waiting_for_review or intent.first_result_gate_pending or intent.pre_fanout_review_pending:
        return "waiting_review"
    if "review" in awaiting:
        return "waiting_review"
    if "user" in awaiting or "human" in awaiting:
        return "awaiting_user"
    return "paused"


def _generated_segment_id(intent: GpdReturnCheckpointIntent, *, phase: str | None, plan: str | None) -> str:
    parts = ["checkpoint", intent.checkpoint_reason, phase, plan]
    raw = "-".join(part for part in parts if part)
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-._")
    return normalized or "checkpoint"
