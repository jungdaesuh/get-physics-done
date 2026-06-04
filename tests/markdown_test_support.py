"""Test-only semantic markdown assertion helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import yaml

from gpd.core.frontmatter import FrontmatterParseError, extract_frontmatter
from gpd.core.strict_yaml import load_strict_yaml
from tests.prompt_metrics_support import iter_markdown_fences

__all__ = [
    "MarkdownSection",
    "ParsedMarkdownLink",
    "ParsedMarkdownTable",
    "ParsedContractFinding",
    "ParsedYamlFence",
    "assert_markdown_link",
    "assert_contract_finding",
    "assert_contract_relation_finding",
    "assert_forbidden_fragments",
    "assert_no_contract_finding",
    "assert_no_contract_relation_finding",
    "assert_ordered_fragments",
    "assert_required_fragments",
    "parse_contract_findings",
    "extract_marker_range",
    "extract_markdown_section",
    "has_line_with_terms",
    "iter_markdown_sections",
    "markdown_fence_bodies",
    "markdown_section",
    "markdown_sections",
    "markdown_table_blocks",
    "normalize_text",
    "parse_frontmatter_mapping",
    "parse_markdown_links",
    "parse_markdown_table",
    "parse_yaml_fences",
    "require_mapping",
    "tag_blocks",
    "yaml_fence_bodies",
]

_YAML_FENCE_LANGUAGES = {"yaml", "yml"}
_TABLE_SEPARATOR_RE = re.compile(r":?-{3,}:?")
_INLINE_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)]\(([^)\n]+)\)")
_YAML_FENCE_RE = re.compile(
    r"(?ms)^[ \t]*(?P<marker>`{3,}|~{3,})(?P<info>[^\n]*)\n(?P<body>.*?)^[ \t]*(?P=marker)[ \t]*$"
)


@dataclass(frozen=True, slots=True)
class MarkdownSection:
    """One ATX markdown section with source line metadata."""

    heading: str
    level: int
    body: str
    start_line: int
    end_line: int
    atx_heading: str
    text: str


@dataclass(frozen=True, slots=True)
class ParsedYamlFence:
    """A parsed YAML code fence with source line metadata."""

    info: str
    body: str
    data: object
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class ParsedMarkdownTable:
    """A simple parsed markdown table with normalized cell values."""

    headers: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class ParsedMarkdownLink:
    """A markdown inline link split into public label and target."""

    label: str
    href: str


@dataclass(frozen=True, slots=True)
class ParsedContractFinding:
    """A path-prefixed contract finding split into stable path and reason."""

    message: str
    path: str
    reason: str


def normalize_text(text: str) -> str:
    """Return text with incidental whitespace collapsed."""

    return " ".join(text.split())


def _strip_wrapping_code_span(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("`") and stripped.endswith("`") and stripped.count("`") == 2:
        return stripped[1:-1]
    return stripped


def _split_markdown_table_row(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise AssertionError(f"expected markdown table row with edge pipes: {line!r}")
    return tuple(_strip_wrapping_code_span(cell) for cell in stripped.strip("|").split("|"))


def _is_markdown_table_separator(line: str) -> bool:
    if "|" not in line:
        return False
    cells = tuple(cell.strip().replace(" ", "") for cell in line.strip().strip("|").split("|"))
    return bool(cells) and all(_TABLE_SEPARATOR_RE.fullmatch(cell) for cell in cells)


def parse_markdown_table(section: str, *, context: str = "markdown section") -> ParsedMarkdownTable:
    """Parse the first pipe table in a markdown section."""

    lines = section.splitlines()
    for index, line in enumerate(lines[:-1]):
        if not line.strip().startswith("|") or not _is_markdown_table_separator(lines[index + 1]):
            continue

        headers = _split_markdown_table_row(line)
        rows: list[dict[str, str]] = []
        row_index = index + 2
        while row_index < len(lines) and lines[row_index].strip().startswith("|"):
            if _is_markdown_table_separator(lines[row_index]):
                row_index += 1
                continue
            values = _split_markdown_table_row(lines[row_index])
            if len(values) != len(headers):
                raise AssertionError(
                    f"malformed markdown table in {context}: row has {len(values)} cells, expected {len(headers)}"
                )
            rows.append(dict(zip(headers, values, strict=True)))
            row_index += 1

        if not rows:
            raise AssertionError(f"markdown table in {context} has no body rows")
        return ParsedMarkdownTable(headers=headers, rows=tuple(rows))

    raise AssertionError(f"missing markdown table in {context}")


def parse_markdown_links(section: str) -> tuple[ParsedMarkdownLink, ...]:
    """Return inline markdown links with label and href kept separate."""

    return tuple(
        ParsedMarkdownLink(label=match.group(1), href=match.group(2)) for match in _INLINE_LINK_RE.finditer(section)
    )


def assert_markdown_link(section: str, label: str, href: str, *, context: str) -> None:
    links = parse_markdown_links(section)
    if any(link.label == label and link.href == href for link in links):
        return
    raise AssertionError(f"missing markdown link in {context}: label={label!r} href={href!r}; links={links!r}")


def markdown_fence_bodies(text: str, *, info: str | None = None) -> tuple[str, ...]:
    """Return stripped fenced-code bodies, optionally filtered by exact info string."""

    return tuple(
        fence.body.strip() for fence in iter_markdown_fences(text) if info is None or fence.info.strip() == info
    )


def yaml_fence_bodies(text: str, *, info: str | None = None) -> tuple[str, ...]:
    """Return stripped YAML fenced-code bodies."""

    requested_language = info.lower() if info is not None else None
    bodies: list[str] = []
    for match in _YAML_FENCE_RE.finditer(text):
        fence_info = match.group("info").strip()
        language = _fence_language(fence_info)
        if requested_language is None:
            if language not in _YAML_FENCE_LANGUAGES:
                continue
        elif fence_info != info and language != requested_language:
            continue
        bodies.append(match.group("body").strip())
    return tuple(bodies)


def has_line_with_terms(text: str, *terms: str, casefold: bool = False) -> bool:
    """Return whether one line contains all terms."""

    if not terms:
        raise ValueError("at least one term is required")
    needles = tuple(term.casefold() for term in terms) if casefold else terms
    for line in text.splitlines():
        haystack = line.casefold() if casefold else line
        if all(needle in haystack for needle in needles):
            return True
    return False


def tag_blocks(text: str, tag: str) -> tuple[str, ...]:
    """Return bodies for repeated simple XML-style markdown prompt tags."""

    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", tag):
        raise ValueError(f"unsupported tag name: {tag!r}")
    pattern = re.compile(rf"<{re.escape(tag)}(?:\s[^>]*)?>(.*?)</{re.escape(tag)}>", re.DOTALL)
    return tuple(match.group(1).strip("\n") for match in pattern.finditer(text))


def markdown_table_blocks(text: str) -> tuple[tuple[str, ...], ...]:
    """Return contiguous pipe-table line blocks."""

    blocks: list[tuple[str, ...]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            current.append(line)
            continue
        if current:
            blocks.append(tuple(current))
            current = []
    if current:
        blocks.append(tuple(current))
    return tuple(blocks)


def _coerce_fragments(fragments: Iterable[str] | str) -> tuple[str, ...]:
    if isinstance(fragments, str):
        fragments = (fragments,)
    coerced = tuple(fragments)
    if any(fragment == "" for fragment in coerced):
        raise ValueError("fragments must be non-empty")
    return coerced


def _normalize_fragment(fragment: str, *, normalize: bool) -> str:
    return normalize_text(fragment) if normalize else fragment


def _format_fragment_list(fragments: Iterable[str]) -> str:
    return "\n".join(f"- {fragment!r}" for fragment in fragments)


_CONTRACT_FINDING_PATH_RE = re.compile(
    r"^(?P<path>[A-Za-z_][A-Za-z0-9_-]*(?:[.](?:[A-Za-z_][A-Za-z0-9_-]*|[0-9]+)|\[[0-9]+\])*)"
    r"(?::\s*|\s+(?=(?:is|must|references|targets|has|contains|uses|requires|missing)\b))"
    r"(?P<reason>.+)$"
)
_CONTRACT_TOP_LEVEL_FIELDS = {
    "schema_version",
    "scope",
    "context_intake",
    "uncertainty_markers",
    "observables",
    "claims",
    "deliverables",
    "acceptance_tests",
    "references",
    "forbidden_proxies",
    "links",
    "approach_policy",
    "legacy_notes",
    "contract_results",
}


def _looks_like_contract_path(path: str) -> bool:
    return "." in path or "[" in path or "_" in path or path in _CONTRACT_TOP_LEVEL_FIELDS


def parse_contract_findings(messages: Iterable[str]) -> tuple[ParsedContractFinding, ...]:
    """Return path-prefixed contract findings, ignoring free-form relation prose."""

    parsed: list[ParsedContractFinding] = []
    for message in messages:
        for candidate in _contract_finding_candidates(message):
            match = _CONTRACT_FINDING_PATH_RE.match(candidate)
            if match is None:
                continue
            path = match.group("path")
            if not _looks_like_contract_path(path):
                continue
            parsed.append(ParsedContractFinding(message=message, path=path, reason=match.group("reason")))
            break
    return tuple(parsed)


def _contract_finding_candidates(message: str) -> tuple[str, ...]:
    stripped = message.strip()
    candidates = [stripped]
    for marker in ("Invalid contract payload: ", "Value error, "):
        if marker in stripped:
            candidates.append(stripped.split(marker, 1)[1].strip())
    return tuple(candidates)


def assert_contract_finding(
    messages: Iterable[str],
    *,
    path: str,
    contains: Iterable[str] | str = (),
    context: str = "contract findings",
) -> ParsedContractFinding:
    """Assert a path-prefixed contract finding without pinning the full prose."""

    required_terms = _coerce_fragments(contains) if contains else ()
    findings = parse_contract_findings(messages)
    for finding in findings:
        if finding.path == path and all(term in finding.message for term in required_terms):
            return finding
    raise AssertionError(
        f"missing {context} finding for path {path!r} with terms {required_terms!r}; "
        f"parsed={findings!r}; messages={tuple(messages)!r}"
    )


def assert_no_contract_finding(
    messages: Iterable[str],
    *,
    path: str,
    contains: Iterable[str] | str = (),
    context: str = "contract findings",
) -> None:
    """Assert a path-prefixed contract finding is absent."""

    required_terms = _coerce_fragments(contains) if contains else ()
    for finding in parse_contract_findings(messages):
        if finding.path == path and all(term in finding.message for term in required_terms):
            raise AssertionError(f"unexpected {context} finding: {finding.message!r}")


def assert_contract_relation_finding(
    messages: Iterable[str],
    *,
    subject_kind: str,
    subject_id: str,
    relation_terms: Iterable[str] | str,
    target_id: str | None = None,
    context: str = "contract findings",
) -> str:
    """Assert a non-path contract relation finding by typed subject and target terms."""

    required_terms = (subject_kind, subject_id, *_coerce_fragments(relation_terms))
    if target_id is not None:
        required_terms = (*required_terms, target_id)
    for message in messages:
        if all(term in message for term in required_terms):
            return message
    raise AssertionError(
        f"missing {context} relation finding for {subject_kind} {subject_id} "
        f"with terms {required_terms[2:]!r}; messages={tuple(messages)!r}"
    )


def assert_no_contract_relation_finding(
    messages: Iterable[str],
    *,
    subject_kind: str,
    subject_id: str,
    relation_terms: Iterable[str] | str,
    target_id: str | None = None,
    context: str = "contract findings",
) -> None:
    """Assert a non-path contract relation finding is absent."""

    required_terms = (subject_kind, subject_id, *_coerce_fragments(relation_terms))
    if target_id is not None:
        required_terms = (*required_terms, target_id)
    for message in messages:
        if all(term in message for term in required_terms):
            raise AssertionError(f"unexpected {context} relation finding: {message!r}")


def assert_required_fragments(
    text: str,
    fragments: Iterable[str] | str,
    *,
    context: str = "markdown",
    normalize: bool = True,
) -> None:
    """Assert that every fragment appears in the text."""

    required = _coerce_fragments(fragments)
    haystack = normalize_text(text) if normalize else text
    missing = [fragment for fragment in required if _normalize_fragment(fragment, normalize=normalize) not in haystack]
    if missing:
        raise AssertionError(f"missing required fragments in {context}:\n{_format_fragment_list(missing)}")


def assert_forbidden_fragments(
    text: str,
    fragments: Iterable[str] | str,
    *,
    context: str = "markdown",
    normalize: bool = True,
) -> None:
    """Assert that no forbidden fragment appears in the text."""

    forbidden = _coerce_fragments(fragments)
    haystack = normalize_text(text) if normalize else text
    present = [fragment for fragment in forbidden if _normalize_fragment(fragment, normalize=normalize) in haystack]
    if present:
        raise AssertionError(f"forbidden fragments present in {context}:\n{_format_fragment_list(present)}")


def assert_ordered_fragments(
    text: str,
    fragments: Iterable[str] | str,
    *,
    context: str = "markdown",
    normalize: bool = True,
) -> None:
    """Assert that fragments appear in the given order."""

    ordered = _coerce_fragments(fragments)
    haystack = normalize_text(text) if normalize else text
    cursor = 0
    previous_fragment: str | None = None
    for fragment in ordered:
        needle = _normalize_fragment(fragment, normalize=normalize)
        index = haystack.find(needle, cursor)
        if index >= 0:
            cursor = index + len(needle)
            previous_fragment = fragment
            continue

        earlier_index = haystack.find(needle)
        if earlier_index >= 0:
            raise AssertionError(
                f"fragment appears out of order in {context}: {fragment!r} appears before {previous_fragment!r}"
            )
        if previous_fragment is None:
            raise AssertionError(f"missing ordered fragment in {context}: {fragment!r}")
        raise AssertionError(f"missing ordered fragment in {context}: {fragment!r} after {previous_fragment!r}")


def _parse_atx_heading(line: str) -> tuple[int, str, str] | None:
    stripped = line.strip()
    match = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", stripped)
    if match is None:
        return None
    title = match.group(2).rstrip()
    closing = re.search(r"[ \t]+#+[ \t]*$", title)
    if closing is not None:
        title = title[: closing.start()].rstrip()
    if not title:
        return None
    return len(match.group(1)), title, stripped


def _parse_heading_query(heading: str, *, level: int | None) -> tuple[str, int | None]:
    target = heading.strip()
    if not target:
        raise ValueError("heading must be non-empty")
    parsed = _parse_atx_heading(target)
    if parsed is not None:
        inferred_level, title, _atx_heading = parsed
        return title, _validate_level(level) if level is not None else inferred_level
    return target, _validate_level(level) if level is not None else None


def _validate_level(level: int) -> int:
    if level < 1 or level > 6:
        raise ValueError(f"markdown heading level must be between 1 and 6, got {level}")
    return level


def _markdown_fence_marker(stripped_line: str) -> str | None:
    if stripped_line.startswith("```"):
        return "```"
    if stripped_line.startswith("~~~"):
        return "~~~"
    return None


def iter_markdown_sections(text: str, *, context: str = "markdown") -> tuple[MarkdownSection, ...]:
    """Return ATX markdown sections, ignoring headings inside fenced code blocks."""

    lines = text.splitlines(keepends=True)
    headings: list[tuple[int, int, str, str]] = []
    active_fence_marker: str | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        fence_marker = _markdown_fence_marker(stripped)
        if fence_marker is not None:
            if active_fence_marker is None:
                active_fence_marker = fence_marker
            elif fence_marker == active_fence_marker:
                active_fence_marker = None
            continue
        if active_fence_marker is not None:
            continue

        parsed_heading = _parse_atx_heading(line)
        if parsed_heading is None:
            continue
        heading_level, heading, atx_heading = parsed_heading
        headings.append((index, heading_level, heading, atx_heading))

    sections: list[MarkdownSection] = []
    for heading_index, (line_index, level, heading, atx_heading) in enumerate(headings):
        end_index = len(lines)
        for next_line_index, next_level, _next_heading, _next_atx_heading in headings[heading_index + 1 :]:
            if next_level <= level:
                end_index = next_line_index
                break
        body = "".join(lines[line_index + 1 : end_index])
        section_text = "".join(lines[line_index:end_index])
        sections.append(
            MarkdownSection(
                heading=heading,
                level=level,
                body=body,
                start_line=line_index + 1,
                end_line=end_index,
                atx_heading=atx_heading,
                text=section_text,
            )
        )

    return tuple(sections)


def markdown_sections(
    text: str,
    heading: str | None = None,
    *,
    level: int | None = None,
    context: str = "markdown",
) -> tuple[MarkdownSection, ...]:
    """Return markdown sections, optionally filtered by heading and/or level."""

    if heading is None:
        target_heading = None
        target_level = _validate_level(level) if level is not None else None
    else:
        target_heading, target_level = _parse_heading_query(heading, level=level)

    matches: list[MarkdownSection] = []
    for section in iter_markdown_sections(text, context=context):
        if target_heading is not None and section.heading != target_heading:
            continue
        if target_level is not None and section.level != target_level:
            continue
        matches.append(section)
    return tuple(matches)


def markdown_section(
    text: str,
    heading: str,
    *,
    level: int | None = None,
    context: str = "markdown",
) -> MarkdownSection:
    """Return exactly one matching markdown section."""

    matches = markdown_sections(text, heading, level=level, context=context)
    if not matches:
        raise AssertionError(f"missing markdown section in {context}: {heading.strip()!r}")
    if len(matches) > 1:
        match_lines = ", ".join(str(section.start_line) for section in matches)
        raise AssertionError(
            f"multiple markdown sections in {context}: {heading.strip()!r} matched lines {match_lines}"
        )
    return matches[0]


def extract_markdown_section(
    text: str,
    heading: str,
    *,
    context: str = "markdown",
    include_heading: bool = False,
    level: int | None = None,
) -> str:
    """Return a markdown section body, ignoring headings inside fences."""

    section = markdown_section(text, heading, level=level, context=context)
    if include_heading:
        return section.text.strip("\n")
    return section.body.strip("\n")


def extract_marker_range(
    text: str,
    start_marker: str,
    end_marker: str | None = None,
    *,
    context: str = "text",
    include_markers: bool = False,
) -> str:
    """Return text scoped by unique start/end markers."""

    if start_marker == "":
        raise ValueError("start_marker must be non-empty")
    if end_marker == "":
        raise ValueError("end_marker must be non-empty when provided")

    start_count = text.count(start_marker)
    if start_count == 0:
        raise AssertionError(f"missing marker range in {context}: start marker {start_marker!r}")
    if start_count > 1:
        raise AssertionError(
            f"multiple marker ranges in {context}: start marker {start_marker!r} found {start_count} times"
        )

    start_index = text.find(start_marker)
    content_start = start_index + len(start_marker)
    if end_marker is None:
        return text[start_index:] if include_markers else text[content_start:]

    end_count = text.count(end_marker, content_start)
    if end_count == 0:
        raise AssertionError(f"missing marker range in {context}: end marker {end_marker!r}")
    if end_count > 1:
        raise AssertionError(f"multiple marker ranges in {context}: end marker {end_marker!r} found {end_count} times")

    end_index = text.find(end_marker, content_start)
    if include_markers:
        return text[start_index : end_index + len(end_marker)]
    return text[content_start:end_index]


def parse_frontmatter_mapping(text: str, *, context: str = "markdown") -> dict[str, object]:
    """Parse the top-level frontmatter mapping from markdown text."""

    try:
        frontmatter, _body = extract_frontmatter(text)
    except FrontmatterParseError as exc:
        raise AssertionError(f"invalid frontmatter in {context}: {exc}") from exc
    return dict(frontmatter)


def _fence_language(info: str) -> str:
    return info.strip().split(maxsplit=1)[0].lower() if info.strip() else ""


def parse_yaml_fences(
    text: str,
    *,
    info: str | None = None,
    context: str = "markdown",
) -> tuple[ParsedYamlFence, ...]:
    """Parse YAML code fences, preserving each fence's source line metadata."""

    parsed: list[ParsedYamlFence] = []
    requested_language = info.lower() if info is not None else None
    for fence in iter_markdown_fences(text):
        language = _fence_language(fence.info)
        if requested_language is None:
            if language not in _YAML_FENCE_LANGUAGES:
                continue
        elif fence.info.strip() != info and language != requested_language:
            continue

        try:
            data = load_strict_yaml(fence.body)
        except yaml.YAMLError as exc:
            raise AssertionError(
                f"invalid YAML fence in {context} at lines {fence.start_line}-{fence.end_line}: {exc}"
            ) from exc
        parsed.append(
            ParsedYamlFence(
                info=fence.info,
                body=fence.body.strip(),
                data=data,
                start_line=fence.start_line,
                end_line=fence.end_line,
            )
        )
    return tuple(parsed)


def require_mapping(value: object, *, context: str) -> Mapping[object, object]:
    """Return a parsed YAML value as a mapping, or fail with context."""

    if not isinstance(value, Mapping):
        raise AssertionError(f"expected mapping in {context}, got {type(value).__name__}")
    return value
