"""Additive Phase 1 prompt-pressure measurements."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from gpd.adapters.install_utils import split_markdown_frontmatter
from gpd.core import prompt_markdown_scan as _prompt_markdown_scan
from gpd.core.prompt_diagnostics_types import (
    DEFAULT_SURFACES,
    PromptSource,
    PromptSurfaceKind,
    StageMechanicsProseMention,
)

_line_count = _prompt_markdown_scan.line_count
_relative_path = _prompt_markdown_scan.relative_path
_body_without_frontmatter_with_line_offset = _prompt_markdown_scan.body_without_frontmatter_with_line_offset
_iter_unfenced_lines = _prompt_markdown_scan.iter_unfenced_lines

_REVIEW_CONTRACT_FRONTMATTER_RE = re.compile(r"(?m)^review[-_]contract:\s*$")
_COMMAND_NAME_RE = re.compile(r"(?m)^name:\s*(?P<name>.+?)\s*$")
_MARKDOWN_HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
_STAGE_MECHANICS_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|;\s*")
_STAGE_MECHANICS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "staged_init_command",
        re.compile(
            r"\bgpd(?:\.runtime_cli|_cli)?\s+--raw\s+init\b.{0,160}--stage\b|"
            r"\b--raw\s+init\b.{0,160}--stage\b",
            re.IGNORECASE,
        ),
    ),
    (
        "field_access_instruction",
        re.compile(
            r"\bgpd(?:\.runtime_cli|_cli)?\s+--raw\s+stage\s+field-access\b|"
            r"\bstaged field-access helper\b|"
            r"\bfield-access helper\b",
            re.IGNORECASE,
        ),
    ),
    (
        "selected_field_gate",
        re.compile(
            r"\bstaged_loading\.required_init_fields\b|"
            r"\bmanifest-selected\b.{0,80}\bfields\b|"
            r"\bselected init keys\b|"
            r"\bread only\b.{0,120}\b(?:required_init_fields|selected .* fields|those keys)\b|"
            r"\btreat unlisted\b.{0,80}\bunavailable\b",
            re.IGNORECASE,
        ),
    ),
    (
        "stale_payload_rejection",
        re.compile(
            r"\b(?:stale|older)\b.{0,80}\b(?:staged-init|init payload|init values|shell variables)\b|"
            r"\bdo not reuse\b.{0,80}\b(?:older stage|another stage|shell variables)\b|"
            r"\bignore older staged-init values\b",
            re.IGNORECASE,
        ),
    ),
    (
        "stage_reload_transition",
        re.compile(
            r"\breload\b.{0,120}\b(?:--stage|stage|staged init|authority|handoff)\b|"
            r"\bfresh (?:stage|late-stage|staged) init\b|"
            r"\brefresh only this stage\b|"
            r"\bdo not continue from\b.{0,80}\bmemory\b",
            re.IGNORECASE,
        ),
    ),
    (
        "eager_authority_follow",
        re.compile(
            r"\bstaged_loading\.eager_authorities\b|"
            r"\bstaged_loading\.must_not_eager_load\b|"
            r"\bmust_not_eager_load\b|"
            r"\bfollow only\b.{0,80}\beager_authorities\b|"
            r"\bactive stage'?s eager authorities\b",
            re.IGNORECASE,
        ),
    ),
)


def measure_review_contract_frontload(source: PromptSource, measured_text: str) -> tuple[int, int, int]:
    """Measure the generated model-visible review-contract block for a command."""

    if source.kind != "command":
        return 0, 0, 0
    _preamble, frontmatter, _separator, _body = split_markdown_frontmatter(measured_text)
    if not frontmatter or _REVIEW_CONTRACT_FRONTMATTER_RE.search(frontmatter) is None:
        return 0, 0, 0

    from gpd.registry import render_command_visibility_sections_from_frontmatter

    command_name = _command_name_from_frontmatter(frontmatter) or source.name
    visibility = render_command_visibility_sections_from_frontmatter(frontmatter, command_name=command_name)
    section = _extract_markdown_heading_section(visibility, heading="Review Contract", level=2)
    if not section:
        return 0, 0, 0
    return 1, _line_count(section), len(section)


def stage_mechanics_scan_paths(src_root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    commands_root = src_root / "commands"
    if commands_root.is_dir():
        paths.extend(sorted(commands_root.glob("*.md")))
    workflows_root = src_root / "specs" / "workflows"
    if workflows_root.is_dir():
        paths.extend(sorted(workflows_root.rglob("*.md")))
    return tuple(path for path in paths if path.is_file() and not path.is_symlink())


def scan_stage_mechanics_prose_mentions(
    paths: Sequence[Path],
    *,
    repo_root: Path,
) -> tuple[StageMechanicsProseMention, ...]:
    mentions: list[StageMechanicsProseMention] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        body, line_offset = _body_without_frontmatter_with_line_offset(text)
        relative = _relative_path(path, repo_root)
        for line_number, line in _iter_unfenced_lines(body):
            categories: list[str] = []
            snippet_source = line
            for clause in _stage_mechanics_clauses(line):
                clause_categories = _stage_mechanics_categories(clause)
                if not clause_categories:
                    continue
                if not categories:
                    snippet_source = clause
                categories.extend(category for category in clause_categories if category not in categories)
            if categories:
                mentions.append(
                    StageMechanicsProseMention(
                        path=relative,
                        line=line_number + line_offset,
                        categories=tuple(categories),
                        severity="info",
                        snippet=_stage_mechanics_snippet(snippet_source),
                    )
                )
    return tuple(
        sorted(
            mentions,
            key=lambda mention: (
                mention.path,
                mention.line,
                mention.categories,
                mention.snippet,
            ),
        )
    )


def stage_mechanics_prose_by_kind(
    mentions: Sequence[StageMechanicsProseMention],
) -> dict[str, int]:
    counts: Counter[str] = Counter(_stage_mechanics_kind_for_path(mention.path) for mention in mentions)
    return {kind: counts.get(kind, 0) for kind in DEFAULT_SURFACES}


def stage_mechanics_prose_by_category(
    mentions: Sequence[StageMechanicsProseMention],
) -> dict[str, int]:
    counts: Counter[str] = Counter(category for mention in mentions for category in mention.categories)
    return {category: counts.get(category, 0) for category, _pattern in _STAGE_MECHANICS_PATTERNS}


def _command_name_from_frontmatter(frontmatter: str) -> str:
    match = _COMMAND_NAME_RE.search(frontmatter)
    if match is None:
        return ""
    return match.group("name").strip().strip("\"'")


def _extract_markdown_heading_section(text: str, *, heading: str, level: int) -> str:
    lines = text.splitlines(keepends=True)
    start_index: int | None = None
    for index, line in enumerate(lines):
        match = _MARKDOWN_HEADING_RE.match(line.rstrip("\r\n"))
        if match is None:
            continue
        if len(match.group("level")) == level and match.group("title").strip() == heading:
            start_index = index
            break
    if start_index is None:
        return ""

    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        match = _MARKDOWN_HEADING_RE.match(lines[index].rstrip("\r\n"))
        if match is not None and len(match.group("level")) <= level:
            end_index = index
            break
    return "".join(lines[start_index:end_index]).rstrip("\r\n")


def _stage_mechanics_clauses(line: str) -> tuple[str, ...]:
    normalized = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", line).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return ()
    return tuple(
        part.strip(" -") for part in _STAGE_MECHANICS_CLAUSE_SPLIT_RE.split(normalized) if part.strip(" -")
    ) or (normalized,)


def _stage_mechanics_categories(clause: str) -> tuple[str, ...]:
    return tuple(category for category, pattern in _STAGE_MECHANICS_PATTERNS if pattern.search(clause))


def _stage_mechanics_snippet(line: str, max_chars: int = 180) -> str:
    snippet = re.sub(r"\s+", " ", line.strip())
    if len(snippet) <= max_chars:
        return snippet
    return snippet[: max_chars - 3].rstrip() + "..."


def _stage_mechanics_kind_for_path(path: str) -> PromptSurfaceKind:
    if path.startswith("src/gpd/commands/") or path.startswith("commands/"):
        return "command"
    if path.startswith("src/gpd/specs/workflows/") or path.startswith("specs/workflows/"):
        return "workflow"
    return "agent"
