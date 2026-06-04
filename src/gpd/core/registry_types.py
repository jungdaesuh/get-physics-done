"""Shared dataclasses for the GPD content registry facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from gpd.core.workflow_staging import WorkflowStageManifest

CommandNameFormat = Literal["slug", "label"]


@dataclass(frozen=True, slots=True)
class AgentDef:
    """Parsed agent definition from a .md file."""

    name: str
    description: str
    system_prompt: str
    tools: list[str]
    color: str
    path: str
    source: str  # "agents"
    commit_authority: str = "orchestrator"
    surface: str = "internal"
    role_family: str = "analysis"
    artifact_write_authority: str = "scoped_write"
    shared_state_authority: str = "return_only"
    role_kits: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandHelpVariant:
    """Display-only documented variant for a registry command."""

    command: str
    description: str
    examples: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandHelpMetadata:
    """Display-only help metadata parsed from command frontmatter."""

    group: str
    order: int
    compact_description: str | None = None
    display_signature: str | None = None
    detail_signature: str | None = None
    examples: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    root_detail_order: int | None = None
    variants: tuple[CommandHelpVariant, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandDef:
    """Parsed command/skill definition from a .md file."""

    name: str
    description: str
    argument_hint: str
    requires: dict[str, object]
    allowed_tools: list[str]
    content: str
    path: str
    source: str  # "commands"
    context_mode: str = "project-required"
    project_reentry_capable: bool = False
    command_policy: CommandPolicy | None = None
    review_contract: ReviewCommandContract | None = None
    help: CommandHelpMetadata | None = None
    agent: str | None = None
    staged_loading: WorkflowStageManifest | None = None
    spawn_contracts: tuple[dict[str, object], ...] = ()
    interactive_spawn_contracts: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class CommandSubjectPolicy:
    """Typed command subject-resolution policy."""

    subject_kind: str | None = None
    resolution_mode: str | None = None
    explicit_input_kinds: list[str] = field(default_factory=list)
    allow_external_subjects: bool | None = None
    allow_interactive_without_subject: bool | None = None
    supported_roots: list[str] = field(default_factory=list)
    allowed_suffixes: list[str] = field(default_factory=list)
    bootstrap_allowed: bool | None = None


@dataclass(frozen=True, slots=True)
class CommandSupportingContextPolicy:
    """Typed command supporting-context policy."""

    project_context_mode: str | None = None
    project_reentry_mode: str | None = None
    required_file_patterns: list[str] = field(default_factory=list)
    optional_file_patterns: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CommandOutputPolicy:
    """Typed command output policy."""

    output_mode: str | None = None
    managed_root_kind: str | None = None
    default_output_subtree: str | None = None
    stage_artifact_policy: str | None = None


@dataclass(frozen=True, slots=True)
class CommandPolicy:
    """Typed additive command policy compiled from frontmatter and companion fields."""

    schema_version: int = 1
    subject_policy: CommandSubjectPolicy | None = None
    supporting_context_policy: CommandSupportingContextPolicy | None = None
    output_policy: CommandOutputPolicy | None = None


@dataclass(frozen=True, slots=True)
class ReviewContractConditionalRequirement:
    """Condition-scoped review-contract requirements."""

    when: str
    required_outputs: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    blocking_conditions: list[str] = field(default_factory=list)
    preflight_checks: list[str] = field(default_factory=list)
    blocking_preflight_checks: list[str] = field(default_factory=list)
    stage_artifacts: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReviewContractScopeVariant:
    """Scope-specific review-contract overrides and relaxed preflight metadata."""

    scope: str
    activation: str
    relaxed_preflight_checks: list[str] = field(default_factory=list)
    optional_preflight_checks: list[str] = field(default_factory=list)
    required_outputs_override: list[str] = field(default_factory=list)
    required_evidence_override: list[str] = field(default_factory=list)
    blocking_conditions_override: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReviewCommandContract:
    """Typed orchestration contract for review-grade commands."""

    review_mode: str
    required_outputs: list[str]
    required_evidence: list[str]
    blocking_conditions: list[str]
    preflight_checks: list[str]
    stage_artifacts: list[str] = field(default_factory=list)
    conditional_requirements: list[ReviewContractConditionalRequirement] = field(default_factory=list)
    scope_variants: list[ReviewContractScopeVariant] = field(default_factory=list)
    required_state: str = ""
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class SkillDef:
    """Canonical skill exposure derived from primary commands and agents."""

    name: str
    description: str
    content: str
    category: str
    path: str
    source_kind: str  # "command" or "agent"
    registry_name: str
    spawn_contracts: tuple[dict[str, object], ...] = ()
    interactive_spawn_contracts: tuple[dict[str, object], ...] = ()


__all__ = [
    "AgentDef",
    "CommandDef",
    "CommandHelpMetadata",
    "CommandHelpVariant",
    "CommandNameFormat",
    "CommandOutputPolicy",
    "CommandPolicy",
    "CommandSubjectPolicy",
    "CommandSupportingContextPolicy",
    "ReviewCommandContract",
    "ReviewContractConditionalRequirement",
    "ReviewContractScopeVariant",
    "SkillDef",
]
