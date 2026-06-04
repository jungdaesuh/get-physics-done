from __future__ import annotations

import re
from pathlib import Path

from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.lifecycle_contract_test_support import assert_semantic_contract as _assert_semantic
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "references" / "publication"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"


def _workflow_authority(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def _assert_round_artifact_semantics(source: str) -> None:
    _assert_semantic(
        source,
        "publication review round artifact family semantics",
        "round-suffix",
        "sibling-artifact",
        "default project-backed",
        "subject-owned publication root",
        "does not by itself promise a full relocation",
    )


def _assert_paired_response_completion_semantics(source: str) -> None:
    _assert_semantic(
        source,
        "publication paired response completion and relocation semantics",
        "stale-output handling",
        "stage-recovery gate",
        "Project-backed response rounds",
        "selected_publication_root=GPD",
        "same paired response artifacts bind under the subject-owned",
    )


def _assert_revision_state_semantics(referee: str) -> None:
    _assert_semantic(
        referee,
        "referee revision state uses paired response package",
        "paired response package",
        "Do not infer revision state",
        "global `GPD/` filenames",
        "suffixes disagree",
        "incomplete response package",
    )


def _assert_parallel_wave_semantics(workflow: str) -> None:
    _assert_semantic(
        workflow,
        "peer-review parallel Stage 2/3/proof wave barrier semantics",
        "Stage 2",
        "Stage 3",
        "proof critique",
        "parallel",
        "barriered wave",
        "Before Stage 4",
        "typed return",
        "apply stage-recovery gate",
        "retry once",
    )


def _assert_later_stage_restart_semantics(workflow: str) -> None:
    _assert_semantic(
        workflow,
        "peer-review later stages restart from persisted artifacts",
        "Stage 4",
        "Stage 5",
        "proof-bearing review",
        "same-round",
        "Retry once",
        "STOP before Stage 5",
        "Stage 6",
        "persisted stage artifacts",
        "carry-forward inputs",
    )


def test_publication_bootstrap_preflight_defines_the_shared_publication_gate() -> None:
    source = (REFERENCES_DIR / "publication-bootstrap-preflight.md").read_text(encoding="utf-8")

    _assert_semantic(
        source,
        "publication bootstrap preflight reference role",
        "Canonical workflow-facing bootstrap",
        "preflight reference",
        "publication tasks",
    )
    assert "publication-manuscript-root-preflight.md" in source
    assert "publication-review-round-artifacts.md" in source
    assert "publication-response-artifacts.md" in source
    assert "publication-artifact-gates.md" not in source


def test_publication_response_writer_handoff_defines_one_shot_child_returns() -> None:
    source = (REFERENCES_DIR / "publication-response-writer-handoff.md").read_text(encoding="utf-8")
    recovery = (REFERENCES_DIR / "stage-recovery-gate.md").read_text(encoding="utf-8")

    _assert_semantic(
        source,
        "publication response writer handoff reference role",
        "Canonical workflow-facing handoff",
        "completion reference",
        "spawned response-writing work",
    )
    assert "stage-recovery-gate.md" in source
    _assert_semantic(
        source + "\n" + recovery,
        "publication response writer one-shot lifecycle gate",
        "publication stage-recovery gate",
        "one-shot",
        "checkpoint",
        "fresh continuation",
        "status: completed",
        "expected response files",
        "fresh typed `gpd_return.files_written`",
    )
    assert "status: checkpoint" in source
    assert "gpd_return.files_written" in source
    assert "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md" in source
    assert "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md" in source
    assert "GPD/AUTHOR-RESPONSE{round_suffix}.md" in source
    assert "GPD/review/REFEREE_RESPONSE{round_suffix}.md" in source
    _assert_semantic(
        source + "\n" + recovery,
        "publication response writer stale-output rejection",
        "prose-only status messages",
        "proof of completion",
        "stale same-round files",
        "do not complete the handoff",
        "stale preexisting files",
        "current-run completion",
    )
    assert "publication-artifact-gates.md" not in source


def test_publication_review_wrapper_guidance_points_to_the_new_shared_refs() -> None:
    source = (REFERENCES_DIR / "publication-review-wrapper-guidance.md").read_text(encoding="utf-8")

    assert "publication-bootstrap-preflight.md" in source
    assert "publication-response-writer-handoff.md" in source
    assert "publication-artifact-gates.md" not in source


def test_publication_review_round_artifacts_define_canonical_round_family() -> None:
    source = (REFERENCES_DIR / "publication-review-round-artifacts.md").read_text(encoding="utf-8")

    _assert_round_artifact_semantics(source)
    assert 'Round 1 uses `round_suffix=""`.' in source
    assert 'Round `N` for `N >= 2` uses `round_suffix="-R{N}"`.' in source
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md" in source
    assert "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in source
    assert "${selected_review_root}/REFEREE-DECISION{round_suffix}.json" in source
    assert "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md" in source
    assert "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md" in source
    assert "${selected_review_root}/PROOF-REDTEAM{round_suffix}.md" in source
    assert "GPD/publication/{subject_slug}" in source
    assert "review-round-artifact-contract.md" not in source
    assert "publication-artifact-gates.md" not in source


def test_publication_final_adjudication_boundary_preserves_stage_six_guards() -> None:
    source = (REFERENCES_DIR / "publication-final-adjudication-boundary.md").read_text(encoding="utf-8")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    _assert_semantic(
        source,
        "publication final adjudication reference role",
        "Compact Stage 6 reference",
        "final `gpd-referee` adjudication pass",
        "local write allowlist",
    )
    assert "selected_publication_root" in source
    assert "selected_review_root" in source
    assert "round_suffix" in source
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md" in source
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.tex" in source
    assert "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in source
    assert "${selected_review_root}/REFEREE-DECISION{round_suffix}.json" in source
    assert "${selected_publication_root}/CONSISTENCY-REPORT.md" in source
    assert "${selected_review_root}/CLAIMS{round_suffix}.json" in source
    assert "any `${selected_review_root}/STAGE-*.json`" in source
    assert "${selected_review_root}/PROOF-REDTEAM{round_suffix}.md" in source
    assert "gpd validate review-ledger ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in source
    assert (
        "gpd validate referee-decision ${selected_review_root}/REFEREE-DECISION{round_suffix}.json --strict "
        "--ledger ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json"
    ) in source
    _assert_semantic(
        source,
        "publication final adjudication proof-redteam clearance guardrail",
        "Stage-review validation alone",
        "not proof-redteam clearance",
    )
    assert "publication-final-adjudication-boundary.md" in referee
    _assert_semantic(
        referee,
        "referee Stage 6 read-only upstream boundary",
        "read-only evidence",
        "Stage 6 writable allowlist",
    )


def test_publication_response_artifacts_define_paired_completion_gate() -> None:
    source = (REFERENCES_DIR / "publication-response-artifacts.md").read_text(encoding="utf-8")

    _assert_semantic(
        source,
        "publication paired response artifact contract role",
        "Canonical paired response-artifact",
        "one-shot child-return contract",
        "referee-response work",
    )
    assert "stage-recovery-gate.md" in source
    _assert_semantic(
        source,
        "publication paired response one-shot freshness gate",
        "spawned writer lifecycle",
        "checkpoint continuation",
        "stale-output rejection",
        "status: completed",
        "response pair exists on disk",
        "typed `gpd_return.files_written`",
    )
    assert "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md" in source
    assert "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md" in source
    _assert_semantic(
        source,
        "publication paired response requires both files",
        "two files as one success gate",
        "do not mark the round complete",
        "only one of them is current",
        "completion requires both",
    )
    assert "status: checkpoint" in source
    assert "gpd_return.files_written" in source
    _assert_paired_response_completion_semantics(source)
    assert "response_to: REFEREE-REPORT{round_suffix}.md" in source
    assert "manuscript_path: path/to/active-manuscript.tex" in source
    _assert_semantic(
        source,
        "publication paired response frontmatter and root relocation boundary",
        "missing or mismatched response frontmatter",
        "incomplete",
        "does not imply a full relocation",
    )
    assert "response-artifact-contract.md" not in source
    assert "publication-artifact-gates.md" not in source


def test_response_templates_include_explicit_subject_binding_frontmatter() -> None:
    templates_dir = REPO_ROOT / "src/gpd/specs/templates/paper"

    for template_name in ("author-response.md", "referee-response.md"):
        source = (templates_dir / template_name).read_text(encoding="utf-8")
        assert "response_to: REFEREE-REPORT{round_suffix}.md" in source
        assert "round: {N}" in source
        assert "manuscript_path: {path/to/active-manuscript.tex}" in source
        assert "review_ledger: ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in source
        assert "referee_decision: ${selected_review_root}/REFEREE-DECISION{round_suffix}.json" in source


def test_referee_revision_mode_requires_a_paired_response_package() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    assert "paired response package" in referee
    assert "${selected_publication_root}/AUTHOR-RESPONSE.md" in referee
    assert "${selected_publication_root}/AUTHOR-RESPONSE-R{N}.md" in referee
    assert "${selected_review_root}/REFEREE_RESPONSE.md" in referee
    assert "${selected_review_root}/REFEREE_RESPONSE-R{N}.md" in referee
    _assert_revision_state_semantics(referee)


def test_paper_writer_and_referee_load_the_canonical_publication_response_contracts() -> None:
    paper_writer = (AGENTS_DIR / "gpd-paper-writer.md").read_text(encoding="utf-8")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    write_paper = _workflow_authority("write-paper")
    respond = _workflow_authority("respond-to-referees")

    for source in (paper_writer, referee):
        assert "publication-artifact-gates.md" not in source
        assert "response-artifact-contract.md" not in source
        assert "review-round-artifact-contract.md" not in source

    assert "publication-response-writer-handoff.md" in paper_writer
    assert "publication-response-artifacts.md" not in paper_writer
    assert "publication-review-round-artifacts.md" not in paper_writer
    assert "publication-response-artifacts.md" in referee
    assert "publication-review-round-artifacts.md" in referee
    _assert_semantic(paper_writer, "paper writer fixed response paths", "fixed", "on disk")
    _assert_semantic(referee, "referee fixed response paths", "fixed", "on disk")
    assert "gpd_return.files_written" in write_paper
    assert "gpd validate handoff-artifacts for both response paths" in write_paper
    assert "publication-response-writer-handoff.md frontmatter, round, and manuscript binding" in write_paper
    assert "publication-bootstrap-preflight.md" in write_paper
    assert "publication-response-writer-handoff.md" in write_paper
    assert "publication-bootstrap-preflight.md" in respond
    assert "publication-response-writer-handoff.md" in respond
    assert "selected_publication_root` / `selected_review_root" in respond
    assert "publication-response-artifacts.md" not in write_paper
    assert "publication-response-artifacts.md" not in respond
    _assert_semantic(
        respond,
        "respond-to-referees response handoff current-run files-written",
        "fresh child handoff",
        "current-run `files_written`",
        "gpd_return.files_written",
    )
    assert "gpd validate handoff-artifacts for revised section plus both response artifacts" in respond


def test_respond_finalize_declares_review_suffix_fallback_field() -> None:
    finalize = load_workflow_stage_manifest("respond-to-referees").stage("finalize")
    source = (WORKFLOWS_DIR / "respond-to-referees" / "finalize.md").read_text(encoding="utf-8")

    assert 'gpd json get .latest_review_round_suffix --default ""' in source
    assert "latest_review_round_suffix" in finalize.required_init_fields


def test_peer_review_stage_six_requires_fresh_referee_return_and_artifacts() -> None:
    workflow = _workflow_authority("peer-review")

    assert "Stage 6 child gate" in workflow
    assert "child_gate:" in workflow
    assert "peer_review_stage6_referee" in workflow
    assert re.search(r"required_status:\s+[\"']?completed", workflow)
    assert "stage-recovery-gate.md" in workflow
    _assert_semantic(
        workflow,
        "peer-review Stage 6 one-shot child gate freshness",
        "checkpoint continuation",
        "gpd_return.files_written",
        "Stage 6 write allowlist",
    )


def test_peer_review_parallel_wave_stops_terminal_children_before_stage_4() -> None:
    workflow = _workflow_authority("peer-review")

    _assert_parallel_wave_semantics(workflow)
    assert "gpd-check-proof" in workflow
    assert re.search(
        r"Missing, malformed,[\s\S]{0,120}proof artifacts\s+block favorable recommendation\. Retry proof-redteam once",
        workflow,
    )
    assert re.search(r"Retry proof-redteam once, then STOP if invalid", workflow)


def test_peer_review_later_stages_restart_from_fresh_context_and_written_artifacts() -> None:
    workflow = _workflow_authority("peer-review")

    _assert_later_stage_restart_semantics(workflow)
    assert "${REVIEW_ROOT}/STAGE-math{round_suffix}.json" in workflow
    assert "${REVIEW_ROOT}/STAGE-literature{round_suffix}.json" in workflow
    assert "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md" in workflow
    assert "${REVIEW_ROOT}/STAGE-physics{round_suffix}.json" in workflow


def test_referee_stage_six_files_written_must_be_fresh_current_run_outputs() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    _assert_semantic(
        referee,
        "referee Stage 6 current-run files-written contract",
        "return file list may name only paths produced in this Stage 6 run",
        "allowed by `<report_format>`",
        "Stage 6 run",
        "upstream-artifact `blocked` returns",
        "keep the list empty",
    )
    assert "${selected_publication_root}/CONSISTENCY-REPORT.md" in referee


def test_referee_stage_six_write_allowlist_stops_before_upstream_repairs() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    assert "Stage 6 writable allowlist" in referee
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md" in referee
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.tex" in referee
    assert "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in referee
    assert "${selected_review_root}/REFEREE-DECISION{round_suffix}.json" in referee
    assert "${selected_publication_root}/CONSISTENCY-REPORT.md" in referee
    assert "never rewrite `${selected_review_root}/CLAIMS{round_suffix}.json`" in referee
    assert "any `${selected_review_root}/STAGE-*.json`" in referee
    assert "`${selected_review_root}/PROOF-REDTEAM{round_suffix}.md`" in referee
    _assert_semantic(
        referee,
        "referee Stage 6 stale upstream artifact blocks instead of repairs",
        "upstream staged-review inputs",
        "block with the earliest failing upstream artifact/stage",
        "return `blocked` instead of repairing",
        "gpd_return.status: blocked",
    )


def test_stage_six_handoff_closure_and_retry_freshness_remain_explicit() -> None:
    workflow = _workflow_authority("peer-review")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    _assert_semantic(
        workflow,
        "peer-review Stage 6 closure requires return files and validators",
        "success text",
        "typed return",
        "on-disk files",
        "validators all agree",
        "gpd_return.files_written",
        "Stage 6 write allowlist",
    )
    _assert_semantic(
        workflow,
        "peer-review Stage 6 retry scope",
        "Only retry Stage 6",
        "Stage 6-owned artifact failures",
        "STOP fail-closed and rerun the earliest failing\nupstream stage",
        "eligible Stage 6 retry also fails",
        "do not proceed",
    )
    _assert_semantic(
        referee,
        "referee checkpoint then fresh continuation",
        "continuation-boundary.md",
        "orchestrator owns the follow-up after the pause",
        "`checkpoint`: missing input",
        "`completed`: valid final report package plus required fresh Stage 6 artifacts",
    )
