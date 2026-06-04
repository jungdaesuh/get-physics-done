"""Stage-contract assertions for the `map-research` workflow."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.workflow_staging import validate_workflow_stage_manifest_payload
from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact, semantic_anchor
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def test_map_research_stage_manifest_defers_heavy_context_and_tracks_visible_delegation() -> None:
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "map-research-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="map-research",
    )

    assert manifest.stage_ids() == (
        "map_bootstrap",
        "mapper_authoring",
    )

    bootstrap = manifest.stage("map_bootstrap")
    authoring = manifest.stage("mapper_authoring")

    assert bootstrap.loaded_authorities == ("workflows/map-research/map-bootstrap.md",)
    assert "project_root" in bootstrap.required_init_fields
    assert "project_root_source" in bootstrap.required_init_fields
    assert "project_root_auto_selected" in bootstrap.required_init_fields
    assert "workspace_root" in bootstrap.required_init_fields
    assert "research_map_dir_absolute" in bootstrap.required_init_fields
    assert "reference_artifacts_content" not in bootstrap.required_init_fields
    assert "workflows/map-research.md" in bootstrap.must_not_eager_load
    assert "workflows/map-research/mapper-authoring.md" in bootstrap.must_not_eager_load
    assert "references/orchestration/runtime-delegation-note.md" in bootstrap.must_not_eager_load
    assert bootstrap.writes_allowed == (
        "GPD/research-map",
        "GPD/research-map.archive-*",
    )

    assert authoring.loaded_authorities == (
        "workflows/map-research/mapper-authoring.md",
        "references/orchestration/runtime-delegation-note.md",
    )
    assert "effective_reference_intake" in authoring.required_init_fields
    assert "reference_artifact_files" in authoring.required_init_fields
    assert "active_references" in authoring.required_init_fields
    assert "selected_protocol_bundle_ids" in authoring.required_init_fields
    assert "protocol_bundle_load_manifest" in authoring.required_init_fields
    assert "protocol_bundle_verifier_extensions" in authoring.required_init_fields
    assert "active_reference_context" not in authoring.required_init_fields
    assert "reference_artifacts_content" not in authoring.required_init_fields
    assert "protocol_bundle_context" not in authoring.required_init_fields
    assert "GPD/research-map/FORMALISM.md" in authoring.writes_allowed
    assert "GPD/research-map/CONCERNS.md" in authoring.writes_allowed


def test_map_research_workflow_uses_project_rooted_map_targets_for_side_effects() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "map-research")

    assert 'PROJECT_ROOT=$(echo "$BOOTSTRAP_INIT" | gpd json get .project_root --default "")' in text
    assert (
        'RESEARCH_MAP_DIR_ABS=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_map_dir_absolute --default "")' in text
    )
    assert 'mkdir -p "$RESEARCH_MAP_DIR_ABS"' in text
    assert 'mv "$RESEARCH_MAP_DIR_ABS" "$RESEARCH_MAP_ARCHIVE_DIR"' in text
    assert 'ls -la "$RESEARCH_MAP_DIR_ABS/"' in text
    assert 'gpd --cwd "$PROJECT_ROOT" commit "docs: map existing research project" --files "$RESEARCH_MAP_DIR"' in text
    assert "option_id: refresh_archive" in text
    assert "option_id: update_selected" in text
    assert "option_id: skip_existing" in text
    assert_prompt_contracts(
        text,
        machine_exact(
            "map-research menu routes by option_id field",
            "route by exact `option_id`, not option number or label",
        ),
        semantic_anchor(
            "update-selected route only delegates selected map documents",
            (
                "selected documents",
                "`UPDATE_SELECTED_DOCS`",
                "spawn only slices",
                "selected documents",
                "unselected map",
                "fail closed",
            ),
        ),
    )
    assert "Delete GPD/research-map" not in text
    assert "mkdir -p GPD/research-map" not in text
    assert "rm -rf GPD/research-map" not in text
