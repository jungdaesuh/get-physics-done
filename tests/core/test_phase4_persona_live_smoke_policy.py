"""Provider-free guards for the Phase 4 persona live-smoke policy."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.validate_phase4_persona_summary import SCHEMA_VERSION, main, validate_summary
from tests.helpers.persona_summary import (
    make_phase4_live_smoke_summary,
    phase4_live_smoke_policy,
    validate_persona_summary,
)
from tests.helpers.phase4_persona.matrix import load_phase4_rows

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "dev" / "phase4-persona-live-smoke.md"
VALID_PUBLIC_SUMMARY = make_phase4_live_smoke_summary()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contains_text(value: str, fragment: str) -> bool:
    return fragment in value


def test_phase4_live_smoke_runbook_documents_manual_only_sanitized_policy() -> None:
    runbook = _read(RUNBOOK_PATH)

    for required_fragment in (
        "Manual live is opt-in",
        "launch provider CLIs",
        "provider secret environment names",
        "Raw live artifacts stay ignored and operator-local",
        "sanitized class-only summary",
        "scripts/validate_phase4_persona_summary.py",
        "phase4.persona-live-smoke-summary.v1",
    ):
        assert required_fragment in runbook


def test_phase4_public_summary_validator_accepts_sanitized_class_only_summary() -> None:
    result = validate_summary(VALID_PUBLIC_SUMMARY)
    helper_result = validate_persona_summary(VALID_PUBLIC_SUMMARY, phase4_live_smoke_policy())

    assert SCHEMA_VERSION == phase4_live_smoke_policy().schema_version
    assert result.valid is True
    assert result.findings == ()
    assert helper_result.valid is True
    assert helper_result.findings == ()


def test_phase4_public_summary_uses_stable_canonical_row_ids() -> None:
    rows = VALID_PUBLIC_SUMMARY["rows"]
    assert isinstance(rows, list)
    row_ids = {row["row_id"] for row in rows if isinstance(row, dict)}
    canonical_user_steering_ids = {row.row_id for row in load_phase4_rows("user_steering")}

    assert row_ids == {"P4-USER-01", "P4-USER-02"}
    assert row_ids <= canonical_user_steering_ids


def test_phase4_public_summary_validator_cli_accepts_and_rejects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    valid_path = tmp_path / "valid-summary.json"
    valid_path.write_text(json.dumps(VALID_PUBLIC_SUMMARY), encoding="utf-8")

    assert main([str(valid_path)]) == 0
    assert _contains_text(capsys.readouterr().out, "phase4 persona summary valid")

    invalid = deepcopy(VALID_PUBLIC_SUMMARY)
    invalid["rows"][0]["provider_reply"] = "redacted"
    invalid_path = tmp_path / "invalid-summary.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")

    assert main([str(invalid_path)]) == 1
    captured = capsys.readouterr()
    assert _contains_text(captured.err, "not sanitized/class-only")
    assert _contains_text(captured.err, "forbidden_key:rows.0.provider_reply")
