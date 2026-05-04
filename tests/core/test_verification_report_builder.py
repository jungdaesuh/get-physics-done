from __future__ import annotations

import copy
from pathlib import Path

import pytest

from gpd.contracts import (
    ResearchContract,
    SuggestedContractCheck,
    parse_comparison_verdicts_data_strict,
    parse_contract_results_data_artifact,
)
from gpd.core.frontmatter import extract_frontmatter, reconstruct_frontmatter, validate_frontmatter
from gpd.core.strict_yaml import load_strict_yaml
from gpd.core.verification_report import (
    build_verification_gap_report_frontmatter,
    build_verification_report_skeleton,
    compose_verification_report_markdown,
    render_verification_report_markdown,
)


def _compact_stale_refresh_contract() -> ResearchContract:
    return ResearchContract.model_validate(
        {
            "schema_version": 1,
            "scope": {
                "question": "Does the refreshed artifact still pass the decisive benchmark?",
                "in_scope": ["stale verification refresh"],
            },
            "context_intake": {
                "must_read_refs": ["ref-stale-verification-benchmark"],
                "crucial_inputs": ["artifacts/phase4/result.json"],
            },
            "claims": [
                {
                    "id": "claim-stale-verification",
                    "statement": "The refreshed phase result matches the benchmark artifact.",
                    "claim_kind": "result",
                    "deliverables": ["deliv-stale-data"],
                    "acceptance_tests": ["test-stale-verification-decisive"],
                    "references": ["ref-stale-verification-benchmark"],
                }
            ],
            "deliverables": [
                {
                    "id": "deliv-stale-data",
                    "kind": "data",
                    "path": "artifacts/phase4/result.json",
                    "description": "Current refreshed phase result data.",
                }
            ],
            "acceptance_tests": [
                {
                    "id": "test-stale-verification-decisive",
                    "subject": "claim-stale-verification",
                    "kind": "benchmark",
                    "procedure": "Compare the refreshed result against the benchmark artifact.",
                    "pass_condition": "The refreshed value matches the benchmark tolerance.",
                    "evidence_required": ["deliv-stale-data", "ref-stale-verification-benchmark"],
                }
            ],
            "references": [
                {
                    "id": "ref-stale-verification-benchmark",
                    "kind": "prior_artifact",
                    "locator": "artifacts/benchmark/reference.json",
                    "role": "benchmark",
                    "why_it_matters": "This is the decisive benchmark for the stale-refresh row.",
                    "applies_to": ["claim-stale-verification"],
                    "must_surface": True,
                    "required_actions": ["read", "compare"],
                }
            ],
            "forbidden_proxies": [
                {
                    "id": "fp-stale-verification-prose-only",
                    "subject": "claim-stale-verification",
                    "proxy": "Accepting a prose-only freshness claim without the benchmark comparison.",
                    "reason": "The stale-refresh row needs decisive artifact evidence.",
                }
            ],
            "uncertainty_markers": {
                "weakest_anchors": ["Benchmark artifact availability."],
                "unvalidated_assumptions": ["The current artifact hash alone is not a benchmark pass."],
                "competing_explanations": ["The stale report can look plausible while using obsolete data."],
                "disconfirming_observations": ["The benchmark artifact is missing."],
            },
        }
    )


def _write_stale_refresh_plan(tmp_path, contract: ResearchContract) -> Path:
    (tmp_path / "artifacts" / "benchmark").mkdir(parents=True)
    (tmp_path / "artifacts" / "benchmark" / "reference.json").write_text('{"benchmark": true}\n', encoding="utf-8")
    (tmp_path / "artifacts" / "phase4").mkdir(parents=True)
    (tmp_path / "artifacts" / "phase4" / "result.json").write_text('{"result": "current"}\n', encoding="utf-8")
    phase_dir = tmp_path / "GPD" / "phases" / "01-baseline"
    phase_dir.mkdir(parents=True)
    plan_path = phase_dir / "01-PLAN.md"
    plan_path.write_text(
        reconstruct_frontmatter(
            {
                "phase": "01-baseline",
                "plan": "01",
                "type": "execute",
                "wave": 1,
                "depends_on": ["GPD/phases/00-baseline/00-SUMMARY.md"],
                "files_modified": ["artifacts/phase4/result.json"],
                "interactive": False,
                "conventions": {"units": "natural", "metric": "(+,-,-,-)", "coordinates": "Cartesian"},
                "contract": contract.model_dump(mode="json", exclude_none=True),
            },
            "# Plan\n\nRefresh stale verification evidence.\n",
        ),
        encoding="utf-8",
    )
    return plan_path


