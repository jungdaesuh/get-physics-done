"""Prompt budget assertions for the `respond-to-referees` startup surface."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from gpd.core.workflow_staging import validate_workflow_stage_manifest_payload
from tests.prompt_metrics_support import expanded_prompt_text, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
RESPOND_STAGE_DIR = WORKFLOWS_DIR / "respond-to-referees"
BOOTSTRAP_AUTHORITY = RESPOND_STAGE_DIR / "bootstrap.md"


def _manifest() -> object:
    return validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "respond-to-referees-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="respond-to-referees",
    )


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


def _yaml_gate_payload(source: str, key: str, gate_id: str) -> dict:
    for block in source.split("```yaml")[1:]:
        yaml_text = block.split("```", 1)[0]
        payload = yaml.safe_load(yaml_text)
        if not isinstance(payload, dict):
            continue
        gate = payload.get(key)
        if isinstance(gate, dict) and gate.get("id") == gate_id:
            return gate
    raise AssertionError(f"missing {key} {gate_id}")


def test_respond_to_referees_command_uses_first_stage_authority_boundary() -> None:
    command_text = (COMMANDS_DIR / "respond-to-referees.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        COMMANDS_DIR / "respond-to-referees.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    bootstrap = measure_prompt_surface(
        BOOTSTRAP_AUTHORITY,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    expanded_command = expanded_prompt_text(
        COMMANDS_DIR / "respond-to-referees.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert "@{GPD_INSTALL_DIR}/workflows/respond-to-referees/bootstrap.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/respond-to-referees.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-review-wrapper-guidance.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/referee-response.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/author-response.md" not in command_text
    assert "Follow the included first-stage authority exactly." in command_text
    assert "The workflow resolves the manuscript root, review artifacts, and revision targets." in command_text
    assert metrics.expanded_line_count > bootstrap.expanded_line_count
    assert metrics.expanded_char_count > bootstrap.expanded_char_count
    assert metrics.expanded_line_count < bootstrap.expanded_line_count + 180
    assert metrics.expanded_char_count < bootstrap.expanded_char_count + 12_000
    assert metrics.expanded_char_count < 24_000

    for forbidden in (
        "gpd-paper-writer",
        'subagent_type="gpd-paper-writer"',
        "respond_to_referees_revision_section",
        "aggregate_child_gate",
        "docs: referee response and manuscript revisions",
        '<step name="commit_and_present">',
    ):
        assert forbidden not in expanded_command


def test_respond_to_referees_workflow_defers_stage_authorities_until_the_manifest_stages_need_them() -> None:
    manifest = _manifest()

    assert manifest.stage_ids() == (
        "bootstrap",
        "report_triage",
        "revision_planning",
        "response_authoring",
        "finalize",
    )

    bootstrap = manifest.stage("bootstrap")
    report_triage = manifest.stage("report_triage")
    revision_planning = manifest.stage("revision_planning")
    response_authoring = manifest.stage("response_authoring")
    finalize = manifest.stage("finalize")

    assert "workflows/respond-to-referees.md" not in {
        path for stage in manifest.stages for path in (*stage.mode_paths, *stage.loaded_authorities)
    }
    assert bootstrap.mode_paths == ("workflows/respond-to-referees/bootstrap.md",)
    assert bootstrap.loaded_authorities == (
        "workflows/respond-to-referees/bootstrap.md",
        "references/publication/publication-bootstrap-preflight.md",
    )
    for deferred in (
        "workflows/respond-to-referees.md",
        "workflows/respond-to-referees/report-triage.md",
        "workflows/respond-to-referees/revision-planning.md",
        "workflows/respond-to-referees/response-authoring.md",
        "workflows/respond-to-referees/finalize.md",
        "references/publication/publication-response-writer-handoff.md",
        "references/publication/peer-review-reliability.md",
        "references/publication/stage-recovery-gate.md",
        "templates/paper/referee-response.md",
        "templates/paper/author-response.md",
    ):
        assert deferred in bootstrap.must_not_eager_load

    assert report_triage.loaded_authorities == (
        "workflows/respond-to-referees/report-triage.md",
        "references/publication/publication-response-writer-handoff.md",
    )
    assert _conditional_authorities_by_when(report_triage) == {
        "review_integrity_recovery_needed": ("references/publication/peer-review-reliability.md",),
        "checkpoint_or_child_recovery_needed": ("references/publication/stage-recovery-gate.md",),
    }
    assert "workflows/respond-to-referees/response-authoring.md" in report_triage.must_not_eager_load
    assert "workflows/respond-to-referees/finalize.md" in report_triage.must_not_eager_load
    assert "references/publication/peer-review-reliability.md" in report_triage.must_not_eager_load
    assert "references/publication/stage-recovery-gate.md" in report_triage.must_not_eager_load
    assert "templates/paper/referee-response.md" in report_triage.must_not_eager_load
    assert "templates/paper/author-response.md" in report_triage.must_not_eager_load

    assert revision_planning.loaded_authorities == ("workflows/respond-to-referees/revision-planning.md",)
    assert _conditional_authorities_by_when(revision_planning) == {
        "response_pair_artifact_contract_needed": ("references/publication/publication-response-writer-handoff.md",),
        "review_integrity_recovery_needed": ("references/publication/peer-review-reliability.md",),
        "checkpoint_or_child_recovery_needed": ("references/publication/stage-recovery-gate.md",),
    }
    assert "reference_artifacts_content" not in revision_planning.required_init_fields
    assert {
        "selected_protocol_bundle_ids",
        "protocol_bundle_load_manifest",
    } <= set(revision_planning.required_init_fields)
    assert "protocol_bundle_context" not in revision_planning.required_init_fields
    assert "active_reference_context" not in revision_planning.required_init_fields
    assert "references/publication/publication-response-writer-handoff.md" in revision_planning.must_not_eager_load
    assert "references/publication/stage-recovery-gate.md" in revision_planning.must_not_eager_load
    assert "templates/paper/referee-response.md" in revision_planning.must_not_eager_load
    assert "templates/paper/author-response.md" in revision_planning.must_not_eager_load

    assert response_authoring.loaded_authorities == (
        "workflows/respond-to-referees/response-authoring.md",
        "references/publication/publication-response-writer-handoff.md",
        "references/publication/stage-recovery-gate.md",
        "templates/paper/referee-response.md",
        "templates/paper/author-response.md",
    )
    assert _conditional_authorities_by_when(response_authoring) == {
        "writer_spawn_needed": ("references/orchestration/runtime-delegation-note.md",),
        "review_integrity_recovery_needed": ("references/publication/peer-review-reliability.md",),
    }
    assert "references/orchestration/runtime-delegation-note.md" in response_authoring.must_not_eager_load
    assert "reference_artifacts_content" in response_authoring.required_init_fields
    assert {"protocol_bundle_context", "active_reference_context"} <= set(response_authoring.required_init_fields)
    assert finalize.loaded_authorities == (
        "workflows/respond-to-referees/finalize.md",
        "references/publication/publication-response-writer-handoff.md",
    )
    assert _conditional_authorities_by_when(finalize) == {
        "review_integrity_recovery_needed": ("references/publication/peer-review-reliability.md",),
        "checkpoint_or_child_recovery_needed": ("references/publication/stage-recovery-gate.md",),
    }
    assert "reference_artifacts_content" not in finalize.required_init_fields


def test_respond_to_referees_triage_stage_blocks_before_response_authoring_and_finalization() -> None:
    manifest = _manifest()
    triage_surface = _expanded_stage_surface(manifest.stage("report_triage"))

    assert "REPORT_TRIAGE_INIT=$(gpd --raw init respond-to-referees --stage report_triage" in triage_surface
    assert "publication-response-writer-handoff.md" in triage_surface
    assert "canonical `${RESPONSE_PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md`" in triage_surface

    for forbidden in (
        'subagent_type="gpd-paper-writer"',
        "respond_to_referees_revision_section",
        "aggregate_child_gate",
        "docs: referee response and manuscript revisions",
        '<step name="commit_and_present">',
    ):
        assert forbidden not in triage_surface


def test_respond_to_referees_response_authoring_stage_retains_response_pair_and_writer_contract() -> None:
    manifest = _manifest()
    response_surface = _expanded_stage_surface(manifest.stage("response_authoring"))
    response_surface_with_writer = _expanded_stage_surface(
        manifest.stage("response_authoring"),
        selected_conditions=("writer_spawn_needed",),
    )
    revision_gate = _yaml_gate_payload(response_surface, "child_gate", "respond_to_referees_revision_section")
    aggregate_gate = _yaml_gate_payload(
        response_surface, "aggregate_child_gate", "respond_to_referees_response_pair_current"
    )

    assert "{GPD_INSTALL_DIR}/templates/paper/author-response.md" in response_surface
    assert "{GPD_INSTALL_DIR}/templates/paper/referee-response.md" in response_surface
    assert "publication-response-writer-handoff.md" in response_surface
    assert "# Runtime Delegation Note" not in response_surface
    assert "# Runtime Delegation Note" in response_surface_with_writer
    assert 'subagent_type="gpd-paper-writer"' in response_surface
    assert revision_gate["expected_artifacts"] == [
        "${PAPER_DIR}/{resolved_section_file}",
        "${RESPONSE_AUTHOR_PATH}",
        "${RESPONSE_REFEREE_PATH}",
    ]
    assert aggregate_gate["expected_artifacts"] == [
        "every required revised section under ${PAPER_DIR}",
        "${RESPONSE_AUTHOR_PATH}",
        "${RESPONSE_REFEREE_PATH}",
    ]
    assert (
        "fresh child\nhandoff and named in current-run `files_written` / `gpd_return.files_written`" in response_surface
    )
    assert (
        "gpd validate handoff-artifacts for revised section plus both response artifacts" in revision_gate["validators"]
    )
