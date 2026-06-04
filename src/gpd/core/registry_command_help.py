"""Command help frontmatter parsing for the registry facade."""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache

from gpd.command_labels import CANONICAL_COMMAND_PREFIX, parse_command_label, runtime_public_command_prefixes
from gpd.core.registry_types import CommandHelpMetadata, CommandHelpVariant

_COMMAND_HELP_KEYS = frozenset(
    {
        "group",
        "order",
        "compact_description",
        "display_signature",
        "detail_signature",
        "examples",
        "notes",
        "root_detail_order",
        "variants",
    }
)
_COMMAND_HELP_VARIANT_KEYS = frozenset({"command", "description", "examples", "notes"})


@lru_cache(maxsize=1)
def _runtime_specific_help_label_pattern() -> re.Pattern[str]:
    prefixes = tuple(prefix for prefix in runtime_public_command_prefixes() if prefix != CANONICAL_COMMAND_PREFIX)
    if not prefixes:
        return re.compile(r"$^")
    escaped_prefixes = "|".join(re.escape(prefix) for prefix in prefixes)
    return re.compile(rf"(?<![A-Za-z0-9_-])(?P<label>(?:{escaped_prefixes})[A-Za-z0-9][A-Za-z0-9-]*)")


def _reject_runtime_specific_help_labels(value: str, *, field_name: str, command_name: str) -> None:
    """Reject runtime-specific command labels in canonical help metadata."""

    match = _runtime_specific_help_label_pattern().search(value)
    if match is not None:
        raise ValueError(
            f"{field_name} for {command_name} must use canonical gpd: labels; "
            f"got runtime-specific label {match.group('label')!r}"
        )


def _parse_command_help_string(
    raw: object,
    *,
    field_name: str,
    command_name: str,
    required: bool = False,
) -> str | None:
    """Validate display-only help scalar string fields."""

    subject = f"{field_name} for {command_name}"
    if raw is None:
        if required:
            raise ValueError(f"{subject} must be a non-empty string")
        return None
    if not isinstance(raw, str):
        raise ValueError(f"{subject} must be a string")
    value = raw.strip()
    if not value:
        raise ValueError(f"{subject} must be a non-empty string")
    _reject_runtime_specific_help_labels(value, field_name=field_name, command_name=command_name)
    return value


def _parse_command_help_int(raw: object, *, field_name: str, command_name: str, required: bool = False) -> int | None:
    """Validate display-only help integer fields without accepting YAML booleans."""

    subject = f"{field_name} for {command_name}"
    if raw is None:
        if required:
            raise ValueError(f"{subject} must be an integer")
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{subject} must be an integer")
    return raw


def _parse_command_help_string_list(
    raw: object,
    *,
    field_name: str,
    command_name: str,
) -> tuple[str, ...]:
    """Validate ordered help examples/notes as duplicate-free strings."""

    if raw is None:
        return ()
    subject = f"{field_name} for {command_name}"
    if not isinstance(raw, list):
        raise ValueError(f"{subject} must be a list of strings")

    values: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"{subject} must contain only strings")
        value = item.strip()
        if not value:
            raise ValueError(f"{subject} must not contain blank entries")
        _reject_runtime_specific_help_labels(value, field_name=field_name, command_name=command_name)
        if value in seen:
            duplicates.append(value)
            continue
        seen.add(value)
        values.append(value)

    if duplicates:
        formatted = ", ".join(repr(value) for value in duplicates)
        raise ValueError(f"{subject} must not contain duplicate entries: {formatted}")
    return tuple(values)


