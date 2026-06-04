"""Tests for the registry-backed help renderer."""

from __future__ import annotations

import re
from collections import Counter

import pytest

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.command_labels import CANONICAL_COMMAND_PREFIX, runtime_public_command_prefixes
from gpd.core import help_renderer
from gpd.core.public_surface_contract import (
    beginner_startup_ladder,
    beginner_startup_ladder_text,
    local_cli_cost_command,
    local_cli_observe_execution_command,
    local_cli_resume_command,
    local_cli_resume_recent_command,
)
from gpd.registry import CommandDef, CommandHelpMetadata, CommandHelpVariant, list_commands

_COMMAND_ROW_RE = re.compile(r"^- `([^`]+)` - (.+)$", re.MULTILINE)
_NUMBERED_COMMAND_ROW_RE = re.compile(r"^\d+\. `([^`]+)` - (.+)$", re.MULTILINE)


def _command_rows(markdown: str) -> dict[str, str]:
    rows = _COMMAND_ROW_RE.findall(markdown)
    assert len(rows) == len({command for command, _description in rows})
    return dict(rows)


def _numbered_command_rows(markdown: str) -> list[tuple[str, str]]:
    return _NUMBERED_COMMAND_ROW_RE.findall(markdown)


def _assert_in_order(text: str, fragments: tuple[str, ...]) -> None:
    positions = [text.index(fragment) for fragment in fragments]
    assert positions == sorted(positions)


def _assert_contains_all(text: str, fragments: tuple[str, ...]) -> None:
    for fragment in fragments:
        assert fragment in text


def _assert_contains_none(text: str, fragments: tuple[str, ...]) -> None:
    for fragment in fragments:
        assert fragment not in text


def _runtime_ladder_commands() -> tuple[str, ...]:
    return tuple(
        f"gpd:{part.strip()}" for step in beginner_startup_ladder() for part in step.split("/") if part.strip()
    )


def _descriptor_with_public_prefix_kind(kind: str):
    return next(
        descriptor
        for descriptor in iter_runtime_descriptors()
        if descriptor.validated_command_surface == f"public_runtime_{kind}_command"
    )


def _fake_command(
    slug: str,
    *,
    description: str,
    help_metadata: CommandHelpMetadata | None,
    argument_hint: str = "",
    context_mode: str = "projectless",
) -> CommandDef:
    return CommandDef(
        name=f"gpd:{slug}",
        description=description,
        argument_hint=argument_hint,
        requires={},
        allowed_tools=[],
        content=f"{slug} body",
        path=f"/fake/{slug}.md",
        source="commands",
        context_mode=context_mode,
        help=help_metadata,
    )


def _fake_registry_label(command_name: str) -> str:
    head = command_name.strip().split()[0]
    for prefix in runtime_public_command_prefixes():
        if prefix != CANONICAL_COMMAND_PREFIX and head.startswith(prefix):
            return f"{CANONICAL_COMMAND_PREFIX}{head.removeprefix(prefix)}"
    if head.startswith(CANONICAL_COMMAND_PREFIX):
        return head
    return f"{CANONICAL_COMMAND_PREFIX}{head}"


@pytest.fixture
def fake_help_registry(monkeypatch: pytest.MonkeyPatch):
    commands_by_label: dict[str, CommandDef] = {}

    def install(*commands: CommandDef) -> None:
        commands_by_label.clear()
        commands_by_label.update({command.name: command for command in commands})

        def fake_list_commands(*, name_format: str = "slug") -> list[str]:
            if name_format == "label":
                return sorted(commands_by_label)
            if name_format == "slug":
                return sorted(label.removeprefix("gpd:") for label in commands_by_label)
            raise ValueError("name_format must be 'slug' or 'label'")

        def fake_get_command(command_name: str) -> CommandDef:
            label = _fake_registry_label(command_name)
            try:
                return commands_by_label[label]
            except KeyError as exc:
                raise KeyError(f"Command not found: {command_name}") from exc

        monkeypatch.setattr(help_renderer, "list_commands", fake_list_commands)
        monkeypatch.setattr(help_renderer, "get_command", fake_get_command)
        help_renderer.help_command_groups.cache_clear()
        help_renderer._root_detailed_reference_commands.cache_clear()

    yield install

    help_renderer.help_command_groups.cache_clear()
    help_renderer._root_detailed_reference_commands.cache_clear()


