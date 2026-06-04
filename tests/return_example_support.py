"""Shared helpers for tests that inspect visible ``gpd_return`` examples."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from gpd.core.return_contract import REQUIRED_RETURN_FIELDS, validate_gpd_return_markdown

FENCED_YAML_RE = re.compile(
    r"^```ya?ml[^\n]*\n(?P<body>.*?)(?:\n^```[ \t]*$)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class GpdReturnExample:
    """One fenced visible ``gpd_return`` example with source location."""

    source_name: str
    line_number: int
    body: str
    markdown: str


def extract_gpd_return_examples(
    path_or_text: Path | str,
    *,
    source_name: str | None = None,
    skip_child_gate_examples: bool = True,
) -> list[GpdReturnExample]:
    """Extract fenced YAML examples whose body contains ``gpd_return``."""

    if isinstance(path_or_text, Path):
        text = path_or_text.read_text(encoding="utf-8")
        name = source_name or path_or_text.as_posix()
    else:
        text = path_or_text
        name = source_name or "<text>"

    examples: list[GpdReturnExample] = []
    for match in FENCED_YAML_RE.finditer(text):
        body = match.group("body")
        if "gpd_return" not in body:
            continue
        if skip_child_gate_examples and ("child_gate:" in body or "child_gates:" in body):
            continue
        examples.append(
            GpdReturnExample(
                source_name=name,
                line_number=text.count("\n", 0, match.start()) + 1,
                body=body,
                markdown=f"```yaml\n{body.rstrip()}\n```",
            )
        )
    return examples


def validate_gpd_return_examples(
    examples: Iterable[GpdReturnExample],
    *,
    require_required_fields: bool = False,
) -> tuple[list[dict[str, object]], list[str]]:
    """Validate extracted examples and return parsed envelopes plus location errors."""

    envelopes: list[dict[str, object]] = []
    failures: list[str] = []
    for example in examples:
        result = validate_gpd_return_markdown(example.markdown)
        if not result.passed:
            failures.append(f"{example.source_name}:{example.line_number}: {'; '.join(result.errors)}")
            continue
        if require_required_fields:
            missing_fields = sorted(set(REQUIRED_RETURN_FIELDS) - set(result.fields))
            if missing_fields:
                failures.append(
                    f"{example.source_name}:{example.line_number}: missing required field(s): "
                    + ", ".join(missing_fields)
                )
                continue
        envelopes.append(result.fields)
    return envelopes, failures


def validated_gpd_return_examples(
    path_or_text: Path | str,
    *,
    source_name: str | None = None,
    require_required_fields: bool = True,
    skip_child_gate_examples: bool = True,
) -> list[dict[str, object]]:
    """Extract visible examples and return validated envelopes, failing with source locations."""

    examples = extract_gpd_return_examples(
        path_or_text,
        source_name=source_name,
        skip_child_gate_examples=skip_child_gate_examples,
    )
    envelopes, failures = validate_gpd_return_examples(examples, require_required_fields=require_required_fields)
    if failures:
        raise AssertionError("Invalid gpd_return YAML examples:\n" + "\n".join(failures))
    return envelopes


def find_gpd_return_example(
    path_or_text: Path | str,
    *,
    source_name: str | None = None,
    field: str | None = None,
    value: object | None = None,
    status: str | None = None,
    require_required_fields: bool = True,
) -> tuple[GpdReturnExample, dict[str, object]]:
    """Find one validated visible example matching a status or top-level field value."""

    examples = extract_gpd_return_examples(path_or_text, source_name=source_name)
    envelopes, failures = validate_gpd_return_examples(examples, require_required_fields=require_required_fields)
    if failures:
        raise AssertionError("Invalid gpd_return YAML examples:\n" + "\n".join(failures))

    matches: list[tuple[GpdReturnExample, dict[str, object]]] = []
    for example, envelope in zip(examples, envelopes, strict=True):
        if status is not None and envelope.get("status") != status:
            continue
        if field is not None:
            if field not in envelope:
                continue
            if value is not None and envelope[field] != value:
                continue
        matches.append((example, envelope))

    if len(matches) != 1:
        filters = []
        if status is not None:
            filters.append(f"status={status!r}")
        if field is not None:
            filters.append(f"field={field!r}")
        if value is not None:
            filters.append(f"value={value!r}")
        detail = ", ".join(filters) or "no filters"
        raise AssertionError(f"expected exactly one gpd_return example matching {detail}, found {len(matches)}")
    return matches[0]


def assert_fields_before(example_body: str, before_fields: Sequence[str], after_fields: Sequence[str]) -> None:
    """Assert that selected top-level envelope fields keep base-before-extension order."""

    positions: dict[str, int] = {}
    for field_name in (*before_fields, *after_fields):
        match = re.search(rf"(?m)^  {re.escape(field_name)}:", example_body)
        if match is None:
            raise AssertionError(f"missing gpd_return field {field_name!r}")
        positions[field_name] = match.start()

    for before_field in before_fields:
        for after_field in after_fields:
            if positions[before_field] >= positions[after_field]:
                raise AssertionError(f"expected {before_field!r} before {after_field!r}")
