"""Policy-driven markdown frontmatter projection scaffolding."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

import yaml

from gpd.adapters.install_utils import render_markdown_frontmatter, split_markdown_frontmatter

ToolTargetShape = Literal["preserve", "yaml-list", "yaml-bool-map"]
FieldBehavior = Literal["preserve", "drop", "force", "map_color_name_to_hex"]
UnsupportedBehavior = Literal["preserve", "drop", "error"]
MarkerLocation = Literal["body_after_frontmatter"]


@dataclass(frozen=True, slots=True)
class ToolFieldProjection:
    """Policy for collecting and rendering tool frontmatter fields."""

    source_fields: tuple[str, ...] = ("allowed-tools", "tools")
    target_field: str = "tools"
    target_shape: ToolTargetShape = "preserve"
    translate: bool = True
    dedupe: bool = True
    drop_empty: bool = True


@dataclass(frozen=True, slots=True)
class FieldProjection:
    """Policy for one scalar frontmatter field."""

    behavior: FieldBehavior = "preserve"
    forced_value: object | None = None
    color_name_map: Mapping[str, str] = field(default_factory=dict)
    preserve_valid_hex: bool = False


@dataclass(frozen=True, slots=True)
class MarkerProjection:
    """Policy for inserting an ownership marker into projected markdown."""

    marker: str
    location: MarkerLocation = "body_after_frontmatter"
    idempotent: bool = True


@dataclass(frozen=True, slots=True)
class FrontmatterProjectionPolicy:
    """Declarative runtime policy for markdown frontmatter projection."""

    runtime: str
    surface: str
    allowed_fields: tuple[str, ...] | None = None
    unsupported: UnsupportedBehavior = "preserve"
    tools: ToolFieldProjection | None = None
    name: FieldProjection = field(default_factory=FieldProjection)
    description: FieldProjection = field(default_factory=FieldProjection)
    color: FieldProjection = field(default_factory=FieldProjection)
    icon: FieldProjection = field(default_factory=lambda: FieldProjection("drop"))
    marker: MarkerProjection | None = None
    field_order: tuple[str, ...] = ()


TranslateToolName = Callable[[str], str | None]
ContentTransform = Callable[[str], str]


def project_markdown_frontmatter(
    content: str,
    *,
    policy: FrontmatterProjectionPolicy,
    translate_tool_name: TranslateToolName | None = None,
    content_transform: ContentTransform | None = None,
) -> str:
    """Project markdown frontmatter according to a runtime-supplied policy."""
    converted = content_transform(content) if content_transform is not None else content
    preamble, frontmatter, separator, body = split_markdown_frontmatter(converted)
    if not frontmatter:
        return _insert_marker(converted, policy)

    metadata = _load_frontmatter_mapping(frontmatter)
    translator = translate_tool_name or (lambda tool: tool)
    projected, collected_tools = _project_fields(metadata, policy, translator)

    if policy.tools is not None and (collected_tools or not policy.tools.drop_empty):
        projected[policy.tools.target_field] = _render_tool_value(collected_tools, policy.tools)

    ordered = _order_projected_fields(projected, policy.field_order)
    rendered_frontmatter = _dump_frontmatter(ordered)
    rendered = render_markdown_frontmatter(preamble, rendered_frontmatter, separator, body)
    return _insert_marker(rendered, policy)


def _project_fields(
    metadata: Mapping[str, object],
    policy: FrontmatterProjectionPolicy,
    translate_tool_name: TranslateToolName,
) -> tuple[dict[str, object], list[str]]:
    projected: dict[str, object] = {}
    collected_tools: list[str] = []
    tool_source_fields = set(policy.tools.source_fields if policy.tools is not None else ())

    for key, value in metadata.items():
        if key in tool_source_fields and policy.tools is not None:
            collected_tools.extend(_project_tool_tokens(value, policy.tools, translate_tool_name))
            continue

        field_policy = _field_policy_for_key(key, policy)
        if field_policy is not None:
            projected_value = _project_field_value(key, value, field_policy)
            if projected_value is _DROP_FIELD:
                continue
            projected[key] = projected_value
            continue

        if not _field_allowed(key, policy):
            if policy.unsupported == "drop":
                continue
            if policy.unsupported == "error":
                raise ValueError(f"{policy.runtime} {policy.surface} frontmatter does not support field: {key}")

        projected[key] = value

    for key, field_policy in _forced_field_policies(policy):
        if key in projected or key in tool_source_fields:
            continue
        projected_value = _project_field_value(key, None, field_policy)
        if projected_value is not _DROP_FIELD:
            projected[key] = projected_value

    return projected, _dedupe(collected_tools)


def _field_policy_for_key(key: str, policy: FrontmatterProjectionPolicy) -> FieldProjection | None:
    return {
        "name": policy.name,
        "description": policy.description,
        "color": policy.color,
        "icon": policy.icon,
    }.get(key)


def _forced_field_policies(policy: FrontmatterProjectionPolicy) -> tuple[tuple[str, FieldProjection], ...]:
    return tuple(
        (key, field_policy)
        for key, field_policy in (
            ("name", policy.name),
            ("description", policy.description),
            ("color", policy.color),
            ("icon", policy.icon),
        )
        if field_policy.behavior == "force"
    )


def _project_field_value(key: str, value: object, policy: FieldProjection) -> object:
    if policy.behavior == "preserve":
        return value
    if policy.behavior == "drop":
        return _DROP_FIELD
    if policy.behavior == "force":
        return policy.forced_value
    if policy.behavior == "map_color_name_to_hex":
        return _project_color_value(key, value, policy)
    raise ValueError(f"unsupported field projection behavior: {policy.behavior}")


def _project_color_value(key: str, value: object, policy: FieldProjection) -> object:
    if key != "color" or not isinstance(value, str):
        return _DROP_FIELD

    normalized = value.strip().lower()
    mapped = policy.color_name_map.get(normalized)
    if mapped:
        return mapped
    if policy.preserve_valid_hex and _is_hex_color(normalized):
        return value.strip()
    return _DROP_FIELD


def _field_allowed(key: str, policy: FrontmatterProjectionPolicy) -> bool:
    return policy.allowed_fields is None or key in policy.allowed_fields


def _project_tool_tokens(
    value: object,
    policy: ToolFieldProjection,
    translate_tool_name: TranslateToolName,
) -> list[str]:
    tokens = _tool_tokens(value)
    if not policy.translate:
        return tokens

    projected: list[str] = []
    for token in tokens:
        translated = translate_tool_name(token)
        if translated:
            projected.append(translated)
    return _dedupe(projected) if policy.dedupe else projected


def _tool_tokens(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip().strip("'\"") for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip().strip("'\"") for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(key).strip().strip("'\"") for key, enabled in value.items() if enabled and str(key).strip()]
    return [str(value).strip().strip("'\"")] if str(value).strip() else []


def _render_tool_value(tokens: list[str], policy: ToolFieldProjection) -> object:
    unique_tokens = _dedupe(tokens) if policy.dedupe else tokens
    if policy.target_shape == "yaml-bool-map":
        return dict.fromkeys(unique_tokens, True)
    if policy.target_shape in {"yaml-list", "preserve"}:
        return unique_tokens
    raise ValueError(f"unsupported tool target shape: {policy.target_shape}")


def _order_projected_fields(projected: Mapping[str, object], field_order: tuple[str, ...]) -> dict[str, object]:
    if not field_order:
        return dict(projected)

    ordered: dict[str, object] = {}
    for key in field_order:
        if key in projected:
            ordered[key] = projected[key]
    for key, value in projected.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _load_frontmatter_mapping(frontmatter: str) -> dict[str, object]:
    try:
        loaded = yaml.safe_load(frontmatter) if frontmatter.strip() else {}
    except yaml.YAMLError as exc:
        raise ValueError("invalid markdown frontmatter") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError("markdown frontmatter must be a mapping")
    return dict(loaded)


def _dump_frontmatter(metadata: Mapping[str, object]) -> str:
    if not metadata:
        return ""
    return yaml.safe_dump(
        dict(metadata),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()


def _insert_marker(content: str, policy: FrontmatterProjectionPolicy) -> str:
    marker = policy.marker
    if marker is None:
        return content
    if marker.idempotent and marker.marker in content:
        return content

    preamble, frontmatter, separator, body = split_markdown_frontmatter(content)
    marker_text = f"{marker.marker}\n"
    if frontmatter:
        return render_markdown_frontmatter(preamble, frontmatter, separator, marker_text + body)
    return marker_text + content


def _is_hex_color(value: str) -> bool:
    if not value.startswith("#") or len(value) not in {4, 7}:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value[1:])


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class _DropField:
    pass


_DROP_FIELD = _DropField()
