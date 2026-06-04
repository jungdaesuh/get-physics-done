"""Phase 1 prompt-pressure rendering helpers.

This module keeps additive pressure-row rendering out of the main diagnostics
renderer, so the facade remains small while the raw JSON shape stays stable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar, cast

from gpd.core.prompt_diagnostics_types import PromptSurfaceItem, PromptSurfaceReport
from gpd.core.prompt_exactness_diagnostics import (
    bounded_exact_assertion_diagnostics as _bounded_exact_assertion_diagnostics,
)
from gpd.core.prompt_markdown_scan import top_limit as _top_limit

_T = TypeVar("_T")


def bounded_exactness_diagnostics(
    diagnostics: Mapping[str, object],
    top: int | None,
) -> Mapping[str, object]:
    payload = dict(_bounded_exact_assertion_diagnostics(diagnostics, top))
    if isinstance(payload.get("migration"), Mapping):
        migration_key = "migration"
    elif isinstance(payload.get("exactness_migration"), Mapping):
        migration_key = "exactness_migration"
    else:
        return payload

    migration = cast(Mapping[str, object], payload[migration_key])
    migration_payload = dict(migration)
    for row_key in ("files", "rows"):
        rows = _mapping_sequence(migration_payload.get(row_key))
        if rows:
            migration_payload[row_key] = [exactness_migration_row_to_dict(row) for row in _limited(rows, top)]
    payload[migration_key] = migration_payload
    payload["migration"] = migration_payload
    return payload


def stage_mechanics_prose_rows(report: PromptSurfaceReport, top: int | None) -> tuple[dict[str, object], ...]:
    mentions = _object_sequence(getattr(report, "stage_mechanics_prose_mentions", ()))
    return tuple(_stage_mechanics_prose_mention_to_dict(mention) for mention in _limited(mentions, top))


def manifest_must_not_duplicate_rows(report: PromptSurfaceReport, top: int | None) -> tuple[dict[str, object], ...]:
    rows = _object_sequence(getattr(report, "manifest_must_not_duplicate_entries", ()))
    return tuple(_manifest_must_not_duplicate_row_to_dict(row) for row in _limited(rows, top))


def exactness_migration_rows(
    diagnostics: Mapping[str, object],
    top: int | None,
) -> list[dict[str, object]]:
    migration = _mapping_get(diagnostics, "migration", "exactness_migration")
    if not migration:
        return []
    rows = _mapping_sequence(migration.get("files")) or _mapping_sequence(migration.get("rows"))
    return [exactness_migration_row_to_dict(row) for row in _limited(rows, top)]


def review_contract_frontload_rows(
    items: Sequence[PromptSurfaceItem],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    rows = [
        {
            "kind": item.kind,
            "name": item.name,
            "path": item.path,
            "sections": getattr(item, "review_contract_frontload_section_count", 0),
            "lines": getattr(item, "review_contract_frontload_line_count", 0),
            "chars": getattr(item, "review_contract_frontload_char_count", 0),
        }
        for item in items
        if (
            getattr(item, "review_contract_frontload_section_count", 0)
            or getattr(item, "review_contract_frontload_line_count", 0)
            or getattr(item, "review_contract_frontload_char_count", 0)
        )
    ]
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -cast(int, row["chars"]),
            -cast(int, row["lines"]),
            cast(str, row["kind"]),
            cast(str, row["name"]),
        ),
    )
    return _limited(sorted_rows, top)


def stage_total_int(totals: Mapping[str, object], *keys: str) -> int:
    stage_totals = _mapping_get(totals, "stage_diagnostics")
    return _row_int(stage_totals, *keys) or _row_int(totals, *keys)


def phase1_summary_lines(totals: Mapping[str, object]) -> list[str]:
    return [
        f"- Review-contract frontload chars: {totals.get('review_contract_frontload_char_count', 0)}",
        f"- Stage mechanics prose mentions: {totals.get('stage_mechanics_prose_count', 0)}",
        "- Manifest `must_not_eager_load` duplicate entries: "
        f"{stage_total_int(totals, 'manifest_must_not_duplicate_entry_count')}",
    ]


def phase1_markdown_sections(report: PromptSurfaceReport, top: int | None) -> list[str]:
    lines: list[str] = []
    lines.extend(_review_contract_frontload_markdown(report, top))
    lines.extend(_stage_mechanics_markdown(report, top))
    lines.extend(_manifest_duplicates_markdown(report, top))
    return lines


def exactness_migration_markdown(
    diagnostics: Mapping[str, object],
    top: int | None,
) -> list[str]:
    rows = exactness_migration_rows(diagnostics, top)
    if not rows:
        return []
    lines = [
        "",
        "## Exactness Migration",
        "",
        "| File | Machine exact | Public exact | Semantic candidate | Raw brittle | Helper calls | Gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row.get('path', '')}` | "
            f"{_row_int(row, 'machine_exact_assertions', 'machine_exact_keep_count', 'machine_contract_exact_assertions')} | "
            f"{_row_int(row, 'public_exact_assertions', 'public_exact_keep_count', 'public_ux_exact_assertions')} | "
            f"{_row_int(row, 'semantic_concept_candidate_assertions', 'semantic_concept_candidate_count')} | "
            f"{_row_int(row, 'raw_brittle_prose_assertions', 'raw_brittle_prose_count', 'brittle_prose_assertions')} | "
            f"{_row_int(row, 'taxonomy_helper_call_count')} | "
            f"{_markdown_cell(_row_text(row, 'taxonomy_helper_brittle_gate', 'gate'))} |"
        )
    return lines


def phase1_table_sections(report: PromptSurfaceReport, top: int | None) -> list[str]:
    lines: list[str] = []
    review_rows = [
        (
            str(row["kind"]),
            str(row["name"]),
            str(row["sections"]),
            str(row["lines"]),
            str(row["chars"]),
            str(row["path"]),
        )
        for row in review_contract_frontload_rows(report.items, top)
    ]
    lines.extend(
        _fixed_table_section_lines(
            "review-contract frontload",
            ("kind", "name", "sections", "lines", "chars", "path"),
            review_rows,
        )
    )
    stage_rows = [
        (
            str(row["path"]),
            str(row["line"]),
            ", ".join(str(category) for category in row["categories"]),
            str(row["severity"]),
            str(row["snippet"]),
        )
        for row in stage_mechanics_prose_rows(report, top)
    ]
    lines.extend(
        _fixed_table_section_lines(
            "stage mechanics prose",
            ("path", "line", "categories", "severity", "snippet"),
            stage_rows,
        )
    )
    manifest_rows = [
        (
            str(row["workflow_id"]),
            str(row["stage_id"]),
            str(row["raw_entry_count"]),
            str(row["effective_unique_entry_count"]),
            str(row["duplicate_entry_count"]),
            ", ".join(
                str(entry.get("value", "")) for entry in cast(Sequence[Mapping[str, object]], row["duplicate_entries"])
            ),
        )
        for row in manifest_must_not_duplicate_rows(report, top)
    ]
    lines.extend(
        _fixed_table_section_lines(
            "manifest must_not_eager_load duplicates",
            ("workflow", "stage", "raw_entries", "unique_entries", "duplicate_entries", "values"),
            manifest_rows,
        )
    )
    return lines


def exactness_migration_table_section(diagnostics: Mapping[str, object], top: int | None) -> list[str]:
    rows = [
        (
            str(row.get("path", "")),
            str(
                _row_int(
                    row, "machine_exact_assertions", "machine_exact_keep_count", "machine_contract_exact_assertions"
                )
            ),
            str(_row_int(row, "public_exact_assertions", "public_exact_keep_count", "public_ux_exact_assertions")),
            str(_row_int(row, "semantic_concept_candidate_assertions", "semantic_concept_candidate_count")),
            str(_row_int(row, "raw_brittle_prose_assertions", "raw_brittle_prose_count", "brittle_prose_assertions")),
            str(_row_int(row, "taxonomy_helper_call_count")),
            _row_text(row, "taxonomy_helper_brittle_gate", "gate"),
        )
        for row in exactness_migration_rows(diagnostics, top)
    ]
    return _fixed_table_section_lines(
        "exactness migration",
        (
            "file",
            "machine_exact",
            "public_exact",
            "semantic_candidate",
            "raw_brittle",
            "helper_calls",
            "gate",
        ),
        rows,
    )


def prior_stage_residue_markdown(rows: Sequence[Mapping[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = [
        "",
        "## Prior-Stage Residue Contributors",
        "",
        "| Authority | Occurrences | Workflows | Stages | Expanded chars | Expanded lines | First-turn chains | Transitive includes | Workflow IDs | Stage IDs | Eager via |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{_row_text(row, 'authority')}` | {_row_int(row, 'occurrence_count')} | "
            f"{_row_int(row, 'workflow_count')} | {_row_int(row, 'stage_count')} | "
            f"{_row_int(row, 'expanded_char_count')} | {_row_int(row, 'expanded_line_count')} | "
            f"{_row_int(row, 'first_turn_chain_count')} | {_row_int(row, 'transitive_include_count')} | "
            f"{_markdown_cell(_row_sequence_text(row, 'workflows'))} | "
            f"{_markdown_cell(_row_sequence_text(row, 'stages'))} | "
            f"{_markdown_cell(_row_sequence_text(row, 'eager_via'))} |"
        )
    return lines


def prior_stage_residue_table_section(rows: Sequence[Mapping[str, object]]) -> list[str]:
    table_rows = [
        (
            _row_text(row, "authority"),
            str(_row_int(row, "occurrence_count")),
            str(_row_int(row, "workflow_count")),
            str(_row_int(row, "stage_count")),
            str(_row_int(row, "expanded_char_count")),
            str(_row_int(row, "expanded_line_count")),
            str(_row_int(row, "first_turn_chain_count")),
            str(_row_int(row, "transitive_include_count")),
            _row_sequence_text(row, "workflows"),
            _row_sequence_text(row, "stages"),
            _row_sequence_text(row, "eager_via"),
        )
        for row in rows
    ]
    return _fixed_table_section_lines(
        "prior-stage residue contributors",
        (
            "authority",
            "occurrences",
            "workflows",
            "stages",
            "expanded_chars",
            "expanded_lines",
            "first_turn_chains",
            "transitive_includes",
            "workflow_ids",
            "stage_ids",
            "eager_via",
        ),
        table_rows,
    )


def _review_contract_frontload_markdown(report: PromptSurfaceReport, top: int | None) -> list[str]:
    rows = review_contract_frontload_rows(report.items, top)
    if not rows:
        return []
    lines = [
        "",
        "## Review-Contract Frontload",
        "",
        "| Kind | Name | Sections | Lines | Chars | Path |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['kind']} | `{row['name']}` | {row['sections']} | {row['lines']} | "
            f"{row['chars']} | `{row['path']}` |"
        )
    return lines


def _stage_mechanics_markdown(report: PromptSurfaceReport, top: int | None) -> list[str]:
    rows = stage_mechanics_prose_rows(report, top)
    if not rows:
        return []
    lines = [
        "",
        "## Stage Mechanics Prose",
        "",
        "| Path | Line | Categories | Severity | Snippet |",
        "|---|---:|---|---|---|",
    ]
    for row in rows:
        categories = ", ".join(str(category) for category in row["categories"])
        lines.append(
            f"| `{row['path']}` | {row['line']} | `{_markdown_cell(categories)}` | "
            f"{row['severity']} | `{_markdown_cell(str(row['snippet']))}` |"
        )
    return lines


def _manifest_duplicates_markdown(report: PromptSurfaceReport, top: int | None) -> list[str]:
    rows = manifest_must_not_duplicate_rows(report, top)
    if not rows:
        return []
    lines = [
        "",
        "## Manifest must_not_eager_load Duplicates",
        "",
        "| Workflow | Stage | Raw entries | Unique entries | Duplicate entries | Values |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        values = ", ".join(
            str(entry.get("value", "")) for entry in cast(Sequence[Mapping[str, object]], row["duplicate_entries"])
        )
        lines.append(
            f"| `{row['workflow_id']}` | `{row['stage_id']}` | {row['raw_entry_count']} | "
            f"{row['effective_unique_entry_count']} | {row['duplicate_entry_count']} | "
            f"`{_markdown_cell(values)}` |"
        )
    return lines


def _stage_mechanics_prose_mention_to_dict(mention: object) -> dict[str, object]:
    return {
        "path": _object_text(mention, "path"),
        "line": _object_int(mention, "line"),
        "categories": list(_object_sequence(_object_get(mention, "categories", default=()))),
        "severity": _object_text(mention, "severity"),
        "snippet": _object_text(mention, "snippet"),
    }


def _manifest_must_not_duplicate_row_to_dict(row: object) -> dict[str, object]:
    return {
        "workflow_id": _object_text(row, "workflow_id"),
        "manifest_path": _object_text(row, "manifest_path"),
        "stage_id": _object_text(row, "stage_id"),
        "stage_index": _object_int(row, "stage_index"),
        "field_name": _object_text(row, "field_name") or "must_not_eager_load",
        "raw_entry_count": _object_int(row, "raw_entry_count"),
        "effective_unique_entry_count": _object_int(row, "effective_unique_entry_count"),
        "duplicate_entry_count": _object_int(row, "duplicate_entry_count"),
        "duplicate_entries": [
            _manifest_must_not_duplicate_entry_to_dict(entry)
            for entry in _object_sequence(_object_get(row, "duplicate_entries", default=()))
        ],
    }


def _manifest_must_not_duplicate_entry_to_dict(entry: object) -> dict[str, object]:
    return {
        "value": _object_text(entry, "value"),
        "raw_occurrence_count": _object_int(entry, "raw_occurrence_count"),
        "first_index": _object_int(entry, "first_index"),
        "duplicate_indexes": [
            _object_int(index) for index in _object_sequence(_object_get(entry, "duplicate_indexes", default=()))
        ],
    }


def exactness_migration_row_to_dict(row: object) -> dict[str, object]:
    if isinstance(row, Mapping):
        return dict(row)
    return {
        "path": _object_text(row, "path"),
        "machine_exact_assertions": _object_int(
            row,
            "machine_exact_assertions",
            "machine_exact_keep_count",
            "machine_contract_exact_assertions",
        ),
        "public_exact_assertions": _object_int(
            row,
            "public_exact_assertions",
            "public_exact_keep_count",
            "public_ux_exact_assertions",
        ),
        "semantic_concept_candidate_assertions": _object_int(
            row,
            "semantic_concept_candidate_assertions",
            "semantic_concept_candidate_count",
        ),
        "raw_brittle_prose_assertions": _object_int(
            row,
            "raw_brittle_prose_assertions",
            "raw_brittle_prose_count",
            "brittle_prose_assertions",
        ),
        "uses_taxonomy_helpers": bool(_object_get(row, "uses_taxonomy_helpers", default=False)),
        "taxonomy_helper_call_count": _object_int(row, "taxonomy_helper_call_count"),
        "semantic_helper_call_count": _object_int(row, "semantic_helper_call_count"),
        "taxonomy_helper_brittle_baseline": _object_get(row, "taxonomy_helper_brittle_baseline"),
        "taxonomy_helper_brittle_delta": _object_get(row, "taxonomy_helper_brittle_delta"),
        "taxonomy_helper_brittle_gate": _object_text(row, "taxonomy_helper_brittle_gate", "gate"),
    }


def _row_int(row: Mapping[str, object], *keys: str) -> int:
    for key in keys:
        value = row.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 0


def _row_text(row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return str(value)
    return ""


def _row_sequence_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return "" if value is None else str(value)
    return ", ".join(
        " > ".join(str(part) for part in item)
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray))
        else str(item)
        for item in value
    )


def _mapping_get(row: Mapping[str, object], *keys: str) -> Mapping[str, object]:
    for key in keys:
        value = row.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _mapping_sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _object_get(value: object, key: str, *, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _object_int(value: object, *keys: str) -> int:
    if not keys:
        return value if isinstance(value, int) and not isinstance(value, bool) else 0
    for key in keys:
        raw = _object_get(value, key)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
    return 0


def _object_text(value: object, *keys: str) -> str:
    for key in keys:
        raw = _object_get(value, key)
        if raw is not None:
            return str(raw)
    return ""


def _object_sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _limited(rows: Sequence[_T], top: int | None) -> tuple[_T, ...]:
    limit = _top_limit(top)
    if limit is None:
        return tuple(rows)
    return tuple(rows[:limit])


def _fixed_table_lines(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row, strict=True)]

    def render_row(row: Sequence[str]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()

    return [render_row(headers), render_row(tuple("-" * width for width in widths)), *(render_row(row) for row in rows)]


def _fixed_table_section_lines(
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> list[str]:
    if not rows:
        return []
    return ["", title, *_fixed_table_lines(headers, rows)]


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "\\`").replace("\n", " ")
