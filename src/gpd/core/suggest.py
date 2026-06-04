"""Next-action intelligence for GPD research projects.

Analyzes current project state and returns prioritized recommendations for next steps.

Layer 1 code: stdlib + pathlib + json + dataclasses only.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from gpd.command_labels import canonical_command_label, parse_command_label, runtime_public_command_prefixes
from gpd.contracts import ConventionLock
from gpd.core.command_run_hints import (
    NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME,
    NEXT_COMMAND_SURFACE_CONTEXT_SHARED_NEXT_UP,
    NextCommand,
    classify_next_command,
)
from gpd.core.constants import (
    LITERATURE_DIR_NAME,
    PHASES_DIR_NAME,
    PLAN_SUFFIX,
    PLANNING_DIR_NAME,
    PROJECT_FILENAME,
    RESEARCH_SUFFIX,
    ROADMAP_FILENAME,
    STANDALONE_PLAN,
    STANDALONE_RESEARCH,
    STANDALONE_SUMMARY,
    STATE_JSON_FILENAME,
    SUMMARY_SUFFIX,
    TODOS_DIR_NAME,
    VERIFICATION_SUFFIX,
)
from gpd.core.manuscript_artifacts import (
    locate_publication_artifact,
    resolve_current_manuscript_artifacts,
    resolve_current_manuscript_resolution,
    resolve_current_publication_subject,
)
from gpd.core.phases import _milestone_completion_snapshot, roadmap_analyze
from gpd.core.project_reentry import resolve_project_reentry
from gpd.core.proof_review import (
    manuscript_requires_theorem_bearing_review,
    publication_lineage_roots,
    resolve_manuscript_proof_review_status,
)
from gpd.core.public_surface_contract import recovery_cross_workspace_command, recovery_local_snapshot_command
from gpd.core.publication_runtime import (
    resolve_latest_publication_response_artifacts,
    resolve_latest_publication_review_artifacts,
    resolve_publication_response_freshness,
)
from gpd.core.reproducibility import compute_sha256
from gpd.core.runtime_command_surfaces import format_active_runtime_command
from gpd.core.utils import (
    compare_phase_numbers as _compare_phase_numbers,
)
from gpd.core.utils import (
    is_phase_complete as _is_phase_complete,
)
from gpd.core.utils import (
    matching_phase_artifact_count as _matching_phase_artifact_count,
)
from gpd.core.utils import (
    phase_normalize as _phase_normalize,
)
from gpd.core.utils import (
    phase_sort_key as _phase_sort_key,
)
from gpd.core.utils import (
    phase_unpad as _phase_unpad,
)
from gpd.core.verification_status import read_verification_status
from gpd.mcp.paper.bibliography import BibliographyAudit
from gpd.mcp.paper.models import ArtifactManifest

logger = logging.getLogger(__name__)

__all__ = [
    "NextCommand",
    "Recommendation",
    "SuggestContext",
    "SuggestResult",
    "suggest_next",
]

# ─── Constants ────────────────────────────────────────────────────────────────

CORE_CONVENTIONS = ("metric_signature", "natural_units", "coordinate_system")


# ─── Data Models ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A single prioritized next-action recommendation."""

    action: str
    priority: int
    reason: str
    command: str
    phase: str | None = None
    next_command: NextCommand | None = None


@dataclass(slots=True)
class _MutableRecommendation:
    """Internal mutable recommendation for priority adjustment."""

    action: str
    priority: int
    reason: str
    command: str
    phase: str | None = None
    next_command: NextCommand | None = None

    def freeze(self) -> Recommendation:
        return Recommendation(
            action=self.action,
            priority=self.priority,
            reason=self.reason,
            command=self.command,
            phase=self.phase,
            next_command=self.next_command
            or _build_next_command_decision(
                action=self.action,
                command=self.command,
                phase=self.phase,
                reason=self.reason,
            ),
        )


@dataclass(frozen=True, slots=True)
class SuggestContext:
    """Contextual information gathered during analysis."""

    current_phase: str | None = None
    status: str | None = None
    progress_percent: float = 0.0
    paused_at: str | None = None
    phase_count: int = 0
    completed_phases: int = 0
    active_blockers: int = 0
    unverified_results: int = 0
    open_questions: int = 0
    active_calculations: int = 0
    pending_todos: int = 0
    missing_conventions: tuple[str, ...] = ()
    has_paper: bool = False
    has_literature_review: bool = False
    has_referee_report: bool = False
    autonomy: str = "supervised"
    research_mode: str = "balanced"
    adaptive_approach_locked: bool = False


@dataclass(frozen=True, slots=True)
class SuggestResult:
    """Complete suggestion output with recommendations and context."""

    suggestions: list[Recommendation]
    total_suggestions: int
    suggestion_count: int
    top_action: Recommendation | None
    context: SuggestContext


@dataclass(frozen=True, slots=True)
class _PhaseAnalysis:
    """Internal analysis of a single phase directory."""

    number: str
    name: str | None
    status: str  # "complete", "in_progress", "researched", "pending"
    plan_count: int
    summary_count: int
    incomplete_count: int
    has_research: bool
    has_verification: bool
    verification_status: str


@dataclass(frozen=True, slots=True)
class _PhaseLifecycleSuggestion:
    """Blocking lifecycle recommendation for a summary-complete phase."""

    action: str
    priority: int
    reason: str
    command: str
    phase: str
    next_command: NextCommand | None = None


# ─── Internal Helpers ─────────────────────────────────────────────────────────


def _planning_dir(cwd: Path) -> Path:
    return cwd / PLANNING_DIR_NAME


def _path_exists(cwd: Path, relative: str) -> bool:
    return (cwd / relative).exists()


def _is_plan_file(name: str) -> bool:
    return name.endswith(PLAN_SUFFIX) or name == STANDALONE_PLAN


def _is_summary_file(name: str) -> bool:
    return name.endswith(SUMMARY_SUFFIX) or name == STANDALONE_SUMMARY


def _is_research_file(name: str) -> bool:
    return name.endswith(RESEARCH_SUFFIX) or name == STANDALONE_RESEARCH


def _is_verification_file(name: str) -> bool:
    return name.endswith(VERIFICATION_SUFFIX)


def _phase_verification_status(phase_path: Path, files: list[str]) -> str:
    """Classify phase verification freshness from local verification artifacts."""
    verification_files = sorted(file for file in files if _is_verification_file(file))
    if not verification_files:
        return "missing"

    statuses: list[str] = []
    for filename in verification_files:
        payload = read_verification_status(phase_path / filename)
        statuses.append(payload.routing_status)

    blocking = {
        "unreadable",
        "unparseable",
        "missing_status",
        "unknown_status",
        "gaps_found",
        "human_needed",
        "expert_needed",
    }
    for status in statuses:
        if status in blocking:
            return status
    if any(status == "passed" for status in statuses):
        return "passed"
    return "present"


def _load_config(cwd: Path) -> dict[str, object]:
    """Load project config.json, preserving canonical validation behavior.

    Missing config files still resolve to defaults via
    :func:`gpd.core.config.load_config`. Malformed files and removed keys are
    intentionally surfaced to callers instead of being silently masked here.
    """
    from gpd.core.config import load_config as _load_config_canonical

    cfg = _load_config_canonical(cwd)
    return {
        "autonomy": str(cfg.autonomy.value),
        "research_mode": str(cfg.research_mode.value),
    }


_LOCAL_CLI_INIT_COMMANDS: dict[str, str] = {
    "check-todos": "todos",
    "execute-phase": "execute-phase",
    "map-research": "map-research",
    "milestone-op": "milestone-op",
    "new-milestone": "new-milestone",
    "new-project": "new-project",
    "phase-op": "phase-op",
    "plan-phase": "plan-phase",
    "quick": "quick",
    "resume": "resume",
    "resume-work": "resume",
    "verify-work": "verify-work",
}

