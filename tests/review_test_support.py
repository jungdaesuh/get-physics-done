"""Review artifact fixtures shared by command-level tests."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

from gpd.core.reproducibility import compute_sha256
from tests.helpers.cli import write_managed_publication_manuscript
from tests.manuscript_test_support import manuscript_relpath as canonical_manuscript_relpath

REVIEW_STAGE_IDS = ("reader", "literature", "math", "physics", "interestingness")


def _round_suffix(round_number: int) -> str:
    return "" if round_number <= 1 else f"-R{round_number}"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_review_stage_artifacts(
    project_root: Path,
    artifact_names: tuple[str, ...] | None = None,
    *,
    manuscript_path: str = canonical_manuscript_relpath(),
    proof_bearing: bool = False,
    write_proof_redteam: bool = False,
    proof_redteam_status: str = "passed",
) -> None:
    review_dir = project_root / "GPD" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    manuscript_abspath = (project_root / manuscript_path).resolve(strict=False)
    manuscript_sha256 = compute_sha256(manuscript_abspath) if manuscript_abspath.exists() else "a" * 64
    written_claim_indexes: set[str] = set()
    for artifact_name in artifact_names or tuple(f"STAGE-{stage_id}.json" for stage_id in REVIEW_STAGE_IDS):
        artifact_path = review_dir / artifact_name
        if not artifact_name.startswith("STAGE-") or not artifact_name.endswith(".json"):
            artifact_path.write_text("{}", encoding="utf-8")
            continue

        artifact_stem = artifact_name[len("STAGE-") : -len(".json")]
        if "-R" in artifact_stem:
            stage_id, round_text = artifact_stem.rsplit("-R", 1)
            if not round_text.isdigit():
                artifact_path.write_text("{}", encoding="utf-8")
                continue
            round_number = int(round_text)
            round_suffix = f"-R{round_number}"
        else:
            stage_id = artifact_stem
            round_number = 1
            round_suffix = ""

        if stage_id not in REVIEW_STAGE_IDS:
            artifact_path.write_text("{}", encoding="utf-8")
            continue

        if round_suffix not in written_claim_indexes:
            _write_json(
                review_dir / f"CLAIMS{round_suffix}.json",
                {
                    "version": 1,
                    "manuscript_path": manuscript_path,
                    "manuscript_sha256": manuscript_sha256,
                    "claims": [
                        {
                            "claim_id": "CLM-001",
                            "claim_type": "main_result",
                            "text": (
                                "For every r_0 > 0, the orbit intersects the target annulus."
                                if proof_bearing
                                else "The manuscript makes a test claim."
                            ),
                            "artifact_path": manuscript_path,
                            "section": "Conclusion",
                            "equation_refs": [],
                            "figure_refs": [],
                            "supporting_artifacts": [],
                            "theorem_assumptions": ["chi > 0"] if proof_bearing else [],
                            "theorem_parameters": ["r_0"] if proof_bearing else [],
                        }
                    ],
                },
            )
            written_claim_indexes.add(round_suffix)

        _write_json(
            artifact_path,
            {
                "version": 1,
                "round": round_number,
                "stage_id": stage_id,
                "stage_kind": stage_id,
                "manuscript_path": manuscript_path,
                "manuscript_sha256": manuscript_sha256,
                "claims_reviewed": ["CLM-001"],
                "summary": f"{stage_id} review summary.",
                "strengths": ["Structured review artifact emitted."],
                "findings": [
                    {
                        "issue_id": "REF-001",
                        "claim_ids": ["CLM-001"],
                        "severity": "minor",
                        "summary": "Minor concern.",
                        "rationale": "",
                        "evidence_refs": [f"{manuscript_path}#Conclusion"],
                        "manuscript_locations": [],
                        "support_status": "unclear",
                        "blocking": False,
                        "required_action": "",
                    }
                ],
                "proof_audits": [
                    {
                        "claim_id": "CLM-001",
                        "theorem_assumptions_checked": ["chi > 0"],
                        "theorem_parameters_checked": ["r_0"],
                        "proof_locations": [f"{manuscript_path}:1"],
                        "uncovered_assumptions": [],
                        "uncovered_parameters": [],
                        "coverage_gaps": [],
                        "alignment_status": "aligned",
                        "notes": "Reviewed against theorem inventory.",
                    }
                ]
                if proof_bearing and stage_id == "math"
                else [],
                "confidence": "medium",
                "recommendation_ceiling": "major_revision",
            },
        )

    if write_proof_redteam:
        for round_suffix in written_claim_indexes:
            (review_dir / f"PROOF-REDTEAM{round_suffix}.md").write_text(
                proof_redteam_markdown(
                    manuscript_path=manuscript_path,
                    manuscript_sha256=manuscript_sha256,
                    proof_redteam_status=proof_redteam_status,
                    round_number=1 if not round_suffix else int(round_suffix.removeprefix("-R")),
                ),
                encoding="utf-8",
            )


def proof_redteam_markdown(
    *,
    manuscript_path: str,
    manuscript_sha256: str,
    proof_redteam_status: str,
    round_number: int,
) -> str:
    return (
        "---\n"
        f"status: {proof_redteam_status}\n"
        "reviewer: gpd-check-proof\n"
        "claim_ids:\n"
        "  - CLM-001\n"
        "proof_artifact_paths:\n"
        f"  - {manuscript_path}\n"
        f"manuscript_path: {manuscript_path}\n"
        f"manuscript_sha256: {manuscript_sha256}\n"
        f"round: {round_number}\n"
        "missing_parameter_symbols: []\n"
        "missing_hypothesis_ids: []\n"
        "coverage_gaps: []\n"
        "scope_status: matched\n"
        "quantifier_status: matched\n"
        "counterexample_status: none_found\n"
        "---\n\n"
        "# Proof Redteam\n"
        "## Proof Inventory\n"
        "- Exact claim / theorem text: For every r_0 > 0, the orbit intersects the target annulus.\n"
        "- Claim / theorem target: Annulus intersection for every target radius.\n"
        "- Named parameters:\n"
        "  - `r_0`: target radius\n"
        "- Hypotheses:\n"
        "  - `H1`: chi > 0\n"
        "- Quantifier / domain obligations:\n"
        "  - for every r_0 > 0\n"
        "- Conclusion clauses:\n"
        "  - annulus intersection holds\n"
        "## Coverage Ledger\n"
        "### Named-Parameter Coverage\n"
        "| Parameter | Role / Domain | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| `r_0` | target radius | {manuscript_path}:1 | covered | Tracked explicitly. |\n"
        "### Hypothesis Coverage\n"
        "| Hypothesis | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| `H1` | {manuscript_path}:1 | covered | Used in the proof. |\n"
        "### Quantifier / Domain Coverage\n"
        "| Obligation | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| `for every r_0 > 0` | {manuscript_path}:1 | covered | No narrowing introduced. |\n"
        "### Conclusion-Clause Coverage\n"
        "| Clause | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| annulus intersection holds | {manuscript_path}:1 | covered | Final theorem statement matches. |\n"
        "## Adversarial Probe\n"
        "- Probe type: dropped-parameter test\n"
        "- Result: The proof still references r_0, so the full claim survives.\n"
        "## Verdict\n"
        "- Scope status: `matched`\n"
        "- Quantifier status: `matched`\n"
        "- Counterexample status: `none_found`\n"
        "- Blocking gaps:\n"
        "  - None.\n"
        "## Required Follow-Up\n"
        "- None.\n"
    )


def write_publication_review_outcome(
    project_root: Path,
    *,
    final_recommendation: str = "accept",
    round_number: int = 1,
    blocking_issue_ids: list[str] | None = None,
    manuscript_path: str = canonical_manuscript_relpath(),
    proof_bearing: bool = False,
    write_proof_redteam: bool = False,
    proof_redteam_status: str = "passed",
) -> None:
    review_dir = project_root / "GPD" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    round_suffix = _round_suffix(round_number)
    stage_artifact_names = tuple(f"STAGE-{stage_id}{round_suffix}.json" for stage_id in REVIEW_STAGE_IDS)
    write_review_stage_artifacts(
        project_root,
        artifact_names=stage_artifact_names,
        manuscript_path=manuscript_path,
        proof_bearing=proof_bearing,
        write_proof_redteam=write_proof_redteam,
        proof_redteam_status=proof_redteam_status,
    )
    unresolved_blocking_issue_ids = blocking_issue_ids or []
    _write_json(
        review_dir / f"REVIEW-LEDGER{round_suffix}.json",
        {
            "version": 1,
            "round": round_number,
            "manuscript_path": manuscript_path,
            "issues": [
                {
                    "issue_id": issue_id,
                    "opened_by_stage": "reader",
                    "severity": "major",
                    "blocking": True,
                    "claim_ids": ["CLM-001"],
                    "summary": "Blocking review issue.",
                    "rationale": "",
                    "evidence_refs": [],
                    "required_action": "Revise the manuscript.",
                    "status": "open",
                }
                for issue_id in unresolved_blocking_issue_ids
            ],
        },
    )
    _write_json(
        review_dir / f"REFEREE-DECISION{round_suffix}.json",
        {
            "manuscript_path": manuscript_path,
            "target_journal": "jhep",
            "final_recommendation": final_recommendation,
            "final_confidence": "medium",
            "stage_artifacts": [f"GPD/review/{name}" for name in stage_artifact_names],
            "central_claims_supported": True,
            "claim_scope_proportionate_to_evidence": True,
            "physical_assumptions_justified": True,
            "unsupported_claims_are_central": False,
            "reframing_possible_without_new_results": True,
            "proof_audit_coverage_complete": True,
            "theorem_proof_alignment_adequate": True,
            "mathematical_correctness": "adequate",
            "novelty": "adequate",
            "significance": "adequate",
            "venue_fit": "adequate",
            "literature_positioning": "adequate",
            "unresolved_major_issues": len(unresolved_blocking_issue_ids),
            "unresolved_minor_issues": 0,
            "blocking_issue_ids": unresolved_blocking_issue_ids,
        },
    )


def move_publication_review_outcome_to_subject_review(
    project_root: Path,
    *,
    subject_slug: str,
    round_number: int = 1,
) -> None:
    round_suffix = _round_suffix(round_number)
    global_review_dir = project_root / "GPD" / "review"
    subject_review_dir = project_root / "GPD" / "publication" / subject_slug / "review"
    subject_review_dir.mkdir(parents=True, exist_ok=True)
    stage_names = [f"STAGE-{stage_id}{round_suffix}.json" for stage_id in REVIEW_STAGE_IDS]
    for name in (
        *stage_names,
        f"CLAIMS{round_suffix}.json",
        f"REVIEW-LEDGER{round_suffix}.json",
        f"REFEREE-DECISION{round_suffix}.json",
    ):
        source = global_review_dir / name
        target = subject_review_dir / name
        target.write_bytes(source.read_bytes())
        source.unlink()
    decision_path = subject_review_dir / f"REFEREE-DECISION{round_suffix}.json"
    decision_payload = json.loads(decision_path.read_text(encoding="utf-8"))
    decision_payload["stage_artifacts"] = [f"GPD/publication/{subject_slug}/review/{name}" for name in stage_names]
    _write_json(decision_path, decision_payload)


def write_managed_arxiv_submission_package(
    project_root: Path,
    *,
    subject_slug: str = "curvature-flow",
    entrypoint_name: str = "managed_manuscript.tex",
    tex_body: str = "\\documentclass{article}\n\\begin{document}\nManaged manuscript.\n\\end{document}\n",
    extra_files: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    arxiv_root = project_root / "GPD" / "publication" / subject_slug / "arxiv"
    submission_dir = arxiv_root / "submission"
    submission_dir.mkdir(parents=True, exist_ok=True)
    (submission_dir / entrypoint_name).write_text(tex_body, encoding="utf-8")
    for relative_path, content in (extra_files or {}).items():
        target = submission_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    tarball = arxiv_root / "arxiv-submission.tar.gz"
    with tarfile.open(tarball, "w:gz") as archive:
        for path in sorted(submission_dir.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(submission_dir).as_posix(), recursive=False)
    return submission_dir, tarball


def update_claim_index_claim(
    project_root: Path,
    *,
    round_number: int = 1,
    **overrides: object,
) -> None:
    claims_path = project_root / "GPD" / "review" / f"CLAIMS{_round_suffix(round_number)}.json"
    claims_payload = json.loads(claims_path.read_text(encoding="utf-8"))
    claims_payload["claims"][0].update(overrides)
    _write_json(claims_path, claims_payload)


def prepare_accepted_managed_arxiv_subject(
    project_root: Path,
    *,
    subject_slug: str = "curvature-flow",
    managed_manuscript_path: str = "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex",
) -> tuple[str, Path]:
    manuscript = write_managed_publication_manuscript(project_root, subject_slug=subject_slug)
    write_publication_review_outcome(
        project_root,
        final_recommendation="accept",
        manuscript_path=managed_manuscript_path,
    )
    move_publication_review_outcome_to_subject_review(project_root, subject_slug=subject_slug)
    return managed_manuscript_path, manuscript


def write_publication_response_round(
    project_root: Path,
    *,
    round_number: int,
    subject_slug: str = "curvature-flow",
) -> None:
    round_suffix = _round_suffix(round_number)
    subject_root = project_root / "GPD" / "publication" / subject_slug
    review_dir = subject_root / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (subject_root / f"AUTHOR-RESPONSE{round_suffix}.md").write_text("# Author Response\n", encoding="utf-8")
    (review_dir / f"REFEREE_RESPONSE{round_suffix}.md").write_text("# Referee Response\n", encoding="utf-8")


def write_draft_knowledge_document(
    workspace: Path,
    *,
    knowledge_id: str = "K-renormalization-group-fixed-points",
    relative_dir: str = "GPD/knowledge",
) -> Path:
    knowledge_dir = workspace / relative_dir
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    knowledge_path = knowledge_dir / f"{knowledge_id}.md"
    knowledge_path.write_text(
        "---\n"
        "knowledge_schema_version: 1\n"
        f"knowledge_id: {knowledge_id}\n"
        "title: Renormalization Group Fixed Points\n"
        "topic: renormalization-group\n"
        "status: draft\n"
        "created_at: 2026-04-07T12:00:00Z\n"
        "updated_at: 2026-04-07T12:00:00Z\n"
        "sources:\n"
        "  - source_id: source-main\n"
        "    kind: paper\n"
        "    locator: Doe et al., 2024\n"
        "    title: Renormalization Group Fixed Points\n"
        "    why_it_matters: Trusted source for the topic\n"
        "coverage_summary:\n"
        "  covered_topics: [fixed points]\n"
        "  excluded_topics: [implementation]\n"
        "  open_gaps: [review approval]\n"
        "---\n\n"
        "Draft knowledge body.\n",
        encoding="utf-8",
    )
    return knowledge_path
