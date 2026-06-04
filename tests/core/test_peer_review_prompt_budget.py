"""Prompt budget assertions for the `peer-review` startup surface."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.workflow_staging import validate_workflow_stage_manifest_payload
from tests.prompt_metrics_support import expanded_prompt_text, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"


def _expanded_stage_surface(stage: object, *, selected_conditions: tuple[str, ...] = ()) -> str:
    authority_paths = stage.eager_authorities(selected_conditions=selected_conditions)
    return "\n\n".join(
        expanded_prompt_text(
            SOURCE_ROOT / "specs" / authority,
            src_root=SOURCE_ROOT,
            path_prefix=PATH_PREFIX,
        )
        for authority in authority_paths
    )


def _conditional_authorities_by_when(stage: object) -> dict[str, tuple[str, ...]]:
    return {conditional.when: conditional.authorities for conditional in stage.conditional_authorities}


def test_peer_review_command_stays_thin_and_only_eagerly_loads_bootstrap_authority() -> None:
    command_text = (COMMANDS_DIR / "peer-review.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        COMMANDS_DIR / "peer-review.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    bootstrap = measure_prompt_surface(
        WORKFLOWS_DIR / "peer-review" / "bootstrap.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    expanded_command = expanded_prompt_text(
        COMMANDS_DIR / "peer-review.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert "@{GPD_INSTALL_DIR}/workflows/peer-review/bootstrap.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/peer-review.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/publication/peer-review-panel.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/paper-config-schema.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/review-ledger-schema.md" not in command_text
    assert "Follow the included bootstrap authority exactly." in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md" not in expanded_command
    assert "Canonical manuscript-root publication preflight." not in expanded_command
    assert "@{GPD_INSTALL_DIR}/references/publication/peer-review-panel.md" not in expanded_command
    assert "review-ledger-schema.md" not in expanded_command
    assert "proof-redteam-protocol.md" not in expanded_command
    assert metrics.expanded_line_count > bootstrap.expanded_line_count
    assert metrics.expanded_char_count > bootstrap.expanded_char_count
    assert metrics.expanded_line_count < bootstrap.expanded_line_count + 250
    assert metrics.expanded_char_count < 30000


def test_peer_review_workflow_defers_stage_authorities_until_the_manifest_stages_need_them() -> None:
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "peer-review-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="peer-review",
    )

    assert manifest.stage_ids() == (
        "bootstrap",
        "preflight",
        "artifact_discovery",
        "panel_stages",
        "final_adjudication",
        "finalize",
    )

    bootstrap = manifest.stages[0]
    preflight = manifest.stages[1]
    artifact_discovery = manifest.stages[2]
    panel_execution = manifest.stages[3]
    final_adjudication = manifest.stages[4]
    finalize = manifest.stages[5]

    assert bootstrap.loaded_authorities == ("workflows/peer-review/bootstrap.md",)
    assert "workflows/peer-review.md" in bootstrap.must_not_eager_load
    assert "workflows/peer-review/panel-stages.md" in bootstrap.must_not_eager_load
    assert "workflows/peer-review/final-adjudication.md" in bootstrap.must_not_eager_load
    assert "workflows/peer-review/finalize.md" in bootstrap.must_not_eager_load
    assert "references/publication/publication-review-round-artifacts.md" in bootstrap.must_not_eager_load
    assert "references/publication/publication-response-artifacts.md" in bootstrap.must_not_eager_load
    assert "references/publication/peer-review-panel.md" in bootstrap.must_not_eager_load
    assert "references/publication/peer-review-reliability.md" in bootstrap.must_not_eager_load
    assert "references/verification/core/proof-redteam-protocol.md" in bootstrap.must_not_eager_load
    assert "templates/paper/paper-config-schema.md" in bootstrap.must_not_eager_load
    assert "templates/paper/artifact-manifest-schema.md" in bootstrap.must_not_eager_load
    assert "templates/paper/bibliography-audit-schema.md" in bootstrap.must_not_eager_load
    assert "templates/paper/reproducibility-manifest.md" in bootstrap.must_not_eager_load
    assert "templates/paper/review-ledger-schema.md" in bootstrap.must_not_eager_load
    assert "templates/paper/referee-decision-schema.md" in bootstrap.must_not_eager_load

    assert preflight.loaded_authorities == (
        "workflows/peer-review/preflight.md",
        "templates/paper/publication-manuscript-root-preflight.md",
    )
    assert _conditional_authorities_by_when(preflight) == {
        "review_integrity_recovery_needed": ("references/publication/peer-review-reliability.md",),
        "manual_publication_artifact_validation": (
            "templates/paper/paper-config-schema.md",
            "templates/paper/artifact-manifest-schema.md",
            "templates/paper/bibliography-audit-schema.md",
            "templates/paper/reproducibility-manifest.md",
        ),
    }
    assert "references/publication/peer-review-reliability.md" in preflight.must_not_eager_load
    assert "templates/paper/artifact-manifest-schema.md" in preflight.must_not_eager_load
    assert "protocol_bundle_context" not in preflight.required_init_fields
    assert "active_reference_context" not in preflight.required_init_fields
    assert "reference_artifacts_content" not in preflight.required_init_fields
    assert {"protocol_bundle_context", "active_reference_context"}.isdisjoint(bootstrap.required_init_fields)
    assert "reference_artifacts_content" not in artifact_discovery.required_init_fields
    assert "reference_artifacts_content" not in final_adjudication.required_init_fields
    assert {
        "project_contract",
        "reference_artifacts_content",
        "active_reference_context",
        "protocol_bundle_context",
    }.isdisjoint(panel_execution.required_init_fields)
    assert {
        "selected_protocol_bundle_ids",
        "protocol_bundle_load_manifest",
        "reference_artifact_files",
    } <= set(panel_execution.required_init_fields)
    assert artifact_discovery.loaded_authorities == (
        "workflows/peer-review/artifact-discovery.md",
        "references/publication/publication-review-round-artifacts.md",
        "references/publication/publication-response-artifacts.md",
    )
    assert panel_execution.loaded_authorities == (
        "workflows/peer-review/panel-stages.md",
        "references/publication/peer-review-panel.md",
    )
    assert _conditional_authorities_by_when(panel_execution) == {
        "panel_rubric_expansion_needed": ("references/publication/peer-review-panel-playbook.md",),
        "panel_child_recovery_needed": ("references/publication/stage-recovery-gate.md",),
        "theorem_bearing_claims_present": (
            "references/verification/core/proof-redteam-workflow-gate.md",
            "references/verification/core/proof-redteam-protocol.md",
            "templates/proof-redteam-schema.md",
        ),
    }
    assert "references/publication/stage-recovery-gate.md" in panel_execution.must_not_eager_load
    assert "references/publication/peer-review-panel-playbook.md" in panel_execution.must_not_eager_load
    assert "references/verification/core/proof-redteam-protocol.md" in panel_execution.must_not_eager_load
    assert "workflows/peer-review/final-adjudication.md" in final_adjudication.loaded_authorities
    assert "references/publication/publication-final-adjudication-boundary.md" in final_adjudication.loaded_authorities
    assert "references/publication/peer-review-panel.md" not in final_adjudication.loaded_authorities
    assert _conditional_authorities_by_when(final_adjudication) == {
        "upstream_stage_artifact_index_needed": ("references/publication/peer-review-panel.md",)
    }
    assert "references/publication/peer-review-panel.md" in final_adjudication.must_not_eager_load
    assert "references/publication/peer-review-panel-playbook.md" not in final_adjudication.loaded_authorities
    assert "templates/paper/review-ledger-schema.md" in final_adjudication.loaded_authorities
    assert "templates/paper/referee-decision-schema.md" in final_adjudication.loaded_authorities
    assert finalize.loaded_authorities == (
        "workflows/peer-review/finalize.md",
        "references/publication/publication-review-round-artifacts.md",
        "references/publication/publication-response-artifacts.md",
        "references/publication/publication-response-writer-handoff.md",
    )


def test_peer_review_panel_stage_eager_surface_stays_below_phase5_cap() -> None:
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "peer-review-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="peer-review",
    )
    panel_stage = manifest.stage("panel_stages")
    final_adjudication = manifest.stage("final_adjudication")

    panel_surface = _expanded_stage_surface(panel_stage)
    final_surface = _expanded_stage_surface(final_adjudication)
    panel_with_playbook = _expanded_stage_surface(
        panel_stage,
        selected_conditions=("panel_rubric_expansion_needed",),
    )

    assert len(panel_surface) <= 21_000
    assert "# Peer Review Panel Contract" in panel_surface
    assert "# Peer Review Panel Playbook" not in panel_surface
    assert "# Peer Review Panel Playbook" in panel_with_playbook
    assert "# Peer Review Panel Playbook" not in final_surface