_LOCAL_CLI_PUBLIC_COMMANDS: dict[str, str] = {
    # Resume is a user-facing recovery command even when the local CLI still
    # routes most workflow assembly through `gpd init ...`.
    "resume": recovery_local_snapshot_command(),
    "resume-work": recovery_local_snapshot_command(),
    "progress": "gpd progress",
}

_RUNTIME_LABEL_FALLBACK_ACTIONS = frozenset({"verify-work"})


def _format_local_cli_command(action: str) -> str:
    """Format the best available local CLI equivalent for a workflow action."""
    if action in _RUNTIME_LABEL_FALLBACK_ACTIONS:
        return canonical_command_label(action)
    public_command = _LOCAL_CLI_PUBLIC_COMMANDS.get(action)
    if public_command is not None:
        return public_command
    init_action = _LOCAL_CLI_INIT_COMMANDS.get(action)
    if init_action is not None:
        return f"gpd init {init_action}"
    return canonical_command_label(action)


def _format_command(action: str, *, cwd: Path | None = None) -> str:
    """Format a GPD command name."""
    try:
        formatted = format_active_runtime_command(action, cwd=cwd, fallback=None)
    except Exception:
        formatted = None
    return formatted if formatted is not None else _format_local_cli_command(action)


def _build_recommendation(
    *,
    action: str,
    priority: int,
    reason: str,
    command: str,
    phase: str | None = None,
) -> Recommendation:
    return Recommendation(
        action=action,
        priority=priority,
        reason=reason,
        command=command,
        phase=phase,
        next_command=_build_next_command_decision(action=action, command=command, phase=phase, reason=reason),
    )


def _display_action_from_command(command: str, fallback: str) -> str:
    parsed = parse_command_label(command)
    if parsed.prefix and parsed.slug:
        return parsed.slug
    if command.startswith("gpd init "):
        parts = command.split()
        if len(parts) >= 3:
            return parts[2]
    return fallback


def _active_runtime_public_prefix_for_command(command: str) -> str | None:
    parsed = parse_command_label(command)
    if parsed.prefix and parsed.prefix in runtime_public_command_prefixes():
        return parsed.prefix
    return None


def _build_next_command_decision(
    *,
    action: str,
    command: str,
    phase: str | None = None,
    reason: str | None = None,
) -> NextCommand | None:
    normalized_command = command.strip()
    command_action = _display_action_from_command(normalized_command, action)
    active_runtime_public_prefix = _active_runtime_public_prefix_for_command(normalized_command)
    return classify_next_command(
        command=normalized_command,
        action=command_action,
        phase=phase,
        reason=reason,
        surface_context=NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME
        if active_runtime_public_prefix is not None
        else NEXT_COMMAND_SURFACE_CONTEXT_SHARED_NEXT_UP,
        active_runtime_public_prefix=active_runtime_public_prefix,
    )


_SHARED_LIFECYCLE_UNAVAILABLE = object()
_SHARED_LIFECYCLE_BLOCKS_WITHOUT_SUGGESTION = object()


def _lifecycle_value(decision: object, *names: str) -> object | None:
    for name in names:
        if isinstance(decision, dict) and name in decision:
            return decision[name]
        value = getattr(decision, name, None)
        if value is not None:
            return value
    return None


