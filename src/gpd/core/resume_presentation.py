"""Pure resume projection helpers for public recovery surfaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gpd.core.resume_surface import (
    canonicalize_resume_public_payload,
    lookup_resume_surface_list,
    lookup_resume_surface_value,
    resume_candidate_kind,
    resume_candidate_kind_from_source,
)

__all__ = [
    "format_display_path",
    "project_root_source_label",
    "public_resume_origin_family",
    "resume_active_result",
    "resume_augmented_payload",
    "resume_authoritative_active_execution",
    "resume_candidate_kind_label",
    "resume_candidate_last_result",
    "resume_candidate_notes",
    "resume_candidate_origin",
    "resume_candidate_phase_plan",
    "resume_candidate_projection",
    "resume_candidate_rerun_anchor",
    "resume_candidate_target",
    "resume_mode_label",
    "resume_origin_label",
    "resume_result_payload",
    "resume_result_summary",
    "resume_status_label",
    "resume_status_message",
    "resume_visible_candidates",
]


def _advice_value(advice: object, field: str) -> object:
    if isinstance(advice, Mapping):
        return advice.get(field)
    return getattr(advice, field, None)


def _advice_text(advice: object, field: str) -> str | None:
    value = _advice_value(advice, field)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _strict_bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _payload_flag(payload: Mapping[str, object], key: str) -> bool:
    return _strict_bool_value(payload.get(key)) is True


def _resume_text(payload: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _resume_candidate_canonical_kind(candidate: Mapping[str, object]) -> str:
    return resume_candidate_kind(candidate) or "unknown"


def _serialize_recovery_advice(recovery_advice: object) -> dict[str, object]:
    if isinstance(recovery_advice, Mapping):
        return dict(recovery_advice)
    from gpd.core.recovery_advice import serialize_recovery_advice

    return serialize_recovery_advice(recovery_advice)


def format_display_path(target: str | Path | None, *, cwd: Path | None = None) -> str:
    """Format a path for concise human-facing output."""
    if target is None:
        return ""

    raw_target = str(target)
    if not raw_target:
        return ""

    base_cwd = (cwd or Path.cwd()).expanduser()
    target_path = Path(raw_target).expanduser()
    if not target_path.is_absolute():
        target_path = base_cwd / target_path

    try:
        resolved_target = target_path.resolve(strict=False)
    except OSError:
        return target_path.as_posix()
    try:
        resolved_cwd = base_cwd.resolve(strict=False)
    except OSError:
        resolved_cwd = base_cwd
    try:
        resolved_home = Path.home().expanduser().resolve(strict=False)
    except OSError:
        return resolved_target.as_posix()

    try:
        relative_to_cwd = resolved_target.relative_to(resolved_cwd)
    except ValueError:
        pass
    else:
        relative_text = relative_to_cwd.as_posix()
        return "." if relative_text in ("", ".") else f"./{relative_text}"

    try:
        relative_to_home = resolved_target.relative_to(resolved_home)
    except ValueError:
        return resolved_target.as_posix()

    relative_text = relative_to_home.as_posix()
    return "~" if relative_text in ("", ".") else f"~/{relative_text}"


def resume_status_message(payload: Mapping[str, object], *, recovery_advice: object) -> str:
    """Return a concise human summary of resume readiness for this workspace."""
    auto_selected = _payload_flag(payload, "project_root_auto_selected")
    if _advice_text(recovery_advice, "decision_source") == "ambiguous-recent-projects":
        return (
            _advice_text(recovery_advice, "project_reentry_reason")
            or _advice_text(recovery_advice, "primary_reason")
            or "Multiple recoverable recent projects were found; choose one explicitly."
        )
    if not _payload_flag(payload, "planning_exists"):
        return "No GPD planning directory is present in this workspace."
    if not any(_payload_flag(payload, key) for key in ("state_exists", "roadmap_exists", "project_exists")):
        return "Planning scaffolding exists, but there is no recoverable project state yet."

    status = _advice_text(recovery_advice, "status")
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
    if status == "workspace-recovery" and _advice_text(recovery_advice, "machine_change_notice"):
        return "A machine change was detected, but the project state is portable and does not require repair."
    if status == "workspace-recovery":
        return "Current workspace has recorded recovery context to inspect."
    if _advice_text(recovery_advice, "machine_change_notice"):
        return "A machine change was detected, but the project state is portable and does not require repair."
    return "No recent local recovery target is currently recorded."


def resume_mode_label(value: object) -> str:
    """Format a resume mode for human-facing output."""
    if not isinstance(value, str) or not value.strip():
        return "none"
    return value.replace("_", " ")


def resume_status_label(status: object) -> str:
    """Return a canonical human label for one recovery status."""
    labels = {
        "bounded-segment": "Bounded segment",
        "interrupted-agent": "Interrupted agent",
        "session-handoff": "Continuity handoff",
        "missing-handoff": "Missing continuity handoff",
        "live-execution": "Advisory live execution",
        "workspace-recovery": "Recovery context",
        "recent-projects": "Recent projects",
        "recovery-error": "Recovery error",
        "no-recovery": "No recovery target",
    }
    status_text = str(status).strip() if status is not None else ""
    return labels.get(status_text, status_text.replace("_", " ") if status_text else "Unknown")


def project_root_source_label(source: object, *, auto_selected: bool = False) -> str:
    """Map a project-root source to a plain-language re-entry label."""
    labels = {
        "current_workspace": "current workspace",
        "workspace": "current workspace",
        "recent_project": "machine-local recent-project index",
    }
    source_text = str(source).strip() if source is not None else ""
    label = labels.get(source_text, source_text.replace("_", " ") if source_text else "unknown")
    if source_text == "recent_project":
        if auto_selected:
            return f"auto-selected recent project (unique recoverable match from the {label})"
        return f"recent project selected explicitly from the {label}"
    return label


def resume_candidate_kind_label(candidate: Mapping[str, object]) -> str:
    """Map one resume candidate to a user-facing kind label."""
    kind = _resume_candidate_canonical_kind(candidate)
    labels = {
        "bounded_segment": "Bounded segment",
        "continuity_handoff": "Continuity handoff",
        "interrupted_agent": "Interrupted agent",
    }
    return labels.get(kind, kind.replace("_", " ") if kind else "unknown")


def resume_origin_label(origin: object) -> str:
    """Map one canonical resume origin to a user-facing label."""
    labels = {
        "canonical_continuation": "canonical continuation",
        "derived_execution_head": "derived execution head",
        "interrupted_agent": "interrupted agent",
    }
    origin_text = str(origin).strip() if origin is not None else ""
    if not origin_text:
        return "Unknown"
    return labels.get(origin_text, "Unknown")


def public_resume_origin_family(
    origin: object,
    *,
    source: object = None,
    active_execution: Mapping[str, object] | None = None,
    current_execution: Mapping[str, object] | None = None,
) -> str | None:
    """Collapse internal resume-origin tokens into public resume-origin families."""
    origin_text = str(origin).strip() if origin is not None else ""
    if origin_text in {"canonical_continuation", "derived_execution_head", "interrupted_agent"}:
        return origin_text

    normalized_source = str(source).strip() if source is not None else ""

    if normalized_source == "current_execution":
        return "canonical_continuation" if isinstance(active_execution, Mapping) else "derived_execution_head"
    if normalized_source == "handoff_resume_file":
        return "canonical_continuation"
    if normalized_source == "interrupted_agent":
        return "interrupted_agent"

    if origin_text == "current_execution":
        return "canonical_continuation" if isinstance(active_execution, Mapping) else "derived_execution_head"
    if origin_text == "handoff_resume_file":
        return "canonical_continuation"
    if origin_text in {"continuation.bounded_segment", "continuation.handoff"}:
        return "canonical_continuation"
    if origin_text == "interrupted_agent_marker":
        return "interrupted_agent"
    return None


def resume_authoritative_active_execution(payload: Mapping[str, object]) -> dict[str, object] | None:
    """Return the bounded segment only when it comes from canonical continuation."""
    active_bounded_segment_raw = lookup_resume_surface_value(payload, "active_bounded_segment")
    if not isinstance(active_bounded_segment_raw, Mapping):
        return None

    active_origin = payload.get("active_resume_origin")
    if not isinstance(active_origin, str) or not active_origin.strip():
        active_origin = lookup_resume_surface_value(payload, "active_resume_origin")

    if str(active_origin).strip() in {"canonical_continuation", "continuation.bounded_segment"}:
        return dict(active_bounded_segment_raw)
    return None


def resume_candidate_phase_plan(candidate: Mapping[str, object]) -> str:
    """Format phase/plan context for one resume candidate."""
    phase = candidate.get("phase")
    plan = candidate.get("plan")
    phase_text = str(phase).strip() if phase is not None else ""
    plan_text = str(plan).strip() if plan is not None else ""
    if phase_text and plan_text:
        return f"{phase_text} / {plan_text}"
    if phase_text:
        return phase_text
    if plan_text:
        return plan_text
    return "-"


def resume_visible_candidates(payload: Mapping[str, object]) -> list[dict[str, object]]:
    """Return the canonical candidate list to render."""
    candidates = lookup_resume_surface_list(payload, "resume_candidates")
    if not isinstance(candidates, list):
        return []
    return [dict(item) for item in candidates if isinstance(item, Mapping)]


def resume_candidate_target(candidate: Mapping[str, object], *, cwd: Path | None = None) -> str:
    """Format the primary target or pointer for one resume candidate."""
    source = str(candidate.get("source") or "").strip()
    if source == "interrupted_agent":
        agent_id = candidate.get("agent_id")
        return str(agent_id).strip() if agent_id is not None and str(agent_id).strip() else "-"

    resume_file = candidate.get("resume_file")
    if isinstance(resume_file, str) and resume_file.strip():
        return format_display_path(resume_file.strip(), cwd=cwd)
    return "-"


def resume_candidate_rerun_anchor(candidate: Mapping[str, object]) -> str | None:
    """Return the canonical rerun anchor note for one candidate, if any."""
    last_result_id = candidate.get("last_result_id")
    last_result_label = candidate.get("last_result_label")
    if not isinstance(last_result_id, str) or not last_result_id.strip():
        if isinstance(last_result_label, str) and last_result_label.strip():
            return f"last result: {last_result_label.strip()}"
        return None

    last_result_id_text = last_result_id.strip()
    if isinstance(last_result_label, str) and last_result_label.strip():
        return f"rerun anchor: {last_result_label.strip()} ({last_result_id_text})"
    return f"rerun anchor: {last_result_id_text}"


def resume_result_payload(value: object) -> dict[str, object] | None:
    """Normalize a hydrated result payload into a plain dictionary."""
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump(mode="json")
        except Exception:
            return None
    if isinstance(value, Mapping):
        return dict(value)
    return None


def resume_result_summary(result: Mapping[str, object] | None, *, include_id: bool = True) -> str | None:
    """Render a concise human summary for one hydrated intermediate result."""
    if not isinstance(result, Mapping):
        return None

    result_id = _resume_text(result, "id")
    description = _resume_text(result, "description", "label", "name", "title")
    equation = _resume_text(result, "equation")
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

    if include_id and result_id and summary != result_id:
        summary = f"{summary} ({result_id})"
    if _strict_bool_value(result.get("verified")) is True or bool(result.get("verification_records")):
        summary = f"{summary} · verified"
    return summary


def resume_candidate_last_result(
    candidate: Mapping[str, object],
    *,
    payload: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    """Return the hydrated last-result payload for one candidate, if available."""
    result = resume_result_payload(candidate.get("last_result"))
    if result is not None:
        return result

    if payload is None:
        return None

    last_result_id = _resume_text(candidate, "last_result_id")
    if not isinstance(last_result_id, str) or not last_result_id.strip():
        return None

    active_result = resume_result_payload(lookup_resume_surface_value(payload, "active_resume_result"))
    if active_result is not None and _resume_text(active_result, "id") == last_result_id:
        return active_result

    derived_results = lookup_resume_surface_value(payload, "derived_intermediate_results")
    if isinstance(derived_results, list):
        for item in derived_results:
            result = resume_result_payload(item)
            if result is not None and _resume_text(result, "id") == last_result_id:
                return result

    return None


def resume_active_result(
    payload: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    """Return the most relevant hydrated result for the current resume view."""
    active_result = resume_result_payload(lookup_resume_surface_value(payload, "active_resume_result"))
    if active_result is not None:
        return active_result

    for candidate in candidates:
        result = resume_candidate_last_result(candidate, payload=payload)
        if result is not None:
            return result

    return None


def resume_candidate_origin(
    candidate: Mapping[str, object],
    *,
    active_execution: Mapping[str, object] | None,
    current_execution: Mapping[str, object] | None,
) -> tuple[str, str]:
    """Return a machine label and human summary for one candidate origin."""
    origin = candidate.get("origin")
    source = str(candidate.get("source") or "").strip()
    public_origin = public_resume_origin_family(
        origin,
        source=source,
        active_execution=active_execution,
        current_execution=current_execution,
    )
    if public_origin is not None and source != "current_execution":
        return public_origin, resume_origin_label(public_origin)
    status = str(candidate.get("status") or "").strip()
    if source == "current_execution":
        active_resume = (
            str(active_execution.get("resume_file")).strip()
            if isinstance(active_execution, Mapping) and active_execution.get("resume_file") is not None
            else ""
        )
        current_resume = (
            str(current_execution.get("resume_file")).strip()
            if isinstance(current_execution, Mapping) and current_execution.get("resume_file") is not None
            else ""
        )
        if isinstance(active_execution, Mapping):
            if active_resume and current_resume and active_resume != current_resume:
                return (
                    "canonical_continuation",
                    "canonical continuation; current execution points at a different handoff file",
                )
            return ("canonical_continuation", "canonical continuation")
        if isinstance(current_execution, Mapping):
            return ("derived_execution_head", "derived execution head")
        return ("derived_execution_head", "derived execution head")
    if source == "handoff_resume_file":
        if status == "missing":
            return ("canonical_continuation", "canonical continuation; handoff file missing")
        return ("canonical_continuation", "canonical continuation")
    if source == "interrupted_agent":
        return ("interrupted_agent", "interrupted-agent marker")
    return ("unknown", "unknown origin")


def resume_candidate_notes(
    candidate: Mapping[str, object],
    *,
    payload: Mapping[str, object] | None = None,
    active_execution: Mapping[str, object] | None = None,
    current_execution: Mapping[str, object] | None = None,
) -> str:
    """Render the most relevant resume notes for one candidate."""
    notes: list[str] = []

    checkpoint_reason = candidate.get("checkpoint_reason")
    if isinstance(checkpoint_reason, str) and checkpoint_reason.strip():
        notes.append(f"checkpoint: {checkpoint_reason.strip().replace('_', ' ')}")

    waiting_reason = candidate.get("waiting_reason")
    if isinstance(waiting_reason, str) and waiting_reason.strip():
        notes.append(waiting_reason.strip())

    blocked_reason = candidate.get("blocked_reason")
    if isinstance(blocked_reason, str) and blocked_reason.strip():
        notes.append(f"blocked: {blocked_reason.strip()}")

    hydrated_result = resume_candidate_last_result(candidate, payload=payload)
    if hydrated_result is not None:
        hydrated_summary = resume_result_summary(hydrated_result)
        if hydrated_summary is not None:
            notes.append(f"result: {hydrated_summary}")
    else:
        rerun_anchor = resume_candidate_rerun_anchor(candidate)
        if rerun_anchor is not None:
            notes.append(rerun_anchor)

    if _strict_bool_value(candidate.get("first_result_gate_pending")) is True:
        notes.append("first-result gate pending")
    if _strict_bool_value(candidate.get("pre_fanout_review_pending")) is True:
        notes.append("pre-fanout review pending")
    if _strict_bool_value(candidate.get("skeptical_requestioning_required")) is True:
        notes.append("skeptical re-questioning required")
    if _strict_bool_value(candidate.get("downstream_locked")) is True:
        notes.append("downstream locked")

    execution_view = current_execution or active_execution
    if execution_view is not None:
        current_task = execution_view.get("current_task")
        current_task_index = execution_view.get("current_task_index")
        current_task_total = execution_view.get("current_task_total")
        if isinstance(current_task, str) and current_task.strip():
            if current_task_index is not None and current_task_total is not None:
                notes.append(f"task {current_task_index}/{current_task_total}: {current_task.strip()}")
            else:
                notes.append(current_task.strip())

        updated_at = execution_view.get("updated_at")
        if isinstance(updated_at, str) and updated_at.strip():
            notes.append(f"updated {updated_at.strip()}")

    if not notes:
        kind = _resume_candidate_canonical_kind(candidate)
        status = str(candidate.get("status") or "").strip()
        if kind == "continuity_handoff" and status == "missing":
            return "Recorded in canonical continuation state, but the handoff file is missing from this workspace."
        if kind == "continuity_handoff":
            return "Recorded in canonical continuation state."
        if kind == "interrupted_agent":
            return "Interrupted agent marker only; inspect agent output before continuing."
        return "No additional resume notes recorded."
    return "; ".join(notes[:5])


def resume_candidate_projection(
    candidate: Mapping[str, object],
    *,
    payload: Mapping[str, object] | None = None,
    active_execution: Mapping[str, object] | None = None,
    current_execution: Mapping[str, object] | None = None,
    cwd: Path | None = None,
) -> dict[str, object]:
    """Project one raw candidate into a canonical recovery view."""
    origin, origin_label = resume_candidate_origin(
        candidate,
        active_execution=active_execution,
        current_execution=current_execution,
    )
    status = str(candidate.get("status") or "unknown").strip() or "unknown"
    kind = _resume_candidate_canonical_kind(candidate)
    if kind == "unknown":
        kind = resume_candidate_kind_from_source(str(candidate.get("source") or "").strip()) or "unknown"
    return {
        "kind": kind,
        "kind_label": resume_candidate_kind_label(candidate),
        "status": status,
        "status_label": status.replace("_", " "),
        "origin": origin,
        "origin_label": origin_label,
        "phase_plan": resume_candidate_phase_plan(candidate),
        "target": resume_candidate_target(candidate, cwd=cwd),
        "notes": resume_candidate_notes(
            candidate,
            payload=payload,
            active_execution=active_execution,
            current_execution=current_execution,
        ),
        "source": candidate.get("source"),
        "resume_file": candidate.get("resume_file"),
        "resumable": candidate.get("resumable"),
        "advisory": candidate.get("advisory"),
    }


def resume_augmented_payload(
    payload: Mapping[str, object],
    *,
    recovery_advice: object,
    cwd: Path | None = None,
) -> dict[str, object]:
    """Augment the raw resume payload with canonical recovery projections."""
    public_payload = canonicalize_resume_public_payload(payload)
    derived_execution_head_raw = lookup_resume_surface_value(public_payload, "derived_execution_head")
    derived_execution_head = (
        dict(derived_execution_head_raw) if isinstance(derived_execution_head_raw, Mapping) else None
    )
    active_execution = resume_authoritative_active_execution(public_payload)
    current_execution = derived_execution_head
    active_resume_kind = public_payload.get("active_resume_kind")
    if isinstance(active_resume_kind, str) and active_resume_kind.strip():
        active_resume_kind = _resume_candidate_canonical_kind({"kind": active_resume_kind})
    segment_candidates = resume_visible_candidates(public_payload)
    projected_candidates = [
        resume_candidate_projection(
            candidate,
            payload=public_payload,
            active_execution=active_execution
            if _resume_candidate_canonical_kind(candidate) == "bounded_segment"
            else None,
            current_execution=current_execution
            if _resume_candidate_canonical_kind(candidate) == "bounded_segment"
            else None,
            cwd=cwd,
        )
        for candidate in segment_candidates
    ]
    active_resume_result = resume_active_result(public_payload, segment_candidates)
    augmented = dict(public_payload)
    active_resume_origin = augmented.get("active_resume_origin")
    if isinstance(active_resume_origin, str) and active_resume_origin.strip():
        public_active_origin = public_resume_origin_family(
            active_resume_origin,
            active_execution=active_execution,
            current_execution=current_execution,
        )
        if public_active_origin is not None:
            augmented["active_resume_origin"] = public_active_origin
    normalized_resume_candidates: list[dict[str, object]] = []
    for candidate in list(augmented.get("resume_candidates") or []):
        if not isinstance(candidate, Mapping):
            continue
        normalized_candidate = dict(candidate)
        candidate_origin = normalized_candidate.get("origin")
        public_candidate_origin = public_resume_origin_family(
            candidate_origin,
            source=normalized_candidate.get("source"),
            active_execution=active_execution
            if _resume_candidate_canonical_kind(normalized_candidate) == "bounded_segment"
            else None,
            current_execution=current_execution
            if _resume_candidate_canonical_kind(normalized_candidate) == "bounded_segment"
            else None,
        )
        if public_candidate_origin is not None:
            normalized_candidate["origin"] = public_candidate_origin
        normalized_resume_candidates.append(normalized_candidate)
    augmented["resume_candidates"] = normalized_resume_candidates
    augmented["recovery_status"] = _advice_text(recovery_advice, "status") or "no-recovery"
    augmented["recovery_status_label"] = resume_status_label(_advice_text(recovery_advice, "status"))
    augmented["recovery_summary"] = resume_status_message(public_payload, recovery_advice=recovery_advice)
    augmented["active_resume_kind_label"] = resume_mode_label(active_resume_kind)
    recovery_advice_payload = _serialize_recovery_advice(recovery_advice)
    advice_origin = recovery_advice_payload.get("active_resume_origin")
    if isinstance(advice_origin, str) and advice_origin.strip():
        public_advice_origin = public_resume_origin_family(
            advice_origin,
            active_execution=active_execution,
            current_execution=current_execution,
        )
        if public_advice_origin is not None:
            recovery_advice_payload["active_resume_origin"] = public_advice_origin
    augmented["recovery_advice"] = recovery_advice_payload
    augmented["recovery_candidates"] = projected_candidates
    if active_resume_result is not None and "active_resume_result_summary" not in augmented:
        active_resume_result_summary = resume_result_summary(active_resume_result)
        if active_resume_result_summary is not None:
            augmented["active_resume_result_summary"] = active_resume_result_summary
    if projected_candidates:
        augmented["primary_recovery_target"] = projected_candidates[0]
    return augmented
