"""Shared support for context staged-init tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from gpd.core.frontmatter import compute_knowledge_reviewed_content_sha256
from gpd.core.reproducibility import compute_sha256
from gpd.core.state import default_state_dict
from tests.helpers.cli import artifact_manifest_payload, write_managed_publication_manuscript
from tests.workflow_stage_test_support import assert_staged_payload_matches_manifest

_MISSING = object()

EMPTY_REFERENCE_INTAKE = {
    "must_read_refs": [],
    "must_include_prior_outputs": [],
    "user_asserted_anchors": [],
    "known_good_baselines": [],
    "context_gaps": [],
    "crucial_inputs": [],
}

REFERENCE_HEAVY_FIELDS = (
    "active_reference_context",
    "protocol_bundle_context",
    "reference_artifacts_content",
)


def fail_if_context_builder_runs(name: str):
    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        pytest.fail(f"{name} should not run for this staged init")

    return fail


def record_reference_artifact_payload_calls(calls: list[bool]):
    def record(
        _cwd: Path,
        *,
        include_content: bool = True,
    ) -> dict[str, object]:
        calls.append(include_content)
        return {
            "literature_review_files": [],
            "literature_review_count": 0,
            "research_map_reference_files": ["GPD/research-map/REFERENCES.md"],
            "research_map_reference_count": 1,
            "knowledge_doc_files": [],
            "knowledge_doc_count": 0,
            "stable_knowledge_doc_files": [],
            "stable_knowledge_doc_count": 0,
            "knowledge_doc_status_counts": {},
            "reference_artifact_files": ["GPD/research-map/REFERENCES.md"],
            "reference_artifacts_content": "hydrated reference artifacts" if include_content else None,
        }

    return record


def assert_context_stage(
    payload: Mapping[str, object],
    manifest: object,
    workflow_id: str,
    stage_id: str,
) -> None:
    assert_staged_payload_matches_manifest(
        payload,
        manifest,
        workflow_id=workflow_id,
        stage_id=stage_id,
    )


def assert_no_state_lock_after(project_root: Path, action: Callable[[], object]) -> object:
    result = action()
    assert not (project_root / "GPD" / "state.json.lock").exists()
    return result


def assert_stage_omits_heavy_reference_context(
    payload: Mapping[str, object],
    *,
    extra_fields: tuple[str, ...] = (),
) -> None:
    for field in (*REFERENCE_HEAVY_FIELDS, *extra_fields):
        assert field not in payload


def assert_stage_uses_reference_handles_only(
    payload: Mapping[str, object],
    *,
    reference_files: list[str] | None = None,
) -> None:
    if reference_files is not None:
        assert payload["reference_artifact_files"] == reference_files
    assert_stage_omits_heavy_reference_context(
        payload,
        extra_fields=("active_reference_context", "protocol_bundle_context"),
    )


def assert_empty_reference_intake(payload: Mapping[str, object]) -> None:
    assert payload.get("contract_intake") is None
    assert payload["effective_reference_intake"] == EMPTY_REFERENCE_INTAKE


def assert_publication_subject_roots(
    payload: Mapping[str, object],
    *,
    slug: str | None = None,
    managed_root: str | None = None,
    expected: Mapping[str, object] | None = None,
    optional_expected: Mapping[str, object] | None = None,
) -> str:
    if slug is None:
        assert payload["publication_subject_slug"]
        slug = str(payload["publication_subject_slug"])
    else:
        assert payload["publication_subject_slug"] == slug

    if managed_root is None:
        managed_root = f"GPD/publication/{slug}"
    assert payload["managed_publication_root"] == managed_root

    for key, value in (expected or {}).items():
        assert payload[key] == value
    for key, value in (optional_expected or {}).items():
        if key in payload:
            assert payload[key] == value
    return managed_root


def assert_project_manuscript_publication_roots(
    payload: Mapping[str, object],
    *,
    bootstrap_root: str = "paper",
    artifact_base: object = _MISSING,
    manuscript_root: object = _MISSING,
    manuscript_entrypoint: object = _MISSING,
    artifact_manifest_path: object = _MISSING,
) -> str:
    slug = str(payload["publication_subject_slug"])
    managed_root = f"GPD/publication/{slug}"
    expected: dict[str, object] = {
        "publication_subject_status": "resolved",
        "publication_bootstrap_mode": "resume_existing_manuscript",
        "publication_bootstrap_root": bootstrap_root,
        "publication_lane_kind": "canonical_project_manuscript",
        "publication_lane_owner": "project_managed",
        "selected_publication_root": "GPD",
        "publication_intake_root": f"{managed_root}/intake",
        "managed_manuscript_root": f"{managed_root}/manuscript",
    }
    optional_values = {
        "publication_artifact_base": artifact_base,
        "manuscript_root": manuscript_root,
        "manuscript_entrypoint": manuscript_entrypoint,
        "artifact_manifest_path": artifact_manifest_path,
    }
    expected.update({key: value for key, value in optional_values.items() if value is not _MISSING})
    return assert_publication_subject_roots(payload, managed_root=managed_root, expected=expected)


def assert_managed_publication_roots(
    payload: Mapping[str, object],
    *,
    slug: str,
    status: str = "resolved",
    owner: str = "project_managed",
    staged_payload: bool = False,
    source: object = _MISSING,
    bootstrap_mode: object = _MISSING,
    bootstrap_root: object = _MISSING,
    artifact_base: object = _MISSING,
    manuscript_root: object = _MISSING,
    manuscript_entrypoint: object = _MISSING,
    selected_review_root: object = _MISSING,
) -> str:
    managed_root = f"GPD/publication/{slug}"
    expected: dict[str, object] = {
        "publication_lane_kind": "managed_publication_manuscript",
        "publication_lane_owner": owner,
        "selected_publication_root": managed_root,
    }
    if not staged_payload:
        expected["publication_subject_status"] = status
        expected["managed_manuscript_root"] = f"{managed_root}/manuscript"
        expected["publication_intake_root"] = f"{managed_root}/intake"
    optional_values = {
        "publication_subject_source": source,
        "publication_bootstrap_mode": bootstrap_mode,
        "publication_bootstrap_root": bootstrap_root,
        "publication_artifact_base": artifact_base,
        "manuscript_root": manuscript_root,
        "manuscript_entrypoint": manuscript_entrypoint,
        "selected_review_root": selected_review_root,
    }
    expected.update({key: value for key, value in optional_values.items() if value is not _MISSING})
    return assert_publication_subject_roots(payload, slug=slug, managed_root=managed_root, expected=expected)


def assert_external_artifact_publication_roots(
    payload: Mapping[str, object],
    *,
    managed_manuscript_root: object = _MISSING,
) -> str:
    slug = str(payload["publication_subject_slug"])
    managed_root = f"GPD/publication/{slug}"
    optional_expected = {"managed_manuscript_root": managed_manuscript_root}
    return assert_publication_subject_roots(
        payload,
        managed_root=managed_root,
        expected={
            "publication_lane_kind": "external_artifact",
            "publication_lane_owner": "external_artifact",
            "selected_publication_root": managed_root,
            "selected_review_root": f"{managed_root}/review",
        },
        optional_expected={key: value for key, value in optional_expected.items() if value is not _MISSING},
    )


def write_project_paper_manuscript(
    project_root: Path,
    *,
    paper_dir: str = "paper",
    stem: str = "main",
    body: str = "Draft manuscript.",
    title: str = "Curvature Flow Bounds",
) -> Path:
    manuscript_dir = project_root / paper_dir
    manuscript_dir.mkdir(parents=True, exist_ok=True)
    manuscript = manuscript_dir / f"{stem}.tex"
    manuscript.write_text(
        f"\\documentclass{{article}}\\begin{{document}}{body}\\end{{document}}\n",
        encoding="utf-8",
    )
    (manuscript_dir / "ARTIFACT-MANIFEST.json").write_text(
        json.dumps(
            artifact_manifest_payload(
                manuscript,
                title=title,
                journal="jhep",
                artifact_id="main-tex",
                produced_by="test",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return manuscript


def write_managed_context_manuscript(
    project_root: Path,
    *,
    subject_slug: str,
    stem: str = "main",
    body: str = "Draft manuscript.",
) -> Path:
    return write_managed_publication_manuscript(
        project_root,
        subject_slug=subject_slug,
        stem=stem,
        body=body,
        produced_by="tests.core.test_context",
    )


def write_manuscript_proof_review_artifacts(project_root: Path) -> Path:
    return write_manuscript_proof_review_artifacts_with_proof_path(
        project_root,
        proof_artifact_path="paper/curvature_flow_bounds.tex",
    )


def write_manuscript_proof_review_artifacts_with_proof_path(
    project_root: Path,
    *,
    proof_artifact_path: str,
) -> Path:
    manuscript_path = project_root / "paper" / "curvature_flow_bounds.tex"
    manuscript_path.parent.mkdir(parents=True, exist_ok=True)
    manuscript_path.write_text(
        "\\documentclass{article}\n\\begin{document}\n\\begin{theorem}For every r_0 > 0, the orbit intersects the target annulus.\\end{theorem}\n\\end{document}\n",
        encoding="utf-8",
    )
    (manuscript_path.parent / "PAPER-CONFIG.json").write_text(
        json.dumps(
            {
                "title": "Curvature Flow Bounds",
                "authors": [{"name": "Test Author"}],
                "abstract": "A test manuscript used to exercise proof-review freshness.",
                "sections": [],
                "journal": "jhep",
                "output_filename": "curvature_flow_bounds",
            }
        ),
        encoding="utf-8",
    )
    proof_artifact = project_root / proof_artifact_path
    proof_artifact.parent.mkdir(parents=True, exist_ok=True)
    if proof_artifact != manuscript_path:
        proof_artifact.write_text(
            "\\documentclass{article}\n\\begin{document}\n\\begin{theorem}External theorem proof.\\end{theorem}\n\\end{document}\n",
            encoding="utf-8",
        )
    proof_redteam_artifact_paths = f"  - {proof_artifact_path}\n"
    if proof_artifact_path != "paper/curvature_flow_bounds.tex":
        proof_redteam_artifact_paths += "  - paper/curvature_flow_bounds.tex\n"
    review_dir = project_root / "GPD" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    manuscript_sha256 = compute_sha256(manuscript_path)
    (review_dir / "CLAIMS.json").write_text(
        json.dumps(
            {
                "version": 1,
                "manuscript_path": "paper/curvature_flow_bounds.tex",
                "manuscript_sha256": manuscript_sha256,
                "claims": [
                    {
                        "claim_id": "CLM-001",
                        "claim_type": "main_result",
                        "claim_kind": "theorem",
                        "text": "For every r_0 > 0, the orbit intersects the target annulus.",
                        "artifact_path": proof_artifact_path,
                        "section": "Main Result",
                        "equation_refs": [],
                        "figure_refs": [],
                        "supporting_artifacts": [],
                        "theorem_assumptions": ["chi > 0"],
                        "theorem_parameters": ["r_0"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (review_dir / "STAGE-math.json").write_text(
        json.dumps(
            {
                "version": 1,
                "round": 1,
                "stage_id": "math",
                "stage_kind": "math",
                "manuscript_path": "paper/curvature_flow_bounds.tex",
                "manuscript_sha256": manuscript_sha256,
                "claims_reviewed": ["CLM-001"],
                "summary": "math review",
                "strengths": ["checked proof"],
                "findings": [],
                "proof_audits": [
                    {
                        "claim_id": "CLM-001",
                        "theorem_assumptions_checked": ["chi > 0"],
                        "theorem_parameters_checked": ["r_0"],
                        "proof_locations": [f"{proof_artifact_path}:1"],
                        "uncovered_assumptions": [],
                        "uncovered_parameters": [],
                        "coverage_gaps": [],
                        "alignment_status": "aligned",
                        "notes": "Complete coverage.",
                    }
                ],
                "confidence": "high",
                "recommendation_ceiling": "minor_revision",
            }
        ),
        encoding="utf-8",
    )
    (review_dir / "PROOF-REDTEAM.md").write_text(
        (
            "---\n"
            "status: passed\n"
            "reviewer: gpd-check-proof\n"
            "claim_ids:\n"
            "  - CLM-001\n"
            "proof_artifact_paths:\n"
            f"{proof_redteam_artifact_paths}"
            "manuscript_path: paper/curvature_flow_bounds.tex\n"
            f"manuscript_sha256: {manuscript_sha256}\n"
            "round: 1\n"
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
            f"| `r_0` | target radius | {proof_artifact_path}:1 | covered | Carried through the argument. |\n"
            "### Hypothesis Coverage\n"
            "| Hypothesis | Proof Location | Status | Notes |\n"
            "| --- | --- | --- | --- |\n"
            f"| `H1` | {proof_artifact_path}:1 | covered | Used in the positivity step. |\n"
            "### Quantifier / Domain Coverage\n"
            "| Obligation | Proof Location | Status | Notes |\n"
            "| --- | --- | --- | --- |\n"
            f"| `for every r_0 > 0` | {proof_artifact_path}:1 | covered | No specialization introduced. |\n"
            "### Conclusion-Clause Coverage\n"
            "| Clause | Proof Location | Status | Notes |\n"
            "| --- | --- | --- | --- |\n"
            f"| annulus intersection holds | {proof_artifact_path}:1 | covered | Final sentence states it. |\n"
            "## Adversarial Probe\n"
            "- Probe type: dropped-parameter test\n"
            "- Result: The proof still references r_0, so the theorem remains global in the target radius.\n"
            "## Verdict\n"
            "- Scope status: `matched`\n"
            "- Quantifier status: `matched`\n"
            "- Counterexample status: `none_found`\n"
            "- Blocking gaps:\n"
            "  - None.\n"
            "## Required Follow-Up\n"
            "- None.\n"
        ),
        encoding="utf-8",
    )
    return project_root / "paper" / "references.bib"


def write_bundle_ready_contract_state(project_root: Path) -> None:
    state = default_state_dict()
    state["project_contract"] = {
        "schema_version": 1,
        "scope": {
            "question": "What finite-size scaling collapse and benchmark comparison does the simulation recover?",
            "in_scope": ["Recover the decisive finite-size scaling benchmark for the simulation regime"],
        },
        "claims": [
            {
                "id": "claim-critical",
                "statement": "Recover benchmark finite-size scaling behavior",
                "deliverables": ["deliv-data", "deliv-figure"],
                "acceptance_tests": ["test-benchmark"],
                "references": ["ref-benchmark"],
            }
        ],
        "deliverables": [
            {
                "id": "deliv-data",
                "kind": "dataset",
                "path": "results/measurements.csv",
                "description": "Raw Monte Carlo measurements with metadata",
            },
            {
                "id": "deliv-figure",
                "kind": "figure",
                "path": "figures/collapse.png",
                "description": "Finite-size scaling collapse figure",
            },
        ],
        "acceptance_tests": [
            {
                "id": "test-benchmark",
                "subject": "claim-critical",
                "kind": "benchmark",
                "procedure": "Compare Binder cumulants and finite-size scaling against literature benchmarks",
                "pass_condition": "Benchmark agreement is within uncertainty",
            }
        ],
        "references": [
            {
                "id": "ref-benchmark",
                "kind": "paper",
                "locator": "Benchmark Monte Carlo paper",
                "role": "benchmark",
                "why_it_matters": "Decisive comparison for the simulation regime",
                "applies_to": ["claim-critical"],
                "must_surface": True,
                "required_actions": ["read", "compare", "cite"],
            }
        ],
        "context_intake": {
            "must_read_refs": ["ref-benchmark"],
        },
        "forbidden_proxies": [
            {
                "id": "fp-proxy",
                "subject": "claim-critical",
                "proxy": "Qualitative agreement without scaling analysis",
                "reason": "Would not validate the decisive benchmarked observable",
            }
        ],
        "uncertainty_markers": {
            "weakest_anchors": ["Autocorrelation estimate near the critical point"],
            "disconfirming_observations": ["Finite-size crossings drift away from the benchmark window"],
        },
    }
    (project_root / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")


def write_numerical_relativity_project(project_root: Path) -> None:
    project = project_root / "GPD" / "PROJECT.md"
    project.write_text(
        """# Test Project