def _yaml_block(frontmatter_yaml: str) -> str:
    assert frontmatter_yaml.startswith("---\n")
    assert frontmatter_yaml.endswith("---\n")
    return frontmatter_yaml.removeprefix("---\n").removesuffix("---\n")


def _stale_refresh_oracle_body() -> str:
    return (
        "# Verification\n\n"
        "## Computational Verification Details\n\n"
        "### Computational Oracle: stale-refresh artifact freshness\n\n"
        "```python\n"
        "from pathlib import Path\n"
        "import hashlib\n\n"
        'artifact = Path("artifacts/phase4/result.json")\n'
        'benchmark = Path("artifacts/benchmark/reference.json")\n'
        'print("artifact_exists", artifact.exists())\n'
        'print("artifact_sha256", hashlib.sha256(artifact.read_bytes()).hexdigest())\n'
        'print("benchmark_exists", benchmark.exists())\n'
        "```\n\n"
        "**Output:**\n\n"
        "```output\n"
        "artifact_exists True\n"
        "artifact_sha256 535a1589ab8300e57539ddf784fbaaedba95dd159ca2012e8a1dcb77feebe04f\n"
        "benchmark_exists True\n"
        "```\n\n"
        "**Verdict:** INCONCLUSIVE. The files are present, but this skeleton has not completed the comparison.\n\n"
        "## Gaps\n\n"
        "- `claim-stale-verification` remains blocked.\n"
    )


def _stale_refresh_prose_only_body() -> str:
    return (
        "# Verification\n\n"
        "## Evidence\n\n"
        "The current result hash differs from the stale report, and the decisive benchmark is missing.\n\n"
        "## Verdict\n\n"
        "FAIL: the old passed report cannot be reused, so this should remain gaps_found.\n"
    )


