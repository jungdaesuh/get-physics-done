"""Prompt-level coverage for the required GPD acknowledgment."""

from __future__ import annotations

from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REQUIRED_GPD_ACKNOWLEDGMENT = (
    "This research made use of Get Physics Done (GPD), developed by Physical Superintelligence PBC (PSI)."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_FUNDING_CLAIM_FRAGMENT = "supported in part by"


def _read(relative_path: str) -> str:
    if relative_path == "src/gpd/specs/workflows/write-paper.md":
        return workflow_authority_text(REPO_ROOT / "src/gpd/specs/workflows", "write-paper")
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_required_acknowledgment_is_wired_into_paper_prompts() -> None:
    for relative_path in (
        "src/gpd/specs/templates/paper/paper-config-schema.md",
        "src/gpd/specs/workflows/write-paper.md",
        "src/gpd/agents/gpd-paper-writer.md",
    ):
        content = _read(relative_path)
        if relative_path == "src/gpd/specs/workflows/write-paper.md":
            assert "templates/paper/paper-config-schema.md" in content, relative_path
        else:
            assert REQUIRED_GPD_ACKNOWLEDGMENT in content, relative_path
        assert FORBIDDEN_FUNDING_CLAIM_FRAGMENT not in content, relative_path
