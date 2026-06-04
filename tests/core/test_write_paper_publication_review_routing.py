"""Routing and budget checks for `write-paper.publication_review`."""

from __future__ import annotations

from pathlib import Path

from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.prompt_metrics_support import expanded_prompt_text

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
WORKFLOWS_DIR = SOURCE_ROOT / "specs" / "workflows"
PUBLICATION_REVIEW_PATH = WORKFLOWS_DIR / "write-paper" / "publication-review-finalization.md"
PATH_PREFIX = "/runtime/"
PUBLICATION_REVIEW_EAGER_CHAR_BUDGET = 45_000

EAGER_AUTHORITIES = (
    "workflows/write-paper/publication-review-finalization.md",
    "references/publication/publication-review-round-artifacts.md",
)
RESPONSE_PAIR_AUTHORITIES = (
    "references/publication/publication-response-writer-handoff.md",
    "references/publication/publication-response-artifacts.md",
    "references/publication/stage-recovery-gate.md",
    "templates/paper/author-response.md",
    "templates/paper/referee-response.md",
)
NON_EAGER_AUTHORITIES = {
    *RESPONSE_PAIR_AUTHORITIES,
    "references/publication/peer-review-panel.md",
    "references/publication/peer-review-reliability.md",
    "references/publication/paper-quality-scoring.md",
    "references/publication/proactive-critique-loop.md",
    "templates/paper/review-ledger-schema.md",
    "templates/paper/referee-decision-schema.md",
}


def _publication_review_surface() -> str:
    stage = load_workflow_stage_manifest("write-paper").stage("publication_review")
    return "\n\n".join(
        expanded_prompt_text(
            SOURCE_ROOT / "specs" / authority,
            src_root=SOURCE_ROOT,
            path_prefix=PATH_PREFIX,
        )
        for authority in stage.eager_authorities()
    )


def test_publication_review_stage_is_a_compact_router_not_a_panel_owner() -> None:
    stage = load_workflow_stage_manifest("write-paper").stage("publication_review")
    conditional = {entry.when: entry.authorities for entry in stage.conditional_authorities}

    assert stage.loaded_authorities == EAGER_AUTHORITIES
    assert conditional["response_pair_authoring"] == RESPONSE_PAIR_AUTHORITIES
    assert conditional["advisory_paper_quality_scoring"] == (
        "references/publication/paper-quality-scoring.md",
    )
    assert conditional["proactive_critique_loop"] == (
        "references/publication/proactive-critique-loop.md",
    )
    assert conditional["review_failure_or_round_state_debug"] == (
        "references/publication/peer-review-reliability.md",
    )
    assert NON_EAGER_AUTHORITIES.isdisjoint(stage.loaded_authorities)
    assert NON_EAGER_AUTHORITIES.issubset(stage.must_not_eager_load)
    assert "reference_artifact_files" in stage.required_init_fields
    assert "protocol_bundle_load_manifest" in stage.required_init_fields
    assert "derived_manuscript_reference_status" in stage.required_init_fields
    assert "citation_source_files" in stage.required_init_fields
    assert "reference_artifacts_content" not in stage.required_init_fields
    assert "active_reference_context" not in stage.required_init_fields
    assert "protocol_bundle_context" not in stage.required_init_fields
    assert {
        "GPD/publication/{subject_slug}/AUTHOR-RESPONSE{round_suffix}.md",
        "GPD/publication/{subject_slug}/review/REFEREE_RESPONSE{round_suffix}.md",
        "GPD/publication/{subject_slug}/REFEREE-REPORT{round_suffix}.md",
        "GPD/publication/{subject_slug}/REFEREE-REPORT{round_suffix}.tex",
    } <= set(stage.writes_allowed)

    eager_surface = _publication_review_surface()
    assert len(eager_surface) < PUBLICATION_REVIEW_EAGER_CHAR_BUDGET
    assert "Peer Review Panel Contract" not in eager_surface
    assert "Peer Review Phase Reliability" not in eager_surface
    assert "Author Response Template" not in eager_surface
    assert "Referee Response Template" not in eager_surface


def test_publication_review_prompt_preserves_lane_routing_boundaries() -> None:
    prompt = PUBLICATION_REVIEW_PATH.read_text(encoding="utf-8")

    assert "route to staged `gpd:peer-review`" in prompt
    assert "Use the peer-review stage manifest for panel" in prompt
    assert "Do not inline those authorities here." in prompt
    assert "Use `gpd-referee` only through the peer-review final-adjudication authority." in prompt
    assert "Load the conditional `response_pair_authoring` authorities only" in prompt
    assert "reference handles/statuses, citation-source" in prompt
    assert "protocol load manifests visible" in prompt
    assert "Read a specific reference or" in prompt
    assert "**External-authoring lane:** do **not** run the embedded staged panel here." in prompt
    assert "route the user to standalone `gpd:peer-review`" in prompt
    assert "do not recommend `gpd:arxiv-submission` directly from this lane." in prompt
    assert "bounded external-authoring lane did not widen into generic folder" in prompt
    assert "Response-pair child gate:" in prompt
    assert "child_gate:" in prompt
