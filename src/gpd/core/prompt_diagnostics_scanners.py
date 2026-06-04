"""Scanner helpers for prompt-surface diagnostics."""

from __future__ import annotations

import difflib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

import yaml

from gpd.adapters.install_utils import DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES
from gpd.core import prompt_markdown_scan as _prompt_markdown_scan
from gpd.core.frontmatter import (
    UNSUPPORTED_FRONTMATTER_FIELDS,
    VERIFICATION_REPORT_STATUSES,
    FrontmatterParseError,
    extract_frontmatter,
    validate_frontmatter,
)
from gpd.core.prompt_diagnostics_types import (
    ForbiddenChildReturnSynthesisMention,
    InvalidFrontmatterExample,
    InvalidGpdReturnExample,
    PromptReturnFieldMention,
    PromptSource,
)
from gpd.core.return_contract import GpdReturnEnvelope, validate_gpd_return_markdown
from gpd.core.return_fields import ReturnFieldAllowedSource, known_return_field_names, return_field_source

MarkdownFence = _prompt_markdown_scan.MarkdownFence
_body_without_frontmatter = _prompt_markdown_scan.body_without_frontmatter
_body_without_frontmatter_with_line_offset = _prompt_markdown_scan.body_without_frontmatter_with_line_offset
_iter_markdown_fences = _prompt_markdown_scan.iter_markdown_fences
_iter_unfenced_lines = _prompt_markdown_scan.iter_unfenced_lines
_relative_path = _prompt_markdown_scan.relative_path
_RETURN_FIELD_BASE_FIELDS = tuple(GpdReturnEnvelope.model_fields)

_SPAWN_CONTRACT_RE = re.compile(
    r"^[ \t]*<spawn_contract(?:_interactive)?>[ \t]*$",
    re.MULTILINE,
)
_SCHEMA_BLOCK_MARKERS = (
    "gpd_return:",
    '"gpd_return"',
    "'gpd_return'",
    "schema_version",
    "contract_results",
    "project_contract",
)
_SCHEMA_FENCE_LANGUAGES = frozenset({"yaml", "yml", "json", "toml"})
_MARKDOWN_FRONTMATTER_FENCE_LANGUAGES = frozenset({"markdown", "md", ""})
_VERIFICATION_FRONTMATTER_KEYS = frozenset(
    {
        "phase",
        "verified",
        "status",
        "score",
        "plan_contract_ref",
        "contract_results",
        "comparison_verdicts",
        "suggested_contract_checks",
    }
)
_VERIFICATION_FRONTMATTER_STRONG_KEYS = frozenset(
    {
        "plan_contract_ref",
        "contract_results",
        "comparison_verdicts",
        "suggested_contract_checks",
    }
)
_GPD_RETURN_EXAMPLE_RE = re.compile(r"(?m)(?:^|[\s{,\[\('\"`])['\"]?gpd_return['\"]?\s*:")
_HARD_GATE_LINE_RE = re.compile(
    r"\b(?:STOP|fail[- ]closed|do not proceed|must|required|never|forbidden|reject|cannot|blocked)\b",
    re.IGNORECASE,
)
_SHELL_PARSING_RE = re.compile(
    r"(?:\bgpd\s+--raw\b|\bjq\b|\bsed\b|\bawk\b|\bgrep\b|\bmktemp\b|\$\(|<<-?|"
    r"^\s*case\b|\bcase\s+.*\bin\b|\bprintf\b|\bcat\s+GPD\b)"
)
_GPD_RETURN_FIELD_REFERENCE_RE = re.compile(r"(?<![A-Za-z0-9_])\.?gpd_return\.([A-Za-z_][A-Za-z0-9_]*)")
_RETURN_FIELD_DECLARATION_RE = re.compile(
    r"\b(?:extended fields?|role-specific field|agent-specific extended field|role fields such as)\b",
    re.IGNORECASE,
)
_ROLE_FIELD_DECLARATION_RE = re.compile(
    r"\b(?:role-specific field|agent-specific extended field|role fields such as)\b",
    re.IGNORECASE,
)
_BACKTICK_IDENTIFIER_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_RETURN_FIELD_NEGATION_RE = re.compile(
    r"\b(?:do not|don't|never|forbidden|must not|not part of|omit|without)\b",
    re.IGNORECASE,
)
_YAML_KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?)\s*:")
_FIELD_DECLARATION_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "come",
        "comes",
        "extended",
        "field",
        "fields",
        "from",
        "include",
        "is",
        "must",
        "or",
        "role",
        "such",
        "the",
        "these",
        "this",
        "top",
        "with",
    }
)
_CHILD_RETURN_SYNTHESIS_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|;\s*")
_CHILD_RETURN_SYNTHESIS_ACTION_RE = re.compile(
    r"\b(?P<action>"
    r"synthesi[sz]e|synthesi[sz]ed|synthesi[sz]ing|"
    r"fabricate|fabricated|fabricating|"
    r"patch|patched|patching|"
    r"paste|pasted|pasting|"
    r"hand-author|hand-authored|hand-authoring|hand author|hand authored|hand authoring"
    r")\b",
    re.IGNORECASE,
)
_CHILD_RETURN_SYNTHESIS_CONTEXT_RE = re.compile(
    r"\b(?:child|planner|checker|verifier|agent|subagent)\b.{0,140}"
    r"\b(?:gpd_return|return envelope)\b|"
    r"\b(?:gpd_return|return envelope)\b.{0,140}"
    r"\b(?:child|planner|checker|verifier|agent|subagent)\b",
    re.IGNORECASE,
)
_CHILD_RETURN_SYNTHESIS_NEGATION_RE = re.compile(
    r"\b(?:do not|don't|never|must not|should not|cannot|can't|forbidden|not allowed|without|instead of)\b",
    re.IGNORECASE,
)


