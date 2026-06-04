from __future__ import annotations

import pytest

from gpd.contracts import ResearchContract, parse_contract_results_data_artifact
from gpd.core.contract_skeletons import build_contract_results_skeleton


def _contract_with_full_result_surface() -> ResearchContract:
    return ResearchContract.model_validate(
        {
            "schema_version": 1,
            "scope": {
                "question": "Does the phase prove and benchmark the advertised result?",
                "in_scope": ["proof-bearing claim", "benchmark output"],
            },
            "context_intake": {
                "must_read_refs": ["ref-proof-source", "ref-benchmark"],
                "crucial_inputs": ["artifacts/result.json", "proofs/main-proof.md"],
            },
            "claims": [
                {
                    "id": "claim-proof",
                    "statement": "For every admissible n, the phase proof establishes the stated bound.",
                    "claim_kind": "theorem",
                    "deliverables": ["deliv-proof"],
                    "acceptance_tests": ["test-proof-audit"],
                    "references": ["ref-proof-source"],
                    "parameters": [{"symbol": "n", "domain_or_type": "positive integer"}],
                    "hypotheses": [{"id": "hyp-admissible", "text": "n is admissible.", "symbols": ["n"]}],
                    "quantifiers": ["for all admissible n"],
                    "conclusion_clauses": [{"id": "conclusion-bound", "text": "The claimed bound holds."}],
                    "proof_deliverables": ["deliv-proof"],
                },
                {
                    "id": "claim-benchmark",
                    "statement": "The generated result matches the benchmark table.",
                    "claim_kind": "result",
                    "deliverables": ["deliv-data"],
                    "acceptance_tests": ["test-benchmark"],
                    "references": ["ref-benchmark", "ref-background"],
                },
            ],
            "deliverables": [
                {
                    "id": "deliv-proof",
                    "kind": "derivation",
                    "path": "proofs/main-proof.md",
                    "description": "Machine-readable proof artifact.",
                },
                {
                    "id": "deliv-data",
                    "kind": "data",
                    "path": "artifacts/result.json",
                    "description": "Generated benchmark result.",
                },
            ],
            "acceptance_tests": [
                {
                    "id": "test-proof-audit",
                    "subject": "claim-proof",
                    "kind": "claim_to_proof_alignment",
                    "procedure": "Run the proof-redteam audit and check theorem metadata.",
                    "pass_condition": "The proof-redteam audit is complete and aligned with the claim.",
                    "evidence_required": ["deliv-proof", "ref-proof-source"],
                },
                {
                    "id": "test-benchmark",
                    "subject": "claim-benchmark",
                    "kind": "benchmark",
                    "procedure": "Compare artifacts/result.json to the benchmark table.",
                    "pass_condition": "The generated value matches the benchmark tolerance.",
                    "evidence_required": ["deliv-data", "ref-benchmark"],
                },
            ],
            "references": [
                {
                    "id": "ref-proof-source",
                    "kind": "paper",
                    "locator": "proof-source.pdf",
                    "role": "must_consider",
                    "why_it_matters": "The theorem statement and hypotheses are anchored here.",
                    "applies_to": ["claim-proof"],
                    "must_surface": True,
                    "required_actions": ["read", "cite"],
                },
                {
                    "id": "ref-benchmark",
                    "kind": "prior_artifact",
                    "locator": "benchmarks/reference-table.json",
                    "role": "benchmark",
                    "why_it_matters": "This is the decisive benchmark table.",
                    "applies_to": ["claim-benchmark"],
                    "must_surface": True,
                    "required_actions": ["read", "compare"],
                },
                {
                    "id": "ref-background",
                    "kind": "paper",
                    "locator": "background-note.pdf",
                    "role": "background",
                    "why_it_matters": "This contextualizes the method but is not a decisive check.",
                    "applies_to": ["claim-benchmark"],
                    "must_surface": False,
                    "required_actions": [],
                },
            ],
            "forbidden_proxies": [
                {
                    "id": "fp-prose-only",
                    "subject": "claim-benchmark",
                    "proxy": "Treating a prose assertion as a benchmark comparison.",
                    "reason": "The benchmark must be checked against the reference table.",
                },
                {
                    "id": "fp-unaudited-proof",
                    "subject": "claim-proof",
                    "proxy": "Treating a proof artifact as accepted without proof-redteam metadata.",
                    "reason": "The theorem-bearing claim needs an explicit proof audit.",
                },
            ],
            "uncertainty_markers": {
                "weakest_anchors": ["Benchmark tolerance has not been checked."],
                "unvalidated_assumptions": ["The proof hypotheses match the source theorem."],
                "competing_explanations": ["A stale artifact could match the prose but not the benchmark."],
                "disconfirming_observations": ["The proof-redteam audit finds a missing hypothesis."],
            },
        }
    )


