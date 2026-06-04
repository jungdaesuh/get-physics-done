"""Payload and text renderers for prompt-surface diagnostics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from gpd.core import prompt_semantic_duplicate_diagnostics
from gpd.core.prompt_diagnostics_types import PromptSurfaceItem, PromptSurfaceReport, StageAwareWorkflowPromptMetric
from gpd.core.prompt_exactness_diagnostics import (
    EXACT_ASSERTION_THRESHOLDS as _EXACT_ASSERTION_THRESHOLDS,
)
from gpd.core.prompt_exactness_diagnostics import (
    exact_assertion_file_rows as _exact_assertion_file_rows,
)
from gpd.core.prompt_markdown_scan import top_limit as _top_limit
from gpd.core.prompt_stage_diagnostics import (
    repeated_prior_stage_residue_rows as _core_repeated_prior_stage_residue_rows,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_authority_top_rows as _stage_authority_top_rows,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_diagnostic_to_dict as _stage_diagnostic_to_dict,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_init_field_top_rows as _stage_init_field_top_rows,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_top_prompt_rows as _stage_top_prompt_rows,
)
from gpd.core.prompt_stage_diagnostics import (
    top_stage_diagnostics as _top_stage_diagnostics,
)
from gpd.core.prompt_surface_phase1_rendering import (
    bounded_exactness_diagnostics as _bounded_exactness_diagnostics,
)
from gpd.core.prompt_surface_phase1_rendering import (
    exactness_migration_markdown as _exactness_migration_markdown,
)
from gpd.core.prompt_surface_phase1_rendering import (
    exactness_migration_rows as _exactness_migration_rows,
)
from gpd.core.prompt_surface_phase1_rendering import (
    exactness_migration_table_section as _exactness_migration_table_section,
)
from gpd.core.prompt_surface_phase1_rendering import (
    manifest_must_not_duplicate_rows as _manifest_must_not_duplicate_rows,
)
from gpd.core.prompt_surface_phase1_rendering import (
    phase1_markdown_sections as _phase1_markdown_sections,
)
from gpd.core.prompt_surface_phase1_rendering import (
    phase1_summary_lines as _phase1_summary_lines,
)
from gpd.core.prompt_surface_phase1_rendering import (
    phase1_table_sections as _phase1_table_sections,
)
from gpd.core.prompt_surface_phase1_rendering import (
    prior_stage_residue_markdown as _prior_stage_residue_markdown,
)
from gpd.core.prompt_surface_phase1_rendering import (
    prior_stage_residue_table_section as _prior_stage_residue_table_section,
)
from gpd.core.prompt_surface_phase1_rendering import (
    stage_mechanics_prose_rows as _stage_mechanics_prose_rows,
)
from gpd.core.prompt_surface_serialization import (
    forbidden_child_return_synthesis_mention_to_dict as _forbidden_child_return_synthesis_mention_to_dict,
)
from gpd.core.prompt_surface_serialization import (
    invalid_frontmatter_example_to_dict as _invalid_frontmatter_example_to_dict,
)
from gpd.core.prompt_surface_serialization import (
    invalid_gpd_return_example_to_dict as _invalid_gpd_return_example_to_dict,
)
from gpd.core.prompt_surface_serialization import (
    prompt_item_to_dict as _prompt_item_to_dict,
)
from gpd.core.prompt_surface_serialization import (
    return_field_mention_to_dict as _return_field_mention_to_dict,
)
from gpd.core.prompt_surface_serialization import (
    runtime_top_prompt_rows as _runtime_top_prompt_rows,
)
from gpd.core.prompt_surface_serialization import (
    runtime_top_prompts_to_dict as _runtime_top_prompts_to_dict,
)


def report_to_dict(report: PromptSurfaceReport, top: int | None = None) -> dict[str, object]:
    """Convert a report into JSON-serializable primitives."""

    limit = _top_limit(top)
    semantic_example_limit = prompt_semantic_duplicate_diagnostics.semantic_example_limit(top)
    stage_authority_rows = _stage_authority_top_prompt_rows(report.stage_diagnostics, top)
    stage_init_field_rows = _stage_init_field_pressure_rows(report.stage_diagnostics, top)
    repeated_residue_rows = _repeated_prior_stage_residue_rows(report.stage_diagnostics, top)
    stage_mechanics_rows = _stage_mechanics_prose_rows(report, top)
    manifest_duplicate_rows = _manifest_must_not_duplicate_rows(report, top)
    exactness = _bounded_exactness_diagnostics(report.exact_assertion_diagnostics, top)
    return {
        "schema_version": report.schema_version,
        "repo_root": report.repo_root,
        "totals": report.totals,
        "items": [_prompt_item_to_dict(item) for item in _top_items(report.items, top)],
        "runtime_top_prompts": _runtime_top_prompts_to_dict(report.items, top),
        "stage_diagnostics": [
            _stage_diagnostic_to_dict(metric) for metric in _top_stage_diagnostics(report.stage_diagnostics, top)
        ],
        "stage_authority_top_prompts": list(stage_authority_rows),
        "stage_authority_top": list(stage_authority_rows),
        "stage_init_field_diagnostics": list(stage_init_field_rows),
        "stage_field_payload_pressure": list(stage_init_field_rows),
        "repeated_prior_stage_residue_rows": list(repeated_residue_rows),
        "stage_mechanics_prose_mentions": list(stage_mechanics_rows),
        "manifest_must_not_duplicate_entries": list(manifest_duplicate_rows),
        "invalid_gpd_return_examples": [
            _invalid_gpd_return_example_to_dict(example) for example in report.invalid_gpd_return_examples
        ],
        "invalid_frontmatter_examples": [
            _invalid_frontmatter_example_to_dict(example) for example in report.invalid_frontmatter_examples
        ],
        "disallowed_return_field_mentions": [
            _return_field_mention_to_dict(mention) for mention in report.disallowed_return_field_mentions
        ],
        "forbidden_child_return_synthesis_mentions": [
            _forbidden_child_return_synthesis_mention_to_dict(mention)
            for mention in report.forbidden_child_return_synthesis_mentions
        ],
        "duplicate_invariants": [
            {
                "phrase": group.phrase,
                "occurrence_count": group.occurrence_count,
                "file_count": group.file_count,
                "severity": group.severity,
                "locations": list(group.locations),
            }
            for group in report.duplicate_invariants[:limit]
        ],
        "semantic_duplicate_invariants": [
            {
                "category": group.category,
                "label": group.label,
                "occurrence_count": group.occurrence_count,
                "file_count": group.file_count,
                "non_reference_occurrence_count": group.non_reference_occurrence_count,
                "non_reference_file_count": group.non_reference_file_count,
                "severity": group.severity,
                "canonical_references": list(group.canonical_references),
                "suggested_action": group.suggested_action,
                "examples": [
                    {
                        "path": example.path,
                        "line": example.line,
                        "category": example.category,
                        "snippet": example.snippet,
                        "matched_terms": list(example.matched_terms),
                        "is_reference_or_template": example.is_reference_or_template,
                    }
                    for example in group.examples[:semantic_example_limit]
                ],
            }
            for group in report.semantic_duplicate_invariants[:limit]
        ],
        "exact_assertion_diagnostics": exactness,
        "exactness_migration_rows": _exactness_migration_rows(exactness, top),
        "exact_prose_assertion_files": [dict(entry) for entry in report.exact_prose_assertion_files[:limit]],
        "warnings": list(report.warnings),
    }


def _stage_authority_top_prompt_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    return tuple(dict(row) for row in _stage_authority_top_rows(stage_diagnostics, top))


def _stage_init_field_pressure_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    return tuple(dict(row) for row in _stage_init_field_top_rows(stage_diagnostics, top))


def _repeated_prior_stage_residue_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    return tuple(
        _qualified_repeated_residue_row(dict(row))
        for row in _core_repeated_prior_stage_residue_rows(stage_diagnostics, top)
    )


def _qualified_repeated_residue_row(row: dict[str, object]) -> dict[str, object]:
    workflows = row.get("workflows")
    stages = row.get("stages")
    if not isinstance(workflows, Sequence) or isinstance(workflows, (str, bytes, bytearray)) or len(workflows) != 1:
        return row
    if not isinstance(stages, Sequence) or isinstance(stages, (str, bytes, bytearray)):
        return row
    prefix = f"{workflows[0]}."
    row["stages"] = [stage if (stage := str(value)).startswith(prefix) else f"{prefix}{stage}" for value in stages]
    return row


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


def render_prompt_surface_markdown(report: PromptSurfaceReport, top: int | None = None) -> str:
    """Render a human-readable markdown report."""

    top_items = _top_items(report.items, top)
    totals = report.totals
    lines = [
        "# Prompt Surface Diagnostics",
        "",
        f"- Schema version: `{report.schema_version}`",
        f"- Repo root: `{report.repo_root}`",
        f"- Prompt sources: {totals.get('item_count', 0)}",
        f"- Expanded chars: {totals.get('expanded_char_count', 0)}",
        f"- Invalid `gpd_return` examples: {len(report.invalid_gpd_return_examples)}",
        f"- Invalid verification frontmatter examples: {len(report.invalid_frontmatter_examples)}",
        f"- Disallowed `gpd_return` field mentions: {len(report.disallowed_return_field_mentions)}",
        f"- Forbidden child `gpd_return` synthesis instructions: "
        f"{len(report.forbidden_child_return_synthesis_mentions)}",
        f"- Hard-gate lines: {totals.get('hard_gate_line_count', 0)}",
        f"- Shell parsing lines: {totals.get('shell_parsing_line_count', 0)}",
        *_phase1_summary_lines(totals),
        "",
        "## Top Prompt Sources",
        "",
        "| Rank | Kind | Name | Expanded chars | Raw lines | Includes | Hard gates | Shell parse | Schemas | Invalid returns | Invalid frontmatter | Bad fields | Rigidity |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, item in enumerate(top_items, start=1):
        lines.append(
            f"| {index} | {item.kind} | `{item.name}` | {item.expanded_char_count} | {item.raw_line_count} | "
            f"{item.raw_include_count} | {item.hard_gate_line_count} | {item.shell_parsing_line_count} | "
            f"{item.visible_schema_example_count} | {item.invalid_gpd_return_example_count} | "
            f"{item.invalid_frontmatter_example_count} | "
            f"{item.disallowed_return_field_mention_count} | "
            f"{item.rigidity_index} |"
        )

    lines.extend(_phase1_markdown_sections(report, top))

    if report.invalid_gpd_return_examples:
        lines.extend(
            [
                "",
                "## Invalid `gpd_return` Examples",
                "",
                "| Path | Lines | Errors | Preview |",
                "|---|---:|---|---|",
            ]
        )
        for example in report.invalid_gpd_return_examples:
            lines.append(
                f"| `{example.path}` | {example.start_line}-{example.end_line} | "
                f"{_markdown_table_cell('; '.join(example.errors))} | "
                f"`{_markdown_table_cell(example.preview)}` |"
            )

    if report.invalid_frontmatter_examples:
        lines.extend(
            [
                "",
                "## Invalid Verification Frontmatter Examples",
                "",
                "| Path | Lines | Schema | Fields | Errors | Preview |",
                "|---|---:|---|---|---|---|",
            ]
        )
        for example in report.invalid_frontmatter_examples:
            lines.append(
                f"| `{example.path}` | {example.start_line}-{example.end_line} | `{example.schema_name}` | "
                f"{_markdown_table_cell(', '.join(example.fields))} | "
                f"{_markdown_table_cell('; '.join(example.errors))} | "
                f"`{_markdown_table_cell(example.preview)}` |"
            )

    if report.disallowed_return_field_mentions:
        lines.extend(
            [
                "",
                "## Disallowed `gpd_return` Field Mentions",
                "",
                "| Path | Line | Field | Kind | Suggestion | Snippet |",
                "|---|---:|---|---|---|---|",
            ]
        )
        for mention in report.disallowed_return_field_mentions:
            suggestion = mention.suggestion or ""
            lines.append(
                f"| `{mention.path}` | {mention.line} | `{mention.field}` | {mention.mention_kind} | "
                f"{_markdown_table_cell(suggestion)} | `{_markdown_table_cell(mention.snippet)}` |"
            )

    if report.forbidden_child_return_synthesis_mentions:
        lines.extend(
            [
                "",
                "## Forbidden Child `gpd_return` Synthesis Instructions",
                "",
                "| Path | Line | Action | Snippet |",
                "|---|---:|---|---|",
            ]
        )
        for mention in report.forbidden_child_return_synthesis_mentions:
            lines.append(
                f"| `{mention.path}` | {mention.line} | `{mention.action}` | "
                f"`{_markdown_table_cell(mention.snippet)}` |"
            )

    runtime_totals = cast(Mapping[str, Mapping[str, object]], totals.get("runtime_projection", {}))
    if runtime_totals:
        lines.extend(
            [
                "",
                "## Runtime Projection Totals",
                "",
                "| Runtime | Native includes | Items | Projected chars | Char delta | Includes | Runtime notes | Bridge calls |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for runtime, metric in sorted(runtime_totals.items()):
            lines.append(
                f"| `{runtime}` | {str(metric.get('native_include_support', False)).lower()} | "
                f"{metric.get('item_count', 0)} | {metric.get('char_count', 0)} | "
                f"{metric.get('char_delta', 0)} | "
                f"{metric.get('include_count', 0)} | {metric.get('runtime_note_count', 0)} | "
                f"{metric.get('bridge_command_occurrences', 0)} |"
            )

    runtime_top_prompts = _runtime_top_prompt_rows(report.items, top)
    if runtime_top_prompts:
        lines.extend(
            [
                "",
                "## Runtime Top Prompts",
                "",
                "| Runtime | Rank | Native includes | Kind | Name | Projected chars | Expanded chars | Char delta | Line delta | Includes | Runtime notes | Shell fences | Shell rewrites | Bridge calls |",
                "|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        ranks_by_runtime: dict[str, int] = defaultdict(int)
        for row in runtime_top_prompts:
            runtime = str(row["runtime"])
            ranks_by_runtime[runtime] += 1
            lines.append(
                f"| `{runtime}` | {ranks_by_runtime[runtime]} | "
                f"{str(row['native_include_support']).lower()} | {row['kind']} | `{row['name']}` | "
                f"{row['projected_char_count']} | {row['expanded_char_count']} | "
                f"{row['char_delta']} | {row['line_delta']} | {row['include_count']} | "
                f"{row['runtime_note_count']} | {row['shell_fence_count']} | "
                f"{row['shell_rewrite_count']} | {row['bridge_command_occurrences']} |"
            )

    stage_top_prompts = _stage_top_prompt_rows(report.stage_diagnostics, top)
    if stage_top_prompts:
        lines.extend(
            [
                "",
                "## Stage-Aware Staged Loading",
                "",
                "| Workflow | Stage | First-turn chars | Eager chars | Lazy chars | Residue chars | Residue lines | Residue records | Violations |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in stage_top_prompts:
            lines.append(
                f"| `{row['workflow_id']}` | `{row['stage_id']}` | {row['first_turn_char_count']} | "
                f"{row['eager_char_count']} | {row['lazy_char_count']} | "
                f"{row['prior_stage_residue_char_count']} | {row['prior_stage_residue_line_count']} | "
                f"{row['prior_stage_residue_count']} | {row['violation_count']} |"
            )

    lines.extend(_prior_stage_residue_markdown(_repeated_prior_stage_residue_rows(report.stage_diagnostics, top)))

    stage_authority_rows = _stage_authority_top_prompt_rows(report.stage_diagnostics, top)
    if stage_authority_rows:
        lines.extend(
            [
                "",
                "## Stage Authority Hotspots",
                "",
                "| Workflow | Stage | Bucket | Authority | Expanded chars | Lines | Includes | Transitive includes |",
                "|---|---|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in stage_authority_rows:
            lines.append(
                f"| `{_row_text(row, 'workflow_id')}` | `{_row_text(row, 'stage_id')}` | "
                f"{_row_text(row, 'bucket')} | `{_row_text(row, 'authority')}` | "
                f"{_row_int(row, 'expanded_char_count')} | {_row_int(row, 'expanded_line_count')} | "
                f"{_row_int(row, 'raw_include_count')} | "
                f"{_row_int(row, 'transitive_include_count')} |"
            )

    stage_init_field_rows = _stage_init_field_pressure_rows(report.stage_diagnostics, top)
    if stage_init_field_rows:
        lines.extend(
            [
                "",
                "## Staged-Init Field Pressure",
                "",
                "| Workflow | Stage | Required fields | Likely bulky | Field | Kind | Pressure | Selections |",
                "|---|---|---:|---:|---|---|---|---:|",
            ]
        )
        for row in stage_init_field_rows:
            lines.append(
                f"| `{_row_text(row, 'workflow_id')}` | `{_row_text(row, 'stage_id')}` | "
                f"{_row_int(row, 'required_init_field_count')} | "
                f"{_row_int(row, 'likely_bulky_field_count')} | `{_row_text(row, 'field_name')}` | "
                f"{_row_text(row, 'field_kind_guess')} | {_row_text(row, 'field_pressure_class')} | "
                f"{_row_int(row, 'selection_count')} |"
            )

    duplicate_groups = report.duplicate_invariants[: top or len(report.duplicate_invariants)]
    if duplicate_groups:
        lines.extend(
            [
                "",
                "## Duplicate Invariants",
                "",
                "| Severity | Occurrences | Files | Phrase |",
                "|---|---:|---:|---|",
            ]
        )
        for group in duplicate_groups:
            lines.append(f"| {group.severity} | {group.occurrence_count} | {group.file_count} | `{group.phrase}` |")

    semantic_groups = report.semantic_duplicate_invariants[: top or len(report.semantic_duplicate_invariants)]
    if semantic_groups:
        lines.extend(
            [
                "",
                "## Semantic Duplicate Invariants",
                "",
                "| Severity | Category | Occurrences | Non-ref occurrences | Files | Non-ref files | Canonical refs | Suggested action |",
                "|---|---|---:|---:|---:|---:|---|---|",
            ]
        )
        for group in semantic_groups:
            refs = ", ".join(Path(reference).name for reference in group.canonical_references)
            lines.append(
                f"| {group.severity} | `{group.category}` | {group.occurrence_count} | "
                f"{group.non_reference_occurrence_count} | {group.file_count} | {group.non_reference_file_count} | "
                f"{_markdown_table_cell(refs)} | "
                f"{_markdown_table_cell(group.suggested_action)} |"
            )
        example_limit = prompt_semantic_duplicate_diagnostics.semantic_example_limit(top)
        for group in semantic_groups:
            examples = group.examples[:example_limit]
            if not examples:
                continue
            lines.extend(["", f"### `{group.category}` Examples", ""])
            for example in examples:
                lines.append(f"- `{example.path}:{example.line}` - {_markdown_table_cell(example.snippet)}")

    exact_files = _exact_assertion_file_rows(report.exact_assertion_diagnostics, top)
    if exact_files:
        brittle_threshold = _EXACT_ASSERTION_THRESHOLDS["brittle_prose_assertions"]
        lines.extend(
            [
                "",
                "## Prompt-Test Exactness",
                "",
                f"Thresholds: brittle prose warn > {brittle_threshold['warn']}, fail > {brittle_threshold['fail']}.",
                "",
                "| File | Exact | Machine | Public UX | Brittle prose | Brittle % | Severity |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for entry in exact_files:
            brittle_density = 100 * cast(float, entry.get("brittle_prose_density", 0.0))
            lines.append(
                f"| `{entry.get('path', '')}` | {entry.get('exact_assertion_count', 0)} | "
                f"{entry.get('machine_contract_exact_assertions', 0)} | "
                f"{entry.get('public_ux_exact_assertions', 0)} | "
                f"{entry.get('brittle_prose_assertions', 0)} | "
                f"{brittle_density:.1f}% | {entry.get('severity', 'info')} |"
            )

    lines.extend(_exactness_migration_markdown(report.exact_assertion_diagnostics, top))

    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)

    return "\n".join(lines) + "\n"


def render_prompt_surface_table(report: PromptSurfaceReport, top: int | None = None) -> str:
    """Render a compact fixed-width table for terminal output."""

    rows = [
        (
            item.kind,
            item.name,
            str(item.expanded_char_count),
            str(item.raw_include_count),
            str(item.visible_schema_example_count),
            str(item.invalid_gpd_return_example_count),
            str(item.invalid_frontmatter_example_count),
            str(item.disallowed_return_field_mention_count),
            str(item.hard_gate_line_count),
            str(item.shell_parsing_line_count),
            str(item.rigidity_index),
        )
        for item in _top_items(report.items, top)
    ]
    headers = (
        "kind",
        "name",
        "expanded_chars",
        "includes",
        "schemas",
        "invalid",
        "bad_frontmatter",
        "bad_fields",
        "hard_gates",
        "shell_parse",
        "rigidity",
    )
    lines = _fixed_table_lines(headers, rows)
    lines.extend(_phase1_table_sections(report, top))
    runtime_rows = [
        (
            str(row["runtime"]),
            str(row["kind"]),
            str(row["name"]),
            str(row["projected_char_count"]),
            str(row["expanded_char_count"]),
            str(row["char_delta"]),
            str(row["line_delta"]),
            str(row["include_count"]),
            str(row["runtime_note_count"]),
            str(row["shell_fence_count"]),
            str(row["shell_rewrite_count"]),
            str(row["bridge_command_occurrences"]),
        )
        for row in _runtime_top_prompt_rows(report.items, top)
    ]
    runtime_headers = (
        "runtime",
        "kind",
        "name",
        "projected_chars",
        "expanded_chars",
        "char_delta",
        "line_delta",
        "includes",
        "runtime_notes",
        "shell_fences",
        "shell_rewrites",
        "bridge_calls",
    )
    lines.extend(_fixed_table_section_lines("runtime top prompts", runtime_headers, runtime_rows))
    stage_rows = [
        (
            str(row["workflow_id"]),
            str(row["stage_id"]),
            str(row["first_turn_char_count"]),
            str(row["eager_char_count"]),
            str(row["lazy_char_count"]),
            str(row["prior_stage_residue_char_count"]),
            str(row["prior_stage_residue_line_count"]),
            str(row["prior_stage_residue_count"]),
            str(row["violation_count"]),
        )
        for row in _stage_top_prompt_rows(report.stage_diagnostics, top)
    ]
    stage_headers = (
        "workflow",
        "stage",
        "first_turn_chars",
        "eager_chars",
        "lazy_chars",
        "residue_chars",
        "residue_lines",
        "residue_records",
        "violations",
    )
    lines.extend(_fixed_table_section_lines("stage top prompts", stage_headers, stage_rows))
    lines.extend(_prior_stage_residue_table_section(_repeated_prior_stage_residue_rows(report.stage_diagnostics, top)))
    authority_rows = [
        (
            _row_text(row, "workflow_id"),
            _row_text(row, "stage_id"),
            _row_text(row, "bucket"),
            _row_text(row, "authority"),
            str(_row_int(row, "expanded_char_count")),
            str(_row_int(row, "raw_include_count")),
            str(_row_int(row, "transitive_include_count")),
        )
        for row in _stage_authority_top_prompt_rows(report.stage_diagnostics, top)
    ]
    lines.extend(
        _fixed_table_section_lines(
            "stage authority hotspots",
            ("workflow", "stage", "bucket", "authority", "expanded_chars", "includes", "transitive_includes"),
            authority_rows,
        )
    )
    init_field_rows = [
        (
            _row_text(row, "workflow_id"),
            _row_text(row, "stage_id"),
            str(_row_int(row, "required_init_field_count")),
            str(_row_int(row, "likely_bulky_field_count")),
            _row_text(row, "field_name"),
            _row_text(row, "field_kind_guess"),
            _row_text(row, "field_pressure_class"),
            str(_row_int(row, "selection_count")),
        )
        for row in _stage_init_field_pressure_rows(report.stage_diagnostics, top)
    ]
    lines.extend(
        _fixed_table_section_lines(
            "staged-init field pressure",
            (
                "workflow",
                "stage",
                "required_fields",
                "likely_bulky",
                "field_name",
                "field_kind",
                "pressure",
                "selections",
            ),
            init_field_rows,
        )
    )
    exact_rows = [
        (
            str(row.get("path", "")),
            str(row.get("exact_assertion_count", 0)),
            str(row.get("machine_contract_exact_assertions", 0)),
            str(row.get("public_ux_exact_assertions", 0)),
            str(row.get("brittle_prose_assertions", 0)),
            f"{100 * cast(float, row.get('brittle_prose_density', 0.0)):.1f}",
            str(row.get("severity", "info")),
        )
        for row in _exact_assertion_file_rows(report.exact_assertion_diagnostics, top)
    ]
    exact_headers = ("file", "exact", "machine", "public_ux", "brittle", "brittle_pct", "severity")
    lines.extend(_fixed_table_section_lines("prompt-test exactness", exact_headers, exact_rows))
    lines.extend(_exactness_migration_table_section(report.exact_assertion_diagnostics, top))
    outside_top_disallowed = _disallowed_return_field_mentions_outside_top_rows(report, top)
    if outside_top_disallowed:
        lines.extend(("", f"disallowed return field mentions outside top prompt rows: {outside_top_disallowed}"))
    if report.forbidden_child_return_synthesis_mentions:
        lines.extend(
            (
                "",
                "forbidden child return synthesis instructions: "
                f"{len(report.forbidden_child_return_synthesis_mentions)}",
            )
        )
    return "\n".join(lines) + "\n"


def _top_items(items: Sequence[PromptSurfaceItem], top: int | None) -> tuple[PromptSurfaceItem, ...]:
    sorted_items = sorted(
        items,
        key=lambda item: (-item.expanded_char_count, -item.rigidity_index, item.kind, item.name),
    )
    if top is None or top <= 0:
        return tuple(sorted_items)
    return tuple(sorted_items[:top])


def _disallowed_return_field_mentions_outside_top_rows(report: PromptSurfaceReport, top: int | None) -> int:
    top_paths = {item.path for item in _top_items(report.items, top)}
    return sum(1 for mention in report.disallowed_return_field_mentions if mention.path not in top_paths)


def _markdown_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "\\`").replace("\n", " ")
