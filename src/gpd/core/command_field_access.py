"""Registry-backed command-context field access metadata."""

from __future__ import annotations

from dataclasses import dataclass

from gpd.command_labels import canonical_command_label, parse_command_label
from gpd.core.command_subjects import (
    _command_effective_context_mode,
    _command_explicit_input_labels_from_policy,
    _command_has_typed_subject_policy,
)

COMMAND_FIELD_ACCESS_STYLES = frozenset({"instruction", "json"})

COMMAND_CONTEXT_FIELD_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    ("command", "Canonical public command label returned by command-context validation."),
    ("context_mode", "Effective command context mode used for workspace gating."),
    ("passed", "Overall validation result after blocking checks are evaluated."),
    ("project_exists", "Whether the validated context includes GPD/PROJECT.md."),
    ("explicit_inputs", "Accepted standalone input kinds for project-aware commands."),
    ("guidance", "User-facing recovery text when validation does not pass."),
    ("checks", "Validation checks; inspect entries by name before acting on a result."),
    ("resolved_mode", "Specialized mode selected by command-specific validation, when present."),
    ("mode_reason", "Reason for the specialized resolved mode, when present."),
    ("validated_surface", "Public runtime command surface that was validated."),
    ("public_runtime_command_prefix", "Public command prefix for the active runtime surface."),
    ("local_cli_equivalence_guaranteed", "Whether a same-name local CLI command is guaranteed."),
    ("dispatch_note", "Short note separating runtime command validation from local CLI dispatch."),
    ("resolved_subject", "Structured subject resolution record for subject-aware commands."),
    ("selected_publication_root", "Publication root selected by publication-oriented commands, when any."),
    ("selected_review_root", "Review root selected by review-oriented commands, when any."),
)

CHECK_FIELD_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    ("name", "Stable check identifier."),
    ("passed", "Whether that check passed."),
    ("blocking", "Whether this failed check blocks command execution."),
    ("detail", "Human-readable evidence or recovery detail for the check."),
)

RESOLVED_SUBJECT_FIELD_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    ("command", "Canonical command label that owns this subject resolution."),
    ("workspace_root", "Workspace that supplied the command-context request."),
    ("resolved_project_root", "Project root selected for project-backed subjects, when any."),
    ("context_root", "Root used for command-owned reads and managed outputs."),
    ("target_path", "Resolved concrete target path, when any."),
    ("target_root", "Resolved target container, when any."),
    ("subject_kind", "Registry subject kind for the command."),
    ("ownership_mode", "Whether the subject is workspace-locked, project-backed, or external."),
    ("status", "Resolution status such as resolved, bootstrap, interactive, or missing."),
    ("exists", "Whether the concrete target path exists."),
    ("explicit_input", "Whether the user supplied a concrete subject argument."),
    ("project_root_source", "How the project root was selected, when applicable."),
    ("project_root_auto_selected", "Whether project root selection was automatic."),
    ("reentry_mode", "Project reentry mode used for the subject, when applicable."),
    ("ancestor_walked_up", "Whether an ancestor project root was used."),
    ("detail", "Human-readable subject resolution detail."),
)


@dataclass(frozen=True, slots=True)
class CommandContextField:
    """One selected field from the command-context payload."""

    name: str
    description: str

    def to_payload(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}


