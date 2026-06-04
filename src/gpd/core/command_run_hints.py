"""Read-only run-hint metadata for already-produced command strings."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from gpd.command_labels import parse_command_label, runtime_public_command_prefixes
from gpd.core.public_surface_contract import local_cli_bridge_commands

COMMAND_RUN_HINT_SCHEMA_VERSION = 1
COMMAND_RUN_HINT_EXECUTION = "not_executed"
NEXT_COMMAND_SURFACE_CONTEXT_SHARED_NEXT_UP = "shared_next_up"
NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME = "active_runtime"

NEXT_COMMAND_OWNER_RUNTIME = "runtime"
NEXT_COMMAND_OWNER_LOCAL_READONLY = "local_readonly"
NEXT_COMMAND_OWNER_LOCAL_HELPER = "local_helper"
NEXT_COMMAND_OWNER_LOCAL_FINALIZER = "local_finalizer"
NEXT_COMMAND_OWNER_LOCAL_TRANSITION = "local_transition"
NEXT_COMMAND_OWNER_DISPLAY_ONLY = "display_only"

KIND_RUNTIME_COMMAND_LABEL = "runtime_command_label"
KIND_LOCAL_CLI_VALIDATION_COMMAND = "local_cli_validation_command"
KIND_LOCAL_CLI_HELPER_COMMAND = "local_cli_helper_command"
KIND_LOCAL_CLI_FINALIZER_COMMAND = "local_cli_finalizer_command"
KIND_LOCAL_CLI_TRANSITION_COMMAND = "local_cli_transition_command"
KIND_UNKNOWN_DISPLAY_ONLY = "unknown_display_only"

_SHELL_CONTROL_TOKENS = ("\n", "\r", ";", "|", "&", "<", ">", "`", "$(")

NextCommandOwner = Literal[
    "runtime",
    "local_readonly",
    "local_helper",
    "local_finalizer",
    "local_transition",
    "display_only",
]
NextCommandSurfaceContext = Literal["shared_next_up", "active_runtime"]


@dataclass(frozen=True, slots=True)
class CommandRunHint:
    """Compact metadata for rendering a command suggestion without executing it."""

    source: str
    kind: str
    command: str
    action: str | None = None
    phase: str | None = None
    requires_user_initiated_runtime_command: bool = False
    fresh_context_recommended: bool = False
    notes: tuple[str, ...] = ()
    schema_version: int = COMMAND_RUN_HINT_SCHEMA_VERSION
    execution: str = COMMAND_RUN_HINT_EXECUTION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-stable run-hint payload."""

        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "kind": self.kind,
            "command": self.command,
            "action": self.action,
            "phase": self.phase,
            "execution": self.execution,
            "requires_user_initiated_runtime_command": self.requires_user_initiated_runtime_command,
            "fresh_context_recommended": self.fresh_context_recommended,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class NextCommand:
    """Typed decision for rendering a visible next command without running it."""

    label: str
    action: str | None
    owner: NextCommandOwner
    phase: str | None = None
    reason: str | None = None
    kind: str = KIND_UNKNOWN_DISPLAY_ONLY
    requires_user_initiated_runtime_command: bool = False
    fresh_context_recommended: bool = False
    notes: tuple[str, ...] = ()
    schema_version: int = COMMAND_RUN_HINT_SCHEMA_VERSION
    execution: str = COMMAND_RUN_HINT_EXECUTION

    @property
    def command(self) -> str:
        """Return the rendered command label."""

        return self.label

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-stable typed next-command payload."""

        return {
            "schema_version": self.schema_version,
            "label": self.label,
            "command": self.command,
            "action": self.action,
            "phase": self.phase,
            "owner": self.owner,
            "reason": self.reason,
            "kind": self.kind,
            "execution": self.execution,
            "requires_user_initiated_runtime_command": self.requires_user_initiated_runtime_command,
            "fresh_context_recommended": self.fresh_context_recommended,
            "notes": list(self.notes),
        }

    def as_run_hint(self, *, source: str) -> dict[str, object]:
        """Return the legacy run-hint dict for compatibility consumers."""

        return CommandRunHint(
            source=source,
            kind=self.kind,
            command=self.command,
            action=self.action,
            phase=self.phase,
            requires_user_initiated_runtime_command=self.requires_user_initiated_runtime_command,
            fresh_context_recommended=self.fresh_context_recommended,
            notes=self.notes,
            schema_version=self.schema_version,
            execution=self.execution,
        ).as_dict()


@dataclass(frozen=True, slots=True)
class _LocalCliRunHintRule:
    kind: str
    owner: NextCommandOwner
    command_roots: tuple[str, ...]
    notes: tuple[str, ...] = ("display_copy_safe", "not_executed")


@lru_cache(maxsize=1)
def _registered_command_slugs() -> frozenset[str]:
    try:
        from gpd.registry import list_commands
    except ModuleNotFoundError as exc:
        if exc.name != "gpd.registry":
            raise
        return frozenset()
    return frozenset(str(slug) for slug in list_commands(name_format="slug"))


def _unique_ordered(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _local_validation_command_root(command: str) -> str | None:
    parts = command.split()
    if len(parts) >= 2 and parts[0] == "gpd" and parts[1] == "validate":
        return " ".join(parts[:2])
    return None


@lru_cache(maxsize=1)
def _contract_local_validation_command_roots() -> tuple[str, ...]:
    roots = tuple(
        root for command in local_cli_bridge_commands() if (root := _local_validation_command_root(command)) is not None
    )
    return _unique_ordered(roots)


@lru_cache(maxsize=1)
def _local_cli_run_hint_rules() -> tuple[_LocalCliRunHintRule, ...]:
    return (
        _LocalCliRunHintRule(
            kind=KIND_LOCAL_CLI_VALIDATION_COMMAND,
            owner=NEXT_COMMAND_OWNER_LOCAL_READONLY,
            command_roots=(
                *_contract_local_validation_command_roots(),
                "gpd phase closeout-readiness",
                "gpd --raw phase closeout-readiness",
            ),
        ),
        _LocalCliRunHintRule(
            kind=KIND_LOCAL_CLI_HELPER_COMMAND,
            owner=NEXT_COMMAND_OWNER_LOCAL_HELPER,
            command_roots=("gpd --raw phase checkpoint cleanup",),
        ),
        _LocalCliRunHintRule(
            kind=KIND_LOCAL_CLI_FINALIZER_COMMAND,
            owner=NEXT_COMMAND_OWNER_LOCAL_FINALIZER,
            command_roots=(
                "gpd verification-report",
                "gpd proof-redteam",
                "gpd apply-return-updates",
            ),
        ),
        _LocalCliRunHintRule(
            kind=KIND_LOCAL_CLI_TRANSITION_COMMAND,
            owner=NEXT_COMMAND_OWNER_LOCAL_TRANSITION,
            command_roots=(
                "gpd phase complete",
                "gpd state advance",
                "gpd state record-verification",
            ),
        ),
    )


def _contains_shell_control_tokens(command: str) -> bool:
    return any(token in command for token in _SHELL_CONTROL_TOKENS)


def _is_registered_runtime_label(command: str) -> bool:
    parts = parse_command_label(command)
    if not parts.prefix or not parts.slug:
        return False

    registered_slugs = _registered_command_slugs()
    return not registered_slugs or parts.slug in registered_slugs


def _shared_next_up_public_runtime_prefixes() -> tuple[str, ...]:
    return tuple(prefix for prefix in runtime_public_command_prefixes() if not prefix.startswith("$"))


def _runtime_label_allowed_for_surface(
    prefix: str,
    *,
    surface_context: NextCommandSurfaceContext,
    active_runtime_public_prefix: str | None,
) -> bool:
    if prefix == "gpd:":
        return True
    if prefix in _shared_next_up_public_runtime_prefixes():
        return True
    if (
        surface_context == NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME
        and active_runtime_public_prefix is not None
        and prefix == active_runtime_public_prefix.strip()
    ):
        return True
    return False


def _starts_with_command_prefix(command: str, prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        if command == prefix or command.startswith(f"{prefix} "):
            return True
    return False


def _raw_loader_display_only_notes(command: str) -> tuple[str, ...] | None:
    lowered = command.lower()
    if lowered.startswith("gpd --raw init") or lowered.startswith("--raw init"):
        return ("raw_staged_init_display_only", "display_only")
    if lowered.startswith("gpd --raw stage field-access") or lowered.startswith("--raw stage field-access"):
        return ("raw_stage_field_access_display_only", "display_only")
    return None


def _display_only_next_command(
    *,
    command: str,
    action: str | None,
    phase: str | None,
    reason: str | None = None,
    notes: tuple[str, ...],
) -> NextCommand:
    return NextCommand(
        label=command,
        kind=KIND_UNKNOWN_DISPLAY_ONLY,
        owner=NEXT_COMMAND_OWNER_DISPLAY_ONLY,
        action=action,
        phase=phase,
        reason=reason,
        notes=notes,
    )


def classify_next_command(
    *,
    command: str | None,
    action: str | None = None,
    phase: str | None = None,
    reason: str | None = None,
    surface_context: NextCommandSurfaceContext = NEXT_COMMAND_SURFACE_CONTEXT_SHARED_NEXT_UP,
    active_runtime_public_prefix: str | None = None,
) -> NextCommand | None:
    """Classify an already-rendered command label without executing it."""

    normalized_command = command.strip() if isinstance(command, str) else ""
    if not normalized_command:
        return None

    if _contains_shell_control_tokens(normalized_command):
        return _display_only_next_command(
            command=normalized_command,
            action=action,
            phase=phase,
            reason=reason,
            notes=("shell_control_tokens_present", "display_only"),
        )

    if (raw_loader_notes := _raw_loader_display_only_notes(normalized_command)) is not None:
        return _display_only_next_command(
            command=normalized_command,
            action=action,
            phase=phase,
            reason=reason,
            notes=raw_loader_notes,
        )

    parsed = parse_command_label(normalized_command)
    if parsed.prefix and _is_registered_runtime_label(normalized_command):
        if not _runtime_label_allowed_for_surface(
            parsed.prefix,
            surface_context=surface_context,
            active_runtime_public_prefix=active_runtime_public_prefix,
        ):
            return _display_only_next_command(
                command=normalized_command,
                action=action or parsed.slug,
                phase=phase,
                reason=reason,
                notes=("runtime_label_not_valid_for_surface_context", "display_only"),
            )

        return NextCommand(
            label=normalized_command,
            action=action or parsed.slug,
            owner=NEXT_COMMAND_OWNER_RUNTIME,
            phase=phase,
            reason=reason,
            kind=KIND_RUNTIME_COMMAND_LABEL,
            requires_user_initiated_runtime_command=True,
            fresh_context_recommended=True,
            notes=("user_initiated_runtime_command_required",),
        )

    if action == "verify-work" and normalized_command.startswith("gpd verify phase"):
        return _display_only_next_command(
            command=normalized_command,
            action=action,
            phase=phase,
            reason=reason,
            notes=("structural_verify_phase_display_only", "unrecognized_command_display_only"),
        )

    for rule in _local_cli_run_hint_rules():
        if _starts_with_command_prefix(normalized_command, rule.command_roots):
            return NextCommand(
                label=normalized_command,
                action=action,
                owner=rule.owner,
                phase=phase,
                reason=reason,
                kind=rule.kind,
                notes=rule.notes,
            )

    return _display_only_next_command(
        command=normalized_command,
        action=action,
        phase=phase,
        reason=reason,
        notes=("unrecognized_command_display_only",),
    )


def build_command_run_hint(
    *,
    command: str | None,
    source: str,
    action: str | None = None,
    phase: str | None = None,
    surface_context: NextCommandSurfaceContext = NEXT_COMMAND_SURFACE_CONTEXT_SHARED_NEXT_UP,
    active_runtime_public_prefix: str | None = None,
) -> dict[str, object] | None:
    """Return read-only run metadata for an existing command string.

    This helper never shells out, never dispatches through the runtime bridge,
    and never interprets shell syntax for execution.
    """

    next_command = classify_next_command(
        command=command,
        action=action,
        phase=phase,
        surface_context=surface_context,
        active_runtime_public_prefix=active_runtime_public_prefix,
    )
    return next_command.as_run_hint(source=source) if next_command is not None else None


__all__ = [
    "COMMAND_RUN_HINT_EXECUTION",
    "COMMAND_RUN_HINT_SCHEMA_VERSION",
    "KIND_LOCAL_CLI_HELPER_COMMAND",
    "KIND_LOCAL_CLI_TRANSITION_COMMAND",
    "KIND_LOCAL_CLI_FINALIZER_COMMAND",
    "KIND_LOCAL_CLI_VALIDATION_COMMAND",
    "KIND_RUNTIME_COMMAND_LABEL",
    "KIND_UNKNOWN_DISPLAY_ONLY",
    "NEXT_COMMAND_OWNER_DISPLAY_ONLY",
    "NEXT_COMMAND_OWNER_LOCAL_FINALIZER",
    "NEXT_COMMAND_OWNER_LOCAL_HELPER",
    "NEXT_COMMAND_OWNER_LOCAL_READONLY",
    "NEXT_COMMAND_OWNER_LOCAL_TRANSITION",
    "NEXT_COMMAND_OWNER_RUNTIME",
    "NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME",
    "NEXT_COMMAND_SURFACE_CONTEXT_SHARED_NEXT_UP",
    "CommandRunHint",
    "NextCommand",
    "build_command_run_hint",
    "classify_next_command",
]
