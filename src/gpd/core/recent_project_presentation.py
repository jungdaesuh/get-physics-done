"""Pure recent-project row projection helpers for resume surfaces."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from gpd.core import recent_projects as recent_projects_module
from gpd.core.project_reentry import recent_project_row_sort_key, recoverable_project_context
from gpd.core.resume_presentation import (
    format_display_path,
    public_resume_origin_family,
    resume_origin_label,
    resume_status_label,
    resume_status_message,
)
from gpd.core.resume_surface import canonicalize_resume_public_payload, lookup_resume_surface_value

__all__ = [
    "annotate_recent_project_rows",
    "build_recent_resume_summary_lines",
    "load_recent_project_display_rows",
    "normalize_recent_project_row",
    "recent_project_current_state",
    "recent_project_label",
    "recent_project_notes",
    "recent_project_recovery_view",
    "recent_project_resume_command",
    "recent_project_resume_file_state",
    "recent_project_selection_reason",
    "recent_project_summary",
    "recent_project_text",
]


RecoveryAdviceBuilder = Callable[..., object]
ResumeLoader = Callable[[Path], Mapping[str, object]]


def _strict_bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def recent_project_text(payload: Mapping[str, object], *keys: str) -> str | None:
    """Return the first non-empty string value among keys."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def recent_project_label(row: Mapping[str, object]) -> str | None:
    """Return an optional human label for one recent-project row."""
    return recent_project_text(row, "label", "title", "project_label", "project_title", "name")


def recent_project_summary(row: Mapping[str, object]) -> str | None:
    """Return an optional human summary for one recent-project row."""
    return recent_project_text(row, "summary", "project_summary", "description", "project_description")


def recent_project_current_state(row: Mapping[str, object]) -> str | None:
    """Return an optional phase/status/progress summary for one recent-project row."""
    current_phase = row.get("current_phase")
    if isinstance(current_phase, Mapping):
        phase = recent_project_text(current_phase, "phase", "id", "number", "name", "title")
        phase_label = recent_project_text(current_phase, "label", "name", "title")
        status = recent_project_text(current_phase, "status", "state")
        progress = recent_project_text(current_phase, "progress", "progress_summary", "summary")
        pieces: list[str] = []
        if phase and phase_label and phase_label != phase:
            pieces.append(f"phase {phase} ({phase_label})")
        elif phase_label:
            pieces.append(phase_label)
        elif phase:
            pieces.append(f"phase {phase}" if not phase.lower().startswith("phase") else phase)
        if status is not None:
            pieces.append(status.replace("_", " "))
        if progress is not None:
            pieces.append(progress)
        return " · ".join(pieces) if pieces else None

    phase = recent_project_text(row, "current_phase", "phase")
    phase_label = recent_project_text(row, "current_phase_name", "phase_name")
    status = recent_project_text(row, "project_status", "status")
    progress = recent_project_text(row, "progress", "progress_summary", "phase_progress")
    pieces = []
    if phase and phase_label and phase_label != phase:
        pieces.append(f"phase {phase} ({phase_label})")
    elif phase_label:
        pieces.append(phase_label)
    elif phase:
        pieces.append(f"phase {phase}" if not phase.lower().startswith("phase") else phase)
    if status is not None and status.replace("_", " ") not in {"recent", "resumable", "unavailable"}:
        pieces.append(status.replace("_", " "))
    if progress is not None:
        pieces.append(progress)
    return " · ".join(pieces) if pieces else None


