from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from gpd.core.frontmatter import extract_frontmatter
from gpd.core.proof_redteam import (
    build_proof_redteam_skeleton,
    finalize_proof_redteam_artifact,
    validate_proof_redteam_artifact,
)
from gpd.core.proof_redteam_contract import (
    PROOF_REDTEAM_OPEN_STATUS_VALUES,
    PROOF_REDTEAM_REQUIRED_COVERAGE_SUBSECTIONS,
    PROOF_REDTEAM_REQUIRED_SECTIONS,
    PROOF_REDTEAM_STATUS_VALUES,
)
from tests.manuscript_test_support import write_proof_review_package


def _passed_body(claim_text: str, proof_artifact_path: str) -> str:
    return (
        "# Proof Redteam\n\n"
        "## Proof Inventory\n\n"
        f"- Exact claim / theorem text: {claim_text}\n"
        "- Claim / theorem target: Full theorem statement.\n"
        "- Named parameters:\n"
        "  - `r_0`: target radius\n"
        "- Hypotheses:\n"
        "  - `H1`: positivity hypothesis\n"
        "- Quantifier / domain obligations:\n"
        "  - for every r_0 > 0\n"
        "- Conclusion clauses:\n"
        "  - target annulus is intersected\n\n"
        "## Coverage Ledger\n\n"
        "### Named-Parameter Coverage\n\n"
        "| Parameter | Role / Domain | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"| `r_0` | target radius | {proof_artifact_path}:4 | covered | Kept throughout. |\n\n"
        "### Hypothesis Coverage\n\n"
        "| Hypothesis | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| `H1` | {proof_artifact_path}:2 | covered | Used in the positivity step. |\n\n"
        "### Quantifier / Domain Coverage\n\n"
        "| Obligation | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| `for every r_0 > 0` | {proof_artifact_path}:4 | covered | No specialization introduced. |\n\n"
        "### Conclusion-Clause Coverage\n\n"
        "| Clause | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| target annulus is intersected | {proof_artifact_path}:7 | covered | Final step establishes it. |\n\n"
        "## Adversarial Probe\n\n"
        "- Probe type: dropped-parameter test\n"
        "- Result: The proof still tracks r_0 through the final conclusion.\n\n"
        "## Verdict\n\n"
        "- Scope status: `matched`\n"
        "- Quantifier status: `matched`\n"
        "- Counterexample status: `none_found`\n"
        "- Blocking gaps:\n"
        "  - None.\n\n"
        "## Required Follow-Up\n\n"
        "- None.\n"
    )


def test_proof_redteam_skeleton_defaults_to_gap_status_without_passed_text() -> None:
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
    )

    assert skeleton.target_status == "gaps_found"
    assert skeleton.frontmatter["status"] == "gaps_found"
    assert skeleton.frontmatter["reviewer"] == "gpd-check-proof"
    assert skeleton.frontmatter["claim_ids"] == ["CLM-001"]
    assert skeleton.frontmatter["proof_artifact_paths"] == ["TODO-proof-artifact-path"]
    assert skeleton.frontmatter["missing_parameter_symbols"] == ["TODO-check-named-parameters"]
    assert skeleton.frontmatter["scope_status"] == "unclear"
    assert skeleton.frontmatter["counterexample_status"] == "not_attempted"
    assert "# Proof Redteam" in skeleton.markdown_draft
    assert "## Proof Inventory" in skeleton.markdown_draft
    assert "## Coverage Ledger" in skeleton.markdown_draft
    assert "## Adversarial Probe" in skeleton.markdown_draft
    assert "## Verdict" in skeleton.markdown_draft
    assert "## Required Follow-Up" in skeleton.markdown_draft
    assert "passed" not in skeleton.markdown_draft


