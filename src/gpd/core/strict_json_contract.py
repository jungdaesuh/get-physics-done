"""Small strict JSON validation helpers for checked-in machine contracts."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

JsonObject = dict[str, object]


def load_json_file(path: Path, *, label: str) -> object:
    """Load a JSON file and label decode failures with the owning contract."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON: {exc.msg}") from exc


def require_object(
    value: object,
    *,
    label: str,
    object_name: str = "JSON object",
    non_empty: bool = False,
) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a {object_name}")
    if non_empty and not value:
        raise ValueError(f"{label} must be a non-empty {object_name}")
    return value


def require_required_keys(payload: Mapping[str, object], *, label: str, keys: Iterable[str]) -> None:
    missing = sorted(key for key in keys if key not in payload)
    if missing:
        raise ValueError(f"{label} is missing required key(s): {', '.join(missing)}")


def require_allowed_keys(payload: Mapping[str, object], *, label: str, keys: Iterable[str]) -> None:
    unknown = sorted(key for key in payload if key not in keys)
    if unknown:
        raise ValueError(f"{label} contains unknown key(s): {', '.join(unknown)}")


def require_schema_version(
    value: object,
    *,
    label: str,
    expected: int = 1,
    invalid_message: str | None = None,
) -> int:
    if type(value) is int and value == expected:
        return value
    if invalid_message is not None:
        raise ValueError(invalid_message.format(label=label, expected=expected, value=value))
    raise ValueError(f"{label} must be the integer {expected}; got {value!r}")


def require_string(value: object, *, label: str, trim: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a non-empty string")
    normalized = value.strip() if trim else value
    if not normalized or (not trim and value != value.strip()):
        raise ValueError(f"{label} must be a non-empty string")
    return normalized


def require_bool(value: object, *, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} must be a boolean")
    return value


def require_int(value: object, *, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


def require_unique_string_tuple(
    value: object,
    *,
    label: str,
    allow_empty: bool,
    trim: bool = False,
    list_label: str = "list of strings",
    empty_message: str | None = None,
    entry_message: str | None = None,
    duplicate_message: str | None = None,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a {list_label}")
    if not value and not allow_empty:
        raise ValueError(empty_message or f"{label} must contain at least one string")

    items: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        try:
            normalized = require_string(item, label=f"{label}[{index}]", trim=trim)
        except ValueError as exc:
            if entry_message is None:
                raise
            raise ValueError(entry_message.format(label=label, index=index)) from exc
        if normalized in seen:
            raise ValueError(duplicate_message or f"{label} must not contain duplicate values")
        seen.add(normalized)
        items.append(normalized)
    return tuple(items)


def require_literal(value: object, *, label: str, allowed: Iterable[str]) -> str:
    normalized = require_string(value, label=label)
    allowed_values = tuple(sorted(allowed))
    if normalized not in allowed_values:
        formatted = ", ".join(allowed_values)
        raise ValueError(f"{label} must be one of: {formatted}; got {normalized!r}")
    return normalized


def require_key_coverage(
    payload: Mapping[str, object],
    *,
    label: str,
    allowed_keys: Iterable[str],
    required_keys: Iterable[str] | None = None,
) -> None:
    allowed = frozenset(allowed_keys)
    required = allowed if required_keys is None else frozenset(required_keys)
    missing = sorted(key for key in required if key not in payload)
    unknown = sorted(key for key in payload if key not in allowed)
    if not missing and not unknown:
        return

    problems: list[str] = []
    if missing:
        problems.append(f"missing required key(s): {', '.join(missing)}")
    if unknown:
        problems.append(f"unknown key(s): {', '.join(unknown)}")
    raise ValueError(f"{label} key coverage mismatch: {'; '.join(problems)}")


__all__ = [
    "JsonObject",
    "load_json_file",
    "require_allowed_keys",
    "require_bool",
    "require_int",
    "require_key_coverage",
    "require_literal",
    "require_object",
    "require_required_keys",
    "require_schema_version",
    "require_string",
    "require_unique_string_tuple",
]
