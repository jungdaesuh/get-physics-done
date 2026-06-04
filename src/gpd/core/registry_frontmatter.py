"""Frontmatter parsing helpers used by the registry facade."""

from __future__ import annotations

import re
from collections.abc import Callable

import yaml

from gpd.core.strict_yaml import load_strict_yaml

YamlLoader = Callable[[str], object]

_LEADING_BLANK_LINES_BEFORE_FRONTMATTER_RE = re.compile(r"^(?:[ \t]*\r?\n)+(?=---\r?\n)")
_FRONTMATTER_DELIMITER_RE = re.compile(r"^---[ \t]*(?:\r?\n)?$")


def _frontmatter_parts(text: str) -> tuple[str | None, str]:
    """Return raw frontmatter YAML and body from markdown text when present."""

    text = text.lstrip("\ufeff")
    frontmatter_candidate = _LEADING_BLANK_LINES_BEFORE_FRONTMATTER_RE.sub("", text, count=1)
    frontmatter_parts = _split_frontmatter_block(frontmatter_candidate)
    if frontmatter_parts is None:
        return None, text
    return frontmatter_parts


def _parse_frontmatter(
    text: str,
    *,
    yaml_loader: YamlLoader = load_strict_yaml,
) -> tuple[dict[str, object], str]:
    """Parse YAML frontmatter from markdown text. Returns (meta, body)."""

    yaml_str, body = _frontmatter_parts(text)
    if yaml_str is None:
        return {}, text
    meta = _load_frontmatter_mapping(
        yaml_str,
        error_prefix="Malformed YAML frontmatter",
        yaml_loader=yaml_loader,
    )
    return meta, body


def _load_frontmatter_mapping(
    frontmatter: str,
    *,
    error_prefix: str,
    yaml_loader: YamlLoader = load_strict_yaml,
) -> dict[str, object]:
    """Load YAML frontmatter into a mapping while rejecting duplicate keys."""

    try:
        meta = yaml_loader(frontmatter) if frontmatter.strip() else {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{error_prefix}: {exc}") from exc
    if meta is None:
        return {}
    if not isinstance(meta, dict):
        raise ValueError(f"Frontmatter must parse to a mapping, got {type(meta).__name__}")
    return meta


def _split_frontmatter_block(text: str) -> tuple[str, str] | None:
    """Return ``(frontmatter, body)`` when *text* begins with markdown frontmatter."""

    lines = text.splitlines(keepends=True)
    if not lines or not _is_frontmatter_delimiter(lines[0]):
        return None

    frontmatter_lines: list[str] = []
    for index, line in enumerate(lines[1:], start=1):
        if _is_frontmatter_delimiter(line):
            return "".join(frontmatter_lines), "".join(lines[index + 1 :])
        frontmatter_lines.append(line)
    return None


def _is_frontmatter_delimiter(line: str) -> bool:
    """Return whether *line* is a frontmatter delimiter line."""

    return _FRONTMATTER_DELIMITER_RE.fullmatch(line) is not None


def _format_frontmatter_field_subject(field_name: str, owner_name: str | None = None) -> str:
    """Return a field label suitable for targeted validation errors."""

    if owner_name:
        return f"{field_name} for {owner_name}"
    return field_name


def _raw_scalar_frontmatter_value(frontmatter: str | None, *, field_name: str) -> str | None:
    """Return the raw scalar text for one frontmatter field when present."""

    if not frontmatter:
        return None

    pattern = re.compile(rf"(?m)^[ \t]*{re.escape(field_name)}:[ \t]*(?P<value>[^#\r\n]*)[ \t]*(?:#.*)?$")
    match = pattern.search(frontmatter)
    if match is None:
        return None
    return match.group("value").strip()


def _parse_frontmatter_string_field(
    raw: object,
    *,
    field_name: str,
    owner_name: str,
    default: str = "",
    required: bool = False,
) -> str:
    """Validate frontmatter scalar fields that must stay strings."""

    if raw is None:
        if default:
            return default
        if required:
            subject = _format_frontmatter_field_subject(field_name, owner_name)
            raise ValueError(f"{subject} must be a non-empty string")
        return default
    if not isinstance(raw, str):
        subject = _format_frontmatter_field_subject(field_name, owner_name)
        raise ValueError(f"{subject} must be a string")
    value = raw.strip()
    if required and not value:
        subject = _format_frontmatter_field_subject(field_name, owner_name)
        raise ValueError(f"{subject} must be a non-empty string")
    return value


def _parse_tools(raw: object, *, field_name: str = "tools", owner_name: str | None = None) -> list[str]:
    """Normalize tools-like frontmatter fields with explicit validation."""

    if raw is None:
        return []
    values: list[str] = []
    seen: set[str] = set()
    subject = _format_frontmatter_field_subject(field_name, owner_name)

    def _append(value: str) -> None:
        if not value:
            raise ValueError(f"{subject} must not contain blank entries")
        if value not in seen:
            seen.add(value)
            values.append(value)

    if isinstance(raw, str):
        for item in raw.split(","):
            _append(item.strip())
        return values
    if not isinstance(raw, list):
        raise ValueError(f"{subject} must be a string or list of strings")

    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"{subject} must contain only strings")
        _append(item.strip())
    return values