def test_help_renderer_renders_quick_start_structure_without_freezing_marker_body() -> None:
    quick_start = help_renderer.render_quick_start_markdown()

    assert quick_start.startswith("## Quick Start")
    assert beginner_startup_ladder_text() in quick_start
    for section_heading in ("**New work**", "**Existing work**", "**Returning work**", "**Post-startup settings**"):
        assert section_heading in quick_start

    _assert_in_order(
        quick_start,
        tuple(f"`{command}`" for command in _runtime_ladder_commands()),
    )

    rows = _numbered_command_rows(quick_start)
    commands = {command for command, _description in rows}
    expected_rows = set(_runtime_ladder_commands()[1:])
    expected_rows.update(
        {
            "gpd:new-project --minimal",
            "gpd:progress",
            "gpd:suggest-next",
            "gpd:settings",
            "gpd:set-tier-models",
            local_cli_resume_command(),
            local_cli_resume_recent_command(),
            local_cli_observe_execution_command(),
            local_cli_cost_command(),
        }
    )
    assert expected_rows <= commands
    assert all(description.strip() for _command, description in rows)


def test_help_renderer_renders_default_help_as_short_three_choice_chooser() -> None:
    default_help = help_renderer.render_default_help_markdown()

    assert default_help.startswith("## Quick Start")
    assert len(default_help.splitlines()) <= 45
    assert len(default_help) <= 3_500
    for section_heading in ("**New folder**", "**Existing research folder**", "**Returning project**"):
        assert section_heading in default_help

    rows = _numbered_command_rows(default_help)
    commands = {command for command, _description in rows}
    assert commands == {
        "gpd:start",
        "gpd:new-project",
        "gpd:new-project --minimal",
        "gpd:map-research",
        local_cli_resume_command(),
        local_cli_resume_recent_command(),
        "gpd:resume-work",
    }
    assert all(description.strip() for _command, description in rows)
    _assert_contains_none(
        default_help,
        (
            "`gpd:tour`",
            "`gpd:progress`",
            "`gpd:suggest-next`",
            "`gpd:settings`",
            "`gpd:set-tier-models`",
            "`gpd:tangent`",
            "`gpd:branch-hypothesis`",
            f"`{local_cli_observe_execution_command()}`",
            f"`{local_cli_cost_command()}`",
        ),
    )


def test_help_renderer_default_help_rewrites_runtime_commands_for_public_prefix() -> None:
    public_prefix = _descriptor_with_public_prefix_kind("dollar").public_command_surface_prefix
    default_help = help_renderer.render_default_help_markdown(public_prefix=public_prefix)

    _assert_contains_all(
        default_help,
        (
            f"`{public_prefix}start`",
            f"`{public_prefix}new-project`",
            f"`{public_prefix}new-project --minimal`",
            f"`{public_prefix}map-research`",
            f"`{public_prefix}resume-work`",
            f"`{local_cli_resume_command()}`",
            f"`{local_cli_resume_recent_command()}`",
        ),
    )
    _assert_contains_none(default_help, ("`gpd:start`", "`gpd:resume-work`", f"`{public_prefix}progress`"))


