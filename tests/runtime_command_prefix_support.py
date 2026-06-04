"""Shared assertions for runtime-specific public command labels."""

from __future__ import annotations

from collections.abc import Sequence

from gpd.adapters.runtime_catalog import get_runtime_descriptor
from gpd.core.onboarding_surfaces import BeginnerRuntimeSurface, beginner_runtime_surfaces


def beginner_runtime_quickstart_labels(surface: BeginnerRuntimeSurface) -> tuple[str, ...]:
    """Return labels expected in the selected runtime's beginner quickstart."""

    return (
        surface.help_command,
        surface.start_command,
        surface.tour_command,
        surface.new_project_minimal_command,
        surface.map_research_command,
        surface.resume_work_command,
        surface.settings_command,
    )


def beginner_runtime_command_labels(surface: BeginnerRuntimeSurface) -> tuple[str, ...]:
    """Return beginner labels whose prefixes must not leak across runtime families."""

    return (
        surface.help_command,
        surface.start_command,
        surface.tour_command,
        surface.new_project_command,
        surface.new_project_minimal_command,
        surface.map_research_command,
        surface.resume_work_command,
        surface.settings_command,
    )


def runtime_public_command_prefix(surface: BeginnerRuntimeSurface) -> str:
    return get_runtime_descriptor(surface.runtime_name).public_command_surface_prefix


def incompatible_beginner_command_labels(
    surface: BeginnerRuntimeSurface,
    *,
    surfaces: Sequence[BeginnerRuntimeSurface] | None = None,
) -> tuple[str, ...]:
    """Return beginner labels from incompatible public-prefix families."""

    active_prefix = runtime_public_command_prefix(surface)
    peers = tuple(surfaces) if surfaces is not None else beginner_runtime_surfaces()
    labels: list[str] = []
    for other in peers:
        if runtime_public_command_prefix(other) == active_prefix:
            continue
        labels.extend(beginner_runtime_command_labels(other))
    return tuple(dict.fromkeys(labels))


def assert_no_incompatible_beginner_command_labels(
    text: str,
    surface: BeginnerRuntimeSurface,
    *,
    context: str,
    surfaces: Sequence[BeginnerRuntimeSurface] | None = None,
) -> None:
    leaked = [
        label
        for label in incompatible_beginner_command_labels(surface, surfaces=surfaces)
        if label in text
    ]
    assert not leaked, f"{context} leaked incompatible runtime command labels: {leaked!r}"
