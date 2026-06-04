"""Test-only prompt-surface measurement helpers."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import import_module
from math import ceil
from pathlib import Path

from gpd.adapters import get_adapter
from gpd.adapters.install_utils import (
    expand_at_includes,
    parse_at_include_path,
    project_markdown_for_runtime,
    strip_display_only_command_help_frontmatter,
)
from gpd.core import prompt_markdown_scan as _prompt_markdown_scan
from gpd.core.model_visible_text import command_visibility_note

DEFAULT_PROMPT_BUDGET_MARGIN = 0.03
_PROMPT_DIAGNOSTICS_UNSET = object()
_PROMPT_DIAGNOSTICS_MODULE: object = _PROMPT_DIAGNOSTICS_UNSET

__all__ = [
    "DEFAULT_PROMPT_BUDGET_MARGIN",
    "MarkdownFence",
    "PromptSurfaceMetrics",
    "budget_from_baseline",
    "count_raw_includes",
    "count_unfenced_heading",
    "expanded_include_markers",
    "expanded_prompt_text",
    "first_line_containing_any",
    "iter_markdown_fences",
    "iter_unfenced_lines",
    "line_number_for_fragment",
    "measure_prompt_surface",
    "measure_projected_prompt_surface",
    "parse_at_include_path",
    "projected_prompt_text",
    "runtime_command_visibility_note",
]

MarkdownFence = _prompt_markdown_scan.MarkdownFence


@dataclass(frozen=True, slots=True)
class PromptSurfaceMetrics:
    """Compact measurements for one expanded prompt surface."""

    source_path: Path
    raw_include_count: int
    expanded_line_count: int
    expanded_char_count: int
    first_question_line: int | None = None
    first_question_marker: str | None = None


def _prompt_diagnostics_module() -> object | None:
    """Return the production diagnostics module when this checkout has it."""

    global _PROMPT_DIAGNOSTICS_MODULE
    if _PROMPT_DIAGNOSTICS_MODULE is _PROMPT_DIAGNOSTICS_UNSET:
        try:
            _PROMPT_DIAGNOSTICS_MODULE = import_module("gpd.core.prompt_diagnostics")
        except ModuleNotFoundError as exc:
            if exc.name != "gpd.core.prompt_diagnostics":
                raise
            _PROMPT_DIAGNOSTICS_MODULE = None
    if _PROMPT_DIAGNOSTICS_MODULE is None:
        return None
    return _PROMPT_DIAGNOSTICS_MODULE


def _diagnostics_callable(*names: str) -> Callable[..., object] | None:
    module = _prompt_diagnostics_module()
    if module is None:
        return None
    for name in names:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    return None


def budget_from_baseline(
    value: int,
    *,
    minimum_margin: int,
    margin: float = DEFAULT_PROMPT_BUDGET_MARGIN,
) -> int:
    """Return a stable prompt budget with a small growth allowance."""

    return value + max(minimum_margin, ceil(value * margin))


def runtime_command_visibility_note(runtime: str) -> str:
    """Return the canonical command wrapper note after runtime command translation."""

    return get_adapter(runtime).translate_shared_command_references(command_visibility_note())


def expanded_prompt_text(
    path: Path,
    *,
    src_root: Path,
    path_prefix: str,
    runtime: str | None = None,
) -> str:
    """Return one prompt file with runtime includes expanded."""

    diagnostics_expander = _diagnostics_callable("expanded_prompt_text")
    if diagnostics_expander is not None:
        return str(diagnostics_expander(path, src_root=src_root, path_prefix=path_prefix, runtime=runtime))

    content = path.read_text(encoding="utf-8")
    return expand_at_includes(content, src_root, path_prefix, runtime=runtime)


def projected_prompt_text(
    path: Path,
    *,
    runtime: str,
    src_root: Path,
    path_prefix: str,
    surface_kind: str = "command",
    command_name: str | None = None,
) -> str:
    """Return one prompt file as the final runtime-visible projected text."""

    diagnostics_projector = _diagnostics_callable("projected_prompt_text")
    if diagnostics_projector is not None:
        return str(
            diagnostics_projector(
                path,
                runtime=runtime,
                src_root=src_root,
                path_prefix=path_prefix,
                surface_kind=surface_kind,
                command_name=command_name,
            )
        )

    content = path.read_text(encoding="utf-8")
    return project_markdown_for_runtime(
        content,
        runtime=runtime,
        path_prefix=path_prefix,
        surface_kind=surface_kind,
        src_root=src_root,
        protect_agent_prompt_body=surface_kind == "agent",
        command_name=command_name or path.stem,
    )


def _coerce_markdown_fence(fence: object) -> MarkdownFence:
    if isinstance(fence, MarkdownFence):
        return fence
    return MarkdownFence(
        info=str(fence.info),
        body=str(fence.body),
        start_line=int(fence.start_line),
        end_line=int(fence.end_line),
    )


def iter_markdown_fences(text: str) -> Sequence[MarkdownFence]:
    """Return fenced code blocks with 1-based source line metadata."""

    diagnostics_iter = _diagnostics_callable("iter_markdown_fences")
    if diagnostics_iter is not None:
        return tuple(_coerce_markdown_fence(fence) for fence in diagnostics_iter(text))
    return _prompt_markdown_scan.iter_markdown_fences(text)


def count_raw_includes(text: str) -> int:
    """Count raw ``@`` include lines recognized by the installer."""

    diagnostics_counter = _diagnostics_callable("count_raw_includes", "_count_raw_includes")
    if diagnostics_counter is not None:
        return int(diagnostics_counter(text))
    return _prompt_markdown_scan.count_raw_includes(text)


def expanded_include_markers(text: str) -> tuple[str, ...]:
    """Return include marker filenames from an expanded prompt surface."""

    diagnostics_extractor = _diagnostics_callable("expanded_include_markers")
    if diagnostics_extractor is not None:
        return tuple(str(marker) for marker in diagnostics_extractor(text))
    return tuple(re.findall(r"<!-- \[included: ([^\]]+)\] -->", text))


def _coerce_unfenced_line(line: object) -> str:
    if isinstance(line, tuple) and len(line) == 2:
        return str(line[1])
    return str(line)


def iter_unfenced_lines(text: str) -> Sequence[str]:
    """Return lines outside fenced code blocks."""

    diagnostics_iter = _diagnostics_callable("iter_unfenced_lines")
    if diagnostics_iter is not None:
        return tuple(_coerce_unfenced_line(line) for line in diagnostics_iter(text))
    return tuple(line for _line_number, line in _prompt_markdown_scan.iter_unfenced_lines(text))


def count_unfenced_heading(text: str, heading: str) -> int:
    """Count exact markdown heading lines outside fenced code blocks."""

    diagnostics_counter = _diagnostics_callable("count_unfenced_heading")
    if diagnostics_counter is not None:
        return int(diagnostics_counter(text, heading))
    return sum(1 for line in iter_unfenced_lines(text) if line.strip() == heading)


def line_number_for_fragment(text: str, fragment: str, *, start: int = 1) -> int | None:
    """Return the first 1-based line number containing *fragment*."""

    diagnostics_finder = _diagnostics_callable("line_number_for_fragment")
    if diagnostics_finder is not None:
        line_number = diagnostics_finder(text, fragment, start=start)
        return int(line_number) if line_number is not None else None

    for line_number, line in enumerate(text.splitlines(), start=1):
        if line_number < start:
            continue
        if fragment in line:
            return line_number
    return None


def first_line_containing_any(text: str, fragments: Sequence[str], *, start: int = 1) -> tuple[int, str] | None:
    """Return the first line number and matched fragment among *fragments*."""

    diagnostics_finder = _diagnostics_callable("first_line_containing_any")
    if diagnostics_finder is not None:
        match = diagnostics_finder(text, fragments, start=start)
        if match is None:
            return None
        line_number, marker = match
        return int(line_number), str(marker)

    if not fragments:
        return None
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line_number < start:
            continue
        for fragment in fragments:
            if fragment in line:
                return line_number, fragment
    return None


def measure_prompt_surface(
    path: Path,
    *,
    src_root: Path,
    path_prefix: str,
    runtime: str | None = None,
    first_question_fragments: Sequence[str] = (),
) -> PromptSurfaceMetrics:
    """Measure prompt weight and first-question anchors for one prompt file."""

    raw_text = path.read_text(encoding="utf-8")
    if path.parent.name == "commands":
        raw_text = strip_display_only_command_help_frontmatter(raw_text)
    expanded_text = expand_at_includes(raw_text, src_root, path_prefix, runtime=runtime)
    first_question_line = None
    first_question_marker = None

    if first_question_fragments:
        match = first_line_containing_any(expanded_text, first_question_fragments)
        if match is not None:
            first_question_line, first_question_marker = match

    return PromptSurfaceMetrics(
        source_path=path,
        raw_include_count=count_raw_includes(raw_text),
        expanded_line_count=len(expanded_text.splitlines()),
        expanded_char_count=len(expanded_text),
        first_question_line=first_question_line,
        first_question_marker=first_question_marker,
    )


def measure_projected_prompt_surface(
    path: Path,
    *,
    runtime: str,
    src_root: Path,
    path_prefix: str,
    surface_kind: str = "command",
    command_name: str | None = None,
) -> PromptSurfaceMetrics:
    """Measure the final runtime-visible projected prompt surface."""

    raw_text = path.read_text(encoding="utf-8")
    if path.parent.name == "commands":
        raw_text = strip_display_only_command_help_frontmatter(raw_text)
    projected_text = projected_prompt_text(
        path,
        runtime=runtime,
        src_root=src_root,
        path_prefix=path_prefix,
        surface_kind=surface_kind,
        command_name=command_name,
    )
    return PromptSurfaceMetrics(
        source_path=path,
        raw_include_count=count_raw_includes(raw_text),
        expanded_line_count=len(projected_text.splitlines()),
        expanded_char_count=len(projected_text),
    )
