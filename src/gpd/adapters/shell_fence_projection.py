"""Runtime-neutral shell fence classification for projection adapters."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

ShellFenceProjectionKind = Literal[
    "direct_command",
    "variable_capture",
    "control_flow",
    "heredoc_or_stdin_contract_write",
    "terminal_example",
    "pseudocode",
    "non_runnable",
]


@dataclass(frozen=True, slots=True)
class ShellFenceProjection:
    """Runtime-neutral classification for one fenced shell body."""

    kind: ShellFenceProjectionKind
    first_command: str | None
    reasons: tuple[str, ...]


DEFAULT_DIRECT_COMMAND_PREFIXES: tuple[str, ...] = ("gpd ",)
DEFAULT_TERMINAL_EXAMPLE_PREFIXES: tuple[str, ...] = (
    "./",
    "awk ",
    "cat ",
    "cd ",
    "cp ",
    "curl ",
    "echo ",
    "find ",
    "git ",
    "grep ",
    "jq ",
    "ls ",
    "mkdir ",
    "python ",
    "python3 ",
    "rg ",
    "rm ",
    "sed ",
    "tar ",
    "uv ",
    "wc ",
    "zip ",
)

_ASSIGNMENT_RE = re.compile(r"^(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*=")
_BACKTICK_COMMAND_SUBSTITUTION_RE = re.compile(r"`[^`]+`")
_BRACE_PLACEHOLDER_RE = re.compile(r"(?<![$\\])\{[A-Za-z][A-Za-z0-9_.:/ -]*\}")
_ANGLE_PLACEHOLDER_RE = re.compile(r"<[A-Za-z][A-Za-z0-9_.:/ -]*>")
_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\$(?:ARGUMENTS|\{[^}\n]+\})")
_TERMINAL_PROMPT_RE = re.compile(r"^(?:[$%>]|[A-Za-z0-9_.-]+[$%#])\s+\S+")

_CONTROL_PREFIXES: tuple[str, ...] = (
    "case ",
    "elif ",
    "else ",
    "for ",
    "function ",
    "if ",
    "select ",
    "until ",
    "while ",
)
_CONTROL_KEYWORDS: frozenset[str] = frozenset({"do", "done", "else", "esac", "fi", "then"})
_CONTROL_OPERATORS: tuple[str, ...] = (" && ", " || ", " | ", "; ")
_STDIN_CONTRACT_FRAGMENTS: tuple[str, ...] = (
    "PROJECT_CONTRACT_JSON",
    "printf '%s\\n'",
    'printf "%s\\n"',
)


def shell_fence_runnable_lines(body: str) -> tuple[str, ...]:
    """Return non-empty, non-comment lines from a shell fence body."""
    return tuple(stripped for line in body.splitlines() if (stripped := line.strip()) and not stripped.startswith("#"))


def classify_shell_fence_body(
    body: str,
    *,
    direct_command_prefixes: Sequence[str] = DEFAULT_DIRECT_COMMAND_PREFIXES,
    terminal_example_prefixes: Sequence[str] = DEFAULT_TERMINAL_EXAMPLE_PREFIXES,
) -> ShellFenceProjection:
    """Classify a fenced shell body without applying runtime-specific policy.

    The classifier intentionally uses conservative structural checks rather
    than a full shell grammar.  Adapters can pass their own direct-command
    prefixes, but adapter policy decisions and allowlists stay outside this
    module.
    """

    lines = shell_fence_runnable_lines(body)
    if not lines:
        return ShellFenceProjection("non_runnable", None, ("empty-shell-fence",))

    first = lines[0]
    reasons = _classification_reasons(body, lines)

    if any(reason in reasons for reason in ("heredoc", "stdin-contract-write", "contract-json-transport")):
        return ShellFenceProjection("heredoc_or_stdin_contract_write", first, reasons)
    if any(reason in reasons for reason in ("leading-assignment", "command-substitution")):
        return ShellFenceProjection("variable_capture", first, reasons)
    if any(reason in reasons for reason in ("shell-control-prefix", "shell-control-operator")):
        return ShellFenceProjection("control_flow", first, reasons)
    if any(
        reason in reasons
        for reason in ("angle-placeholder", "brace-placeholder", "template-placeholder", "ellipsis-placeholder")
    ):
        return ShellFenceProjection("pseudocode", first, reasons)
    if _starts_with_known_prefix(first, direct_command_prefixes):
        return ShellFenceProjection("direct_command", first, ("direct-command-prefix",))
    if _looks_like_terminal_example(first, terminal_example_prefixes):
        return ShellFenceProjection("terminal_example", first, ("terminal-example-prefix",))
    return ShellFenceProjection("pseudocode", first, ("unclassified-shell-shape",))


def _classification_reasons(body: str, lines: tuple[str, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    lowered_lines = tuple(line.lower() for line in lines)

    if "<<" in body:
        reasons.append("heredoc")
    if any(fragment in body for fragment in _STDIN_CONTRACT_FRAGMENTS):
        reasons.append("stdin-contract-write")
    if _uses_contract_stdin_transport(lines):
        reasons.append("contract-json-transport")
    if any(_ASSIGNMENT_RE.match(line) for line in lines):
        reasons.append("leading-assignment")
    if "$(" in body or _BACKTICK_COMMAND_SUBSTITUTION_RE.search(body):
        reasons.append("command-substitution")
    if any(_has_control_prefix(line) for line in lowered_lines):
        reasons.append("shell-control-prefix")
    if any(_has_control_operator(line) for line in lines):
        reasons.append("shell-control-operator")
    if _ANGLE_PLACEHOLDER_RE.search(body):
        reasons.append("angle-placeholder")
    if _BRACE_PLACEHOLDER_RE.search(body):
        reasons.append("brace-placeholder")
    if _TEMPLATE_PLACEHOLDER_RE.search(body):
        reasons.append("template-placeholder")
    if "..." in body:
        reasons.append("ellipsis-placeholder")

    return tuple(dict.fromkeys(reasons))


def _uses_contract_stdin_transport(lines: tuple[str, ...]) -> bool:
    for line in lines:
        if "|" not in line:
            continue
        if "gpd " not in line:
            continue
        if line.rstrip().endswith(" -") or " project-contract " in line:
            return True
    return False


def _has_control_operator(line: str) -> bool:
    return any(operator in line for operator in _CONTROL_OPERATORS)


def _has_control_prefix(lowered_line: str) -> bool:
    first_word = lowered_line.split(None, 1)[0].rstrip(";")
    return first_word in _CONTROL_KEYWORDS or lowered_line.startswith(_CONTROL_PREFIXES)


def _starts_with_known_prefix(command: str, prefixes: Sequence[str]) -> bool:
    return any(_starts_with_command_prefix(command, prefix) for prefix in prefixes)


def _starts_with_command_prefix(command: str, prefix: str) -> bool:
    stripped_prefix = prefix.rstrip()
    if prefix.endswith(" "):
        return command == stripped_prefix or command.startswith(prefix)
    return command.startswith(prefix)


def _looks_like_terminal_example(command: str, prefixes: Sequence[str]) -> bool:
    lowered = command.lower()
    return _TERMINAL_PROMPT_RE.match(command) is not None or _starts_with_known_prefix(lowered, prefixes)