def _count_shell_fences(text: str) -> int:
    count = 0
    for fence in _iter_markdown_fences(_body_without_frontmatter(text)):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
            count += 1
    return count


def _inspect_visible_schema_examples(
    text: str,
    path: str,
) -> tuple[int, tuple[InvalidGpdReturnExample, ...], tuple[InvalidFrontmatterExample, ...]]:
    body, line_offset = _body_without_frontmatter_with_line_offset(text)
    visible_count = 0
    invalid_return_examples: list[InvalidGpdReturnExample] = []
    invalid_frontmatter_examples: list[InvalidFrontmatterExample] = []

    for fence in _iter_markdown_fences(body):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        invalid_frontmatter = _inspect_verification_frontmatter_example(
            fence,
            path=path,
            line_offset=line_offset,
            language=language,
        )
        is_schema_block = _is_visible_schema_fence(language, fence.body)
        if not is_schema_block and invalid_frontmatter is None:
            continue
        visible_count += 1
        if invalid_frontmatter is not None:
            invalid_frontmatter_examples.append(invalid_frontmatter)
        if invalid_frontmatter is not None or not _contains_visible_gpd_return_example(fence.body):
            continue
        validation = validate_gpd_return_markdown(f"```yaml\n{fence.body}\n```")
        if validation.passed:
            continue
        invalid_return_examples.append(
            InvalidGpdReturnExample(
                path=path,
                start_line=fence.start_line + line_offset,
                end_line=fence.end_line + line_offset,
                errors=tuple(validation.errors),
                preview=_preview_fence_body(fence.body),
            )
        )

    spawn_contract_count = len(_SPAWN_CONTRACT_RE.findall(body))
    visible_count += spawn_contract_count
    return visible_count, tuple(invalid_return_examples), tuple(invalid_frontmatter_examples)