def _command_label_from_value(value: object) -> str | None:
    if isinstance(value, str):
        label = value.strip()
        return label or None
    if isinstance(value, dict):
        for key in ("command", "label", "primary"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return None
    for attr in ("command", "label"):
        nested = getattr(value, attr, None)
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def _mapping_from_value(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, NextCommand):
        return value.as_dict()
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json")
        except TypeError:
            dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        dumped = as_dict()
        if isinstance(dumped, dict):
            return dumped
    return None


def _payload_value(value: object, *names: str) -> object | None:
    mapping = _mapping_from_value(value)
    if mapping is not None:
        for name in names:
            if name in mapping:
                return mapping[name]
        return None
    for name in names:
        nested = getattr(value, name, None)
        if nested is not None:
            return nested
    return None


def _payload_text(value: object, *names: str) -> str | None:
    nested = _payload_value(value, *names)
    if nested is None:
        return None
    text = str(nested).strip()
    return text or None


def _payload_bool(
    value: object,
    name: str,
    *,
    default: bool,
) -> bool:
    nested = _payload_value(value, name)
    if nested is None:
        return default
    return bool(nested)


def _payload_int(value: object, name: str, *, default: int) -> int:
    nested = _payload_value(value, name)
    if nested is None:
        return default
    try:
        return int(nested)
    except (TypeError, ValueError):
        return default


def _payload_notes(value: object) -> tuple[str, ...]:
    raw_notes = _payload_value(value, "notes")
    if not isinstance(raw_notes, (list, tuple)):
        return ()
    return tuple(str(note) for note in raw_notes if str(note).strip())


def _normalize_lifecycle_owner(owner: object, *, kind: object | None = None) -> str | None:
    raw_owner = str(owner or "").strip().lower().replace("-", "_")
    if raw_owner == "local_helper":
        return "local_readonly"
    if raw_owner in {"runtime", "local_readonly", "local_finalizer", "local_transition", "display_only"}:
        return raw_owner

    raw_kind = str(kind or "").strip().lower()
    if raw_kind == "runtime_command_label":
        return "runtime"
    if raw_kind == "local_cli_transition_command":
        return "local_transition"
    if raw_kind == "local_cli_finalizer_command":
        return "local_finalizer"
    if raw_kind == "local_cli_validation_command":
        return "local_readonly"
    if raw_kind == "unknown_display_only":
        return "display_only"
    return None


def _is_typed_lifecycle_command_payload(value: object) -> bool:
    if isinstance(value, NextCommand):
        return True
    mapping = _mapping_from_value(value)
    if mapping is None:
        return False
    if "next_command" in mapping:
        return True
    return "owner" in mapping and "kind" in mapping and any(key in mapping for key in ("label", "command", "action"))


def _call_lifecycle_value(value: object) -> object:
    if not callable(value):
        return value
    try:
        return value()
    except TypeError:
        return value


def _typed_route_command_candidate(route: object, *names: str) -> object | None:
    for name in names:
        candidate = _call_lifecycle_value(_lifecycle_value(route, name))
        if _is_typed_lifecycle_command_payload(candidate):
            return candidate
    return None


def _canonical_lifecycle_primary_command_payload(route: object) -> object | None:
    transition_owner = (
        str(_lifecycle_value(route, "transition_owner", "primary_owner") or "")
        .strip()
        .lower()
        .replace("-", "_")
    )
    local_transition = _typed_route_command_candidate(route, "local_transition_command")
    if transition_owner == "local_transition" and local_transition is not None:
        return local_transition

    runtime_primary = _typed_route_command_candidate(route, "primary_runtime_command")
    if runtime_primary is not None:
        return runtime_primary

    after_local_runtime = _typed_route_command_candidate(route, "after_local_runtime_command")
    if transition_owner == "local_transition" and after_local_runtime is not None:
        return after_local_runtime
    if local_transition is not None:
        return local_transition
    return None


def _canonical_lifecycle_primary_command_payload_from_decision(decision: object) -> object | None:
    for route in (_lifecycle_value(decision, "lifecycle_next_up"), _lifecycle_value(decision, "next_up")):
        if route is None:
            continue
        candidate = _canonical_lifecycle_primary_command_payload(route)
        if candidate is not None:
            return candidate
    return None


def _lifecycle_primary_command_payload(decision: object) -> object | None:
    typed_lifecycle_next_up = _lifecycle_value(decision, "lifecycle_next_up")
    lifecycle_next_up = typed_lifecycle_next_up or _lifecycle_value(decision, "next_up")
    if lifecycle_next_up is not None:
        canonical_candidate = _canonical_lifecycle_primary_command_payload(lifecycle_next_up)
        if canonical_candidate is not None:
            return canonical_candidate

        for key in ("primary_next_command", "primary_command", "primary", "next_command", "typed_next_command"):
            candidate = _call_lifecycle_value(_lifecycle_value(lifecycle_next_up, key))
            if _is_typed_lifecycle_command_payload(candidate):
                return candidate

        next_up_mapping = _mapping_from_value(lifecycle_next_up)
        if next_up_mapping is not None:
            for key in ("primary_next_command", "primary_command", "primary", "next_command", "typed_next_command"):
                candidate = _call_lifecycle_value(next_up_mapping.get(key))
                if _is_typed_lifecycle_command_payload(candidate) and not isinstance(candidate, str):
                    return candidate

    for key in ("primary_next_command", "next_command", "typed_next_command"):
        candidate = _call_lifecycle_value(_lifecycle_value(decision, key))
        if _is_typed_lifecycle_command_payload(candidate):
            return candidate

    next_up = _lifecycle_value(decision, "next_up")
    next_up_mapping = _mapping_from_value(next_up)
    if next_up_mapping is None:
        return None

    for key in ("primary_next_command", "next_command", "typed_next_command", "primary_command", "primary"):
        candidate = next_up_mapping.get(key)
        if _is_typed_lifecycle_command_payload(candidate) and not isinstance(candidate, str):
            return candidate

    commands = next_up_mapping.get("commands")
    if not isinstance(commands, list):
        return None

    first_typed: object | None = None
    for candidate in commands:
        if not _is_typed_lifecycle_command_payload(candidate):
            continue
        if first_typed is None:
            first_typed = candidate
        if _payload_text(candidate, "role") == "primary":
            return candidate
    return first_typed


_PHASE_RUNTIME_ACTIONS = frozenset({"verify-work", "execute-phase", "plan-phase", "discuss-phase"})


def _lifecycle_runtime_command_label(
    *,
    action: str | None,
    phase: str | None,
    fallback_command: str | None,
    format_command,
) -> str | None:
    if not action:
        return fallback_command
    try:
        base_command = format_command(action)
    except Exception:
        logger.debug("suggest: active runtime command formatting failed for lifecycle payload", exc_info=True)
        base_command = None
    if base_command is None:
        base_command = canonical_command_label(action)
    if action in _PHASE_RUNTIME_ACTIONS and phase:
        return f"{base_command} {phase}"
    return base_command


def _next_command_from_lifecycle_payload(
    payload: object,
    *,
    fallback_action: str | None,
    fallback_phase: str | None,
    fallback_reason: str | None,
    format_command,
) -> NextCommand | None:
    if payload is None:
        return None

    if isinstance(payload, NextCommand):
        action = _normalize_lifecycle_action(payload.action, None) or fallback_action
        phase = payload.phase or fallback_phase
        label = payload.label
        if payload.owner == "runtime":
            label = (
                _lifecycle_runtime_command_label(
                    action=action,
                    phase=phase,
                    fallback_command=label,
                    format_command=format_command,
                )
                or label
            )
        return NextCommand(
            label=label,
            action=action,
            owner=payload.owner,
            phase=phase,
            reason=payload.reason or fallback_reason,
            kind=payload.kind,
            requires_user_initiated_runtime_command=payload.requires_user_initiated_runtime_command,
            fresh_context_recommended=payload.fresh_context_recommended,
            notes=payload.notes,
            schema_version=payload.schema_version,
            execution=payload.execution,
        )

    mapping = _mapping_from_value(payload)
    if mapping is None:
        return None

    nested = mapping.get("next_command")
    if nested is not None and nested is not payload:
        nested_next_command = _next_command_from_lifecycle_payload(
            nested,
            fallback_action=fallback_action,
            fallback_phase=fallback_phase,
            fallback_reason=fallback_reason,
            format_command=format_command,
        )
        if nested_next_command is not None:
            return nested_next_command

    owner = _normalize_lifecycle_owner(mapping.get("owner"), kind=mapping.get("kind"))
    kind = _payload_text(mapping, "kind")
    if owner is None or kind is None:
        return None

    action = _normalize_lifecycle_action(_payload_value(mapping, "action"), None) or fallback_action
    phase = _payload_text(mapping, "phase") or fallback_phase
    label = _command_label_from_value(mapping)
    if owner == "runtime":
        label = _lifecycle_runtime_command_label(
            action=action,
            phase=phase,
            fallback_command=label,
            format_command=format_command,
        )
    if label is None:
        return None

    reason = _payload_text(mapping, "reason") or fallback_reason
    return NextCommand(
        label=label,
        action=action,
        owner=owner,
        phase=phase,
        reason=reason,
        kind=kind,
        requires_user_initiated_runtime_command=_payload_bool(
            mapping,
            "requires_user_initiated_runtime_command",
            default=owner == "runtime",
        ),
        fresh_context_recommended=_payload_bool(
            mapping,
            "fresh_context_recommended",
            default=owner == "runtime",
        ),
        notes=_payload_notes(mapping),
        schema_version=_payload_int(mapping, "schema_version", default=1),
        execution=_payload_text(mapping, "execution") or "not_executed",
    )


def _normalize_lifecycle_action(action: object, status: object | None = None) -> str | None:
    raw = str(action or "").strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "verify": "verify-work",
        "verification": "verify-work",
        "run-verification": "verify-work",
        "run-verify-work": "verify-work",
        "closeout": "phase-complete",
        "complete-phase": "phase-complete",
        "phase-complete": "phase-complete",
        "phase-transition": "phase-complete",
        "local-transition": "phase-complete",
    }
    if raw in aliases:
        return aliases[raw]
    if raw in {"", "none", "ready", "after-closeout", "next-phase", "next"}:
        raw_status = str(status or "").strip().lower().replace("_", "-").replace(" ", "-")
        if "verify" in raw_status or "verification" in raw_status:
            return "verify-work"
        if "closeout" in raw_status or "phase-complete" in raw_status or "transition" in raw_status:
            return "phase-complete"
        return None
    return raw


def _coerce_shared_phase_lifecycle_suggestion(
    decision: object,
    *,
    phase: _PhaseAnalysis,
    format_command,
) -> _PhaseLifecycleSuggestion | None | object:
    if decision is None:
        return None

    decision_kind = (
        str(_lifecycle_value(decision, "decision", "lifecycle_state") or "").strip().lower().replace("-", "_")
    )
    status = _lifecycle_value(decision, "status", "state", "decision", "lifecycle_state")
    phase_number = str(_lifecycle_value(decision, "phase", "phase_number") or phase.number)
    closed_next_phase = decision_kind == "closed_ready_next_phase"
    primary_payload = (
        _canonical_lifecycle_primary_command_payload_from_decision(decision)
        if closed_next_phase
        else _lifecycle_primary_command_payload(decision)
    )
    if decision_kind == "closed_milestone_complete":
        return None
    if closed_next_phase:
        primary_action = _normalize_lifecycle_action(_payload_value(primary_payload, "action"), status)
        if primary_action not in {"discuss-phase", "execute-phase", "plan-phase"}:
            return None

    ready_for_next = _lifecycle_value(
        decision,
        "ready_for_next_phase",
        "ready_for_downstream",
        "closeout_complete",
        "closed",
        "after_closeout",
        "phase_closed",
    )
    if ready_for_next is True and not closed_next_phase:
        return None

    blocks_downstream = _lifecycle_value(
        decision,
        "blocks_downstream",
        "block_downstream",
        "blocks_next_phase",
        "blocks_downstream_suggestions",
    )
    if blocks_downstream is False and not closed_next_phase:
        return None

    if primary_payload is None:
        logger.debug("suggest: lifecycle decision for phase %s had no typed primary next-up", phase_number)
        return _SHARED_LIFECYCLE_BLOCKS_WITHOUT_SUGGESTION

    primary_payload_action = _payload_value(primary_payload, "action") if primary_payload is not None else None
    action = _normalize_lifecycle_action(
        _lifecycle_value(decision, "action", "next_action", "recommended_action", "primary_action")
        or primary_payload_action,
        status,
    )
    if action is None:
        logger.debug("suggest: lifecycle decision for phase %s had no primary action", phase_number)
        return _SHARED_LIFECYCLE_BLOCKS_WITHOUT_SUGGESTION

    priority_value = _lifecycle_value(decision, "priority")
    try:
        priority = int(priority_value) if priority_value is not None else 2
    except (TypeError, ValueError):
        priority = 2

    reason_value = _lifecycle_value(decision, "reason", "message", "summary")
    reason = str(reason_value).strip() if reason_value is not None else ""
    if not reason:
        blockers = _lifecycle_value(decision, "closeout_blockers", "blockers")
        if decision_kind == "blocked_closeout" and isinstance(blockers, list) and blockers:
            blocker_preview = "; ".join(str(blocker) for blocker in blockers[:2])
            reason = f"Phase {phase_number} closeout is blocked: {blocker_preview}"
        elif action == "verify-work":
            routing_status = str(_lifecycle_value(decision, "verification_routing_status") or "missing")
            if routing_status == "missing":
                reason = f"Phase {phase_number} is complete but unverified — run verification"
            else:
                reason = f"Phase {phase_number} verification is {routing_status} — refresh verification"
        elif action == "phase-complete":
            reason = f"Phase {phase_number} passed verification but is not closed — run the local transition"
        else:
            reason = f"Phase {phase_number} lifecycle gate blocks downstream suggestions"

    next_command = _next_command_from_lifecycle_payload(
        primary_payload,
        fallback_action=action,
        fallback_phase=phase_number,
        fallback_reason=reason,
        format_command=format_command,
    )
    if next_command is None or next_command.owner == "display_only":
        logger.debug("suggest: lifecycle decision for phase %s had no executable typed primary", phase_number)
        return _SHARED_LIFECYCLE_BLOCKS_WITHOUT_SUGGESTION

    command = next_command.command
    if next_command.action:
        action = next_command.action

    return _PhaseLifecycleSuggestion(
        action=action,
        priority=priority,
        reason=reason,
        command=command,
        phase=next_command.phase or phase_number,
        next_command=next_command,
    )