def test_proof_redteam_skeleton_supports_human_needed_without_certifying() -> None:
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-002",
        status="human_needed",
        proof_artifact_paths=["paper/theorem.tex", "paper/theorem.tex"],
    )

    assert skeleton.target_status == "human_needed"
    assert skeleton.frontmatter["status"] == "human_needed"
    assert skeleton.frontmatter["proof_artifact_paths"] == ["paper/theorem.tex"]
    assert skeleton.frontmatter["coverage_gaps"] == ["Human judgment is required before this proof audit can close."]
    assert "status: human_needed" in skeleton.frontmatter_yaml
    assert "passed" not in skeleton.markdown_draft


def test_proof_redteam_skeleton_statuses_are_shared_open_statuses() -> None:
    assert PROOF_REDTEAM_STATUS_VALUES == ("passed", "gaps_found", "human_needed")
    assert PROOF_REDTEAM_OPEN_STATUS_VALUES == ("gaps_found", "human_needed")
    assert "passed" not in PROOF_REDTEAM_OPEN_STATUS_VALUES


def test_proof_redteam_skeleton_rejects_passed_status() -> None:
    with pytest.raises(ValueError, match="gaps_found.*human_needed"):
        build_proof_redteam_skeleton(claim_id="CLM-001", status="passed")


def test_proof_redteam_skeleton_requires_complete_manuscript_binding() -> None:
    with pytest.raises(ValueError, match="manuscript_path.*manuscript_sha256.*round_number"):
        build_proof_redteam_skeleton(
            claim_id="CLM-001",
            manuscript_path="paper/main.tex",
        )


def test_validate_proof_redteam_artifact_accepts_conservative_skeleton_with_real_proof_path(
    tmp_path: Path,
) -> None:
    proof_path = tmp_path / "paper" / "theorem.tex"
    proof_path.parent.mkdir(parents=True)
    proof_path.write_text("\\begin{theorem}Demo.\\end{theorem}\n", encoding="utf-8")
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
        proof_artifact_paths=["paper/theorem.tex"],
    )
    artifact_path = tmp_path / "PROOF-REDTEAM.md"
    artifact_path.write_text(skeleton.markdown_draft, encoding="utf-8")

    result = validate_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        expected_claim_ids=("CLM-001",),
        expected_proof_artifact_paths=("paper/theorem.tex",),
    )

    assert result.valid is True
    assert result.status == "gaps_found"
    assert result.errors == []


def test_proof_redteam_skeleton_body_sections_follow_shared_contract() -> None:
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
    )

    for section in PROOF_REDTEAM_REQUIRED_SECTIONS:
        assert section in skeleton.body_stub
    for subsection in PROOF_REDTEAM_REQUIRED_COVERAGE_SUBSECTIONS:
        assert subsection in skeleton.body_stub


@pytest.mark.parametrize("section", PROOF_REDTEAM_REQUIRED_SECTIONS)
def test_validate_proof_redteam_artifact_rejects_missing_shared_required_section(
    tmp_path: Path,
    section: str,
) -> None:
    proof_path = tmp_path / "paper" / "theorem.tex"
    proof_path.parent.mkdir(parents=True)
    proof_path.write_text("\\begin{theorem}Demo.\\end{theorem}\n", encoding="utf-8")
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
        proof_artifact_paths=["paper/theorem.tex"],
    )
    artifact_path = tmp_path / "PROOF-REDTEAM.md"
    artifact_path.write_text(
        skeleton.markdown_draft.replace(section, f"REMOVED-{section.replace('#', '').replace(' ', '-')}", 1),
        encoding="utf-8",
    )

    result = validate_proof_redteam_artifact(artifact_path, project_root=tmp_path)

    assert result.valid is False
    assert result.errors
    assert "proof-redteam body is missing required sections" in result.errors[0]