def _parse_command_help_variant(raw: object, *, command_name: str, variant_index: int) -> CommandHelpVariant:
    """Validate one documented help variant for a command."""

    subject = f"help.variants[{variant_index}] for {command_name}"
    if not isinstance(raw, Mapping):
        raise ValueError(f"{subject} must be a mapping")
    unknown_keys = sorted(str(key) for key in raw if str(key) not in _COMMAND_HELP_VARIANT_KEYS)
    if unknown_keys:
        raise ValueError(f"{subject} has unknown keys: {', '.join(unknown_keys)}")

    command = _parse_command_help_string(
        raw.get("command"),
        field_name=f"help.variants[{variant_index}].command",
        command_name=command_name,
        required=True,
    )
    assert command is not None
    parsed_variant = parse_command_label(command)
    if parsed_variant.canonical_command != command_name:
        raise ValueError(
            f"help.variants[{variant_index}].command for {command_name} must normalize to {command_name}; "
            f"got {parsed_variant.canonical_command}"
        )

    description = _parse_command_help_string(
        raw.get("description"),
        field_name=f"help.variants[{variant_index}].description",
        command_name=command_name,
        required=True,
    )
    assert description is not None
    return CommandHelpVariant(
        command=command,
        description=description,
        examples=_parse_command_help_string_list(
            raw.get("examples"),
            field_name=f"help.variants[{variant_index}].examples",
            command_name=command_name,
        ),
        notes=_parse_command_help_string_list(
            raw.get("notes"),
            field_name=f"help.variants[{variant_index}].notes",
            command_name=command_name,
        ),
    )


def _parse_command_help_variants(raw: object, *, command_name: str) -> tuple[CommandHelpVariant, ...]:
    """Validate documented help variants."""

    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"help.variants for {command_name} must be a list of mappings")

    variants: list[CommandHelpVariant] = []
    seen_commands: set[str] = set()
    duplicate_commands: list[str] = []
    for index, item in enumerate(raw):
        variant = _parse_command_help_variant(item, command_name=command_name, variant_index=index)
        if variant.command in seen_commands:
            duplicate_commands.append(variant.command)
            continue
        seen_commands.add(variant.command)
        variants.append(variant)

    if duplicate_commands:
        formatted = ", ".join(repr(command) for command in duplicate_commands)
        raise ValueError(f"help.variants for {command_name} must not contain duplicate commands: {formatted}")
    return tuple(variants)


def _parse_command_help_metadata(meta: Mapping[object, object], *, command_name: str) -> CommandHelpMetadata | None:
    """Parse strict display-only help metadata from command frontmatter."""

    if "help" not in meta:
        return None

    raw = meta.get("help")
    if not isinstance(raw, Mapping):
        raise ValueError(f"help for {command_name} must be a mapping")

    unknown_keys = sorted(str(key) for key in raw if str(key) not in _COMMAND_HELP_KEYS)
    if unknown_keys:
        raise ValueError(f"help for {command_name} has unknown keys: {', '.join(unknown_keys)}")

    group = _parse_command_help_string(
        raw.get("group"),
        field_name="help.group",
        command_name=command_name,
        required=True,
    )
    assert group is not None
    order = _parse_command_help_int(
        raw.get("order"),
        field_name="help.order",
        command_name=command_name,
        required=True,
    )
    assert order is not None

    return CommandHelpMetadata(
        group=group,
        order=order,
        compact_description=_parse_command_help_string(
            raw.get("compact_description"),
            field_name="help.compact_description",
            command_name=command_name,
        ),
        display_signature=_parse_command_help_string(
            raw.get("display_signature"),
            field_name="help.display_signature",
            command_name=command_name,
        ),
        detail_signature=_parse_command_help_string(
            raw.get("detail_signature"),
            field_name="help.detail_signature",
            command_name=command_name,
        ),
        examples=_parse_command_help_string_list(
            raw.get("examples"),
            field_name="help.examples",
            command_name=command_name,
        ),
        notes=_parse_command_help_string_list(
            raw.get("notes"),
            field_name="help.notes",
            command_name=command_name,
        ),
        root_detail_order=_parse_command_help_int(
            raw.get("root_detail_order"),
            field_name="help.root_detail_order",
            command_name=command_name,
        ),
        variants=_parse_command_help_variants(raw.get("variants"), command_name=command_name),
    )


__all__ = [
    "_COMMAND_HELP_KEYS",
    "_COMMAND_HELP_VARIANT_KEYS",
    "_parse_command_help_metadata",
]
