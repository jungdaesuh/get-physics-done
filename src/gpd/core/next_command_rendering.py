"""Visible rendering for already-classified next-command decisions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from gpd.core.command_run_hints import (
    KIND_RUNTIME_COMMAND_LABEL,
    NEXT_COMMAND_OWNER_DISPLAY_ONLY,
    NEXT_COMMAND_OWNER_LOCAL_FINALIZER,
    NEXT_COMMAND_OWNER_LOCAL_HELPER,
    NEXT_COMMAND_OWNER_LOCAL_READONLY,
    NEXT_COMMAND_OWNER_LOCAL_TRANSITION,
    NEXT_COMMAND_OWNER_RUNTIME,
    NextCommand,
)

NEXT_UP_HEADING = "## > Next Up"

_SHELL_CONTROL_TOKENS = ("\n", "\r", ";", "|", "&", "<", ">", "`", "$(")
_FORBIDDEN_VISIBLE_COMMAND_FRAGMENTS = (
    "gpd --raw init",
    "--raw init",
    "gpd --raw stage field-access",
    "--raw stage field-access",
    "gpd verify phase",
    "gpd:verify-phase",
)
_COMMAND_LIKE_PREFIXES = ("gpd ", "gpd:", "gpd-", "/gpd", "$gpd")
_LOCAL_HELPER_OWNERS = {NEXT_COMMAND_OWNER_LOCAL_READONLY, NEXT_COMMAND_OWNER_LOCAL_HELPER}


class NextCommandRenderingError(ValueError):
    """Raised when a classified next command cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class RenderedNextUpBlock:
    """Rendered shared Next Up markdown plus its runtime-only stage-stop projection."""

    markdown: str
    stage_stop_next_runtime_command: str | None
    stage_stop_also_available: tuple[str, ...] = ()


def stage_stop_next_runtime_command(next_command: NextCommand | None) -> str | None:
    """Return the stage-stop runtime command for a classified command, if any."""

    if next_command is None or next_command.owner != NEXT_COMMAND_OWNER_RUNTIME:
        return None
    return _runtime_command_label(next_command)


def render_next_up_block(
    *,
    primary: NextCommand,
    after_this_completes: NextCommand | None = None,
    secondary: Iterable[NextCommand] = (),
) -> RenderedNextUpBlock:
    """Render a shared ``## > Next Up`` block without reclassifying or executing commands."""

    lines = [NEXT_UP_HEADING]
    stage_stop_primary: str | None

    if primary.owner == NEXT_COMMAND_OWNER_RUNTIME:
        primary_label = _runtime_command_label(primary)
        lines.append(f"Primary: `{primary_label}`")
        stage_stop_primary = primary_label
    elif primary.owner == NEXT_COMMAND_OWNER_LOCAL_TRANSITION:
        primary_label = _local_command_label(primary)
        lines.append(f"Primary local transition: `{primary_label}`")
        if after_this_completes is None:
            raise NextCommandRenderingError(
                "local transition next-up blocks require an after_this_completes runtime route"
            )
        after_label = _runtime_command_label(after_this_completes)
        lines.append(f"**After this completes:** `{after_label}`")
        stage_stop_primary = after_label
    else:
        raise NextCommandRenderingError(f"unsupported primary next-command owner: {primary.owner}")

    also_available: list[str] = []
    for next_command in secondary:
        line = _secondary_line(next_command)
        if line is None:
            continue
        lines.append(line)
        secondary_runtime = stage_stop_next_runtime_command(next_command)
        if secondary_runtime is not None and secondary_runtime != stage_stop_primary:
            _append_unique(also_available, secondary_runtime)

    return RenderedNextUpBlock(
        markdown="\n".join(lines),
        stage_stop_next_runtime_command=stage_stop_primary,
        stage_stop_also_available=tuple(also_available),
    )


def _secondary_line(next_command: NextCommand) -> str | None:
    if next_command.owner == NEXT_COMMAND_OWNER_RUNTIME:
        return f"Secondary runtime: `{_runtime_command_label(next_command)}`"
    if next_command.owner in _LOCAL_HELPER_OWNERS:
        return f"Secondary local helper: `{_local_command_label(next_command)}`"
    if next_command.owner == NEXT_COMMAND_OWNER_LOCAL_FINALIZER:
        return f"Secondary local finalizer: `{_local_command_label(next_command)}`"
    if next_command.owner == NEXT_COMMAND_OWNER_LOCAL_TRANSITION:
        return f"Secondary local transition: `{_local_command_label(next_command)}`"
    if next_command.owner == NEXT_COMMAND_OWNER_DISPLAY_ONLY:
        explanation = _display_only_explanation(next_command)
        return f"Note: {explanation}" if explanation else None
    raise NextCommandRenderingError(f"unsupported secondary next-command owner: {next_command.owner}")


def _runtime_command_label(next_command: NextCommand) -> str:
    if next_command.owner != NEXT_COMMAND_OWNER_RUNTIME or next_command.kind != KIND_RUNTIME_COMMAND_LABEL:
        raise NextCommandRenderingError("stage-stop runtime commands must be classified runtime command labels")
    return _renderable_command_label(next_command)


def _local_command_label(next_command: NextCommand) -> str:
    return _renderable_command_label(next_command)


def _renderable_command_label(next_command: NextCommand) -> str:
    label = next_command.label.strip()
    if not label:
        raise NextCommandRenderingError("next command label is empty")
    if _contains_shell_control_tokens(label):
        raise NextCommandRenderingError(f"next command contains shell control tokens: {label}")
    lowered = label.lower()
    for fragment in _FORBIDDEN_VISIBLE_COMMAND_FRAGMENTS:
        if fragment in lowered:
            raise NextCommandRenderingError(f"forbidden command fragment in visible next-up block: {fragment}")
    if lowered.startswith("gpd-") and (
        next_command.owner != NEXT_COMMAND_OWNER_RUNTIME or next_command.kind != KIND_RUNTIME_COMMAND_LABEL
    ):
        raise NextCommandRenderingError("bare gpd- runtime labels require an active runtime classification")
    return label


def _display_only_explanation(next_command: NextCommand) -> str | None:
    for candidate in (next_command.reason, next_command.label):
        if not isinstance(candidate, str):
            continue
        text = candidate.strip()
        if text and _is_safe_display_only_text(text):
            return text
    return None


def _is_safe_display_only_text(text: str) -> bool:
    lowered = text.lower()
    if _contains_shell_control_tokens(text):
        return False
    if any(fragment in lowered for fragment in _FORBIDDEN_VISIBLE_COMMAND_FRAGMENTS):
        return False
    return not lowered.startswith(_COMMAND_LIKE_PREFIXES)


def _contains_shell_control_tokens(value: str) -> bool:
    return any(token in value for token in _SHELL_CONTROL_TOKENS)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


__all__ = [
    "NEXT_COMMAND_OWNER_LOCAL_HELPER",
    "NEXT_UP_HEADING",
    "NextCommandRenderingError",
    "RenderedNextUpBlock",
    "render_next_up_block",
    "stage_stop_next_runtime_command",
]