@pytest.mark.parametrize("subsection", PROOF_REDTEAM_REQUIRED_COVERAGE_SUBSECTIONS)
def test_validate_proof_redteam_artifact_rejects_missing_shared_coverage_subsection(
    tmp_path: Path,
    subsection: str,
) -> None:
    proof_path = tmp_path / "paper" / "theorem.tex"
    proof_path.parent.mkdir(parents=True)
    proof_path.write_text("\\begin{theorem}Demo.\\end{theorem}\n", encoding="utf-8")
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
        proof_artifact_paths=["paper/theorem.tex"],
    )
    artifact_path = tmp_path / "PROOF-REDTEAM.md"
    artifact_path.write_text(
        skeleton.markdown_draft.replace(subsection, f"REMOVED-{subsection.replace('#', '').replace(' ', '-')}", 1),
        encoding="utf-8",
    )

    result = validate_proof_redteam_artifact(artifact_path, project_root=tmp_path)

    assert result.valid is False
    assert result.errors == [f"proof-redteam coverage subsection is empty: {subsection}"]


def test_validate_proof_redteam_artifact_surfaces_existing_parser_errors(tmp_path: Path) -> None:
    proof_path = tmp_path / "paper" / "theorem.tex"
    proof_path.parent.mkdir(parents=True)
    proof_path.write_text("\\begin{theorem}Demo.\\end{theorem}\n", encoding="utf-8")
    skeleton = build_proof_redteam_skeleton(
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
        proof_artifact_paths=["paper/theorem.tex"],
    )
    artifact_path = tmp_path / "PROOF-REDTEAM.md"
    artifact_path.write_text(skeleton.markdown_draft, encoding="utf-8")

    result = validate_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        expected_claim_ids=("CLM-002",),
    )

    assert result.valid is False
    assert result.status is None
    assert result.errors == ["top-level frontmatter `claim_ids` does not match the theorem-bearing claims under review"]


def test_finalize_proof_redteam_artifact_computes_hashes_and_validates_passed_artifact(tmp_path: Path) -> None:
    phase_dir = tmp_path / "GPD" / "phases" / "01-proof"
    proof_path = phase_dir / "derivations" / "theorem-proof.tex"
    proof_path.parent.mkdir(parents=True)
    proof_path.write_text("\\begin{proof}The parameter r_0 is retained.\\end{proof}\n", encoding="utf-8")
    claim_text = "For every r_0 > 0, the orbit intersects the target annulus."
    draft_path = phase_dir / "draft-PROOF-REDTEAM.md"
    draft_path.write_text(_passed_body(claim_text, "derivations/theorem-proof.tex"), encoding="utf-8")
    artifact_path = phase_dir / "01-01-PROOF-REDTEAM.md"

    result = finalize_proof_redteam_artifact(
        draft_path,
        project_root=tmp_path,
        claim_id="CLM-001",
        claim_text=claim_text,
        proof_artifact_path="derivations/theorem-proof.tex",
        reviewed_at="2026-05-07T12:00:00Z",
        output_path=artifact_path,
    )

    expected_proof_sha = hashlib.sha256(proof_path.read_bytes()).hexdigest()
    expected_claim_sha = hashlib.sha256(claim_text.encode("utf-8")).hexdigest()
    expected_audit_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    meta, _body = extract_frontmatter(artifact_path.read_text(encoding="utf-8"))
    assert result.valid is True
    assert result.status == "passed"
    assert result.errors == []
    assert result.proof_artifact_sha256 == expected_proof_sha
    assert result.claim_statement_sha256 == expected_claim_sha
    assert result.audit_artifact_sha256 == expected_audit_sha
    assert result.artifact_sha256 == expected_audit_sha
    assert meta["status"] == "passed"
    assert meta["reviewer"] == "gpd-check-proof"
    assert meta["claim_ids"] == ["CLM-001"]
    assert meta["proof_artifact_paths"] == ["GPD/phases/01-proof/derivations/theorem-proof.tex"]
    assert meta["missing_parameter_symbols"] == []
    assert meta["missing_hypothesis_ids"] == []
    assert meta["coverage_gaps"] == []
    assert meta["scope_status"] == "matched"
    assert meta["quantifier_status"] == "matched"
    assert meta["counterexample_status"] == "none_found"
    assert meta["proof_artifact_sha256"] == expected_proof_sha
    assert meta["claim_statement_sha256"] == expected_claim_sha
    assert meta["reviewed_at"] == "2026-05-07T12:00:00Z"
    assert "audit_artifact_sha256" not in meta
    assert draft_path.read_text(encoding="utf-8").startswith("# Proof Redteam")

    assert result.proof_audit == {
        "completeness": "complete",
        "reviewed_at": "2026-05-07T12:00:00Z",
        "reviewer": "gpd-check-proof",
        "proof_artifact_path": "derivations/theorem-proof.tex",
        "proof_artifact_sha256": expected_proof_sha,
        "audit_artifact_path": "01-01-PROOF-REDTEAM.md",
        "audit_artifact_sha256": expected_audit_sha,
        "claim_statement_sha256": expected_claim_sha,
        "covered_hypothesis_ids": [],
        "missing_hypothesis_ids": [],
        "covered_parameter_symbols": [],
        "missing_parameter_symbols": [],
        "uncovered_quantifiers": [],
        "uncovered_conclusion_clause_ids": [],
        "quantifier_status": "matched",
        "scope_status": "matched",
        "counterexample_status": "none_found",
        "stale": False,
    }

    validation = validate_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        expected_claim_ids=("CLM-001",),
        expected_proof_artifact_paths=("GPD/phases/01-proof/derivations/theorem-proof.tex",),
    )
    assert validation.valid is True
    assert validation.status == "passed"


