"""Workflow-neutral staged-init payload assembly."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from gpd.core.workflow_staging import (
    WorkflowStage,
    WorkflowStageManifest,
    load_workflow_stage_manifest,
)


@dataclass(frozen=True, slots=True)
class StagedInitAssemblyContext:
    workflow_id: str
    stage: WorkflowStage
    required_fields: frozenset[str]
    cwd: Path
    base_payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class StagedInitProvider:
    name: str
    trigger_fields: frozenset[str]
    build: Callable[[StagedInitAssemblyContext], Mapping[str, object]]


def assemble_staged_init_payload(
    *,
    workflow_id: str,
    stage_id: str,
    cwd: Path,
    base_payload: Mapping[str, object],
    manifest: WorkflowStageManifest | None = None,
    providers: Iterable[StagedInitProvider] = (),
    postprocessors: Iterable[Callable[[StagedInitAssemblyContext, dict[str, object]], None]] = (),
    validate_init_spec: bool = True,
    error_label: str | None = None,
) -> dict[str, object]:
    """Assemble one staged-init payload from a manifest stage and lazy field providers."""
    active_manifest = manifest if manifest is not None else load_workflow_stage_manifest(workflow_id)
    label = error_label or workflow_id
    stage = _stage_by_id(active_manifest, stage_id, label=label)
    required_fields = frozenset(stage.required_init_fields)
    context = StagedInitAssemblyContext(
        workflow_id=workflow_id,
        stage=stage,
        required_fields=required_fields,
        cwd=cwd,
        base_payload=base_payload,
    )

    staged_source = dict(base_payload)
    for provider in providers:
        if required_fields.isdisjoint(provider.trigger_fields):
            continue
        staged_source.update(provider.build(context))

    for postprocessor in postprocessors:
        postprocessor(context, staged_source)

    missing_fields = [field for field in stage.required_init_fields if field not in staged_source]
    if missing_fields:
        raise ValueError(
            f"{label} stage {stage_id!r} requires unavailable init field(s): {', '.join(missing_fields)}"
        )

    staged_payload = {field: staged_source[field] for field in stage.required_init_fields}
    init_spec_id = stage.init_spec_id
    if validate_init_spec and init_spec_id:
        _validate_init_spec_payload(
            workflow_id=workflow_id,
            stage=stage,
            init_spec_id=init_spec_id,
            payload=staged_payload,
            label=label,
        )

    staged_payload["staged_loading"] = active_manifest.staged_loading_payload(stage.id)
    _assert_active_payload_shape(staged_payload, stage)
    return staged_payload


def _stage_by_id(manifest: WorkflowStageManifest, stage_id: str, *, label: str) -> WorkflowStage:
    try:
        return manifest.stage_by_id(stage_id)
    except KeyError as exc:
        raise ValueError(
            f"Unknown {label} stage {stage_id!r}. Allowed values: {', '.join(manifest.stage_ids())}."
        ) from exc


def _validate_init_spec_payload(
    *,
    workflow_id: str,
    stage: WorkflowStage,
    init_spec_id: str,
    payload: Mapping[str, object],
    label: str,
) -> None:
    from gpd.core.workflow_init_specs import validate_staged_init_payload

    try:
        validate_staged_init_payload(workflow_id, stage.id, init_spec_id, payload)
    except ValueError as exc:
        raise ValueError(
            f"{label} staged init payload validation failed "
            f"(workflow={workflow_id}, stage={stage.id}, init_spec_id={init_spec_id}): {exc}"
        ) from exc


def _assert_active_payload_shape(payload: Mapping[str, object], stage: WorkflowStage) -> None:
    expected_keys = set(stage.required_init_fields) | {"staged_loading"}
    observed_keys = set(payload)
    if observed_keys != expected_keys:
        raise AssertionError(
            f"staged init payload keys must match active manifest fields plus staged_loading; "
            f"missing={sorted(expected_keys - observed_keys)}, extra={sorted(observed_keys - expected_keys)}"
        )


__all__ = [
    "StagedInitAssemblyContext",
    "StagedInitProvider",
    "assemble_staged_init_payload",
]
