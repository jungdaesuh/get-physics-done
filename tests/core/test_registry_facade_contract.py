"""Executable guardrails for the public ``gpd.registry`` facade."""

from __future__ import annotations

from dataclasses import is_dataclass

import pytest

import gpd.registry as registry
from gpd.core import workflow_staging

_PUBLIC_EXPORT_NAMES = (
    "AGENTS_DIR",
    "AgentDef",
    "COMMANDS_DIR",
    "LOCAL_CLI_BRIDGE_WORKFLOW_EXEMPT_COMMANDS",
    "CommandDef",
    "CommandHelpMetadata",
    "CommandHelpVariant",
    "CommandOutputPolicy",
    "CommandPolicy",
    "CommandSubjectPolicy",
    "CommandSupportingContextPolicy",
    "ReviewContractConditionalRequirement",
    "ReviewContractScopeVariant",
    "ReviewCommandContract",
    "SkillDef",
    "SPECS_DIR",
    "AGENT_ARTIFACT_WRITE_AUTHORITIES",
    "AGENT_COMMIT_AUTHORITIES",
    "AGENT_ROLE_FAMILIES",
    "AGENT_SHARED_STATE_AUTHORITIES",
    "AGENT_SURFACES",
    "VALID_CONTEXT_MODES",
    "canonical_agent_names",
    "get_agent",
    "get_command",
    "get_skill",
    "invalidate_cache",
    "load_agents_from_dir",
    "list_agents",
    "list_commands",
    "list_review_commands",
    "list_skills",
    "render_agent_visibility_sections_from_frontmatter",
    "render_agent_requirements_section",
    "render_agent_role_kits_section",
    "render_command_visibility_sections",
    "render_command_visibility_sections_from_frontmatter",
    "render_review_contract_section",
)

_COMPATIBILITY_FACADE_NAMES = (
    "WorkflowStageManifest",
    "resolve_workflow_stage_manifest_path",
    "skill_categories",
    "_COMMAND_FRONTMATTER_KEYS",
    "_RegistryCache",
    "_discover_agents",
    "_discover_commands",
    "_frontmatter_parts",
    "_infer_skill_category",
    "_load_frontmatter_mapping",
    "_parse_agent_file",
    "_parse_command_file",
    "_parse_frontmatter",
    "_parse_frontmatter_string_field",
    "_parse_interactive_spawn_contracts",
    "_parse_review_contract",
    "_parse_spawn_contracts",
    "_parse_tools",
)


def test_registry_public_exports_remain_on_facade() -> None:
    missing_from_all = [name for name in _PUBLIC_EXPORT_NAMES if name not in registry.__all__]
    missing_attributes = [name for name in _PUBLIC_EXPORT_NAMES if not hasattr(registry, name)]

    assert missing_from_all == []
    assert missing_attributes == []


def test_registry_private_and_runtime_compatibility_shims_remain_on_facade() -> None:
    missing = [name for name in _COMPATIBILITY_FACADE_NAMES if not hasattr(registry, name)]

    assert missing == []


def test_registry_dataclass_exports_keep_runtime_identity() -> None:
    command = registry.get_command(registry.list_commands()[0])
    agent = registry.get_agent(registry.list_agents()[0])
    skill = registry.get_skill(registry.list_skills()[0])

    assert is_dataclass(registry.CommandDef)
    assert is_dataclass(registry.AgentDef)
    assert is_dataclass(registry.SkillDef)
    assert type(command) is registry.CommandDef
    assert type(agent) is registry.AgentDef
    assert type(skill) is registry.SkillDef
    assert registry.WorkflowStageManifest is workflow_staging.WorkflowStageManifest


def test_registry_private_parser_shims_execute_from_facade() -> None:
    text = "---\nname: sample\ntools: Read, Write\n---\nBody\n"

    raw_frontmatter, body = registry._frontmatter_parts(text)
    parsed, parsed_body = registry._parse_frontmatter(text)
    loaded = registry._load_frontmatter_mapping(raw_frontmatter or "", error_prefix="test frontmatter")

    assert body == "Body\n"
    assert parsed_body == "Body\n"
    assert loaded == parsed
    assert parsed["name"] == "sample"
    assert (
        registry._parse_frontmatter_string_field(
            parsed["name"],
            field_name="name",
            owner_name="sample",
            required=True,
        )
        == "sample"
    )
    assert registry._parse_tools(parsed["tools"], owner_name="sample") == ["Read", "Write"]
    assert registry._parse_review_contract(None, "gpd:sample") is None
    assert registry._parse_spawn_contracts("", owner_name="gpd:sample") == ()
    assert registry._parse_interactive_spawn_contracts("", owner_name="gpd:sample") == ()


@pytest.mark.parametrize("name", ("COMMANDS_DIR", "AGENTS_DIR", "resolve_workflow_stage_manifest_path"))
def test_registry_monkeypatchable_runtime_facade_names_are_module_attributes(name: str) -> None:
    assert name in vars(registry)
