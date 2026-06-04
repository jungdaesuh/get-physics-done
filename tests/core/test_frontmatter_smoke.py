"""Focused smoke coverage for plan frontmatter validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from gpd.core.correctness_validators import validate_verification_oracle_evidence
from gpd.core.frontmatter import extract_frontmatter, validate_frontmatter, verify_plan_structure


def _plan_markdown(*, extra_frontmatter: str = "") -> str:
    lines = [
        "---",
        "phase: 01-test",
        "plan: 01",
        "type: execute",
        "wave: 1",
        "depends_on: []",
        "files_modified: []",
        "interactive: false",
    ]
    if extra_frontmatter.strip():
        lines.extend(line.rstrip() for line in extra_frontmatter.strip().splitlines())
    lines.extend(
        [
            "conventions:",
            "  units: natural",
            "  metric: (+,-,-,-)",
            "  coordinates: Cartesian",
            "contract:",
            "  schema_version: 1",
            "  scope:",
            "    question: What benchmark must this plan recover?",
            "    in_scope: [benchmark recovery]",
            "  context_intake:",
            "    must_read_refs: [ref-main]",
            "    must_include_prior_outputs: [GPD/phases/00-baseline/00-01-SUMMARY.md]",
            "  claims:",
            "    - id: claim-main",
            "      statement: Recover the benchmark value within tolerance",
            "      deliverables: [deliv-main]",
            "      acceptance_tests: [test-main]",
            "      references: [ref-main]",
            "  deliverables:",
            "    - id: deliv-main",
            "      kind: figure",
            "      path: figures/main.png",
            "      description: Main benchmark figure",
            "  references:",
            "    - id: ref-main",
            "      kind: paper",
            "      locator: Author et al., Journal, 2024",
            "      role: benchmark",
            "      why_it_matters: Published comparison target",
            "      applies_to: [claim-main]",
            "      must_surface: true",
            "      required_actions: [read, compare, cite]",
            "  acceptance_tests:",
            "    - id: test-main",
            "      subject: claim-main",
            "      kind: benchmark",
            "      procedure: Compare against the benchmark reference",
            "      pass_condition: Matches reference within tolerance",
            "      evidence_required: [deliv-main, ref-main]",
            "  forbidden_proxies:",
            "    - id: fp-main",
            "      subject: claim-main",
            "      proxy: Qualitative trend match without numerical comparison",
            "      reason: Would allow false progress without the decisive benchmark",
            "  uncertainty_markers:",
            "    weakest_anchors: [Reference tolerance interpretation]",
            "    disconfirming_observations: [Benchmark agreement disappears after normalization fix]",
            "---",
            "",
            "Body",
            "",
        ]
    )
    return "\n".join(lines)


def _gaps_found_verification_markdown() -> str:
    return "\n".join(
        [
            "---",
            "phase: 01-test",
            "verified: 2026-05-03T12:00:00Z",
            "status: gaps_found",
            "score: 2/3 contract targets verified",
            "plan_contract_ref: GPD/phases/01-test/01-01-PLAN.md#/contract",
            "contract_results:",
            "  claims:",
            "    claim-main:",
            "      status: failed",
            "      summary: Benchmark miss remains above tolerance.",
            "      linked_ids: [deliv-main, test-main, ref-main]",
            "  deliverables:",
            "    deliv-main:",
            "      status: passed",
            "      path: figures/main.png",
            "      summary: Benchmark figure exists with the comparison overlay.",
            "      linked_ids: [claim-main, test-main]",
            "  acceptance_tests:",
            "    test-main:",
            "      status: failed",
            "      summary: Benchmark comparison exceeds the contracted tolerance.",
            "      linked_ids: [claim-main, deliv-main, ref-main]",
            "  references:",
            "    ref-main:",
            "      status: completed",
            "      completed_actions: [read, compare, cite]",
            "      missing_actions: []",
            "      summary: Published benchmark anchor was read and compared.",
            "  forbidden_proxies:",
            "    fp-main:",
            "      status: rejected",
            "      notes: Qualitative trend matching was not accepted as sufficient evidence.",
            "  uncertainty_markers:",
            "    weakest_anchors: [Reference tolerance interpretation]",
            "    disconfirming_observations: [Benchmark agreement disappears after normalization fix]",
            "comparison_verdicts:",
            "  - subject_id: claim-main",
            "    subject_kind: claim",
            "    subject_role: decisive",
            "    reference_id: ref-main",
            "    comparison_kind: benchmark",
            "    metric: relative_error",
            '    threshold: "<= 0.01"',
            "    verdict: fail",
            "    recommended_action: Re-run after the normalization fix.",
            "suggested_contract_checks:",
            "  - check: re-run-benchmark-after-normalization",
            "    reason: The decisive benchmark comparison currently fails tolerance.",
            "    suggested_subject_kind: acceptance_test",
            "    suggested_subject_id: test-main",
            "    evidence_path: GPD/phases/01-test/01-VERIFICATION.md",
            "---",
            "",
            "# Verification",
            "",
            "```python",
            "print({'relative_error': 0.04, 'threshold': 0.01})",
            "```",
            "",
            "**Output:**",
            "```output",
            "{'relative_error': 0.04, 'threshold': 0.01}",
            "```",
            "",
            "FAIL: relative error exceeds the benchmark tolerance.",
            "",
        ]
    )


def test_verify_plan_structure_accepts_minimal_valid_plan_frontmatter(tmp_path: Path) -> None:
    plan_path = tmp_path / "01-01-PLAN.md"
    plan_path.write_text(_plan_markdown(), encoding="utf-8")

    result = verify_plan_structure(tmp_path, plan_path)

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == ["No <task> elements found"]


def test_validate_frontmatter_verification_accepts_minimal_gaps_found_fixture(tmp_path: Path) -> None:
    phase_dir = tmp_path / "GPD" / "phases" / "01-test"
    phase_dir.mkdir(parents=True)
    (phase_dir / "01-01-PLAN.md").write_text(_plan_markdown(), encoding="utf-8")
    verification_path = phase_dir / "01-VERIFICATION.md"
    content = _gaps_found_verification_markdown()
    verification_path.write_text(content, encoding="utf-8")

    meta, _body = extract_frontmatter(content)
    schema_result = validate_frontmatter(content, "verification", source_path=verification_path)
    oracle_result = validate_verification_oracle_evidence(content, source_path=verification_path)

    assert meta["status"] == "gaps_found"
    assert schema_result.valid is True
    assert schema_result.missing == []
    assert schema_result.errors == []
    assert oracle_result.valid is True
    assert oracle_result.evidence_count == 1


@pytest.mark.parametrize(
    ("field_name", "expected_missing"),
    [
        ("wave", "wave"),
        ("conventions", "conventions"),
    ],
)
def test_validate_frontmatter_plan_reports_missing_required_fields(
    field_name: str,
    expected_missing: str,
) -> None:
    content = (
        _plan_markdown().replace("wave: 1\n", "", 1)
        if field_name == "wave"
        else _plan_markdown().replace(
            "conventions:\n  units: natural\n  metric: (+,-,-,-)\n  coordinates: Cartesian\n",
            "",
            1,
        )
    )

    result = validate_frontmatter(content, "plan")

    assert result.valid is False
    assert expected_missing in result.missing


def test_validate_frontmatter_plan_rejects_contract_anchors_without_contract_block() -> None:
    content = (
        "---\n"
        "phase: 01\n"
        "plan_id: 01-01\n"
        "title: Execute the deterministic fixture baseline\n"
        "status: planned_ready\n"
        "command_authority: $gpd-plan-phase 01\n"
        "execution_authority: $gpd-execute-phase 01\n"
        "---\n"
        "\n"
        "## Contract Anchors\n"
        "\n"
        "- Observable: `obs-benchmark`\n"
        "- Claim under test: `claim-benchmark`\n"
    )

    meta, _body = extract_frontmatter(content)
    result = validate_frontmatter(content, "plan")

    assert meta["plan_id"] == "01-01"
    assert "plan" not in meta
    assert result.valid is False
    assert {
        "plan",
        "type",
        "wave",
        "depends_on",
        "files_modified",
        "interactive",
        "conventions",
        "contract",
    }.issubset(set(result.missing))
    assert "plan" not in result.present


def test_validate_frontmatter_plan_rejects_invalid_tool_requirements_shape() -> None:
    content = _plan_markdown(extra_frontmatter="tool_requirements: oops")

    result = validate_frontmatter(content, "plan")

    assert result.valid is False
    assert "tool_requirements: Input should be a valid list" in result.errors