def _shared_phase_lifecycle_suggestion(
    cwd: Path,
    phase: _PhaseAnalysis,
    *,
    format_command,
) -> _PhaseLifecycleSuggestion | None | object:
    try:
        from gpd.core.phase_lifecycle import phase_lifecycle_decision
    except (ImportError, ModuleNotFoundError):
        return _SHARED_LIFECYCLE_UNAVAILABLE

    try:
        decision = phase_lifecycle_decision(cwd, phase.number, require_verification=True)
    except TypeError:
        decision = phase_lifecycle_decision(cwd, phase.number)
    except Exception:
        logger.debug("shared phase lifecycle decision failed", exc_info=True)
        return _SHARED_LIFECYCLE_UNAVAILABLE

    return _coerce_shared_phase_lifecycle_suggestion(
        decision,
        phase=phase,
        format_command=format_command,
    )


def _roadmap_marks_phase_closed(cwd: Path, phase_number: str) -> bool:
    try:
        roadmap = roadmap_analyze(cwd)
    except Exception:
        logger.debug("suggest: roadmap lifecycle analysis failed", exc_info=True)
        return False

    normalized = _phase_normalize(phase_number)
    return any(_phase_normalize(phase.number) == normalized and phase.roadmap_complete for phase in roadmap.phases)


def _state_indicates_phase_closed(state: dict[str, object] | None, phase_number: str) -> bool:
    if not isinstance(state, dict):
        return False
    position = state.get("position")
    if not isinstance(position, dict):
        return False

    status = str(position.get("status") or "").strip().casefold()
    current_phase = position.get("current_phase")
    if status == "milestone complete" and str(current_phase or "").strip().casefold() in {"", "none", "null"}:
        return True
    if current_phase is None:
        return False

    current = str(current_phase).strip()
    if not current or current.casefold() in {"none", "null", "n/a"}:
        return status == "milestone complete"
    if _phase_normalize(current) == _phase_normalize(phase_number):
        return False
    return _compare_phase_numbers(_phase_normalize(current), _phase_normalize(phase_number)) > 0


def _phase_is_closed_after_verification(
    cwd: Path,
    phase_number: str,
    *,
    state: dict[str, object] | None,
) -> bool:
    return _roadmap_marks_phase_closed(cwd, phase_number) or _state_indicates_phase_closed(state, phase_number)


def _closeout_readiness_safely(cwd: Path, phase_number: str):
    try:
        from gpd.core.phase_closeout import phase_closeout_readiness

        return phase_closeout_readiness(cwd, phase_number, require_verification=True)
    except Exception:
        logger.debug("suggest: phase closeout readiness failed", exc_info=True)
        return None


def _blocked_closeout_lifecycle_suggestion(
    readiness: object,
    *,
    phase_number: str,
    format_command,
) -> _PhaseLifecycleSuggestion:
    next_up = getattr(readiness, "next_up", {})
    command_entries = next_up.get("commands") if isinstance(next_up, dict) else None
    primary_entry = command_entries[0] if isinstance(command_entries, list) and command_entries else {}
    if not isinstance(primary_entry, dict):
        primary_entry = {}
    primary_action = primary_entry.get("action") if isinstance(primary_entry, dict) else None
    action = str(primary_action or "phase-closeout-blocked")

    blockers = getattr(readiness, "blockers", [])
    blocker_preview = "; ".join(str(blocker) for blocker in blockers[:2]) if isinstance(blockers, list) else ""
    reason = f"Phase {phase_number} closeout is blocked"
    if blocker_preview:
        reason += f": {blocker_preview}"

    next_command = _next_command_from_lifecycle_payload(
        primary_entry,
        fallback_action=action,
        fallback_phase=phase_number,
        fallback_reason=reason,
        format_command=format_command,
    )
    if next_command is not None:
        command = next_command.command
        if next_command.action:
            action = next_command.action
    elif action == "verify-work":
        command = f"{format_command('verify-work')} {phase_number}"
    elif action == "resume-work":
        command = format_command("resume-work")
    elif action == "execute-phase":
        command = f"{format_command('execute-phase')} {phase_number}"
    else:
        command = _command_label_from_value(primary_entry)
        if command is None and isinstance(next_up, dict):
            command = _command_label_from_value(next_up.get("primary"))
        command = command or f"gpd phase complete {phase_number}"

    return _PhaseLifecycleSuggestion(
        action=action,
        priority=2,
        reason=reason,
        command=command,
        phase=phase_number,
        next_command=next_command,
    )


def _pending_phase_lifecycle_suggestion(
    cwd: Path,
    phase: _PhaseAnalysis,
    *,
    state: dict[str, object] | None,
    format_command,
) -> _PhaseLifecycleSuggestion | None | object:
    shared = _shared_phase_lifecycle_suggestion(cwd, phase, format_command=format_command)
    if shared is not _SHARED_LIFECYCLE_UNAVAILABLE:
        return shared

    if phase.verification_status != "passed":
        if phase.verification_status == "missing":
            reason = f"Phase {phase.number} is complete but unverified — run verification"
        else:
            reason = f"Phase {phase.number} verification is {phase.verification_status} — refresh verification"
        return _PhaseLifecycleSuggestion(
            action="verify-work",
            priority=2,
            command=f"{format_command('verify-work')} {phase.number}",
            reason=reason,
            phase=phase.number,
        )

    if _phase_is_closed_after_verification(cwd, phase.number, state=state):
        return None

    readiness = _closeout_readiness_safely(cwd, phase.number)
    if readiness is not None and getattr(readiness, "ready", False) is False:
        return _blocked_closeout_lifecycle_suggestion(
            readiness,
            phase_number=phase.number,
            format_command=format_command,
        )

    closeout_command = getattr(readiness, "closeout_command", None) if readiness is not None else None
    return _PhaseLifecycleSuggestion(
        action="phase-complete",
        priority=2,
        command=str(closeout_command or f"gpd phase complete {phase.number}"),
        reason=f"Phase {phase.number} passed verification but is not closed — run the local transition",
        phase=phase.number,
    )


