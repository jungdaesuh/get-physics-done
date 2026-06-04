"""Shared test helpers for canonical ``gpd_return`` rendering."""

from __future__ import annotations

import textwrap
from collections.abc import Mapping, Sequence

import yaml

from gpd.core.return_skeleton import build_gpd_return_skeleton, render_gpd_return_markdown


def render_gpd_return_block(
    files_written: Sequence[str],
    *,
    status: str = "completed",
    issues: Sequence[str] | None = None,
    next_actions: Sequence[str] | None = None,
    extra_fields: Mapping[str, object] | None = None,
    extra_yaml: str = "",
) -> str:
    """Render a valid fenced ``gpd_return`` block through the canonical renderer."""

    envelope: dict[str, object] = {
        "status": status,
        "files_written": list(files_written),
        "issues": list(issues or ()),
        "next_actions": list(next_actions or ()),
    }
    envelope.update(_extra_fields(extra_fields=extra_fields, extra_yaml=extra_yaml))
    return render_gpd_return_markdown(envelope)


def build_gpd_return_skeleton_markdown(
    *,
    role: str,
    status: str = "completed",
    files_written: Sequence[str] = (),
    issues: Sequence[str] = (),
    next_actions: Sequence[str] = (),
    extra_fields: Mapping[str, object] | None = None,
) -> str:
    """Build and render a role-aware return skeleton for tests."""

    return build_gpd_return_skeleton(
        role=role,
        status=status,
        files_written=files_written,
        issues=issues,
        next_actions=next_actions,
        extra_fields=extra_fields,
    ).markdown


def _extra_fields(
    *,
    extra_fields: Mapping[str, object] | None,
    extra_yaml: str,
) -> dict[str, object]:
    if extra_fields is not None and extra_yaml.strip():
        raise ValueError("use either extra_fields or extra_yaml, not both")
    if extra_fields is not None:
        return dict(extra_fields)
    if not extra_yaml.strip():
        return {}

    parsed = yaml.safe_load(textwrap.dedent(extra_yaml)) or {}
    if not isinstance(parsed, dict):
        raise TypeError("extra_yaml must render a YAML mapping")
    return parsed
