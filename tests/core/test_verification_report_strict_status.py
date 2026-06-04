from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact, semantic_concept

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "gpd" / "specs" / "templates"


def test_verification_report_strict_pass_mentions_required_reference_coverage() -> None:
    verification_report = (TEMPLATES_DIR / "verification-report.md").read_text(encoding="utf-8")

    assert_prompt_contracts(
        verification_report,
        machine_exact(
            "verification report status schema fields",
            (
                "`status: passed` is strict",
                "comparison_verdicts",
                "structured `suggested_contract_checks`",
                "Nested `contract_results` entries still use the canonical contract-result status vocabulary",
            ),
        ),
        *semantic_concept(
            "verification report strict pass status semantics",
            required=(
                "every required decisive comparison is decisive",
                "Proof-backed claims follow the proof-audit rules in the canonical schema",
                "If decisive work remains open, use `gaps_found`, `expert_needed`, or `human_needed`",
                "including `partial` when a specific claim, deliverable, or acceptance test is only partly satisfied",
            ),
        ),
    )
