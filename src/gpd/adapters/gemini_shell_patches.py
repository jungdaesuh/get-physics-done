"""Gemini-owned structural shell workflow rewrites."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

GEMINI_APPROVED_CONTRACT_PATH = "GPD/.approved-project-contract.json"

GeminiShellWorkflowClass = Literal[
    "direct-gpd-command",
    "gpd-capture-status-block",
    "gpd-capture-echo-block",
    "gpd-precheck-commit-sequence",
    "gpd-contract-file-transport",
    "gpd-health-tempfile-wrapper",
    "profile-argument-validation-guidance",
    "set-profile-persistence-guidance",
    "unsafe-or-pseudocode",
    "unchanged",
]


@dataclass(frozen=True, slots=True)
class GeminiShellWorkflowRewrite:
    """Classification and replacement for one Gemini-visible shell workflow."""

    kind: GeminiShellWorkflowClass
    replacement: str | None = None
    reason: str = ""


_SHELL_FENCE_LANGUAGES = frozenset({"bash", "sh", "shell", "zsh"})
_GEMINI_CONTRACT_PERSIST_SENTENCE = (
    "Write the exact approved contract JSON to "
    f"`{GEMINI_APPROVED_CONTRACT_PATH}` using file tools, then persist it into `GPD/state.json`:"
)
_GEMINI_CONTRACT_FILE_NOTE = (
    "Do not write `/tmp` intermediates for the approved contract. In Gemini headless auto-edit mode, keep the "
    f"exact approved JSON in `{GEMINI_APPROVED_CONTRACT_PATH}`, then validate and persist from that file using "
    "direct `gpd` commands. Do not stash the approved contract in shell variables, command substitutions, or "
    "heredocs."
)
_GEMINI_SET_PROFILE_VALIDATE_REPLACEMENT = (
    "Validate the single profile argument without a shell call before running persistence commands. Trim "
    "surrounding whitespace. Accept exactly one of: `deep-theory`, `numerical`, `exploratory`, `review`, "
    "`paper-writing`. If the argument is missing, contains whitespace, or is not in that list, stop and surface "
    "the validation error."
)
_GEMINI_SET_PROFILE_REPLACEMENT = (
    "Run these as separate shell calls in Gemini auto-edit mode. Do not combine them into one multi-line shell "
    "block.\n\n"
    "```bash\n"
    "gpd config ensure-section\n"
    "```\n\n"
    "Then run:\n\n"
    "```bash\n"
    'gpd config set model_profile "$PROFILE"\n'
    "```\n\n"
    "These commands may only repair `GPD/config.json` and update `GPD/config.json::model_profile`; do not run "
    "project init, progress, state sync, or project reentry from `set-profile`."
)
_GEMINI_HEALTH_BLOCK_REPLACEMENT = (
    "In Gemini auto-edit mode, run health checks as direct shell calls instead of capturing stderr through temp "
    "files.\n\n"
    "Default read-only check:\n\n"
    "```bash\n"
    "gpd --raw health\n"
    "```\n\n"
    "Only after explicit confirmation for `--fix`:\n\n"
    "```bash\n"
    "gpd --raw health --fix\n"
    "```\n\n"
    "Do not treat a nonzero health exit status as a wrapper failure when the command output parses as the valid "
    "report JSON below."
)

_GEMINI_CAPTURE_ASSIGNMENT_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<var>[A-Z][A-Z0-9_]*)=\$\((?P<command>gpd[^\n]*)\)(?P<suffix>[ \t]*(?:\|\|\s*true)?)$",
    re.MULTILINE,
)
_GEMINI_CAPTURED_GPD_STATUS_BLOCK_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<var>[A-Z][A-Z0-9_]*)=\$\((?P<command>gpd[^\n]*)\)(?P<suffix>[ \t]*(?:\|\|\s*true)?)\n"
    r"(?P=indent)if \[ \$\? -ne 0 \]; then\n"
    r"(?:(?P=indent)[ \t]+.*\n)+?"
    r"(?P=indent)fi[ \t]*$",
    re.MULTILINE,
)
_GEMINI_CAPTURED_GPD_ECHO_BLOCK_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<var>[A-Z][A-Z0-9_]*)=\$\((?P<command>gpd[^\n]*)\)(?P<suffix>[ \t]*(?:\|\|\s*true)?)\n"
    r'(?P=indent)echo "\$(?P=var)"[ \t]*$',
    re.MULTILINE,
)
_GEMINI_PRECHECK_CAPTURE_ECHO_RE = re.compile(
    r'(?m)^(?P<indent>[ \t]*)PRE_CHECK=\$\((?P<command>gpd(?: --cwd "[^"]+")? pre-commit-check --files [^\n]+?) 2>&1\) \|\| true\n'
    r'(?P=indent)echo "\$PRE_CHECK"[ \t]*$'
)
_GEMINI_CONTRACT_VALIDATE_STDIN_RE = re.compile(
    r"printf '%s\\n' \"\$PROJECT_CONTRACT_JSON\" \| gpd --raw validate project-contract -(?P<suffix>[^\n]*)"
)
_GEMINI_CONTRACT_PERSIST_STDIN_RE = re.compile(
    r"printf '%s\\n' \"\$PROJECT_CONTRACT_JSON\" \| gpd state set-project-contract -(?P<suffix>[^\n]*)"
)


def _markdown_fence_marker(stripped_line: str) -> str | None:
    """Return a Markdown fence marker from *stripped_line*, if present."""
    if stripped_line.startswith("```"):
        char = "`"
    elif stripped_line.startswith("~~~"):
        char = "~"
    else:
        return None
    marker_length = 0
    for marker_char in stripped_line:
        if marker_char != char:
            break
        marker_length += 1
    return stripped_line[:marker_length] if marker_length >= 3 else None


def _markdown_fence_language(stripped_line: str, marker: str) -> str:
    """Return the normalized first Markdown fence info token."""
    info = stripped_line[len(marker) :].strip().split(None, 1)
    return info[0].lower() if info else ""


def _is_shell_fence(opening_line: str, marker: str) -> bool:
    return _markdown_fence_language(opening_line.lstrip(), marker) in _SHELL_FENCE_LANGUAGES


def _fenced(language: str, body: str) -> str:
    body = body.strip("\n")
    return f"```{language}\n{body}\n```"


def _gemini_direct_command_comment(command: str) -> str:
    """Return a concise Gemini note for transformed shell-capture examples."""
    if command.startswith("gpd --raw init"):
        return "# Gemini: run initialization directly."
    return "# Gemini: run this command directly."


def _strip_control_suffix(command: str, suffix: str) -> tuple[str, str | None]:
    """Return a runnable direct command plus prose for unsupported shell control suffixes."""
    suffix = suffix.strip()
    if suffix == "|| true":
        return command, "# If this exits non-zero, surface the output and continue only when the workflow says to."
    return command, None


def _rewrite_capture_block_body(match: re.Match[str]) -> str:
    indent = match.group("indent")
    command = match.group("command").strip()
    suffix = (match.group("suffix") or "").strip()
    command, suffix_note = _strip_control_suffix(command, suffix)
    lines = [f"{indent}{_gemini_direct_command_comment(command)}", f"{indent}{command}"]
    if suffix_note:
        lines.append(f"{indent}{suffix_note}")
    return "\n".join(lines)


def _rewrite_capture_assignment_body(body: str) -> str:
    body = _GEMINI_CAPTURED_GPD_STATUS_BLOCK_RE.sub(_rewrite_capture_block_body, body)
    body = _GEMINI_CAPTURED_GPD_ECHO_BLOCK_RE.sub(_rewrite_capture_block_body, body)

    def _replace_safe_assignment(match: re.Match[str]) -> str:
        variable = match.group("var")
        reference_re = re.compile(rf"\$(?:\{{{re.escape(variable)}\}}|{re.escape(variable)})(?![A-Z0-9_])")
        remaining_body = body[: match.start()] + body[match.end() :]
        if reference_re.search(remaining_body):
            return match.group(0)
        return _rewrite_capture_block_body(match)

    return _GEMINI_CAPTURE_ASSIGNMENT_RE.sub(_replace_safe_assignment, body)


def _rewrite_precheck_capture_echo_body(body: str) -> tuple[str, bool]:
    def _replace(match: re.Match[str]) -> str:
        indent = match.group("indent")
        command = match.group("command").strip()
        return "\n".join(
            (
                f"{indent}# Gemini: run the pre-check directly; inspect output before committing.",
                f"{indent}{command}",
                f"{indent}# If the pre-check exits non-zero, surface the output and continue only if commit remains appropriate.",
            )
        )

    rewritten = _GEMINI_PRECHECK_CAPTURE_ECHO_RE.sub(_replace, body)
    return rewritten, rewritten != body


def _rewrite_contract_stdin_body(body: str) -> tuple[str, bool]:
    rewritten = _GEMINI_CONTRACT_VALIDATE_STDIN_RE.sub(
        rf"gpd --raw validate project-contract {GEMINI_APPROVED_CONTRACT_PATH}\g<suffix>",
        body,
    )
    rewritten = _GEMINI_CONTRACT_PERSIST_STDIN_RE.sub(
        rf"gpd state set-project-contract {GEMINI_APPROVED_CONTRACT_PATH}\g<suffix>",
        rewritten,
    )
    return rewritten, rewritten != body


def _is_set_profile_validation_body(body: str) -> bool:
    stripped = body.strip()
    return (
        stripped.startswith('PROFILE="$(printf')
        and 'case "$PROFILE" in' in stripped
        and "deep-theory|numerical|exploratory|review|paper-writing" in stripped
    )


def _is_set_profile_persistence_body(body: str) -> bool:
    stripped = body.strip()
    return (
        "gpd config ensure-section" in stripped
        and "INIT=$(gpd --raw init progress --include state,config" in stripped
        and "model_profile" not in stripped
    )


def _is_legacy_set_profile_persistence_body(body: str) -> bool:
    stripped = body.strip()
    return (
        stripped.startswith("gpd config ensure-section\n")
        and "INIT=$(gpd --raw init progress --include state,config)\n" in stripped
        and "--no-project-reentry" not in stripped
    )


def _is_health_tempfile_body(body: str) -> bool:
    stripped = body.strip()
    return (
        "HEALTH_ERR=$(mktemp)" in stripped
        and "gpd --raw health" in stripped
        and "HEALTH_STDERR=$(cat" in stripped
    )


def _body_has_precheck_commit_sequence(body: str) -> bool:
    return "PRE_CHECK=$(gpd" in body and "pre-commit-check --files" in body and "\ngpd commit" in body


def classify_gemini_shell_workflow_block(
    body: str,
    *,
    command_name: str | None = None,
) -> GeminiShellWorkflowRewrite:
    """Classify a Gemini-visible shell block and return any structural replacement."""
    if command_name == "set-profile" and _is_set_profile_validation_body(body):
        return GeminiShellWorkflowRewrite(
            "profile-argument-validation-guidance",
            _GEMINI_SET_PROFILE_VALIDATE_REPLACEMENT,
            "set-profile validates model arguments outside shell policy",
        )
    # Semantic exception: older set-profile prompt surfaces used this init block
    # before model_profile persistence. Structural capture rewriting cannot infer
    # the replacement command (`gpd config set model_profile "$PROFILE"`).
    if _is_set_profile_persistence_body(body) and (
        command_name == "set-profile" or _is_legacy_set_profile_persistence_body(body)
    ):
        return GeminiShellWorkflowRewrite(
            "set-profile-persistence-guidance",
            _GEMINI_SET_PROFILE_REPLACEMENT,
            "set-profile must not run project init as part of profile persistence",
        )
    if _is_health_tempfile_body(body):
        return GeminiShellWorkflowRewrite(
            "gpd-health-tempfile-wrapper",
            _GEMINI_HEALTH_BLOCK_REPLACEMENT,
            "Gemini shell policy cannot approve tempfile stderr wrappers",
        )

    rewritten, contract_changed = _rewrite_contract_stdin_body(body)
    if contract_changed:
        return GeminiShellWorkflowRewrite(
            "gpd-contract-file-transport",
            _fenced("bash", rewritten),
            "Gemini persists approved contracts through a project file, not stdin pipes",
        )

    rewritten, precheck_changed = _rewrite_precheck_capture_echo_body(body)
    rewritten_capture = _rewrite_capture_assignment_body(rewritten)
    if rewritten_capture != body:
        if precheck_changed and _body_has_precheck_commit_sequence(body):
            return GeminiShellWorkflowRewrite(
                "gpd-precheck-commit-sequence",
                _fenced("bash", rewritten_capture),
                "pre-check capture is structural visibility before an explicit commit",
            )
        kind: GeminiShellWorkflowClass = "gpd-capture-echo-block" if "echo \"$" in body else "gpd-capture-status-block"
        return GeminiShellWorkflowRewrite(
            kind,
            _fenced("bash", rewritten_capture),
            "captured GPD shell output is rewritten to a direct Gemini-approved command",
        )

    return GeminiShellWorkflowRewrite("unchanged")


def _rewrite_contract_prose(content: str) -> str:
    content = content.replace(
        "Persist the approved contract into `GPD/state.json` from the same stdin payload:",
        _GEMINI_CONTRACT_PERSIST_SENTENCE,
    )
    content = content.replace(
        "After validation passes, persist the approved contract into `GPD/state.json` from the same stdin payload:",
        _GEMINI_CONTRACT_PERSIST_SENTENCE,
    )
    return content.replace(
        "Do not write `/tmp` intermediates for the approved contract. Prefer piping the exact approved JSON "
        "directly to `gpd ... -`. Only write a file if the user explicitly wants a durable saved copy, and if so "
        "place it under the project, not an OS temp directory.",
        _GEMINI_CONTRACT_FILE_NOTE,
    )


def rewrite_gemini_shell_workflow_guidance(content: str, *, command_name: str | None = None) -> str:
    """Rewrite known shell-heavy workflow snippets into Gemini-safe structural forms."""
    content = _rewrite_contract_prose(content)
    rendered: list[str] = []
    active_marker: str | None = None
    opening_line = ""
    body_lines: list[str] = []
    opening_is_shell = False

    for line in content.splitlines(keepends=True):
        stripped = line.lstrip()
        fence_marker = _markdown_fence_marker(stripped)
        if active_marker is None:
            if fence_marker is None:
                rendered.append(line)
                continue

            active_marker = fence_marker
            opening_line = line
            body_lines = []
            opening_is_shell = _is_shell_fence(stripped, fence_marker)
            continue

        if fence_marker == active_marker:
            body = "".join(body_lines)
            if not opening_is_shell:
                rendered.append(opening_line)
                rendered.append(body)
                rendered.append(line)
            else:
                rewrite = classify_gemini_shell_workflow_block(body, command_name=command_name)
                if rewrite.replacement is None:
                    rendered.append(opening_line)
                    rendered.append(body)
                    rendered.append(line)
                else:
                    rendered.append(rewrite.replacement.rstrip("\n"))
                    rendered.append("\n")
            active_marker = None
            opening_line = ""
            body_lines = []
            opening_is_shell = False
            continue

        body_lines.append(line)

    if active_marker is not None:
        rendered.append(opening_line)
        rendered.extend(body_lines)

    return "".join(rendered)


def apply_gemini_shell_workflow_patches(content: str) -> str:
    """Compatibility wrapper for older callers; structural rewrites replaced the patch ledger."""
    return rewrite_gemini_shell_workflow_guidance(content)


__all__ = [
    "GEMINI_APPROVED_CONTRACT_PATH",
    "GeminiShellWorkflowRewrite",
    "classify_gemini_shell_workflow_block",
    "rewrite_gemini_shell_workflow_guidance",
    "apply_gemini_shell_workflow_patches",
]
