"""Focused CLI tests for review-validation commands split from test_cli_commands."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.cli import app
from tests.helpers.cli import json_output_from_result
from tests.manuscript_test_support import CANONICAL_MANUSCRIPT_STEM
from tests.test_cli_commands import (
    _CANONICAL_MANUSCRIPT_BASENAME,
    _CANONICAL_MANUSCRIPT_REL,
    _help_text,
    _manuscript_entrypoint_relpath,
    _raw_json,
    _write_review_stage_artifacts,
    runner,
)
from tests.test_cli_commands import (
    _chdir as _chdir,
)
from tests.test_cli_commands import (
    gpd_project as gpd_project,
)


def test_validate_paper_quality_command(gpd_project: Path) -> None:
    quality_path = gpd_project / "paper-quality.json"
    quality_path.write_text(
        json.dumps(
            {
                "title": "Review-grade paper",
                "journal": "prd",
                "equations": {
                    "labeled": {"satisfied": 4, "total": 4},
                    "symbols_defined": {"satisfied": 4, "total": 4},
                    "dimensionally_verified": {"satisfied": 4, "total": 4},
                    "limiting_cases_verified": {"satisfied": 4, "total": 4},
                },
                "figures": {
                    "axes_labeled_with_units": {"satisfied": 2, "total": 2},
                    "error_bars_present": {"satisfied": 2, "total": 2},
                    "referenced_in_text": {"satisfied": 2, "total": 2},
                    "captions_self_contained": {"satisfied": 2, "total": 2},
                    "colorblind_safe": {"satisfied": 2, "total": 2},
                },
                "citations": {
                    "citation_keys_resolve": {"satisfied": 5, "total": 5},
                    "missing_placeholders": {"passed": True},
                    "key_prior_work_cited": {"passed": True},
                    "hallucination_free": {"passed": True},
                },
                "conventions": {
                    "convention_lock_complete": {"passed": True},
                    "assert_convention_coverage": {"satisfied": 3, "total": 3},
                    "notation_consistent": {"passed": True},
                },
                "verification": {
                    "report_passed": {"passed": True},
                    "contract_targets_verified": {"satisfied": 3, "total": 3},
                    "key_result_confidences": ["INDEPENDENTLY CONFIRMED"],
                },
                "completeness": {
                    "abstract_written_last": {"passed": True},
                    "required_sections_present": {"satisfied": 4, "total": 4},
                    "placeholders_cleared": {"passed": True},
                    "supplemental_cross_referenced": {"passed": True},
                },
                "results": {
                    "uncertainties_present": {"satisfied": 3, "total": 3},
                    "comparison_with_prior_work_present": {"passed": True},
                    "physical_interpretation_present": {"passed": True},
                },
                "journal_extra_checks": {"convergence_three_points": True},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--raw", "validate", "paper-quality", str(quality_path)], catch_exceptions=False)

    payload = json_output_from_result(result)
    assert payload["ready_for_submission"] is True
    assert payload["journal"] == "prd"


def test_validate_paper_quality_command_fails_on_blockers(gpd_project: Path) -> None:
    quality_path = gpd_project / "paper-quality-blocked.json"
    quality_path.write_text(
        json.dumps(
            {
                "title": "Blocked paper",
                "journal": "jhep",
                "citations": {
                    "citation_keys_resolve": {"satisfied": 1, "total": 2},
                    "missing_placeholders": {"passed": False},
                    "key_prior_work_cited": {"passed": False},
                    "hallucination_free": {"passed": False},
                },
                "verification": {
                    "report_passed": {"passed": False},
                    "contract_targets_verified": {"satisfied": 0, "total": 2},
                    "key_result_confidences": ["UNRELIABLE"],
                },
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "paper-quality", str(quality_path)],
        expect_exit=1,
    )
    assert payload["ready_for_submission"] is False


def test_validate_paper_quality_command_blocks_invalid_ledger_integrity_flags(gpd_project: Path) -> None:
    quality_path = gpd_project / "paper-quality-ledger-blocked.json"
    quality_path.write_text(
        json.dumps(
            {
                "title": "Ledger blocked paper",
                "journal": "generic",
                "verification": {
                    "report_passed": {"passed": True},
                    "contract_targets_verified": {"satisfied": 1, "total": 1},
                    "key_result_confidences": ["INDEPENDENTLY CONFIRMED"],
                },
                "journal_extra_checks": {
                    "contract_results_parse_ok": False,
                    "contract_results_alignment_ok": False,
                    "comparison_verdicts_valid": False,
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--raw", "validate", "paper-quality", str(quality_path)], catch_exceptions=False)

    payload = json_output_from_result(result, expect_exit=1)
    blocker_checks = {issue["check"] for issue in payload["blocking_issues"]}
    assert "contract_results_parse_ok" in blocker_checks
    assert "contract_results_alignment_ok" in blocker_checks
    assert "comparison_verdicts_valid" in blocker_checks


def test_validate_paper_quality_command_blocks_missing_decisive_verdicts(gpd_project: Path) -> None:
    quality_path = gpd_project / "paper-quality-decisive-blocked.json"
    quality_path.write_text(
        json.dumps(
            {
                "title": "Decisive blocker",
                "journal": "generic",
                "verification": {
                    "report_passed": {"passed": True},
                    "contract_targets_verified": {"satisfied": 1, "total": 1},
                    "key_result_confidences": ["INDEPENDENTLY CONFIRMED"],
                },
                "results": {
                    "uncertainties_present": {"satisfied": 1, "total": 1},
                    "comparison_with_prior_work_present": {"passed": True},
                    "physical_interpretation_present": {"passed": True},
                    "decisive_artifacts_with_explicit_verdicts": {"satisfied": 0, "total": 1},
                    "decisive_artifacts_benchmark_anchored": {"satisfied": 1, "total": 1},
                    "decisive_comparison_failures_scoped": {"passed": True},
                },
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "paper-quality", str(quality_path)],
        expect_exit=1,
    )
    blocker_checks = {issue["check"] for issue in payload["blocking_issues"]}
    assert "decisive_artifacts_with_explicit_verdicts" in blocker_checks


def test_validate_paper_quality_command_from_project_artifacts(gpd_project: Path) -> None:
    stage4_dir = Path(__file__).resolve().parent / "fixtures" / "stage4"
    paper_dir = gpd_project / "paper"
    (paper_dir / _CANONICAL_MANUSCRIPT_BASENAME).write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\begin{abstract}Benchmark result with explicit comparison.\\end{abstract}\n"
        "\\section{Introduction}See Fig.~\\ref{fig:benchmark} and \\cite{bench2026}.\n"
        "\\section{Conclusion}Recovered the benchmark within tolerance.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (paper_dir / "ARTIFACT-MANIFEST.json").write_text(
        json.dumps(
            {
                "version": 1,
                "paper_title": "Benchmark Paper",
                "journal": "jhep",
                "created_at": "2026-03-13T00:00:00+00:00",
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    (paper_dir / "PAPER-CONFIG.json").write_text(
        json.dumps(
            {
                "title": "Benchmark Paper",
                "journal": "jhep",
                "output_filename": CANONICAL_MANUSCRIPT_STEM,
                "authors": [{"name": "A. Researcher"}],
                "abstract": "Benchmark abstract.",
                "sections": [{"heading": "Introduction", "content": "Intro."}],
            }
        ),
        encoding="utf-8",
    )
    (paper_dir / "BIBLIOGRAPHY-AUDIT.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-13T00:00:00+00:00",
                "total_sources": 1,
                "resolved_sources": 1,
                "partial_sources": 0,
                "unverified_sources": 0,
                "failed_sources": 0,
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    tracker_dir = gpd_project / "paper"
    tracker_dir.mkdir(parents=True, exist_ok=True)
    (tracker_dir / "FIGURE_TRACKER.md").write_text(
        "---\n"
        "figure_registry:\n"
        "  - id: fig-benchmark\n"
        '    label: "Fig. 1"\n'
        "    kind: figure\n"
        "    role: benchmark\n"
        "    path: paper/figures/benchmark.pdf\n"
        "    contract_ids: [claim-benchmark, deliv-figure]\n"
        "    decisive: true\n"
        "    has_units: true\n"
        "    has_uncertainty: true\n"
        "    referenced_in_text: true\n"
        "    caption_self_contained: true\n"
        "    colorblind_safe: true\n"
        "    comparison_sources:\n"
        "      - GPD/comparisons/benchmark-COMPARISON.md\n"
        "---\n\n"
        "# Figure Tracker\n",
        encoding="utf-8",
    )
    comparison_dir = gpd_project / "GPD" / "comparisons"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    (comparison_dir / "benchmark-COMPARISON.md").write_text(
        "---\n"
        "comparison_kind: benchmark\n"
        "comparison_sources:\n"
        "  - label: theory\n"
        "    kind: summary\n"
        "    path: GPD/phases/01-benchmark/01-SUMMARY.md\n"
        "  - label: benchmark\n"
        "    kind: verification\n"
        "    path: GPD/phases/01-benchmark/01-VERIFICATION.md\n"
        "comparison_verdicts:\n"
        "  - subject_id: claim-benchmark\n"
        "    subject_kind: claim\n"
        "    subject_role: decisive\n"
        "    reference_id: ref-benchmark\n"
        "    comparison_kind: benchmark\n"
        "    metric: relative_error\n"
        '    threshold: "<= 0.01"\n'
        "    verdict: pass\n"
        "    recommended_action: Keep benchmark figure in manuscript\n"
        "---\n\n"
        "# Internal Comparison\n",
        encoding="utf-8",
    )
    phase_dir = gpd_project / "GPD" / "phases" / "01-benchmark"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "01-SUMMARY.md").write_text(
        (stage4_dir / "summary_with_contract_results.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (phase_dir / "01-VERIFICATION.md").write_text(
        (stage4_dir / "verification_with_contract_results.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "paper-quality", "--from-project", str(gpd_project)],
        expect_exit=1,
    )
    assert payload["journal"] == "jhep"
    assert payload["categories"]["verification"]["checks"]["contract_targets_verified"] > 0
    assert payload["categories"]["results"]["checks"]["comparison_with_prior_work_present"] > 0


def test_validate_referee_decision_command_accepts_consistent_major_revision(gpd_project: Path) -> None:
    _write_review_stage_artifacts(gpd_project)
    decision_path = gpd_project / "referee-decision.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "target_journal": "jhep",
                "final_recommendation": "major_revision",
                "final_confidence": "high",
                "stage_artifacts": [
                    "GPD/review/STAGE-reader.json",
                    "GPD/review/STAGE-literature.json",
                    "GPD/review/STAGE-math.json",
                    "GPD/review/STAGE-physics.json",
                    "GPD/review/STAGE-interestingness.json",
                ],
                "central_claims_supported": True,
                "claim_scope_proportionate_to_evidence": False,
                "physical_assumptions_justified": True,
                "proof_audit_coverage_complete": True,
                "theorem_proof_alignment_adequate": True,
                "unsupported_claims_are_central": False,
                "reframing_possible_without_new_results": True,
                "mathematical_correctness": "adequate",
                "novelty": "adequate",
                "significance": "weak",
                "venue_fit": "adequate",
                "literature_positioning": "adequate",
                "unresolved_major_issues": 0,
                "unresolved_minor_issues": 0,
                "blocking_issue_ids": [],
            }
        ),
        encoding="utf-8",
    )
    ledger_path = gpd_project / "review-ledger-consistent.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": [],
            }
        ),
        encoding="utf-8",
    )
    ledger_path = gpd_project / "review-ledger-extra-artifact.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": [],
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "referee-decision", str(decision_path), "--strict", "--ledger", str(ledger_path)],
    )
    assert payload["valid"] is True
    assert payload["most_positive_allowed_recommendation"] == "major_revision"


def test_validate_referee_decision_help_surfaces_strict_policy_semantics() -> None:
    output = _help_text("validate", "referee-decision", catch_exceptions=False)
    assert "Require staged peer-review artifact coverage" in output
    assert "recommendation-floor consistency" in output
    assert "policy-driving inputs" in output
    assert "all journals" in output


def test_validate_referee_decision_strict_requires_matching_ledger(gpd_project: Path) -> None:
    _write_review_stage_artifacts(gpd_project)
    decision_path = gpd_project / "referee-decision-strict-no-ledger.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "target_journal": "jhep",
                "final_recommendation": "major_revision",
                "stage_artifacts": [
                    "GPD/review/STAGE-reader.json",
                    "GPD/review/STAGE-literature.json",
                    "GPD/review/STAGE-math.json",
                    "GPD/review/STAGE-physics.json",
                    "GPD/review/STAGE-interestingness.json",
                ],
            }
        ),
        encoding="utf-8",
    )
    payload = _raw_json(
        ["--raw", "validate", "referee-decision", str(decision_path), "--strict"],
        expect_exit=1,
    )
    assert "Strict referee-decision validation requires --ledger" in payload["error"]


def test_validate_referee_decision_command_accepts_round_suffixed_stage_artifacts(gpd_project: Path) -> None:
    _write_review_stage_artifacts(
        gpd_project,
        artifact_names=(
            "STAGE-reader-R2.json",
            "STAGE-literature-R2.json",
            "STAGE-math-R2.json",
            "STAGE-physics-R2.json",
            "STAGE-interestingness-R2.json",
        ),
        manuscript_path=_manuscript_entrypoint_relpath(root_name="submission"),
    )
    decision_path = gpd_project / "referee-decision-r2.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _manuscript_entrypoint_relpath(root_name="submission"),
                "target_journal": "jhep",
                "final_recommendation": "major_revision",
                "final_confidence": "high",
                "stage_artifacts": [
                    "GPD/review/STAGE-reader-R2.json",
                    "GPD/review/STAGE-literature-R2.json",
                    "GPD/review/STAGE-math-R2.json",
                    "GPD/review/STAGE-physics-R2.json",
                    "GPD/review/STAGE-interestingness-R2.json",
                ],
                "central_claims_supported": True,
                "claim_scope_proportionate_to_evidence": True,
                "physical_assumptions_justified": True,
                "proof_audit_coverage_complete": True,
                "theorem_proof_alignment_adequate": True,
                "unsupported_claims_are_central": False,
                "reframing_possible_without_new_results": True,
                "mathematical_correctness": "adequate",
                "novelty": "adequate",
                "significance": "adequate",
                "venue_fit": "adequate",
                "literature_positioning": "adequate",
                "unresolved_major_issues": 0,
                "unresolved_minor_issues": 0,
                "blocking_issue_ids": [],
            }
        ),
        encoding="utf-8",
    )
    ledger_path = gpd_project / "review-ledger-r2.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 2,
                "manuscript_path": _manuscript_entrypoint_relpath(root_name="submission"),
                "issues": [],
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "referee-decision", str(decision_path), "--strict", "--ledger", str(ledger_path)],
    )
    assert payload["valid"] is True


def test_validate_referee_decision_command_rejects_wrong_existing_artifact_set(gpd_project: Path) -> None:
    _write_review_stage_artifacts(
        gpd_project,
        artifact_names=(
            "CLAIMS.json",
            "REVIEW-LEDGER.json",
            "REFEREE-DECISION.json",
            "STAGE-meta.json",
            "STAGE-summary.json",
        ),
    )
    decision_path = gpd_project / "referee-decision-wrong-artifacts.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "target_journal": "jhep",
                "final_recommendation": "major_revision",
                "stage_artifacts": [
                    "GPD/review/CLAIMS.json",
                    "GPD/review/REVIEW-LEDGER.json",
                    "GPD/review/REFEREE-DECISION.json",
                    "GPD/review/STAGE-meta.json",
                    "GPD/review/STAGE-summary.json",
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger_path = gpd_project / "review-ledger-extra-artifact.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": [],
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "referee-decision", str(decision_path), "--strict", "--ledger", str(ledger_path)],
        expect_exit=1,
    )
    assert payload["valid"] is False
    assert any("canonical five specialist stage artifacts" in reason for reason in payload["reasons"])


def test_validate_referee_decision_command_rejects_extra_noncanonical_stage_artifact(gpd_project: Path) -> None:
    _write_review_stage_artifacts(gpd_project)
    decision_path = gpd_project / "referee-decision-extra-artifact.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "target_journal": "jhep",
                "final_recommendation": "major_revision",
                "stage_artifacts": [
                    "GPD/review/STAGE-reader.json",
                    "GPD/review/STAGE-literature.json",
                    "GPD/review/STAGE-math.json",
                    "GPD/review/STAGE-physics.json",
                    "GPD/review/STAGE-interestingness.json",
                    "GPD/review/STAGE-meta.json",
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger_path = gpd_project / "review-ledger-extra-artifact.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": [],
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "referee-decision", str(decision_path), "--strict", "--ledger", str(ledger_path)],
        expect_exit=1,
    )
    assert payload["valid"] is False
    assert any("rejects noncanonical stage artifacts" in reason for reason in payload["reasons"])
    assert any("STAGE-meta.json" in reason for reason in payload["reasons"])


def test_validate_referee_decision_command_blocks_overly_positive_prl_decision(gpd_project: Path) -> None:
    _write_review_stage_artifacts(gpd_project)
    decision_path = gpd_project / "referee-decision-prl.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "target_journal": "prl",
                "final_recommendation": "minor_revision",
                "stage_artifacts": [
                    "GPD/review/STAGE-reader.json",
                    "GPD/review/STAGE-literature.json",
                    "GPD/review/STAGE-math.json",
                    "GPD/review/STAGE-physics.json",
                    "GPD/review/STAGE-interestingness.json",
                ],
                "novelty": "adequate",
                "significance": "weak",
                "venue_fit": "weak",
            }
        ),
        encoding="utf-8",
    )
    ledger_path = gpd_project / "review-ledger-prl.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": [],
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "referee-decision", str(decision_path), "--strict", "--ledger", str(ledger_path)],
        expect_exit=1,
    )
    assert payload["valid"] is False
    assert payload["most_positive_allowed_recommendation"] == "reject"


def test_validate_referee_decision_command_rejects_missing_stage_artifacts(gpd_project: Path) -> None:
    decision_path = gpd_project / "referee-decision-missing-artifacts.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "target_journal": "jhep",
                "final_recommendation": "major_revision",
                "stage_artifacts": [
                    "GPD/review/STAGE-reader.json",
                    "GPD/review/STAGE-literature.json",
                    "GPD/review/STAGE-math.json",
                    "GPD/review/STAGE-physics.json",
                    "GPD/review/STAGE-interestingness.json",
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger_path = gpd_project / "review-ledger-missing-artifacts.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": [],
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "referee-decision", str(decision_path), "--strict", "--ledger", str(ledger_path)],
        expect_exit=1,
    )
    assert payload["valid"] is False
    assert any("listed staged review artifacts do not exist" in reason for reason in payload["reasons"])


def test_validate_referee_decision_command_rejects_unknown_blocking_issue_ids_when_ledger_given(
    gpd_project: Path,
) -> None:
    _write_review_stage_artifacts(gpd_project)
    decision_path = gpd_project / "referee-decision-ledger-mismatch.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "target_journal": "jhep",
                "final_recommendation": "major_revision",
                "stage_artifacts": [
                    "GPD/review/STAGE-reader.json",
                    "GPD/review/STAGE-literature.json",
                    "GPD/review/STAGE-math.json",
                    "GPD/review/STAGE-physics.json",
                    "GPD/review/STAGE-interestingness.json",
                ],
                "blocking_issue_ids": ["REF-999"],
            }
        ),
        encoding="utf-8",
    )
    ledger_path = gpd_project / "review-ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": [
                    {
                        "issue_id": "REF-001",
                        "opened_by_stage": "physics",
                        "severity": "major",
                        "blocking": True,
                        "summary": "Evidence is incomplete.",
                        "required_action": "Add the missing benchmark comparison.",
                        "status": "open",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        [
            "--raw",
            "validate",
            "referee-decision",
            str(decision_path),
            "--strict",
            "--ledger",
            str(ledger_path),
        ],
        expect_exit=1,
    )
    assert payload["valid"] is False
    assert any("blocking_issue_ids not found in review ledger" in reason for reason in payload["reasons"])


def test_validate_referee_decision_command_rejects_dual_stdin_inputs() -> None:
    payload = _raw_json(
        ["--raw", "validate", "referee-decision", "-", "--ledger", "-"],
        input="{}\n",
        expect_exit=1,
    )
    assert "Cannot read both referee-decision and review-ledger from stdin" in payload["error"]


def test_validate_referee_decision_command_rejects_omitted_unresolved_blocking_ledger_issues(gpd_project: Path) -> None:
    _write_review_stage_artifacts(gpd_project)
    decision_path = gpd_project / "referee-decision-omits-blocker.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "target_journal": "jhep",
                "final_recommendation": "major_revision",
                "stage_artifacts": [
                    "GPD/review/STAGE-reader.json",
                    "GPD/review/STAGE-literature.json",
                    "GPD/review/STAGE-math.json",
                    "GPD/review/STAGE-physics.json",
                    "GPD/review/STAGE-interestingness.json",
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger_path = gpd_project / "review-ledger-open-blocker.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": [
                    {
                        "issue_id": "REF-001",
                        "opened_by_stage": "physics",
                        "severity": "major",
                        "blocking": True,
                        "summary": "Evidence is incomplete.",
                        "required_action": "Add the missing benchmark comparison.",
                        "status": "open",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        [
            "--raw",
            "validate",
            "referee-decision",
            str(decision_path),
            "--strict",
            "--ledger",
            str(ledger_path),
        ],
        expect_exit=1,
    )
    assert payload["valid"] is False
    assert any(
        "unresolved blocking review-ledger issues missing from blocking_issue_ids" in reason
        for reason in payload["reasons"]
    )


def test_validate_paper_quality_command_reports_shape_errors_without_traceback(gpd_project: Path) -> None:
    input_path = gpd_project / "paper-quality-invalid.json"
    input_path.write_text(
        json.dumps(
            {
                "title": "Bad Input",
                "journal": "prd",
                "equations": "broken",
                "figures": {},
                "citations": {},
                "conventions": {},
                "verification": {},
                "completeness": {},
                "results": {},
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "paper-quality", str(input_path)],
        expect_exit=1,
    )
    assert "paper-quality input.equations must be an object, not str" in payload["error"]


def test_validate_paper_quality_command_rejects_unknown_fields_without_traceback(gpd_project: Path) -> None:
    input_path = gpd_project / "paper-quality-unknown-field.json"
    input_path.write_text(
        json.dumps(
            {
                "title": "Bad Input",
                "journal": "prd",
                "equations": {},
                "figures": {},
                "citations": {},
                "conventions": {},
                "verification": {"report_exists": {"passed": True}},
                "completeness": {},
                "results": {},
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "paper-quality", str(input_path)],
        expect_exit=1,
    )
    assert "paper-quality input.verification.report_exists: Extra inputs are not permitted" in payload["error"]
    assert "templates/paper/paper-quality-input-schema.md" in payload["error"]


def test_validate_referee_decision_command_reports_shape_errors_without_traceback(gpd_project: Path) -> None:
    decision_path = gpd_project / "referee-decision-invalid.json"
    decision_path.write_text(
        json.dumps(
            {
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "target_journal": "jhep",
                "final_recommendation": "major_revision",
                "stage_artifacts": "not-a-list",
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "referee-decision", str(decision_path)],
        expect_exit=1,
    )
    assert "referee-decision.stage_artifacts must be an array, not str" in payload["error"]


def test_validate_review_ledger_command_accepts_valid_ledger(gpd_project: Path) -> None:
    ledger_path = gpd_project / "review-ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": [
                    {
                        "issue_id": "REF-001",
                        "opened_by_stage": "physics",
                        "severity": "major",
                        "blocking": True,
                        "claim_ids": ["CLM-001"],
                        "summary": "Evidence is incomplete.",
                        "required_action": "Add the missing benchmark comparison.",
                        "status": "open",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "review-ledger", str(ledger_path)],
    )
    assert payload["issues"][0]["issue_id"] == "REF-001"


def test_validate_review_ledger_command_reports_shape_errors_without_traceback(gpd_project: Path) -> None:
    ledger_path = gpd_project / "review-ledger-invalid.json"
    ledger_path.write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "manuscript_path": _CANONICAL_MANUSCRIPT_REL,
                "issues": "not-a-list",
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "review-ledger", str(ledger_path)],
        expect_exit=1,
    )
    assert "review-ledger.issues must be an array, not str" in payload["error"]


def test_validate_reproducibility_manifest_strict_command(gpd_project: Path) -> None:
    manifest_path = gpd_project / "reproducibility-ready.json"
    manifest_path.write_text(
        json.dumps(
            {
                "paper_title": "Reproducible Paper",
                "date": "2026-03-10",
                "environment": {
                    "python_version": "3.12.1",
                    "package_manager": "uv",
                    "required_packages": [{"package": "numpy", "version": "1.26.4"}],
                    "lock_file": "uv.lock",
                    "system_requirements": {},
                },
                "input_data": [
                    {
                        "name": "benchmark",
                        "source": "NIST",
                        "version_or_date": "2026-03-01",
                        "checksum_sha256": "a" * 64,
                    }
                ],
                "generated_data": [{"name": "spectrum", "script": "scripts/run.py", "checksum_sha256": "b" * 64}],
                "execution_steps": [
                    {"name": "prepare", "command": "python scripts/prepare.py"},
                    {"name": "sample", "command": "python scripts/run.py", "stochastic": True},
                ],
                "expected_results": [
                    {"quantity": "x", "expected_value": "1", "tolerance": "0.1", "script": "scripts/run.py"}
                ],
                "output_files": [{"path": "results/out.json", "checksum_sha256": "c" * 64}],
                "resource_requirements": [
                    {"step": "prepare", "cpu_cores": 1, "memory_gb": 1.0},
                    {"step": "sample", "cpu_cores": 2, "memory_gb": 2.0},
                ],
                "random_seeds": [{"computation": "sample", "seed": "42"}],
                "seeding_strategy": "Fixed seed per stochastic step",
                "verification_steps": ["rerun pipeline", "compare numbers", "inspect artifacts"],
                "minimum_viable": "1 core",
                "recommended": "2 cores",
                "last_verified": "2026-03-10",
                "last_verified_platform": "macOS 14 arm64",
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "reproducibility-manifest", str(manifest_path), "--strict"],
    )
    assert payload["valid"] is True
    assert payload["reproducibility_ready"] is True
    assert "ready_for_review" not in payload


def test_validate_reproducibility_manifest_reports_shape_errors_without_traceback(gpd_project: Path) -> None:
    manifest_path = gpd_project / "reproducibility-invalid.json"
    manifest_path.write_text(
        json.dumps({"paper_title": "Bad Input", "environment": []}),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "reproducibility-manifest", str(manifest_path)],
        expect_exit=1,
    )
    assert payload["valid"] is False
    assert payload["schema_reference"].endswith("paper/reproducibility-manifest.md")
    assert any(issue["field"] == "environment" and "object" in issue["message"].lower() for issue in payload["issues"])


def test_validate_reproducibility_manifest_stdin_strict_fails_when_not_review_ready() -> None:
    manifest = {
        "paper_title": "Needs more metadata",
        "date": "2026-03-10",
        "environment": {
            "python_version": "3.12.1",
            "package_manager": "uv",
            "required_packages": [{"package": "numpy", "version": "1.26.4"}],
            "lock_file": "uv.lock",
            "system_requirements": {},
        },
        "execution_steps": [{"name": "run", "command": "python scripts/run.py"}],
        "expected_results": [{"quantity": "x", "expected_value": "1", "tolerance": "0.1", "script": "scripts/run.py"}],
        "output_files": [{"path": "results/out.json", "checksum_sha256": "a" * 64}],
        "resource_requirements": [],
        "verification_steps": ["rerun"],
        "minimum_viable": "",
        "recommended": "",
        "last_verified": "",
        "last_verified_platform": "",
    }

    payload = _raw_json(
        ["--raw", "validate", "reproducibility-manifest", "-", "--strict"],
        input=json.dumps(manifest),
        expect_exit=1,
    )
    assert payload["valid"] is True
    assert payload["reproducibility_ready"] is False
    assert payload["schema_reference"].endswith("paper/reproducibility-manifest.md")
    assert "ready_for_review" not in payload


def test_validate_reproducibility_manifest_can_emit_kernel_verdict(gpd_project: Path) -> None:
    manifest_path = gpd_project / "reproducibility-kernel.json"
    manifest_path.write_text(
        json.dumps(
            {
                "paper_title": "Kernel Ready",
                "date": "2026-03-10",
                "environment": {
                    "python_version": "3.12.1",
                    "package_manager": "uv",
                    "required_packages": [{"package": "numpy", "version": "1.26.4"}],
                    "lock_file": "uv.lock",
                    "system_requirements": {},
                },
                "execution_steps": [{"name": "run", "command": "python scripts/run.py", "stochastic": True}],
                "expected_results": [
                    {"quantity": "x", "expected_value": "1", "tolerance": "0.1", "script": "scripts/run.py"}
                ],
                "output_files": [{"path": "results/out.json", "checksum_sha256": "a" * 64}],
                "resource_requirements": [{"step": "run", "cpu_cores": 1, "memory_gb": 1.0}],
                "random_seeds": [{"computation": "run", "seed": "42"}],
                "seeding_strategy": "Fixed seed",
                "verification_steps": ["rerun pipeline", "compare outputs", "inspect artifacts"],
                "minimum_viable": "1 core",
                "recommended": "2 cores",
                "last_verified": "2026-03-10",
                "last_verified_platform": "macOS 14 arm64",
            }
        ),
        encoding="utf-8",
    )

    payload = _raw_json(
        ["--raw", "validate", "reproducibility-manifest", str(manifest_path), "--kernel-verdict"],
    )
    assert payload["validation"]["valid"] is True
    assert payload["validation"]["reproducibility_ready"] is True
    assert "ready_for_review" not in payload["validation"]
    assert payload["kernel_verdict"]["overall"] == "PASS"
    assert payload["kernel_verdict"]["verdict_hash"].startswith("sha256:")
