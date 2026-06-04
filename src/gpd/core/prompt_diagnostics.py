"""Read-only prompt-surface diagnostics for canonical GPD sources."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import cast

from gpd.adapters.install_utils import (
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    build_runtime_cli_bridge_command,
    expand_at_includes,
    project_markdown_for_runtime,
    projection_target_dir_from_path_prefix,
    strip_display_only_command_help_frontmatter,
)
from gpd.adapters.runtime_catalog import (
    get_runtime_descriptor,
    iter_runtime_descriptors,
    normalize_runtime_name,
)
from gpd.core import prompt_markdown_scan as _prompt_markdown_scan
from gpd.core import prompt_semantic_duplicate_diagnostics
from gpd.core.prompt_diagnostics_renderers import (
    render_prompt_surface_markdown,
    render_prompt_surface_table,
    report_to_dict,
)
from gpd.core.prompt_diagnostics_scanners import (
    _count_shell_fences,
    _count_shell_parsing_lines,
    _disallowed_return_field_mentions,
    _hard_gate_metrics,
    _inspect_visible_schema_examples,
    _scan_forbidden_child_return_synthesis_mentions,
    _scan_return_field_mentions,
    _scan_return_field_mentions_for_repo,
)
from gpd.core.prompt_diagnostics_types import (
    DEFAULT_PATH_PREFIX,
    DEFAULT_SURFACES,
    PROMPT_SURFACE_REPORT_SCHEMA_VERSION,
    AuthorityPromptMetric,
    DuplicateInvariantGroup,
    ForbiddenChildReturnSynthesisMention,
    InvalidFrontmatterExample,
    InvalidGpdReturnExample,
    MustNotEagerLoadViolation,
    PromptReturnFieldMention,
    PromptSource,
    PromptSurfaceItem,
    PromptSurfaceKind,
    PromptSurfaceReport,
    RuntimeProjectionMetric,
    SemanticDuplicateGroup,
    SemanticDuplicateOccurrence,
    StageAwareWorkflowPromptMetric,
    StageMechanicsProseMention,
    WorkflowStagePromptMetric,
)
from gpd.core.prompt_exactness_diagnostics import (
    empty_exact_assertion_diagnostics as _empty_exact_assertion_diagnostics,
)
from gpd.core.prompt_exactness_diagnostics import (
    exact_prose_assertion_files_from_diagnostics as _exact_prose_assertion_files_from_diagnostics,
)
from gpd.core.prompt_exactness_diagnostics import (
    scan_exact_assertion_diagnostics as _scan_exact_assertion_diagnostics,
)
from gpd.core.prompt_stage_diagnostics import (
    build_manifest_must_not_duplicate_entries as _build_manifest_must_not_duplicate_entries,
)
from gpd.core.prompt_stage_diagnostics import (
    build_stage_diagnostics as _build_stage_diagnostics,
)
from gpd.core.prompt_stage_diagnostics import (
    manifest_must_not_duplicate_entries_totals as _manifest_must_not_duplicate_entries_totals,
)
from gpd.core.prompt_stage_diagnostics import (
    stage_diagnostics_totals as _stage_diagnostics_totals,
)
from gpd.core.prompt_surface_phase1_measurement import (
    measure_review_contract_frontload as _measure_review_contract_frontload,
)
from gpd.core.prompt_surface_phase1_measurement import (
    scan_stage_mechanics_prose_mentions as _scan_stage_mechanics_prose_mentions,
)
from gpd.core.prompt_surface_phase1_measurement import (
    stage_mechanics_prose_by_category as _stage_mechanics_prose_by_category,
)
from gpd.core.prompt_surface_phase1_measurement import (
    stage_mechanics_prose_by_kind as _stage_mechanics_prose_by_kind,
)
from gpd.core.prompt_surface_phase1_measurement import (
    stage_mechanics_scan_paths as _stage_mechanics_scan_paths,
)

_count_raw_includes = _prompt_markdown_scan.count_raw_includes
_iter_markdown_fences = _prompt_markdown_scan.iter_markdown_fences
_line_count = _prompt_markdown_scan.line_count
_relative_path = _prompt_markdown_scan.relative_path
_body_without_frontmatter = _prompt_markdown_scan.body_without_frontmatter

_INCLUDED_MARKER_RE = re.compile(r"<!-- \[included: [^\]]+\] -->")
_UNRESOLVED_INCLUDE_RE = re.compile(r"<!-- @ include (?:not resolved|cycle detected|read error|depth limit reached):")
_BRIDGE_COMMAND_RE = re.compile(r"(?:gpd\.runtime_cli|\bgpd_cli\s+--raw\b|\bgpd\s+--raw\b)")
_RUNTIME_NOTE_RE = re.compile(
    r"(?:runtime note|runtime bridge|runtime-visible|shared runtime cli bridge|GPD runtime|"
    r"When shell steps call the GPD CLI)",
    re.IGNORECASE,
)

__all__ = [
    "DEFAULT_SURFACES",
    "PROMPT_SURFACE_REPORT_SCHEMA_VERSION",
    "AuthorityPromptMetric",
    "DuplicateInvariantGroup",
    "ForbiddenChildReturnSynthesisMention",
    "InvalidFrontmatterExample",
    "InvalidGpdReturnExample",
    "MustNotEagerLoadViolation",
    "PromptSource",
    "PromptReturnFieldMention",
    "PromptSurfaceItem",
    "PromptSurfaceReport",
    "RuntimeProjectionMetric",
    "SemanticDuplicateGroup",
    "SemanticDuplicateOccurrence",
    "StageAwareWorkflowPromptMetric",
    "StageMechanicsProseMention",
    "WorkflowStagePromptMetric",
    "build_prompt_surface_report",
    "iter_prompt_sources",
    "measure_prompt_file",
    "render_prompt_surface_markdown",
    "render_prompt_surface_table",
    "report_to_dict",
]


def iter_prompt_sources(
    repo_root: str | Path,
    surfaces: Iterable[str] | str = DEFAULT_SURFACES,
) -> tuple[PromptSource, ...]:
    """Return canonical command, agent, and workflow markdown sources."""

    root = Path(repo_root).expanduser().resolve()
    src_root = _source_root_for_repo(root)
    normalized_surfaces = _normalize_surfaces(surfaces)
    source_dirs: dict[PromptSurfaceKind, Path] = {
        "command": src_root / "commands",
        "agent": src_root / "agents",
        "workflow": src_root / "specs" / "workflows",
    }

    sources: list[PromptSource] = []
    for kind in normalized_surfaces:
        source_dir = source_dirs[kind]
        if not source_dir.is_dir():
            continue
        for path in sorted(source_dir.glob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            sources.append(
                PromptSource(
                    kind=kind,
                    name=path.stem,
                    path=_relative_path(path, root),
                    absolute_path=path,
                    repo_root=root,
                    src_root=src_root,
                )
            )
    return tuple(sources)


def measure_prompt_file(
    source: PromptSource,
    runtime_names: Iterable[str] | str = (),
    include_runtime_projections: bool = True,
) -> PromptSurfaceItem:
    """Measure one prompt source without mutating repo or project state."""

    raw_text = source.absolute_path.read_text(encoding="utf-8")
    measured_text = strip_display_only_command_help_frontmatter(raw_text) if source.kind == "command" else raw_text
    expanded_text = expand_at_includes(measured_text, source.src_root, DEFAULT_PATH_PREFIX)
    raw_include_count = _count_raw_includes(measured_text)
    (
        visible_schema_example_count,
        invalid_return_examples,
        invalid_frontmatter_examples,
    ) = _inspect_visible_schema_examples(measured_text, source.path)
    invalid_return_count = len(invalid_return_examples)
    invalid_frontmatter_count = len(invalid_frontmatter_examples)
    return_field_mentions = _scan_return_field_mentions(measured_text, source.path)
    disallowed_return_field_mentions = _disallowed_return_field_mentions(return_field_mentions)
    hard_gate_line_count, hard_gate_density = _hard_gate_metrics(measured_text)
    shell_fence_count = _count_shell_fences(measured_text)
    shell_parsing_line_count = _count_shell_parsing_lines(measured_text)
    unresolved_include_count = len(_UNRESOLVED_INCLUDE_RE.findall(expanded_text))
    (
        review_contract_frontload_section_count,
        review_contract_frontload_line_count,
        review_contract_frontload_char_count,
    ) = _measure_review_contract_frontload(source, measured_text)

    runtime_projection: tuple[RuntimeProjectionMetric, ...] = ()
    if include_runtime_projections and source.kind in {"command", "agent"}:
        runtime_projection = tuple(
            _measure_runtime_projection(source, measured_text, expanded_text, runtime_name)
            for runtime_name in _normalize_runtime_names(runtime_names)
        )

    rigidity_index = (
        2 * visible_schema_example_count
        + 3 * invalid_return_count
        + 3 * invalid_frontmatter_count
        + hard_gate_line_count
        + 2 * shell_parsing_line_count
        + 5 * unresolved_include_count
    )

    return PromptSurfaceItem(
        kind=source.kind,
        name=source.name,
        path=source.path,
        raw_line_count=_line_count(measured_text),
        raw_char_count=len(measured_text),
        raw_include_count=raw_include_count,
        expanded_line_count=_line_count(expanded_text),
        expanded_char_count=len(expanded_text),
        expanded_include_count=len(_INCLUDED_MARKER_RE.findall(expanded_text)),
        unresolved_include_count=unresolved_include_count,
        visible_schema_example_count=visible_schema_example_count,
        invalid_gpd_return_example_count=invalid_return_count,
        invalid_gpd_return_examples=invalid_return_examples,
        invalid_frontmatter_example_count=invalid_frontmatter_count,
        invalid_frontmatter_examples=invalid_frontmatter_examples,
        return_field_mention_count=len(return_field_mentions),
        disallowed_return_field_mention_count=len(disallowed_return_field_mentions),
        disallowed_return_field_mentions=disallowed_return_field_mentions,
        hard_gate_line_count=hard_gate_line_count,
        hard_gate_density=hard_gate_density,
        shell_fence_count=shell_fence_count,
        shell_parsing_line_count=shell_parsing_line_count,
        rigidity_index=rigidity_index,
        runtime_projection=runtime_projection,
        review_contract_frontload_section_count=review_contract_frontload_section_count,
        review_contract_frontload_line_count=review_contract_frontload_line_count,
        review_contract_frontload_char_count=review_contract_frontload_char_count,
    )


def build_prompt_surface_report(
    repo_root: str | Path,
    surfaces: Iterable[str] | str = DEFAULT_SURFACES,
    runtime_names: Iterable[str] | str = (),
    include_tests: bool = False,
    top: int | None = None,
    include_runtime_projections: bool = True,
) -> PromptSurfaceReport:
    """Build the full prompt diagnostics report for canonical source files."""

    del top
    root = Path(repo_root).expanduser().resolve()
    warnings: list[str] = []
    sources = iter_prompt_sources(root, surfaces)
    if not sources:
        warnings.append("no prompt sources found for requested surfaces")

    items = tuple(
        measure_prompt_file(
            source,
            runtime_names=runtime_names,
            include_runtime_projections=include_runtime_projections,
        )
        for source in sources
    )
    duplicate_invariants: tuple[DuplicateInvariantGroup, ...] = ()
    semantic_duplicate_invariants = prompt_semantic_duplicate_diagnostics.scan_semantic_duplicate_invariant_groups(
        _duplicate_scan_paths(root, include_tests=include_tests),
        repo_root=root,
    )
    exact_assertion_diagnostics = (
        _scan_exact_assertion_diagnostics(root) if include_tests else _empty_exact_assertion_diagnostics()
    )
    exact_assertions = _exact_prose_assertion_files_from_diagnostics(exact_assertion_diagnostics)
    invalid_return_examples = tuple(example for item in items for example in item.invalid_gpd_return_examples)
    invalid_frontmatter_examples = tuple(example for item in items for example in item.invalid_frontmatter_examples)
    return_field_mentions = _scan_return_field_mentions_for_repo(root, include_tests=include_tests)
    disallowed_return_field_mentions = _disallowed_return_field_mentions(return_field_mentions)
    forbidden_child_return_synthesis_mentions = _scan_forbidden_child_return_synthesis_mentions(sources)
    stage_mechanics_prose_mentions = _scan_stage_mechanics_prose_mentions(
        _stage_mechanics_scan_paths(_source_root_for_repo(root)),
        repo_root=root,
    )
    stage_diagnostics = _build_stage_diagnostics(
        sources,
        items,
        report_warnings=warnings,
        path_prefix=DEFAULT_PATH_PREFIX,
    )
    manifest_must_not_duplicate_entries = _build_manifest_must_not_duplicate_entries(sources)

    return PromptSurfaceReport(
        schema_version=PROMPT_SURFACE_REPORT_SCHEMA_VERSION,
        repo_root=str(root),
        totals=_build_totals(
            items,
            stage_diagnostics=stage_diagnostics,
            return_field_mentions=return_field_mentions,
            forbidden_child_return_synthesis_mentions=forbidden_child_return_synthesis_mentions,
            stage_mechanics_prose_mentions=stage_mechanics_prose_mentions,
            manifest_must_not_duplicate_entries=manifest_must_not_duplicate_entries,
        ),
        items=items,
        stage_diagnostics=stage_diagnostics,
        invalid_gpd_return_examples=invalid_return_examples,
        invalid_frontmatter_examples=invalid_frontmatter_examples,
        return_field_mentions=return_field_mentions,
        disallowed_return_field_mentions=disallowed_return_field_mentions,
        forbidden_child_return_synthesis_mentions=forbidden_child_return_synthesis_mentions,
        duplicate_invariants=duplicate_invariants,
        semantic_duplicate_invariants=semantic_duplicate_invariants,
        exact_assertion_diagnostics=exact_assertion_diagnostics,
        exact_prose_assertion_files=exact_assertions,
        warnings=tuple(warnings),
        stage_mechanics_prose_mentions=stage_mechanics_prose_mentions,
        manifest_must_not_duplicate_entries=manifest_must_not_duplicate_entries,
    )


def _source_root_for_repo(repo_root: Path) -> Path:
    src_root = repo_root / "src" / "gpd"
    if src_root.is_dir():
        return src_root
    if (repo_root / "commands").is_dir() and (repo_root / "agents").is_dir():
        return repo_root
    return src_root


def _normalize_surfaces(surfaces: Iterable[str] | str) -> tuple[PromptSurfaceKind, ...]:
    if isinstance(surfaces, str):
        raw_values = (surfaces,)
    else:
        raw_values = tuple(surfaces)
    if not raw_values or any(value == "all" for value in raw_values):
        return DEFAULT_SURFACES

    normalized: list[PromptSurfaceKind] = []
    for value in raw_values:
        if value not in DEFAULT_SURFACES:
            allowed = ", ".join((*DEFAULT_SURFACES, "all"))
            raise ValueError(f"surface must be one of: {allowed}")
        kind = cast(PromptSurfaceKind, value)
        if kind not in normalized:
            normalized.append(kind)
    return tuple(normalized)


def _normalize_runtime_names(runtime_names: Iterable[str] | str) -> tuple[str, ...]:
    descriptors = iter_runtime_descriptors()
    all_names = tuple(descriptor.runtime_name for descriptor in descriptors)
    if isinstance(runtime_names, str):
        raw_values = (runtime_names,)
    else:
        raw_values = tuple(runtime_names)
    if not raw_values:
        return ()
    if any(value == "all" for value in raw_values):
        return all_names

    normalized: list[str] = []
    for value in raw_values:
        runtime_name = normalize_runtime_name(value)
        if runtime_name is None:
            supported = ", ".join(all_names)
            raise KeyError(f"Unknown runtime {value!r}. Supported: {supported}")
        if runtime_name not in normalized:
            normalized.append(runtime_name)
    return tuple(normalized)


def _percent_delta(delta: int, baseline: int) -> float:
    if baseline <= 0:
        return 0.0
    return round(100 * delta / baseline, 6)


def _measure_runtime_projection(
    source: PromptSource,
    raw_text: str,
    expanded_text: str,
    runtime_name: str,
) -> RuntimeProjectionMetric:
    descriptor = get_runtime_descriptor(runtime_name)
    projected_text = project_markdown_for_runtime(
        raw_text,
        runtime=runtime_name,
        path_prefix=DEFAULT_PATH_PREFIX,
        surface_kind=source.kind,
        src_root=source.src_root,
        protect_agent_prompt_body=source.kind == "agent",
        command_name=source.name,
    )
    bridge_command = _projection_bridge_command(runtime_name) if source.kind == "command" else None
    runtime_note_lines = [line for line in projected_text.splitlines() if _RUNTIME_NOTE_RE.search(line)]
    expanded_line_count = _line_count(expanded_text)
    expanded_char_count = len(expanded_text)
    projected_line_count = _line_count(projected_text)
    projected_char_count = len(projected_text)
    line_delta = projected_line_count - expanded_line_count
    char_delta = projected_char_count - expanded_char_count
    return RuntimeProjectionMetric(
        runtime=runtime_name,
        native_include_support=descriptor.native_include_support,
        expanded_line_count=expanded_line_count,
        expanded_char_count=expanded_char_count,
        line_count=projected_line_count,
        char_count=projected_char_count,
        line_delta=line_delta,
        char_delta=char_delta,
        char_delta_percent=_percent_delta(char_delta, expanded_char_count),
        include_count=_count_raw_includes(projected_text),
        runtime_note_count=len(runtime_note_lines),
        runtime_note_chars=sum(len(line) for line in runtime_note_lines),
        shell_fence_count=_count_shell_fences(projected_text),
        shell_rewrite_count=_count_shell_fences_containing(projected_text, bridge_command),
        bridge_command_occurrences=len(_BRIDGE_COMMAND_RE.findall(projected_text)),
    )


def _projection_bridge_command(runtime_name: str) -> str:
    descriptor = get_runtime_descriptor(runtime_name)
    target_dir = projection_target_dir_from_path_prefix(
        DEFAULT_PATH_PREFIX,
        config_dir_name=descriptor.config_dir_name,
    )
    return build_runtime_cli_bridge_command(
        runtime_name,
        target_dir=target_dir,
        config_dir_name=descriptor.config_dir_name,
        is_global=False,
    )


def _count_shell_fences_containing(text: str, needle: str | None) -> int:
    if not needle:
        return 0

    count = 0
    for fence in _iter_markdown_fences(_body_without_frontmatter(text)):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES and needle in fence.body:
            count += 1
    return count


def _build_totals(
    items: Sequence[PromptSurfaceItem],
    *,
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric] = (),
    return_field_mentions: Sequence[PromptReturnFieldMention] = (),
    forbidden_child_return_synthesis_mentions: Sequence[ForbiddenChildReturnSynthesisMention] = (),
    stage_mechanics_prose_mentions: Sequence[StageMechanicsProseMention] = (),
    manifest_must_not_duplicate_entries: Sequence[object] = (),
) -> dict[str, object]:
    numeric_fields = (
        "raw_line_count",
        "raw_char_count",
        "raw_include_count",
        "expanded_line_count",
        "expanded_char_count",
        "expanded_include_count",
        "unresolved_include_count",
        "visible_schema_example_count",
        "invalid_gpd_return_example_count",
        "invalid_frontmatter_example_count",
        "return_field_mention_count",
        "disallowed_return_field_mention_count",
        "hard_gate_line_count",
        "shell_fence_count",
        "shell_parsing_line_count",
        "rigidity_index",
        "review_contract_frontload_section_count",
        "review_contract_frontload_line_count",
        "review_contract_frontload_char_count",
    )
    totals: dict[str, object] = {"item_count": len(items)}
    for field in numeric_fields:
        totals[field] = sum(cast(int, getattr(item, field)) for item in items)

    by_kind: dict[str, dict[str, int]] = {}
    for kind in DEFAULT_SURFACES:
        kind_items = [item for item in items if item.kind == kind]
        by_kind[kind] = {"item_count": len(kind_items)}
        for field in numeric_fields:
            by_kind[kind][field] = sum(cast(int, getattr(item, field)) for item in kind_items)
    if return_field_mentions:
        disallowed_mentions = _disallowed_return_field_mentions(return_field_mentions)
        totals["return_field_mention_count"] = len(return_field_mentions)
        totals["disallowed_return_field_mention_count"] = len(disallowed_mentions)
        totals["negative_return_field_mention_count"] = sum(
            1 for mention in return_field_mentions if mention.polarity == "negative"
        )
        totals["allowed_return_field_mention_count"] = sum(1 for mention in return_field_mentions if mention.allowed)
    else:
        totals["negative_return_field_mention_count"] = 0
        totals["allowed_return_field_mention_count"] = 0
    totals["forbidden_child_return_synthesis_mention_count"] = len(forbidden_child_return_synthesis_mentions)
    totals["stage_mechanics_prose_count"] = len(stage_mechanics_prose_mentions)
    totals["stage_mechanics_prose_by_kind"] = _stage_mechanics_prose_by_kind(stage_mechanics_prose_mentions)
    totals["stage_mechanics_prose_by_category"] = _stage_mechanics_prose_by_category(stage_mechanics_prose_mentions)
    totals["by_kind"] = by_kind
    totals["runtime_projection"] = _runtime_projection_totals(items)
    stage_totals = _stage_diagnostics_totals(stage_diagnostics)
    stage_totals.update(_manifest_must_not_duplicate_entries_totals(manifest_must_not_duplicate_entries))
    totals["stage_diagnostics"] = stage_totals
    return totals


def _runtime_projection_totals(items: Sequence[PromptSurfaceItem]) -> dict[str, dict[str, object]]:
    totals: dict[str, dict[str, object]] = {}
    for item in items:
        for metric in item.runtime_projection:
            runtime_totals = totals.setdefault(
                metric.runtime,
                {
                    "native_include_support": metric.native_include_support,
                    "item_count": 0,
                    "expanded_line_count": 0,
                    "expanded_char_count": 0,
                    "line_count": 0,
                    "char_count": 0,
                    "line_delta": 0,
                    "char_delta": 0,
                    "char_delta_percent": 0.0,
                    "include_count": 0,
                    "runtime_note_count": 0,
                    "runtime_note_chars": 0,
                    "shell_fence_count": 0,
                    "shell_rewrite_count": 0,
                    "bridge_command_occurrences": 0,
                },
            )
            runtime_totals["item_count"] = cast(int, runtime_totals["item_count"]) + 1
            runtime_totals["expanded_line_count"] = (
                cast(int, runtime_totals["expanded_line_count"]) + metric.expanded_line_count
            )
            runtime_totals["expanded_char_count"] = (
                cast(int, runtime_totals["expanded_char_count"]) + metric.expanded_char_count
            )
            runtime_totals["line_count"] = cast(int, runtime_totals["line_count"]) + metric.line_count
            runtime_totals["char_count"] = cast(int, runtime_totals["char_count"]) + metric.char_count
            runtime_totals["line_delta"] = cast(int, runtime_totals["line_delta"]) + metric.line_delta
            runtime_totals["char_delta"] = cast(int, runtime_totals["char_delta"]) + metric.char_delta
            runtime_totals["include_count"] = cast(int, runtime_totals["include_count"]) + metric.include_count
            runtime_totals["runtime_note_count"] = (
                cast(int, runtime_totals["runtime_note_count"]) + metric.runtime_note_count
            )
            runtime_totals["runtime_note_chars"] = (
                cast(int, runtime_totals["runtime_note_chars"]) + metric.runtime_note_chars
            )
            runtime_totals["shell_fence_count"] = (
                cast(int, runtime_totals["shell_fence_count"]) + metric.shell_fence_count
            )
            runtime_totals["shell_rewrite_count"] = (
                cast(int, runtime_totals["shell_rewrite_count"]) + metric.shell_rewrite_count
            )
            runtime_totals["bridge_command_occurrences"] = (
                cast(int, runtime_totals["bridge_command_occurrences"]) + metric.bridge_command_occurrences
            )
    for runtime_totals in totals.values():
        runtime_totals["char_delta_percent"] = _percent_delta(
            cast(int, runtime_totals["char_delta"]),
            cast(int, runtime_totals["expanded_char_count"]),
        )
    return totals


def _duplicate_scan_paths(repo_root: Path, *, include_tests: bool) -> tuple[Path, ...]:
    src_root = _source_root_for_repo(repo_root)
    roots = (
        src_root / "commands",
        src_root / "agents",
        src_root / "specs" / "workflows",
        src_root / "specs" / "references",
        src_root / "specs" / "templates",
    )
    paths: list[Path] = []
    for root in roots:
        if root.is_dir():
            paths.extend(path for path in sorted(root.rglob("*.md")) if path.is_file() and not path.is_symlink())
    if include_tests:
        tests_root = repo_root / "tests"
        if tests_root.is_dir():
            paths.extend(path for path in sorted(tests_root.rglob("*.py")) if path.is_file() and not path.is_symlink())
    return tuple(paths)
