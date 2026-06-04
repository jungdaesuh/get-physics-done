"""JSON row helpers for prompt-surface diagnostics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import cast

from gpd.core.prompt_diagnostics_types import (
    ForbiddenChildReturnSynthesisMention,
    InvalidFrontmatterExample,
    InvalidGpdReturnExample,
    PromptReturnFieldMention,
    PromptSurfaceItem,
    RuntimeProjectionMetric,
)


def prompt_item_to_dict(item: PromptSurfaceItem) -> dict[str, object]:
    return {
        "kind": item.kind,
        "name": item.name,
        "path": item.path,
        "raw_line_count": item.raw_line_count,
        "raw_char_count": item.raw_char_count,
        "raw_include_count": item.raw_include_count,
        "expanded_line_count": item.expanded_line_count,
        "expanded_char_count": item.expanded_char_count,
        "expanded_include_count": item.expanded_include_count,
        "unresolved_include_count": item.unresolved_include_count,
        "visible_schema_example_count": item.visible_schema_example_count,
        "invalid_gpd_return_example_count": item.invalid_gpd_return_example_count,
        "invalid_gpd_return_examples": [
            invalid_gpd_return_example_to_dict(example) for example in item.invalid_gpd_return_examples
        ],
        "invalid_frontmatter_example_count": item.invalid_frontmatter_example_count,
        "invalid_frontmatter_examples": [
            invalid_frontmatter_example_to_dict(example) for example in item.invalid_frontmatter_examples
        ],
        "return_field_mention_count": item.return_field_mention_count,
        "disallowed_return_field_mention_count": item.disallowed_return_field_mention_count,
        "disallowed_return_field_mentions": [
            return_field_mention_to_dict(mention) for mention in item.disallowed_return_field_mentions
        ],
        "hard_gate_line_count": item.hard_gate_line_count,
        "hard_gate_density": item.hard_gate_density,
        "shell_fence_count": item.shell_fence_count,
        "shell_parsing_line_count": item.shell_parsing_line_count,
        "rigidity_index": item.rigidity_index,
        "review_contract_frontload_section_count": getattr(
            item,
            "review_contract_frontload_section_count",
            0,
        ),
        "review_contract_frontload_line_count": getattr(item, "review_contract_frontload_line_count", 0),
        "review_contract_frontload_char_count": getattr(item, "review_contract_frontload_char_count", 0),
        "runtime_projection": [runtime_projection_metric_to_dict(metric) for metric in item.runtime_projection],
    }


def runtime_top_prompt_rows(
    items: Sequence[PromptSurfaceItem],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    rows_by_runtime: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in items:
        for metric in item.runtime_projection:
            rows_by_runtime[metric.runtime].append(
                {
                    "runtime": metric.runtime,
                    "native_include_support": metric.native_include_support,
                    "kind": item.kind,
                    "name": item.name,
                    "path": item.path,
                    "projected_line_count": metric.line_count,
                    "projected_char_count": metric.char_count,
                    "expanded_line_count": metric.expanded_line_count,
                    "expanded_char_count": metric.expanded_char_count,
                    "line_delta": metric.line_delta,
                    "char_delta": metric.char_delta,
                    "char_delta_percent": metric.char_delta_percent,
                    "include_count": metric.include_count,
                    "runtime_note_count": metric.runtime_note_count,
                    "runtime_note_chars": metric.runtime_note_chars,
                    "shell_fence_count": metric.shell_fence_count,
                    "shell_rewrite_count": metric.shell_rewrite_count,
                    "bridge_command_occurrences": metric.bridge_command_occurrences,
                }
            )

    limit = top if top is not None and top > 0 else None
    rows: list[dict[str, object]] = []
    for runtime in sorted(rows_by_runtime):
        runtime_rows = sorted(
            rows_by_runtime[runtime],
            key=lambda row: (
                -cast(int, row["projected_char_count"]),
                -cast(int, row["expanded_char_count"]),
                cast(str, row["kind"]),
                cast(str, row["name"]),
                cast(str, row["path"]),
            ),
        )
        rows.extend(runtime_rows[:limit])
    return tuple(rows)


def runtime_top_prompts_to_dict(
    items: Sequence[PromptSurfaceItem],
    top: int | None,
) -> dict[str, list[dict[str, object]]]:
    rows_by_runtime: dict[str, list[dict[str, object]]] = {}
    for row in runtime_top_prompt_rows(items, top):
        rows_by_runtime.setdefault(cast(str, row["runtime"]), []).append(dict(row))
    return rows_by_runtime


def runtime_projection_metric_to_dict(metric: RuntimeProjectionMetric) -> dict[str, object]:
    return {
        "runtime": metric.runtime,
        "native_include_support": metric.native_include_support,
        "expanded_line_count": metric.expanded_line_count,
        "expanded_char_count": metric.expanded_char_count,
        "line_count": metric.line_count,
        "char_count": metric.char_count,
        "line_delta": metric.line_delta,
        "char_delta": metric.char_delta,
        "char_delta_percent": metric.char_delta_percent,
        "include_count": metric.include_count,
        "runtime_note_count": metric.runtime_note_count,
        "runtime_note_chars": metric.runtime_note_chars,
        "shell_fence_count": metric.shell_fence_count,
        "shell_rewrite_count": metric.shell_rewrite_count,
        "bridge_command_occurrences": metric.bridge_command_occurrences,
    }


def invalid_gpd_return_example_to_dict(example: InvalidGpdReturnExample) -> dict[str, object]:
    return {
        "path": example.path,
        "start_line": example.start_line,
        "end_line": example.end_line,
        "errors": list(example.errors),
        "preview": example.preview,
    }


def invalid_frontmatter_example_to_dict(example: InvalidFrontmatterExample) -> dict[str, object]:
    return {
        "path": example.path,
        "start_line": example.start_line,
        "end_line": example.end_line,
        "schema_name": example.schema_name,
        "fields": list(example.fields),
        "errors": list(example.errors),
        "preview": example.preview,
    }


def return_field_mention_to_dict(mention: PromptReturnFieldMention) -> dict[str, object]:
    return {
        "path": mention.path,
        "line": mention.line,
        "field": mention.field,
        "mention_kind": mention.mention_kind,
        "polarity": mention.polarity,
        "allowed": mention.allowed,
        "allowed_source": mention.allowed_source,
        "severity": mention.severity,
        "snippet": mention.snippet,
        "suggestion": mention.suggestion,
    }


def forbidden_child_return_synthesis_mention_to_dict(
    mention: ForbiddenChildReturnSynthesisMention,
) -> dict[str, object]:
    return {
        "path": mention.path,
        "line": mention.line,
        "action": mention.action,
        "polarity": mention.polarity,
        "severity": mention.severity,
        "snippet": mention.snippet,
    }