def test_help_renderer_quick_start_rewrites_runtime_commands_for_public_prefix() -> None:
    public_prefix = _descriptor_with_public_prefix_kind("dollar").public_command_surface_prefix
    quick_start = help_renderer.render_quick_start_markdown(public_prefix=public_prefix)

    _assert_contains_all(
        quick_start,
        (
            f"`{public_prefix}help`",
            f"`{public_prefix}start`",
            f"`{public_prefix}tour`",
            f"`{public_prefix}new-project --minimal`",
            f"`{public_prefix}progress`",
            f"`{public_prefix}suggest-next`",
            f"`{local_cli_resume_command()}`",
            f"`{local_cli_resume_recent_command()}`",
            f"`{local_cli_observe_execution_command()}`",
            f"`{local_cli_cost_command()}`",
        ),
    )
    _assert_contains_none(quick_start, ("`gpd:start`", "`gpd:progress`"))


def test_help_command_groups_follow_command_owned_metadata(fake_help_registry) -> None:
    fake_help_registry(
        _fake_command(
            "alpha",
            description="Fallback alpha description",
            argument_hint="[target]",
            help_metadata=CommandHelpMetadata(
                group="Synthetic later group",
                order=20,
                compact_description="Alpha compact row from metadata",
                display_signature="gpd:alpha [metadata-target]",
                variants=(
                    CommandHelpVariant(
                        command="gpd:alpha --brief",
                        description="Alpha documented variant from metadata",
                    ),
                ),
            ),
        ),
        _fake_command(
            "beta",
            description="Beta registry description fallback",
            help_metadata=CommandHelpMetadata(group="Synthetic first group", order=10),
        ),
    )

    groups = help_renderer.help_command_groups()

    assert [group.name for group in groups] == ["Synthetic first group", "Synthetic later group"]
    assert [
        (entry.command, entry.description, entry.registry_command, entry.documented_variant)
        for entry in groups[0].commands
    ] == [("gpd:beta", "Beta registry description fallback", "gpd:beta", False)]
    assert [
        (entry.command, entry.description, entry.registry_command, entry.documented_variant)
        for entry in groups[1].commands
    ] == [
        ("gpd:alpha [metadata-target]", "Alpha compact row from metadata", "gpd:alpha", False),
        ("gpd:alpha --brief", "Alpha documented variant from metadata", "gpd:alpha", True),
    ]

    command_index = help_renderer.render_command_index_markdown()
    _assert_in_order(command_index, ("### Synthetic first group", "### Synthetic later group"))
    _assert_contains_all(
        command_index,
        (
            "- `gpd:alpha [metadata-target]` - Alpha compact row from metadata",
            "- `gpd:alpha --brief` - Alpha documented variant from metadata",
        ),
    )


def test_help_renderer_renders_command_index_from_registry_backed_groups() -> None:
    command_index = help_renderer.render_command_index_markdown()

    assert command_index.startswith("## Command Index")
    rows = _command_rows(command_index)
    expected_commands = {entry.command for group in help_renderer.help_command_groups() for entry in group.commands}
    assert set(rows) == expected_commands
    assert all(description.strip() for description in rows.values())

    for group in help_renderer.help_command_groups():
        assert f"### {group.name}" in command_index
        fragments = (f"### {group.name}",) + tuple(f"`{entry.command}`" for entry in group.commands)
        _assert_in_order(command_index, fragments)


def test_help_renderer_command_index_rewrites_runtime_commands_but_not_local_cli_help() -> None:
    public_prefix = _descriptor_with_public_prefix_kind("slash").public_command_surface_prefix
    command_index = help_renderer.render_command_index_markdown(public_prefix=public_prefix)
    rows = _command_rows(command_index)

    assert f"{public_prefix}help" in rows
    assert f"{public_prefix}new-project --minimal" in rows
    assert "gpd:help" not in rows
    _assert_contains_all(command_index, ("`gpd --help`",))
    _assert_contains_none(command_index, ("`/gpd --help`",))


