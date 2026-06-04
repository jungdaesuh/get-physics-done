"""Read-only phase closeout readiness checks."""

from __future__ import annotations

from pathlib import Path

from gpd.core.command_run_hints import (
    NEXT_COMMAND_OWNER_RUNTIME,
    classify_next_command,
)
from gpd.core.next_command_rendering import render_next_up_block
from gpd.core.phase_lifecycle import (
    OWNER_LOCAL_HELPER,
    OWNER_LOCAL_TRANSITION,
    OWNER_RUNTIME,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    CanonicalLifecycleClass,
    LifecycleNextUp,
    PhaseCloseoutReadiness,
    phase_lifecycle_decision,
)
from gpd.core.phases import roadmap_analyze
from gpd.core.utils import phase_normalize

_NON_PHASE_ROUTE_ACTIONS = frozenset(
    {
        "audit-milestone",
        "complete-milestone",
        "new-milestone",
    }
)


def phase_closeout_readiness(
    cwd: Path,
    phase: str,
    *,
    require_verification: bool = True,
) -> PhaseCloseoutReadiness:
    """Return a read-only closeout gate result; never mutate roadmap, state, or tags."""

    return phase_lifecycle_decision(
        cwd,
        phase,
        require_verification=require_verification,
    ).closeout_readiness


def phase_closeout_readiness_payload(readiness: PhaseCloseoutReadiness) -> dict[str, object]:
    """Return raw CLI JSON with canonical route projection plus legacy next_up."""

    payload = readiness.model_dump(mode="json")
    route_payload = _projected_lifecycle_next_up(readiness)
    if route_payload is None:
        return payload

    lifecycle_next_up, next_up = route_payload
    payload["lifecycle_next_up"] = lifecycle_next_up
    payload["next_up"] = next_up
    payload["lifecycle_route"] = _lifecycle_route_projection(
        readiness=readiness,
        lifecycle_next_up=lifecycle_next_up,
    )
    return payload


def _projected_lifecycle_next_up(
    readiness: PhaseCloseoutReadiness,
) -> tuple[dict[str, object], dict[str, object]] | None:
    lifecycle_next_up = readiness.lifecycle_next_up
    if lifecycle_next_up is None:
        return None

    projected_lifecycle = lifecycle_next_up
    lifecycle_payload = projected_lifecycle.model_dump(mode="json")
    primary = lifecycle_payload.get("primary")
    if not isinstance(primary, dict):
        return lifecycle_payload, dict(readiness.next_up)

    next_phase = _command_phase(primary)
    next_phase_context_class = _next_phase_context_class(readiness.project_root, next_phase)
    if (
        lifecycle_payload.get("status") == "closed"
        and primary.get("action") == "plan-phase"
        and next_phase_context_class == "missing_context"
    ):
        command = _runtime_next_command(
            action="discuss-phase",
            phase=next_phase,
            reason="collect missing next-phase context before planning",
        )
        rendered = render_next_up_block(primary=command)
        projected_lifecycle = lifecycle_next_up.model_copy(
            update={
                "primary": command,
                "primary_label": "Primary",
                "rendered_markdown": rendered.markdown,
                "stage_stop_next_runtime_command": rendered.stage_stop_next_runtime_command,
                "stage_stop_also_available": list(rendered.stage_stop_also_available),
            }
        )

    return (
        projected_lifecycle.model_dump(mode="json"),
        projected_lifecycle.as_legacy_next_up_dict(),
    )


def _lifecycle_route_projection(
    *,
    readiness: PhaseCloseoutReadiness,
    lifecycle_next_up: dict[str, object],
) -> dict[str, object]:
    primary = _command_dict(lifecycle_next_up.get("primary"))
    after_this_completes = _command_dict(lifecycle_next_up.get("after_this_completes"))
    primary_owner = primary.get("owner") if primary is not None else None
    local_transition_command = primary if primary_owner == OWNER_LOCAL_TRANSITION else None
    after_local_runtime_command = after_this_completes if local_transition_command is not None else None
    primary_runtime_command = (
        after_local_runtime_command
        if local_transition_command is not None
        else primary
        if primary_owner == NEXT_COMMAND_OWNER_RUNTIME
        else None
    )
    next_phase = _command_phase(primary_runtime_command)
    status_class = str(lifecycle_next_up.get("status_class") or "")

    return {
        "schema_version": lifecycle_next_up.get("schema_version", 1),
        "source": lifecycle_next_up.get("source", "phase-lifecycle"),
        "phase": lifecycle_next_up.get("phase", readiness.phase),
        "status": lifecycle_next_up.get("status"),
        "status_class": status_class,
        "transition_owner": "local_transition" if local_transition_command is not None else "runtime",
        "next_phase": next_phase,
        "next_phase_context_class": _next_phase_context_class(readiness.project_root, next_phase),
        "primary_runtime_command": primary_runtime_command,
        "primary_runtime_command_text": _command_text(primary_runtime_command),
        "local_transition_command": local_transition_command,
        "after_local_runtime_command": after_local_runtime_command,
        "blockers": list(lifecycle_next_up.get("blockers", [])),
        "rendered_markdown": lifecycle_next_up.get("rendered_markdown", ""),
        "stage_stop_next_runtime_command": lifecycle_next_up.get("stage_stop_next_runtime_command"),
        "stage_stop_also_available": list(lifecycle_next_up.get("stage_stop_also_available", [])),
    }


def _runtime_next_command(*, action: str, phase: str | None, reason: str | None):
    label = f"gpd:{action} {phase}" if phase else f"gpd:{action}"
    classified = classify_next_command(command=label, action=action, phase=phase, reason=reason)
    if classified is not None and classified.owner == NEXT_COMMAND_OWNER_RUNTIME:
        return classified
    raise ValueError(f"runtime lifecycle route could not be classified: {label}")


def _command_dict(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def _command_text(command: dict[str, object] | None) -> str | None:
    if command is None:
        return None
    value = command.get("command")
    return str(value) if value is not None else None


def _command_phase(command: dict[str, object] | None) -> str | None:
    if command is None:
        return None
    action = command.get("action")
    if action is not None and str(action) in _NON_PHASE_ROUTE_ACTIONS:
        return None
    phase = command.get("phase")
    if phase is not None:
        return str(phase)
    text = _command_text(command)
    if not text:
        return None
    parts = text.split()
    return parts[-1] if len(parts) > 1 else None


def _next_phase_context_class(project_root: str, next_phase: str | None) -> str:
    if not next_phase:
        return "not_applicable"
    try:
        target = phase_normalize(next_phase)
        for roadmap_phase in roadmap_analyze(Path(project_root)).phases:
            if phase_normalize(roadmap_phase.number) != target:
                continue
            if roadmap_phase.plan_count > 0:
                return "planned"
            if roadmap_phase.has_research:
                return "has_research"
            if roadmap_phase.has_context:
                return "has_context"
            return "missing_context"
    except Exception:  # noqa: BLE001 - raw payload projection should not break readiness.
        return "unknown"
    return "missing_context"


__all__ = [
    "CanonicalLifecycleClass",
    "LifecycleNextUp",
    "OWNER_LOCAL_HELPER",
    "OWNER_LOCAL_TRANSITION",
    "OWNER_RUNTIME",
    "PhaseCloseoutReadiness",
    "ROLE_PRIMARY",
    "ROLE_SECONDARY",
    "phase_closeout_readiness",
    "phase_closeout_readiness_payload",
]
