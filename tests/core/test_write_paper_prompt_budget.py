"""Prompt budget assertions for the `write-paper` startup surface."""

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
WRITE_PAPER_STAGE_DIR = WORKFLOWS_DIR / "write-paper"
BOOTSTRAP_AUTHORITY = WRITE_PAPER_STAGE_DIR / "paper-bootstrap.md"
PUBLICATION_REVIEW_EAGER_CHAR_BUDGET = 45_000


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


def test_write_paper_command_uses_first_stage_authority_boundary() -> None:
    command_text = (COMMANDS_DIR / "write-paper.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        COMMANDS_DIR / "write-paper.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    bootstrap = measure_prompt_surface(
        BOOTSTRAP_AUTHORITY,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert bootstrap.raw_include_count == 0
    assert "context_mode: project-aware" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/write-paper/paper-bootstrap.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/write-paper.md" not in command_text
    assert "--intake path/to/write-paper-authoring-input.json" in command_text
    assert "GPD/publication/{subject_slug}" in command_text
    assert "`.../intake/` is provenance only" in command_text
    assert command_text.count("{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md") == 1
    assert "@{GPD_INSTALL_DIR}/references/publication/peer-review-panel.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/paper-config-schema.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/review-ledger-schema.md" not in command_text
    assert "required_evidence:" in command_text
    assert "external-authoring lane: explicit `--intake` manifest with claim-to-evidence bindings" in command_text
    assert "stage_artifacts:" not in command_text
    assert "GPD/review/CLAIMS{round_suffix}.json" not in command_text
    assert "GPD/review/STAGE-reader{round_suffix}.json" not in command_text
    assert "Follow the included first-stage authority exactly." in command_text
    assert "The root workflow index is only a staged-file map." in command_text
    assert metrics.expanded_char_count < 32_000
    assert metrics.expanded_line_count < 700

    expanded_command = expanded_prompt_text(
        COMMANDS_DIR / "write-paper.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    assert 'subagent_type="gpd-paper-writer"' not in expanded_command
    assert 'subagent_type="gpd-bibliographer"' not in expanded_command
    assert "gpd-referee" not in expanded_command
    assert "templates/paper/review-ledger-schema.md" not in expanded_command
    assert "references/publication/peer-review-panel.md" not in expanded_command


def test_write_paper_workflow_defers_stage_authorities_until_the_manifest_stages_need_them() -> None:
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "write-paper-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="write-paper",
    )

    assert manifest.stage_ids() == (
        "paper_bootstrap",
        "outline_and_scaffold",
        "figure_and_section_authoring",
        "consistency_and_references",
        "publication_review",
    )

    bootstrap = manifest.stages[0]
    outline = manifest.stages[1]
    figure_authoring = manifest.stages[2]
    consistency = manifest.stages[3]
    publication_review = manifest.stages[4]
    late_stage_authorities = {authority for stage in manifest.stages[1:] for authority in stage.loaded_authorities}

    assert "workflows/write-paper.md" not in {
        path for stage in manifest.stages for path in (*stage.mode_paths, *stage.loaded_authorities)
    }
    assert bootstrap.mode_paths == ("workflows/write-paper/paper-bootstrap.md",)
    assert bootstrap.loaded_authorities == (
        "workflows/write-paper/paper-bootstrap.md",
        "references/publication/publication-bootstrap-preflight.md",
        "templates/paper/publication-manuscript-root-preflight.md",
    )
    assert "workflows/write-paper.md" in bootstrap.must_not_eager_load
    assert late_stage_authorities.issubset(set(bootstrap.must_not_eager_load))
    assert "workflows/write-paper/outline-scaffold.md" in bootstrap.must_not_eager_load
    assert "workflows/write-paper/authoring.md" in bootstrap.must_not_eager_load
    assert "workflows/write-paper/consistency-references.md" in bootstrap.must_not_eager_load
    assert "workflows/write-paper/publication-review-finalization.md" in bootstrap.must_not_eager_load
    assert "references/publication/publication-review-round-artifacts.md" in bootstrap.must_not_eager_load
    assert "references/publication/publication-response-artifacts.md" in bootstrap.must_not_eager_load
    assert "references/publication/peer-review-panel.md" in bootstrap.must_not_eager_load
    assert "references/publication/peer-review-reliability.md" in bootstrap.must_not_eager_load
    assert "references/publication/stage-recovery-gate.md" in bootstrap.must_not_eager_load
    assert "references/publication/publication-pipeline-modes.md" in bootstrap.must_not_eager_load
    assert "templates/paper/paper-config-schema.md" in bootstrap.must_not_eager_load
    assert "templates/paper/artifact-manifest-schema.md" in bootstrap.must_not_eager_load
    assert "templates/paper/review-ledger-schema.md" in bootstrap.must_not_eager_load
    assert "templates/paper/referee-decision-schema.md" in bootstrap.must_not_eager_load

    assert outline.loaded_authorities == ("workflows/write-paper/outline-scaffold.md",)
    assert {conditional.when: conditional.authorities for conditional in outline.conditional_authorities} == {
        "publication_lane_or_builder_config_selection": ("references/publication/publication-pipeline-modes.md",),
        "paper_builder_config_or_artifact_manifest_write": (
            "templates/paper/paper-config-schema.md",
            "templates/paper/artifact-manifest-schema.md",
        ),
    }
    assert "references/publication/publication-pipeline-modes.md" in outline.must_not_eager_load
    assert "templates/paper/paper-config-schema.md" in outline.must_not_eager_load
    assert "templates/paper/artifact-manifest-schema.md" in outline.must_not_eager_load
    assert figure_authoring.loaded_authorities == (
        "workflows/write-paper/authoring.md",
        "references/publication/stage-recovery-gate.md",
        "references/shared/canonical-schema-discipline.md",
        "templates/paper/figure-tracker.md",
    )
    assert {conditional.when: conditional.authorities for conditional in figure_authoring.conditional_authorities} == {
        "writer_spawn_needed": ("references/orchestration/runtime-delegation-note.md",),
    }
    assert "references/orchestration/runtime-delegation-note.md" in figure_authoring.must_not_eager_load
    assert consistency.loaded_authorities == (
        "workflows/write-paper/consistency-references.md",
        "references/publication/stage-recovery-gate.md",
        "templates/paper/bibliography-audit-schema.md",
        "templates/paper/reproducibility-manifest.md",
    )
    assert publication_review.loaded_authorities == (
        "workflows/write-paper/publication-review-finalization.md",
        "references/publication/publication-review-round-artifacts.md",
    )
    conditional_authorities = {
        conditional.when: conditional.authorities for conditional in publication_review.conditional_authorities
    }
    assert conditional_authorities == {
        "response_pair_authoring": (
            "references/publication/publication-response-writer-handoff.md",
            "references/publication/publication-response-artifacts.md",
            "references/publication/stage-recovery-gate.md",
            "templates/paper/author-response.md",
            "templates/paper/referee-response.md",
        ),
        "advisory_paper_quality_scoring": ("references/publication/paper-quality-scoring.md",),
        "proactive_critique_loop": ("references/publication/proactive-critique-loop.md",),
        "review_failure_or_round_state_debug": ("references/publication/peer-review-reliability.md",),
    }
    assert "references/publication/peer-review-panel.md" in publication_review.must_not_eager_load
    assert "templates/paper/review-ledger-schema.md" in publication_review.must_not_eager_load
    assert "templates/paper/referee-decision-schema.md" in publication_review.must_not_eager_load
    assert len(_expanded_stage_surface(publication_review)) < PUBLICATION_REVIEW_EAGER_CHAR_BUDGET


def test_write_paper_authoring_defers_reference_and_planning_bodies_until_target_selection() -> None:
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "write-paper-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="write-paper",
    )
    figure_authoring = manifest.stage("figure_and_section_authoring")
    consistency = manifest.stage("consistency_and_references")
    publication_review = manifest.stage("publication_review")

    assert "reference_artifact_files" in figure_authoring.required_init_fields
    assert "reference_artifacts_content" not in figure_authoring.required_init_fields
    assert {
        "state_content",
        "roadmap_content",
        "requirements_content",
    }.isdisjoint(figure_authoring.required_init_fields)
    assert {
        "citation_source_files",
        "citation_source_count",
        "citation_source_warnings",
        "derived_citation_sources",
        "derived_citation_source_count",
    } <= set(figure_authoring.required_init_fields)
    assert "protocol_bundle_context" not in figure_authoring.required_init_fields
    assert "active_reference_context" not in figure_authoring.required_init_fields
    figure_authoring_surface = _expanded_stage_surface(figure_authoring)
    assert "# Runtime Delegation Note" not in figure_authoring_surface
    assert "Handle-first authoring invariant" in figure_authoring_surface
    assert "protocol_bundle_load_manifest" in figure_authoring_surface
    assert "verification_domains" in figure_authoring_surface
    assert "execution_guides" in figure_authoring_surface
    assert "If a tensor-network or other method-specific section" in figure_authoring_surface
    assert "# Tensor Networks" not in figure_authoring_surface
    assert "Bond-dimension-limited" not in figure_authoring_surface
    assert "# Runtime Delegation Note" in _expanded_stage_surface(
        figure_authoring,
        selected_conditions=("writer_spawn_needed",),
    )

    for stage in (consistency, publication_review):
        assert "reference_artifact_files" in stage.required_init_fields
        assert "protocol_bundle_load_manifest" in stage.required_init_fields
        assert "derived_manuscript_reference_status" in stage.required_init_fields
        assert "citation_source_files" in stage.required_init_fields
        assert "reference_artifacts_content" not in stage.required_init_fields
        assert "protocol_bundle_context" not in stage.required_init_fields
        assert "active_reference_context" not in stage.required_init_fields


def test_write_paper_publication_review_keeps_exact_round_artifact_reads_before_routing() -> None:
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "write-paper-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="write-paper",
    )
    publication_review = manifest.stage("publication_review")
    publication_review_surface = _expanded_stage_surface(publication_review)

    assert "selected_publication_root" in publication_review.required_init_fields
    assert "selected_review_root" in publication_review.required_init_fields
    assert "references/publication/publication-review-round-artifacts.md" in publication_review.loaded_authorities
    assert "references/publication/publication-response-artifacts.md" in publication_review.must_not_eager_load
    assert (
        "Read `${selected_review_root}/REFEREE-DECISION{round_suffix}.json` and\n"
        "`${selected_review_root}/REVIEW-LEDGER{round_suffix}.json` first"
    ) in publication_review_surface
    assert "then read `${selected_publication_root}/REFEREE-REPORT{round_suffix}.md`" in publication_review_surface
    assert (
        "Recommend `gpd:arxiv-submission` only when project-backed staged review already\nclears packaging."
        in publication_review_surface
    )
    assert "summary-only" not in publication_review_surface
    assert "summarized favorable flag" not in publication_review_surface


def test_write_paper_bootstrap_stage_blocks_before_downstream_prompt_loading() -> None:
    manifest = validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "write-paper-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="write-paper",
    )
    bootstrap_surface = _expanded_stage_surface(manifest.stage("paper_bootstrap"))

    assert "checkpoint: manuscript_root_gate" in bootstrap_surface
    assert "checkpoint: bibliography_gate" in bootstrap_surface
    assert "checkpoint: claim_evidence_gate" in bootstrap_surface
    assert "command_execution_state: blocked_before_write" in bootstrap_surface
    assert "Fresh bootstrap exception" in bootstrap_surface
    assert "authoring cannot load until Stage 2 has" in bootstrap_surface
    assert "produced a concrete scaffold" in bootstrap_surface
    assert "No bibliography file" not in bootstrap_surface
    assert "no bibliography" in bootstrap_surface
    assert "literature review with concrete prior-work entries" in bootstrap_surface

    for forbidden in (
        'subagent_type="gpd-paper-writer"',
        'subagent_type="gpd-bibliographer"',
        "gpd-referee",
        "peer-review-panel.md",
        "review-ledger-schema.md",
        "referee-decision-schema.md",
    ):
        assert forbidden not in bootstrap_surface