def test_help_command_groups_cover_registry_without_treating_minimal_variant_as_command() -> None:
    groups = help_renderer.help_command_groups()

    grouped_registry_commands = {
        entry.registry_command for group in groups for entry in group.commands if not entry.documented_variant
    }
    assert grouped_registry_commands == set(list_commands(name_format="label"))

    documented_variants = [entry for group in groups for entry in group.commands if entry.documented_variant]
    assert [(entry.command, entry.registry_command) for entry in documented_variants] == [
        ("gpd:new-project --minimal", "gpd:new-project")
    ]
    assert "gpd:new-project --minimal" not in set(list_commands(name_format="label"))


def test_command_groups_payload_preserves_raw_help_shape() -> None:
    groups = help_renderer.command_groups_payload()

    assert groups[0]["name"] == "Starter commands"
    first_command = groups[0]["commands"][0]
    assert first_command["command"] == "gpd:help"
    assert set(first_command) == {"command", "description"}
    assert isinstance(first_command["description"], str)
    description = first_command["description"].casefold()
    for fragment in ("quick start", "command index"):
        assert fragment in description
    starter_commands = {entry["command"] for entry in groups[0]["commands"]}
    assert "gpd:new-project --minimal" in starter_commands


def test_command_detail_payload_uses_registry_and_normalizes_documented_variants() -> None:
    detail = help_renderer.command_detail_payload("gpd:new-project --minimal", minimal=True, include_markdown=True)

    assert detail["canonical_command"] == "gpd:new-project"
    assert detail["slug"] == "new-project"
    assert detail["context_mode"] == "projectless"
    assert detail["group"] == "Starter commands"
    assert detail["argument_hint"] == "[--auto] [--minimal [@file.md]]"
    assert detail["signature"] == "gpd:new-project"
    assert detail["documented_variants"] == ["gpd:new-project --minimal"]
    assert detail["allowed_tools"] == []
    assert detail["requires"] == {}
    assert "**`gpd:new-project`**" in detail["detail_markdown"]
    assert "`gpd:new-project --minimal`" in detail["detail_markdown"]


def test_command_detail_payload_fails_closed_for_unknown_commands() -> None:
    with pytest.raises(KeyError):
        help_renderer.command_detail_payload("does-not-exist")


def test_command_detail_rendering_uses_command_help_signatures_examples_notes_and_variants(
    fake_help_registry,
) -> None:
    fake_help_registry(
        _fake_command(
            "alpha",
            description="Alpha detail description",
            argument_hint="[fallback-target]",
            help_metadata=CommandHelpMetadata(
                group="Synthetic detail group",
                order=10,
                display_signature="gpd:alpha [index-signature]",
                detail_signature="gpd:alpha --detail <metadata-target>",
                examples=("gpd:alpha --detail paper.tex", "gpd:alpha --detail data.csv"),
                notes=("Metadata detail note.",),
                variants=(
                    CommandHelpVariant(
                        command="gpd:alpha --quick",
                        description="Quick documented path",
                    ),
                ),
            ),
        )
    )

    payload = help_renderer.command_detail_payload("gpd:alpha --quick", minimal=True)
    detail = help_renderer.render_command_detail_markdown("gpd:alpha")

    assert payload["canonical_command"] == "gpd:alpha"
    assert payload["group"] == "Synthetic detail group"
    assert payload["signature"] == "gpd:alpha --detail <metadata-target>"
    assert payload["documented_variants"] == ["gpd:alpha --quick"]
    assert detail.startswith("### Synthetic detail group")
    _assert_contains_all(
        detail,
        (
            "**`gpd:alpha --detail <metadata-target>`**",
            "`gpd:alpha --detail paper.tex`",
            "`gpd:alpha --detail data.csv`",
            "Documented variants:",
            "`gpd:alpha --quick`",
            "Notes:",
            "Metadata detail note.",
        ),
    )
    _assert_contains_none(detail, ("gpd:alpha [fallback-target]", "gpd:alpha [index-signature]"))