def test_finalize_proof_redteam_artifact_rejects_missing_proof_artifact(tmp_path: Path) -> None:
    claim_text = "For every r_0 > 0, the orbit intersects the target annulus."
    artifact_path = tmp_path / "PROOF-REDTEAM.md"
    original = _passed_body(claim_text, "paper/missing.tex")
    artifact_path.write_text(original, encoding="utf-8")

    result = finalize_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        claim_id="CLM-001",
        claim_text=claim_text,
        proof_artifact_path="paper/missing.tex",
        reviewed_at="2026-05-07T12:00:00Z",
    )

    assert result.valid is False
    assert result.errors == ["proof_artifact_path does not resolve to a readable file: paper/missing.tex"]
    assert artifact_path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("manuscript_kwargs", "expected_error"),
    [
        (
            {"expected_manuscript_path": "paper/main.tex"},
            "manuscript-scoped proof-redteam finalization requires expected_manuscript_path, "
            "expected_manuscript_sha256, and expected_round",
        ),
        (
            {
                "expected_manuscript_path": " ",
                "expected_manuscript_sha256": "a" * 64,
                "expected_round": 1,
            },
            "expected_manuscript_path must not be blank",
        ),
        (
            {
                "expected_manuscript_path": "paper/main.tex",
                "expected_manuscript_sha256": "not-a-sha",
                "expected_round": 1,
            },
            "expected_manuscript_sha256 must be a lowercase 64-hex digest",
        ),
        (
            {
                "expected_manuscript_path": "paper/main.tex",
                "expected_manuscript_sha256": "a" * 64,
                "expected_round": 0,
            },
            "expected_round must be a positive integer",
        ),
    ],
)
def test_finalize_proof_redteam_artifact_reuses_manuscript_binding_validation(
    tmp_path: Path,
    manuscript_kwargs: dict[str, object],
    expected_error: str,
) -> None:
    result = finalize_proof_redteam_artifact(
        tmp_path / "missing-PROOF-REDTEAM.md",
        project_root=tmp_path,
        claim_id="CLM-001",
        claim_text="For every r_0 > 0, the orbit intersects the target annulus.",
        proof_artifact_path="paper/theorem.tex",
        reviewed_at="2026-05-07T12:00:00Z",
        **manuscript_kwargs,
    )

    assert result.valid is False
    assert result.errors == [expected_error]


