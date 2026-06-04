"""Prompt budget assertions for the `new-milestone` startup surface."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from gpd.core.child_handoff import ChildGateTuple, child_gate_tuple_from_payload
from gpd.core.workflow_staging import validate_workflow_stage_manifest_payload
from tests.prompt_metrics_support import measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
SURVEY_AUTHORITY = WORKFLOWS_DIR / "new-milestone" / "survey-objectives.md"
ROADMAP_AUTHORITY = WORKFLOWS_DIR / "new-milestone" / "roadmap-authoring.md"


def _new_milestone_manifest():
    return validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "new-milestone-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="new-milestone",
    )


def _child_gate(source: str, gate_id: str) -> ChildGateTuple:
    for block in source.split("```yaml")[1:]:
        yaml_text = block.split("```", 1)[0]
        payload = yaml.safe_load(yaml_text)
        if not isinstance(payload, dict):
            continue
        child_gate = payload.get("child_gate")
        if isinstance(child_gate, dict) and child_gate.get("id") == gate_id:
            return child_gate_tuple_from_payload(payload)
    raise AssertionError(f"missing child gate {gate_id}")


def _artifact_paths(gate: ChildGateTuple) -> tuple[str, ...]:
    return tuple(artifact.path for artifact in gate.expected_artifacts)


def test_new_milestone_command_stays_thin_and_only_eagerly_loads_the_workflow() -> None:
    command_text = (COMMANDS_DIR / "new-milestone.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        COMMANDS_DIR / "new-milestone.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert "@{GPD_INSTALL_DIR}/workflows/new-milestone/milestone-bootstrap.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/new-milestone.md" not in command_text
    assert "Project contract gate:" not in command_text
    assert "Project contract load info:" not in command_text
    assert "Project contract validation:" not in command_text
    assert "expected_artifacts:" not in command_text
    assert "shared_state_policy:" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/research/questioning.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/ui/ui-brand.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/project.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/requirements.md" not in command_text
    assert "The workflow handles the full milestone initialization flow:" not in command_text
    assert "Load local late authorities only at matching stages" in command_text
    assert "questioning reference for guided milestone questions" in command_text
    assert "project/requirements templates for those writes" in command_text
    assert "UI brand for completion or status blocks" in command_text


def test_new_milestone_command_budget_tracks_the_workflow_without_wrapper_bloat() -> None:
    command = measure_prompt_surface(
        COMMANDS_DIR / "new-milestone.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    bootstrap = measure_prompt_surface(
        WORKFLOWS_DIR / "new-milestone" / "milestone-bootstrap.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert command.expanded_line_count < bootstrap.expanded_line_count + 120
    assert command.expanded_char_count < bootstrap.expanded_char_count + 4000
    assert command.expanded_char_count < 9000


def test_new_milestone_child_gates_preserve_artifact_contracts() -> None:
    survey = SURVEY_AUTHORITY.read_text(encoding="utf-8")
    roadmap_source = ROADMAP_AUTHORITY.read_text(encoding="utf-8")
    scouts = _child_gate(survey, "milestone_literature_scouts")
    synthesizer = _child_gate(survey, "milestone_literature_synthesizer")
    roadmapper = _child_gate(roadmap_source, "milestone_roadmapper")

    assert _artifact_paths(scouts) == (
        "GPD/literature/PRIOR-WORK.md",
        "GPD/literature/METHODS.md",
        "GPD/literature/COMPUTATIONAL.md",
        "GPD/literature/PITFALLS.md",
    )
    assert scouts.allowed_roots == ("GPD/literature",)
    assert scouts.freshness is not None
    assert scouts.freshness.marker == "$SCOUT_HANDOFF_STARTED_AT per scout"

    assert _artifact_paths(synthesizer) == ("GPD/literature/SUMMARY.md",)
    assert synthesizer.allowed_roots == ("GPD/literature",)
    assert synthesizer.freshness is not None
    assert synthesizer.freshness.marker == "$SYNTHESIZER_HANDOFF_STARTED_AT"

    assert _artifact_paths(roadmapper) == ("GPD/ROADMAP.md", "GPD/REQUIREMENTS.md")
    assert roadmapper.allowed_roots == ("GPD",)
    assert roadmapper.applicator.command.startswith("main workflow applies accepted state changes")
    assert roadmapper.applicator.require_passed_true is False


def test_new_milestone_planning_stages_use_handles_instead_of_embedded_bodies() -> None:
    manifest = _new_milestone_manifest()
    survey = manifest.stage("survey_objectives")
    roadmap = manifest.stage("roadmap_authoring")

    required_handle_fields = {
        "contract_intake",
        "effective_reference_intake",
        "reference_artifact_files",
        "literature_review_files",
        "research_map_reference_files",
    }
    removed_body_fields = {
        "active_reference_context",
        "project_content",
        "state_content",
        "milestones_content",
        "requirements_content",
        "roadmap_content",
    }

    assert required_handle_fields <= set(survey.required_init_fields)
    assert required_handle_fields <= set(roadmap.required_init_fields)
    assert removed_body_fields.isdisjoint(survey.required_init_fields)
    assert removed_body_fields.isdisjoint(roadmap.required_init_fields)

    survey_source = SURVEY_AUTHORITY.read_text(encoding="utf-8")
    roadmap_source = ROADMAP_AUTHORITY.read_text(encoding="utf-8")
    assert "<files_to_read>" in survey_source
    assert "ROADMAPPER_INIT.staged_loading.field_access_instruction" in roadmap_source
    assert "stage field-access new-milestone --stage roadmap_authoring --style instruction" not in roadmap_source
    assert "reference_artifact_files" in roadmap_source
    assert "Project content: {project_content}" not in survey_source
    assert "Project content: {project_content}" not in roadmap_source
    assert "Active references: {active_reference_context}" not in survey_source
    assert "Active references: {active_reference_context}" not in roadmap_source
