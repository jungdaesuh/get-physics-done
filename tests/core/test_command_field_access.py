from __future__ import annotations

import json

import pytest

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.core.command_field_access import (
    COMMAND_CONTEXT_FIELD_DESCRIPTIONS,
    build_command_field_access,
)

REPRESENTATIVE_PROJECT_AWARE_COMMANDS = (
    "compare-experiment",
    "explain",
    "dimensional-analysis",
)

SHELL_LOCAL_TOKENS = (
    "gpd json get",
    "$(",
    "CONTEXT=",
    "bash",
    "zsh",
    "shell alias",
)

PROVIDER_TOKENS = tuple(descriptor.display_name for descriptor in iter_runtime_descriptors())


@pytest.mark.parametrize("command_name", REPRESENTATIVE_PROJECT_AWARE_COMMANDS)
def test_instruction_style_is_shell_free_and_provider_neutral(command_name: str) -> None:
    access = build_command_field_access(command_name)
    payload = access.to_payload()

    assert payload["command"] == f"gpd:{command_name}"
    assert payload["style"] == "instruction"
    assert payload["read_only"] is True
    assert payload["selected_fields"] == [name for name, _description in COMMAND_CONTEXT_FIELD_DESCRIPTIONS]
    assert "shell_bindings" not in payload

    instruction_text = "\n".join(payload["instructions"])
    for token in (*SHELL_LOCAL_TOKENS, *PROVIDER_TOKENS):
        assert token not in instruction_text
    assert "checks entries by their name field" in instruction_text
    assert "resolved_subject" in instruction_text


@pytest.mark.parametrize("command_name", REPRESENTATIVE_PROJECT_AWARE_COMMANDS)
def test_representative_commands_expose_subject_aware_metadata(command_name: str) -> None:
    payload = build_command_field_access(command_name, style="json").to_payload()

    assert payload["command_metadata"]["effective_context_mode"] == "project-aware"
    assert payload["command_metadata"]["context_mode"] == "project-aware"
    assert payload["command_metadata"]["explicit_input_labels"]
    assert "checks" in payload["nested_field_descriptions"]
    assert "resolved_subject" in payload["nested_field_descriptions"]
    assert "instructions" not in payload


def test_json_style_is_deterministic_and_testable() -> None:
    first = build_command_field_access("gpd:compare-experiment benchmark", style="json").to_payload()
    second = build_command_field_access("compare-experiment", style="json").to_payload()

    assert first["command"] == second["command"] == "gpd:compare-experiment"
    first_without_request = {key: value for key, value in first.items() if key != "requested_command"}
    second_without_request = {key: value for key, value in second.items() if key != "requested_command"}
    assert first_without_request == second_without_request
    assert json.dumps(second, sort_keys=True) == json.dumps(
        build_command_field_access("compare-experiment", style="json").to_payload(),
        sort_keys=True,
    )


def test_unknown_command_rejects_with_allowed_values() -> None:
    with pytest.raises(ValueError) as exc_info:
        build_command_field_access("not-a-real-command")

    message = str(exc_info.value)
    assert "Unknown GPD command: gpd:not-a-real-command" in message
    assert "Allowed commands include:" in message
    assert "gpd:compare-experiment" in message


def test_invalid_style_rejects_closed() -> None:
    with pytest.raises(ValueError, match="Unknown command field-access style"):
        build_command_field_access("explain", style="shell")
