from __future__ import annotations

from pathlib import Path

from tests.lifecycle_contract_test_support import (
    assert_forbidden_contract as _assert_forbidden,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import assert_semantic_contract as _assert_semantic

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
PEER_REVIEW_STAGE_FILES = (
    "bootstrap.md",
    "preflight.md",
    "artifact-discovery.md",
    "panel-stages.md",
    "final-adjudication.md",
    "finalize.md",
)


def _peer_review_stage_text(*names: str) -> str:
    stage_names = names or PEER_REVIEW_STAGE_FILES
    return "\n".join((WORKFLOWS_DIR / "peer-review" / name).read_text(encoding="utf-8") for name in stage_names)


def test_peer_review_workflow_references_canonical_reliability_doc_and_round_suffixed_artifacts() -> None:
    workflow = _peer_review_stage_text()

    _assert_machine(
        workflow,
        "peer-review workflow reliability and round artifacts",
        "{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md",
        "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-reader{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-literature{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-math{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-physics{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json",
        "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
        "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md",
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex",
        "gpd validate review-ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
        "gpd validate referee-decision ${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json --strict --ledger "
        "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
    )
    _assert_forbidden(workflow, "peer-review workflow no hidden GPD path", ".gpd/")


def test_peer_review_reliability_reference_uses_selected_review_roots() -> None:
    reliability = (REFERENCES_DIR / "publication" / "peer-review-reliability.md").read_text(encoding="utf-8")

    _assert_machine(
        reliability,
        "peer-review reliability selected review roots",
        "Peer Review Phase Reliability",
        "GPD/STATE.md",
        "GPD/ROADMAP.md",
        "GPD/phases/",
        "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json",
        "${selected_review_root}/REFEREE-DECISION{round_suffix}.json",
        "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md",
        "${selected_publication_root}/CONSISTENCY-REPORT.md",
        "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md",
        "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md",
    )
    _assert_semantic(
        reliability,
        "peer-review reliability Stage 6 behavior contract",
        "paired response artifacts are present",
        "Stage 6 Artifact Boundary",
        "fresh `gpd_return.files_written`",
        "gpd_return.status: blocked",
        "read-only upstream artifacts during Stage 6",
        "Stage 6 repaired upstream artifacts",
    )
    _assert_machine(
        reliability,
        "peer-review reliability validation commands and blocker fields",
        "gpd validate review-claim-index ${selected_review_root}/CLAIMS{round_suffix}.json",
        "gpd validate review-stage-report ${selected_review_root}/STAGE-<stage_id>{round_suffix}.json",
        "gpd validate review-ledger ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json",
        "gpd validate referee-decision ${selected_review_root}/REFEREE-DECISION{round_suffix}.json --strict "
        "--ledger ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json",
        "bibliography_audit_clean",
        "reproducibility_ready",
        "proof_audits[]",
        "theorem-bearing claims",
        "claim record itself",
    )
    _assert_semantic(
        reliability,
        "peer-review reliability claim proof-bearing status source",
        "theorem-bearing claims",
        "claim record itself",
    )
    _assert_forbidden(
        reliability,
        "peer-review reliability stale unsuffixed or hidden artifacts",
        "detects prior reports and author responses to increment the round number automatically",
        "theorem_assumptions",
        "theorem_parameters",
        "`CLAIMS.json`",
        "`REFEREE-DECISION.json`",
        "`REVIEW-LEDGER.json`",
        ".gpd/",
    )


def test_peer_review_surfaces_describe_dual_mode_project_and_external_artifact_review() -> None:
    command = (COMMANDS_DIR / "peer-review.md").read_text(encoding="utf-8")
    workflow = _peer_review_stage_text()
    reliability = (REFERENCES_DIR / "publication" / "peer-review-reliability.md").read_text(encoding="utf-8")
    publication_modes = (REFERENCES_DIR / "publication" / "publication-pipeline-modes.md").read_text(encoding="utf-8")

    _assert_machine(
        command,
        "peer-review command external artifact mode references",
        "{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md",
    )
    _assert_semantic(
        command,
        "peer-review command dual mode scope",
        "current GPD project or an explicit external artifact",
        "standalone external artifact review",
        "do not infer a full publication-tree relocation from that one continuation path",
    )
    _assert_semantic(
        publication_modes,
        "publication modes subject-owned root",
        "subject-owned publication root at `GPD/publication/{subject_slug}`",
    )
    _assert_forbidden(
        workflow, "peer-review workflow no standalone skeptical label", "standalone skeptical peer review"
    )
    _assert_semantic(
        workflow,
        "peer-review workflow current project or external path",
        "current GPD project manuscript",
        "explicit\nexternal artifact path",
    )
    _assert_semantic(
        reliability,
        "peer-review reliability dual mode scope",
        "reviewing the current GPD project manuscript",
        "explicit external artifact review",
    )


def test_peer_review_finalize_separates_review_completion_from_manuscript_quality() -> None:
    workflow = _peer_review_stage_text("finalize.md")

    _assert_semantic(
        workflow,
        "peer-review finalize separates completion from manuscript quality",
        "A completed staged review of a rejected manuscript is still a completed review run.",
        "present `BIBLIOGRAPHY-AUDIT.json` with no failed or unverified sources as verified",
        "classify the manuscript claim state as overclaim-blocked rather than evidence-bound",
        "do not turn a terminal `reject` recommendation into an automatic project-authoring command",
    )


def test_publication_reference_docs_keep_gpd_aux_outputs_separate_from_manuscript_root_contract() -> None:
    preflight = (REPO_ROOT / "src/gpd/specs/templates/paper/publication-manuscript-root-preflight.md").read_text(
        encoding="utf-8"
    )
    bootstrap = (REFERENCES_DIR / "publication" / "publication-bootstrap-preflight.md").read_text(encoding="utf-8")
    round_artifacts = (REFERENCES_DIR / "publication" / "publication-review-round-artifacts.md").read_text(
        encoding="utf-8"
    )
    response_artifacts = (REFERENCES_DIR / "publication" / "publication-response-artifacts.md").read_text(
        encoding="utf-8"
    )
    reliability = (REFERENCES_DIR / "publication" / "peer-review-reliability.md").read_text(encoding="utf-8")
    wrapper_guidance = (REFERENCES_DIR / "publication" / "publication-review-wrapper-guidance.md").read_text(
        encoding="utf-8"
    )

    _assert_semantic(
        preflight,
        "publication preflight external-subject boundary",
        "does not by itself authorize standalone external-subject support for every publication command",
        "Keep GPD-authored auxiliary review, response, and packaging outputs under `GPD/`",
    )
    _assert_semantic(
        bootstrap,
        "publication bootstrap standalone external-artifact boundary",
        "It does not decide whether a command may accept a standalone external manuscript/artifact",
        "Do not infer standalone external-artifact support from this pack alone.",
    )
    _assert_semantic(
        round_artifacts,
        "publication round artifacts root policy",
        "default project-backed canonical layout",
        "centralized preflight resolves `selected_publication_root=GPD`",
        "subject-owned publication root `GPD/publication/{subject_slug}`",
        "does not by itself promise a full relocation",
        "Do not copy manuscript-local artifacts into `GPD/` to satisfy strict review or submission gates.",
    )
    _assert_semantic(
        response_artifacts,
        "publication response artifacts local companion boundary",
        "optional manuscript-local response-letter companion such as `response-letter.tex` is additive only",
        "same paired response artifacts may instead bind under the subject-owned publication root",
        "does not imply a full relocation",
    )
    _assert_semantic(
        reliability,
        "peer-review reliability no manuscript root relocation",
        "That output policy does not relocate the manuscript draft or manuscript-root manifests",
        "copied stand-ins under `GPD/` do not satisfy strict gates",
    )
    _assert_semantic(
        wrapper_guidance,
        "publication wrapper guidance no implied migration",
        "Do not imply full external-subject support or manuscript-root migration unless the workflow/runtime actually provides it.",
    )


def test_peer_review_stage_six_boundary_aligns_reliability_workflow_panel_and_referee() -> None:
    workflow = _peer_review_stage_text("final-adjudication.md")
    panel = (REFERENCES_DIR / "publication" / "peer-review-panel.md").read_text(encoding="utf-8")
    reliability = (REFERENCES_DIR / "publication" / "peer-review-reliability.md").read_text(encoding="utf-8")
    boundary = (REFERENCES_DIR / "publication" / "publication-final-adjudication-boundary.md").read_text(
        encoding="utf-8"
    )
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    stage_six_outputs = (
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md",
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex",
        "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
        "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
        "${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md",
    )
    for artifact in stage_six_outputs:
        _assert_machine(workflow, f"peer-review Stage 6 workflow artifact {artifact}", artifact)
    for artifact in (
        "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
        "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
    ):
        _assert_machine(panel, f"peer-review panel artifact {artifact}", artifact)
    for artifact in (
        "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json",
        "${selected_review_root}/REFEREE-DECISION{round_suffix}.json",
    ):
        _assert_machine(reliability, f"peer-review reliability artifact {artifact}", artifact)
        _assert_machine(boundary, f"peer-review boundary artifact {artifact}", artifact)
    for artifact in (
        "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json",
        "${selected_review_root}/REFEREE-DECISION{round_suffix}.json",
    ):
        _assert_machine(referee, f"peer-review referee artifact {artifact}", artifact)

    _assert_semantic(
        workflow,
        "peer-review workflow Stage 6 files-written write allowlist",
        "gpd_return.files_written",
        "Stage 6 write allowlist",
    )
    for label, source in (
        ("reliability", reliability),
        ("boundary", boundary),
    ):
        _assert_semantic(
            source,
            f"peer-review Stage 6 {label} fresh files-written",
            "fresh `gpd_return.files_written`",
        )
    _assert_semantic(
        referee,
        "peer-review Stage 6 referee current-run file list",
        "return file list may name only paths produced in this Stage 6 run",
        "allowed by `<report_format>`",
    )

    _assert_semantic(
        workflow,
        "peer-review workflow Stage 6 does not modify upstream artifacts",
        "Do not modify",
        "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-*.json",
        "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md",
    )
    _assert_semantic(
        panel,
        "peer-review panel Stage 6 upstream artifacts are evidence",
        "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-*.json",
        "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md",
        "read-only upstream evidence",
    )
    _assert_semantic(
        reliability,
        "peer-review reliability Stage 6 selected upstream roots",
        "${selected_review_root}/CLAIMS{round_suffix}.json",
        "${selected_review_root}/STAGE-*.json",
        "${selected_review_root}/PROOF-REDTEAM{round_suffix}.md",
        "read-only upstream artifacts during Stage 6",
    )
    _assert_semantic(
        boundary,
        "peer-review Stage 6 boundary never lists upstream repairs in files-written",
        "Never create, rewrite, patch, rename, backfill, or list in `files_written`",
    )
    _assert_semantic(
        referee,
        "referee never modifies upstream staged-review inputs",
        "Do NOT modify upstream staged-review inputs",
    )
    _assert_machine(
        referee,
        "referee upstream staged review inputs",
        "CLAIMS{round_suffix}.json",
        "STAGE-*.json",
        "PROOF-REDTEAM{round_suffix}.md",
    )

    _assert_semantic(workflow, "peer-review workflow Stage 6 blocked return", "gpd_return.status: blocked")
    _assert_semantic(
        panel,
        "peer-review panel routes Stage 6 inconsistency upstream",
        "route the inconsistency back",
        "earliest failing upstream stage",
    )
    for label, source in (
        ("reliability", reliability),
        ("boundary", boundary),
        ("referee", referee),
    ):
        _assert_semantic(source, f"peer-review {label} Stage 6 blocked return", "gpd_return.status: blocked")
    _assert_semantic(
        reliability,
        "peer-review reliability names failed Stage 6 upstream repair",
        "Stage 6 repaired upstream artifacts",
    )


def test_peer_review_reliability_reference_documents_runtime_neutral_stage_cleanup() -> None:
    workflow = _peer_review_stage_text("panel-stages.md")
    reliability = (REFERENCES_DIR / "publication" / "peer-review-reliability.md").read_text(encoding="utf-8")
    recovery = (REFERENCES_DIR / "publication" / "stage-recovery-gate.md").read_text(encoding="utf-8")

    _assert_semantic(
        workflow,
        "peer-review stages are fresh one-shot artifact writers",
        "Each stage runs in a fresh subagent context",
        "writes a compact artifact",
    )
    _assert_machine(workflow, "peer-review stage recovery gate path", "stage-recovery-gate.md")

    _assert_semantic(
        reliability,
        "peer-review reliability runtime-neutral cleanup section",
        "Runtime-Neutral Stage Cleanup",
        "stage-recovery-gate.md",
    )
    _assert_machine(reliability, "peer-review reliability stage recovery gate path", "stage-recovery-gate.md")
    _assert_semantic(
        recovery,
        "publication stage recovery one-shot fresh retry behavior",
        "spawned publication child",
        "one-shot",
        "validate or classify every promised artifact",
        "persisted artifacts",
        "prose success text",
        "live child memory",
        "fresh child run from persisted inputs",
        "not a resumed live child",
    )


def test_peer_review_references_keep_generic_claim_kind_out_of_default_theorem_bearing_classification() -> None:
    reliability = (REFERENCES_DIR / "publication" / "peer-review-reliability.md").read_text(encoding="utf-8")
    panel = (REFERENCES_DIR / "publication" / "peer-review-panel.md").read_text(encoding="utf-8")
    referee = (REPO_ROOT / "src" / "gpd" / "agents" / "gpd-referee.md").read_text(encoding="utf-8")

    _assert_semantic(
        reliability,
        "peer-review reliability theorem-bearing status source",
        "theorem-bearing claims in the claim record",
        "The runtime determines theorem-bearing coverage from the claim record itself",
    )
    _assert_forbidden(reliability, "peer-review reliability no claim kind vocabulary", "claim_kind:")

    _assert_semantic(
        panel,
        "peer-review panel theorem-bearing status source",
        "Treat theorem-bearing status from the full Stage 1 Paper `ClaimRecord`, not from the `ProjectContract` `ContractClaim` vocabulary",
        "The theorem-style `claim_kind` values are limited to `theorem`, `lemma`, `corollary`, and `proposition`.",
        "Do not treat `claim_kind: claim` as theorem-bearing by default.",
        "This Paper `ClaimRecord` rule is intentionally different from `ProjectContract.claims[]`",
    )
    _assert_semantic(
        referee,
        "referee non-theorem generic claim kind status",
        "non-theorem-style kinds such as `claim`, `result`, or `other` become theorem-bearing only",
        "including a generic `claim_kind: claim`",
    )