def test_root_detailed_reference_selection_and_order_come_from_command_help_metadata(
    fake_help_registry,
) -> None:
    fake_help_registry(
        _fake_command(
            "alpha",
            description="Alpha root detail",
            help_metadata=CommandHelpMetadata(
                group="Synthetic root group",
                order=10,
                root_detail_order=30,
                examples=("gpd:alpha --root",),
                notes=("Alpha root note.",),
            ),
        ),
        _fake_command(
            "beta",
            description="Beta root detail",
            help_metadata=CommandHelpMetadata(
                group="Synthetic root group",
                order=20,
                root_detail_order=10,
                detail_signature="gpd:beta [metadata-root]",
                examples=("gpd:beta --root",),
            ),
        ),
        _fake_command(
            "hidden",
            description="Hidden root detail",
            help_metadata=CommandHelpMetadata(group="Synthetic root group", order=30),
        ),
    )

    root_reference = help_renderer.render_root_detailed_command_reference_markdown()

    _assert_in_order(root_reference, ("**`gpd:beta [metadata-root]`**", "**`gpd:alpha`**"))
    _assert_contains_all(
        root_reference,
        (
            "Usage: `gpd:beta --root`",
            "Usage: `gpd:alpha --root`",
            "Notes: Alpha root note.",
        ),
    )
    assert "Hidden root detail" not in root_reference


def test_render_command_detail_markdown_uses_registry_and_renderer_metadata() -> None:
    payload = help_renderer.command_detail_payload("gpd:peer-review", minimal=True)
    detail = help_renderer.render_command_detail_markdown("gpd:peer-review")

    assert detail.startswith(f"### {payload['group']}")
    assert f"**`{payload['signature']}`**" in detail
    assert payload["description"] in detail
    assert payload["canonical_command"] == "gpd:peer-review"
    assert payload["argument_hint"] == "[paper directory or manuscript/artifact path]"
    assert payload["context_mode"] == "project-aware"
    assert "Subject policy:" in detail
    assert "Review contract:" in detail
    assert "Staged workflow: `peer-review`." in detail
    assert "Registry metadata:" not in detail
    assert "Canonical command:" not in detail
    assert "Argument hint:" not in detail
    assert "Context mode:" not in detail
    assert "`.txt`, `.pdf`, `.docx`, `.csv`, `.tsv`, and `.xlsx`" not in detail


def test_render_command_detail_markdown_rewrites_runtime_signature_and_examples() -> None:
    public_prefix = _descriptor_with_public_prefix_kind("dollar").public_command_surface_prefix
    detail = help_renderer.render_command_detail_markdown("gpd:new-project", public_prefix=public_prefix)

    _assert_contains_all(detail, (f"**`{public_prefix}new-project`**", f"`{public_prefix}new-project --minimal`"))
    _assert_contains_none(detail, ("`gpd:new-project --minimal`",))


def test_render_detailed_command_reference_covers_registry_once() -> None:
    detailed_reference = help_renderer.render_detailed_command_reference_markdown()
    headings = re.findall(r"(?m)^\*\*`gpd:([a-z0-9-]+)\b", detailed_reference)
    heading_counts = Counter(headings)

    duplicate_headings = sorted(command for command, count in heading_counts.items() if count > 1)
    assert duplicate_headings == []
    assert set(headings) == set(list_commands(name_format="slug"))
    assert "gpd:new-project --minimal" in detailed_reference
    assert "## Command Index" not in detailed_reference

    for boilerplate in (
        "Usage examples:",
        "Registry metadata:",
        "Canonical command:",
        "Argument hint:",
        "Context mode:",
        "Project reentry:",
        " with stages ",
    ):
        assert boilerplate not in detailed_reference

    for command in list_commands(name_format="label"):
        payload = help_renderer.command_detail_payload(command, minimal=True)
        assert f"Usage: `{payload['signature']}`" not in detailed_reference

    assert "`gpd:peer-review draft.docx`" in detailed_reference
    assert "`gpd:progress --full`" in detailed_reference
    assert "Documented variants:" in detailed_reference