def _scan_phases(cwd: Path) -> list[_PhaseAnalysis]:
    """Scan all phase directories and return analysis of each."""
    phases_dir = _planning_dir(cwd) / PHASES_DIR_NAME
    if not phases_dir.is_dir():
        return []

    try:
        dir_names = sorted(
            [d.name for d in phases_dir.iterdir() if d.is_dir()],
            key=_phase_sort_key,
        )
    except OSError:
        return []

    results: list[_PhaseAnalysis] = []
    for dir_name in dir_names:
        match = re.match(r"^(\d+(?:\.\d+)*)-?(.*)", dir_name)
        phase_number = match.group(1) if match else dir_name
        phase_name = match.group(2) if match and match.group(2) else None

        phase_path = phases_dir / dir_name
        try:
            files = [f.name for f in phase_path.iterdir() if f.is_file()]
        except OSError:
            continue

        plans = [f for f in files if _is_plan_file(f)]
        summaries = [f for f in files if _is_summary_file(f)]
        has_research = any(_is_research_file(f) for f in files)
        verification_status = _phase_verification_status(phase_path, files)
        has_verification = verification_status != "missing"

        plan_count = len(plans)
        summary_count = _matching_phase_artifact_count(plans, summaries)
        complete = _is_phase_complete(plan_count, summary_count)

        if complete:
            status = "complete"
        elif plan_count > 0:
            status = "in_progress"
        elif has_research:
            status = "researched"
        else:
            status = "pending"

        results.append(
            _PhaseAnalysis(
                number=phase_number,
                name=phase_name,
                status=status,
                plan_count=plan_count,
                summary_count=summary_count,
                incomplete_count=max(0, plan_count - summary_count),
                has_research=has_research,
                has_verification=has_verification,
                verification_status=verification_status,
            )
        )

    return results


def _phase_label(phase: _PhaseAnalysis) -> str:
    """Format a phase number + optional name for display."""
    if phase.name:
        return f"{phase.number} ({phase.name})"
    return phase.number


def _filter_unresolved(items: list[object]) -> list[object]:
    """Filter a list of strings/dicts keeping only unresolved entries."""
    result: list[object] = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict) and not item.get("resolved", False):
            result.append(item)
    return result


def _item_text(item: object, fallback_keys: tuple[str, ...] = ("text",)) -> str:
    """Extract display text from a string or dict item."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in fallback_keys:
            val = item.get(key)
            if val and isinstance(val, str):
                return val
    return "unnamed"


def _result_has_verification_evidence(result: dict[str, object]) -> bool:
    """Return whether a result has any verification signal."""
    return result.get("verified") is True or bool(result.get("verification_records"))


def _resolve_unverified_result_phase(
    unverified_results: list[dict[str, object]],
    phase_analysis: list[_PhaseAnalysis],
) -> str | None:
    """Return one runnable phase number for unverified results when unambiguous."""
    known_phases = {_phase_unpad(phase.number): phase.number for phase in phase_analysis}
    resolved_phases: list[str] = []
    for result in unverified_results:
        raw_phase = result.get("phase")
        if raw_phase is None:
            continue
        phase = known_phases.get(_phase_unpad(str(raw_phase)))
        if phase and phase not in resolved_phases:
            resolved_phases.append(phase)

    if len(resolved_phases) == 1:
        return resolved_phases[0]
    return None


def _count_pending_todos(cwd: Path) -> int:
    """Count .md files in GPD/todos/pending/."""
    pending_dir = _planning_dir(cwd) / TODOS_DIR_NAME / "pending"
    if not pending_dir.is_dir():
        return 0
    return sum(1 for f in pending_dir.iterdir() if f.is_file() and f.suffix == ".md")


def _has_literature_review(cwd: Path) -> bool:
    """Check if any literature review files exist."""
    lit_dir = _planning_dir(cwd) / LITERATURE_DIR_NAME
    if not lit_dir.is_dir():
        return False
    return any(f.name.endswith("-REVIEW.md") for f in lit_dir.iterdir() if f.is_file())


def _latest_referee_decision_recommendation(decision_path: Path | None) -> str | None:
    if decision_path is None:
        return None

    try:
        payload = json.loads(decision_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    recommendation = payload.get("final_recommendation")
    if not isinstance(recommendation, str):
        return None
    normalized = recommendation.strip().lower()
    return normalized or None


def _manuscript_has_submission_support_artifacts(cwd: Path, manuscript_entrypoint: Path | None) -> bool:
    if manuscript_entrypoint is None or manuscript_entrypoint.suffix != ".tex":
        return False

    artifacts = resolve_current_manuscript_artifacts(cwd, allow_markdown=True)
    if artifacts.manuscript_entrypoint is None:
        return False
    if artifacts.manuscript_entrypoint.resolve(strict=False) != manuscript_entrypoint.resolve(strict=False):
        return False
    if artifacts.artifact_manifest is None or artifacts.bibliography_audit is None:
        return False

    try:
        ArtifactManifest.model_validate(json.loads(artifacts.artifact_manifest.read_text(encoding="utf-8")))
        bibliography_audit = BibliographyAudit.model_validate(
            json.loads(artifacts.bibliography_audit.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, PydanticValidationError):
        return False
    if not (
        bibliography_audit.resolved_sources == bibliography_audit.total_sources
        and bibliography_audit.partial_sources == 0
        and bibliography_audit.unverified_sources == 0
        and bibliography_audit.failed_sources == 0
    ):
        return False

    if artifacts.reproducibility_manifest is None:
        return False
    if not _reproducibility_manifest_is_ready(artifacts.reproducibility_manifest):
        return False

    compiled_manuscript = locate_publication_artifact(
        manuscript_entrypoint,
        manuscript_entrypoint.with_suffix(".pdf").name,
    )
    return compiled_manuscript is not None and compiled_manuscript.exists()


def _reproducibility_manifest_is_ready(reproducibility_manifest: Path) -> bool:
    try:
        payload = json.loads(reproducibility_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    from gpd.core.reproducibility import validate_reproducibility_manifest

    validation = validate_reproducibility_manifest(payload)
    return validation.valid and validation.ready_for_review and not validation.warnings


def _current_publication_blockers(cwd: Path) -> list[str]:
    state = _load_state_json_safe(cwd) or {}
    raw_blockers = state.get("blockers") or []
    blockers: list[str] = []
    for item in _filter_unresolved(raw_blockers):
        text = _item_text(item, ("text", "description")).strip()
        if text:
            blockers.append(text)
    return blockers


def _publication_review_package_allows_submission(cwd: Path, manuscript_entrypoint: Path | None) -> bool:
    if manuscript_entrypoint is None or manuscript_entrypoint.suffix != ".tex":
        return False

    latest_review_artifacts = resolve_latest_publication_review_artifacts(
        cwd,
        manuscript_entrypoint=manuscript_entrypoint,
    )
    if latest_review_artifacts is None:
        return False
    response_freshness = resolve_publication_response_freshness(
        cwd,
        manuscript_entrypoint=manuscript_entrypoint,
        review_artifacts=latest_review_artifacts,
    )
    if response_freshness.requires_fresh_review:
        return False

    ledger_path = latest_review_artifacts.review_ledger
    decision_path = latest_review_artifacts.referee_decision
    if ledger_path is None or decision_path is None:
        return False

    try:
        from gpd.core.referee_policy import evaluate_referee_decision
        from gpd.mcp.paper.review_artifacts import read_referee_decision, read_review_ledger

        review_ledger = read_review_ledger(ledger_path)
        decision = read_referee_decision(decision_path)
        report = evaluate_referee_decision(
            decision,
            strict=True,
            require_explicit_inputs=True,
            review_ledger=review_ledger,
            project_root=cwd,
            expected_manuscript_sha256=compute_sha256(manuscript_entrypoint),
        )
    except (OSError, json.JSONDecodeError, PydanticValidationError):
        return False
    except ValueError:
        return False
    if not report.valid:
        return False
    if decision.final_recommendation not in {"accept", "minor_revision"}:
        return False
    return not decision.blocking_issue_ids and _manuscript_has_submission_support_artifacts(cwd, manuscript_entrypoint)


def _conventions_are_ready(cwd: Path) -> bool:
    state = _load_state_json_safe(cwd) or {}
    convention_lock = state.get("convention_lock")
    if not isinstance(convention_lock, dict):
        return False
    from gpd.core.conventions import is_bogus_value

    return all(convention_lock.get(key) and not is_bogus_value(convention_lock.get(key)) for key in CORE_CONVENTIONS)


def _missing_conventions_from_state(state: dict[str, object]) -> tuple[str, ...]:
    """Return canonical missing convention keys from a loaded state payload."""
    convention_lock = state.get("convention_lock")
    if not isinstance(convention_lock, dict):
        return ()

    try:
        lock = ConventionLock.model_validate(convention_lock)
    except PydanticValidationError:
        return ()

    from gpd.core.conventions import convention_check

    return tuple(entry.key for entry in convention_check(lock).missing)


def _format_missing_conventions_reason(missing: tuple[str, ...]) -> str:
    """Format a readable missing-convention recommendation without truncating the count."""
    from gpd.core.conventions import CONVENTION_LABELS

    labels = [CONVENTION_LABELS.get(key, key.replace("_", " ").title()) for key in missing]
    preview_count = min(4, len(labels))
    preview = ", ".join(labels[:preview_count])
    if len(labels) > preview_count:
        preview += f", and {len(labels) - preview_count} more"
    plural = "field" if len(labels) == 1 else "fields"
    return f"{len(labels)} convention {plural} missing: {preview} — define before calculations"


def _is_bounded_external_write_paper_lane(cwd: Path, manuscript_entrypoint: Path | None) -> bool:
    """Return whether the active managed manuscript is the standalone external-authoring lane."""

    if manuscript_entrypoint is None or _path_exists(cwd, f"{PLANNING_DIR_NAME}/{PROJECT_FILENAME}"):
        return False

    publication_subject = resolve_current_publication_subject(cwd, allow_markdown=True)
    if not publication_subject.resolved or publication_subject.manuscript_entrypoint is None:
        return False
    return (
        publication_subject.publication_lane_kind == "managed_publication_manuscript"
        and publication_subject.manuscript_entrypoint.resolve(strict=False)
        == manuscript_entrypoint.resolve(strict=False)
    )


def _publication_submission_is_strictly_ready(cwd: Path, manuscript_entrypoint: Path | None) -> bool:
    if manuscript_entrypoint is None:
        return False
    if _is_bounded_external_write_paper_lane(cwd, manuscript_entrypoint):
        return False
    if _current_publication_blockers(cwd):
        return False
    if not _conventions_are_ready(cwd):
        return False
    if not _publication_review_package_allows_submission(cwd, manuscript_entrypoint):
        return False
    return _manuscript_submission_proof_review_is_fresh(cwd, manuscript_entrypoint)


def _manuscript_submission_proof_review_is_fresh(
    cwd: Path,
    manuscript_entrypoint: Path | None,
) -> bool:
    if manuscript_entrypoint is None:
        return True

    if not manuscript_requires_theorem_bearing_review(cwd, manuscript_entrypoint):
        return True

    proof_review_status = resolve_manuscript_proof_review_status(cwd, manuscript_entrypoint)
    return proof_review_status.can_rely_on_prior_review and proof_review_status.state == "fresh"


def _has_referee_report(cwd: Path) -> bool:
    """Check for the active manuscript's referee report bundle."""

    manuscript_resolution = resolve_current_manuscript_resolution(cwd, allow_markdown=True)
    manuscript_entrypoint = (
        manuscript_resolution.manuscript_entrypoint if manuscript_resolution.status == "resolved" else None
    )
    if manuscript_entrypoint is None:
        return False

    publication_root, review_dir = publication_lineage_roots(cwd, manuscript_entrypoint)
    review_artifacts = resolve_latest_publication_review_artifacts(
        cwd,
        manuscript_entrypoint=manuscript_entrypoint,
    )
    if review_artifacts is None or review_artifacts.referee_report_md is None:
        return any(path.is_file() for path in publication_root.glob("REFEREE-REPORT*.md")) or any(
            path.is_file() for path in review_dir.glob("REFEREE-REPORT*.md")
        )

    response_artifacts = resolve_latest_publication_response_artifacts(
        cwd,
        review_artifacts=review_artifacts,
    )
    if (
        response_artifacts is not None
        and response_artifacts.complete
        and _latest_referee_decision_recommendation(review_artifacts.referee_decision) == "accept"
    ):
        return False
    return True


