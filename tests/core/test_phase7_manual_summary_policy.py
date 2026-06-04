"""Provider-free guards for the Phase 7 manual live canary policy."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.persona_summary import (
    assert_persona_summary_valid,
    make_phase7_live_canary_summary,
    phase7_live_canary_policy,
)
from tests.helpers.phase7_live_like import phase7_fixture_rows_by_id

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "dev" / "phase7-live-persona-canary.md"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

VALID_PUBLIC_SUMMARY = make_phase7_live_canary_summary()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _first_row(summary: dict[str, object]) -> dict[str, object]:
    rows = summary["rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    return row


def test_phase7_manual_live_canary_runbook_documents_the_policy_shape() -> None:
    runbook = _read(RUNBOOK_PATH)

    for required_fragment in (
        "Manual live is opt-in",
        "Raw artifacts stay ignored/operator-local",
        "Phase 6 shadow-live rows",
        "sanitized class-only summary",
        "Release and publish jobs must not launch provider CLIs",
        "Nightly is deferred",
        "`workflow_dispatch`",
        "`schedule`",
        "phase7.live-persona-canary-summary.v1",
        "tests.helpers.persona_summary",
    ):
        assert required_fragment in runbook


def test_phase7_manual_public_summary_shape_is_class_only_and_opt_in() -> None:
    assert_persona_summary_valid(VALID_PUBLIC_SUMMARY, phase7_live_canary_policy())


def test_phase7_raw_live_artifacts_remain_operator_local_under_ignored_tmp() -> None:
    gitignore_lines = {line.strip() for line in _read(GITIGNORE_PATH).splitlines()}
    runbook = _read(RUNBOOK_PATH)

    assert "tmp/" in gitignore_lines
    assert VALID_PUBLIC_SUMMARY["raw_artifact_retention_class"] == "operator_local_ignored_tmp"
    assert "repo-local `tmp/`" in runbook
    assert "inside ignored" in runbook
    assert "`tmp/` paths" in runbook


def test_phase7_manual_summary_fixture_marks_shadow_live_observations_class_only() -> None:
    row = _first_row(VALID_PUBLIC_SUMMARY)

    assert row["row_id"] == "LP01-START-PROJECTLESS-READONLY"
    assert row["row_id"] in phase7_fixture_rows_by_id()
    assert row["observation_mode_class"] == "shadow_live_persona"
    assert row["capture_policy_class"] == "classes_and_counts_only"
    assert VALID_PUBLIC_SUMMARY["ci_provider_launch_allowed"] is False
