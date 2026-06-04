"""Shared resume-surface normalization helpers.

The public resume surface is canonical-only: canonical continuation fields stay
at the top level and backend-only marker keys are stripped before payloads
leave the backend. This module centralizes that projection so ``init_resume()``,
CLI raw output, and other public surfaces do not each reinvent resume
normalization.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

__all__ = [
    "RESUME_SURFACE_SCHEMA_VERSION",
    "RESUME_BACKEND_ONLY_FIELDS",
    "RESUME_CANDIDATE_KIND_BOUNDED_SEGMENT",
    "RESUME_CANDIDATE_KIND_CONTINUITY_HANDOFF",
    "RESUME_CANDIDATE_KIND_INTERRUPTED_AGENT",
    "RESUME_CANDIDATE_ORIGIN_CONTINUATION_BOUNDED_SEGMENT",
    "RESUME_CANDIDATE_ORIGIN_CONTINUATION_HANDOFF",
    "RESUME_CANDIDATE_ORIGIN_INTERRUPTED_AGENT_MARKER",
    "RESUME_PRESENTATION_LANE_BLOCKER_NEXT_COMMAND",
    "RESUME_PRESENTATION_LANE_PRIMARY_RESUME_TARGET",
    "RESUME_PRESENTATION_LANE_SELECTED_PROJECT",
    "build_resume_presentation_lanes",
    "build_resume_candidate",
    "build_resume_segment_candidate",
    "build_resume_static_candidate",
    "canonicalize_resume_public_payload",
    "lookup_resume_surface_list",
    "lookup_resume_surface_mapping",
    "lookup_resume_surface_text",
    "lookup_resume_surface_value",
    "resume_candidate_kind",
    "resume_candidate_origin",
    "resume_candidate_kind_from_source",
    "resume_candidate_origin_from_source",
    "resume_origin_for_bounded_segment",
    "resume_origin_for_handoff",
    "resume_origin_for_interrupted_agent",
    "resume_payload_has_local_recovery_target",
]

RESUME_SURFACE_SCHEMA_VERSION = 1

RESUME_BACKEND_ONLY_FIELDS: tuple[str, ...] = (
    "active_execution_segment",
    "current_execution",
    "current_execution_resume_file",
    "execution_resume_file",
    "execution_resume_file_source",
    "missing_handoff_resume_file",
    "recorded_handoff_resume_file",
    "resume_mode",
    "resume_surface",
    "segment_candidates",
    "handoff_resume_file",
)

RESUME_CANDIDATE_KIND_BOUNDED_SEGMENT = "bounded_segment"
RESUME_CANDIDATE_KIND_CONTINUITY_HANDOFF = "continuity_handoff"
RESUME_CANDIDATE_KIND_INTERRUPTED_AGENT = "interrupted_agent"

RESUME_CANDIDATE_ORIGIN_CONTINUATION_BOUNDED_SEGMENT = "continuation.bounded_segment"
RESUME_CANDIDATE_ORIGIN_CONTINUATION_HANDOFF = "continuation.handoff"
RESUME_CANDIDATE_ORIGIN_INTERRUPTED_AGENT_MARKER = "interrupted_agent_marker"

RESUME_PRESENTATION_LANE_SELECTED_PROJECT = "selected_project"
RESUME_PRESENTATION_LANE_PRIMARY_RESUME_TARGET = "primary_resume_target"
RESUME_PRESENTATION_LANE_BLOCKER_NEXT_COMMAND = "blocker_next_command"

_RESUME_CANDIDATE_SEGMENT_FIELDS: tuple[str, ...] = (
    "phase",
    "plan",
    "segment_id",
    "resume_file",
    "checkpoint_reason",
    "first_result_gate_pending",
    "pre_fanout_review_pending",
    "pre_fanout_review_cleared",
    "skeptical_requestioning_required",
    "skeptical_requestioning_summary",
    "weakest_unchecked_anchor",
    "disconfirming_observation",
    "transition_id",
    "last_result_id",
    "downstream_locked",
    "waiting_reason",
    "blocked_reason",
    "last_result_label",
    "updated_at",
)


def _lookup_resume_surface_field(
    payload: Mapping[str, object] | None,
    key: str,
    *,
    accept: Callable[[object], object | None],
) -> object | None:
    if isinstance(payload, Mapping) and key in payload:
        accepted = accept(payload[key])
        if accepted is not None:
            return accepted
    return None


def lookup_resume_surface_text(
    payload: Mapping[str, object] | None,
    key: str,
) -> str | None:
    """Return the first non-blank text value for one canonical field."""
    return _lookup_resume_surface_field(
        payload,
        key,
        accept=lambda value: value if isinstance(value, str) and value.strip() else None,
    )


def lookup_resume_surface_value(
    payload: Mapping[str, object] | None,
    key: str,
) -> object | None:
    """Return the first non-empty value for one canonical field."""
    return _lookup_resume_surface_field(
        payload,
        key,
        accept=lambda value: None if value is None or (isinstance(value, str) and not value.strip()) else value,
    )


def lookup_resume_surface_mapping(
    payload: Mapping[str, object] | None,
    key: str,
) -> dict[str, object] | None:
    """Return the first mapping value for one canonical field."""
    result = _lookup_resume_surface_field(
        payload,
        key,
        accept=lambda value: dict(value) if isinstance(value, Mapping) else None,
    )
    return result if isinstance(result, dict) else None


def lookup_resume_surface_list(
    payload: Mapping[str, object] | None,
    key: str,
) -> list[object] | None:
    """Return the first list value for one canonical field."""
    result = _lookup_resume_surface_field(
        payload,
        key,
        accept=lambda value: list(value) if isinstance(value, list) else None,
    )
    return result if isinstance(result, list) else None


def build_resume_segment_candidate(
    segment: Mapping[str, object],
    *,
    source: str = "current_execution",
) -> dict[str, object]:
    """Return the raw segment candidate payload used by resume synthesis."""
    candidate = {
        "source": source,
        "status": segment.get("segment_status"),
    }
    for field in _RESUME_CANDIDATE_SEGMENT_FIELDS:
        candidate[field] = segment.get(field)
    return candidate


def build_resume_static_candidate(
    *,
    source: str,
    status: object,
    resume_file: str | None = None,
    agent_id: str | None = None,
    resumable: bool | None = None,
    advisory: bool | None = None,
) -> dict[str, object]:
    """Return the raw non-segment candidate payload used by resume synthesis."""
    candidate: dict[str, object] = {
        "source": source,
        "status": status,
    }
    if resume_file is not None:
        candidate["resume_file"] = resume_file
    if agent_id is not None:
        candidate["agent_id"] = agent_id
    if resumable is not None:
        candidate["resumable"] = resumable
    if advisory is not None:
        candidate["advisory"] = advisory
    return candidate


def build_resume_candidate(
    candidate: Mapping[str, object],
    *,
    kind: str,
    origin: str,
    resume_pointer: str | None = None,
) -> dict[str, object]:
    """Return the canonical candidate shape for public resume surfaces."""
    payload = dict(candidate)
    payload.pop("source", None)
    payload["kind"] = kind
    payload["origin"] = _canonical_resume_origin(origin)
    payload["resume_pointer"] = resume_pointer
    return payload


def _canonical_resume_origin(origin: str | None) -> str | None:
    normalized = (origin or "").strip()
    if not normalized:
        return None
    if normalized == "current_execution":
        return RESUME_CANDIDATE_ORIGIN_CONTINUATION_BOUNDED_SEGMENT
    if normalized == "handoff_resume_file":
        return RESUME_CANDIDATE_ORIGIN_CONTINUATION_HANDOFF
    return normalized


def resume_candidate_kind_from_source(source: str | None) -> str | None:
    """Map a raw resume source label to the canonical candidate kind."""
    normalized = (source or "").strip()
    if normalized == "current_execution":
        return RESUME_CANDIDATE_KIND_BOUNDED_SEGMENT
    if normalized == "handoff_resume_file":
        return RESUME_CANDIDATE_KIND_CONTINUITY_HANDOFF
    if normalized == "interrupted_agent":
        return RESUME_CANDIDATE_KIND_INTERRUPTED_AGENT
    return None


def resume_candidate_kind(candidate: Mapping[str, object]) -> str | None:
    """Return the canonical family for one resume candidate."""
    kind = candidate.get("kind")
    if isinstance(kind, str):
        normalized = kind.strip()
        if normalized in {"handoff", "continuity_handoff", "missing_handoff", "missing_continuity_handoff"}:
            return RESUME_CANDIDATE_KIND_CONTINUITY_HANDOFF
        if normalized in {
            RESUME_CANDIDATE_KIND_BOUNDED_SEGMENT,
            RESUME_CANDIDATE_KIND_INTERRUPTED_AGENT,
        }:
            return normalized

    origin = resume_candidate_origin(candidate)
    if origin == RESUME_CANDIDATE_ORIGIN_INTERRUPTED_AGENT_MARKER:
        return RESUME_CANDIDATE_KIND_INTERRUPTED_AGENT
    if origin in {
        RESUME_CANDIDATE_ORIGIN_CONTINUATION_BOUNDED_SEGMENT,
    }:
        return RESUME_CANDIDATE_KIND_BOUNDED_SEGMENT
    if origin in {
        RESUME_CANDIDATE_ORIGIN_CONTINUATION_HANDOFF,
    }:
        return RESUME_CANDIDATE_KIND_CONTINUITY_HANDOFF

    source = candidate.get("source")
    return resume_candidate_kind_from_source(str(source).strip() if isinstance(source, str) else None)


def resume_origin_for_bounded_segment() -> str:
    """Return the canonical origin for a bounded execution candidate."""
    return RESUME_CANDIDATE_ORIGIN_CONTINUATION_BOUNDED_SEGMENT


def resume_origin_for_handoff() -> str:
    """Return the canonical origin for a recorded handoff candidate."""
    return RESUME_CANDIDATE_ORIGIN_CONTINUATION_HANDOFF


def resume_origin_for_interrupted_agent() -> str:
    """Return the canonical origin for an interrupted-agent candidate."""
    return RESUME_CANDIDATE_ORIGIN_INTERRUPTED_AGENT_MARKER


def resume_candidate_origin_from_source(
    source: str | None,
) -> str | None:
    """Map a raw candidate source label to a canonical origin string."""
    normalized = (source or "").strip()
    if normalized == "current_execution":
        return RESUME_CANDIDATE_ORIGIN_CONTINUATION_BOUNDED_SEGMENT
    if normalized == "handoff_resume_file":
        return RESUME_CANDIDATE_ORIGIN_CONTINUATION_HANDOFF
    if normalized == "interrupted_agent":
        return resume_origin_for_interrupted_agent()
    return None


def resume_candidate_origin(candidate: Mapping[str, object]) -> str | None:
    """Return the canonical origin for one resume candidate."""
    origin = candidate.get("origin")
    if isinstance(origin, str) and origin.strip():
        return _canonical_resume_origin(origin)
    source = candidate.get("source")
    return resume_candidate_origin_from_source(str(source).strip() if isinstance(source, str) else None)


def _resume_candidate_exposes_local_target(candidate: Mapping[str, object]) -> bool:
    kind = resume_candidate_kind(candidate)
    status = str(candidate.get("status") or "").strip()
    if status == "missing":
        return False
    if kind == RESUME_CANDIDATE_KIND_INTERRUPTED_AGENT:
        agent_id = candidate.get("agent_id")
        return isinstance(agent_id, str) and bool(agent_id.strip())
    if kind not in {
        RESUME_CANDIDATE_KIND_BOUNDED_SEGMENT,
        RESUME_CANDIDATE_KIND_CONTINUITY_HANDOFF,
    }:
        return False
    resume_file = candidate.get("resume_file")
    return isinstance(resume_file, str) and bool(resume_file.strip())


def resume_payload_has_local_recovery_target(payload: Mapping[str, object] | None) -> bool:
    """Return whether one resume payload already exposes a local recovery target."""
    if not isinstance(payload, Mapping):
        return False
    active_resume_kind = lookup_resume_surface_text(
        payload,
        "active_resume_kind",
    )
    active_resume_pointer = lookup_resume_surface_text(
        payload,
        "active_resume_pointer",
    )
    if (
        active_resume_kind
        in {
            RESUME_CANDIDATE_KIND_BOUNDED_SEGMENT,
            RESUME_CANDIDATE_KIND_CONTINUITY_HANDOFF,
            RESUME_CANDIDATE_KIND_INTERRUPTED_AGENT,
        }
        and active_resume_pointer is not None
    ):
        return True
    if (
        lookup_resume_surface_text(
            payload,
            "continuity_handoff_file",
        )
        is not None
    ):
        return True

    candidates = lookup_resume_surface_list(payload, "resume_candidates")
    if not isinstance(candidates, list):
        return False
    return any(
        isinstance(candidate, Mapping) and _resume_candidate_exposes_local_target(candidate) for candidate in candidates
    )


def _presentation_text(payload: Mapping[str, object] | None, *keys: str) -> str | None:
    for key in keys:
        value = lookup_resume_surface_text(payload, key)
        if value is not None:
            return value
    return None


def _presentation_mapping(payload: Mapping[str, object] | None, key: str) -> dict[str, object] | None:
    return lookup_resume_surface_mapping(payload, key)


def _presentation_list(payload: Mapping[str, object] | None, key: str) -> list[Mapping[str, object]]:
    items = lookup_resume_surface_list(payload, key)
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _presentation_bool(payload: Mapping[str, object], key: str) -> bool:
    return payload.get(key) is True


def _presentation_command(command: str | None) -> str | None:
    if not isinstance(command, str) or not command.strip():
        return None
    stripped = command.strip()
    return stripped if "`" in stripped else f"`{stripped}`"


def _presentation_display_path(path: str) -> str:
    if path.startswith(("./", "/", "~")):
        return path
    return f"./{path}"


def _presentation_result_summary(result: object) -> str | None:
    if not isinstance(result, Mapping):
        return None

    result_id = _presentation_text(result, "id")
    description = _presentation_text(result, "description", "label", "name", "title")
    equation = _presentation_text(result, "equation")
    if description and equation:
        summary = f"{description} [{equation}]"
    elif description:
        summary = description
    elif equation:
        summary = equation
    elif result_id:
        summary = result_id
    else:
        return None

    if result_id and summary != result_id:
        summary = f"{summary} ({result_id})"
    if result.get("verified") is True or bool(result.get("verification_records")):
        summary = f"{summary}; verified"
    return summary


def _presentation_result_summary_from_payload(
    payload: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
) -> str | None:
    explicit_summary = _presentation_text(payload, "active_resume_result_summary")
    if explicit_summary is not None:
        return explicit_summary

    active_result_summary = _presentation_result_summary(payload.get("active_resume_result"))
    if active_result_summary is not None:
        return active_result_summary

    for candidate in candidates:
        candidate_result_summary = _presentation_result_summary(candidate.get("last_result"))
        if candidate_result_summary is not None:
            return candidate_result_summary
        last_result_id = _presentation_text(candidate, "last_result_id")
        if last_result_id is None:
            continue
        derived_results = lookup_resume_surface_list(payload, "derived_intermediate_results")
        if not isinstance(derived_results, list):
            continue
        for item in derived_results:
            result = item if isinstance(item, Mapping) else None
            if result is not None and _presentation_text(result, "id") == last_result_id:
                derived_result_summary = _presentation_result_summary(result)
                if derived_result_summary is not None:
                    return derived_result_summary
    return None


def _presentation_candidate_kinds(candidates: Sequence[Mapping[str, object]]) -> str:
    kinds = [resume_candidate_kind(candidate) for candidate in candidates]
    visible = [kind for kind in kinds if isinstance(kind, str) and kind.strip()]
    if not visible:
        return "none"
    ordered = [
        RESUME_CANDIDATE_KIND_BOUNDED_SEGMENT,
        RESUME_CANDIDATE_KIND_CONTINUITY_HANDOFF,
        RESUME_CANDIDATE_KIND_INTERRUPTED_AGENT,
    ]
    unique = [kind for kind in ordered if kind in visible]
    unique.extend(kind for kind in visible if kind not in unique)
    return ", ".join(unique)


def _presentation_phase_plan(segment: Mapping[str, object] | None) -> str | None:
    if not isinstance(segment, Mapping):
        return None
    phase = _presentation_text(segment, "phase")
    plan = _presentation_text(segment, "plan")
    if phase and plan:
        return f"phase {phase}, plan {plan}"
    if phase:
        return f"phase {phase}"
    if plan:
        return f"plan {plan}"
    return None


def _selected_project_lane(payload: Mapping[str, object]) -> str:
    workspace_root = _presentation_text(payload, "workspace_root")
    project_root = _presentation_text(payload, "project_root")
    project_label = _presentation_text(payload, "project_label", "project_title", "project_name")
    project_summary = _presentation_text(payload, "project_summary", "summary", "description")
    project_root_source = _presentation_text(payload, "project_root_source")
    project_requires_selection = _presentation_bool(payload, "project_reentry_requires_selection")
    auto_selected = _presentation_bool(payload, "project_root_auto_selected")

    parts: list[str] = []
    if project_root is not None:
        parts.append(f"Project root: {project_root}")
    elif workspace_root is not None:
        parts.append(f"No project selected; workspace {workspace_root}")
    else:
        parts.append("No project selected")

    if project_label is not None:
        parts.append(f"Project label: {project_label}")
    if project_summary is not None:
        parts.append(f"Project summary: {project_summary}")
    if workspace_root is not None and workspace_root != project_root:
        parts.append(f"Workspace: {workspace_root}")
    if auto_selected:
        parts.append(
            "Source: auto-selected recent project from the machine-local recent-project index; reopen or confirm before writes"
        )
    elif project_root_source == "recent_project":
        parts.append("Source: recent project selected explicitly from the machine-local recent-project index")
    elif project_root_source is not None:
        parts.append(f"Source: {project_root_source.replace('_', ' ')}")
    if project_requires_selection:
        parts.append("Explicit recent-project selection required")
    return "; ".join(parts)


def _presentation_status_message(payload: Mapping[str, object], advice: Mapping[str, object] | None) -> str | None:
    advice = advice or {}
    decision_source = _presentation_text(advice, "decision_source")
    project_reentry_reason = _presentation_text(advice, "project_reentry_reason", "primary_reason")
    if decision_source == "ambiguous-recent-projects":
        return project_reentry_reason or "Multiple recoverable recent projects were found; choose one explicitly."
    if payload.get("planning_exists") is False:
        return "No GPD planning directory is present in this workspace."

    status = _presentation_text(advice, "status")
    auto_selected = _presentation_bool(payload, "project_root_auto_selected")
    if status == "bounded-segment":
        if auto_selected:
            return "A bounded segment is resumable from an auto-selected recent project."
        return "A bounded segment is resumable from the current workspace state."
    if status == "interrupted-agent":
        return "An interrupted agent marker is present, but no bounded resume segment is active."
    if status == "session-handoff":
        return "A continuity handoff is available, but no resumable bounded segment is currently active."
    if status == "missing-handoff":
        return "Canonical recovery metadata exists, but the continuity handoff file is missing."
    if status == "live-execution":
        return "A live execution snapshot exists, but it is advisory only and does not expose a portable bounded-segment target."
    if _presentation_text(payload, "machine_change_notice") is not None:
        return "A machine change was detected, but the project state is portable and does not require repair."
    return None


def _primary_resume_target_lane(payload: Mapping[str, object], *, recovery_advice: Mapping[str, object] | None) -> str:
    active_kind = _presentation_text(payload, "active_resume_kind")
    if active_kind is not None:
        active_kind = resume_candidate_kind({"kind": active_kind}) or active_kind
    active_pointer = _presentation_text(payload, "active_resume_pointer")
    active_segment = _presentation_mapping(payload, "active_bounded_segment")
    derived_execution_head = _presentation_mapping(payload, "derived_execution_head")
    missing_handoff = _presentation_text(payload, "missing_continuity_handoff_file")
    candidates = _presentation_list(payload, "resume_candidates")
    auto_selected = _presentation_bool(payload, "project_root_auto_selected")

    parts: list[str] = []
    status_message = _presentation_status_message(payload, recovery_advice)
    if status_message is not None:
        parts.append(status_message)

    if active_kind == RESUME_CANDIDATE_KIND_BOUNDED_SEGMENT and active_pointer is not None:
        if status_message is not None:
            pass
        elif auto_selected:
            parts.append("A bounded segment is resumable from an auto-selected recent project.")
        else:
            parts.append("A bounded segment is resumable from the selected project.")
        parts.append("Kind: Bounded segment")
        phase_plan = _presentation_phase_plan(active_segment)
        if phase_plan is not None:
            parts.append(phase_plan)
        parts.append(f"Primary pointer: {_presentation_display_path(active_pointer)}")
    elif active_kind == RESUME_CANDIDATE_KIND_CONTINUITY_HANDOFF and active_pointer is not None:
        if status_message is None:
            parts.append("A continuity handoff is available, but no resumable bounded segment is currently active.")
        parts.append("Kind: Continuity handoff")
        if payload.get("execution_resumable") is not True:
            parts.append("no resumable bounded segment is currently active")
        parts.append(f"Primary pointer: {_presentation_display_path(active_pointer)}")
    elif active_kind == RESUME_CANDIDATE_KIND_INTERRUPTED_AGENT:
        if status_message is None:
            parts.append("An interrupted agent marker is present, but no bounded resume segment is active.")
        if active_pointer is not None:
            parts.append(f"Primary pointer: {_presentation_display_path(active_pointer)}")
    elif missing_handoff is not None:
        if status_message is None:
            parts.append("Canonical recovery metadata exists, but the continuity handoff file is missing.")
        parts.append(f"Primary pointer: {_presentation_display_path(missing_handoff)}")
    elif derived_execution_head is not None:
        if status_message is None:
            parts.append(
                "A live execution snapshot exists, but it is advisory only and does not expose a portable bounded-segment target."
            )
        parts.append("no bounded resume segment is currently active")
    else:
        if status_message is None:
            parts.append("No bounded_segment, continuity_handoff, or interrupted_agent candidate is currently recorded")

    result_summary = _presentation_result_summary_from_payload(payload, candidates)
    if result_summary is not None:
        parts.append(f"Resume result: {result_summary}")

    parts.append(
        "Canonical candidate kinds: bounded_segment, continuity_handoff, interrupted_agent"
        f"; recorded: {_presentation_candidate_kinds(candidates)}"
    )
    return "; ".join(parts)


def _project_contract_needs_repair(payload: Mapping[str, object]) -> bool:
    gate = _presentation_mapping(payload, "project_contract_gate")
    if not isinstance(gate, Mapping):
        return False
    if gate.get("repair_required") is True:
        return True
    status = _presentation_text(gate, "status", "load_status")
    return status in {"error", "invalid", "malformed", "blocked"}


def _blocker_next_command_lane(
    payload: Mapping[str, object],
    *,
    recovery_advice: Mapping[str, object] | None,
    local_resume_command: str,
    recent_resume_command: str,
    raw_resume_command: str,
) -> str:
    advice = recovery_advice or {}
    continue_command = _presentation_command(_presentation_text(advice, "continue_command")) or "runtime `resume-work`"
    fast_next_command = (
        _presentation_command(_presentation_text(advice, "fast_next_command")) or "runtime `suggest-next`"
    )
    local_command = _presentation_command(local_resume_command) or "`gpd resume`"
    recent_command = _presentation_command(recent_resume_command) or "`gpd resume --recent`"
    raw_command = _presentation_command(raw_resume_command) or "`gpd --raw resume`"

    if _presentation_bool(payload, "project_reentry_requires_selection"):
        resumable_count = advice.get("resumable_projects_count")
        if isinstance(resumable_count, int) and resumable_count > 0:
            return f"Blocker: {resumable_count} recoverable choices require explicit selection; next command: {recent_command}"
        return f"Blocker: explicit recent-project selection required; next command: {recent_command}"

    project_root_source = _presentation_text(payload, "project_root_source")
    if _presentation_bool(payload, "project_root_auto_selected") or project_root_source == "recent_project":
        return (
            "Blocker: auto-selected recent project cannot quick-resume from an unrelated workspace; "
            f"next command: {recent_command}, then reopen the selected project and run {continue_command}; "
            f"fast next after reopening: {fast_next_command}; local snapshot: {local_command}; raw: {raw_command}"
        )

    if _project_contract_needs_repair(payload):
        return "Blocker: project contract or state repair required; next command: `gpd:sync-state`"

    missing_handoff = _presentation_text(payload, "missing_continuity_handoff_file")
    if missing_handoff is not None:
        return f"Blocker: recorded handoff file is missing ({missing_handoff}); next command: `gpd:sync-state`"

    machine_change_notice = _presentation_text(payload, "machine_change_notice")
    has_local_recovery_target = resume_payload_has_local_recovery_target(payload)
    if machine_change_notice is not None and not has_local_recovery_target:
        return f"Advisory: {machine_change_notice}; local snapshot: {local_command}; raw: {raw_command}"

    if not has_local_recovery_target:
        return f"Next command: {recent_command} to search other recent projects; local snapshot: {local_command}; raw: {raw_command}"

    advisory_prefix = f"Advisory: {machine_change_notice}; " if machine_change_notice is not None else ""
    return (
        f"{advisory_prefix}Next command: {continue_command}; fast next: {fast_next_command}; "
        f"local snapshot: {local_command}; cross-project: {recent_command}; raw: {raw_command}"
    )


def build_resume_presentation_lanes(
    payload: Mapping[str, object],
    *,
    recovery_advice: Mapping[str, object] | None = None,
    local_resume_command: str = "gpd resume",
    recent_resume_command: str = "gpd resume --recent",
    raw_resume_command: str = "gpd --raw resume",
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Return the three human-facing resume lanes for compressed rendering."""

    public_payload = canonicalize_resume_public_payload(payload)
    return (
        {
            "lane": RESUME_PRESENTATION_LANE_SELECTED_PROJECT,
            "label": "Selected project",
            "value": _selected_project_lane(public_payload),
        },
        {
            "lane": RESUME_PRESENTATION_LANE_PRIMARY_RESUME_TARGET,
            "label": "Primary resume target",
            "value": _primary_resume_target_lane(public_payload, recovery_advice=recovery_advice),
        },
        {
            "lane": RESUME_PRESENTATION_LANE_BLOCKER_NEXT_COMMAND,
            "label": "Blocker / next command",
            "value": _blocker_next_command_lane(
                public_payload,
                recovery_advice=recovery_advice,
                local_resume_command=local_resume_command,
                recent_resume_command=recent_resume_command,
                raw_resume_command=raw_resume_command,
            ),
        },
    )


def _strip_top_level_resume_backend_only_keys(
    payload: Mapping[str, object],
    *,
    backend_only_fields: frozenset[str],
) -> dict[str, object]:
    """Drop top-level backend-only marker keys from one public resume payload."""

    cleaned: dict[str, object] = {}
    for key, value in payload.items():
        if key in backend_only_fields:
            continue
        cleaned[key] = value
    return cleaned


def canonicalize_resume_public_payload(
    payload: Mapping[str, object],
    *,
    backend_only_fields: Sequence[str] = RESUME_BACKEND_ONLY_FIELDS,
) -> dict[str, object]:
    """Strip backend-only marker keys from one public resume payload."""
    return _strip_top_level_resume_backend_only_keys(
        dict(payload),
        backend_only_fields=frozenset(backend_only_fields),
    )
