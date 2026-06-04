"""Shared prompt diagnostics data types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gpd.core import prompt_semantic_duplicate_diagnostics
from gpd.core.prompt_stage_diagnostics import (
    AuthorityPromptMetric,
    MustNotEagerLoadViolation,
    StageAwareWorkflowPromptMetric,
    WorkflowStagePromptMetric,
)

SemanticDuplicateGroup = prompt_semantic_duplicate_diagnostics.SemanticDuplicateGroup
SemanticDuplicateOccurrence = prompt_semantic_duplicate_diagnostics.SemanticDuplicateOccurrence

PromptSurfaceKind = Literal["command", "agent", "workflow"]

PROMPT_SURFACE_REPORT_SCHEMA_VERSION = "prompt_surface_diagnostics.v8"
DEFAULT_PATH_PREFIX = "/runtime/"
DEFAULT_SURFACES: tuple[PromptSurfaceKind, ...] = ("command", "agent", "workflow")


@dataclass(frozen=True, slots=True)
class PromptSource:
    """One canonical prompt source discovered under the repository source tree."""

    kind: PromptSurfaceKind
    name: str
    path: str
    absolute_path: Path
    repo_root: Path
    src_root: Path


@dataclass(frozen=True, slots=True)
class RuntimeProjectionMetric:
    runtime: str
    native_include_support: bool
    expanded_line_count: int
    expanded_char_count: int
    line_count: int
    char_count: int
    line_delta: int
    char_delta: int
    char_delta_percent: float
    include_count: int
    runtime_note_count: int
    runtime_note_chars: int
    shell_fence_count: int
    shell_rewrite_count: int
    bridge_command_occurrences: int


@dataclass(frozen=True, slots=True)
class InvalidGpdReturnExample:
    path: str
    start_line: int
    end_line: int
    errors: tuple[str, ...]
    preview: str


@dataclass(frozen=True, slots=True)
class InvalidFrontmatterExample:
    path: str
    start_line: int
    end_line: int
    schema_name: Literal["verification"]
    fields: tuple[str, ...]
    errors: tuple[str, ...]
    preview: str


@dataclass(frozen=True, slots=True)
class PromptReturnFieldMention:
    path: str
    line: int
    field: str
    mention_kind: Literal[
        "direct_reference",
        "extended_field_list",
        "role_field_statement",
        "yaml_example_key",
    ]
    polarity: Literal["positive", "negative"]
    allowed: bool
    allowed_source: Literal["base", "extension", "unknown"]
    severity: Literal["info", "warn", "error"]
    snippet: str
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class ForbiddenChildReturnSynthesisMention:
    path: str
    line: int
    action: str
    polarity: Literal["positive"]
    severity: Literal["error"]
    snippet: str


@dataclass(frozen=True, slots=True)
class StageMechanicsProseMention:
    path: str
    line: int
    categories: tuple[str, ...]
    severity: Literal["info", "warn"]
    snippet: str


@dataclass(frozen=True, slots=True)
class ManifestMustNotDuplicateEntry:
    value: str
    raw_occurrence_count: int
    first_index: int
    duplicate_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ManifestMustNotDuplicateEntriesDiagnostic:
    workflow_id: str
    manifest_path: str
    stage_id: str
    stage_index: int
    field_name: Literal["must_not_eager_load"]
    raw_entry_count: int
    effective_unique_entry_count: int
    duplicate_entry_count: int
    duplicate_entries: tuple[ManifestMustNotDuplicateEntry, ...]


@dataclass(frozen=True, slots=True)
class PromptSurfaceItem:
    kind: PromptSurfaceKind
    name: str
    path: str
    raw_line_count: int
    raw_char_count: int
    raw_include_count: int
    expanded_line_count: int
    expanded_char_count: int
    expanded_include_count: int
    unresolved_include_count: int
    visible_schema_example_count: int
    invalid_gpd_return_example_count: int
    invalid_gpd_return_examples: tuple[InvalidGpdReturnExample, ...]
    invalid_frontmatter_example_count: int
    invalid_frontmatter_examples: tuple[InvalidFrontmatterExample, ...]
    return_field_mention_count: int
    disallowed_return_field_mention_count: int
    disallowed_return_field_mentions: tuple[PromptReturnFieldMention, ...]
    hard_gate_line_count: int
    hard_gate_density: float
    shell_fence_count: int
    shell_parsing_line_count: int
    rigidity_index: int
    runtime_projection: tuple[RuntimeProjectionMetric, ...]
    review_contract_frontload_section_count: int = 0
    review_contract_frontload_line_count: int = 0
    review_contract_frontload_char_count: int = 0


@dataclass(frozen=True, slots=True)
class DuplicateInvariantGroup:
    phrase: str
    occurrence_count: int
    file_count: int
    severity: Literal["info", "warn", "high"]
    locations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PromptSurfaceReport:
    schema_version: str
    repo_root: str
    totals: Mapping[str, object]
    items: tuple[PromptSurfaceItem, ...]
    stage_diagnostics: tuple[StageAwareWorkflowPromptMetric, ...]
    invalid_gpd_return_examples: tuple[InvalidGpdReturnExample, ...]
    invalid_frontmatter_examples: tuple[InvalidFrontmatterExample, ...]
    return_field_mentions: tuple[PromptReturnFieldMention, ...]
    disallowed_return_field_mentions: tuple[PromptReturnFieldMention, ...]
    forbidden_child_return_synthesis_mentions: tuple[ForbiddenChildReturnSynthesisMention, ...]
    duplicate_invariants: tuple[DuplicateInvariantGroup, ...]
    semantic_duplicate_invariants: tuple[SemanticDuplicateGroup, ...]
    exact_assertion_diagnostics: Mapping[str, object]
    exact_prose_assertion_files: tuple[Mapping[str, object], ...]
    warnings: tuple[str, ...]
    stage_mechanics_prose_mentions: tuple[StageMechanicsProseMention, ...] = ()
    manifest_must_not_duplicate_entries: tuple[ManifestMustNotDuplicateEntriesDiagnostic, ...] = ()


__all__ = [
    "DEFAULT_PATH_PREFIX",
    "DEFAULT_SURFACES",
    "PROMPT_SURFACE_REPORT_SCHEMA_VERSION",
    "AuthorityPromptMetric",
    "DuplicateInvariantGroup",
    "ForbiddenChildReturnSynthesisMention",
    "InvalidFrontmatterExample",
    "InvalidGpdReturnExample",
    "ManifestMustNotDuplicateEntriesDiagnostic",
    "ManifestMustNotDuplicateEntry",
    "MustNotEagerLoadViolation",
    "PromptSource",
    "PromptReturnFieldMention",
    "PromptSurfaceItem",
    "PromptSurfaceKind",
    "PromptSurfaceReport",
    "RuntimeProjectionMetric",
    "SemanticDuplicateGroup",
    "SemanticDuplicateOccurrence",
    "StageAwareWorkflowPromptMetric",
    "StageMechanicsProseMention",
    "WorkflowStagePromptMetric",
]
