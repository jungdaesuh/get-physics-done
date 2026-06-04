"""Install presentation helpers that do not depend on Typer command globals."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from gpd.core.onboarding_surfaces import beginner_onboarding_hub_url
from gpd.core.public_surface_contract import local_cli_help_command
from gpd.core.runtime_targeting import format_target_for_display

GPD_BANNER = r"""
 ██████╗ ██████╗ ██████╗
██╔════╝ ██╔══██╗██╔══██╗
██║  ███╗██████╔╝██║  ██║
██║   ██║██╔═══╝ ██║  ██║
╚██████╔╝██║     ██████╔╝
 ╚═════╝ ╚═╝     ╚═════╝
"""

GPD_DISPLAY_NAME = "Get Physics Done"
GPD_OWNER = "Physical Superintelligence PBC"
GPD_OWNER_SHORT = "PSI"
GPD_COPYRIGHT_YEAR = 2026
INSTALL_LOGO_COLOR = "#F3F0E8"
INSTALL_TITLE_COLOR = "#F7F4ED"
INSTALL_META_COLOR = "#9E988C"
INSTALL_ACCENT_COLOR = "#D8C7A3"


class InstallSelectionError(ValueError):
    """Raised when an interactive install choice cannot be resolved."""


def format_install_header_lines(version: str) -> tuple[str, str]:
    """Return the branded header shown during interactive install."""

    return (
        f"GPD v{version} - {GPD_DISPLAY_NAME}",
        f"© {GPD_COPYRIGHT_YEAR} {GPD_OWNER} ({GPD_OWNER_SHORT})",
    )


def print_install_header(version: str, *, console: Console) -> None:
    """Render the branded install banner for human-facing install flows."""

    console.print(GPD_BANNER, style=f"bold {INSTALL_LOGO_COLOR}")
    console.print()
    header_line, attribution_line = format_install_header_lines(version)
    console.print(header_line, style=f"bold {INSTALL_TITLE_COLOR}", markup=False, highlight=False)
    console.print(attribution_line, style=f"dim {INSTALL_META_COLOR}", markup=False, highlight=False)
    console.print()


def render_install_option_line(index: int, label: str, *details: str, label_width: int | None = None) -> Text:
    """Return a single-line formatted install menu option."""

    rendered = Text("  ")
    rendered.append(f"[{index}]", style=f"bold {INSTALL_ACCENT_COLOR}")
    rendered.append(" ")
    rendered.append(label.ljust(label_width or len(label)), style=f"bold {INSTALL_TITLE_COLOR}")
    filtered_details = [detail for detail in details if detail]
    if filtered_details:
        rendered.append("  ")
        for detail_index, detail in enumerate(filtered_details):
            if detail_index:
                rendered.append(" ")
            rendered.append("·", style=f"bold {INSTALL_ACCENT_COLOR}")
            rendered.append(" ")
            rendered.append(detail, style=f"dim {INSTALL_META_COLOR}")
    return rendered


def render_install_choice_prompt() -> Text:
    """Return the shared interactive prompt label for install menus."""

    rendered = Text()
    rendered.append("Enter choice", style=f"bold {INSTALL_TITLE_COLOR}")
    rendered.append(" [1]", style=f"dim {INSTALL_META_COLOR}")
    return rendered


def resolve_runtime_choice(
    choice: str,
    *,
    runtime_names: Sequence[str],
    adapter_lookup: Callable[[str], object],
    normalize_runtime_name: Callable[[str | None], str | None],
) -> list[str]:
    """Resolve a runtime menu response into canonical runtime names."""

    adapters = {runtime: adapter_lookup(runtime) for runtime in runtime_names}
    try:
        idx = int(choice)
    except ValueError:
        canonical_runtime = normalize_runtime_name(choice)
        if canonical_runtime in adapters:
            return [canonical_runtime]

        normalized = choice.strip().casefold()
        exact_matches = [
            runtime_name
            for runtime_name, adapter in adapters.items()
            if normalized
            in {
                runtime_name.casefold(),
                str(getattr(adapter, "display_name", "")).casefold(),
                *(str(alias).casefold() for alias in getattr(adapter, "selection_aliases", ())),
            }
        ]
        if len(exact_matches) == 1:
            return exact_matches

        fuzzy_matches = [
            runtime_name
            for runtime_name, adapter in adapters.items()
            if normalized
            and any(
                normalized in candidate
                for candidate in (
                    runtime_name.casefold(),
                    str(getattr(adapter, "display_name", "")).casefold(),
                    *(str(alias).casefold() for alias in getattr(adapter, "selection_aliases", ())),
                )
            )
        ]
        if len(fuzzy_matches) == 1:
            return fuzzy_matches
        if len(fuzzy_matches) > 1:
            raise InstallSelectionError(
                f"Ambiguous selection: {choice!r}. Matches: {', '.join(fuzzy_matches)}"
            ) from None
        raise InstallSelectionError(f"Invalid selection: {choice!r}") from None

    if idx == len(runtime_names) + 1:
        return list(runtime_names)
    if 1 <= idx <= len(runtime_names):
        return [runtime_names[idx - 1]]
    raise InstallSelectionError(f"Invalid selection: {idx}")


def prompt_runtimes(
    *,
    action: str,
    runtime_names: Sequence[str],
    adapter_lookup: Callable[[str], object],
    normalize_runtime_name: Callable[[str | None], str | None],
    console: Console,
    prompt_ask: Callable[..., str],
) -> list[str]:
    """Render the runtime menu and resolve the selected runtime names."""

    adapters = {runtime: adapter_lookup(runtime) for runtime in runtime_names}
    label_width = max(len(str(getattr(adapter, "display_name", ""))) for adapter in adapters.values())
    all_label = "All runtimes"
    label_width = max(label_width, len(all_label))
    console.print(f"\n[bold {INSTALL_TITLE_COLOR}]Select runtime(s) to {action}[/]\n")
    for i, runtime_name in enumerate(runtime_names, 1):
        adapter = adapters[runtime_name]
        console.print(
            render_install_option_line(
                i,
                str(getattr(adapter, "display_name", runtime_name)),
                runtime_name,
                label_width=label_width,
            )
        )
    console.print(render_install_option_line(len(runtime_names) + 1, all_label, label_width=label_width))
    console.print()
    choice = prompt_ask(render_install_choice_prompt(), default="1", show_default=False)
    return resolve_runtime_choice(
        str(choice),
        runtime_names=runtime_names,
        adapter_lookup=adapter_lookup,
        normalize_runtime_name=normalize_runtime_name,
    )


def location_example(
    runtimes: Sequence[str],
    *,
    is_global: bool,
    action: str,
    cwd: Path,
    adapter_lookup: Callable[[str], object],
) -> str:
    """Return a representative install location example for the selected runtime set."""

    if len(runtimes) != 1:
        return "one config dir per runtime"

    adapter = adapter_lookup(runtimes[0])
    target = adapter.resolve_target_dir(is_global, cwd)
    return format_target_for_display(target, cwd=cwd)


def prompt_location(
    runtimes: Sequence[str],
    *,
    action: str,
    cwd: Path,
    adapter_lookup: Callable[[str], object],
    console: Console,
    prompt_ask: Callable[..., str],
) -> bool:
    """Render the location menu and return True for global, False for local."""

    label = "Install" if action == "install" else "Uninstall"
    local_example = location_example(
        runtimes,
        is_global=False,
        action=action,
        cwd=cwd,
        adapter_lookup=adapter_lookup,
    )
    global_example = location_example(
        runtimes,
        is_global=True,
        action=action,
        cwd=cwd,
        adapter_lookup=adapter_lookup,
    )
    label_width = max(len("Local"), len("Global"))
    console.print(f"\n[bold {INSTALL_TITLE_COLOR}]{label} location[/]\n")
    console.print(
        render_install_option_line(1, "Local", "current project only", local_example, label_width=label_width)
    )
    console.print(render_install_option_line(2, "Global", "all projects", global_example, label_width=label_width))
    console.print()

    choice = str(prompt_ask(render_install_choice_prompt(), default="1", show_default=False))
    normalized = choice.strip().lower()
    if normalized in {"1", "local"}:
        return False
    if normalized in {"2", "global"}:
        return True
    raise InstallSelectionError(f"Invalid selection: {choice!r}")


def install_summary_local_cli_bridge_line(*, help_command: str | None = None) -> str:
    """Return the concise local-CLI bridge follow-up for install summaries."""

    command = help_command or local_cli_help_command()
    return f"Diagnostics: use [bold]{command}[/] for local diagnostics and later setup."


def print_install_summary(
    results: Sequence[tuple[str, dict[str, object]]],
    *,
    cwd: Path,
    console: Console,
    adapter_lookup: Callable[[str], object],
    include_next_steps: bool = True,
    docs_hub_url: str | None = None,
    diagnostics_line: str | None = None,
) -> None:
    """Print a rich summary table of install results."""

    console.print()
    table = Table(
        title="Install Summary",
        title_style=f"italic {INSTALL_ACCENT_COLOR}",
        show_header=True,
        header_style=f"bold {INSTALL_ACCENT_COLOR}",
    )
    table.add_column("Runtime", style="bold")
    table.add_column("Target")
    table.add_column("Status")

    for runtime_name, result in results:
        adapter = adapter_lookup(runtime_name)
        target = format_target_for_display(result.get("target"), cwd=cwd)
        agents = result.get("agents", 0)
        commands = result.get("commands", 0)
        table.add_row(
            str(getattr(adapter, "display_name", runtime_name)),
            target,
            f"[green]✓[/] {agents} agents, {commands} commands",
        )

    console.print(table)

    if results and include_next_steps:
        next_step_entries: list[tuple[str, str]] = []
        seen_runtime_names: set[str] = set()
        for runtime_name, _result in results:
            if runtime_name in seen_runtime_names:
                continue
            seen_runtime_names.add(runtime_name)
            adapter = adapter_lookup(runtime_name)
            next_step_entries.append(
                (
                    str(getattr(adapter, "display_name", runtime_name)),
                    adapter.format_command("start"),
                )
            )

        console.print()
        console.print("[bold]After install[/]")
        console.print(f"Docs hub: {docs_hub_url or beginner_onboarding_hub_url()}", soft_wrap=True)
        if len(next_step_entries) == 1:
            display_name, start_command = next_step_entries[0]
            console.print(
                f"Next: open {display_name} in this folder, then run [{INSTALL_ACCENT_COLOR} bold]{start_command}[/].",
                soft_wrap=True,
            )
        else:
            console.print("Next: choose a runtime and run its GPD start command:", soft_wrap=True)
            for display_name, start_command in next_step_entries:
                console.print(f"- {display_name}: [{INSTALL_ACCENT_COLOR} bold]{start_command}[/]", soft_wrap=True)
        console.print(diagnostics_line or install_summary_local_cli_bridge_line(), soft_wrap=True)
        console.print()
