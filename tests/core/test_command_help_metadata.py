"""Focused tests for command-owned help metadata parsing."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from textwrap import dedent

import pytest

from gpd import registry
from gpd.adapters.install_utils import strip_display_only_command_help_frontmatter
from gpd.registry import (
    CommandHelpMetadata,
    CommandHelpVariant,
    _parse_command_file,
    render_command_visibility_sections_from_frontmatter,
)


def _parse_sample_command(tmp_path: Path, help_yaml: str | None = None) -> registry.CommandDef:
    path = tmp_path / "sample.md"
    help_block = ""
    if help_yaml is not None:
        help_block = dedent(help_yaml).strip("\n") + "\n"
    path.write_text(
        "---\n"
        "name: gpd:sample\n"
        "description: Sample command\n"
        'argument-hint: "[target]"\n'
        f"{help_block}"
        "---\n"
        "Command body.",
        encoding="utf-8",
    )
    return _parse_command_file(path, source="commands")


def test_command_help_metadata_parses_to_frozen_typed_objects(tmp_path: Path) -> None:
    command = _parse_sample_command(
        tmp_path,
        """
        help:
          group: Starter commands
          order: 10
          compact_description: Show the compact row
          display_signature: gpd:sample [target]
          detail_signature: gpd:sample [target]
          examples:
            - gpd:sample example
          notes:
            - Use `gpd:sample` for samples.
          root_detail_order: 20
          variants:
            - command: gpd:sample --minimal
              description: Use the short path
              examples:
                - gpd:sample --minimal @brief.md
              notes:
                - Variant note.
        """,
    )

    assert command.help == CommandHelpMetadata(
        group="Starter commands",
        order=10,
        compact_description="Show the compact row",
        display_signature="gpd:sample [target]",
        detail_signature="gpd:sample [target]",
        examples=("gpd:sample example",),
        notes=("Use `gpd:sample` for samples.",),
        root_detail_order=20,
        variants=(
            CommandHelpVariant(
                command="gpd:sample --minimal",
                description="Use the short path",
                examples=("gpd:sample --minimal @brief.md",),
                notes=("Variant note.",),
            ),
        ),
    )
    assert isinstance(command.help, CommandHelpMetadata)
    assert isinstance(command.help.variants[0], CommandHelpVariant)
    with pytest.raises((AttributeError, FrozenInstanceError)):
        command.help.group = "Other"  # type: ignore[misc]


def test_command_without_help_metadata_remains_backwards_compatible(tmp_path: Path) -> None:
    command = _parse_sample_command(tmp_path)

    assert command.help is None
    assert command.content.endswith("Command body.")


def test_help_metadata_does_not_render_into_model_visible_command_content(tmp_path: Path) -> None:
    command = _parse_sample_command(
        tmp_path,
        """
        help:
          group: Starter commands
          order: 10
          compact_description: This belongs only to help metadata
        """,
    )

    assert command.help is not None
    assert "This belongs only to help metadata" not in command.content
    assert command.content.endswith("Command body.")


def test_command_visibility_frontmatter_helper_accepts_but_omits_help_metadata() -> None:
    rendered = render_command_visibility_sections_from_frontmatter(
        dedent(
            """
            name: gpd:sample
            context_mode: project-aware
            help:
              group: Starter commands
              order: 10
              compact_description: This is display-only
            """
        ),
        command_name="gpd:sample",
    )

    assert "context_mode: project-aware" in rendered
    assert "This is display-only" not in rendered


def test_display_only_help_frontmatter_is_stripped_from_runtime_markdown() -> None:
    source = dedent(
        """
        ---
        name: gpd:sample
        description: Sample command
        allowed-tools:
          - file_read
        help:
          group: Starter commands
          order: 10
          compact_description: This belongs only to help metadata
        ---
        Command body.
        """
    ).lstrip()

    stripped = strip_display_only_command_help_frontmatter(source)

    assert "help:" not in stripped
    assert "This belongs only to help metadata" not in stripped
    assert "allowed-tools:" in stripped
    assert "Command body." in stripped


@pytest.mark.parametrize(
    ("help_yaml", "match"),
    [
        ("help: not-a-mapping", r"help for gpd:sample must be a mapping"),
        (
            """
            help:
              group: Starter commands
              order: 1
              unexpected: true
            """,
            r"help for gpd:sample has unknown keys: unexpected",
        ),
        (
            """
            help:
              order: 1
            """,
            r"help\.group for gpd:sample must be a non-empty string",
        ),
        (
            """
            help:
              group: 12
              order: 1
            """,
            r"help\.group for gpd:sample must be a string",
        ),
        (
            """
            help:
              group: Starter commands
            """,
            r"help\.order for gpd:sample must be an integer",
        ),
        (
            """
            help:
              group: Starter commands
              order: true
            """,
            r"help\.order for gpd:sample must be an integer",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              compact_description: 7
            """,
            r"help\.compact_description for gpd:sample must be a string",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              root_detail_order: soon
            """,
            r"help\.root_detail_order for gpd:sample must be an integer",
        ),
    ],
)
def test_help_metadata_rejects_bad_mapping_and_scalar_shapes(
    tmp_path: Path,
    help_yaml: str,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _parse_sample_command(tmp_path, help_yaml)


@pytest.mark.parametrize(
    ("help_yaml", "match"),
    [
        (
            """
            help:
              group: Starter commands
              order: 1
              examples: gpd:sample
            """,
            r"help\.examples for gpd:sample must be a list of strings",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              examples:
                - gpd:sample
                - 7
            """,
            r"help\.examples for gpd:sample must contain only strings",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              notes:
                - First note
                - ""
            """,
            r"help\.notes for gpd:sample must not contain blank entries",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              examples:
                - gpd:sample
                - gpd:sample
            """,
            r"help\.examples for gpd:sample must not contain duplicate entries: 'gpd:sample'",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              notes:
                - Repeated note
                - Repeated note
            """,
            r"help\.notes for gpd:sample must not contain duplicate entries: 'Repeated note'",
        ),
    ],
)
def test_help_metadata_rejects_bad_examples_and_notes(
    tmp_path: Path,
    help_yaml: str,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _parse_sample_command(tmp_path, help_yaml)


@pytest.mark.parametrize(
    ("help_yaml", "match"),
    [
        (
            """
            help:
              group: Starter commands
              order: 1
              variants: gpd:sample --minimal
            """,
            r"help\.variants for gpd:sample must be a list of mappings",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              variants:
                - gpd:sample --minimal
            """,
            r"help\.variants\[0\] for gpd:sample must be a mapping",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              variants:
                - command: gpd:sample --minimal
                  description: Short path
                  extra: nope
            """,
            r"help\.variants\[0\] for gpd:sample has unknown keys: extra",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              variants:
                - description: Short path
            """,
            r"help\.variants\[0\]\.command for gpd:sample must be a non-empty string",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              variants:
                - command: gpd:sample --minimal
            """,
            r"help\.variants\[0\]\.description for gpd:sample must be a non-empty string",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              variants:
                - command: gpd:other --minimal
                  description: Wrong base
            """,
            r"help\.variants\[0\]\.command for gpd:sample must normalize to gpd:sample; got gpd:other",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              variants:
                - command: gpd:sample --minimal
                  description: Short path
                - command: gpd:sample --minimal
                  description: Short path again
            """,
            r"help\.variants for gpd:sample must not contain duplicate commands: 'gpd:sample --minimal'",
        ),
    ],
)
def test_help_metadata_rejects_bad_variant_shapes(
    tmp_path: Path,
    help_yaml: str,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _parse_sample_command(tmp_path, help_yaml)


@pytest.mark.parametrize(
    ("help_yaml", "match"),
    [
        (
            """
            help:
              group: Starter commands
              order: 1
              display_signature: /gpd:sample
            """,
            r"help\.display_signature for gpd:sample must use canonical gpd: labels; "
            r"got runtime-specific label '/gpd:sample'",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              examples:
                - $gpd-sample --minimal
            """,
            r"help\.examples for gpd:sample must use canonical gpd: labels; "
            r"got runtime-specific label '\$gpd-sample'",
        ),
        (
            """
            help:
              group: Starter commands
              order: 1
              variants:
                - command: $gpd-sample --minimal
                  description: Runtime label
            """,
            r"help\.variants\[0\]\.command for gpd:sample must use canonical gpd: labels; "
            r"got runtime-specific label '\$gpd-sample'",
        ),
    ],
)
def test_help_metadata_rejects_runtime_specific_command_labels(
    tmp_path: Path,
    help_yaml: str,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _parse_sample_command(tmp_path, help_yaml)
