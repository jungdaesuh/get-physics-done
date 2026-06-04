"""Todo metadata parsing helpers for context assembly."""

from __future__ import annotations

import re
from datetime import date, datetime

__all__ = [
    "_extract_frontmatter_field",
    "_looks_like_todo_frontmatter_candidate",
    "_normalize_todo_frontmatter_text",
    "_normalize_todo_metadata_value",
    "_read_todo_frontmatter",
]


_LEADING_BLANK_LINES_BEFORE_FRONTMATTER_RE = re.compile(r"^(?:[ \t]*\r?\n)+(?=---[ \t]*\r?\n)")


def _normalize_todo_metadata_value(value: object, *, allow_typed_scalars: bool = False) -> str | None:
    """Return a normalized todo metadata value from a todo metadata block."""
    if allow_typed_scalars:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
    if not isinstance(value, str):
        return None
    val = value.strip()
    if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
        val = val[1:-1]
    return val or None


def _normalize_todo_frontmatter_text(content: str) -> str:
    """Return a todo text view that preserves valid frontmatter after blank lines."""
    text = content.lstrip("\ufeff")
    return _LEADING_BLANK_LINES_BEFORE_FRONTMATTER_RE.sub("", text, count=1)


def _read_todo_frontmatter(content: str) -> dict[str, object] | None:
    """Read one todo's YAML frontmatter, returning ``None`` when it is malformed."""
    text = _normalize_todo_frontmatter_text(content)
    if not text.startswith("---"):
        return {}

    from gpd.core.frontmatter import FrontmatterParseError, extract_frontmatter

    try:
        meta, body = extract_frontmatter(text)
    except FrontmatterParseError:
        return None
    if body == text and _looks_like_todo_frontmatter_candidate(text):
        return None
    return meta if isinstance(meta, dict) else {}


def _looks_like_todo_frontmatter_candidate(text: str) -> bool:
    """Return whether a leading ``---`` block appears to be attempted metadata."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for raw_line in lines[1:]:
        stripped = raw_line.strip()
        if not stripped:
            return False
        if stripped == "---":
            return True
        return re.fullmatch(r"[A-Za-z0-9_-]+:[ \t]*(.*)", raw_line) is not None
    return False


def _extract_frontmatter_field(
    content: str,
    field: str,
    *,
    parsed_frontmatter: dict[str, object] | None = None,
) -> str | None:
    """Extract a bare field from the leading todo metadata block only."""
    text = _normalize_todo_frontmatter_text(content)

    if text.startswith("---"):
        meta = parsed_frontmatter if parsed_frontmatter is not None else _read_todo_frontmatter(text)
        if not isinstance(meta, dict):
            return None
        raw_value = meta.get(field)
        return _normalize_todo_metadata_value(raw_value, allow_typed_scalars=field == "created")

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            break
        match = re.fullmatch(r"([A-Za-z0-9_-]+):[ \t]*(.*)", line)
        if not match:
            break
        if match.group(1) != field:
            continue
        return _normalize_todo_metadata_value(match.group(2))

    return None
