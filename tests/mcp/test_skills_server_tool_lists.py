"""Assertions for MCP skill tool list projection."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import gpd.registry as registry_module
from gpd.core.workflow_staging import WorkflowStage, WorkflowStageConditionalAuthority, WorkflowStageManifest
from gpd.registry import AgentDef, CommandDef, SkillDef
from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_concept

_TASK_OVERLAY_BODY_KEYS = frozenset(
    {"body", "content", "markdown", "text", "overlay_body", "overlay_content", "overlay_markdown", "overlay_text"}
)


def _assert_body_free_task_overlay_metadata(payload: dict[str, object]) -> None:
    assert payload["body_policy"] == "metadata_only"
    for entry in payload["overlays"]:
        assert _TASK_OVERLAY_BODY_KEYS.isdisjoint(entry)
        assert entry["body_loaded"] is False
        assert entry["portable_path"] == "@{GPD_INSTALL_DIR}/references/orchestration/task-overlays.md"


def test_get_skill_tool_schema_publishes_transitive_reference_body_opt_in() -> None:
    import anyio

    from gpd.mcp.servers.skills_server import mcp

    async def _get_schema() -> dict[str, object]:
        tools = await mcp.list_tools()
        tool = next(tool for tool in tools if tool.name == "get_skill")
        return tool.inputSchema

    schema = anyio.run(_get_schema)
    opt_in = schema["properties"]["include_transitive_reference_bodies"]

    assert opt_in["type"] == "boolean"
    assert opt_in["default"] is False
    assert schema["required"] == ["name"]


def test_get_skill_command_allowed_tools_are_defensive_copies() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    command_tools = ["file_read", "shell", "shell"]
    command = CommandDef(
        name="gpd:help",
        description="Help.",
        argument_hint="",
        agent=None,
        requires={},
        allowed_tools=command_tools,
        content="Command body.",
        path="/tmp/gpd-help.md",
        source="commands",
    )
    skill = SkillDef(
        name="gpd-help",
        description="Help.",
        content="Command body.",
        category="help",
        path="/tmp/gpd-help.md",
        source_kind="command",
        registry_name="help",
    )

    with (
        patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill("gpd-help")

    assert result["allowed_tools"] == ["file_read", "shell"]
    assert result["allowed_tools"] is not command.allowed_tools
    assert result["allowed_tools_surface"] == "command.allowed-tools"
    result["allowed_tools"].append("network")
    assert command.allowed_tools == ["file_read", "shell", "shell"]


def test_get_skill_loading_hint_stays_focused_on_skill_loading() -> None:
    from gpd.mcp.descriptor_text import SKILL_BEHAVIORAL_GUARDRAIL_HINT
    from gpd.mcp.servers.skills_server import get_skill

    command = CommandDef(
        name="gpd:help",
        description="Help.",
        argument_hint="",
        agent=None,
        requires={},
        allowed_tools=["file_read"],
        content="Command body.",
        path="/tmp/gpd-help.md",
        source="commands",
    )
    skill = SkillDef(
        name="gpd-help",
        description="Help.",
        content="Command body.",
        category="help",
        path="/tmp/gpd-help.md",
        source_kind="command",
        registry_name="help",
    )

    with (
        patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill("gpd-help")

    assert result["loading_hint"] == (
        "Treat `content` as the wrapper/context surface. It already embeds the model-visible "
        "`Command Requirements` section. Follow that section for command-specific constraints."
    )
    assert SKILL_BEHAVIORAL_GUARDRAIL_HINT not in result["loading_hint"]
    assert "missing evidence" not in result["loading_hint"]
    assert "never fabricate" not in result["loading_hint"]


def test_get_skill_index_surfaces_shared_behavioral_guardrail_once() -> None:
    from gpd.mcp.descriptor_text import SKILL_BEHAVIORAL_GUARDRAIL_HINT
    from gpd.mcp.servers.skills_server import get_skill_index

    skill = SkillDef(
        name="gpd-help",
        description="Help.",
        content="Command body.",
        category="help",
        path="/tmp/gpd-help.md",
        source_kind="command",
        registry_name="help",
    )
    command = CommandDef(
        name="gpd:help",
        description="Help.",
        argument_hint="",
        agent=None,
        requires={},
        allowed_tools=["file_read"],
        content="Command body.",
        path="/tmp/gpd-help.md",
        source="commands",
    )

    with (
        patch("gpd.mcp.servers.skills_server._load_skill_index", return_value=[skill]),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill_index()

    assert result["index_text"].count(SKILL_BEHAVIORAL_GUARDRAIL_HINT) == 1
    assert result["index_text"].count("missing evidence") == 1
    assert result["index_text"].count("never fabricate") == 1


def test_get_skill_command_surfaces_agent_metadata() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    command = CommandDef(
        name="gpd:plan-phase",
        description="Plan.",
        argument_hint="",
        agent="gpd-planner",
        requires={},
        allowed_tools=["file_read"],
        content="## Command Requirements\n\n```yaml\ncontext_mode: project-required\nproject_reentry_capable: false\nagent: gpd-planner\nallowed_tools:\n  - file_read\n```\n\nBody.",
        path="/tmp/gpd-plan-phase.md",
        source="commands",
    )
    skill = SkillDef(
        name="gpd-plan-phase",
        description="Plan.",
        content=command.content,
        category="planning",
        path="/tmp/gpd-plan-phase.md",
        source_kind="command",
        registry_name="plan-phase",
    )

    with (
        patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill("gpd-plan-phase")

    assert result["agent"] == "gpd-planner"
    assert result["allowed_tools_surface"] == "command.allowed-tools"
    assert result["structured_metadata_authority"]["agent"] == "mirrored"
    assert "agent: gpd-planner" in result["content"]


def test_list_skills_filters_consistency_checker_by_verification_category() -> None:
    from gpd.mcp.servers.skills_server import list_skills

    consistency_checker = SkillDef(
        name="gpd-consistency-checker",
        description="Consistency checker.",
        content="Consistency checker body.",
        category="verification",
        path="/tmp/gpd-consistency-checker.md",
        source_kind="agent",
        registry_name="gpd-consistency-checker",
    )
    help_skill = SkillDef(
        name="gpd-help",
        description="Help.",
        content="Help body.",
        category="help",
        path="/tmp/gpd-help.md",
        source_kind="command",
        registry_name="help",
    )

    with patch("gpd.mcp.servers.skills_server._load_skill_index", return_value=[consistency_checker, help_skill]):
        result = list_skills(category="verification")

    assert result["count"] == 1
    assert result["skills"] == [
        {
            "name": "gpd-consistency-checker",
            "category": "verification",
            "description": "Consistency checker.",
        }
    ]
    assert result["categories"] == ["help", "verification"]


def test_list_skills_filters_beginner_help_entrypoints_by_help_category() -> None:
    from gpd.mcp.servers.skills_server import list_skills

    registry_module.invalidate_cache()
    help_skill = registry_module.get_skill("gpd-help")
    start_skill = registry_module.get_skill("gpd-start")
    tour_skill = registry_module.get_skill("gpd-tour")

    with patch(
        "gpd.mcp.servers.skills_server._load_skill_index",
        return_value=[help_skill, start_skill, tour_skill],
    ):
        result = list_skills(category="help")

    assert result["count"] == 3
    assert result["skills"] == [
        {
            "name": "gpd-help",
            "category": "help",
            "description": help_skill.description,
        },
        {
            "name": "gpd-start",
            "category": "help",
            "description": start_skill.description,
        },
        {
            "name": "gpd-tour",
            "category": "help",
            "description": tour_skill.description,
        },
    ]
    assert result["categories"] == ["help"]


def test_get_skill_command_surfaces_staged_loading_sidecar() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    staged_loading = WorkflowStageManifest(
        schema_version=1,
        workflow_id="new-project",
        stages=(
            WorkflowStage(
                id="scope_intake",
                order=1,
                purpose="intake",
                mode_paths=("workflows/new-project.md",),
                required_init_fields=("researcher_model",),
                loaded_authorities=("workflows/new-project.md",),
                conditional_authorities=(
                    WorkflowStageConditionalAuthority(
                        when="conditional",
                        authorities=("references/research/questioning.md",),
                    ),
                ),
                must_not_eager_load=("references/research/questioning.md",),
                allowed_tools=("file_read",),
                writes_allowed=(),
                produced_state=(),
                next_stages=(),
                checkpoints=(),
            ),
        ),
    )
    command = CommandDef(
        name="gpd:new-project",
        description="New project.",
        argument_hint="",
        agent=None,
        requires={},
        allowed_tools=["file_read"],
        content="Command body.",
        path="/tmp/gpd-new-project.md",
        source="commands",
        staged_loading=staged_loading,
    )
    skill = SkillDef(
        name="gpd-new-project",
        description="New project.",
        content="Command body.",
        category="project",
        path="/tmp/gpd-new-project.md",
        source_kind="command",
        registry_name="new-project",
    )

    with (
        patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill("gpd-new-project")

    assert result["staged_loading"]["workflow_id"] == "new-project"
    assert result["staged_loading"]["stages"][0]["id"] == "scope_intake"
    assert result["structured_metadata_authority"]["staged_loading"] == "mirrored"


def test_staged_authority_seeds_are_metadata_only_and_scanned_transitively(tmp_path: Path) -> None:
    from gpd.mcp.servers import skills_server

    fixtures = {
        "stage-authority.md": "Stage authority references @{GPD_INSTALL_DIR}/templates/staged-schema.md.\n",
        "staged-schema.md": "---\ntype: schema\n---\n# Staged Schema\nDefault payload omits this body.\n",
        "conditional-authority.md": "# Conditional Authority\n",
        "lazy-schema.md": (
            "---\ntype: schema\n---\n# Lazy Schema\n"
            "This lazy body mentions @{GPD_INSTALL_DIR}/templates/lazy-nested-schema.md.\n"
        ),
        "lazy-nested-schema.md": "---\ntype: schema\n---\n# Lazy Nested Schema\n",
    }
    fixture_paths = {name: tmp_path / name for name in fixtures}
    for name, body in fixtures.items():
        fixture_paths[name].write_text(body, encoding="utf-8")

    staged_loading = WorkflowStageManifest(
        schema_version=1,
        workflow_id="debug",
        stages=(
            WorkflowStage(
                id="bootstrap",
                order=1,
                purpose="debug bootstrap",
                mode_paths=(),
                required_init_fields=(),
                loaded_authorities=("workflows/stage-authority.md",),
                conditional_authorities=(
                    WorkflowStageConditionalAuthority(
                        when="needs_extra_context",
                        authorities=("workflows/conditional-authority.md",),
                    ),
                ),
                must_not_eager_load=("templates/lazy-schema.md",),
                allowed_tools=("file_read",),
                writes_allowed=(),
                produced_state=(),
                next_stages=(),
                checkpoints=(),
            ),
        ),
    )
    portable_paths = {
        "workflows/stage-authority.md": (
            "@{GPD_INSTALL_DIR}/workflows/stage-authority.md",
            fixture_paths["stage-authority.md"],
        ),
        "workflows/conditional-authority.md": (
            "@{GPD_INSTALL_DIR}/workflows/conditional-authority.md",
            fixture_paths["conditional-authority.md"],
        ),
        "templates/lazy-schema.md": ("@{GPD_INSTALL_DIR}/templates/lazy-schema.md", fixture_paths["lazy-schema.md"]),
        "@{GPD_INSTALL_DIR}/templates/staged-schema.md": (
            "@{GPD_INSTALL_DIR}/templates/staged-schema.md",
            fixture_paths["staged-schema.md"],
        ),
        "@{GPD_INSTALL_DIR}/templates/lazy-nested-schema.md": (
            "@{GPD_INSTALL_DIR}/templates/lazy-nested-schema.md",
            fixture_paths["lazy-nested-schema.md"],
        ),
    }
    original_portable_reference_path = skills_server._portable_reference_path

    def _patched_portable_reference_path(raw_path: str, *, base_path: Path | None = None):
        if raw_path in portable_paths:
            return portable_paths[raw_path]
        return original_portable_reference_path(raw_path, base_path=base_path)

    with patch("gpd.mcp.servers.skills_server._portable_reference_path", side_effect=_patched_portable_reference_path):
        referenced_files, transitive_referenced_files = skills_server._build_skill_reference_lists(
            "Command body.",
            source_path=tmp_path / "gpd-debug.md",
            staged_loading=staged_loading,
            read_transitive_reference_bodies=False,
        )

    direct_by_name = {Path(entry["path"]).name: entry for entry in referenced_files}
    transitive_paths = {entry["path"] for entry in transitive_referenced_files}
    assert direct_by_name["stage-authority.md"] == {
        "path": "@{GPD_INSTALL_DIR}/workflows/stage-authority.md",
        "kind": "workflow",
        "source": "staged_loading",
        "stage": "bootstrap",
        "relationship": "stage_eager",
    }
    assert direct_by_name["conditional-authority.md"] == {
        "path": "@{GPD_INSTALL_DIR}/workflows/conditional-authority.md",
        "kind": "workflow",
        "source": "staged_loading",
        "stage": "bootstrap",
        "relationship": "stage_conditional",
        "conditional_when": "needs_extra_context",
    }
    assert direct_by_name["lazy-schema.md"] == {
        "path": "@{GPD_INSTALL_DIR}/templates/lazy-schema.md",
        "kind": "template",
        "source": "staged_loading",
        "stage": "bootstrap",
        "relationship": "stage_lazy_declared",
    }
    assert "@{GPD_INSTALL_DIR}/templates/staged-schema.md" in transitive_paths
    assert "@{GPD_INSTALL_DIR}/templates/lazy-nested-schema.md" not in transitive_paths


def test_get_skill_plan_phase_surfaces_staged_loading_sidecar() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    staged_loading = WorkflowStageManifest(
        schema_version=1,
        workflow_id="plan-phase",
        stages=(
            WorkflowStage(
                id="phase_bootstrap",
                order=1,
                purpose="phase lookup",
                mode_paths=("workflows/plan-phase.md",),
                required_init_fields=("researcher_model",),
                loaded_authorities=("workflows/plan-phase.md",),
                conditional_authorities=(),
                must_not_eager_load=("references/ui/ui-brand.md",),
                allowed_tools=("file_read",),
                writes_allowed=(),
                produced_state=(),
                next_stages=("research_routing",),
                checkpoints=(),
            ),
        ),
    )
    command = CommandDef(
        name="gpd:plan-phase",
        description="Plan.",
        argument_hint="",
        agent="gpd-planner",
        requires={},
        allowed_tools=["file_read"],
        content="Command body.",
        path="/tmp/gpd-plan-phase.md",
        source="commands",
        staged_loading=staged_loading,
    )
    skill = SkillDef(
        name="gpd-plan-phase",
        description="Plan.",
        content="Command body.",
        category="planning",
        path="/tmp/gpd-plan-phase.md",
        source_kind="command",
        registry_name="plan-phase",
    )

    with (
        patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill("gpd-plan-phase")

    assert result["staged_loading"]["workflow_id"] == "plan-phase"
    assert result["staged_loading"]["stages"][0]["id"] == "phase_bootstrap"
    assert result["structured_metadata_authority"]["staged_loading"] == "mirrored"


def test_get_skill_command_surfaces_spawn_contract_sidecar_without_content_injection() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    spawn_contracts = (
        {
            "agent": "gpd-notation-coordinator",
            "shared_state_policy": "return_only",
            "write_scope": {"mode": "scoped_write", "paths": ["GPD/CONVENTIONS.md"]},
            "expected_artifacts": ["GPD/CONVENTIONS.md"],
        },
    )
    interactive_spawn_contracts = (
        {
            "activation": "mode == interactive",
            "shared_state_policy": "none",
            "write_scope": {"mode": "no_write", "allowed_paths": []},
            "expected_artifacts": [],
            "expected_return": {"status": "checkpoint"},
        },
    )
    command = CommandDef(
        name="gpd:new-project",
        description="New project.",
        argument_hint="",
        agent=None,
        requires={},
        allowed_tools=["file_read"],
        content="Command body.",
        path="/tmp/gpd-new-project.md",
        source="commands",
        spawn_contracts=spawn_contracts,
        interactive_spawn_contracts=interactive_spawn_contracts,
    )
    skill = SkillDef(
        name="gpd-new-project",
        description="New project.",
        content="Command body.",
        category="project",
        path="/tmp/gpd-new-project.md",
        source_kind="command",
        registry_name="new-project",
        spawn_contracts=spawn_contracts,
        interactive_spawn_contracts=interactive_spawn_contracts,
    )

    with (
        patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill("gpd-new-project")

    assert result["content"] == "Command body."
    assert result["spawn_contracts"] == [dict(spawn_contracts[0])]
    assert result["spawn_contracts"] is not command.spawn_contracts
    result["spawn_contracts"][0]["expected_artifacts"].append("GPD/EXTRA.md")
    assert command.spawn_contracts[0]["expected_artifacts"] == ["GPD/CONVENTIONS.md"]
    assert result["structured_metadata_authority"]["spawn_contracts"] == "mirrored"
    assert result["interactive_spawn_contracts"] == [dict(interactive_spawn_contracts[0])]
    assert result["interactive_spawn_contracts"] is not command.interactive_spawn_contracts
    result["interactive_spawn_contracts"][0]["expected_artifacts"].append("GPD/EXTRA.md")
    assert command.interactive_spawn_contracts[0]["expected_artifacts"] == []
    assert result["structured_metadata_authority"]["interactive_spawn_contracts"] == "mirrored"


def test_get_skill_execute_phase_surfaces_staged_loading_sidecar() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    staged_loading = WorkflowStageManifest(
        schema_version=1,
        workflow_id="execute-phase",
        stages=(
            WorkflowStage(
                id="phase_bootstrap",
                order=1,
                purpose="phase lookup and routing",
                mode_paths=("workflows/execute-phase.md",),
                required_init_fields=(),
                loaded_authorities=("workflows/execute-phase.md",),
                conditional_authorities=(),
                must_not_eager_load=("references/ui/ui-brand.md",),
                allowed_tools=("file_read",),
                writes_allowed=(),
                produced_state=(),
                next_stages=(),
                checkpoints=(),
            ),
        ),
    )
    command = CommandDef(
        name="gpd-execute-phase",
        description="Execute.",
        argument_hint="",
        agent=None,
        requires={},
        allowed_tools=["file_read"],
        content="Execute body.",
        path="/tmp/gpd-execute-phase.md",
        source="commands",
        staged_loading=staged_loading,
    )
    skill = SkillDef(
        name="gpd-execute-phase",
        description="Execute.",
        content="Execute body.",
        category="execution",
        path="/tmp/gpd-execute-phase.md",
        source_kind="command",
        registry_name="execute-phase",
    )

    with (
        patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill("gpd-execute-phase")

    assert result["staged_loading"]["workflow_id"] == "execute-phase"
    assert result["staged_loading"]["stages"][0]["id"] == "phase_bootstrap"
    assert result["structured_metadata_authority"]["staged_loading"] == "mirrored"


def test_get_skill_index_surfaces_spawn_contract_presence_sidecar() -> None:
    from gpd.mcp.servers.skills_server import get_skill_index

    staged_loading = WorkflowStageManifest(
        schema_version=1,
        workflow_id="new-project",
        stages=(
            WorkflowStage(
                id="scope_intake",
                order=1,
                purpose="intake",
                mode_paths=("workflows/new-project.md",),
                required_init_fields=(),
                loaded_authorities=("workflows/new-project.md",),
                conditional_authorities=(),
                must_not_eager_load=(),
                allowed_tools=("file_read",),
                writes_allowed=(),
                produced_state=(),
                next_stages=(),
                checkpoints=(),
            ),
        ),
    )
    skill = SkillDef(
        name="gpd-new-project",
        description="New project.",
        content="Command body.",
        category="project",
        path="/tmp/gpd-new-project.md",
        source_kind="command",
        registry_name="new-project",
    )
    command = CommandDef(
        name="gpd:new-project",
        description="New project.",
        argument_hint="",
        agent="gpd-planner",
        requires={},
        allowed_tools=["file_read"],
        content="Command body.",
        path="/tmp/gpd-new-project.md",
        source="commands",
        staged_loading=staged_loading,
        spawn_contracts=(
            {
                "agent": "gpd-notation-coordinator",
                "shared_state_policy": "return_only",
                "write_scope": {"mode": "scoped_write", "paths": ["GPD/CONVENTIONS.md"]},
                "expected_artifacts": ["GPD/CONVENTIONS.md"],
            },
        ),
        interactive_spawn_contracts=(
            {
                "activation": "mode == interactive",
                "shared_state_policy": "none",
                "write_scope": {"mode": "no_write", "allowed_paths": []},
                "expected_artifacts": [],
                "expected_return": {"status": "checkpoint"},
            },
        ),
    )

    with (
        patch("gpd.mcp.servers.skills_server._load_skill_index", return_value=[skill]),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill_index()

    assert result["total_skills"] == 1
    assert result["command_envelopes"]["gpd-new-project"]["has_spawn_contracts"] is True
    assert result["command_envelopes"]["gpd-new-project"]["has_interactive_spawn_contracts"] is True
    assert result["command_envelopes"]["gpd-new-project"]["has_review_contract"] is False
    assert result["command_envelopes"]["gpd-new-project"]["agent"] == "gpd-planner"
    assert result["command_envelopes"]["gpd-new-project"]["has_staged_loading"] is True
    assert result["command_envelopes"]["gpd-new-project"]["stage_count"] == 1
    assert "agent=gpd-planner" in result["index_text"]
    assert "staged-loading" in result["index_text"]
    assert "stage_count=1" in result["index_text"]


def test_get_skill_verify_work_surfaces_staged_loading_sidecar() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = repo_root / "src" / "gpd" / "specs" / "workflows" / "verify-work-stage-manifest.json"
    original_resolve_manifest_path = registry_module.resolve_workflow_stage_manifest_path
    with (
        patch(
            "gpd.registry.resolve_workflow_stage_manifest_path",
            lambda workflow_id: (
                manifest_path if workflow_id == "verify-work" else original_resolve_manifest_path(workflow_id)
            ),
        ),
    ):
        registry_module.invalidate_cache()
        result = get_skill("gpd-verify-work")

    assert [stage["id"] for stage in result["staged_loading"]["stages"]] == [
        "session_router",
        "phase_bootstrap",
        "inventory_build",
        "interactive_validation",
        "gap_repair",
    ]
    assert result["staged_loading"]["workflow_id"] == "verify-work"
    assert result["staged_loading"]["stages"][0]["loaded_authorities"] == ["workflows/verify-work/session-router.md"]
    assert_prompt_contracts(
        result["content"],
        *semantic_concept(
            "verify-work skill delegates detailed checks to staged authorities",
            required=(
                "Follow the included first-stage authority exactly",
                "The staged workflow authorities own the detailed check taxonomy; this wrapper only bootstraps the canonical verification surface and delegates the physics checks.",
            ),
            forbidden=(
                "One check at a time, plain text responses, no interrogation.",
                "Physics verification is not binary:",
            ),
        ),
    )
    assert "Severity Classification" not in result["content"]
    assert "For deeper focused analysis" not in result["content"]
    inventory_build = result["staged_loading"]["stages"][2]
    assert inventory_build["loaded_authorities"] == ["workflows/verify-work/inventory-build.md"]
    assert inventory_build["conditional_authorities"] == [
        {
            "when": "full_independence_policy_check",
            "authorities": ["references/verification/meta/verification-independence.md"],
        }
    ]
    assert "references/verification/meta/verification-independence.md" in inventory_build["must_not_eager_load"]
    assert inventory_build["next_stages"] == ["interactive_validation"]
    assert inventory_build["checkpoints"] == [
        "verifier delegation completed",
        "handoff remains fail-closed",
        "anchor obligations explicit",
    ]
    assert result["staged_loading"]["stages"][3]["allowed_tools"] == [
        "ask_user",
        "file_read",
        "file_edit",
        "file_write",
        "find_files",
        "search_files",
        "shell",
        "task",
    ]
    assert result["staged_loading"]["stages"][3]["loaded_authorities"] == [
        "workflows/verify-work/interactive-validation.md",
    ]
    assert result["staged_loading"]["stages"][3]["conditional_authorities"] == [
        {
            "when": "session_overlay_write_or_repair",
            "authorities": [
                "templates/research-verification.md",
                "templates/verification-report.md",
                "templates/contract-results-schema.md",
                "references/shared/canonical-schema-discipline.md",
            ],
        },
        {
            "when": "custom_verifier_continuation",
            "authorities": [
                "templates/verification-report.md",
                "templates/contract-results-schema.md",
                "references/shared/canonical-schema-discipline.md",
            ],
        },
    ]
    assert result["staged_loading"]["stages"][3]["writes_allowed"] == ["GPD/phases/XX-name/XX-VERIFICATION.md"]
    assert result["staged_loading"]["stages"][3]["next_stages"] == ["gap_repair"]
    assert result["staged_loading"]["stages"][3]["checkpoints"] == [
        "verification file can be written",
        "writer-stage schema deferral barrier is visible",
        "check results remain contract-backed",
    ]
    assert result["staged_loading"]["stages"][4]["loaded_authorities"] == [
        "workflows/verify-work/gap-repair.md",
    ]
    assert result["staged_loading"]["stages"][4]["conditional_authorities"] == [
        {
            "when": "gap_report_write_or_schema_repair",
            "authorities": [
                "templates/research-verification.md",
                "templates/verification-report.md",
                "templates/contract-results-schema.md",
                "references/shared/canonical-schema-discipline.md",
            ],
        },
        {
            "when": "error_propagation_gap",
            "authorities": [
                "references/protocols/error-propagation-protocol.md",
            ],
        },
    ]
    assert result["staged_loading"]["stages"][4]["writes_allowed"] == ["GPD/phases/XX-name/XX-VERIFICATION.md"]
    assert result["staged_loading"]["stages"][4]["next_stages"] == []
    assert result["staged_loading"]["stages"][4]["checkpoints"] == [
        "gaps are diagnosed",
        "repair plans are verified",
        "verification closeout is ready",
    ]
    assert result["structured_metadata_authority"]["staged_loading"] == "mirrored"
    assert result["allowed_tools_surface"] == "command.allowed-tools"


def test_get_skill_unrelated_command_does_not_expose_stage_sidecars() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    command = CommandDef(
        name="gpd:help",
        description="Help.",
        argument_hint="",
        agent=None,
        requires={},
        allowed_tools=["file_read"],
        content="Command body.",
        path="/tmp/gpd-help.md",
        source="commands",
    )
    skill = SkillDef(
        name="gpd-help",
        description="Help.",
        content="Command body.",
        category="help",
        path="/tmp/gpd-help.md",
        source_kind="command",
        registry_name="help",
    )

    with (
        patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
        patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
    ):
        result = get_skill("gpd-help")

    assert "staged_loading" not in result
    assert "staged_loading" not in result["structured_metadata_authority"]
    assert "new-project-stage-manifest.json" not in result["content"]


def test_get_skill_agent_surfaces_allowed_tools() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    agent_tools = ["shell", "file_read", "shell"]
    agent = AgentDef(
        name="gpd-debugger",
        description="Debugger.",
        system_prompt="Agent body.",
        tools=agent_tools,
        color="blue",
        path="/tmp/gpd-debugger.md",
        source="agents",
    )
    skill = SkillDef(
        name="gpd-debugger",
        description="Debugger.",
        content="Agent body.",
        category="debugging",
        path="/tmp/gpd-debugger.md",
        source_kind="agent",
        registry_name="gpd-debugger",
    )

    with (
        patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
        patch("gpd.mcp.servers.skills_server.content_registry.get_agent", return_value=agent),
    ):
        result = get_skill("gpd-debugger")

    assert result["allowed_tools"] == ["shell", "file_read"]
    assert result["allowed_tools"] is not agent.tools
    assert result["allowed_tools_surface"] == "agent.tools"
    assert result["structured_metadata_authority"] == {
        "content": "canonical",
        "allowed_tools": "mirrored",
        "agent_policy": "mirrored",
    }
    result["allowed_tools"].append("network")
    assert agent.tools == ["shell", "file_read", "shell"]


def test_get_skill_debugger_agent_keeps_schema_dependencies_transitive_only() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    result = get_skill("gpd-debugger")

    assert result["allowed_tools_surface"] == "agent.tools"
    assert result["schema_references"] == []
    assert result["schema_documents"] == []
    assert result["contract_references"] == []
    assert result["contract_documents"] == []
    assert result["transitive_schema_references"] == []
    assert result["transitive_schema_documents"] == []
    assert result["structured_metadata_authority"] == {
        "content": "canonical",
        "allowed_tools": "mirrored",
        "agent_policy": "mirrored",
    }


def test_get_skill_executor_agent_does_not_expose_staged_loading_sidecar() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    result = get_skill("gpd-executor")

    assert result["allowed_tools_surface"] == "agent.tools"
    assert result["structured_metadata_authority"] == {
        "content": "canonical",
        "allowed_tools": "mirrored",
        "agent_policy": "mirrored",
        "compatible_task_overlays": "mirrored",
    }
    assert result["compatible_task_overlays"]["compatible_task_overlay_ids"] == [
        "executor.proof_bearing",
        "executor.bounded_segment",
    ]
    _assert_body_free_task_overlay_metadata(result["compatible_task_overlays"])
    assert "staged_loading" not in result
    assert "staged_loading" not in result["structured_metadata_authority"]


def test_get_skill_planner_agent_does_not_expose_staged_loading_sidecar(monkeypatch) -> None:
    from pathlib import Path

    from gpd import registry as content_registry
    from gpd.mcp.servers.skills_server import get_skill

    repo_agents_dir = Path(__file__).resolve().parents[2] / "src/gpd/agents"
    monkeypatch.setattr(content_registry, "AGENTS_DIR", repo_agents_dir)
    content_registry.invalidate_cache()

    result = get_skill("gpd-planner")

    assert result["allowed_tools_surface"] == "agent.tools"
    assert result["structured_metadata_authority"]["content"] == "canonical"
    assert "staged_loading" not in result
    assert "staged_loading" not in result["structured_metadata_authority"]


def test_get_skill_planner_ignores_fenced_docs_examples(monkeypatch) -> None:
    from pathlib import Path

    from gpd import registry as content_registry
    from gpd.mcp.servers.skills_server import get_skill

    repo_agents_dir = Path(__file__).resolve().parents[2] / "src/gpd/agents"
    monkeypatch.setattr(content_registry, "AGENTS_DIR", repo_agents_dir)
    content_registry.invalidate_cache()

    result = get_skill("gpd-planner")
    docs_references = [entry for entry in result["referenced_files"] if entry["kind"] == "docs"]

    assert all(entry["path"] != "@GPD/docs/conventions.md" for entry in docs_references)
    assert all(not entry["path"].startswith("/") for entry in docs_references)
    assert result["loading_hint"].startswith("Treat `content` as the wrapper/context surface.")


def test_missing_docs_reference_rejects_unsafe_relative_suffixes() -> None:
    from gpd.mcp.servers.skills_server import _portable_reference_path

    assert _portable_reference_path("docs/future-conventions.md") == ("@GPD/docs/future-conventions.md", None)
    assert _portable_reference_path("docs/../README.md") is None
    assert _portable_reference_path("docs//future-conventions.md") is None
    assert _portable_reference_path("docs/./future-conventions.md") is None


def test_reference_shorthand_aliases_resolve_under_references_root() -> None:
    from gpd.mcp.servers.skills_server import _extract_referenced_files, _portable_reference_path

    shared = _portable_reference_path("shared/shared-protocols.md")
    verification = _portable_reference_path("@{GPD_INSTALL_DIR}/verification/core/verification-core.md")

    assert shared is not None
    assert shared[0] == "@{GPD_INSTALL_DIR}/references/shared/shared-protocols.md"
    assert shared[1] is not None
    assert shared[1].as_posix().endswith("src/gpd/specs/references/shared/shared-protocols.md")
    assert verification is not None
    assert verification[0] == "@{GPD_INSTALL_DIR}/references/verification/core/verification-core.md"
    assert _portable_reference_path("domains/verification-domain-qft.md") is None

    direct_references, _transitive_references = _extract_referenced_files(
        "Read shared/shared-protocols.md and verification/core/verification-core.md.\n"
    )
    direct_paths = {entry["path"] for entry in direct_references}

    assert "@{GPD_INSTALL_DIR}/references/shared/shared-protocols.md" in direct_paths
    assert "@{GPD_INSTALL_DIR}/references/verification/core/verification-core.md" in direct_paths
    assert all(not path.startswith("@{GPD_INSTALL_DIR}/shared/") for path in direct_paths)


def test_relative_domains_reference_extracts_from_reference_docs() -> None:
    from gpd.mcp.servers.skills_server import _extract_referenced_files

    source_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "gpd"
        / "specs"
        / "references"
        / "verification"
        / "core"
        / "verification-core.md"
    )

    direct_references, _transitive_references = _extract_referenced_files(
        "Read ../domains/verification-domain-qft.md before applying this profile.",
        source_path=source_path,
    )

    assert {entry["path"] for entry in direct_references} == {
        "@{GPD_INSTALL_DIR}/references/verification/domains/verification-domain-qft.md"
    }


def test_extract_referenced_files_ignores_fenced_code_blocks(tmp_path: Path) -> None:
    from gpd.mcp.servers import skills_server

    workflow_path = tmp_path / "wrapper.md"
    workflow_path.write_text(
        "Example only:\n\n```markdown\n@{GPD_INSTALL_DIR}/templates/fenced-schema.md\n```\n",
        encoding="utf-8",
    )
    schema_path = tmp_path / "fenced-schema.md"
    schema_path.write_text("---\ntype: schema\n---\n# Fenced Schema\n", encoding="utf-8")
    portable_paths = {
        "@{GPD_INSTALL_DIR}/workflows/wrapper.md": workflow_path,
        "@{GPD_INSTALL_DIR}/templates/fenced-schema.md": schema_path,
    }
    original_portable_reference_path = skills_server._portable_reference_path

    def _patched_portable_reference_path(raw_path: str, *, base_path: Path | None = None):
        if raw_path in portable_paths:
            return raw_path, portable_paths[raw_path]
        return original_portable_reference_path(raw_path, base_path=base_path)

    with patch(
        "gpd.mcp.servers.skills_server._portable_reference_path",
        side_effect=_patched_portable_reference_path,
    ):
        fenced_direct, fenced_transitive = skills_server._extract_referenced_files(
            "```markdown\n@{GPD_INSTALL_DIR}/templates/fenced-schema.md\n```\n"
        )
        direct_references, transitive_references = skills_server._extract_referenced_files(
            "Read @{GPD_INSTALL_DIR}/workflows/wrapper.md first.\n"
        )

    assert fenced_direct == []
    assert fenced_transitive == []
    assert [entry["path"] for entry in direct_references] == ["@{GPD_INSTALL_DIR}/workflows/wrapper.md"]
    assert transitive_references == []


def test_get_skill_transitive_reference_documents_are_metadata_only_by_default(tmp_path: Path) -> None:
    from gpd.mcp.servers import skills_server

    workflow_path = tmp_path / "wrapper.md"
    workflow_path.write_text(
        "See @{GPD_INSTALL_DIR}/templates/nested-schema.md for the schema.\n",
        encoding="utf-8",
    )
    schema_path = tmp_path / "nested-schema.md"
    schema_path.write_text(
        "---\ntype: schema\n---\n# Nested Schema\n"
        "Transitive body.\n"
        "See @{GPD_INSTALL_DIR}/templates/deeper-schema.md.\n",
        encoding="utf-8",
    )
    deeper_schema_path = tmp_path / "deeper-schema.md"
    deeper_schema_path.write_text("---\ntype: schema\n---\n# Deeper Schema\n", encoding="utf-8")
    command = CommandDef(
        name="gpd:debug",
        description="Debug.",
        argument_hint="",
        requires={},
        allowed_tools=["file_read"],
        content="Command body.",
        path=str(tmp_path / "gpd-debug.md"),
        source="commands",
    )
    skill = SkillDef(
        name="gpd-debug",
        description="Debug.",
        content="Read @{GPD_INSTALL_DIR}/workflows/wrapper.md first.\n",
        category="debugging",
        path=str(tmp_path / "gpd-debug.md"),
        source_kind="command",
        registry_name="debug",
    )
    portable_paths = {
        "@{GPD_INSTALL_DIR}/workflows/wrapper.md": workflow_path,
        "@{GPD_INSTALL_DIR}/templates/nested-schema.md": schema_path,
        "@{GPD_INSTALL_DIR}/templates/deeper-schema.md": deeper_schema_path,
    }
    original_portable_reference_path = skills_server._portable_reference_path

    def _patched_portable_reference_path(raw_path: str, *, base_path: Path | None = None):
        if raw_path in portable_paths:
            return raw_path, portable_paths[raw_path]
        return original_portable_reference_path(raw_path, base_path=base_path)

    skills_server._reference_document_metadata.cache_clear()
    try:
        with (
            patch("gpd.mcp.servers.skills_server._resolve_skill", return_value=skill),
            patch("gpd.mcp.servers.skills_server.content_registry.get_command", return_value=command),
            patch(
                "gpd.mcp.servers.skills_server._portable_reference_path",
                side_effect=_patched_portable_reference_path,
            ),
        ):
            result = skills_server.get_skill("gpd-debug")
            opt_in_result = skills_server.get_skill("gpd-debug", include_transitive_reference_bodies=True)
    finally:
        skills_server._reference_document_metadata.cache_clear()

    nested_doc = next(entry for entry in result["transitive_schema_documents"] if entry["name"] == "nested-schema.md")
    opt_in_nested_doc = next(
        entry for entry in opt_in_result["transitive_schema_documents"] if entry["name"] == "nested-schema.md"
    )

    assert nested_doc["frontmatter"] == {"type": "schema"}
    assert "body" not in nested_doc
    assert all(not path.endswith("deeper-schema.md") for path in result["transitive_schema_references"])
    assert any(path.endswith("deeper-schema.md") for path in opt_in_result["transitive_schema_references"])
    assert "# Nested Schema" in opt_in_nested_doc["body"]


def test_get_skill_plan_checker_agent_surfaces_direct_schema_dependency_and_least_privilege(
    tmp_path, monkeypatch
) -> None:
    from functools import lru_cache
    from shutil import copytree

    from gpd import registry as content_registry
    from gpd.mcp.servers.skills_server import get_skill

    agents_dir = tmp_path / "agents"
    copytree(Path(__file__).resolve().parents[2] / "src" / "gpd" / "agents", agents_dir)
    plan_checker_path = agents_dir / "gpd-plan-checker.md"
    plan_checker_text = plan_checker_path.read_text(encoding="utf-8")
    plan_checker_text = plan_checker_text.replace(
        "artifact_write_authority: return_only",
        "artifact_write_authority: read_only",
    )
    plan_checker_path.write_text(
        plan_checker_text.replace(
            "tools: file_read, file_write, shell, find_files, search_files, web_search, web_fetch",
            "tools: file_read, shell, find_files, search_files, web_search, web_fetch",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(content_registry, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(
        content_registry,
        "_builtin_agent_names",
        lru_cache(maxsize=1)(lambda: frozenset()),
    )
    content_registry.invalidate_cache()

    result = get_skill("gpd-plan-checker")
    schema_documents = {Path(entry["path"]).name: entry for entry in result["schema_documents"]}

    assert result["allowed_tools_surface"] == "agent.tools"
    assert "file_write" not in result["allowed_tools"]
    assert any(path.endswith("plan-contract-schema.md") for path in result["schema_references"])
    assert "@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md" in result["content"]
    assert "plan-contract-schema.md" in schema_documents
    assert "PLAN Contract Schema" in schema_documents["plan-contract-schema.md"]["body"]


def test_skills_server_import_is_resilient_to_registry_index_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        registry_module,
        "list_skills",
        lambda: (_ for _ in ()).throw(ValueError("boom")),
    )
    sys.modules.pop("gpd.mcp.servers.skills_server", None)

    module = importlib.import_module("gpd.mcp.servers.skills_server")

    assert hasattr(module, "list_skills")
    assert hasattr(module, "get_skill")
