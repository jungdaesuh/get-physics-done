"""Raw stage-manifest duplicate diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from gpd.core import prompt_markdown_scan as _prompt_markdown_scan

_relative_path = _prompt_markdown_scan.relative_path


class StageManifestSource(Protocol):
    kind: str
    name: str
    repo_root: Path
    src_root: Path


def build_manifest_must_not_duplicate_entries(sources: Sequence[StageManifestSource]) -> tuple[object, ...]:
    """Return raw manifest duplicate diagnostics without relaxing strict validation."""

    from gpd.core import prompt_diagnostics_types as prompt_types

    rows = []
    for source in sources:
        if source.kind != "command":
            continue
        manifest_path = source.src_root / "specs" / "workflows" / f"{source.name}-stage-manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        stages = payload.get("stages")
        if not isinstance(stages, list):
            continue
        workflow_id = payload.get("workflow_id")
        if not isinstance(workflow_id, str):
            workflow_id = source.name
        for stage_index, raw_stage in enumerate(stages):
            if not isinstance(raw_stage, Mapping):
                continue
            raw_values = raw_stage.get("must_not_eager_load")
            if not isinstance(raw_values, list):
                continue
            positions: dict[str, list[int]] = {}
            for raw_index, raw_value in enumerate(raw_values):
                if isinstance(raw_value, str) and (value := raw_value.strip()):
                    positions.setdefault(value, []).append(raw_index)
            duplicate_entries = tuple(
                prompt_types.ManifestMustNotDuplicateEntry(
                    value=value,
                    raw_occurrence_count=len(indexes),
                    first_index=indexes[0],
                    duplicate_indexes=tuple(indexes[1:]),
                )
                for value, indexes in positions.items()
                if len(indexes) > 1
            )
            if not duplicate_entries:
                continue
            stage_id = raw_stage.get("id")
            if not isinstance(stage_id, str):
                stage_id = f"stage[{stage_index}]"
            rows.append(
                prompt_types.ManifestMustNotDuplicateEntriesDiagnostic(
                    workflow_id=workflow_id,
                    manifest_path=_relative_path(manifest_path, source.repo_root),
                    stage_id=stage_id,
                    stage_index=stage_index,
                    field_name="must_not_eager_load",
                    raw_entry_count=len(raw_values),
                    effective_unique_entry_count=len(positions),
                    duplicate_entry_count=sum(len(indexes) - 1 for indexes in positions.values()),
                    duplicate_entries=duplicate_entries,
                )
            )
    return tuple(sorted(rows, key=lambda row: (row.workflow_id, row.stage_index, row.stage_id)))


def manifest_must_not_duplicate_entries_totals(diagnostics: Sequence[object]) -> dict[str, int]:
    duplicated_authorities = {
        entry.value
        for diagnostic in diagnostics
        for entry in getattr(diagnostic, "duplicate_entries", ())
        if hasattr(entry, "value")
    }
    return {
        "manifest_must_not_duplicate_entry_count": sum(
            int(getattr(diagnostic, "duplicate_entry_count", 0)) for diagnostic in diagnostics
        ),
        "manifest_must_not_duplicate_stage_count": len(diagnostics),
        "manifest_must_not_duplicate_authority_count": len(duplicated_authorities),
    }