def _merge_tool_lists(*tool_lists: list[str]) -> list[str]:
    """Merge multiple tool lists while preserving first-seen order."""

    merged: list[str] = []
    seen: set[str] = set()
    for tool_list in tool_lists:
        for tool in tool_list:
            if tool in seen:
                continue
            seen.add(tool)
            merged.append(tool)
    return merged


def _parse_requires(raw: object, *, command_name: str) -> dict[str, object]:
    """Normalize command requires frontmatter without accepting malformed mappings."""

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"requires for {command_name} must be a mapping")
    unsupported_keys = sorted(str(key) for key in raw if str(key) != "files")
    if unsupported_keys:
        formatted = ", ".join(unsupported_keys)
        raise ValueError(f"requires for {command_name} only supports files; got {formatted}")
    files = raw.get("files")
    if files is None:
        return {}
    normalized_files: list[str] = []
    seen: set[str] = set()
    if isinstance(files, str):
        candidates = [files]
    elif isinstance(files, list):
        candidates = files
    else:
        raise ValueError(f"files for {command_name} must be a string or list of strings")
    for item in candidates:
        if not isinstance(item, str):
            raise ValueError(f"files for {command_name} must contain only strings")
        normalized = item.strip()
        if not normalized:
            raise ValueError(f"files for {command_name} must not contain blank entries")
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_files.append(normalized)
    return {"files": normalized_files}


def _parse_allowed_tools(raw: object, *, command_name: str) -> list[str]:
    """Normalize command allowed-tools frontmatter without coercing invalid entries."""

    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"allowed-tools for {command_name} must be a list of strings")

    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"allowed-tools for {command_name} must contain only strings")
        value = item.strip()
        if not value:
            raise ValueError(f"allowed-tools for {command_name} must not contain blank entries")
        if value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _parse_bool_field(raw: object, *, field_name: str, command_name: str, default: bool = False) -> bool:
    """Parse a strict YAML boolean and reject non-boolean coercion aliases."""

    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    raise ValueError(f"{field_name} for {command_name} must be a boolean")


def _validate_raw_boolean_frontmatter_field(
    frontmatter: str | None,
    *,
    field_name: str,
    command_name: str,
) -> None:
    """Reject non-boolean scalar spellings before YAML coercion can hide them."""

    raw_value = _raw_scalar_frontmatter_value(frontmatter, field_name=field_name)
    if raw_value is None:
        return
    if raw_value.casefold() in {"true", "false"}:
        return
    raise ValueError(f"{field_name} for {command_name} must be a boolean")


def _validate_raw_nonempty_string_frontmatter_field(
    frontmatter: str | None,
    *,
    field_name: str,
    owner_name: str,
) -> None:
    """Reject explicit blank or null scalar spellings before YAML hides them."""

    raw_value = _raw_scalar_frontmatter_value(frontmatter, field_name=field_name)
    if raw_value is None:
        return
    if raw_value.casefold() not in {"", "null", "~"}:
        return
    raise ValueError(f"{field_name} for {owner_name} must be a non-empty string")


__all__ = [
    "YamlLoader",
    "_frontmatter_parts",
    "_load_frontmatter_mapping",
    "_merge_tool_lists",
    "_parse_allowed_tools",
    "_parse_bool_field",
    "_parse_frontmatter",
    "_parse_frontmatter_string_field",
    "_parse_requires",
    "_parse_tools",
    "_raw_scalar_frontmatter_value",
    "_validate_raw_boolean_frontmatter_field",
    "_validate_raw_nonempty_string_frontmatter_field",
]
