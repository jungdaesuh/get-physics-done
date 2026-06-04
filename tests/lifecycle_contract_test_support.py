"""Shared test helpers for lifecycle prompt behavior contracts."""

from __future__ import annotations

import re

from gpd.core.child_handoff import ChildGateTuple, parse_child_gate_markdown
from tests.assertion_taxonomy_support import (
    MatchMode,
    assert_prompt_contracts,
    forbidden_duplicate,
    machine_exact,
    public_exact,
    semantic_anchor,
    semantic_concept,
)

_YAML_BLOCK_RE = re.compile(r"```ya?ml\n(?P<body>.*?)\n```", re.DOTALL)


def child_gate_from_text(text: str, gate_id: str) -> ChildGateTuple:
    """Return the parsed child gate tuple with ``gate_id`` from prompt text."""

    for match in _YAML_BLOCK_RE.finditer(text):
        body = match.group("body")
        if "child_gate:" not in body:
            continue
        gate = parse_child_gate_markdown(f"```yaml\n{body}\n```")
        if gate.id == gate_id:
            return gate
    raise AssertionError(f"missing child_gate {gate_id}")


def artifact_paths(gate: ChildGateTuple) -> tuple[str, ...]:
    return tuple(artifact.path for artifact in gate.expected_artifacts)


def assert_semantic_contract(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(
        text,
        semantic_anchor(label, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label),
    )


def assert_machine_contract(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(text, machine_exact(label, fragments, context=label))


def assert_public_contract(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(text, public_exact(label, fragments, context=label))


def assert_forbidden_contract(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(
        text,
        *(
            forbidden_duplicate(f"{label} forbidden fragment {index}", fragment, max_count=0, context=label)
            for index, fragment in enumerate(fragments, start=1)
        ),
    )


def assert_forbidden_lifecycle_prose(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(
        text,
        *semantic_concept(label, forbidden=fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label),
    )
