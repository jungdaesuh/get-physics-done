"""Assertions for verification scaffold and workflow surface alignment."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, get_args, get_origin

from gpd.contracts import ComparisonVerdict
from gpd.core.frontmatter import extract_frontmatter
from gpd.core.strict_yaml import load_strict_yaml
from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, semantic_concept
from tests.markdown_test_support import extract_marker_range, markdown_fence_bodies
from tests.workflow_authority_support import workflow_authority_text

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "gpd" / "specs" / "templates"
WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "src" / "gpd" / "specs" / "workflows"


def _read(relative_path: str) -> str:
    if relative_path == "src/gpd/specs/workflows/verify-work.md":
        return workflow_authority_text(WORKFLOWS_DIR, "verify-work")
    return (Path(__file__).resolve().parents[2] / relative_path).read_text(encoding="utf-8")


def _literal_values(annotation: object) -> tuple[str, ...]:
    origin = get_origin(annotation)
    if origin is Literal:
        return tuple(arg for arg in get_args(annotation) if isinstance(arg, str))
    values: list[str] = []
    for arg in get_args(annotation):
        values.extend(_literal_values(arg))
    return tuple(values)


def _assert_semantic_contract(
    text: str,
    label: str,
    *,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> None:
    assert_prompt_contracts(
        text,
        *semantic_concept(
            label,
            required=required or None,
            forbidden=forbidden or None,
            match=MatchMode.CASEFOLD_NORMALIZED,
            context=label,
        ),
    )


def _research_verification_example_frontmatter(template_text: str) -> dict[str, object]:
    examples = markdown_fence_bodies(template_text, info="markdown")
    assert len(examples) == 1
    frontmatter, _body = extract_frontmatter(examples[0])
    return dict(frontmatter)


def test_verification_scaffolds_surface_closed_comparison_kind_enum_without_blank_placeholder() -> None:
    research_verification = _read("src/gpd/specs/templates/research-verification.md")
    verify_workflow = _read("src/gpd/specs/workflows/verify-work.md")

    comparison_kinds = _literal_values(ComparisonVerdict.model_fields["comparison_kind"].annotation)
    expected_enum = f"`comparison_kind`: {'|'.join(comparison_kinds)}"
    omit_instruction = "omit both `comparison_kind` and `comparison_reference_id` instead of leaving blank placeholders"
    paired_id_instruction = "omit both keys instead of leaving one blank"

    _assert_semantic_contract(
        research_verification,
        "research verification body enum guidance",
        required=("Allowed body enum values", "comparison_kind", *comparison_kinds),
    )
    assert expected_enum in research_verification
    assert expected_enum not in verify_workflow
    assert research_verification.count(omit_instruction) == 1
    assert research_verification.count(paired_id_instruction) == 1
    _assert_semantic_contract(
        verify_workflow,
        "verify-work owns only session overlay",
        required=("session overlay", "verifier-produced evidence", "exactly once per check"),
    )


def test_verification_report_strict_pass_guidance_includes_reference_coverage_rules() -> None:
    verification_report = _read("src/gpd/specs/templates/verification-report.md")

    _assert_semantic_contract(
        verification_report,
        "strict passed verification guidance",
        required=(
            "status: passed",
            "strict",
            "structured `suggested_contract_checks`",
            "non-canonical frontmatter aliases",
            "proof-backed claims",
            "proof-audit",
            "canonical schema",
        ),
    )


def test_verification_guidance_surfaces_the_same_canonical_suggestion_contract() -> None:
    research_verification = _read("src/gpd/specs/templates/research-verification.md")
    verify_workflow = _read("src/gpd/specs/workflows/verify-work.md")

    expected_suggestion = "suggested_contract_checks"

    assert expected_suggestion in research_verification
    assert expected_suggestion not in verify_workflow
    _assert_semantic_contract(
        verify_workflow,
        "canonical report content is verifier-owned",
        required=("canonical verifier report content", "owned", "gpd-verifier"),
    )


def test_verify_work_current_check_overlay_stays_separate_from_verifier_scaffold() -> None:
    verify_workflow = _read("src/gpd/specs/workflows/verify-work.md")

    _assert_semantic_contract(
        verify_workflow,
        "current-check overlay stays separate from canonical scaffold",
        required=(
            "verifier-supplied current check",
            "verification file",
            "report state",
            "verifier-produced evidence",
            "exactly once per check",
            "session overlay",
            "canonical verifier verdict",
            "verifier-owned",
            "one-shot delegation",
        ),
    )
    assert 'summary: "verification not started yet"' not in verify_workflow


def test_verify_work_gap_repair_uses_explicit_stage_route_and_stays_fail_closed() -> None:
    verify_workflow = _read("src/gpd/specs/workflows/verify-work.md")

    assert 'gpd --raw init verify-work "${PHASE_ARG}" --stage gap_repair' in verify_workflow
    _assert_semantic_contract(
        verify_workflow,
        "gap repair stays fail closed",
        required=("preexisting PLAN files", "success"),
        forbidden=("skipping gap closure",),
    )
    assert "skipping gap closure" not in verify_workflow


def test_model_visible_worked_examples_keep_summary_and_verdict_shapes_copy_safe() -> None:
    executor_example = _read("src/gpd/specs/references/execution/executor-worked-example.md")
    verification_report = _read("src/gpd/specs/templates/verification-report.md")
    verifier_prompt = _read("src/gpd/agents/gpd-verifier.md")

    assert "depth: full" in executor_example
    assert "completed: 2026-03-15" in executor_example
    assert "evidence:" in executor_example
    assert "verifier: gpd-verifier" in executor_example
    _assert_semantic_contract(
        executor_example,
        "worked example comparison verdict is copy safe",
        required=(
            "recommended_action",
            "benchmark coefficient comparison",
            "verification report",
            "notes",
            "pole agreement",
            "decisive benchmark requirement",
        ),
    )
    assert "comparison_verdicts" in verification_report
    assert "comparison_verdicts" in verifier_prompt
    assert "subject_role: decisive" in verifier_prompt


def test_research_verification_template_keeps_source_as_yaml_list() -> None:
    research_verification = _read("src/gpd/specs/templates/research-verification.md")
    frontmatter = _research_verification_example_frontmatter(research_verification)
    multi_source_yaml = extract_marker_range(
        research_verification,
        "Multi-source `source` frontmatter stays a YAML list:",
        "<guidelines>",
        context="research verification multi-source example",
    )
    multi_source_example = load_strict_yaml(multi_source_yaml)

    assert frontmatter["source"] == ["[SUMMARY.md file validated]"]
    assert multi_source_example == {"source": ["03-01-SUMMARY.md", "03-02-SUMMARY.md", "03-03-SUMMARY.md"]}
    _assert_semantic_contract(
        research_verification,
        "source field remains YAML list",
        required=("source", "YAML list", "one SUMMARY path"),
    )
    assert "source: 03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md" not in research_verification


def test_research_verification_template_keeps_contract_results_and_scalar_examples_copy_safe() -> None:
    research_verification = _read("src/gpd/specs/templates/research-verification.md")

    assert "evidence:\n        - verifier: gpd-verifier" in research_verification
    assert "Non-canonical frontmatter aliases are forbidden in model-facing output" in research_verification
    for legacy_alias in ("must_haves", "verification_inputs", "contract_evidence", "independently_confirmed"):
        assert legacy_alias not in research_verification


def test_summary_template_keeps_reference_action_ledger_and_legacy_alias_note() -> None:
    summary_template = _read("src/gpd/specs/templates/summary.md")

    assert "single detailed rule source" in summary_template
    assert "plan_contract_ref" in summary_template
    assert "contract_results" in summary_template
    assert "comparison_verdicts" in summary_template
    assert "suggested_contract_checks" in summary_template
    assert "Non-canonical frontmatter aliases are forbidden in model-facing output" in summary_template
    for legacy_alias in ("must_haves", "verification_inputs", "contract_evidence", "independently_confirmed"):
        assert legacy_alias not in summary_template
