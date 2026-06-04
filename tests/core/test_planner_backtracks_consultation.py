"""Spec-text contract test for planner BACKTRACKS.md consultation."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
REFERENCES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "references"


def test_planner_reads_backtracks_when_present() -> None:
    planner_path = AGENTS_DIR / "gpd-planner.md"
    procedure_path = REFERENCES_DIR / "planning" / "planner-execution-procedure.md"
    assert planner_path.exists(), f"planner agent spec missing at {planner_path}"
    assert procedure_path.exists(), f"planner procedure reference missing at {procedure_path}"

    text = planner_path.read_text(encoding="utf-8")
    procedure = procedure_path.read_text(encoding="utf-8")

    assert "planner-execution-procedure.md" in text, "gpd-planner.md must point to the execution procedure module"
    assert "GPD/BACKTRACKS.md" in procedure, "planner procedure must reference GPD/BACKTRACKS.md in context triage"

    # The reference should keep BACKTRACKS.md near filtering and cap guidance
    # so agents do not inject the whole accumulated-history file.
    backtracks_anchor = procedure.index("GPD/BACKTRACKS.md")
    backtracks_window = procedure[backtracks_anchor : backtracks_anchor + 220]
    assert "same planning stage" in backtracks_window
    assert "last 10 matching rows" in backtracks_window
    assert "cap the rendered block" in backtracks_window

    assert "patterns_consulted" in procedure, "planner procedure must reference 'patterns_consulted'"

    # The `backtracks` key should live near the patterns_consulted anchor so
    # the frontmatter record extension is real rather than a stray mention.
    anchor = procedure.index("patterns_consulted")
    window = procedure[anchor : anchor + 600]
    assert "backtracks" in window, (
        "gpd-planner.md must list 'backtracks' inside the patterns_consulted frontmatter block"
    )
