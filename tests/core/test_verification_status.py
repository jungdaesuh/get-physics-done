"""Canonical verification-status reader tests."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.state import (
    default_state_dict,
    generate_state_markdown,
    save_state_json,
    save_state_markdown,
    state_record_verification,
)
from gpd.core.verification_status import read_verification_status


def test_read_verification_status_reads_only_frontmatter(tmp_path: Path) -> None:
    report = tmp_path / "01-VERIFICATION.md"
    report.write_text(
        "# Verification\n\nThe prose says status: passed.\n",
        encoding="utf-8",
    )

    status = read_verification_status(report)

    assert status.is_known is False
    assert status.routing_status == "missing_status"
    assert status.status is None
    assert status.errors == ("missing verification frontmatter status",)


def test_read_verification_status_rejects_unknown_frontmatter_status(tmp_path: Path) -> None:
    report = tmp_path / "01-VERIFICATION.md"
    report.write_text(
        "---\n"
        "status: stale\n"
        "session_status: validating\n"
        "---\n\n"
        "# Verification\n",
        encoding="utf-8",
    )

    status = read_verification_status(report)

    assert status.is_known is False
    assert status.routing_status == "unknown_status"
    assert status.status == "stale"
    assert status.session_status == "validating"


def test_state_record_verification_fails_closed_on_unroutable_frontmatter(tmp_path: Path) -> None:
    state = default_state_dict()
    state["position"]["status"] = "Verifying"
    save_state_json(tmp_path, state)
    save_state_markdown(tmp_path, generate_state_markdown(state))
    phase_dir = tmp_path / "GPD" / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)
    (phase_dir / "02-VERIFICATION.md").write_text(
        "# Verification\n\nAll checks passed in prose.\n",
        encoding="utf-8",
    )

    result = state_record_verification(tmp_path, phase="02")

    assert result.recorded is False
    assert result.reason == "missing verification frontmatter status"
    reloaded = json.loads((tmp_path / "GPD" / "state.json").read_text(encoding="utf-8"))
    assert reloaded["position"]["status"] == "Verifying"
