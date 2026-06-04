"""Registry-backed rendering helpers for the public GPD help surface."""

from __future__ import annotations

import dataclasses
import textwrap
from functools import lru_cache
from typing import TypeAlias

from gpd.command_labels import canonical_command_label, parse_command_label, rewrite_runtime_command_surfaces_to_public
from gpd.core.public_surface_contract import (
    beginner_startup_ladder,
    beginner_startup_ladder_text,
    local_cli_cost_command,
    local_cli_observe_execution_command,
    local_cli_resume_command,
    local_cli_resume_recent_command,
)
from gpd.registry import CommandDef, CommandHelpMetadata, get_command, list_commands

CommandGroupPayload: TypeAlias = dict[str, object]
CommandEntryPayload: TypeAlias = dict[str, str]

DETAILED_HELP_FOLLOW_UP = "Use `gpd:help --command <name>` when you want detailed notes for one runtime command."


@dataclasses.dataclass(frozen=True, slots=True)
class HelpCommandEntry:
    """One compact command-index row."""

    command: str
    description: str
    registry_command: str
    documented_variant: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class HelpCommandGroup:
    """One compact command-index group."""

    name: str
    commands: tuple[HelpCommandEntry, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class HelpCommandDetail:
    """Compact registry metadata used by machine-readable help consumers."""

    canonical_command: str
    slug: str
    description: str
    argument_hint: str
    context_mode: str
    project_reentry_capable: bool
    signature: str
    group: str
    documented_variants: list[str]
    allowed_tools: list[str]
    requires: dict[str, object]

    def as_payload(self) -> dict[str, object]:
        return dataclasses.asdict(self)


_ADDITIONAL_QUICK_START_RUNTIME_COMMANDS = (
    "gpd:progress",
    "gpd:suggest-next",
    "gpd:settings",
    "gpd:set-tier-models",
    "gpd:tangent",
    "gpd:branch-hypothesis",
)

_DEFAULT_HELP_RUNTIME_COMMANDS = (
    "gpd:start",
    "gpd:new-project",
    "gpd:map-research",
    "gpd:resume-work",
)


def _runtime_command_for_ladder_step(step: str) -> tuple[str, ...]:
    return tuple(f"gpd:{part.strip()}" for part in step.split("/") if part.strip())


def _startup_ladder_runtime_command_map(ladder: tuple[str, ...]) -> dict[str, str]:
    commands: dict[str, str] = {}
    for step in ladder:
        for command in _runtime_command_for_ladder_step(step):
            commands[parse_command_label(command).slug] = command
    return commands


def _required_ladder_command(commands: dict[str, str], slug: str) -> str:
    try:
        return commands[slug]
    except KeyError as exc:
        raise ValueError(f"beginner startup ladder must include {slug!r}") from exc


def _format_ladder_step_as_runtime_commands(step: str, *, public_prefix: str = "gpd:") -> str:
    commands = _runtime_command_for_ladder_step(step)
    if not commands:
        raise ValueError("beginner startup ladder steps must contain at least one command")
    return " or ".join(f"`{_apply_public_prefix(command, public_prefix=public_prefix)}`" for command in commands)


def _runtime_ladder_sentence(ladder: tuple[str, ...], *, public_prefix: str = "gpd:") -> str:
    command_fragments = tuple(
        _format_ladder_step_as_runtime_commands(step, public_prefix=public_prefix) for step in ladder
    )
    if len(command_fragments) < 2:
        raise ValueError("beginner startup ladder must contain at least two steps")
    return (
        "In runtime terms, that means "
        + ", then ".join(command_fragments[:-1])
        + f", and later {command_fragments[-1]} when you return."
    )


def _quick_start_runtime_commands() -> tuple[str, ...]:
    ladder_commands = tuple(
        command for step in beginner_startup_ladder() for command in _runtime_command_for_ladder_step(step)
    )
    return (*ladder_commands, *_ADDITIONAL_QUICK_START_RUNTIME_COMMANDS)


def _required_help_metadata(command: CommandDef) -> CommandHelpMetadata:
    """Return parsed command-owned help metadata, failing closed if absent."""

    if command.help is None:
        raise ValueError(f"{command.name} is missing required help metadata")
    return command.help


def _default_signature_for_command(command: CommandDef) -> str:
    if command.argument_hint:
        return f"{command.name} {command.argument_hint}"
    return command.name


def _index_signature_for_command(command: CommandDef) -> str:
    help_metadata = _required_help_metadata(command)
    return help_metadata.display_signature or _default_signature_for_command(command)


def _variant_entries_for_command(command: CommandDef) -> tuple[HelpCommandEntry, ...]:
    help_metadata = _required_help_metadata(command)
    return tuple(
        HelpCommandEntry(
            command=variant.command,
            description=variant.description,
            registry_command=command.name,
            documented_variant=True,
        )
        for variant in help_metadata.variants
    )


def _base_command_entries_by_label() -> dict[str, tuple[str, HelpCommandEntry]]:
    entries: dict[str, tuple[str, HelpCommandEntry]] = {}
    for group in help_command_groups():
        for entry in group.commands:
            if entry.documented_variant:
                continue
            entries[entry.registry_command] = (group.name, entry)
    return entries


def _documented_variants_for(registry_command: str) -> tuple[str, ...]:
    command = get_command(registry_command)
    help_metadata = _required_help_metadata(command)
    return tuple(variant.command for variant in help_metadata.variants)


def _display_signature_for_command(registry_command: str) -> str:
    command = get_command(registry_command)
    help_metadata = _required_help_metadata(command)
    if help_metadata.detail_signature:
        return help_metadata.detail_signature
    if command.argument_hint:
        return f"{command.name} {command.argument_hint}"
    return help_metadata.display_signature or command.name


def _usage_examples_for(registry_command: str) -> tuple[str, ...]:
    command = get_command(registry_command)
    examples = _required_help_metadata(command).examples
    seen: set[str] = set()
    deduped: list[str] = []
    for example in examples:
        if example in seen:
            continue
        seen.add(example)
        deduped.append(example)
    return tuple(deduped)


def _notes_for(registry_command: str) -> tuple[str, ...]:
    command = get_command(registry_command)
    return _required_help_metadata(command).notes


@lru_cache(maxsize=1)
def _root_detailed_reference_commands() -> tuple[str, ...]:
    records: list[tuple[int, str]] = []
    seen_orders: dict[int, str] = {}
    for command_label in list_commands(name_format="label"):
        command = get_command(command_label)
        help_metadata = _required_help_metadata(command)
        if help_metadata.root_detail_order is None:
            continue
        if help_metadata.root_detail_order in seen_orders:
            earlier = seen_orders[help_metadata.root_detail_order]
            raise ValueError(
                f"duplicate help.root_detail_order {help_metadata.root_detail_order}: {earlier} and {command.name}"
            )
        seen_orders[help_metadata.root_detail_order] = command.name
        records.append((help_metadata.root_detail_order, command.name))
    return tuple(command_name for _order, command_name in sorted(records))


def _format_sequence(values: list[str] | tuple[str, ...], *, limit: int = 4) -> str:
    cleaned = [value for value in values if value]
    if not cleaned:
        return ""
    shown = cleaned[:limit]
    suffix = "" if len(cleaned) <= limit else f", and {len(cleaned) - limit} more"
    return ", ".join(f"`{value}`" for value in shown) + suffix


def _requires_summary(requires: dict[str, object]) -> tuple[str, ...]:
    lines: list[str] = []
    for key in sorted(requires):
        value = requires[key]
        if isinstance(value, list):
            rendered = _format_sequence([str(item) for item in value])
            if rendered:
                lines.append(f"{key}: {rendered}")
            continue
        if isinstance(value, tuple):
            rendered = _format_sequence(tuple(str(item) for item in value))
            if rendered:
                lines.append(f"{key}: {rendered}")
            continue
        if value not in (None, "", [], {}):
            lines.append(f"{key}: `{value}`")
    return tuple(lines)


def _command_policy_summary(command_name: str) -> tuple[str, ...]:
    command = get_command(command_name)
    policy = command.command_policy
    if policy is None:
        return ()

    lines: list[str] = []
    subject = policy.subject_policy
    if subject is not None and (
        subject.subject_kind
        or subject.resolution_mode
        or subject.explicit_input_kinds
        or subject.allow_external_subjects is not None
        or subject.bootstrap_allowed is not None
    ):
        parts: list[str] = []
        if subject.subject_kind:
            parts.append(f"subject={subject.subject_kind}")
        if subject.resolution_mode:
            parts.append(f"resolution={subject.resolution_mode}")
        if subject.explicit_input_kinds:
            parts.append("explicit inputs=" + ", ".join(subject.explicit_input_kinds))
        if subject.allow_external_subjects is not None:
            parts.append(f"external subjects allowed={str(subject.allow_external_subjects).lower()}")
        if subject.bootstrap_allowed is not None:
            parts.append(f"bootstrap allowed={str(subject.bootstrap_allowed).lower()}")
        lines.append("Subject policy: " + "; ".join(parts))

    output = policy.output_policy
    if output is not None and (
        output.output_mode or output.managed_root_kind or output.default_output_subtree or output.stage_artifact_policy
    ):
        parts = []
        if output.output_mode:
            parts.append(f"mode={output.output_mode}")
        if output.managed_root_kind:
            parts.append(f"managed root={output.managed_root_kind}")
        if output.default_output_subtree:
            parts.append(f"default subtree={output.default_output_subtree}")
        if output.stage_artifact_policy:
            parts.append(f"stage artifacts={output.stage_artifact_policy}")
        lines.append("Output policy: " + "; ".join(parts))
    return tuple(lines)


def _review_contract_summary(command_name: str) -> tuple[str, ...]:
    command = get_command(command_name)
    contract = command.review_contract
    if contract is None:
        return ()
    lines = [
        (
            f"Review contract: {contract.review_mode} mode with "
            f"{len(contract.required_outputs)} required output(s), "
            f"{len(contract.preflight_checks)} preflight check(s), and "
            f"{len(contract.blocking_conditions)} blocking condition(s)."
        )
    ]
    if contract.scope_variants:
        scopes = ", ".join(variant.scope for variant in contract.scope_variants)
        lines.append(f"Scope variants: {scopes}.")
    return tuple(lines)


def _staged_workflow_summary(command_name: str) -> tuple[str, ...]:
    command = get_command(command_name)
    manifest = command.staged_loading
    if manifest is None:
        return ()
    return (f"Staged workflow: `{manifest.workflow_id}`.",)


@lru_cache(maxsize=1)
def help_command_groups() -> tuple[HelpCommandGroup, ...]:
    """Return compact help groups, validating every base command against the registry."""

    records: list[tuple[int, str, tuple[HelpCommandEntry, ...]]] = []
    seen_orders: dict[int, str] = {}
    for command_label in list_commands(name_format="label"):
        command = get_command(command_label)
        help_metadata = _required_help_metadata(command)
        if help_metadata.order in seen_orders:
            earlier = seen_orders[help_metadata.order]
            raise ValueError(f"duplicate help.order {help_metadata.order}: {earlier} and {command.name}")
        seen_orders[help_metadata.order] = command.name
        base_entry = HelpCommandEntry(
            command=_index_signature_for_command(command),
            description=help_metadata.compact_description or command.description,
            registry_command=command.name,
            documented_variant=False,
        )
        records.append((help_metadata.order, help_metadata.group, (base_entry, *_variant_entries_for_command(command))))

    group_entries: dict[str, list[HelpCommandEntry]] = {}
    for _order, group_name, entries in sorted(records):
        group_entries.setdefault(group_name, []).extend(entries)

    groups = tuple(
        HelpCommandGroup(name=group_name, commands=tuple(entries)) for group_name, entries in group_entries.items()
    )
    registry_commands = set(list_commands(name_format="label"))
    grouped_registry_commands = {
        entry.registry_command for group in groups for entry in group.commands if not entry.documented_variant
    }
    missing = sorted(registry_commands - grouped_registry_commands)
    extra = sorted(grouped_registry_commands - registry_commands)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing registry commands: {', '.join(missing)}")
        if extra:
            details.append(f"unknown grouped commands: {', '.join(extra)}")
        raise ValueError("; ".join(details))
    return groups


def command_groups_payload() -> list[CommandGroupPayload]:
    """Return raw-help-compatible grouped command metadata."""

    return [
        {
            "name": group.name,
            "commands": [
                {
                    "command": entry.command,
                    "description": entry.description,
                }
                for entry in group.commands
            ],
        }
        for group in help_command_groups()
    ]


def build_help_catalog() -> dict[str, object]:
    """Return registry-backed help metadata for sync tests and integrations."""

    return {"command_groups": help_command_groups()}


def command_index_payload() -> list[dict[str, str]]:
    """Return compact registry command metadata in stable registry order."""

    return [
        {
            "command": command.name,
            "slug": parse_command_label(command.name).slug,
            "description": command.description,
        }
        for slug in list_commands(name_format="slug")
        for command in (get_command(slug),)
    ]


def command_detail_payload(
    command_name: str,
    *,
    minimal: bool = False,
    include_markdown: bool = False,
) -> dict[str, object]:
    """Return compact registry metadata for one command lookup."""

    command = get_command(canonical_command_label(command_name))
    group_name, _entry = _base_command_entries_by_label()[command.name]
    detail = HelpCommandDetail(
        canonical_command=command.name,
        slug=parse_command_label(command.name).slug,
        description=command.description,
        argument_hint=command.argument_hint,
        context_mode=command.context_mode,
        project_reentry_capable=command.project_reentry_capable,
        signature=_display_signature_for_command(command.name),
        group=group_name,
        documented_variants=list(_documented_variants_for(command.name)),
        allowed_tools=[] if minimal else command.allowed_tools,
        requires={} if minimal else command.requires,
    )
    payload = detail.as_payload()
    if include_markdown:
        payload["detail_markdown"] = render_command_detail_markdown(command.name, include_group_heading=True)
    return payload


def _render_command_detail_block(
    registry_command: str,
    *,
    include_group_heading: bool,
    public_prefix: str,
    include_metadata: bool = True,
) -> str:
    command = get_command(registry_command)
    group_name, _entry = _base_command_entries_by_label()[command.name]
    signature = _apply_public_prefix(_display_signature_for_command(command.name), public_prefix=public_prefix)
    lines: list[str] = []
    if include_group_heading:
        lines.extend((f"### {group_name}", ""))

    lines.extend(
        (
            f"**`{signature}`**",
            command.description.strip(),
        )
    )
    examples = _usage_examples_for(command.name)
    if examples:
        lines.append("")
        lines.extend(f"- `{_apply_public_prefix(example, public_prefix=public_prefix)}`" for example in examples)

    variants = tuple(
        _apply_public_prefix(variant, public_prefix=public_prefix) for variant in _documented_variants_for(command.name)
    )
    if variants:
        lines.extend(("", "Documented variants:"))
        lines.extend(f"- `{variant}`" for variant in variants)

    notes = _notes_for(command.name)
    if notes:
        lines.extend(("", "Notes:"))
        lines.extend(f"- {note}" for note in notes)

    if include_metadata:
        metadata_lines: list[str] = []
        for require_line in _requires_summary(command.requires):
            metadata_lines.append(f"- Requires {require_line}")
        for policy_line in _command_policy_summary(command.name):
            metadata_lines.append(f"- {policy_line}")
        for review_line in _review_contract_summary(command.name):
            metadata_lines.append(f"- {review_line}")
        for staged_line in _staged_workflow_summary(command.name):
            metadata_lines.append(f"- {staged_line}")
        if metadata_lines:
            lines.extend(("", *metadata_lines))
    return "\n".join(lines).strip()


def _render_root_command_detail_block(
    registry_command: str,
    *,
    public_prefix: str,
) -> str:
    """Render a terse root-help command detail without metadata expansion."""

    command = get_command(registry_command)
    signature = _apply_public_prefix(_display_signature_for_command(command.name), public_prefix=public_prefix)
    lines = [f"**`{signature}`**", command.description.strip()]

    examples = tuple(
        _apply_public_prefix(example, public_prefix=public_prefix) for example in _usage_examples_for(command.name)
    )
    if examples:
        lines.append("Usage: " + "; ".join(f"`{example}`" for example in examples))

    notes = _notes_for(command.name)
    if notes:
        lines.append("Notes: " + " ".join(notes))

    return "\n".join(lines).strip()


def _apply_public_prefix(text: str, *, public_prefix: str) -> str:
    if public_prefix == "gpd:":
        return text
    return rewrite_runtime_command_surfaces_to_public(text, public_prefix=public_prefix)


def format_help_all_command(*, public_prefix: str = "gpd:") -> str:
    """Render the runtime-public command for the compact help index."""

    return _apply_public_prefix("gpd:help --all", public_prefix=public_prefix)


def format_detailed_help_follow_up(*, public_prefix: str = "gpd:") -> str:
    """Render the runtime-public detailed-help follow-up sentence."""

    return _apply_public_prefix(DETAILED_HELP_FOLLOW_UP, public_prefix=public_prefix)


def render_command_detail_markdown(
    command_name: str,
    *,
    public_prefix: str = "gpd:",
    include_group_heading: bool = True,
) -> str:
    """Render one detailed command block from registry and renderer help metadata."""

    command = get_command(canonical_command_label(command_name))
    return _render_command_detail_block(
        command.name,
        include_group_heading=include_group_heading,
        public_prefix=public_prefix,
    )


def _detailed_reference_intro_lines(*, public_prefix: str) -> list[str]:
    return [
        "## Detailed Command Reference",
        "",
        _apply_public_prefix(
            "Use `gpd:help --command <name>` when you want the detailed notes for one runtime command at a time.",
            public_prefix=public_prefix,
        ),
        "",
        _apply_public_prefix(
            "Core workflow: `gpd:new-project` -> `gpd:discuss-phase` -> `gpd:plan-phase` -> `gpd:execute-phase` -> `gpd:verify-work` -> repeat.",
            public_prefix=public_prefix,
        ),
        "",
        _apply_public_prefix(
            (
                "Project-aware technical-analysis lane: `gpd:derive-equation`, `gpd:dimensional-analysis`, "
                "`gpd:limiting-cases`, `gpd:numerical-convergence`, `gpd:sensitivity-analysis`, "
                "`GPD/analysis/`, and `GPD/sweeps/`. "
                "`gpd:graph` and `gpd:error-propagation` are separate commands and are not part of this relaxed "
                "current-workspace lane."
            ),
            public_prefix=public_prefix,
        ),
    ]


def render_root_detailed_command_reference_markdown(*, public_prefix: str = "gpd:") -> str:
    """Render the compact root fallback for detailed help."""

    lines = _detailed_reference_intro_lines(public_prefix=public_prefix)
    lines.extend(
        (
            "",
            (
                "The full generated command detail reference is installed at "
                "`{GPD_INSTALL_DIR}/references/help/detailed-command-reference.md`; the runtime bridge serves "
                "that detail one command at a time."
            ),
            "",
            _apply_public_prefix(
                (
                    "Current-workspace durable outputs can be created from a project context or outside a project "
                    "only when the user supplies an explicit derivation target or explicit file path. Parameter "
                    "and sensitivity helpers keep their explicit flags visible: `--param`, `--range`, `--target`, "
                    "and `--params`."
                ),
                public_prefix=public_prefix,
            ),
        )
    )
    for command_name in _root_detailed_reference_commands():
        lines.extend(
            (
                "",
                _render_root_command_detail_block(
                    command_name,
                    public_prefix=public_prefix,
                ),
            )
        )
    return "\n".join(lines).strip()


def render_detailed_command_reference_markdown(*, public_prefix: str = "gpd:") -> str:
    """Render the detailed command reference from registry and renderer help metadata."""

    lines = _detailed_reference_intro_lines(public_prefix=public_prefix)
    emitted: set[str] = set()
    for group in help_command_groups():
        lines.extend(("", f"### {group.name}"))
        for entry in group.commands:
            if entry.documented_variant or entry.registry_command in emitted:
                continue
            emitted.add(entry.registry_command)
            lines.extend(
                (
                    "",
                    _render_command_detail_block(
                        entry.registry_command,
                        include_group_heading=False,
                        public_prefix=public_prefix,
                    ),
                )
            )
    return "\n".join(lines).strip()


def render_quick_start_markdown(*, public_prefix: str = "gpd:") -> str:
    """Render the broad public quick-start reference used by help --all."""

    for command in _quick_start_runtime_commands():
        get_command(command)
    startup_ladder = beginner_startup_ladder()
    local_resume = local_cli_resume_command()
    local_resume_recent = local_cli_resume_recent_command()
    local_observe_execution = local_cli_observe_execution_command()
    local_cost = local_cli_cost_command()
    ladder_commands = _startup_ladder_runtime_command_map(startup_ladder)
    start_command = _required_ladder_command(ladder_commands, "start")
    tour_command = _required_ladder_command(ladder_commands, "tour")
    new_project_command = _required_ladder_command(ladder_commands, "new-project")
    map_research_command = _required_ladder_command(ladder_commands, "map-research")
    resume_work_command = _required_ladder_command(ladder_commands, "resume-work")
    start_command = _apply_public_prefix(start_command, public_prefix=public_prefix)
    tour_command = _apply_public_prefix(tour_command, public_prefix=public_prefix)
    new_project_command = _apply_public_prefix(new_project_command, public_prefix=public_prefix)
    map_research_command = _apply_public_prefix(map_research_command, public_prefix=public_prefix)
    resume_work_command = _apply_public_prefix(resume_work_command, public_prefix=public_prefix)
    return textwrap.dedent(
        f"""\
        ## Quick Start

        If you only remember one order, use this: {beginner_startup_ladder_text()}.
        {_runtime_ladder_sentence(startup_ladder, public_prefix=public_prefix)}

        Use the path that matches your current situation:

        **New work**
        1. `{start_command}` - Guided first-run router that chooses the safest first step for this folder
        2. `{tour_command}` - Get a read-only overview before choosing
        3. `{new_project_command}` - Create a full GPD project
        4. `{_apply_public_prefix("gpd:new-project --minimal", public_prefix=public_prefix)}` - Create a project through the shortest setup path

        **Existing work**
        1. `{map_research_command}` - Map an existing folder before turning it into a GPD project
        2. `{new_project_command}` - Turn that mapped context into a full GPD project

        **Returning work**
        1. `{local_resume}` - Reopen the current-workspace recovery snapshot from your normal terminal
        2. `{local_resume_recent}` - Find a different workspace first from your normal terminal
        3. `{resume_work_command}` - Continue inside the reopened project's canonical state
        4. `{_apply_public_prefix("gpd:progress", public_prefix=public_prefix)}` - See the broader project snapshot
        5. `{_apply_public_prefix("gpd:suggest-next", public_prefix=public_prefix)}` - Get the fastest next action
        6. `{local_observe_execution}` - Read-only progress / waiting state snapshot, conservative `possibly stalled` wording, and the next read-only checks from your normal terminal
        7. `{local_cost}` - Review recorded local telemetry usage / cost from your normal terminal

        **Post-startup settings**
        1. `{_apply_public_prefix("gpd:settings", public_prefix=public_prefix)}` - Change autonomy, permissions, and broader runtime preferences after your first successful start or later
        2. `{_apply_public_prefix("gpd:set-tier-models", public_prefix=public_prefix)}` - Pin concrete `tier-1`, `tier-2`, and `tier-3` model ids only

        When a side investigation appears later, use `{_apply_public_prefix("gpd:tangent", public_prefix=public_prefix)}` first. It is the chooser for stay / quick / defer / branch. Use `{_apply_public_prefix("gpd:branch-hypothesis", public_prefix=public_prefix)}` only when that tangent needs its own git-backed branch.
        """
    ).strip()


def render_default_help_markdown(*, public_prefix: str = "gpd:") -> str:
    """Render the short default help chooser."""

    for command in _DEFAULT_HELP_RUNTIME_COMMANDS:
        get_command(command)
    local_resume = local_cli_resume_command()
    local_resume_recent = local_cli_resume_recent_command()
    start_command = _apply_public_prefix("gpd:start", public_prefix=public_prefix)
    new_project_command = _apply_public_prefix("gpd:new-project", public_prefix=public_prefix)
    map_research_command = _apply_public_prefix("gpd:map-research", public_prefix=public_prefix)
    resume_work_command = _apply_public_prefix("gpd:resume-work", public_prefix=public_prefix)
    minimal_project_command = _apply_public_prefix("gpd:new-project --minimal", public_prefix=public_prefix)
    return textwrap.dedent(
        f"""\
        ## Quick Start

        Choose the path that matches this folder:

        **New folder**
        1. `{start_command}` - Let GPD inspect the folder and route the safest first step
        2. `{new_project_command}` - Create a full GPD project here
        3. `{minimal_project_command}` - Use the shortest setup path

        **Existing research folder**
        1. `{map_research_command}` - Map files and context before planning
        2. `{new_project_command}` - Turn the mapped context into a full GPD project

        **Returning project**
        1. `{local_resume}` - Reopen this workspace from your normal terminal
        2. `{local_resume_recent}` - Choose a different recent workspace from your normal terminal
        3. `{resume_work_command}` - Continue inside the reopened project's canonical state
        """
    ).strip()


def render_command_index_markdown(*, public_prefix: str = "gpd:") -> str:
    """Render the compact grouped command index from command-owned help metadata."""

    lines = [
        "## Command Index",
        "",
        "This is the compact grouped list of runtime commands. For normal-terminal install, readiness, and diagnostics commands, use `gpd --help`.",
    ]
    for group in help_command_groups():
        lines.extend(("", f"### {group.name}", ""))
        lines.extend(
            f"- `{_apply_public_prefix(entry.command, public_prefix=public_prefix)}` - {entry.description}"
            for entry in group.commands
        )
    return "\n".join(lines)


def render_quick_start(*, public_prefix: str = "gpd:") -> str:
    """Render the broad public quick-start reference used by help --all."""

    return render_quick_start_markdown(public_prefix=public_prefix)


def render_default_help(*, public_prefix: str = "gpd:") -> str:
    """Render the short default help chooser."""

    return render_default_help_markdown(public_prefix=public_prefix)


def render_command_index(*, public_prefix: str = "gpd:") -> str:
    """Render the compact grouped command index."""

    return render_command_index_markdown(public_prefix=public_prefix)


__all__ = [
    "DETAILED_HELP_FOLLOW_UP",
    "HelpCommandDetail",
    "HelpCommandEntry",
    "HelpCommandGroup",
    "build_help_catalog",
    "command_detail_payload",
    "command_groups_payload",
    "command_index_payload",
    "format_detailed_help_follow_up",
    "format_help_all_command",
    "help_command_groups",
    "render_default_help",
    "render_default_help_markdown",
    "render_command_index",
    "render_command_index_markdown",
    "render_command_detail_markdown",
    "render_detailed_command_reference_markdown",
    "render_root_detailed_command_reference_markdown",
    "render_quick_start",
    "render_quick_start_markdown",
]
