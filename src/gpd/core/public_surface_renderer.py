"""Pure Markdown renderers for repeated public onboarding surfaces."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from gpd.adapters.runtime_catalog import get_shared_install_metadata
from gpd.core.onboarding_surfaces import BeginnerRuntimeSurface, beginner_runtime_surface, beginner_runtime_surfaces
from gpd.core.public_surface_contract import PublicSurfaceContract, load_public_surface_contract

__all__ = [
    "PublicSurfaceRenderContext",
    "public_surface_block_ids",
    "public_surface_context",
    "public_surface_runtime_surfaces",
    "render_beginner_caveat_list",
    "render_beginner_preflight_list",
    "render_local_cli_bridge_summary",
    "render_os_install_matrix",
    "render_os_next_step_table",
    "render_post_start_settings_note",
    "render_recovery_reference_note",
    "render_public_surface_block",
    "render_default_recovery_note",
    "render_recovery_note",
    "render_runtime_doc_links",
    "render_runtime_quickstart_snippet",
    "render_runtime_quickstart_snippets",
    "render_startup_ladder",
    "render_supported_runtime_table",
    "render_terminal_runtime_bridge_text",
    "runtime_doc_filename",
    "runtime_quickstart_block_id",
]


@dataclass(frozen=True, slots=True)
class PublicSurfaceRenderContext:
    """Canonical inputs for public-surface rendering."""

    contract: PublicSurfaceContract
    runtime_surfaces: tuple[BeginnerRuntimeSurface, ...]
    bootstrap_command: str


@dataclass(frozen=True, slots=True)
class _NextStepAction:
    label: str
    command: Callable[[BeginnerRuntimeSurface, PublicSurfaceContract], str]


@dataclass(frozen=True, slots=True)
class _RuntimeCommandGroup:
    display_names: tuple[str, ...]
    commands: tuple[str, ...]


_RUNTIME_QUICKSTART_BLOCK_PREFIX = "runtime-quickstart-"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def public_surface_context(
    *,
    contract: PublicSurfaceContract | None = None,
    runtime_surfaces: Sequence[BeginnerRuntimeSurface] | None = None,
    bootstrap_command: str | None = None,
) -> PublicSurfaceRenderContext:
    """Return renderer inputs derived from canonical public-surface owners."""

    return PublicSurfaceRenderContext(
        contract=contract or load_public_surface_contract(),
        runtime_surfaces=public_surface_runtime_surfaces(runtime_surfaces),
        bootstrap_command=bootstrap_command or get_shared_install_metadata().bootstrap_command,
    )


def public_surface_runtime_surfaces(
    runtime_surfaces: Sequence[BeginnerRuntimeSurface] | None = None,
) -> tuple[BeginnerRuntimeSurface, ...]:
    """Return runtime surfaces in stable public documentation order."""

    catalog_surfaces = beginner_runtime_surfaces()
    if runtime_surfaces is None:
        return catalog_surfaces

    catalog_order = {surface.runtime_name: index for index, surface in enumerate(catalog_surfaces)}
    return tuple(
        surface
        for original_index, surface in sorted(
            enumerate(runtime_surfaces),
            key=lambda item: (catalog_order.get(item[1].runtime_name, len(catalog_order) + item[0]), item[0]),
        )
    )


def _context(context: PublicSurfaceRenderContext | None) -> PublicSurfaceRenderContext:
    return context or public_surface_context()


def _render_bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _markdown_cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", "<br>")


def _render_markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    header_line = "| " + " | ".join(_markdown_cell(header) for header in headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = ["| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join((header_line, separator_line, *row_lines))


def _code(value: str) -> str:
    return f"`{value}`"


def _unique_ordered(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.casefold()).strip("-")
    if not slug:
        raise ValueError("runtime display name must produce a non-empty documentation slug")
    return slug


def _install_command(surface: BeginnerRuntimeSurface, *, bootstrap_command: str) -> str:
    return f"{bootstrap_command} {surface.install_flag} --local"


def render_startup_ladder(context: PublicSurfaceRenderContext | None = None) -> str:
    return _context(context).contract.beginner_onboarding.render_startup_ladder()


def render_beginner_preflight_list(context: PublicSurfaceRenderContext | None = None) -> str:
    return _render_bullets(_context(context).contract.beginner_onboarding.preflight_requirements)


def render_beginner_caveat_list(context: PublicSurfaceRenderContext | None = None) -> str:
    return _render_bullets(_context(context).contract.beginner_onboarding.caveats)


def render_terminal_runtime_bridge_text(context: PublicSurfaceRenderContext | None = None) -> str:
    ctx = _context(context)
    launchers = ", ".join(
        _code(command) for command in _unique_ordered(surface.launch_command for surface in ctx.runtime_surfaces)
    )
    command_styles = ", ".join(
        _code(command) for command in _unique_ordered(surface.help_command for surface in ctx.runtime_surfaces)
    )
    return "\n".join(
        (
            "Use your normal terminal for installs, local `gpd ...` diagnostics, and runtime launchers "
            f"such as {launchers}.",
            "Use the opened runtime for the installed GPD command ladder "
            f"({ctx.contract.beginner_onboarding.render_startup_ladder()}); start with {command_styles}.",
        )
    )


def render_local_cli_bridge_summary(context: PublicSurfaceRenderContext | None = None) -> str:
    bridge = _context(context).contract.local_cli_bridge
    return "\n\n".join((bridge.render_note(), _render_bullets(_code(command) for command in bridge.commands)))


def render_post_start_settings_note(context: PublicSurfaceRenderContext | None = None) -> str:
    return _context(context).contract.post_start_settings.render_note()


def render_default_recovery_note(context: PublicSurfaceRenderContext | None = None) -> str:
    ctx = _context(context)
    ladder = ctx.contract.recovery_ladder
    recovery = (
        f"{ladder.title}: use {_code(ladder.local_snapshot_command)} for {ladder.local_snapshot_phrase}. "
        f"If that is the wrong workspace, use {_code(ladder.cross_workspace_command)} to "
        f"{ladder.cross_workspace_phrase}, then {ladder.resume_phrase} with {_code('resume-work')}. "
        f"After resuming, {_code('suggest-next')} is {ladder.next_phrase}. Before stepping away mid-phase, "
        f"run {_code('pause-work')} so that ladder has an explicit handoff to restore later."
    )
    return (
        f"{recovery} Fresh context resets are for context management, not as a recovery step; run "
        f"{_code(ladder.local_snapshot_command)} in your normal terminal only when workspace "
        f"rediscovery is needed."
    )


def render_recovery_reference_note(context: PublicSurfaceRenderContext | None = None) -> str:
    ctx = _context(context)
    recovery = ctx.contract.recovery_ladder.render_note(
        resume_work_phrase=_code("resume-work"),
        suggest_next_phrase=_code("suggest-next"),
        pause_work_phrase=_code("pause-work"),
    )
    resume = ctx.contract.resume_authority
    return (
        f"{recovery} {resume.durable_authority_phrase}. {resume.public_vocabulary_intro}. "
        f"Fresh context resets are for context management, not as a recovery step; then run "
        f"{ctx.contract.recovery_ladder.local_snapshot_command} in your normal terminal only when workspace "
        f"rediscovery is needed.\n\nResume vocabulary fields: {resume.render_public_field_list()}."
    )


def render_recovery_note(context: PublicSurfaceRenderContext | None = None) -> str:
    """Render the explicit reference form with raw resume vocabulary."""

    return render_recovery_reference_note(context)


def render_supported_runtime_table(context: PublicSurfaceRenderContext | None = None) -> str:
    ctx = _context(context)
    return _render_markdown_table(
        ("Runtime", "`npx` flag", "Help", "Start", "Tour", "New work", "Existing work", "Return later"),
        tuple(
            (
                surface.display_name,
                _code(surface.install_flag),
                _code(surface.help_command),
                _code(surface.start_command),
                _code(surface.tour_command),
                _code(surface.new_project_minimal_command),
                _code(surface.map_research_command),
                _code(surface.resume_work_command),
            )
            for surface in ctx.runtime_surfaces
        ),
    )


def render_os_install_matrix(context: PublicSurfaceRenderContext | None = None) -> str:
    ctx = _context(context)
    return _render_markdown_table(
        ("Runtime", "Install command"),
        tuple(
            (
                surface.display_name,
                _code(_install_command(surface, bootstrap_command=ctx.bootstrap_command)),
            )
            for surface in ctx.runtime_surfaces
        ),
    )


def _next_step_actions() -> tuple[_NextStepAction, ...]:
    return (
        _NextStepAction("Not sure which path fits this folder", lambda surface, _contract: surface.start_command),
        _NextStepAction("Want a guided overview", lambda surface, _contract: surface.tour_command),
        _NextStepAction("Start a new project", lambda surface, _contract: surface.new_project_minimal_command),
        _NextStepAction("Map an existing folder", lambda surface, _contract: surface.map_research_command),
        _NextStepAction(
            "Rediscover the workspace in your normal terminal",
            lambda _surface, contract: contract.recovery_ladder.local_snapshot_command,
        ),
        _NextStepAction("Continue in the reopened runtime", lambda surface, _contract: surface.resume_work_command),
    )


def _runtime_command_groups(
    surfaces: Sequence[BeginnerRuntimeSurface],
    *,
    contract: PublicSurfaceContract,
    actions: Sequence[_NextStepAction],
) -> tuple[_RuntimeCommandGroup, ...]:
    groups: list[_RuntimeCommandGroup] = []
    group_indexes: dict[tuple[str, ...], int] = {}
    for surface in surfaces:
        commands = tuple(action.command(surface, contract) for action in actions)
        group_index = group_indexes.get(commands)
        if group_index is None:
            group_indexes[commands] = len(groups)
            groups.append(_RuntimeCommandGroup(display_names=(surface.display_name,), commands=commands))
            continue
        group = groups[group_index]
        groups[group_index] = _RuntimeCommandGroup(
            display_names=(*group.display_names, surface.display_name),
            commands=group.commands,
        )
    return tuple(groups)


def render_os_next_step_table(context: PublicSurfaceRenderContext | None = None) -> str:
    ctx = _context(context)
    actions = _next_step_actions()
    command_groups = _runtime_command_groups(ctx.runtime_surfaces, contract=ctx.contract, actions=actions)
    headers = ("What you want to do", *(" / ".join(group.display_names) for group in command_groups))
    rows = tuple(
        (action.label, *(_code(group.commands[action_index]) for group in command_groups))
        for action_index, action in enumerate(actions)
    )
    return _render_markdown_table(headers, rows)


def runtime_doc_filename(surface: BeginnerRuntimeSurface) -> str:
    return f"{_slugify(surface.display_name)}.md"


def render_runtime_doc_links(context: PublicSurfaceRenderContext | None = None) -> str:
    return _render_bullets(
        f"[{surface.display_name} quickstart](./{runtime_doc_filename(surface)})"
        for surface in _context(context).runtime_surfaces
    )


def _settings_note_for_runtime(surface: BeginnerRuntimeSurface, *, contract: PublicSurfaceContract) -> str:
    primary = contract.post_start_settings.primary_sentence.replace(
        "the runtime `settings` command",
        _code(surface.settings_command),
    )
    return f"{primary} {contract.post_start_settings.default_sentence}"


def _surface_by_runtime_name(
    runtime_name: str,
    *,
    context: PublicSurfaceRenderContext,
) -> BeginnerRuntimeSurface:
    for surface in context.runtime_surfaces:
        if surface.runtime_name == runtime_name:
            return surface
    return beginner_runtime_surface(runtime_name)


def render_runtime_quickstart_snippet(
    runtime_name: str,
    context: PublicSurfaceRenderContext | None = None,
) -> str:
    ctx = _context(context)
    surface = _surface_by_runtime_name(runtime_name, context=ctx)
    install_command = _install_command(surface, bootstrap_command=ctx.bootstrap_command)
    command_block = "\n".join(
        (
            surface.help_command,
            surface.start_command,
            surface.tour_command,
            surface.new_project_minimal_command,
            surface.map_research_command,
            surface.resume_work_command,
        )
    )
    return "\n\n".join(
        (
            "From your normal terminal:",
            f"```bash\n{install_command}\n{surface.launch_command}\n```",
            f"Inside {surface.display_name}:",
            f"```text\n{command_block}\n```",
            "Suggested order for beginners: "
            f"{_code(surface.help_command)}, {_code(surface.start_command)}, {_code(surface.tour_command)}, then "
            f"either {_code(surface.new_project_minimal_command)}, {_code(surface.map_research_command)}, or "
            f"{_code(surface.resume_work_command)}.",
            "Return to work from your normal terminal with "
            f"{_code(ctx.contract.recovery_ladder.local_snapshot_command)} or "
            f"{_code(ctx.contract.recovery_ladder.cross_workspace_command)}, then reopen "
            f"{_code(surface.launch_command)} in the right folder and run {_code(surface.resume_work_command)}.",
            _settings_note_for_runtime(surface, contract=ctx.contract),
        )
    )


def render_runtime_quickstart_snippets(
    context: PublicSurfaceRenderContext | None = None,
) -> dict[str, str]:
    ctx = _context(context)
    return {
        surface.runtime_name: render_runtime_quickstart_snippet(surface.runtime_name, context=ctx)
        for surface in ctx.runtime_surfaces
    }


def runtime_quickstart_block_id(surface: BeginnerRuntimeSurface) -> str:
    return f"{_RUNTIME_QUICKSTART_BLOCK_PREFIX}{surface.runtime_name}"


def _static_public_surface_block_renderers() -> dict[str, Callable[[PublicSurfaceRenderContext], str]]:
    return {
        "beginner-startup-ladder": render_startup_ladder,
        "beginner-preflight": render_beginner_preflight_list,
        "beginner-caveats": render_beginner_caveat_list,
        "terminal-runtime-bridge": render_terminal_runtime_bridge_text,
        "local-cli-bridge-summary": render_local_cli_bridge_summary,
        "post-start-settings": render_post_start_settings_note,
        "recovery-note": render_default_recovery_note,
        "recovery-reference-note": render_recovery_reference_note,
        "supported-runtimes-table": render_supported_runtime_table,
        "os-install-matrix": render_os_install_matrix,
        "os-next-steps-table": render_os_next_step_table,
        "runtime-doc-links": render_runtime_doc_links,
    }


def _public_surface_block_renderers(
    context: PublicSurfaceRenderContext | None = None,
) -> dict[str, Callable[[PublicSurfaceRenderContext], str]]:
    ctx = _context(context)
    renderers = _static_public_surface_block_renderers()
    for surface in ctx.runtime_surfaces:
        runtime_name = surface.runtime_name
        renderers[runtime_quickstart_block_id(surface)] = lambda render_context, runtime_name=runtime_name: (
            render_runtime_quickstart_snippet(
                runtime_name,
                context=render_context,
            )
        )
    return renderers


def public_surface_block_ids(context: PublicSurfaceRenderContext | None = None) -> tuple[str, ...]:
    return tuple(_public_surface_block_renderers(context))


def render_public_surface_block(
    block_id: str,
    context: PublicSurfaceRenderContext | None = None,
) -> str:
    ctx = _context(context)
    renderers = _public_surface_block_renderers(ctx)
    try:
        renderer = renderers[block_id]
    except KeyError as exc:
        known = ", ".join(sorted(renderers))
        raise KeyError(f"Unknown public surface block {block_id!r}. Known blocks: {known}") from exc
    return renderer(ctx)