@dataclass(frozen=True, slots=True)
class CommandFieldAccess:
    """Field-access metadata for one command-context payload."""

    command: str
    requested_command: str
    style: str
    selected_fields: tuple[CommandContextField, ...]
    check_fields: tuple[CommandContextField, ...]
    resolved_subject_fields: tuple[CommandContextField, ...]
    slug: str
    context_mode: str
    effective_context_mode: str
    argument_hint: str
    project_reentry_capable: bool
    subject_required: bool
    explicit_input_labels: tuple[str, ...]
    instructions: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "command": self.command,
            "requested_command": self.requested_command,
            "style": self.style,
            "read_only": True,
            "source": {
                "type": "command_context_preflight_result",
                "validator": "validate command-context",
            },
            "command_metadata": {
                "slug": self.slug,
                "context_mode": self.context_mode,
                "effective_context_mode": self.effective_context_mode,
                "argument_hint": self.argument_hint,
                "project_reentry_capable": self.project_reentry_capable,
                "subject_required": self.subject_required,
                "explicit_input_labels": list(self.explicit_input_labels),
            },
            "selected_fields": [field.name for field in self.selected_fields],
            "field_descriptions": [field.to_payload() for field in self.selected_fields],
            "nested_field_descriptions": {
                "checks": [field.to_payload() for field in self.check_fields],
                "resolved_subject": [field.to_payload() for field in self.resolved_subject_fields],
            },
        }
        if self.instructions:
            payload["instructions"] = list(self.instructions)
        return payload


def build_command_field_access(command_name: str, *, style: str = "instruction") -> CommandFieldAccess:
    """Build field-access metadata for ``validate command-context`` payloads."""

    normalized_style = style.strip().casefold()
    if normalized_style not in COMMAND_FIELD_ACCESS_STYLES:
        raise ValueError(
            f"Unknown command field-access style {style!r}; expected one of: "
            f"{', '.join(sorted(COMMAND_FIELD_ACCESS_STYLES))}"
        )

    command = _resolve_command_or_error(command_name)
    parsed = parse_command_label(command.name)
    selected_fields = _field_objects(COMMAND_CONTEXT_FIELD_DESCRIPTIONS)
    check_fields = _field_objects(CHECK_FIELD_DESCRIPTIONS)
    resolved_subject_fields = _field_objects(RESOLVED_SUBJECT_FIELD_DESCRIPTIONS)
    explicit_input_labels = tuple(_command_explicit_input_labels_from_policy(command))

    return CommandFieldAccess(
        command=command.name,
        requested_command=command_name,
        style=normalized_style,
        selected_fields=selected_fields,
        check_fields=check_fields,
        resolved_subject_fields=resolved_subject_fields,
        slug=parsed.slug,
        context_mode=str(getattr(command, "context_mode", "") or ""),
        effective_context_mode=_command_effective_context_mode(command),
        argument_hint=str(getattr(command, "argument_hint", "") or ""),
        project_reentry_capable=bool(getattr(command, "project_reentry_capable", False)),
        subject_required=_command_has_typed_subject_policy(command),
        explicit_input_labels=explicit_input_labels,
        instructions=_instruction_lines(command.name, selected_fields) if normalized_style == "instruction" else (),
    )


def _resolve_command_or_error(command_name: str) -> object:
    from gpd import registry as content_registry

    lookup = parse_command_label(command_name).command or command_name.strip()
    try:
        return content_registry.get_command(lookup)
    except KeyError as exc:
        requested_name = canonical_command_label(command_name)
        known_commands = content_registry.list_commands(name_format="label")
        preview = ", ".join(known_commands[:12])
        if len(known_commands) > 12:
            preview += ", ..."
        raise ValueError(f"Unknown GPD command: {requested_name}. Allowed commands include: {preview}") from exc


def _field_objects(field_descriptions: tuple[tuple[str, str], ...]) -> tuple[CommandContextField, ...]:
    return tuple(CommandContextField(name=name, description=description) for name, description in field_descriptions)


def _instruction_lines(command_name: str, selected_fields: tuple[CommandContextField, ...]) -> tuple[str, ...]:
    field_list = ", ".join(field.name for field in selected_fields)
    return (
        f"{command_name} command-context validation returns these selected top-level fields: {field_list}.",
        "Read those keys directly from the returned JSON object.",
        "Use checks entries by their name field; do not rely on list position.",
        "Use resolved_subject only when the command resolves a concrete subject.",
    )


__all__ = [
    "COMMAND_FIELD_ACCESS_STYLES",
    "CommandContextField",
    "CommandFieldAccess",
    "build_command_field_access",
]