def recent_project_selection_reason(row: Mapping[str, object]) -> str:
    """Return a plain-language explanation for why a recent-project row is shown."""
    if _strict_bool_value(row.get("available")) is not True:
        reason = row.get("availability_reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
        return "shown because the project root is missing on this machine"
    if _strict_bool_value(row.get("resumable")) is True:
        reason = row.get("resume_file_reason")
        if isinstance(reason, str) and reason.strip():
            return f"shown because it still has a usable handoff target ({reason.strip()})"
        return "shown because it still has a usable handoff target"
    resume_file = row.get("resume_file")
    if isinstance(resume_file, str) and resume_file.strip():
        return "shown because the checkout is available, but the recorded handoff is not currently usable"
    return "shown because the checkout is available, but no recovery handoff is recorded"


def recent_project_resume_file_state(project_root: object, resume_file: object) -> tuple[bool | None, str | None]:
    """Return whether a recent-project handoff file is still usable."""
    if not isinstance(project_root, str) or not project_root.strip():
        return None, None
    if not isinstance(resume_file, str) or not resume_file.strip():
        return None, None

    project_path = Path(project_root).expanduser()
    try:
        project_exists = project_path.exists()
        project_is_dir = project_path.is_dir()
    except OSError:
        return False, "project unavailable on this machine"
    if not project_exists or not project_is_dir:
        return None, None

    try:
        resolved_project = project_path.resolve(strict=False)
    except OSError:
        return False, "project unavailable on this machine"
    candidate = Path(resume_file).expanduser()
    try:
        resolved_target = (
            candidate.resolve(strict=False)
            if candidate.is_absolute()
            else (project_path / candidate).resolve(strict=False)
        )
    except OSError:
        return False, "resume file unavailable"
    try:
        resolved_target.relative_to(resolved_project)
    except ValueError:
        return False, "resume file outside project root"
    try:
        target_exists = resolved_target.exists()
        target_is_file = resolved_target.is_file()
    except OSError:
        return False, "resume file unavailable"
    if not target_exists:
        return False, "resume file missing"
    if not target_is_file:
        return False, "resume file is not a file"
    return True, None


def normalize_recent_project_row(
    row: object,
    *,
    cwd: Path | None = None,
) -> dict[str, object] | None:
    """Project one canonical recent-project row into the display shape."""
    if not isinstance(row, Mapping):
        return None

    project_root = recent_project_text(row, "project_root")
    if project_root is None:
        unexpected_fields = sorted(
            key for key in row if key not in recent_projects_module.RecentProjectEntry.model_fields
        )
        if unexpected_fields:
            formatted = ", ".join(unexpected_fields)
            raise ValueError(f"recent-project row contains unexpected field(s): {formatted}")
        return None

    project_path = Path(project_root).expanduser()
    available_value = row.get("available")
    if isinstance(available_value, bool):
        available = available_value
        derived_availability_reason = None
    else:
        try:
            available = project_path.is_dir()
        except OSError:
            available = False
            derived_availability_reason = "project unavailable on this machine"
        else:
            if available:
                derived_availability_reason = None
            else:
                try:
                    project_exists = project_path.exists()
                except OSError:
                    derived_availability_reason = "project unavailable on this machine"
                else:
                    derived_availability_reason = (
                        "project root is not a directory" if project_exists else "project root missing"
                    )
    normalized: dict[str, object] = {
        "project_root": project_root,
        "workspace": format_display_path(project_path, cwd=cwd),
        "available": available,
        "missing": not available,
    }
    if not available:
        normalized["command"] = "unavailable"
    elif project_path.is_absolute():
        try:
            resolved_project_path = project_path.resolve(strict=False)
        except OSError:
            normalized["command"] = "unavailable"
        else:
            normalized["command"] = f"gpd --cwd {shlex.quote(str(resolved_project_path))} resume"
    else:
        normalized["command"] = None

    for key in (
        "schema_version",
        "last_session_at",
        "last_seen_at",
        "stopped_at",
        "resume_file",
        "resume_file_available",
        "resume_file_reason",
        "status",
        "resumable",
        "availability_reason",
        "last_result_id",
        "resume_target_kind",
        "resume_target_recorded_at",
        "hostname",
        "platform",
        "source_kind",
        "source_session_id",
        "source_segment_id",
        "source_transition_id",
        "source_event_id",
        "source_recorded_at",
        "recovery_phase",
        "recovery_plan",
    ):
        if key in row:
            normalized[key] = row[key]
    if derived_availability_reason is not None and not normalized.get("availability_reason"):
        normalized["availability_reason"] = derived_availability_reason

    resume_file_available, resume_file_reason = recent_project_resume_file_state(
        normalized.get("project_root"),
        normalized.get("resume_file"),
    )
    if resume_file_available is not None:
        normalized["resume_file_available"] = resume_file_available
    if resume_file_reason is not None:
        normalized["resume_file_reason"] = resume_file_reason

    resumable_value = normalized.get("resumable")
    if resumable_value is None:
        resumable_value = normalized.get("resume_file") if isinstance(normalized.get("resume_file"), str) else False
    else:
        resumable_value = _strict_bool_value(resumable_value) is True
    normalized["resumable"] = (
        bool(resumable_value)
        and _strict_bool_value(normalized["available"]) is True
        and normalized.get("resume_file_available") is not False
    )
    status = recent_project_text(normalized, "status")
    if _strict_bool_value(normalized["available"]) is not True:
        status = "unavailable"
    elif status is None:
        status = "resumable" if normalized["resumable"] else "recent"
    normalized["status"] = status

    return normalized


def load_recent_project_display_rows(
    *,
    data_root: Path | None = None,
    last: int | None = None,
    cwd: Path | None = None,
) -> list[dict[str, object]]:
    """Load and normalize recent-project rows for display."""
    raw_rows = recent_projects_module.list_recent_projects(data_root, last=last)

    rows: list[dict[str, object]] = []
    for row in raw_rows:
        row_payload = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
        normalized = normalize_recent_project_row(row_payload, cwd=cwd)
        if normalized is None:
            raise ValueError("recent-project cache returned a malformed canonical row")
        rows.append(normalized)

    rows.sort(key=recent_project_row_sort_key, reverse=True)
    return rows


def recent_project_resume_command(row: Mapping[str, object]) -> str:
    """Return the exact command to reopen one recent project."""
    project_root = row.get("project_root")
    if not isinstance(project_root, str) or not project_root.strip():
        return "unavailable"
    if row.get("available") is not True:
        return "unavailable"
    try:
        project_path = Path(project_root).expanduser().resolve(strict=False)
    except OSError:
        return "unavailable"
    return f"gpd --cwd {shlex.quote(str(project_path))} resume"


def recent_project_notes(row: Mapping[str, object]) -> str:
    """Return a concise availability/resumability note for one recent project row."""
    recovery_note = recent_project_text(row, "recovery_note")
    if recovery_note is not None:
        return recovery_note
    if _strict_bool_value(row.get("available")) is not True:
        reason = row.get("availability_reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
        return "project unavailable on this machine"
    if _strict_bool_value(row.get("resumable")) is True:
        return "ready to reopen"
    reason = row.get("resume_file_reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    return "continue from local recovery state"


def recent_project_recovery_view(
    row: Mapping[str, object],
    *,
    resume_loader: ResumeLoader | None = None,
    recovery_advice_builder: RecoveryAdviceBuilder | None = None,
) -> dict[str, object] | None:
    """Return a canonical recovery summary for one recent-project row when available."""
    project_root = row.get("project_root")
    if not isinstance(project_root, str) or not project_root.strip():
        return None

    try:
        project_path = Path(project_root).expanduser().resolve(strict=False)
        project_exists = project_path.exists()
        project_is_dir = project_path.is_dir()
    except OSError:
        project_path = Path(project_root).expanduser()
        project_exists = False
        project_is_dir = False
    if not project_exists or not project_is_dir:
        return {
            "recovery_status": "no-recovery",
            "recovery_status_label": "Unavailable checkout",
            "recovery_note": "project unavailable on this machine",
        }

    try:
        state_exists, roadmap_exists, project_exists = recoverable_project_context(project_path)
    except OSError:
        return {
            "recovery_status": "no-recovery",
            "recovery_status_label": "Unavailable checkout",
            "recovery_note": "project unavailable on this machine",
        }
    if not (state_exists or roadmap_exists or project_exists):
        return None

    if resume_loader is None:
        from gpd.core.context import init_resume

        resume_loader = init_resume
    if recovery_advice_builder is None:
        from gpd.core.recovery_advice import build_recovery_advice

        recovery_advice_builder = build_recovery_advice

    try:
        payload = dict(resume_loader(project_path))
        advice = recovery_advice_builder(project_path, resume_payload=payload, recent_rows=[])
    except Exception as exc:
        error_message = str(exc).strip() or type(exc).__name__
        return {
            "recovery_status": "recovery-error",
            "recovery_status_label": resume_status_label("recovery-error"),
            "recovery_note": f"Recovery metadata could not be inspected: {error_message}",
            "recovery_error": error_message,
            "recovery_error_type": type(exc).__name__,
        }

    public_payload = canonicalize_resume_public_payload(payload)
    status = getattr(advice, "status", None)
    view: dict[str, object] = {
        "recovery_status": status,
        "recovery_status_label": resume_status_label(status),
        "recovery_note": resume_status_message(public_payload, recovery_advice=advice),
    }
    primary_resume_file = lookup_resume_surface_value(public_payload, "active_resume_pointer")
    if isinstance(primary_resume_file, str) and primary_resume_file.strip():
        view["recovery_target"] = format_display_path(primary_resume_file.strip())
    execution_source = lookup_resume_surface_value(public_payload, "active_resume_origin")
    public_origin = public_resume_origin_family(execution_source, active_execution=None, current_execution=None)
    if public_origin is not None:
        view["recovery_origin"] = resume_origin_label(public_origin)
    return view


def annotate_recent_project_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    resume_loader: ResumeLoader | None = None,
    recovery_advice_builder: RecoveryAdviceBuilder | None = None,
) -> list[dict[str, object]]:
    """Add canonical recovery summaries to recent-project rows while keeping existing fields."""
    annotated: list[dict[str, object]] = []
    for row in rows:
        payload = dict(row)
        recovery_view = recent_project_recovery_view(
            payload,
            resume_loader=resume_loader,
            recovery_advice_builder=recovery_advice_builder,
        )
        if recovery_view is not None:
            payload.update(recovery_view)
        annotated.append(payload)
    return annotated


def build_recent_resume_summary_lines(
    rows: Sequence[Mapping[str, object]],
    *,
    local_resume_command: str = "gpd resume",
) -> list[str]:
    """Return plain text lines for the recent-project picker."""
    lines = [
        "Recent Projects",
        "Machine-local recovery index. Recent projects are ordered by recovery strength, then recency. A single recoverable match can auto-select; otherwise choose explicitly with the command shown for each row.",
        "",
    ]

    if not rows:
        lines.append("No recent projects are recorded on this machine yet.")
        lines.append(
            f"Run `{local_resume_command}` inside a project first, or wait for session continuity to be recorded."
        )
        return lines

    for idx, row in enumerate(rows, start=1):
        label = recent_project_label(row)
        summary = recent_project_summary(row)
        current_state = recent_project_current_state(row)
        workspace = str(row.get("workspace") or format_display_path(str(row.get("project_root") or "")) or "unknown")
        lines.append(f"{idx}. {workspace}")
        if label is not None:
            lines.append(f"   Label: {label}")
        if summary is not None:
            lines.append(f"   Summary: {summary}")
        if current_state is not None:
            lines.append(f"   Current: {current_state}")
        lines.append(f"   Last session: {str(row.get('last_session_at') or row.get('last_seen_at') or '-')}")
        lines.append(f"   Stopped at: {str(row.get('stopped_at') or '-')}")
        recovery_label = recent_project_text(row, "recovery_status_label")
        if recovery_label is not None:
            lines.append(f"   Recovery: {recovery_label}")
        lines.append(f"   Resumable: {'yes' if _strict_bool_value(row.get('resumable')) is True else 'no'}")
        lines.append(f"   Why shown: {recent_project_selection_reason(row)}")
        lines.append(f"   Notes: {recent_project_notes(row)}")
        lines.append(f"   Resume: {recent_project_resume_command(row)}")
        lines.append("")
    lines.append("Next here")
    lines.append("- Select a workspace above, then continue there with `resume-work`.")
    lines.append("- After resuming, `suggest-next` is the fastest next action.")
    return lines
