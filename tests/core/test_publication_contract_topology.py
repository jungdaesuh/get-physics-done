from __future__ import annotations

import json
from pathlib import Path

from gpd.core.workflow_staging import validate_workflow_stage_manifest_payload
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
REFERENCES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "references" / "publication"
TEMPLATES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "templates" / "paper"


def _load_manifest(workflow_name: str) -> object:
    return validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / f"{workflow_name}-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id=workflow_name,
    )


def _assert_all_present(text: str, fragments: tuple[str, ...]) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    assert missing == []


def _assert_all_absent(text: str, fragments: tuple[str, ...]) -> None:
    present = [fragment for fragment in fragments if fragment in text]
    assert present == []


def test_publication_contract_files_use_canonical_names_without_compatibility_shims() -> None:
    round_contract = (REFERENCES_DIR / "publication-review-round-artifacts.md").read_text(encoding="utf-8")
    response_contract = (REFERENCES_DIR / "publication-response-artifacts.md").read_text(encoding="utf-8")
    bootstrap_preflight = (REFERENCES_DIR / "publication-bootstrap-preflight.md").read_text(encoding="utf-8")
    response_handoff = (REFERENCES_DIR / "publication-response-writer-handoff.md").read_text(encoding="utf-8")
    wrapper_guidance = (REFERENCES_DIR / "publication-review-wrapper-guidance.md").read_text(encoding="utf-8")
    manuscript_preflight = (TEMPLATES_DIR / "publication-manuscript-root-preflight.md").read_text(encoding="utf-8")

    _assert_all_present(
        round_contract,
        (
            "Canonical round-suffix and sibling-artifact contract for publication review rounds.",
            "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md",
            "${selected_publication_root}/REFEREE-REPORT{round_suffix}.tex",
            "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md",
            "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md",
            "${selected_review_root}/PROOF-REDTEAM{round_suffix}.md",
        ),
    )
    _assert_all_absent(round_contract, ("review-round-artifact-contract.md",))

    _assert_all_present(
        response_contract,
        (
            "Canonical paired response-artifact and one-shot child-return contract for referee-response work.",
            "gpd_return.files_written",
            "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md",
            "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md",
            "explicit active manuscript gates",
            "Default current-project response files without frontmatter",
            "existing project-root response rounds",
            "new files should carry the binding metadata",
        ),
    )
    _assert_all_absent(response_contract.lower(), ("backwards compatibility",))
    _assert_all_absent(response_contract, ("response-artifact-contract.md",))

    _assert_all_present(
        bootstrap_preflight,
        ("Canonical workflow-facing bootstrap and preflight reference for publication tasks.",),
    )
    _assert_all_absent(bootstrap_preflight, ("publication-artifact-gates.md",))
    _assert_all_present(
        response_handoff,
        ("Canonical workflow-facing handoff and completion reference for spawned response-writing work.",),
    )
    _assert_all_absent(response_handoff, ("publication-artifact-gates.md",))
    _assert_all_present(
        wrapper_guidance,
        ("publication-bootstrap-preflight.md", "publication-response-writer-handoff.md"),
    )
    _assert_all_absent(wrapper_guidance, ("publication-artifact-gates.md",))

    _assert_all_present(
        manuscript_preflight,
        (
            "gpd paper-build",
            "bibliography_audit_clean",
            "reproducibility_ready",
            "GPD/publication/{subject_slug}/intake/",
            "GPD/publication/{subject_slug}/manuscript/",
            "do not let `intake/` participate in manuscript-root discovery",
        ),
    )
    _assert_all_absent(manuscript_preflight, ("publication-artifact-gates.md",))


def test_publication_workflows_and_agents_reference_only_the_canonical_publication_contracts() -> None:
    for path in (
        AGENTS_DIR / "gpd-paper-writer.md",
        AGENTS_DIR / "gpd-referee.md",
        WORKFLOWS_DIR / "write-paper.md",
        WORKFLOWS_DIR / "respond-to-referees.md",
        WORKFLOWS_DIR / "peer-review.md",
        WORKFLOWS_DIR / "arxiv-submission.md",
    ):
        if path.parent == WORKFLOWS_DIR and path.stem in {"write-paper", "peer-review", "respond-to-referees"}:
            text = workflow_authority_text(WORKFLOWS_DIR, path.stem)
        else:
            text = path.read_text(encoding="utf-8")
        _assert_all_absent(
            text,
            ("publication-artifact-gates.md", "review-round-artifact-contract.md", "response-artifact-contract.md"),
        )

    paper_writer = (AGENTS_DIR / "gpd-paper-writer.md").read_text(encoding="utf-8")
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    _assert_all_present(paper_writer, ("publication-response-writer-handoff.md",))
    _assert_all_absent(paper_writer, ("publication-response-artifacts.md", "publication-review-round-artifacts.md"))
    _assert_all_present(referee, ("publication-review-round-artifacts.md", "publication-response-artifacts.md"))


def test_publication_workflow_prompt_surfaces_surface_the_shared_manuscript_root_contract_before_round_or_response_policy() -> (
    None
):
    write_paper = workflow_authority_text(WORKFLOWS_DIR, "write-paper")
    respond = workflow_authority_text(WORKFLOWS_DIR, "respond-to-referees")
    peer_review = workflow_authority_text(WORKFLOWS_DIR, "peer-review")
    arxiv = workflow_authority_text(WORKFLOWS_DIR, "arxiv-submission")
    handoff_include = "{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md"
    respond_manifest = _load_manifest("respond-to-referees")
    peer_manifest = _load_manifest("peer-review")
    arxiv_manifest = _load_manifest("arxiv-submission")

    _assert_all_present(write_paper, ("publication-bootstrap-preflight.md", "publication-response-writer-handoff.md"))
    _assert_all_present(respond, ("publication-bootstrap-preflight.md", handoff_include))
    _assert_all_present(arxiv, ("publication-bootstrap-preflight.md",))
    _assert_all_present(peer_review, ("templates/paper/publication-manuscript-root-preflight.md",))
    assert (
        "references/publication/publication-bootstrap-preflight.md"
        in respond_manifest.stage("bootstrap").loaded_authorities
    )
    assert (
        "references/publication/publication-bootstrap-preflight.md"
        in arxiv_manifest.stage("bootstrap").loaded_authorities
    )
    assert (
        "templates/paper/publication-manuscript-root-preflight.md"
        in peer_manifest.stage("preflight").loaded_authorities
    )
    _assert_all_absent(peer_review, ("publication-response-artifacts.md",))
    _assert_all_absent(arxiv, ("@{GPD_INSTALL_DIR}/references/publication/publication-response-artifacts.md",))
