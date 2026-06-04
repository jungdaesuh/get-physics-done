from __future__ import annotations

from pathlib import Path

from gpd import registry
from tests.lifecycle_contract_test_support import (
    artifact_paths,
    child_gate_from_text,
)
from tests.lifecycle_contract_test_support import (
    assert_forbidden_lifecycle_prose as _assert_forbidden_semantic,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
PUBLICATION_REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references/publication"
PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE = "@{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md"
PUBLICATION_BOOTSTRAP_PREFLIGHT_PATH = "{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md"
PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE = (
    "{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md"
)
PUBLICATION_ROUND_ARTIFACTS_INCLUDE = "{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md"
PUBLICATION_REVIEW_RELIABILITY_INCLUDE = "{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md"
PUBLICATION_REVIEW_RELIABILITY_INLINE = "{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md"
PEER_REVIEW_STAGE_FILES = (
    "bootstrap.md",
    "preflight.md",
    "artifact-discovery.md",
    "panel-stages.md",
    "final-adjudication.md",
    "finalize.md",
)


def _workflow_text(name: str) -> str:
    if name in {
        "arxiv-submission.md",
        "write-paper.md",
        "peer-review.md",
        "respond-to-referees.md",
        "verify-work.md",
    }:
        return workflow_authority_text(WORKFLOWS_DIR, name)
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _peer_review_stage_text(*names: str) -> str:
    stage_names = names or PEER_REVIEW_STAGE_FILES
    return "\n".join((WORKFLOWS_DIR / "peer-review" / name).read_text(encoding="utf-8") for name in stage_names)


def _command_text(name: str) -> str:
    return (COMMANDS_DIR / name).read_text(encoding="utf-8")


def _publication_reference_text(name: str) -> str:
    return (PUBLICATION_REFERENCES_DIR / name).read_text(encoding="utf-8")


def _assert_arxiv_submission_gate_semantics(workflow: str, shared_preflight: str) -> None:
    combined = f"{workflow}\n{shared_preflight}"
    _assert_semantic(
        combined,
        "arxiv submission bootstrap and review gate semantics",
        "shared publication bootstrap reference",
        "source of truth",
        "latest staged",
        "REVIEW-LEDGER",
        "REFEREE-DECISION",
        "accept",
        "minor_revision",
        "unresolved blocking issues",
        "manuscript_proof_review",
        "strict preflight source of truth",
        "resolved manuscript root",
        "supported roots",
        "arbitrary external directories",
        "preflight-resolved entrypoint",
        "tarballs beside the manuscript root",
    )


def _assert_managed_subject_review_root_semantics(text: str) -> None:
    assert "selected_publication_root" in text
    assert "selected_review_root" in text
    _assert_semantic(
        text,
        "managed publication review artifacts use selected root",
        "managed-subject",
        "global `GPD/review`",
        "fallback",
    )


def test_write_paper_workflow_runs_centralized_review_preflight() -> None:
    workflow = _workflow_text("write-paper.md")
    shared_preflight = (REPO_ROOT / "src/gpd/specs/templates/paper/publication-manuscript-root-preflight.md").read_text(
        encoding="utf-8"
    )

    assert "gpd validate review-preflight write-paper --strict" in workflow
    _assert_semantic(
        workflow,
        "write-paper centralized command-context preflight",
        "centralized command-context preflight",
        "write-paper",
        "stop before",
    )
    assert "publication-bootstrap-preflight.md" in workflow
    assert PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE in workflow
    staging = registry.get_command("write-paper").staged_loading
    assert staging is not None
    round_artifacts_authority = PUBLICATION_ROUND_ARTIFACTS_INCLUDE.removeprefix("{GPD_INSTALL_DIR}/")
    assert round_artifacts_authority in staging.stage("publication_review").loaded_authorities
    _assert_semantic(
        shared_preflight,
        "publication preflight rejects copied artifacts and wildcard scans",
        "artifacts copied from another manuscript root",
        "Do not use ad hoc wildcard discovery",
        "first-match filename scans",
    )
    assert "gpd paper-build" in shared_preflight
    assert "bibliography_audit_clean" in shared_preflight
    assert "reproducibility_ready" in shared_preflight
    assert "missing manuscript" not in workflow
    assert "`PAPER_DIR` to `publication_bootstrap_root`" in workflow
    assert "${PAPER_DIR}/{topic_specific_stem}.tex" in workflow


def test_respond_to_referees_workflow_runs_centralized_review_preflight() -> None:
    workflow = _workflow_text("respond-to-referees.md")
    command = _command_text("respond-to-referees.md")
    shared_preflight = (REPO_ROOT / "src/gpd/specs/templates/paper/publication-manuscript-root-preflight.md").read_text(
        encoding="utf-8"
    )

    assert "context_mode: project-aware" in command
    assert 'argument-hint: "[--manuscript PATH] (--report PATH [--report PATH...] | paste)"' in command
    assert "command-policy:" in command
    assert "subject_kind: publication" in command
    assert "explicit_input_kinds:" in command
    assert "- manuscript_path" in command
    assert "- referee_report_path" in command
    assert "- paste_referee_report" in command
    assert "allow_external_subjects: true" in command
    assert "requires:" not in command
    assert "default_output_subtree: GPD" in command
    assert "scope_variants:" in command
    assert "scope: explicit_external_manuscript" in command
    _assert_semantic(
        command,
        "respond-to-referees publication root mode ownership",
        "Project-backed response rounds",
        "global `GPD/` / `GPD/review/` ownership",
        "subject-owned publication root",
        "GPD/publication/{subject_slug}",
    )
    _assert_semantic(
        workflow,
        "respond-to-referees preflight arguments are normalized before shell",
        "PREFLIGHT_ARGUMENTS",
        "validator-safe normalized intake string",
        "before shelling out",
        "gpd:respond-to-referees --manuscript",
    )
    assert 'gpd --raw validate command-context respond-to-referees -- "$PREFLIGHT_ARGUMENTS"' in workflow
    assert 'gpd validate review-preflight respond-to-referees "$ARGUMENTS" --strict' in workflow
    assert 'gpd validate review-preflight respond-to-referees --strict -- "$PREFLIGHT_ARGUMENTS"' in workflow
    assert "gpd validate review-preflight respond-to-referees --strict" in workflow
    assert 'cd "$PROJECT_ROOT"' in workflow
    for stage_id in ("report_triage", "revision_planning", "response_authoring", "finalize"):
        assert f'gpd --raw init respond-to-referees --stage {stage_id} -- "$ARGUMENTS"' in workflow
    _assert_semantic(
        workflow,
        "respond-to-referees intake and external subject preflight contract",
        "bare positional path",
        "referee-report source only",
        "end-of-options marker",
        "mandatory",
        "missing referee report source",
        "external-manuscript mode",
        "advisory only",
    )
    _assert_semantic(
        workflow,
        "respond-to-referees spawned writer checkpoint uses stage recovery",
        "spawned agent",
        "needs user input",
        "publication stage-recovery gate",
        "checkpoint semantics",
        "status: checkpoint",
    )
    _assert_semantic(
        workflow, "respond-to-referees shared bootstrap preflight", "shared publication bootstrap preflight"
    )
    assert PUBLICATION_BOOTSTRAP_PREFLIGHT_PATH in workflow
    assert PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE in workflow
    assert "bibliography_audit_clean" in shared_preflight
    assert "reproducibility_ready" in shared_preflight
    _assert_semantic(
        workflow,
        "respond-to-referees mirrored response artifacts complete handoff",
        "expected mirrored artifacts",
        "exist on disk",
        "AUTHOR-RESPONSE",
        "REFEREE_RESPONSE",
    )
    assert (
        "import or normalize it into `${RESPONSE_PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md` before parsing comments"
        in workflow
    )
    _assert_semantic(
        workflow,
        "respond-to-referees response outputs stay under selected GPD roots",
        "AUTHOR-RESPONSE",
        "REFEREE_RESPONSE",
        "beside `${PAPER_DIR}`",
        "imported report source",
        "selected GPD roots",
    )
    assert "selected_publication_root` / `selected_review_root" in workflow
    assert "find \"${RESPONSE_REVIEW_ROOT}\" -maxdepth 1 -type f -name 'REVIEW-LEDGER*.json' -print" in workflow
    assert "find GPD/review -maxdepth 1 -type f -name 'REVIEW-LEDGER*.json'" not in workflow
    _assert_semantic(
        workflow,
        "respond-to-referees does not duplicate response pair across roots",
        "Do not duplicate the pair",
        "subject-owned root",
        "global project root",
        "one run",
    )
    assert "${PAPER_DIR}/response-letter.tex" in workflow
    assert "${PAPER_DIR}/{section}.tex" in workflow


def test_arxiv_submission_workflow_runs_centralized_review_preflight() -> None:
    workflow = _workflow_text("arxiv-submission.md")
    shared_preflight = (REPO_ROOT / "src/gpd/specs/templates/paper/publication-manuscript-root-preflight.md").read_text(
        encoding="utf-8"
    )

    assert 'gpd --raw validate review-preflight arxiv-submission --strict -- "${ARGUMENTS}"' in workflow
    assert "gpd --raw validate review-preflight arxiv-submission --strict" in workflow
    assert 'gpd --raw init arxiv-submission --stage bootstrap -- "$ARGUMENTS"' in workflow
    assert 'gpd --raw init arxiv-submission --stage manuscript_preflight -- "$ARGUMENTS"' in workflow
    assert 'gpd --raw init arxiv-submission --stage review_gate -- "$ARGUMENTS"' in workflow
    assert 'gpd --raw init arxiv-submission --stage package -- "$ARGUMENTS"' in workflow
    assert 'gpd --raw init arxiv-submission --stage finalize -- "$ARGUMENTS"' in workflow
    _assert_arxiv_submission_gate_semantics(workflow, shared_preflight)
    assert PUBLICATION_BOOTSTRAP_PREFLIGHT_PATH in workflow
    assert PUBLICATION_REVIEW_RELIABILITY_INCLUDE not in workflow
    assert "staged `peer-review-reliability.md` reference" in workflow
    assert PUBLICATION_ROUND_ARTIFACTS_INCLUDE in workflow
    assert PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE not in workflow
    for artifact_name in ("ARTIFACT-MANIFEST.json", "BIBLIOGRAPHY-AUDIT.json", "reproducibility-manifest.json"):
        assert artifact_name in shared_preflight
    assert "bibliography_audit_clean" in shared_preflight
    assert "reproducibility_ready" in shared_preflight
    for artifact_name in ("ARTIFACT-MANIFEST.json", "BIBLIOGRAPHY-AUDIT.json"):
        assert artifact_name in workflow
    assert "manuscript_entrypoint" in workflow
    assert "manuscript_root" in workflow
    assert 'MAIN_SOURCE=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")' in workflow
    assert 'PACKAGE_ROOT="${PUBLICATION_ROOT}/arxiv"' in workflow
    assert 'SUBMISSION_DIR="${PACKAGE_ROOT}/submission"' in workflow
    assert 'PACKAGE_TARBALL="${PACKAGE_ROOT}/arxiv-submission.tar.gz"' in workflow
    assert (
        'gpd --raw validate arxiv-package --materialize --submission-dir "$SUBMISSION_DIR" --tarball "$PACKAGE_TARBALL"'
        in workflow
    )
    assert "PACKAGE_VALIDATION" in workflow


def test_peer_review_workflow_runs_centralized_review_preflight_with_explicit_arguments() -> None:
    preflight = _peer_review_stage_text("preflight.md")
    panel = _peer_review_stage_text("panel-stages.md")
    final = _peer_review_stage_text("final-adjudication.md")

    assert 'gpd validate review-preflight peer-review --strict -- "$REVIEW_TARGET"' in preflight
    assert "gpd validate review-preflight peer-review --strict)" in preflight
    assert "stage-recovery-gate.md" in panel
    assert "checkpoint continuation" in panel
    gate = child_gate_from_text(final, "peer_review_stage6_referee")
    assert gate.required_status == "completed"
    assert artifact_paths(gate) == (
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md",
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex",
        "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
        "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
        "${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md when produced",
    )
    _assert_semantic(
        final,
        "peer-review Stage 6 closure requires typed return artifacts and validators",
        "success text",
        "typed return",
        "on-disk files",
        "validators all agree",
    )


def test_peer_review_prompts_do_not_route_managed_subjects_to_global_review_root() -> None:
    command = _command_text("peer-review.md")
    workflow = _peer_review_stage_text()
    round_reference = _publication_reference_text("publication-review-round-artifacts.md")
    reliability_reference = _publication_reference_text("peer-review-reliability.md")

    assert "centralized preflight's selected publication/review roots" in command
    assert "Never write managed-subject review artifacts to the global `GPD/review` fallback." in command
    assert "not under the default global `GPD/review` path" in command
    _assert_forbidden_semantic(
        reliability_reference,
        "peer-review reliability avoids stale invoking-workspace global fallback prose",
        "while still writing review artifacts under `GPD/` in the invoking workspace",
    )
    _assert_forbidden_semantic(
        workflow,
        "peer-review workflow avoids stale selected-root fallback prose",
        "Write review artifacts under the target-aware `selected_review_root`, falling back to `GPD/review`.",
    )

    for text in (workflow, round_reference, reliability_reference):
        _assert_managed_subject_review_root_semantics(text)


def test_publication_review_workflows_reference_shared_manuscript_root_contract() -> None:
    for command_name in ("respond-to-referees.md", "arxiv-submission.md"):
        command_text = _command_text(command_name)
        assert PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE not in command_text
        assert PUBLICATION_ROUND_ARTIFACTS_INCLUDE not in command_text
        assert PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE not in command_text
        assert PUBLICATION_REVIEW_RELIABILITY_INCLUDE not in command_text

    for workflow_name in ("respond-to-referees.md", "arxiv-submission.md"):
        workflow_text = _workflow_text(workflow_name)
        assert PUBLICATION_BOOTSTRAP_PREFLIGHT_PATH in workflow_text
        if workflow_name == "respond-to-referees.md":
            assert PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE in workflow_text
            assert PUBLICATION_REVIEW_RELIABILITY_INLINE in workflow_text
        else:
            assert PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE not in workflow_text
            assert PUBLICATION_ROUND_ARTIFACTS_INCLUDE in workflow_text
            assert PUBLICATION_REVIEW_RELIABILITY_INCLUDE not in workflow_text
            assert "staged `peer-review-reliability.md` reference" in workflow_text


def test_verify_work_workflow_runs_centralized_review_preflight() -> None:
    workflow = _workflow_text("verify-work.md")

    assert 'gpd validate review-preflight verify-work "${PHASE_ARG}" --strict' in workflow
    assert "gpd validate review-preflight verify-work --strict" in workflow


def test_review_knowledge_workflow_keeps_strict_current_workspace_canonical_target_contract() -> None:
    workflow = _workflow_text("review-knowledge.md")
    command = _command_text("review-knowledge.md")

    assert "context_mode: project-aware" in command
    assert "review_mode: review" in command
    assert "knowledge_target" in command
    assert "knowledge_document" in command
    assert "knowledge_review_freshness" in command
    assert "missing project state" not in command
    assert "GPD/knowledge/reviews/{knowledge_id}-R{review_round}-REVIEW.md" in command
    assert "{round_suffix}" not in command
    _assert_semantic(
        workflow,
        "review-knowledge stays bound to current workspace",
        "workspace the user invoked from",
        "explicit current-workspace target",
        "do not auto-reenter",
        "different recent project",
    )
    assert 'CONTEXT=$(gpd --raw validate command-context review-knowledge "$ARGUMENTS")' in workflow
    assert 'REVIEW_PREFLIGHT=$(gpd --raw validate review-preflight review-knowledge "$ARGUMENTS" --strict)' in workflow
    assert 'echo "$REVIEW_PREFLIGHT"' in workflow
    assert "GPD/knowledge/{knowledge_id}.md" in workflow
    assert "K-*" in workflow
    _assert_semantic(
        workflow,
        "review-knowledge accepts only canonical target forms",
        "Accept only",
        "exact current-workspace",
        "canonical",
        "resolves uniquely",
        "Do not guess",
        "fuzzy topic text",
    )