@pytest.mark.parametrize("target", ["summary", "verification"])
def test_contract_results_skeleton_covers_contract_surface_and_defaults_to_nonpassing(target: str) -> None:
    contract = _contract_with_full_result_surface()

    skeleton = build_contract_results_skeleton(contract, target=target)

    assert "status" not in skeleton
    assert "summary" not in skeleton
    parsed = parse_contract_results_data_artifact(skeleton)
    assert set(parsed.claims) == {"claim-proof", "claim-benchmark"}
    assert set(parsed.deliverables) == {"deliv-proof", "deliv-data"}
    assert set(parsed.acceptance_tests) == {"test-proof-audit", "test-benchmark"}
    assert set(parsed.references) == {"ref-proof-source", "ref-benchmark", "ref-background"}
    assert set(parsed.forbidden_proxies) == {"fp-prose-only", "fp-unaudited-proof"}
    assert parsed.uncertainty_markers == contract.uncertainty_markers

    assert {entry.status for entry in parsed.claims.values()} == {"blocked"}
    assert {entry.status for entry in parsed.deliverables.values()} == {"not_attempted"}
    assert {entry.status for entry in parsed.acceptance_tests.values()} == {"blocked"}
    assert parsed.references["ref-proof-source"].status == "missing"
    assert parsed.references["ref-benchmark"].status == "missing"
    assert parsed.references["ref-background"].status == "not_applicable"
    assert {proxy.status for proxy in parsed.forbidden_proxies.values()} == {"unresolved"}

    proof_claim = parsed.claims["claim-proof"]
    assert proof_claim.status == "blocked"
    assert proof_claim.proof_audit is None
    assert proof_claim.evidence == []
    assert proof_claim.linked_ids == ["deliv-proof", "test-proof-audit", "ref-proof-source"]

    benchmark_claim = parsed.claims["claim-benchmark"]
    assert benchmark_claim.linked_ids == ["deliv-data", "test-benchmark", "ref-benchmark", "ref-background"]
    assert parsed.deliverables["deliv-proof"].path == "proofs/main-proof.md"
    assert parsed.acceptance_tests["test-benchmark"].linked_ids == ["claim-benchmark", "deliv-data", "ref-benchmark"]
    assert parsed.references["ref-proof-source"].missing_actions == ["read", "cite"]
    assert parsed.references["ref-benchmark"].missing_actions == ["read", "compare"]
    assert parsed.references["ref-background"].completed_actions == []
    assert parsed.references["ref-background"].missing_actions == []


def test_contract_results_skeleton_keeps_verification_gap_wording_stable() -> None:
    contract = _contract_with_full_result_surface()

    skeleton = build_contract_results_skeleton(contract, target="verification")

    assert (
        skeleton["claims"]["claim-proof"]["summary"]
        == "Verification gap skeleton: this claim needs independent evidence before it can pass."
    )
    assert (
        skeleton["forbidden_proxies"]["fp-unaudited-proof"]["notes"]
        == "Verification gap skeleton: this forbidden proxy has not yet been independently rejected."
    )
    assert (
        skeleton["references"]["ref-background"]["summary"]
        == "Verification gap skeleton: no required verification action is recorded for this reference."
    )


def test_contract_results_skeleton_rejects_unknown_target() -> None:
    with pytest.raises(ValueError, match="target must be one of"):
        build_contract_results_skeleton(_contract_with_full_result_surface(), target="publication")
