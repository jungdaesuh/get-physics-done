"""Focused assertions for the validate-conventions command/workflow seam."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_concept

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_validate_conventions_scope_argument_is_real_or_fail_closed() -> None:
    command = _read(COMMANDS_DIR / "validate-conventions.md")
    workflow = _read(WORKFLOWS_DIR / "validate-conventions.md")

    assert_prompt_contracts(
        command,
        *semantic_concept(
            "validate-conventions scope argument policy",
            required=(
                "The optional scope argument is real",
                "Any other input is rejected by command-context validation instead of being guessed",
            ),
        ),
    )
    assert 'PHASE_ARG="${ARGUMENTS:-}"' in workflow
    assert 'if [ -n "${PHASE_ARG}" ]; then' in workflow
    assert 'gpd --raw init phase-op --include state,roadmap,config "${PHASE_ARG}"' in workflow


def test_validate_conventions_routes_on_typed_status_and_expected_artifact_gate() -> None:
    workflow = _read(WORKFLOWS_DIR / "validate-conventions.md")

    assert "gpd_return.status: completed" in workflow
    assert "gpd_return.status: checkpoint" in workflow
    assert "gpd_return.status: blocked" in workflow
    assert "gpd_return.status: failed" in workflow
    assert "gpd_return.files_written" in workflow
    assert_prompt_contracts(
        workflow,
        *semantic_concept(
            "validate-conventions expected artifact gate",
            required=("expected artifact exists on disk",),
        ),
    )
    assert "GPD/phases/${PHASE_DIR}/CONSISTENCY-CHECK.md" in workflow
    assert "GPD/CONSISTENCY-CHECK.md" in workflow


def test_validate_conventions_stays_thin_and_avoids_legacy_checker_routing() -> None:
    workflow = _read(WORKFLOWS_DIR / "validate-conventions.md")

    assert "Thin wrapper around `gpd-consistency-checker`" in workflow
    assert_prompt_contracts(
        workflow,
        *semantic_concept(
            "validate-conventions keeps checker authority thin",
            required=("The checker owns the convention logic",),
        ),
    )
    assert "gpd-notation-coordinator" in workflow
    assert "consistency_status" not in workflow
    assert "CONSISTENT" not in workflow
    assert "INCONSISTENT" not in workflow