@pytest.mark.parametrize(
    ("old_text", "new_text", "expected_fragment"),
    [
        ("## Coverage Ledger", "## Ledger", "proof-redteam body is missing required sections"),
        ("- Probe type:", "- Probe:", "proof-redteam Adversarial Probe must record both probe type and result"),
        ("- Scope status:", "- Scope:", "proof-redteam Verdict must include scope, quantifier, and counterexample"),
    ],
)
def test_finalize_proof_redteam_artifact_rejects_body_missing_required_content(
    tmp_path: Path,
    old_text: str,
    new_text: str,
    expected_fragment: str,
) -> None:
    proof_path = tmp_path / "paper" / "theorem.tex"
    proof_path.parent.mkdir(parents=True)
    proof_path.write_text("\\begin{proof}Demo.\\end{proof}\n", encoding="utf-8")
    claim_text = "For every r_0 > 0, the orbit intersects the target annulus."
    artifact_path = tmp_path / "PROOF-REDTEAM.md"
    original = _passed_body(claim_text, "paper/theorem.tex").replace(old_text, new_text, 1)
    artifact_path.write_text(original, encoding="utf-8")

    result = finalize_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        claim_id="CLM-001",
        claim_text=claim_text,
        proof_artifact_path="paper/theorem.tex",
        reviewed_at="2026-05-07T12:00:00Z",
    )

    assert result.valid is False
    assert result.errors
    assert expected_fragment in result.errors[0]
    assert artifact_path.read_text(encoding="utf-8") == original


def test_validate_proof_redteam_artifact_accepts_existing_passed_artifact(tmp_path: Path) -> None:
    package = write_proof_review_package(
        tmp_path,
        theorem_bearing=True,
        review_report=True,
        proof_redteam_status="passed",
    )
    artifact_path = tmp_path / "GPD" / "review" / "PROOF-REDTEAM.md"

    result = validate_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        expected_claim_ids=("CLM-001",),
        expected_proof_artifact_paths=("paper/curvature_flow_bounds.tex",),
    )

    assert result.valid is True
    assert result.status == "passed"
    assert result.errors == []
    assert package.manuscript_path.exists()


@pytest.mark.parametrize(
    ("old_line", "new_line", "expected_fragment"),
    [
        ("missing_parameter_symbols: []", "missing_parameter_symbols: [r_0]", "missing_parameter_symbols=r_0"),
        ("missing_hypothesis_ids: []", "missing_hypothesis_ids: [H1]", "missing_hypothesis_ids=H1"),
        (
            "coverage_gaps: []",
            "coverage_gaps: ['Proof only establishes the centered case.']",
            "coverage_gaps=Proof only establishes the centered case.",
        ),
        ("scope_status: matched", "scope_status: narrower_than_claim", "scope_status=narrower_than_claim"),
        ("quantifier_status: matched", "quantifier_status: narrowed", "quantifier_status=narrowed"),
        (
            "counterexample_status: none_found",
            "counterexample_status: counterexample_found",
            "counterexample_status=counterexample_found",
        ),
    ],
)
def test_validate_proof_redteam_artifact_rejects_passed_status_with_structured_gap(
    tmp_path: Path,
    old_line: str,
    new_line: str,
    expected_fragment: str,
) -> None:
    write_proof_review_package(
        tmp_path,
        theorem_bearing=True,
        review_report=True,
        proof_redteam_status="passed",
    )
    artifact_path = tmp_path / "GPD" / "review" / "PROOF-REDTEAM.md"
    artifact_path.write_text(
        artifact_path.read_text(encoding="utf-8").replace(old_line, new_line, 1),
        encoding="utf-8",
    )

    result = validate_proof_redteam_artifact(
        artifact_path,
        project_root=tmp_path,
        expected_claim_ids=("CLM-001",),
        expected_proof_artifact_paths=("paper/curvature_flow_bounds.tex",),
    )

    assert result.valid is False
    assert result.status is None
    assert result.errors
    assert expected_fragment in result.errors[0]
