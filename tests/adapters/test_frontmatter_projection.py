from __future__ import annotations

import yaml

from gpd.adapters.frontmatter_projection import (
    FieldProjection,
    FrontmatterProjectionPolicy,
    MarkerProjection,
    ToolFieldProjection,
    project_markdown_frontmatter,
)
from gpd.adapters.install_utils import split_markdown_frontmatter


def _projected_frontmatter_and_body(content: str) -> tuple[dict[str, object], str]:
    _preamble, frontmatter, _separator, body = split_markdown_frontmatter(content)
    metadata = yaml.safe_load(frontmatter) if frontmatter.strip() else {}
    assert isinstance(metadata, dict)
    return metadata, body


def _translate_tool_name(tool: str) -> str | None:
    return {
        "file_read": "read_file",
        "shell": "shell",
        "web_search": "websearch",
        "task": None,
    }.get(tool, tool)


def test_project_markdown_frontmatter_supports_opencode_like_bool_tools_color_and_marker() -> None:
    policy = FrontmatterProjectionPolicy(
        runtime="synthetic-opencode",
        surface="command",
        tools=ToolFieldProjection(target_shape="yaml-bool-map"),
        name=FieldProjection("drop"),
        color=FieldProjection(
            "map_color_name_to_hex",
            color_name_map={"cyan": "#00FFFF"},
            preserve_valid_hex=True,
        ),
        icon=FieldProjection("drop"),
        marker=MarkerProjection("<!-- Managed by synthetic runtime. -->"),
    )
    content = (
        "---\n"
        "name: gpd-help\n"
        "description: Help command\n"
        "color: cyan\n"
        "argument-hint: topic\n"
        "allowed-tools:\n"
        "  - file_read\n"
        "  - shell\n"
        "tools: web_search, mcp__server__tool\n"
        "icon: zap\n"
        "---\n\n"
        "Body.\n"
    )

    projected = project_markdown_frontmatter(content, policy=policy, translate_tool_name=_translate_tool_name)
    metadata, body = _projected_frontmatter_and_body(projected)

    assert {"name", "allowed-tools", "icon"}.isdisjoint(metadata)
    assert metadata["description"] == "Help command"
    assert metadata["argument-hint"] == "topic"
    assert metadata["color"] == "#00FFFF"
    assert metadata["tools"] == {
        "read_file": True,
        "shell": True,
        "websearch": True,
        "mcp__server__tool": True,
    }
    assert body == "<!-- Managed by synthetic runtime. -->\n\nBody.\n"


def test_project_markdown_frontmatter_supports_copilot_like_drop_color_and_body_callback() -> None:
    policy = FrontmatterProjectionPolicy(
        runtime="synthetic-copilot",
        surface="command",
        tools=ToolFieldProjection(target_shape="yaml-bool-map"),
        name=FieldProjection("drop"),
        color=FieldProjection("drop"),
    )
    content = (
        "---\n"
        "name: gpd-debug\n"
        "description: Debug command\n"
        "color: red\n"
        "tools: file_read, task\n"
        "---\n\n"
        "Read ~/.claude/settings.json.\n"
    )

    projected = project_markdown_frontmatter(
        content,
        policy=policy,
        translate_tool_name=_translate_tool_name,
        content_transform=lambda value: value.replace("~/.claude", "~/.copilot"),
    )
    metadata, body = _projected_frontmatter_and_body(projected)

    assert metadata == {"description": "Debug command", "tools": {"read_file": True}}
    assert body == "\nRead ~/.copilot/settings.json.\n"
    assert projected.find("Managed by") == -1


def test_project_markdown_frontmatter_renders_yaml_list_tools_and_dedupes() -> None:
    policy = FrontmatterProjectionPolicy(
        runtime="synthetic-list",
        surface="agent",
        tools=ToolFieldProjection(target_field="tools", target_shape="yaml-list"),
        name=FieldProjection("preserve"),
    )
    content = (
        "---\n"
        "name: gpd-agent\n"
        "allowed-tools: [file_read, file_read, shell]\n"
        "tools:\n"
        "  shell: true\n"
        "  task: true\n"
        "---\n\n"
        "Body.\n"
    )

    projected = project_markdown_frontmatter(content, policy=policy, translate_tool_name=_translate_tool_name)
    metadata, _body = _projected_frontmatter_and_body(projected)

    assert metadata["tools"] == ["read_file", "shell"]


def test_project_markdown_frontmatter_can_drop_unsupported_fields_by_allowlist() -> None:
    policy = FrontmatterProjectionPolicy(
        runtime="strict",
        surface="agent",
        allowed_fields=("description",),
        unsupported="drop",
        tools=None,
        name=FieldProjection("drop"),
        color=FieldProjection("drop"),
    )
    content = "---\nname: gpd-agent\ndescription: Agent\nunknown: value\ncolor: blue\n---\n\nBody.\n"

    projected = project_markdown_frontmatter(content, policy=policy)
    metadata, _body = _projected_frontmatter_and_body(projected)

    assert metadata == {"description": "Agent"}


def test_project_markdown_frontmatter_keeps_marker_idempotent() -> None:
    policy = FrontmatterProjectionPolicy(
        runtime="marked",
        surface="command",
        marker=MarkerProjection("<!-- Managed by synthetic runtime. -->"),
    )
    content = "---\ndescription: Marked\n---\n<!-- Managed by synthetic runtime. -->\nBody.\n"

    projected = project_markdown_frontmatter(content, policy=policy)

    marker = "<!-- Managed by synthetic runtime. -->"
    assert projected.find(marker) == projected.rfind(marker)
