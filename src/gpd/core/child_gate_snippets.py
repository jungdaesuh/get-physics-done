"""Compatibility exports for child gate tuple schema and renderers."""

from __future__ import annotations

from gpd.core.child_gate_profiles import (
    CHILD_GATE_PROFILES,
    ChildGateProfile,
    expand_child_gate_profile,
    expand_child_gate_profile_payload,
    list_child_gate_profiles,
    normalize_child_gate_profile_id,
)
from gpd.core.child_handoff import (
    AggregateChildGateTuple,
    ChildGateApplicator,
    ChildGateArtifact,
    ChildGateFreshness,
    ChildGateTuple,
    aggregate_child_gate_tuple_from_payload,
    child_gate_tuple_from_payload,
    parse_aggregate_child_gate_markdown,
    render_child_gate_inline_summary,
    render_child_gate_markdown,
)

__all__ = [
    "AggregateChildGateTuple",
    "CHILD_GATE_PROFILES",
    "ChildGateApplicator",
    "ChildGateArtifact",
    "ChildGateFreshness",
    "ChildGateProfile",
    "ChildGateTuple",
    "aggregate_child_gate_tuple_from_payload",
    "child_gate_tuple_from_payload",
    "expand_child_gate_profile",
    "expand_child_gate_profile_payload",
    "list_child_gate_profiles",
    "normalize_child_gate_profile_id",
    "parse_aggregate_child_gate_markdown",
    "render_child_gate_inline_summary",
    "render_child_gate_markdown",
]
