"""Prompt/spec assertions for settings and project-contract wiring."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.contracts import (
    CONTRACT_CLAIM_KIND_VALUES,
    CONTRACT_REFERENCE_ACTION_VALUES,
    ContractAcceptanceTest,
    ContractClaim,
    ContractDeliverable,
    ContractForbiddenProxy,
    ContractLink,
    ContractObservable,
    ContractReference,
)
from gpd.core.config import GPDProjectConfig, canonical_config_key, effective_config_value
from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, semantic_concept
from tests.markdown_test_support import parse_markdown_table
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
_RUNTIME_DISPLAY_NAMES = tuple(descriptor.display_name for descriptor in iter_runtime_descriptors())


def _step(text: str, name: str) -> str:
    return text.split(f'<step name="{name}">', 1)[1].split("</step>", 1)[0]


def _assert_semantic_contract(
    text: str,
    label: str,
    *,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> None:
    assert_prompt_contracts(
        text,
        *semantic_concept(
            label,
            required=required or None,
            forbidden=forbidden or None,
            match=MatchMode.CASEFOLD_NORMALIZED,
            context=label,
        ),
    )


def _assert_model_fields_surface(text: str, collection_name: str, model: type) -> None:
    assert f"`{collection_name}`" in text
    for field_name in model.model_fields:
        assert (
            f'"{field_name}"' in text
            or f'"{field_name}[]"' in text
            or f'"{field_name}?"' in text
            or f"`{field_name}`" in text
        ), field_name


def _settings_rows_by_header(settings_workflow: str) -> dict[str, dict[str, str]]:
    present_settings = _step(settings_workflow, "present_settings")
    table = parse_markdown_table(present_settings, context="settings choices")
    return {row["Header"]: row for row in table.rows}


def test_new_project_scope_approval_surfaces_contract_schema_without_restating_it() -> None:
    workflow_text = (WORKFLOWS_DIR / "new-project/scope-approval.md").read_text(encoding="utf-8")
    project_contract_schema_text = expand_at_includes(
        (TEMPLATES_DIR / "project-contract-schema.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd/specs",
        "/runtime/",
    )

    assert "templates/project-contract-schema.md" in workflow_text
    assert "templates/state-json-schema.md" not in workflow_text
    assert "Follow the schema exactly" in workflow_text
    for collection_name, model in (
        ("observables[]", ContractObservable),
        ("claims[]", ContractClaim),
        ("deliverables[]", ContractDeliverable),
        ("acceptance_tests[]", ContractAcceptanceTest),
        ("references[]", ContractReference),
        ("forbidden_proxies[]", ContractForbiddenProxy),
        ("links[]", ContractLink),
    ):
        _assert_model_fields_surface(project_contract_schema_text, collection_name, model)
    for claim_kind in CONTRACT_CLAIM_KIND_VALUES:
        assert claim_kind in project_contract_schema_text
    for action in CONTRACT_REFERENCE_ACTION_VALUES:
        assert f"`{action}`" in project_contract_schema_text
    assert (
        "if `references[].must_surface` is `true`, both `references[].applies_to[]` and "
        "`references[].required_actions[]` must be non-empty"
    ) not in workflow_text
    _assert_semantic_contract(
        project_contract_schema_text,
        "must-surface reference rule",
        required=("must_surface: true", "required_actions", "applies_to", "non-empty"),
    )


def test_settings_and_planning_config_keep_conventions_outside_config_json() -> None:
    settings_command = (COMMANDS_DIR / "settings.md").read_text(encoding="utf-8")
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    planning_config = (REFERENCES_DIR / "planning" / "planning-config.md").read_text(encoding="utf-8")
    workflow_preferences = (WORKFLOWS_DIR / "new-project/workflow-preferences.md").read_text(encoding="utf-8")

    _assert_semantic_contract(
        settings_command + "\n" + settings_workflow,
        "settings keeps convention ownership out of config",
        required=("project conventions", "GPD/config.json", "GPD/state.json", "convention_lock", "GPD/CONVENTIONS.md"),
        forbidden=("physics research preferences", "physics-specific settings"),
    )
    assert '"physics": {' not in planning_config
    _assert_semantic_contract(
        planning_config + "\n" + workflow_preferences,
        "planning config excludes convention physics block",
        required=("project conventions", "config.json", "outside", "physics", "block"),
    )
    assert '"physics": {' not in workflow_preferences


def test_new_project_workflow_preferences_writes_only_existing_config_keys_and_syncs_runtime_permissions() -> None:
    workflow_preferences = (WORKFLOWS_DIR / "new-project/workflow-preferences.md").read_text(encoding="utf-8")
    aggregated_new_project = workflow_authority_text(WORKFLOWS_DIR, "new-project")
    permissions_sync = re.compile(
        r"gpd --raw permissions sync\b"
        r"(?=[^\n]*--runtime \"\$SELECTED_RUNTIME\")"
        r"(?=[^\n]*--autonomy \"\$SELECTED_AUTONOMY\")"
    )

    assert workflow_preferences in aggregated_new_project
    _assert_semantic_contract(
        workflow_preferences,
        "new-project presets resolve only into config keys",
        required=("workflow presets", "existing config keys", "preset block"),
    )
    assert "`SELECTED_RUNTIME`" in workflow_preferences
    assert permissions_sync.search(workflow_preferences)
    assert 'gpd --raw permissions sync --autonomy "$SELECTED_AUTONOMY"' not in workflow_preferences

    for key in (
        "autonomy",
        "research_mode",
        "parallelization",
        "planning.commit_docs",
        "execution.review_cadence",
        "model_profile",
        "workflow.research",
        "workflow.plan_checker",
        "workflow.verifier",
    ):
        assert key in workflow_preferences
        assert canonical_config_key(key) is not None

    forbidden_writes = (
        "gpd config set model_overrides",
        "gpd config set git.branching_strategy",
        "gpd config set execution.max_unattended_minutes_per_plan",
        "gpd config set execution.project_usd_budget",
        "gpd config set execution.session_usd_budget",
        "GPD/init-progress.json",
    )
    for forbidden_write in forbidden_writes:
        assert forbidden_write not in workflow_preferences

    assert (
        "The user can run `gpd:validate-conventions`; the fallback lock must match the values written into `GPD/CONVENTIONS.md`."
        not in workflow_preferences
    )


def test_settings_model_cost_onboarding_stays_qualitative_and_runtime_default_first() -> None:
    settings_command = (COMMANDS_DIR / "settings.md").read_text(encoding="utf-8")
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/settings.md" in settings_command
    _assert_semantic_contract(
        settings_command,
        "settings command stays a thin wrapper",
        required=("wrapper", "thin", "parallel settings flow"),
    )

    rows_by_header = _settings_rows_by_header(settings_workflow)
    assert rows_by_header["Autonomy"]["Options and mapping"].startswith("`Supervised (Recommended)`")
    assert rows_by_header["Tier Models"]["Options and mapping"].count("`") >= 6
    assert "runtime defaults" in settings_workflow
    assert "gpd:set-tier-models" in settings_workflow
    assert "Use runtime defaults" in rows_by_header["Tier Models"]["Options and mapping"]
    assert "Configure explicit tier models" in rows_by_header["Tier Models"]["Options and mapping"]
    assert "tier-1" in settings_workflow
    assert "tier-2" in settings_workflow
    assert "tier-3" in settings_workflow
    assert "dollar" not in settings_workflow.lower()


def test_settings_workflow_surfaces_optional_usd_budget_guardrails_as_advisory_only() -> None:
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")

    assert "project_usd_budget" in settings_workflow
    assert "session_usd_budget" in settings_workflow
    _assert_semantic_contract(
        settings_workflow,
        "optional USD budgets are advisory clearable guardrails",
        required=("advisory", "never stop work automatically", "JSON `null`", "clear", "none", "empty string"),
        forbidden=("Blank / `none` should clear", "live budget enforcement"),
    )


def test_settings_workflow_preset_contract_keeps_runtime_default_tier_model_path_explicit() -> None:
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    rows_by_header = _settings_rows_by_header(settings_workflow)
    tier_row = rows_by_header["Tier Models"]

    assert "gpd:set-tier-models" in settings_workflow
    assert tier_row["Question"] == "How should GPD handle concrete tier models for the active runtime?"
    for option in ("Leave current setting unchanged", "Use runtime defaults", "Configure explicit tier models"):
        assert option in tier_row["Options and mapping"]
    _assert_semantic_contract(
        settings_workflow,
        "runtime default tier overrides clear per tier",
        required=("blank", "runtime default", "none", "no override", "tier"),
    )


def test_settings_workflow_uses_same_selected_runtime_for_models_and_permissions() -> None:
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    permissions_sync = re.compile(
        r"gpd --raw permissions sync\b"
        r"(?=[^\n]*--runtime \"\$SELECTED_RUNTIME\")"
        r"(?=[^\n]*--autonomy \"\$SELECTED_AUTONOMY\")"
    )

    assert "`SELECTED_RUNTIME`" in settings_workflow
    assert "model_overrides.<SELECTED_RUNTIME>" in settings_workflow
    assert permissions_sync.search(settings_workflow)
    assert 'gpd --raw permissions sync --autonomy "$SELECTED_AUTONOMY"' not in settings_workflow


def test_set_tier_models_workflow_keeps_runtime_examples_generic() -> None:
    set_tier_models = (WORKFLOWS_DIR / "set-tier-models.md").read_text(encoding="utf-8")

    for display_name in _RUNTIME_DISPLAY_NAMES:
        assert display_name not in set_tier_models
    assert "gpt-5.4" not in set_tier_models
    _assert_semantic_contract(
        set_tier_models,
        "tier-model examples remain runtime generic",
        required=("runtime-native examples", "not hard-coded"),
    )


def test_settings_workflow_keeps_convention_ownership_outside_settings_and_routes_changes_to_validate_conventions() -> (
    None
):
    settings_command = (COMMANDS_DIR / "settings.md").read_text(encoding="utf-8")
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")

    _assert_semantic_contract(
        settings_command + "\n" + settings_workflow,
        "settings routes convention edits to convention surfaces",
        required=(
            "convention work",
            "outside settings",
            "gpd convention set <key> <value>",
            "gpd:validate-conventions",
            "GPD/state.json",
            "convention_lock",
            "GPD/CONVENTIONS.md",
            "GPD/config.json",
        ),
    )
    assert "gpd:validate-conventions -- verify convention consistency across the project" in settings_workflow
    assert "gpd convention set <key> <value> -- update the locked project conventions directly" in settings_workflow


def test_settings_workflow_writes_canonical_config_keys_through_cli() -> None:
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    update_step = settings_workflow.split('<step name="update_config">', 1)[1].split("</step>", 1)[0]

    assert 'gpd config set autonomy "$SELECTED_AUTONOMY"' in update_step
    assert 'gpd config set workflow.research "$SELECTED_WORKFLOW_RESEARCH"' in update_step
    assert 'gpd config set execution.review_cadence "$SELECTED_REVIEW_CADENCE"' in update_step
    assert 'gpd config set git.branching_strategy "$SELECTED_BRANCHING_STRATEGY"' in update_step
    assert 'gpd config set model_overrides "$MODEL_OVERRIDES_JSON"' in update_step
    assert 'gpd config set git.phase_branch_template "$SELECTED_PHASE_BRANCH_TEMPLATE"' not in update_step
    assert 'gpd config set git.milestone_branch_template "$SELECTED_MILESTONE_BRANCH_TEMPLATE"' not in update_step
    _assert_semantic_contract(
        update_step,
        "settings preserves branch templates while changing strategy",
        required=("preserve", "git.phase_branch_template", "git.milestone_branch_template"),
    )
    table = parse_markdown_table(update_step, context="settings update config keys")
    rows = {row["Config key"].strip("`"): row["Selected variable"].strip("`") for row in table.rows}
    for key, variable in rows.items():
        assert canonical_config_key(key) is not None
        assert variable.startswith("SELECTED_")
        assert effective_config_value(GPDProjectConfig(), key)[0] is True
    for stale_nested_key in ('"planning": {', '"workflow": {', '"execution": {', '"git": {'):
        assert stale_nested_key not in update_step


def test_settings_update_config_selected_variables_are_collected_before_use() -> None:
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    update_step = settings_workflow.split('<step name="update_config">', 1)[1].split("</step>", 1)[0]

    selected_vars_used = set(re.findall(r"\$(SELECTED_[A-Z0-9_]+)\b", update_step))
    selected_vars_collected = set(re.findall(r"- `(SELECTED_[A-Z0-9_]+)`", update_step))

    assert selected_vars_used
    assert selected_vars_used <= selected_vars_collected
    assert "SELECTED_PHASE_BRANCH_TEMPLATE" not in selected_vars_used
    assert "SELECTED_MILESTONE_BRANCH_TEMPLATE" not in selected_vars_used


def test_settings_and_profile_docs_keep_supervised_dense_defaults_consistent() -> None:
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    set_profile_workflow = (WORKFLOWS_DIR / "set-profile.md").read_text(encoding="utf-8")
    continuous_execution = (REFERENCES_DIR / "orchestration" / "continuous-execution.md").read_text(encoding="utf-8")

    _assert_semantic_contract(
        settings_workflow,
        "settings defaults favor supervised dense profile preview",
        required=("core research", "supervised", "default bundle", "schema defaults"),
        forbidden=("balanced default bundle",),
    )

    _assert_semantic_contract(
        set_profile_workflow,
        "profile docs keep dense publication cadence",
        required=("execution.review_cadence=dense", "publication-quality"),
        forbidden=("`execution.review_cadence=adaptive` or `sparse` usually fits",),
    )

    assert "| **Supervised** (default)         | `supervised`" in continuous_execution
    _assert_semantic_contract(
        continuous_execution,
        "supervised is default and auto-advance is opt-in",
        required=("explicit opt-in", "default `supervised` posture", "auto-advance", "balanced", "yolo"),
        forbidden=("The default autonomy setting. The assistant auto-advances",),
    )
