"""Runtime-neutral shell fence projection classification tests."""

from __future__ import annotations

import inspect

import pytest

from gpd.adapters import shell_fence_projection
from gpd.adapters.command_projection import classify_projection_shell_fence
from gpd.adapters.shell_fence_projection import (
    ShellFenceProjection,
    classify_shell_fence_body,
    shell_fence_runnable_lines,
)


@pytest.mark.parametrize(
    ("body", "expected"),
    (
        ("gpd status\n", ShellFenceProjection("direct_command", "gpd status", ("direct-command-prefix",))),
        ("gpd --raw validate project-contract GPD/contract.json 2>&1\n", "direct_command"),
        ("gpd --raw validate project-contract GPD/.approved-project-contract.json --mode approved\n", "direct_command"),
        ("RESULT=$(gpd status 2>&1)\necho \"$RESULT\"\n", "variable_capture"),
        ("gpd status || true\n", "control_flow"),
        ("gpd status; gpd validate project-contract GPD/contract.json\n", "control_flow"),
        ("if [ -d GPD ]; then\n  gpd status\nfi\n", "control_flow"),
        ("cat > GPD/config.json <<'JSON'\n{}\nJSON\n", "heredoc_or_stdin_contract_write"),
        (
            "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd --raw validate project-contract --mode approved -\n",
            "heredoc_or_stdin_contract_write",
        ),
        ("git status --porcelain\n", "terminal_example"),
        ("$ uv run pytest tests/ -q\n", "terminal_example"),
        ("git show {branch}:GPD/STATE.md\n", "pseudocode"),
        ("gpd set-profile <profile>\n", "pseudocode"),
        ("\n# comment only\n", ShellFenceProjection("non_runnable", None, ("empty-shell-fence",))),
    ),
)
def test_classifies_shell_fence_projection_kinds(body: str, expected: str | ShellFenceProjection) -> None:
    classification = classify_shell_fence_body(body)

    if isinstance(expected, ShellFenceProjection):
        assert classification == expected
    else:
        assert classification.kind == expected


def test_variable_capture_takes_precedence_over_status_control_flow() -> None:
    classification = classify_shell_fence_body(
        "CHECK=$(gpd --raw validate project-contract GPD/contract.json 2>&1)\n"
        "if [ $? -ne 0 ]; then\n"
        "  echo \"$CHECK\"\n"
        "  exit 1\n"
        "fi\n"
    )

    assert classification.kind == "variable_capture"
    assert classification.first_command == "CHECK=$(gpd --raw validate project-contract GPD/contract.json 2>&1)"
    assert classification.reasons == (
        "leading-assignment",
        "command-substitution",
        "shell-control-prefix",
        "shell-control-operator",
    )


def test_heredoc_classification_takes_precedence_over_capture_and_control_flow() -> None:
    classification = classify_shell_fence_body(
        "PAYLOAD=$(cat <<'JSON'\n"
        "{\"schema\": true}\n"
        "JSON\n"
        ")\n"
        "if [ -n \"$PAYLOAD\" ]; then\n"
        "  gpd --raw validate project-contract -\n"
        "fi\n"
    )

    assert classification.kind == "heredoc_or_stdin_contract_write"
    assert classification.reasons[:3] == ("heredoc", "leading-assignment", "command-substitution")
    assert "shell-control-prefix" in classification.reasons


def test_control_keywords_do_not_match_ordinary_command_prefixes() -> None:
    docker = classify_shell_fence_body("docker compose ps\n", terminal_example_prefixes=("docker ",))
    loop_keyword = classify_shell_fence_body("do\n  gpd status\ndone\n")

    assert docker.kind == "terminal_example"
    assert "shell-control-prefix" not in docker.reasons
    assert loop_keyword.kind == "control_flow"


def test_direct_command_prefixes_are_configurable_without_runtime_policy() -> None:
    classification = classify_shell_fence_body(
        "/tmp/runtime-gpd status\n",
        direct_command_prefixes=("/tmp/runtime-gpd ",),
    )

    assert classification == ShellFenceProjection(
        "direct_command",
        "/tmp/runtime-gpd status",
        ("direct-command-prefix",),
    )


def test_command_projection_wrapper_delegates_to_shared_classifier() -> None:
    direct = classify_projection_shell_fence("gpd status\n")
    terminal = classify_projection_shell_fence("git status\n")

    assert direct.kind == "direct_command"
    assert terminal.kind == "terminal_example"


def test_runnable_line_extraction_ignores_blank_lines_and_comments() -> None:
    assert shell_fence_runnable_lines("\n# comment\ngpd status\n  # also comment\n git status\n") == (
        "gpd status",
        "git status",
    )


def test_classifier_is_deterministic() -> None:
    body = "RESULT=$(gpd status)\necho \"$RESULT\"\n"

    assert classify_shell_fence_body(body) == classify_shell_fence_body(body)


def test_shared_classifier_does_not_embed_gemini_policy() -> None:
    source = inspect.getsource(shell_fence_projection).lower()

    assert "gemini" not in source
