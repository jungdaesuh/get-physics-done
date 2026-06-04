"""Stage-manifest assertions for the `research-phase` startup surface."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.workflow_staging import validate_workflow_stage_manifest_payload
from tests.prompt_metrics_support import measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"


def test_research_phase_stage_manifest_tracks_visible_runtime_delegation_authority() -> None:
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "research-phase-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="research-phase",
    )

    assert manifest.stage_ids() == (
        "phase_bootstrap",
        "research_handoff",
    )

    bootstrap = manifest.stage("phase_bootstrap")
    handoff = manifest.stage("research_handoff")

    assert bootstrap.loaded_authorities == (
        "workflows/research-phase/phase-bootstrap.md",
        "references/orchestration/model-profile-resolution.md",
    )
    assert "workflows/research-phase.md" in bootstrap.must_not_eager_load
    assert "workflows/research-phase/research-handoff.md" in bootstrap.must_not_eager_load
    assert "references/orchestration/runtime-delegation-note.md" in bootstrap.must_not_eager_load
    assert "reference_artifacts_content" not in bootstrap.required_init_fields

    assert handoff.loaded_authorities == (
        "workflows/research-phase/research-handoff.md",
        "references/orchestration/model-profile-resolution.md",
        "references/orchestration/runtime-delegation-note.md",
    )
    assert "effective_reference_intake" in handoff.required_init_fields
    assert "reference_artifact_files" in handoff.required_init_fields
    assert "active_references" in handoff.required_init_fields
    assert "selected_protocol_bundle_ids" in handoff.required_init_fields
    assert "protocol_bundle_load_manifest" in handoff.required_init_fields
    assert "protocol_bundle_verifier_extensions" in handoff.required_init_fields
    assert "active_reference_context" not in handoff.required_init_fields
    assert "reference_artifacts_content" not in handoff.required_init_fields
    assert "protocol_bundle_context" not in handoff.required_init_fields
    assert "state_content" not in handoff.required_init_fields
    assert "config_content" not in handoff.required_init_fields
    assert "roadmap_content" not in handoff.required_init_fields
    assert handoff.writes_allowed == ("GPD/phases/XX-name/XX-RESEARCH.md",)


def test_research_phase_prompt_budget_keeps_the_vertical_reasonably_tight() -> None:
    agent_metrics = measure_prompt_surface(
        AGENTS_DIR / "gpd-phase-researcher.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    command_metrics = measure_prompt_surface(
        COMMANDS_DIR / "research-phase.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    workflow_metrics = measure_prompt_surface(
        WORKFLOWS_DIR / "research-phase" / "phase-bootstrap.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert agent_metrics.raw_include_count == 0
    assert agent_metrics.expanded_line_count <= 600
    assert agent_metrics.expanded_char_count <= 22000
    assert agent_metrics.expanded_char_count < 130000
    assert command_metrics.raw_include_count == 1
    assert command_metrics.expanded_line_count <= 440
    assert command_metrics.expanded_char_count < 20000
    assert workflow_metrics.expanded_line_count <= 340
    assert workflow_metrics.expanded_char_count < 15000


def test_research_phase_command_prompt_budget_keeps_delegation_authorities_out_of_the_wrapper() -> None:
    command_text = (COMMANDS_DIR / "research-phase.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        COMMANDS_DIR / "research-phase.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    bootstrap = measure_prompt_surface(
        WORKFLOWS_DIR / "research-phase" / "phase-bootstrap.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert "@{GPD_INSTALL_DIR}/workflows/research-phase/phase-bootstrap.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/research-phase.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/orchestration/model-profile-resolution.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md" not in command_text
    assert bootstrap.raw_include_count == 1
    assert metrics.expanded_line_count > bootstrap.expanded_line_count
    assert metrics.expanded_char_count > bootstrap.expanded_char_count
    assert metrics.expanded_line_count < bootstrap.expanded_line_count + 300
    assert metrics.expanded_char_count < bootstrap.expanded_char_count + 18000