def _assert_no_empty_copy_bait(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            assert not (key in {"evidence", "linked_ids"} and child == [])
            _assert_no_empty_copy_bait(child)
    elif isinstance(value, list):
        for item in value:
            _assert_no_empty_copy_bait(item)


def test_build_verification_gap_report_frontmatter_returns_typed_schema_valid_skeleton() -> None:
    contract = _compact_stale_refresh_contract()

    frontmatter = build_verification_gap_report_frontmatter(
        contract,
        phase="01-baseline",
        verified="2026-05-04T00:00:00Z",
        plan_contract_ref="GPD/phases/01-baseline/01-PLAN.md#/contract",
        verification_report_path="GPD/phases/01-baseline/01-VERIFICATION.md",
    )

    assert frontmatter["status"] == "gaps_found"
    assert not {
        "gpd_return",
        "runtime",
        "computational_oracle",
    }.intersection(frontmatter)

    raw_results = frontmatter["contract_results"]
    assert isinstance(raw_results, dict)
    assert "status" not in raw_results
    assert "summary" not in raw_results

    parsed_results = parse_contract_results_data_artifact(raw_results)
    assert set(parsed_results.claims) == {"claim-stale-verification"}
    assert set(parsed_results.deliverables) == {"deliv-stale-data"}
    assert set(parsed_results.acceptance_tests) == {"test-stale-verification-decisive"}
    assert set(parsed_results.references) == {"ref-stale-verification-benchmark"}
    assert set(parsed_results.forbidden_proxies) == {"fp-stale-verification-prose-only"}
    assert parsed_results.claims["claim-stale-verification"].status == "blocked"
    assert parsed_results.acceptance_tests["test-stale-verification-decisive"].status == "blocked"

    reference_usage = parsed_results.references["ref-stale-verification-benchmark"]
    assert reference_usage.status == "missing"
    assert reference_usage.completed_actions == []
    assert reference_usage.missing_actions == ["read", "compare"]

    verdict_payloads = frontmatter["comparison_verdicts"]
    assert isinstance(verdict_payloads, list)
    assert all("evidence" not in verdict for verdict in verdict_payloads)
    verdicts = parse_comparison_verdicts_data_strict(verdict_payloads)
    assert verdicts
    assert {verdict.verdict for verdict in verdicts} == {"inconclusive"}
    assert any(
        verdict.subject_id == "test-stale-verification-decisive"
        and verdict.reference_id == "ref-stale-verification-benchmark"
        for verdict in verdicts
    )

    check_payloads = frontmatter["suggested_contract_checks"]
    assert isinstance(check_payloads, list)
    checks = [SuggestedContractCheck.model_validate(check) for check in check_payloads]
    assert {(check.suggested_subject_kind, check.suggested_subject_id) for check in checks} == {
        ("acceptance_test", "test-stale-verification-decisive"),
        ("reference", "ref-stale-verification-benchmark"),
    }


def test_build_verification_report_skeleton_renders_copy_safe_yaml_and_markdown(tmp_path: Path) -> None:
    contract = _compact_stale_refresh_contract()
    plan_path = _write_stale_refresh_plan(tmp_path, contract)
    report_path = plan_path.with_name("01-VERIFICATION.md")

    skeleton = build_verification_report_skeleton(
        contract=contract,
        plan_path=plan_path,
        plan_contract_ref="GPD/phases/01-baseline/01-PLAN.md#/contract",
    )

    assert skeleton.target_report_path == str(report_path)
    assert skeleton.target_report_ref == "GPD/phases/01-baseline/01-VERIFICATION.md"
    assert skeleton.target_status == "gaps_found"
    assert skeleton.validation_commands == [
        "gpd frontmatter validate GPD/phases/01-baseline/01-VERIFICATION.md --schema verification",
        "gpd validate verification-contract GPD/phases/01-baseline/01-VERIFICATION.md",
    ]
    assert any("frontmatter_yaml" in rule for rule in skeleton.authoring_rules)

    assert skeleton.frontmatter_yaml.startswith("---\n")
    assert "status: gaps_found" in skeleton.frontmatter_yaml
    assert "frontmatter:" not in skeleton.frontmatter_yaml
    assert "target_status:" not in skeleton.frontmatter_yaml
    assert "target_report_path:" not in skeleton.frontmatter_yaml
    assert "evidence: []" not in skeleton.frontmatter_yaml
    assert "linked_ids: []" not in skeleton.frontmatter_yaml

    yaml_meta = load_strict_yaml(_yaml_block(skeleton.frontmatter_yaml))
    assert isinstance(yaml_meta, dict)
    markdown_meta, markdown_body = extract_frontmatter(skeleton.markdown_draft)
    assert markdown_meta == yaml_meta
    assert "# Verification Draft" in markdown_body
    assert "gpd validate verification-contract GPD/phases/01-baseline/01-VERIFICATION.md" in markdown_body

    _assert_no_empty_copy_bait(yaml_meta)
    assert yaml_meta["contract_results"]["claims"]["claim-stale-verification"]["linked_ids"] == [
        "deliv-stale-data",
        "test-stale-verification-decisive",
        "ref-stale-verification-benchmark",
    ]
    assert "linked_ids" not in yaml_meta["contract_results"]["deliverables"]["deliv-stale-data"]

    raw_claim = skeleton.frontmatter["contract_results"]["claims"]["claim-stale-verification"]
    assert raw_claim["evidence"] == []
    assert raw_claim["linked_ids"] == [
        "deliv-stale-data",
        "test-stale-verification-decisive",
        "ref-stale-verification-benchmark",
    ]

    rendered_validation = validate_frontmatter(skeleton.markdown_draft, "verification", source_path=report_path)
    assert rendered_validation.valid, rendered_validation.errors

    raw_markdown = reconstruct_frontmatter(skeleton.frontmatter, skeleton.body_stub)
    raw_validation = validate_frontmatter(raw_markdown, "verification", source_path=report_path)
    assert raw_validation.valid, raw_validation.errors


def test_build_verification_report_skeleton_renders_colon_rich_values_as_parseable_yaml(tmp_path: Path) -> None:
    contract = _compact_stale_refresh_contract()
    plan_path = _write_stale_refresh_plan(tmp_path, contract)
    report_path = plan_path.with_name("01-VERIFICATION.md")
    colon_rich_score = (
        "Freshness check failed: stale pass is unsupported; "
        "artifacts/benchmark/reference.json: missing decisive benchmark"
    )

    skeleton = build_verification_report_skeleton(
        contract=contract,
        plan_path=plan_path,
        plan_contract_ref="GPD/phases/01-baseline/01-PLAN.md#/contract",
        verified="2026-05-04T03:21:16Z",
        score=colon_rich_score,
    )

    yaml_meta = load_strict_yaml(_yaml_block(skeleton.frontmatter_yaml))
    markdown_meta, _ = extract_frontmatter(skeleton.markdown_draft)
    assert yaml_meta["verified"] == "2026-05-04T03:21:16Z"
    assert yaml_meta["score"] == colon_rich_score
    assert markdown_meta["score"] == colon_rich_score
    assert "score: Freshness check failed: stale pass" not in skeleton.frontmatter_yaml
    assert "evidence: []" not in skeleton.frontmatter_yaml
    assert "linked_ids: []" not in skeleton.frontmatter_yaml

    rendered_validation = validate_frontmatter(skeleton.markdown_draft, "verification", source_path=report_path)
    assert rendered_validation.valid, rendered_validation.errors


def test_verification_report_markdown_draft_surfaces_authoring_rules_and_warnings(tmp_path: Path) -> None:
    contract = _compact_stale_refresh_contract()
    plan_path = _write_stale_refresh_plan(tmp_path, contract)

    skeleton = build_verification_report_skeleton(
        contract=contract,
        plan_path=plan_path,
        plan_contract_ref="GPD/phases/01-baseline/01-PLAN.md#/contract",
    )

    payload = skeleton.model_dump(mode="json")
    warnings = payload.get("warnings")
    assert isinstance(warnings, list) and warnings
    assert payload["body_contract"] == skeleton.body_contract
    assert payload["body_template"] == skeleton.body_template
    assert skeleton.body_contract in skeleton.body_stub
    assert skeleton.body_template in skeleton.body_stub
    assert skeleton.body_contract in skeleton.markdown_draft
    assert "```python" in skeleton.body_stub
    assert "**Output:**" in skeleton.body_stub
    assert "```output" in skeleton.body_stub
    assert "**Verdict:** PASS/FAIL/INCONCLUSIVE" in skeleton.body_stub
    assert "not executed - replace" in skeleton.body_template
    assert skeleton.authoring_rules
    for rule in skeleton.authoring_rules:
        assert rule in skeleton.markdown_draft
    for warning in warnings:
        assert warning in skeleton.markdown_draft
    assert "gpd_return" in skeleton.markdown_draft
    assert "Markdown body" in skeleton.markdown_draft or "body" in skeleton.markdown_draft


def test_gap_report_composition_accepts_oracle_evidence_body(tmp_path: Path) -> None:
    contract = _compact_stale_refresh_contract()
    plan_path = _write_stale_refresh_plan(tmp_path, contract)
    report_path = plan_path.with_name("01-VERIFICATION.md")
    target_report_ref = "GPD/phases/01-baseline/01-VERIFICATION.md"
    frontmatter = build_verification_gap_report_frontmatter(
        contract,
        phase="01-baseline",
        plan_contract_ref="GPD/phases/01-baseline/01-PLAN.md#/contract",
        verification_report_path=target_report_ref,
    )

    composition = compose_verification_report_markdown(
        frontmatter,
        _stale_refresh_oracle_body(),
        target_report_ref=target_report_ref,
        source_path=report_path,
        validation_mode="contract",
    )

    assert composition.validation.valid, composition.validation.errors
    assert composition.validation.oracle_evidence_count == 1
    meta, body = extract_frontmatter(composition.markdown)
    assert "Computational Verification Details" in body
    assert "**Output:**" in body
    assert "**Verdict:** INCONCLUSIVE" in body
    assert "Computational Verification Details" not in meta
    assert "artifact_sha256" not in meta


def test_gap_report_composition_rejects_prose_only_body(tmp_path: Path) -> None:
    contract = _compact_stale_refresh_contract()
    plan_path = _write_stale_refresh_plan(tmp_path, contract)
    report_path = plan_path.with_name("01-VERIFICATION.md")
    target_report_ref = "GPD/phases/01-baseline/01-VERIFICATION.md"
    frontmatter = build_verification_gap_report_frontmatter(
        contract,
        phase="01-baseline",
        plan_contract_ref="GPD/phases/01-baseline/01-PLAN.md#/contract",
        verification_report_path=target_report_ref,
    )

    composition = compose_verification_report_markdown(
        frontmatter,
        _stale_refresh_prose_only_body(),
        target_report_ref=target_report_ref,
        source_path=report_path,
        validation_mode="contract",
    )

    assert not composition.validation.valid
    assert composition.validation.oracle_evidence_count == 0
    assert composition.validation.missing == []
    assert any("computational_oracle" in error for error in composition.validation.errors)
    meta, body = extract_frontmatter(composition.markdown)
    assert "old passed report cannot be reused" in body
    assert "old passed report cannot be reused" not in meta


def test_render_verification_report_markdown_keeps_colon_rich_body_out_of_yaml(tmp_path: Path) -> None:
    contract = _compact_stale_refresh_contract()
    plan_path = _write_stale_refresh_plan(tmp_path, contract)
    report_path = plan_path.with_name("01-VERIFICATION.md")
    skeleton = build_verification_report_skeleton(
        contract=contract,
        plan_path=plan_path,
        plan_contract_ref="GPD/phases/01-baseline/01-PLAN.md#/contract",
    )
    colon_rich_body = (
        "# Verification Draft\n\n"
        "## Evidence\n\n"
        "The stale pass is not supported: current hash differs from the old report.\n\n"
        "```yaml\n"
        "gpd_return:\n"
        "  status: completed\n"
        "```\n"
    )

    rendered = render_verification_report_markdown(skeleton.frontmatter_yaml, colon_rich_body)

    meta, body = extract_frontmatter(rendered)
    assert "gpd_return" not in meta
    assert "The stale pass is not supported: current hash differs" in body
    assert "gpd_return:\n  status: completed" in body
    assert "gpd_return:" not in skeleton.frontmatter_yaml
    validation = validate_frontmatter(rendered, "verification", source_path=report_path)
    assert validation.valid, validation.errors


def test_build_verification_report_skeleton_rejects_passed_status() -> None:
    with pytest.raises(ValueError, match="cannot certify passed reports"):
        build_verification_report_skeleton(contract=_compact_stale_refresh_contract(), status="passed")


def test_build_verification_gap_report_frontmatter_rejects_stale_refresh_invalid_schema_shape() -> None:
    frontmatter = build_verification_gap_report_frontmatter(_compact_stale_refresh_contract())
    stale_refresh_results = copy.deepcopy(frontmatter["contract_results"])
    assert isinstance(stale_refresh_results, dict)
    stale_refresh_results["status"] = "gaps_found"
    stale_refresh_results["summary"] = "Parent ledger summary should not be accepted."
    stale_refresh_results["claims"]["claim-stale-verification"]["status"] = "gaps_found"
    stale_refresh_results["claims"]["claim-stale-verification"]["evidence"] = [
        "fresh hash differs from the stale report"
    ]

    with pytest.raises(ValueError) as results_error:
        parse_contract_results_data_artifact(stale_refresh_results)

    assert "status" in str(results_error.value)
    assert "claims.claim-stale-verification.evidence.0" in str(results_error.value)

    stale_refresh_verdicts = copy.deepcopy(frontmatter["comparison_verdicts"])
    assert isinstance(stale_refresh_verdicts, list)
    stale_refresh_verdicts[0]["evidence"] = ["string evidence belongs in notes or contract_results evidence objects"]

    with pytest.raises(ValueError, match=r"\[0\] evidence: Extra inputs are not permitted"):
        parse_comparison_verdicts_data_strict(stale_refresh_verdicts)


def test_rendered_verification_report_rejects_stale_refresh_manual_skeleton_misuse(tmp_path: Path) -> None:
    contract = _compact_stale_refresh_contract()
    plan_path = _write_stale_refresh_plan(tmp_path, contract)
    report_path = plan_path.with_name("01-VERIFICATION.md")
    skeleton = build_verification_report_skeleton(
        contract=contract,
        plan_path=plan_path,
        plan_contract_ref="GPD/phases/01-baseline/01-PLAN.md#/contract",
    )
    meta, body = extract_frontmatter(skeleton.markdown_draft)
    mutated = copy.deepcopy(meta)

    mutated["contract_results"]["claims"]["claim-stale-verification"]["evidence"] = [
        "fresh hash differs from the stale report",
        "benchmark reference is missing",
    ]
    mutated["contract_results"]["forbidden_proxies"]["fp-stale-verification-prose-only"]["status"] = "passed"
    mutated["comparison_verdicts"][0]["comparison_kind"] = "reproducibility"

    validation = validate_frontmatter(reconstruct_frontmatter(mutated, body), "verification", source_path=report_path)
    assert not validation.valid
    joined_errors = "\n".join(validation.errors)
    assert "claims.claim-stale-verification.evidence.0 must be an object, not str" in joined_errors
    assert "forbidden_proxies.fp-stale-verification-prose-only.status" in joined_errors
    assert "comparison_kind" in joined_errors
    assert "reproducibility" in joined_errors