def _inspect_verification_frontmatter_example(
    fence: MarkdownFence,
    *,
    path: str,
    line_offset: int,
    language: str,
) -> InvalidFrontmatterExample | None:
    candidate = _verification_frontmatter_candidate_from_fence(fence, language=language)
    if candidate is None:
        return None
    candidate_text, meta = candidate
    fields = _invalid_verification_frontmatter_fields(meta)
    if not fields:
        return None
    errors = _verification_frontmatter_lint_errors(candidate_text, fields)
    if not errors:
        return None
    return InvalidFrontmatterExample(
        path=path,
        start_line=fence.start_line + line_offset,
        end_line=fence.end_line + line_offset,
        schema_name="verification",
        fields=fields,
        errors=errors,
        preview=_preview_fence_body(fence.body),
    )


def _verification_frontmatter_candidate_from_fence(
    fence: MarkdownFence,
    *,
    language: str,
) -> tuple[str, Mapping[str, object]] | None:
    if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
        return None
    if language in _MARKDOWN_FRONTMATTER_FENCE_LANGUAGES:
        candidate_text = fence.body.lstrip()
        if not _starts_with_markdown_frontmatter(candidate_text):
            return None
        try:
            meta, _body = extract_frontmatter(candidate_text)
        except FrontmatterParseError:
            return None
        if not _looks_like_verification_frontmatter(meta):
            return None
        return candidate_text, meta
    if language not in {"yaml", "yml"}:
        return None
    try:
        parsed = yaml.safe_load(fence.body)
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, Mapping):
        return None
    meta = {key: value for key, value in parsed.items() if isinstance(key, str)}
    if not _looks_like_verification_frontmatter(meta):
        return None
    return f"---\n{fence.body.rstrip()}\n---\n", meta


def _starts_with_markdown_frontmatter(text: str) -> bool:
    return text.startswith("---\n") or text.startswith("---\r\n")


def _looks_like_verification_frontmatter(meta: Mapping[str, object]) -> bool:
    keys = frozenset(key for key in meta if isinstance(key, str))
    if not keys:
        return False
    unsupported_keys = keys & frozenset(UNSUPPORTED_FRONTMATTER_FIELDS["verification"])
    verification_key_count = len(keys & _VERIFICATION_FRONTMATTER_KEYS)
    if keys & _VERIFICATION_FRONTMATTER_STRONG_KEYS:
        return True
    if "phase" in keys and keys & {"verified", "status", "score", "plan_contract_ref"}:
        return True
    if verification_key_count >= 2:
        return True
    return bool(unsupported_keys and keys & {"phase", "status", "verified", "score"})


def _invalid_verification_frontmatter_fields(meta: Mapping[str, object]) -> tuple[str, ...]:
    unsupported = frozenset(UNSUPPORTED_FRONTMATTER_FIELDS["verification"])
    fields = [field for field in sorted(unsupported) if field in meta]
    if "status" in meta:
        raw_status = meta.get("status")
        if not isinstance(raw_status, str) or raw_status.strip() not in VERIFICATION_REPORT_STATUSES:
            fields.append("status")
    return tuple(dict.fromkeys(fields))


def _verification_frontmatter_lint_errors(candidate_text: str, fields: Sequence[str]) -> tuple[str, ...]:
    field_set = frozenset(fields)
    try:
        validation = validate_frontmatter(candidate_text, "verification")
    except FrontmatterParseError:
        return ()
    return tuple(error for error in validation.errors if _verification_frontmatter_lint_error_field(error) in field_set)


def _verification_frontmatter_lint_error_field(error: str) -> str | None:
    field, separator, _detail = error.partition(":")
    if not separator:
        return None
    return field.strip()


