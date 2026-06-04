"""Shared markdown/source scanning helpers for prompt diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gpd.adapters.install_utils import parse_at_include_path, split_markdown_frontmatter


@dataclass(frozen=True, slots=True)
class MarkdownFence:
    """One fenced code block with line metadata."""

    info: str
    body: str
    start_line: int
    end_line: int


def relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def line_count(text: str) -> int:
    return len(text.splitlines())


def body_without_frontmatter(text: str) -> str:
    body, _line_offset = body_without_frontmatter_with_line_offset(text)
    return body


def body_without_frontmatter_with_line_offset(text: str) -> tuple[str, int]:
    _preamble, _frontmatter, _separator, body = split_markdown_frontmatter(text)
    prefix = text[: len(text) - len(body)]
    return body, prefix.count("\n")


def markdown_fence_marker(stripped_line: str) -> str | None:
    if stripped_line.startswith("```"):
        return "```"
    if stripped_line.startswith("~~~"):
        return "~~~"
    return None


def iter_markdown_fences(text: str) -> tuple[MarkdownFence, ...]:
    fences: list[MarkdownFence] = []
    active_marker: str | None = None
    active_info = ""
    active_start_line = 0
    active_body: list[str] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        marker = markdown_fence_marker(stripped)
        if marker is None:
            if active_marker is not None:
                active_body.append(line)
            continue

        if active_marker is None:
            active_marker = marker
            active_info = stripped[len(marker) :].strip()
            active_start_line = line_number
            active_body = []
            continue

        if marker == active_marker:
            fences.append(
                MarkdownFence(
                    info=active_info,
                    body="\n".join(active_body),
                    start_line=active_start_line,
                    end_line=line_number,
                )
            )
            active_marker = None
            active_info = ""
            active_start_line = 0
            active_body = []
            continue

        active_body.append(line)

    return tuple(fences)


def iter_unfenced_lines(text: str) -> tuple[tuple[int, str], ...]:
    lines: list[tuple[int, str]] = []
    active_marker: str | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        marker = markdown_fence_marker(stripped)
        if marker is not None:
            if active_marker is None:
                active_marker = marker
            elif marker == active_marker:
                active_marker = None
            continue
        if active_marker is not None:
            continue
        lines.append((line_number, line))
    return tuple(lines)


def count_raw_includes(text: str) -> int:
    return sum(1 for _line_number, line in iter_unfenced_lines(text) if parse_at_include_path(line.strip()))


def top_limit(top: int | None) -> int | None:
    if top is None or top <= 0:
        return None
    return top