def _has_adaptive_lock_signal(cwd: Path) -> bool:
    """Return whether project artifacts show decisive evidence or an explicit approach lock."""

    phases_dir = _planning_dir(cwd) / PHASES_DIR_NAME
    if not phases_dir.is_dir():
        return False

    explicit_lock_markers = (
        "approach_lock: true",
        "approach_locked: true",
        "approach_validated: true",
    )
    decisive_pass_re = re.compile(r"subject_role:\s*decisive[\s\S]{0,400}?verdict:\s*pass\b", re.IGNORECASE)
    decisive_failure_re = re.compile(
        r"subject_role:\s*decisive[\s\S]{0,400}?verdict:\s*(?:tension|fail)\b", re.IGNORECASE
    )
    passed_status_re = re.compile(r"^status:\s*passed\b", re.IGNORECASE | re.MULTILINE)
    for path in sorted(phases_dir.rglob("*.md")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.casefold()
        if any(marker in lowered for marker in explicit_lock_markers):
            return True
        if (
            "comparison_verdicts:" in lowered
            and passed_status_re.search(text)
            and decisive_pass_re.search(text)
            and not decisive_failure_re.search(text)
        ):
            return True
    return False


# ─── Priority Adjustments ────────────────────────────────────────────────────


def _apply_mode_adjustments(
    suggestions: list[_MutableRecommendation],
    config: dict[str, object],
    *,
    adaptive_approach_locked: bool,
) -> None:
    """Adjust priorities based on research_mode and autonomy settings."""
    research_mode = config.get("research_mode", "balanced")
    autonomy = config.get("autonomy", "supervised")

    for s in suggestions:
        # Research mode adjustments
        if research_mode == "explore":
            if s.action == "discuss-phase":
                s.priority = max(1, s.priority - 2)
            if s.action == "address-questions":
                s.priority = max(1, s.priority - 1)
        elif research_mode == "exploit":
            if s.action == "execute-phase":
                s.priority = max(1, s.priority - 1)
            if s.action == "verify-work":
                s.priority = max(1, s.priority - 1)
        elif research_mode == "adaptive":
            if adaptive_approach_locked:
                if s.action == "execute-phase":
                    s.priority = max(1, s.priority - 1)
                if s.action == "verify-work":
                    s.priority = max(1, s.priority - 1)
            else:
                if s.action == "discuss-phase":
                    s.priority = max(1, s.priority - 1)

        # Autonomy adjustments
        if autonomy == "supervised" and s.action in ("execute-phase", "continue-calculations"):
            s.priority += 1
        if autonomy == "yolo" and s.action == "execute-phase":
            s.priority = max(1, s.priority - 1)


# ─── Main Entry Point ────────────────────────────────────────────────────────


def suggest_next(cwd: Path, *, limit: int = 5) -> SuggestResult:
    """Analyze project state and return prioritized next-action recommendations.

    Scans the project for: paused work, blockers, phase status, unverified results,
    open questions, active calculations, pending todos, convention gaps, paper pipeline
    state, and returns up to ``limit`` prioritized recommendations.

    Args:
        cwd: Project root directory.
        limit: Maximum number of suggestions to return.

    Returns:
        SuggestResult with prioritized suggestions and project context.
    """
    suggestions: list[_MutableRecommendation] = []
    ctx_kwargs: dict[str, object] = {}

    def format_command(action):
        return _format_command(action, cwd=cwd)

    # ── 0. Check project existence ──────────────────────────────────────
    project_exists = _path_exists(cwd, f"{PLANNING_DIR_NAME}/{PROJECT_FILENAME}")
    roadmap_exists = _path_exists(cwd, f"{PLANNING_DIR_NAME}/{ROADMAP_FILENAME}")
    manuscript_resolution = resolve_current_manuscript_resolution(cwd, allow_markdown=True)
    manuscript_entrypoint = (
        manuscript_resolution.manuscript_entrypoint if manuscript_resolution.status == "resolved" else None
    )
    manuscript_state_is_blocked = manuscript_resolution.status in {"ambiguous", "invalid"}

    if not project_exists and manuscript_entrypoint is None:
        reentry = resolve_project_reentry(cwd)
        if reentry.has_recoverable_current_workspace:
            only = _build_recommendation(
                action="resume-work",
                priority=1,
                command=format_command("resume-work"),
                reason="Recoverable GPD state found in this workspace — resume or reconcile it before starting fresh",
            )
            return SuggestResult(
                suggestions=[only],
                total_suggestions=1,
                suggestion_count=1,
                top_action=only,
                context=SuggestContext(),
            )
        recoverable_recent = [
            candidate
            for candidate in reentry.candidates
            if candidate.source == "recent_project" and candidate.recoverable
        ]
        if recoverable_recent:
            count = len(recoverable_recent)
            only = _build_recommendation(
                action="resume-recent",
                priority=1,
                command=recovery_cross_workspace_command(),
                reason=(
                    f"No active project found here, but {count} recent recoverable project"
                    f"{'' if count == 1 else 's'} are available — choose one, reopen it, then run "
                    f"{canonical_command_label('resume-work')}"
                ),
            )
            return SuggestResult(
                suggestions=[only],
                total_suggestions=1,
                suggestion_count=1,
                top_action=only,
                context=SuggestContext(),
            )
        only = _build_recommendation(
            action="new-project",
            priority=1,
            command=format_command("new-project"),
            reason="No PROJECT.md found — initialize a new research project first",
        )
        return SuggestResult(
            suggestions=[only],
            total_suggestions=1,
            suggestion_count=1,
            top_action=only,
            context=SuggestContext(),
        )

    # ── 1. Load state + config ──────────────────────────────────────────
    state = _load_state_json_safe(cwd)
    config = _load_config(cwd)

    if state:
        position = state.get("position") or {}
        _raw_phase = position.get("current_phase")
        ctx_kwargs["current_phase"] = str(_raw_phase) if _raw_phase is not None else None
        ctx_kwargs["status"] = position.get("status")
        ctx_kwargs["progress_percent"] = position.get("progress_percent", 0)
        ctx_kwargs["paused_at"] = position.get("paused_at")

    # ── 2. Check for paused work (highest priority) ─────────────────────
    if state:
        position = state.get("position") or {}
        if position.get("paused_at") or str(position.get("status", "")).strip().lower() == "paused":
            paused_at = position.get("paused_at", "")
            reason = "Work was paused"
            if paused_at:
                reason += f" at {paused_at}"
            reason += " — resume to restore context"
            suggestions.append(
                _MutableRecommendation(
                    action="resume",
                    priority=1,
                    command=format_command("resume-work"),
                    reason=reason,
                )
            )

    # ── 3. Check for blockers ───────────────────────────────────────────
    if state:
        raw_blockers = state.get("blockers") or []
        blockers = _filter_unresolved(raw_blockers)
        if blockers:
            ctx_kwargs["active_blockers"] = len(blockers)
            texts = [_item_text(b, ("text", "description")) for b in blockers[:3]]
            suggestions.append(
                _MutableRecommendation(
                    action="resolve-blockers",
                    priority=2,
                    command=format_command("debug"),
                    reason=f"{len(blockers)} unresolved blocker(s): {'; '.join(texts)}",
                )
            )

    # ── 4. Scan phases ──────────────────────────────────────────────────
    phase_analysis = _scan_phases(cwd)
    current_phase: _PhaseAnalysis | None = None
    next_unplanned: _PhaseAnalysis | None = None
    next_pending: _PhaseAnalysis | None = None

    for pa in phase_analysis:
        if not current_phase and pa.status == "in_progress":
            current_phase = pa
        if not next_unplanned and pa.status == "researched":
            next_unplanned = pa
        if not next_pending and pa.status == "pending":
            next_pending = pa

    milestone_snapshot = _milestone_completion_snapshot(cwd)
    all_complete = milestone_snapshot.all_phases_complete
    ctx_kwargs["phase_count"] = milestone_snapshot.phase_count
    ctx_kwargs["completed_phases"] = milestone_snapshot.completed_phases

    # ── 5. Phase-based suggestions ──────────────────────────────────────

    # 5a. Execute incomplete plans in current phase
    if current_phase:
        suggestions.append(
            _MutableRecommendation(
                action="execute-phase",
                priority=3,
                command=f"{format_command('execute-phase')} {current_phase.number}",
                reason=(
                    f"Phase {_phase_label(current_phase)} has "
                    f"{current_phase.incomplete_count} incomplete plan(s) — continue execution"
                ),
                phase=current_phase.number,
            )
        )

    # 5b. Complete phases must pass lifecycle gates before downstream routing.
    lifecycle_suggestion: _PhaseLifecycleSuggestion | None = None
    lifecycle_blocks_downstream = False
    for phase in phase_analysis:
        if phase.status != "complete":
            continue
        pending_lifecycle = _pending_phase_lifecycle_suggestion(
            cwd,
            phase,
            state=state,
            format_command=format_command,
        )
        if isinstance(pending_lifecycle, _PhaseLifecycleSuggestion) and pending_lifecycle.action in {
            "discuss-phase",
            "execute-phase",
            "plan-phase",
        }:
            target_phase = _phase_normalize(pending_lifecycle.phase)
            if any(_phase_normalize(candidate.number) == target_phase and candidate.status == "complete"
                   for candidate in phase_analysis):
                continue
        if pending_lifecycle is _SHARED_LIFECYCLE_BLOCKS_WITHOUT_SUGGESTION:
            lifecycle_blocks_downstream = True
            break
        if pending_lifecycle is not None:
            lifecycle_suggestion = pending_lifecycle
            lifecycle_blocks_downstream = True
            break
    if lifecycle_blocks_downstream and lifecycle_suggestion is not None:
        blocking_phase = _phase_normalize(lifecycle_suggestion.phase)
        suggestions = [
            suggestion
            for suggestion in suggestions
            if not (
                suggestion.action in _PHASE_RUNTIME_ACTIONS
                and suggestion.phase is not None
                and _compare_phase_numbers(_phase_normalize(suggestion.phase), blocking_phase) > 0
            )
        ]
    if lifecycle_suggestion is not None:
        suggestions.append(
            _MutableRecommendation(
                action=lifecycle_suggestion.action,
                priority=lifecycle_suggestion.priority,
                command=lifecycle_suggestion.command,
                reason=lifecycle_suggestion.reason,
                phase=lifecycle_suggestion.phase,
                next_command=lifecycle_suggestion.next_command,
            )
        )

    # 5c. Plan a researched phase
    if next_unplanned and not lifecycle_blocks_downstream:
        suggestions.append(
            _MutableRecommendation(
                action="plan-phase",
                priority=5,
                command=f"{format_command('plan-phase')} {next_unplanned.number}",
                reason=(f"Phase {_phase_label(next_unplanned)} has research but no plans — create execution plan"),
                phase=next_unplanned.number,
            )
        )

    # 5d. Discover/research next pending phase
    if next_pending and not lifecycle_blocks_downstream:
        suggestions.append(
            _MutableRecommendation(
                action="discuss-phase",
                priority=6,
                command=f"{format_command('discuss-phase')} {next_pending.number}",
                reason=f"Phase {_phase_label(next_pending)} is pending — start with phase discussion",
                phase=next_pending.number,
            )
        )

    # ── 6. Unverified results ───────────────────────────────────────────
    if state:
        raw_results = state.get("intermediate_results") or []
        unverified = [r for r in raw_results if isinstance(r, dict) and not _result_has_verification_evidence(r)]
        if unverified:
            ctx_kwargs["unverified_results"] = len(unverified)
            ids = [r.get("id", "unnamed") for r in unverified[:3]]
            suffix = "..." if len(unverified) > 3 else ""
            verify_phase = _resolve_unverified_result_phase(unverified, phase_analysis)
            if verify_phase is not None:
                suggestions.append(
                    _MutableRecommendation(
                        action="verify-results",
                        priority=5,
                        command=f"{format_command('verify-work')} {verify_phase}",
                        reason=f"{len(unverified)} unverified result(s): {', '.join(str(i) for i in ids)}{suffix}",
                        phase=verify_phase,
                    )
                )

    # ── 7. Open questions ───────────────────────────────────────────────
    if state:
        raw_questions = state.get("open_questions") or []
        open_questions = _filter_unresolved(raw_questions)
        if open_questions:
            ctx_kwargs["open_questions"] = len(open_questions)
            texts = [_item_text(q, ("text", "question")) for q in open_questions[:2]]
            suggestions.append(
                _MutableRecommendation(
                    action="address-questions",
                    priority=7,
                    command=format_command("check-todos"),
                    reason=f"{len(open_questions)} open question(s) — {'; '.join(texts)}",
                )
            )

    # ── 8. Active calculations ──────────────────────────────────────────
    if state:
        raw_calcs = state.get("active_calculations") or []
        active_calcs = [
            c for c in raw_calcs if isinstance(c, str) or (isinstance(c, dict) and not c.get("completed", False))
        ]
        if active_calcs:
            ctx_kwargs["active_calculations"] = len(active_calcs)
            suggestions.append(
                _MutableRecommendation(
                    action="continue-calculations",
                    priority=4,
                    command=format_command("progress"),
                    reason=f"{len(active_calcs)} active calculation(s) in progress — check status",
                )
            )

    # ── 9. Pending todos ────────────────────────────────────────────────
    todo_count = _count_pending_todos(cwd)
    if todo_count > 0:
        ctx_kwargs["pending_todos"] = todo_count
        suggestions.append(
            _MutableRecommendation(
                action="review-todos",
                priority=8,
                command=format_command("check-todos"),
                reason=f"{todo_count} pending todo(s) — review and prioritize",
            )
        )

    # ── 10. Convention gaps ─────────────────────────────────────────────
    if state and not any(s.action == "resume" for s in suggestions):
        missing = _missing_conventions_from_state(state)
        if missing:
            ctx_kwargs["missing_conventions"] = missing
            suggestions.append(
                _MutableRecommendation(
                    action="set-conventions",
                    priority=6,
                    command=format_command("validate-conventions"),
                    reason=_format_missing_conventions_reason(missing),
                )
            )

    # ── 11. No roadmap yet ──────────────────────────────────────────────
    if not roadmap_exists and not lifecycle_blocks_downstream:
        suggestions.append(
            _MutableRecommendation(
                action="new-milestone",
                priority=2,
                command=format_command("new-milestone"),
                reason="No ROADMAP.md found — create milestone roadmap",
            )
        )

    # ── 12. All phases complete → milestone audit ───────────────────────
    all_complete_verified = (
        all_complete and phase_analysis and all(phase.verification_status == "passed" for phase in phase_analysis)
    )
    if all_complete_verified and not lifecycle_blocks_downstream:
        suggestions.append(
            _MutableRecommendation(
                action="audit-milestone",
                priority=3,
                command=format_command("audit-milestone"),
                reason=f"All {len(phase_analysis)} phases complete — audit milestone for gaps",
            )
        )

    # ── 13. Paper pipeline awareness ────────────────────────────────────
    has_paper_flag = manuscript_entrypoint is not None
    has_latex_manuscript = manuscript_entrypoint is not None and manuscript_entrypoint.suffix == ".tex"
    has_lit_review = _has_literature_review(cwd)
    has_referee = _has_referee_report(cwd)
    bounded_external_write_paper_lane = _is_bounded_external_write_paper_lane(cwd, manuscript_entrypoint)
    submission_ready_review = _publication_submission_is_strictly_ready(cwd, manuscript_entrypoint)

    ctx_kwargs["has_paper"] = has_paper_flag
    ctx_kwargs["has_literature_review"] = has_lit_review
    ctx_kwargs["has_referee_report"] = has_referee

    # 13a. All phases complete + verified → suggest paper writing
    if (
        all_complete
        and phase_analysis
        and not has_paper_flag
        and not manuscript_state_is_blocked
        and not lifecycle_blocks_downstream
    ):
        if all_complete_verified:
            suggestions.append(
                _MutableRecommendation(
                    action="write-paper",
                    priority=3,
                    command=format_command("write-paper"),
                    reason=(f"All {len(phase_analysis)} phases complete and verified — ready to write paper"),
                )
            )
        if not has_lit_review:
            suggestions.append(
                _MutableRecommendation(
                    action="literature-review",
                    priority=4,
                    command=format_command("literature-review"),
                    reason=(
                        "No literature review found — recommended before paper writing for comprehensive citations"
                    ),
                )
            )

    # 13b. Paper exists → suggest submission or referee response
    if has_paper_flag and not lifecycle_blocks_downstream:
        if submission_ready_review and has_latex_manuscript:
            suggestions.append(
                _MutableRecommendation(
                    action="arxiv-submission",
                    priority=3,
                    command=format_command("arxiv-submission"),
                    reason=(
                        "Latest peer-review decision clears submission packaging — prepare the LaTeX manuscript for arXiv"
                    ),
                )
            )
        elif has_referee:
            suggestions.append(
                _MutableRecommendation(
                    action="respond-to-referees",
                    priority=2,
                    command=format_command("respond-to-referees"),
                    reason="Referee report exists — respond to referee comments and revise manuscript",
                )
            )
        else:
            suggestions.append(
                _MutableRecommendation(
                    action="peer-review",
                    priority=4,
                    command=format_command("peer-review"),
                    reason=(
                        "Managed external-authoring manuscript exists — route to standalone peer review next"
                        if bounded_external_write_paper_lane
                        else "Paper draft exists — run standalone peer review before submission packaging"
                    ),
                )
            )
    # ── 14. No phases at all → need to plan ─────────────────────────────
    if not phase_analysis and roadmap_exists:
        suggestions.append(
            _MutableRecommendation(
                action="plan-first-phase",
                priority=3,
                command=f"{format_command('discuss-phase')} 1",
                reason="Roadmap exists but no phases created — start with phase 1",
            )
        )

    # ── Mode-aware priority adjustments ─────────────────────────────────
    autonomy_val = str(config.get("autonomy", "supervised"))
    research_mode_val = str(config.get("research_mode", "balanced"))
    ctx_kwargs["autonomy"] = autonomy_val
    ctx_kwargs["research_mode"] = research_mode_val
    adaptive_approach_locked = _has_adaptive_lock_signal(cwd) if research_mode_val == "adaptive" else False
    ctx_kwargs["adaptive_approach_locked"] = adaptive_approach_locked
    _apply_mode_adjustments(suggestions, config, adaptive_approach_locked=adaptive_approach_locked)

    # ── Sort by priority ────────────────────────────────────────────────
    suggestions.sort(key=lambda s: s.priority)

    # ── Limit output ────────────────────────────────────────────────────
    limited = suggestions[:limit]
    frozen = [s.freeze() for s in limited]

    context = SuggestContext(**{k: v for k, v in ctx_kwargs.items() if v is not None})

    return SuggestResult(
        suggestions=frozen,
        total_suggestions=len(suggestions),
        suggestion_count=len(frozen),
        top_action=frozen[0] if frozen else None,
        context=context,
    )


def _load_state_json_safe(cwd: Path) -> dict[str, object] | None:
    """Load visible state without mutating local recovery/lock artifacts.

    Tries the read-only state loader if available; falls back to direct read.
    """
    try:
        from gpd.core.state import load_state_json_readonly

        return load_state_json_readonly(cwd)
    except (FileNotFoundError, OSError, ImportError):
        logger.debug("suggest: state load failed", exc_info=True)

    # Fallback: direct JSON read
    state_path = cwd / PLANNING_DIR_NAME / STATE_JSON_FILENAME
    try:
        raw = state_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
        logger.debug("suggest: state load failed", exc_info=True)
    return None
