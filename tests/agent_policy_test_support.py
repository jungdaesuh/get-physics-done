"""Test-only helpers for AgentDef policy and role-kit section assertions."""

from __future__ import annotations

from collections.abc import Sequence

from gpd.core.agent_role_kits import render_agent_role_kits_section, role_kit_authority_paths
from gpd.registry import AgentDef


def expected_agent_policy_subset(agent: AgentDef) -> dict[str, object]:
    """Return the stable AgentDef policy fields mirrored by agent skill metadata."""

    return {
        "commit_authority": agent.commit_authority,
        "surface": agent.surface,
        "role_family": agent.role_family,
        "artifact_write_authority": agent.artifact_write_authority,
        "shared_state_authority": agent.shared_state_authority,
        "role_kits": list(agent.role_kits),
        "role_kit_authorities": list(role_kit_authority_paths(agent.role_kits)),
        "tools": list(agent.tools),
    }


def assert_agent_role_kit_policy(agent: AgentDef, expected_role_kits: Sequence[str]) -> None:
    expected = tuple(expected_role_kits)
    policy = expected_agent_policy_subset(agent)

    assert agent.role_kits == expected, agent.name
    assert policy["role_kits"] == list(expected), agent.name
    assert policy["role_kit_authorities"] == list(role_kit_authority_paths(expected)), agent.name


def assert_agent_role_kit_section(agent: AgentDef, *, before: str | None = None) -> None:
    assert_role_kit_section_in_prompt(agent.system_prompt, agent.role_kits, before=before, context=agent.name)


def assert_role_kit_section_in_prompt(
    prompt: str,
    role_kits: Sequence[str],
    *,
    before: str | None = None,
    context: str = "agent prompt",
) -> None:
    expected_role_kits = tuple(role_kits)
    assert expected_role_kits, f"{context}: expected at least one role kit"

    rendered_section = render_agent_role_kits_section(expected_role_kits)
    role_kit_heading = "## Agent Role Kits"
    requirements_heading = "## Agent Requirements"

    assert prompt.count(requirements_heading) == 1, context
    assert prompt.count(role_kit_heading) == 1, context
    assert rendered_section in prompt, context
    assert prompt.index(requirements_heading) < prompt.index(role_kit_heading), context
    if before is not None:
        assert prompt.index(role_kit_heading) < prompt.index(before), context
