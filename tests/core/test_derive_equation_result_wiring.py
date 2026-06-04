"""Focused assertions for derive-equation result persistence wiring."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_DOC = REPO_ROOT / "src/gpd/commands/derive-equation.md"
WORKFLOW_DOC = REPO_ROOT / "src/gpd/specs/workflows/derive-equation.md"


def _assert_all_present(text: str, fragments: tuple[str, ...]) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    assert missing == []


def _assert_all_absent(text: str, fragments: tuple[str, ...]) -> None:
    present = [fragment for fragment in fragments if fragment in text]
    assert present == []


def test_derive_equation_command_doc_promises_registry_writeback() -> None:
    text = COMMAND_DOC.read_text(encoding="utf-8")

    _assert_all_present(
        text,
        (
            'gpd --raw validate command-context derive-equation "$ARGUMENTS"',
            "empty standalone launches stay blocked",
            "Keep standalone/current-workspace durable derivation artifacts under `GPD/analysis/` rooted at the invoking workspace.",
            "canonical result lookup via `gpd result search`",
            'direct stored-result inspection via `gpd result show "{result_id}"`',
            "artifact write",
            "authoritative phase context",
            "`gpd result persist-derived`",
            "actual canonical `result_id`",
            "seed continuation",
            "standalone artifacts",
        ),
    )
    _assert_all_absent(
        text,
        (
            "If no argument is given, you will be asked what to derive.",
            "`--carry-forward-last-result`",
        ),
    )


def test_derive_equation_workflow_reuses_prior_results_and_persists_final_equation() -> None:
    text = WORKFLOW_DOC.read_text(encoding="utf-8")

    _assert_all_present(
        text,
        (
            "INIT=$(gpd --raw init progress --include state,config --no-project-reentry)",
            "Treat phase context as authoritative only when the bootstrap surfaces a concrete phase number and phase directory",
            "inspect `intermediate_results` before re-deriving",
            "canonical equation/result entries related to the target",
            "`gpd result search`",
            'gpd result show "{result_id}"',
            'gpd result persist-derived --id "{result_id}" --derivation-slug "{derivation_slug}"',
            "multiple matches",
            "`requested_result_id`",
            "`result_id`",
            "`requested_result_redirected=true`",
            "actual `result_id` forward",
            "authoritative phase context is missing",
            "skip registry write-back",
            "status=skipped",
            "reason=no_recoverable_project_state",
        ),
    )
    _assert_all_absent(
        text,
        (
            "gpd --raw init phase-op --include state,config",
            "`--carry-forward-last-result`",
        ),
    )
