"""Shared mechanics for runtime command projection.

Runtime adapters own their command containers, labels, policy text, and note
wording.  This module only centralizes repeated projection mechanics that are
runtime-agnostic.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from gpd.adapters.install_utils import (
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    _markdown_fence_language,
    _markdown_fence_marker,
    render_markdown_frontmatter,
    rewrite_gpd_cli_invocations_to_runtime_bridge,
    rewrite_gpd_shell_line_to_runtime_bridge,
    split_markdown_frontmatter,
)
from gpd.adapters.shell_fence_projection import (
    DEFAULT_DIRECT_COMMAND_PREFIXES,
    DEFAULT_TERMINAL_EXAMPLE_PREFIXES,
    ShellFenceProjection,
    classify_shell_fence_body,
)


def rewrite_projection_shell_bridge(content: str, bridge_command: str) -> str:
    """Rewrite fenced shell command-position ``gpd`` calls to ``bridge_command``."""
    return rewrite_gpd_cli_invocations_to_runtime_bridge(
        content,
        bridge_command,
        shell_fence_languages=DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    )


def classify_projection_shell_fence(
    body: str,
    *,
    direct_command_prefixes: Sequence[str] = DEFAULT_DIRECT_COMMAND_PREFIXES,
    terminal_example_prefixes: Sequence[str] = DEFAULT_TERMINAL_EXAMPLE_PREFIXES,
) -> ShellFenceProjection:
    """Classify a shell fence body for runtime-neutral projection decisions."""
    return classify_shell_fence_body(
        body,
        direct_command_prefixes=direct_command_prefixes,
        terminal_example_prefixes=terminal_example_prefixes,
    )


def render_projected_command_shell_fences(
    content: str,
    *,
    bridge_command: str,
    direct_command_prefixes: Sequence[str] | None = None,
) -> str:
    """Render command-projection shell fences before runtime-specific notes.

    Only direct GPD CLI shell blocks remain executable.  Terminal transcripts,
    control-flow snippets, variable captures, heredocs/stdin transports,
    pseudocode, and empty shell fences become text fences so non-native runtimes
    do not need prompt-local shell parsing to decide whether the block is safe
    to run.  Variable-capture blocks are still rewritten to the runtime bridge
    before downgrading, so text-rendered GPD CLI captures do not surface a bare
    local ``gpd`` executable.
    """
    direct_prefixes = (
        tuple(direct_command_prefixes) if direct_command_prefixes is not None else ("gpd ", f"{bridge_command} ")
    )

    rendered: list[str] = []
    active_marker: str | None = None
    opening_line = ""
    opening_is_shell = False
    body_lines: list[str] = []

    for line in content.splitlines(keepends=True):
        stripped = line.lstrip()
        fence_marker = _markdown_fence_marker(stripped)
        if active_marker is None:
            if fence_marker is None:
                rendered.append(line)
                continue

            active_marker = fence_marker
            opening_line = line
            opening_is_shell = (
                _markdown_fence_language(stripped, fence_marker) in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES
            )
            body_lines = []
            continue

        if fence_marker == active_marker:
            body = "".join(body_lines)
            if opening_is_shell:
                classification = classify_projection_shell_fence(
                    body,
                    direct_command_prefixes=direct_prefixes,
                )
                if classification.kind == "direct_command" or _is_direct_template_command(
                    classification,
                    direct_prefixes,
                ):
                    rendered.append(opening_line)
                else:
                    rendered.append(_replace_markdown_fence_language(opening_line, active_marker, "text"))
                    if _contains_command_substitution(classification):
                        body = _rewrite_shell_body_lines(body, bridge_command)
            else:
                rendered.append(opening_line)
            rendered.append(body)
            rendered.append(line)
            active_marker = None
            opening_line = ""
            opening_is_shell = False
            body_lines = []
            continue

        body_lines.append(line)

    if active_marker is not None:
        rendered.append(opening_line)
        rendered.extend(body_lines)

    return rewrite_projection_shell_bridge("".join(rendered), bridge_command)


def _is_direct_template_command(
    classification: ShellFenceProjection,
    direct_prefixes: Sequence[str],
) -> bool:
    """Return whether a one-line direct command only carries a runtime argument token."""
    command = classification.first_command
    return (
        classification.kind == "pseudocode"
        and classification.reasons == ("template-placeholder",)
        and command is not None
        and _starts_with_projection_prefix(command, direct_prefixes)
    )


def _starts_with_projection_prefix(command: str, prefixes: Sequence[str]) -> bool:
    return any(command.startswith(prefix) for prefix in prefixes)


def _contains_command_substitution(classification: ShellFenceProjection) -> bool:
    return "command-substitution" in classification.reasons


def _rewrite_shell_body_lines(body: str, bridge_command: str) -> str:
    return "".join(rewrite_gpd_shell_line_to_runtime_bridge(line, bridge_command) for line in body.splitlines(True))


def _replace_markdown_fence_language(line: str, marker: str, language: str) -> str:
    """Return ``line`` with its opening fence language replaced."""
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    eol = "\n" if line.endswith("\n") else ""
    return f"{indent}{marker}{language}{eol}"


def strip_projection_note_blocks(content: str, strip_patterns: Sequence[re.Pattern[str]]) -> str:
    """Remove previously injected runtime note blocks using adapter-owned patterns."""
    stripped = content
    for pattern in strip_patterns:
        stripped = pattern.sub("", stripped)
    return stripped


def prepend_projection_note(
    content: str,
    note: str,
    *,
    strip_patterns: Sequence[re.Pattern[str]],
) -> str:
    """Prepend ``note`` after markdown frontmatter while replacing older notes.

    The supplied note and strip patterns stay adapter-owned so runtime-specific
    labels, shell policy, and wording do not leak into shared code.  ``note``
    should include any desired trailing blank line.
    """
    preamble, frontmatter, separator, body = split_markdown_frontmatter(content)
    if not frontmatter:
        return note + strip_projection_note_blocks(content, strip_patterns)

    body = strip_projection_note_blocks(body, strip_patterns)
    return render_markdown_frontmatter(preamble, frontmatter, separator, note + body)
