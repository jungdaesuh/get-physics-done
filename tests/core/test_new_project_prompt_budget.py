"""Prompt budget assertions for the `new-project` startup surface."""

from __future__ import annotations

import json
from pathlib import Path

from tests.prompt_metrics_support import expanded_prompt_text, line_number_for_fragment, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
SCOPE_INTAKE_AUTHORITY = WORKFLOWS_DIR / "new-project" / "scope-intake.md"
STAGE_MANIFEST = WORKFLOWS_DIR / "new-project-stage-manifest.json"

MINIMAL_QUESTION = "Describe your research project in one pass"
FULL_QUESTION = "What physics problem do you want to investigate?"
SETUP_QUESTION = "Which starting workflow preset should GPD use for `GPD/config.json`?"


def test_new_project_prompt_surface_uses_first_stage_authority_boundary() -> None:
    new_project = measure_prompt_surface(
        COMMANDS_DIR / "new-project.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
        first_question_fragments=(MINIMAL_QUESTION, FULL_QUESTION, SETUP_QUESTION),
    )
    start = measure_prompt_surface(
        COMMANDS_DIR / "start.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    workflow = measure_prompt_surface(
        WORKFLOWS_DIR / "new-project.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert new_project.raw_include_count == 1
    assert start.raw_include_count > 0
    assert new_project.expanded_line_count < start.expanded_line_count
    assert new_project.expanded_char_count < start.expanded_char_count
    assert workflow.raw_include_count == 1
    assert workflow.expanded_line_count < 80
    assert workflow.expanded_char_count < 5_000
    assert new_project.raw_include_count == 1
    assert new_project.first_question_line is not None
    assert new_project.first_question_marker == MINIMAL_QUESTION


def _new_project_stage(stage_id: str) -> dict:
    payload = json.loads(STAGE_MANIFEST.read_text(encoding="utf-8"))
    stage = dict(next(stage for stage in payload["stages"] if stage["id"] == stage_id))
    if "required_init_fields" not in stage:
        groups = payload.get("required_init_field_groups", {})
        fields: list[str] = []
        for group_name in stage.get("required_init_field_groups", []):
            fields.extend(groups.get(group_name, []))
        stage["required_init_fields"] = list(dict.fromkeys(fields))
    return stage


def _expanded_stage_surface(stage: dict) -> str:
    authority_paths = list(dict.fromkeys([*stage["mode_paths"], *stage["loaded_authorities"]]))
    return "\n\n".join(
        expanded_prompt_text(
            SOURCE_ROOT / "specs" / authority,
            src_root=SOURCE_ROOT,
            path_prefix=PATH_PREFIX,
        )
        for authority in authority_paths
    )


def test_new_project_scope_intake_authority_owns_first_question_without_deep_setup_questions() -> None:
    scope_text = SCOPE_INTAKE_AUTHORITY.read_text(encoding="utf-8")

    minimal_line = line_number_for_fragment(scope_text, MINIMAL_QUESTION)
    full_line = line_number_for_fragment(scope_text, FULL_QUESTION)
    setup_line = line_number_for_fragment(scope_text, SETUP_QUESTION)

    assert minimal_line is not None
    assert full_line is None
    assert setup_line is None


def test_new_project_scope_intake_stage_surface_cannot_see_post_scope_machinery() -> None:
    stage = _new_project_stage("scope_intake")
    stage_surface = _expanded_stage_surface(stage)

    assert stage["mode_paths"] == ["workflows/new-project/scope-intake.md"]
    assert stage["loaded_authorities"] == ["workflows/new-project/scope-intake.md"]
    assert "researcher_model" not in stage["required_init_fields"]
    assert "synthesizer_model" not in stage["required_init_fields"]
    assert "roadmapper_model" not in stage["required_init_fields"]
    assert MINIMAL_QUESTION in stage_surface
    assert "Existing Research" in stage_surface
    assert "gpd --raw init new-project --stage scope_intake" in stage_surface

    for forbidden in (
        "POST_SCOPE_INIT",
        ">>> Spawning 4 literature scouts",
        "gpd-roadmapper",
        "gpd-notation-coordinator",
        "Workflow Setup",
        "templates/project.md",
        "templates/requirements.md",
        "references/ui/ui-brand.md",
        "GPD/literature",
        "GPD/CONVENTIONS.md",
    ):
        assert forbidden not in stage_surface


def test_new_project_workflow_preset_gate_is_after_scope_and_before_project_artifacts() -> None:
    command_text = (COMMANDS_DIR / "new-project.md").read_text(encoding="utf-8")
    scope_surface = _expanded_stage_surface(_new_project_stage("scope_intake"))
    prefs_stage = _new_project_stage("workflow_preferences")
    project_stage = _new_project_stage("project_artifacts")
    prefs_surface = _expanded_stage_surface(prefs_stage)
    project_surface = _expanded_stage_surface(project_stage)

    assert SETUP_QUESTION not in scope_surface
    assert "Workflow Setup" not in scope_surface
    assert SETUP_QUESTION in prefs_surface
    assert "after scope approval and before\n`project_artifacts`" in prefs_surface
    assert prefs_stage["writes_allowed"] == ["GPD/config.json"]
    assert prefs_stage["next_stages"] == ["project_artifacts"]
    assert "If `GPD/config.json` is missing" in project_surface
    assert "gpd --raw init new-project --stage workflow_preferences" in project_surface
    assert project_stage["next_stages"] == ["literature_survey"]
    assert "before workflow preferences or before the first project-artifact commit" not in command_text


def test_new_project_minimal_artifacts_stage_surface_excludes_deferred_full_machinery() -> None:
    stage = _new_project_stage("minimal_artifacts")
    stage_surface = _expanded_stage_surface(stage)

    assert stage["mode_paths"] == ["workflows/new-project/minimal-artifacts.md"]
    assert stage["loaded_authorities"] == ["workflows/new-project/minimal-artifacts.md"]
    assert "researcher_model" not in stage["required_init_fields"]
    assert "synthesizer_model" not in stage["required_init_fields"]
    assert "roadmapper_model" not in stage["required_init_fields"]

    core_outputs = {
        "GPD/PROJECT.md",
        "GPD/config.json",
        "GPD/REQUIREMENTS.md",
        "GPD/ROADMAP.md",
        "GPD/STATE.md",
        "GPD/state.json",
    }
    assert core_outputs <= set(stage["writes_allowed"])
    assert "docs: initialize research project (minimal)" in stage_surface
    assert "MINIMAL_ARTIFACTS_INIT=$(gpd --raw init new-project --stage minimal_artifacts)" in stage_surface
    assert "Do not delegate this file to a later roadmap authority in minimal mode." in stage_surface

    forbidden_authorities = {
        "workflows/new-project.md",
        "workflows/new-project/literature-survey.md",
        "workflows/new-project/roadmap-authoring.md",
        "workflows/new-project/conventions-handoff.md",
        "references/ui/ui-brand.md",
    }
    assert forbidden_authorities.isdisjoint(stage["mode_paths"])
    assert forbidden_authorities.isdisjoint(stage["loaded_authorities"])

    for forbidden in (
        ">>> Spawning 4 literature scouts",
        "gpd-project-researcher",
        "gpd-research-synthesizer",
        "gpd-roadmapper",
        "gpd-notation-coordinator",
        "literature survey",
        "GPD/literature",
        "GPD/CONVENTIONS.md",
        "workflows/new-project/literature-survey.md",
        "workflows/new-project/roadmap-authoring.md",
        "workflows/new-project/conventions-handoff.md",
        "references/ui/ui-brand.md",
    ):
        assert forbidden not in stage_surface


def test_new_project_command_no_longer_eagerly_inlines_late_stage_authorities() -> None:
    command_text = (COMMANDS_DIR / "new-project.md").read_text(encoding="utf-8")
    expanded_command = expanded_prompt_text(
        COMMANDS_DIR / "new-project.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert "@{GPD_INSTALL_DIR}/references/research/questioning.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/project-contract-schema.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/project.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/requirements.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/ui/ui-brand.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/shared/canonical-schema-discipline.md" not in expanded_command
    assert "<questioning_guide>" not in expanded_command
    assert "# Canonical Schema Discipline" not in expanded_command
    assert "# PROJECT.md Template" not in expanded_command
    assert "# Requirements Template" not in expanded_command
    assert "<ui_patterns>" not in expanded_command