def _scan_return_field_mentions_for_repo(
    repo_root: Path,
    *,
    include_tests: bool,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for path in _return_field_scan_paths(repo_root, include_tests=include_tests):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        mentions.extend(_scan_return_field_mentions(text, _relative_path(path, repo_root)))
    return tuple(
        sorted(
            mentions,
            key=lambda mention: (
                mention.path,
                mention.line,
                mention.field,
                mention.mention_kind,
            ),
        )
    )


def _scan_return_field_mentions(text: str, path: str) -> tuple[PromptReturnFieldMention, ...]:
    body, line_offset = _body_without_frontmatter_with_line_offset(text)
    mentions: list[PromptReturnFieldMention] = []
    mentions.extend(_scan_direct_return_field_references(body, path, line_offset=line_offset))
    mentions.extend(_scan_return_field_declarations(body, path, line_offset=line_offset))
    mentions.extend(_scan_yaml_return_field_keys(body, path, line_offset=line_offset))
    return tuple(_dedupe_return_field_mentions(mentions))


def _scan_forbidden_child_return_synthesis_mentions(
    sources: Sequence[PromptSource],
) -> tuple[ForbiddenChildReturnSynthesisMention, ...]:
    mentions: list[ForbiddenChildReturnSynthesisMention] = []
    for source in sources:
        if source.kind != "workflow":
            continue
        try:
            text = source.absolute_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        body, line_offset = _body_without_frontmatter_with_line_offset(text)
        for line_number, line in _iter_unfenced_lines(body):
            for clause in _child_return_synthesis_clauses(line):
                action = _forbidden_child_return_synthesis_action(clause)
                if action is None:
                    continue
                mentions.append(
                    ForbiddenChildReturnSynthesisMention(
                        path=source.path,
                        line=line_number + line_offset,
                        action=action,
                        polarity="positive",
                        severity="error",
                        snippet=_prompt_line_snippet(clause),
                    )
                )
    return tuple(
        sorted(
            mentions,
            key=lambda mention: (
                mention.path,
                mention.line,
                mention.action,
                mention.snippet,
            ),
        )
    )


def _child_return_synthesis_clauses(line: str) -> tuple[str, ...]:
    normalized = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", line).strip()
    normalized = normalized.strip("`*_ ")
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return ()
    return tuple(
        part.strip(" -") for part in _CHILD_RETURN_SYNTHESIS_CLAUSE_SPLIT_RE.split(normalized) if part.strip(" -")
    ) or (normalized,)


def _forbidden_child_return_synthesis_action(clause: str) -> str | None:
    action_match = _CHILD_RETURN_SYNTHESIS_ACTION_RE.search(clause)
    if action_match is None:
        return None
    if not _CHILD_RETURN_SYNTHESIS_CONTEXT_RE.search(clause):
        return None
    if _CHILD_RETURN_SYNTHESIS_NEGATION_RE.search(clause):
        return None
    if _is_main_context_fallback_return_clause(clause):
        return None
    return action_match.group("action").casefold().replace(" ", "-")


def _is_main_context_fallback_return_clause(clause: str) -> bool:
    folded = clause.casefold()
    if "fallback" not in folded:
        return False
    has_main_context = "main-context" in folded or "main context" in folded
    has_own_return = ("own" in folded or "owns" in folded) and (
        "gpd_return" in folded or "return envelope" in folded or "own return" in folded
    )
    return has_main_context and has_own_return


def _scan_direct_return_field_references(
    body: str,
    path: str,
    *,
    line_offset: int,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for line_number, line in enumerate(body.splitlines(), start=1):
        for match in _GPD_RETURN_FIELD_REFERENCE_RE.finditer(line):
            mentions.append(
                _build_return_field_mention(
                    path=path,
                    line=line_number + line_offset,
                    field=match.group(1),
                    mention_kind="direct_reference",
                    snippet=line,
                )
            )
    return tuple(mentions)


def _scan_return_field_declarations(
    body: str,
    path: str,
    *,
    line_offset: int,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for line_number, line in _iter_unfenced_lines(body):
        declaration_match = _RETURN_FIELD_DECLARATION_RE.search(line)
        if declaration_match is None:
            continue
        mention_kind: Literal["extended_field_list", "role_field_statement"] = (
            "role_field_statement" if _ROLE_FIELD_DECLARATION_RE.search(line) else "extended_field_list"
        )
        for field in _declared_return_fields(line, declaration_match):
            mentions.append(
                _build_return_field_mention(
                    path=path,
                    line=line_number + line_offset,
                    field=field,
                    mention_kind=mention_kind,
                    snippet=line,
                )
            )
    return tuple(mentions)


def _declared_return_fields(line: str, declaration_match: re.Match[str]) -> tuple[str, ...]:
    field_span = line[declaration_match.end() :]
    backticked = tuple(_BACKTICK_IDENTIFIER_RE.findall(field_span))
    if backticked:
        return tuple(field for field in backticked if field != "gpd_return")

    declaration_text = declaration_match.group(0).casefold()
    has_explicit_list_intro = (
        ":" in field_span or "such as" in declaration_text or re.search(r"\bsuch as\b", field_span, re.IGNORECASE)
    )
    if not has_explicit_list_intro:
        return ()

    such_as_match = re.search(r"\bsuch as\b", field_span, re.IGNORECASE)
    if such_as_match is not None:
        field_span = field_span[such_as_match.end() :]
    colon_index = field_span.find(":")
    if colon_index >= 0:
        field_span = field_span[colon_index + 1 :]
    if "." in field_span:
        field_span = field_span.split(".", 1)[0]
    fields = []
    for field in _IDENTIFIER_RE.findall(field_span):
        if field.casefold() in _FIELD_DECLARATION_STOP_WORDS:
            continue
        fields.append(field)
    return tuple(fields)


def _scan_yaml_return_field_keys(
    body: str,
    path: str,
    *,
    line_offset: int,
) -> tuple[PromptReturnFieldMention, ...]:
    mentions: list[PromptReturnFieldMention] = []
    for fence in _iter_markdown_fences(body):
        language = fence.info.lower().split(None, 1)[0] if fence.info else ""
        if language not in {"yaml", "yml"}:
            continue
        if not _contains_visible_gpd_return_example(fence.body):
            continue
        try:
            parsed = yaml.safe_load(fence.body)
        except yaml.YAMLError:
            continue
        if not isinstance(parsed, Mapping):
            continue
        raw_envelope = parsed.get("gpd_return")
        if not isinstance(raw_envelope, Mapping):
            continue
        for raw_field in raw_envelope:
            if not isinstance(raw_field, str):
                continue
            mentions.append(
                _build_return_field_mention(
                    path=path,
                    line=_yaml_return_field_line(fence.body, raw_field, fence.start_line + line_offset),
                    field=raw_field,
                    mention_kind="yaml_example_key",
                    snippet=f"{raw_field}:",
                )
            )
    return tuple(mentions)


def _yaml_return_field_line(body: str, field: str, fence_start_line: int) -> int:
    in_gpd_return = False
    gpd_return_indent = -1
    child_indent: int | None = None
    for offset, line in enumerate(body.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _YAML_KEY_RE.match(line)
        if match is None:
            continue
        indent = len(match.group("indent").replace("\t", "    "))
        key = match.group("key").strip("'\"")
        if not in_gpd_return:
            if key == "gpd_return":
                in_gpd_return = True
                gpd_return_indent = indent
            continue
        if indent <= gpd_return_indent:
            break
        if child_indent is None:
            child_indent = indent
        if indent == child_indent and key == field:
            return fence_start_line + offset
    return fence_start_line


def _dedupe_return_field_mentions(
    mentions: Sequence[PromptReturnFieldMention],
) -> tuple[PromptReturnFieldMention, ...]:
    seen: set[tuple[str, int, str, str, str]] = set()
    deduped: list[PromptReturnFieldMention] = []
    for mention in mentions:
        key = (
            mention.path,
            mention.line,
            mention.field,
            mention.mention_kind,
            mention.polarity,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(mention)
    return tuple(deduped)


def _build_return_field_mention(
    *,
    path: str,
    line: int,
    field: str,
    mention_kind: Literal[
        "direct_reference",
        "extended_field_list",
        "role_field_statement",
        "yaml_example_key",
    ],
    snippet: str,
) -> PromptReturnFieldMention:
    allowed_source = _return_field_allowed_source(field)
    allowed = allowed_source != "unknown"
    polarity: Literal["positive", "negative"] = "negative" if _RETURN_FIELD_NEGATION_RE.search(snippet) else "positive"
    severity: Literal["info", "warn", "error"] = "info"
    if not allowed:
        severity = "warn" if polarity == "negative" else "error"
    return PromptReturnFieldMention(
        path=path,
        line=line,
        field=field,
        mention_kind=mention_kind,
        polarity=polarity,
        allowed=allowed,
        allowed_source=allowed_source,
        severity=severity,
        snippet=_prompt_line_snippet(snippet),
        suggestion=_return_field_suggestion(field) if not allowed else None,
    )


def _return_field_suggestion(field: str) -> str | None:
    matches = difflib.get_close_matches(field, sorted(_known_return_field_names()), n=1)
    return matches[0] if matches else None


def _return_field_allowed_source(field: str) -> ReturnFieldAllowedSource:
    return return_field_source(field, base_fields=_RETURN_FIELD_BASE_FIELDS)


def _known_return_field_names() -> frozenset[str]:
    return known_return_field_names(_RETURN_FIELD_BASE_FIELDS)


def _prompt_line_snippet(line: str, max_chars: int = 180) -> str:
    snippet = re.sub(r"\s+", " ", line.strip())
    if len(snippet) <= max_chars:
        return snippet
    return snippet[: max_chars - 3].rstrip() + "..."


def _disallowed_return_field_mentions(
    mentions: Sequence[PromptReturnFieldMention],
) -> tuple[PromptReturnFieldMention, ...]:
    return tuple(mention for mention in mentions if mention.severity == "error")


def _is_visible_schema_fence(language: str, body: str) -> bool:
    if language in _SCHEMA_FENCE_LANGUAGES:
        return True
    if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
        return False
    return any(marker in body for marker in _SCHEMA_BLOCK_MARKERS)


def _contains_visible_gpd_return_example(body: str) -> bool:
    return bool(_GPD_RETURN_EXAMPLE_RE.search(body))


def _preview_fence_body(body: str, max_chars: int = 140) -> str:
    preview = " ".join(line.strip() for line in body.splitlines() if line.strip())
    if len(preview) <= max_chars:
        return preview
    return preview[: max_chars - 3].rstrip() + "..."


def _hard_gate_metrics(text: str) -> tuple[int, float]:
    body = _body_without_frontmatter(text)
    lines = [(line_number, line) for line_number, line in _iter_unfenced_lines(body) if line.strip()]
    hard_gate_count = sum(1 for _line_number, line in lines if _HARD_GATE_LINE_RE.search(line))
    density = hard_gate_count / len(lines) if lines else 0.0
    return hard_gate_count, round(density, 6)


def _count_shell_parsing_lines(text: str) -> int:
    body = _body_without_frontmatter(text)
    count = 0
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(r"`?/?gpd:?help`?", stripped):
            continue
        if _SHELL_PARSING_RE.search(stripped):
            count += 1
    return count


def _return_field_scan_paths(repo_root: Path, *, include_tests: bool) -> tuple[Path, ...]:
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


def _source_root_for_repo(repo_root: Path) -> Path:
    src_root = repo_root / "src" / "gpd"
    if src_root.is_dir():
        return src_root
    if (repo_root / "commands").is_dir() and (repo_root / "agents").is_dir():
        return repo_root
    return src_root
