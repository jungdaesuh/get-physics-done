from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact, semantic_concept

AGENTS_DIR = Path(__file__).resolve().parents[2] / "src" / "gpd" / "agents"
STATUS_AUTHORITY = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "gpd"
    / "specs"
    / "references"
    / "verification"
    / "verification-status-authority.md"
)


def test_verifier_prompt_strict_pass_matches_verification_report_reference_rules() -> None:
    verifier_prompt = (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")
    status_authority = STATUS_AUTHORITY.read_text(encoding="utf-8")

    assert "{GPD_INSTALL_DIR}/references/verification/verification-status-authority.md" in verifier_prompt
    assert_prompt_contracts(
        status_authority,
        machine_exact(
            "verification status authority machine fields",
            (
                "`passed`: every decisive target is `VERIFIED`",
                "required references are completed",
                "every `must_surface` reference has all `required_actions` recorded in `completed_actions`",
                "no unresolved decisive `suggested_contract_checks` remain",
            ),
        ),
        *semantic_concept(
            "verification status authority decisive comparison requirement",
            required=("decisive comparison verdicts are acceptable",),
        ),
    )
    assert "required references handled" not in verifier_prompt