## What This Is

BSSN numerical relativity study of a binary black hole merger with moving-puncture evolution.

## Research Context

### Theoretical Framework

General relativity

### Known Results

Apparent horizon tracking, constraint propagation, and gravitational waveform extraction should match trusted benchmarks.
""",
        encoding="utf-8",
    )


def write_numerical_relativity_contract_state(project_root: Path) -> None:
    state = default_state_dict()
    state["project_contract"] = {
        "schema_version": 1,
        "scope": {
            "question": "Does the BSSN evolution reproduce benchmark waveform and remnant behavior?",
            "in_scope": ["Recover the decisive waveform and remnant benchmark for the BSSN evolution"],
        },
        "claims": [
            {
                "id": "claim-waveform",
                "statement": "Recover benchmark waveform phase and remnant properties",
                "deliverables": ["deliv-data", "deliv-figure"],
                "acceptance_tests": ["test-benchmark"],
                "references": ["ref-benchmark"],
            }
        ],
        "deliverables": [
            {
                "id": "deliv-data",
                "kind": "dataset",
                "path": "results/constraints.csv",
                "description": "Constraint histories and remnant diagnostics",
            },
            {
                "id": "deliv-figure",
                "kind": "figure",
                "path": "figures/waveform-comparison.png",
                "description": "Waveform benchmark comparison figure",
            },
        ],
        "acceptance_tests": [
            {
                "id": "test-benchmark",
                "subject": "claim-waveform",
                "kind": "benchmark",
                "procedure": "Compare waveform phase, remnant parameters, and convergence against trusted numerical-relativity results",
                "pass_condition": "Benchmark agreement is within numerical uncertainty",
            }
        ],
        "references": [
            {
                "id": "ref-benchmark",
                "kind": "paper",
                "locator": "https://doi.org/10.1234/numerical-relativity-benchmark",
                "role": "benchmark",
                "why_it_matters": "Provides decisive waveform and remnant anchors",
                "applies_to": ["claim-waveform"],
                "must_surface": True,
                "required_actions": ["read", "compare", "cite"],
            }
        ],
        "context_intake": {
            "must_read_refs": ["ref-benchmark"],
        },
        "forbidden_proxies": [
            {
                "id": "fp-proxy",
                "subject": "claim-waveform",
                "proxy": "Smooth-looking waveforms without converged constraints or benchmark agreement",
                "reason": "Would not validate the decisive strong-field observable",
            }
        ],
        "uncertainty_markers": {
            "weakest_anchors": ["Gauge-parameter sensitivity of the extracted waveform"],
            "disconfirming_observations": ["Constraint growth or waveform phase drift relative to the benchmark"],
        },
    }
    (project_root / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")


def write_knowledge_doc(
    project_root: Path,
    *,
    knowledge_id: str = "K-renormalization-group-fixed-points",
    status: str = "stable",
    body: str = "Trusted knowledge body.\n",
) -> None:
    knowledge_dir = project_root / "GPD" / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    path = knowledge_dir / f"{knowledge_id}.md"
    base_content = (
        "---\n"
        "knowledge_schema_version: 1\n"
        f"knowledge_id: {knowledge_id}\n"
        "title: Renormalization Group Fixed Points\n"
        "topic: renormalization-group\n"
        f"status: {status}\n"
        "created_at: 2026-04-07T12:00:00Z\n"
        "updated_at: 2026-04-07T12:00:00Z\n"
        "sources:\n"
        "  - source_id: source-main\n"
        "    kind: paper\n"
        "    locator: Author et al., 2024\n"
        "    title: Benchmark Reference\n"
        "    why_it_matters: Trusted source for the topic\n"
        "coverage_summary:\n"
        "  covered_topics: [fixed points]\n"
        "  excluded_topics: [implementation]\n"
        "  open_gaps: [none]\n"
        "---\n\n"
        f"{body}"
    )
    reviewed_content_sha256 = compute_knowledge_reviewed_content_sha256(base_content)
    if status == "stable":
        approval_artifact = project_root / "GPD" / "knowledge" / "reviews" / f"{knowledge_id}-R1-REVIEW.md"
        approval_artifact.parent.mkdir(parents=True, exist_ok=True)
        approval_artifact.write_text(f"Approved review for {knowledge_id}.\n", encoding="utf-8")
        approval_artifact_sha256 = hashlib.sha256(approval_artifact.read_bytes()).hexdigest()
        content = base_content.replace(
            "---\n\n",
            "review:\n"
            "  reviewed_at: 2026-04-07T13:00:00Z\n"
            "  review_round: 1\n"
            "  reviewer_kind: workflow\n"
            "  reviewer_id: gpd-review-knowledge\n"
            "  decision: approved\n"
            "  summary: Stable review approved.\n"
            f"  approval_artifact_path: GPD/knowledge/reviews/{knowledge_id}-R1-REVIEW.md\n"
            f"  approval_artifact_sha256: {approval_artifact_sha256}\n"
            f"  reviewed_content_sha256: {reviewed_content_sha256}\n"
            "  stale: false\n"
            "---\n\n",
        )
    elif status == "in_review":
        approval_artifact = project_root / "GPD" / "knowledge" / "reviews" / f"{knowledge_id}-R1-REVIEW.md"
        approval_artifact.parent.mkdir(parents=True, exist_ok=True)
        approval_artifact.write_text(f"Pending review for {knowledge_id}.\n", encoding="utf-8")
        approval_artifact_sha256 = hashlib.sha256(approval_artifact.read_bytes()).hexdigest()
        content = base_content.replace(
            "---\n\n",
            "review:\n"
            "  reviewed_at: 2026-04-07T13:00:00Z\n"
            "  review_round: 1\n"
            "  reviewer_kind: workflow\n"
            "  reviewer_id: gpd-review-knowledge\n"
            "  decision: approved\n"
            "  summary: Needs re-review after edits.\n"
            f"  approval_artifact_path: GPD/knowledge/reviews/{knowledge_id}-R1-REVIEW.md\n"
            f"  approval_artifact_sha256: {approval_artifact_sha256}\n"
            f"  reviewed_content_sha256: {reviewed_content_sha256}\n"
            "  stale: true\n"
            "---\n\n",
        )
    else:
        content = base_content
    path.write_text(content, encoding="utf-8")
