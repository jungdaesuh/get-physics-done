"""Typer-free payload helpers for Research Persona CLI commands."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from gpd.core.research_persona import (
    RESEARCH_PERSONA_TOP_LEVEL_STRING_LIST_FIELDS,
    ResearchPersona,
    ResearchPersonaAxis,
    ResearchPersonaCapsule,
    ResearchPersonaError,
    ResearchPersonaFact,
    ResearchPersonaHistoryEvent,
    ResearchPersonaPatch,
    ResearchPersonaPatchOperation,
    ResearchPersonaTombstone,
    append_research_persona_history,
    append_research_persona_tombstone,
    apply_research_persona_patch,
    build_research_persona_capsule,
    load_research_persona,
    parse_research_persona_data_strict,
    project_research_persona,
    research_persona_path,
    research_persona_root,
    save_research_persona,
    validate_research_persona,
)

__all__ = [
    "build_apply_patch_payload",
    "build_diff_payload",
    "build_export_capsule_payload",
    "build_forget_payload",
    "build_show_payload",
    "build_validate_payload",
    "parse_research_persona_patch_data_strict",
    "research_persona_apply_patch_payload",
    "research_persona_diff_payload",
    "research_persona_export_capsule_payload",
    "research_persona_forget_fact_payload",
    "research_persona_show_payload",
    "research_persona_validate_payload",
    "summarize_research_persona_diff",
]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _format_pydantic_errors(exc: PydanticValidationError) -> list[str]:
    messages: list[str] = []
    seen: set[str] = set()
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ())) or "value"
        message = str(error.get("msg", "validation failed")).strip() or "validation failed"
        if message.startswith("Value error, "):
            message = message.removeprefix("Value error, ")
        formatted = f"{location} {message}" if message.startswith("must ") else f"{location}: {message}"
        if formatted in seen:
            continue
        seen.add(formatted)
        messages.append(formatted)
    return messages or [str(exc)]


def _store_payload(data_root: Path | None) -> dict[str, object]:
    root = research_persona_root(data_root)
    path = research_persona_path(data_root)
    return {
        "root": str(root),
        "path": str(path),
        "exists": path.exists(),
    }


def _persona_counts_from_payload(payload: dict[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field_name in ("facts", "axes", *RESEARCH_PERSONA_TOP_LEVEL_STRING_LIST_FIELDS):
        value = payload.get(field_name)
        counts[field_name] = len(value) if isinstance(value, list) else 0
    return counts


def _normalize_projection_for_cli(projection: str) -> str:
    return projection.strip().replace("-", "_")


def _input_path_payload(input_path: str | None, *, cwd: Path | None = None) -> tuple[str | None, bool | None]:
    if input_path is None:
        return None, None
    if input_path == "-":
        return "stdin", False
    target = Path(input_path)
    if not target.is_absolute() and cwd is not None:
        target = cwd / target
    return str(target), target.exists()


def _persona_counts(persona: ResearchPersona) -> dict[str, int]:
    return _persona_counts_from_payload(persona.model_dump(mode="json"))


def _projection_counts(projection: dict[str, object]) -> dict[str, int]:
    return _persona_counts_from_payload(projection)


def _fact_descriptor(fact: ResearchPersonaFact) -> dict[str, object]:
    return {
        "id": fact.id,
        "category": fact.category,
        "privacy": fact.privacy,
        "confidence": fact.confidence,
    }


def _axis_descriptor(axis: ResearchPersonaAxis) -> dict[str, object]:
    return {
        "id": axis.id,
        "privacy": axis.privacy,
        "confidence": axis.confidence,
        "fact_ids_count": len(axis.fact_ids),
        "has_name": axis.name is not None,
        "has_value": axis.value is not None,
    }


def _changed_fields(before: dict[str, object], after: dict[str, object]) -> list[str]:
    ignored = {"id"}
    return sorted(
        field_name
        for field_name in set(before) | set(after)
        if field_name not in ignored and before.get(field_name) != after.get(field_name)
    )


def _summarize_fact_diff(before: ResearchPersona, after: ResearchPersona) -> dict[str, object]:
    before_by_id = {fact.id: fact for fact in before.facts}
    after_by_id = {fact.id: fact for fact in after.facts}
    added_ids = sorted(set(after_by_id) - set(before_by_id))
    removed_ids = sorted(set(before_by_id) - set(after_by_id))
    changed: list[dict[str, object]] = []
    for fact_id in sorted(set(before_by_id) & set(after_by_id)):
        before_payload = before_by_id[fact_id].model_dump(mode="json")
        after_payload = after_by_id[fact_id].model_dump(mode="json")
        fields = _changed_fields(before_payload, after_payload)
        if not fields:
            continue
        changed.append(
            {
                "id": fact_id,
                "before": _fact_descriptor(before_by_id[fact_id]),
                "after": _fact_descriptor(after_by_id[fact_id]),
                "changed_fields": fields,
            }
        )
    return {
        "added": [_fact_descriptor(after_by_id[fact_id]) for fact_id in added_ids],
        "removed": [_fact_descriptor(before_by_id[fact_id]) for fact_id in removed_ids],
        "changed": changed,
    }


def _summarize_axis_diff(before: ResearchPersona, after: ResearchPersona) -> dict[str, object]:
    before_by_id = {axis.id: axis for axis in before.axes}
    after_by_id = {axis.id: axis for axis in after.axes}
    added_ids = sorted(set(after_by_id) - set(before_by_id))
    removed_ids = sorted(set(before_by_id) - set(after_by_id))
    changed: list[dict[str, object]] = []
    for axis_id in sorted(set(before_by_id) & set(after_by_id)):
        before_payload = before_by_id[axis_id].model_dump(mode="json")
        after_payload = after_by_id[axis_id].model_dump(mode="json")
        fields = _changed_fields(before_payload, after_payload)
        if not fields:
            continue
        changed.append(
            {
                "id": axis_id,
                "before": _axis_descriptor(before_by_id[axis_id]),
                "after": _axis_descriptor(after_by_id[axis_id]),
                "changed_fields": fields,
            }
        )
    return {
        "added": [_axis_descriptor(after_by_id[axis_id]) for axis_id in added_ids],
        "removed": [_axis_descriptor(before_by_id[axis_id]) for axis_id in removed_ids],
        "changed": changed,
    }


def _summarize_list_diff(before: ResearchPersona, after: ResearchPersona) -> dict[str, object]:
    fields: dict[str, object] = {}
    for field_name in RESEARCH_PERSONA_TOP_LEVEL_STRING_LIST_FIELDS:
        before_values = list(getattr(before, field_name))
        after_values = list(getattr(after, field_name))
        before_set = set(before_values)
        after_set = set(after_values)
        fields[field_name] = {
            "before_count": len(before_values),
            "after_count": len(after_values),
            "added_count": len(after_set - before_set),
            "removed_count": len(before_set - after_set),
            "changed": before_values != after_values,
        }
    return fields


def _would_history_path(data_root: Path | None) -> Path:
    return research_persona_root(data_root) / "history" / "events.jsonl"


def _would_tombstone_path(data_root: Path | None) -> Path:
    return research_persona_root(data_root) / "tombstones" / "events.jsonl"


def _patch_tombstones(patch: ResearchPersonaPatch, *, created_at: str) -> list[ResearchPersonaTombstone]:
    tombstones: list[ResearchPersonaTombstone] = []
    seen: set[str] = set()
    for tombstone in patch.tombstones:
        if tombstone.fact_id in seen:
            continue
        seen.add(tombstone.fact_id)
        tombstones.append(tombstone)
    for operation in patch.operations:
        if operation.tombstone is not None:
            tombstone = operation.tombstone
        elif operation.op == "tombstone_fact" and operation.fact_id is not None:
            tombstone = ResearchPersonaTombstone(
                fact_id=operation.fact_id,
                reason=operation.reason or patch.reason,
                source_kind=patch.source_kind,
                created_at=created_at,
            )
        else:
            continue
        if tombstone.fact_id in seen:
            continue
        seen.add(tombstone.fact_id)
        tombstones.append(tombstone)
    return tombstones


def parse_research_persona_patch_data_strict(data: object) -> ResearchPersonaPatch:
    """Parse strict patch data for future CLI wrappers."""

    if isinstance(data, ResearchPersonaPatch):
        return data
    if not isinstance(data, dict):
        raise ResearchPersonaError("research persona patch must be a JSON object")
    try:
        return ResearchPersonaPatch.model_validate(data)
    except PydanticValidationError as exc:
        raise ResearchPersonaError("; ".join(_format_pydantic_errors(exc))) from exc


def summarize_research_persona_diff(before: ResearchPersona, after: ResearchPersona) -> dict[str, object]:
    """Return a value-redacted before/after summary."""

    if not isinstance(before, ResearchPersona) or not isinstance(after, ResearchPersona):
        raise ResearchPersonaError("research persona diff requires ResearchPersona instances")
    counts_before = _persona_counts(before)
    counts_after = _persona_counts(after)
    return {
        "updated": before.model_dump(mode="json") != after.model_dump(mode="json"),
        "counts": {
            "before": counts_before,
            "after": counts_after,
            "delta": {field_name: counts_after[field_name] - counts_before[field_name] for field_name in counts_before},
        },
        "facts": _summarize_fact_diff(before, after),
        "axes": _summarize_axis_diff(before, after),
        "lists": _summarize_list_diff(before, after),
    }


def research_persona_show_payload(
    *,
    data_root: Path | None = None,
    projection: str = "local",
    strict: bool = True,
) -> dict[str, object]:
    """Return path, existence, count, and projection data without writing files."""

    persona = load_research_persona(data_root, strict=strict)
    projected = project_research_persona(persona, purpose=_normalize_projection_for_cli(projection))
    return {
        **_store_payload(data_root),
        "counts": _persona_counts(persona),
        "projection_counts": _projection_counts(projected),
        "projection": projected,
    }


def research_persona_validate_payload(
    data: object,
    *,
    path: str | Path | None = None,
    exists: bool | None = None,
) -> dict[str, object]:
    """Validate arbitrary research-persona JSON data for CLI output."""

    result = validate_research_persona(data)
    payload: dict[str, object] = result.model_dump(mode="json")
    if path is not None:
        payload["path"] = str(path)
    if exists is not None:
        payload["exists"] = exists
    if result.valid:
        persona = parse_research_persona_data_strict(data)
        payload["counts"] = _persona_counts(persona)
    return payload


def research_persona_diff_payload(
    patch_data: object,
    *,
    data_root: Path | None = None,
) -> dict[str, object]:
    """Return the value-redacted diff a patch would produce without writing files."""

    patch = parse_research_persona_patch_data_strict(patch_data)
    before = load_research_persona(data_root, strict=True)
    after = apply_research_persona_patch(before, patch)
    diff = summarize_research_persona_diff(before, after)
    return {
        **_store_payload(data_root),
        "would_update": diff["updated"],
        "diff": diff,
    }


def research_persona_apply_patch_payload(
    patch_data: object,
    *,
    data_root: Path | None = None,
    dry_run: bool = False,
    actor: str | None = None,
    summary: str | None = None,
    event_type: str = "patch_applied",
    now: str | None = None,
) -> dict[str, object]:
    """Strict-load, apply, and optionally persist a research-persona patch."""

    patch = parse_research_persona_patch_data_strict(patch_data)
    before = load_research_persona(data_root, strict=True)
    after = apply_research_persona_patch(before, patch)
    diff = summarize_research_persona_diff(before, after)
    created_at = now or _utc_now()
    tombstones = _patch_tombstones(patch, created_at=created_at)
    payload: dict[str, object] = {
        **_store_payload(data_root),
        "updated": diff["updated"],
        "dry_run": dry_run,
        "diff": diff,
        "history_path": str(_would_history_path(data_root)),
        "tombstone_path": str(_would_tombstone_path(data_root)),
        "tombstones": {
            "count": len(tombstones),
            "fact_ids": sorted(tombstone.fact_id for tombstone in tombstones),
        },
    }
    if dry_run:
        return payload

    saved_path = save_research_persona(after, data_root)
    event = ResearchPersonaHistoryEvent(
        event_type=event_type,
        summary=summary or patch.reason or "Applied research persona patch.",
        source_kind=patch.source_kind,
        created_at=created_at,
        actor=actor,
        patch=patch,
    )
    history_path = append_research_persona_history(event, data_root)
    tombstone_path = _would_tombstone_path(data_root)
    for tombstone in tombstones:
        tombstone_path = append_research_persona_tombstone(tombstone, data_root)

    payload.update(
        {
            "path": str(saved_path),
            "exists": saved_path.exists(),
            "history_path": str(history_path),
            "tombstone_path": str(tombstone_path),
        }
    )
    return payload


def research_persona_forget_fact_payload(
    fact_id: str,
    *,
    data_root: Path | None = None,
    reason: str | None = None,
    dry_run: bool = False,
    actor: str | None = None,
    now: str | None = None,
) -> dict[str, object]:
    """Forget a fact through a tombstone patch and return the apply payload."""

    fact_id = fact_id.strip()
    if not fact_id:
        raise ResearchPersonaError("fact_id must not be blank")
    created_at = now or _utc_now()
    tombstone = ResearchPersonaTombstone(
        fact_id=fact_id,
        reason=reason,
        source_kind="manual_patch",
        created_at=created_at,
    )
    patch = ResearchPersonaPatch(
        tombstones=[tombstone],
        operations=[
            ResearchPersonaPatchOperation(
                op="tombstone_fact",
                fact_id=fact_id,
                reason=reason,
            )
        ],
        source_kind="manual_patch",
        reason=reason or "Forgot research persona fact.",
    )
    payload = research_persona_apply_patch_payload(
        patch,
        data_root=data_root,
        dry_run=dry_run,
        actor=actor,
        summary=reason or f"Forgot research persona fact {fact_id}.",
        event_type="fact_forgotten",
        now=created_at,
    )
    payload["forgot_fact_id"] = fact_id
    return payload


def research_persona_export_capsule_payload(
    *,
    role: str,
    data_root: Path | None = None,
) -> dict[str, object]:
    """Return a prompt-safe capsule payload from the strict local profile."""

    persona = load_research_persona(data_root, strict=True)
    capsule: ResearchPersonaCapsule = build_research_persona_capsule(persona, role=role)
    return capsule.model_dump(mode="json")


def build_show_payload(*, cwd: Path | None = None, projection: str = "local") -> dict[str, object]:
    """CLI wrapper for the stored-profile show command."""

    return research_persona_show_payload(projection=projection)


def build_validate_payload(
    *,
    cwd: Path | None = None,
    document: object | None = None,
    input_path: str | None = None,
) -> dict[str, object]:
    """CLI wrapper for validating a stored profile, JSON file, or stdin."""

    path_text, exists = _input_path_payload(input_path, cwd=cwd)
    if document is not None:
        return research_persona_validate_payload(document, path=path_text, exists=exists)

    stored_path = research_persona_path()
    persona = load_research_persona(strict=True)
    return research_persona_validate_payload(
        persona.model_dump(mode="json"),
        path=str(stored_path),
        exists=stored_path.exists(),
    )


def build_diff_payload(
    *,
    cwd: Path | None = None,
    patch_document: object,
    patch_path: str | None = None,
) -> dict[str, object]:
    """CLI wrapper for a read-only patch diff."""

    payload = research_persona_diff_payload(patch_document)
    path_text, exists = _input_path_payload(patch_path, cwd=cwd)
    if path_text is not None:
        payload["patch_path"] = path_text
        payload["patch_exists"] = exists
    return payload


def build_apply_patch_payload(
    *,
    cwd: Path | None = None,
    patch_document: object,
    patch_path: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """CLI wrapper for applying a governed patch."""

    payload = research_persona_apply_patch_payload(patch_document, dry_run=dry_run, actor="gpd-cli")
    path_text, exists = _input_path_payload(patch_path, cwd=cwd)
    if path_text is not None:
        payload["patch_path"] = path_text
        payload["patch_exists"] = exists
    return payload


def build_forget_payload(
    *,
    cwd: Path | None = None,
    fact_id: str,
    reason: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """CLI wrapper for tombstoning one fact by id."""

    return research_persona_forget_fact_payload(
        fact_id,
        reason=reason,
        dry_run=dry_run,
        actor="gpd-cli",
    )


def build_export_capsule_payload(*, cwd: Path | None = None, role: str) -> dict[str, object]:
    """CLI wrapper for a prompt-safe role capsule."""

    return research_persona_export_capsule_payload(role=role)
