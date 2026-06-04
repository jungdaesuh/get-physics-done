from __future__ import annotations

import re
from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def _workflow(name: str) -> str:
    if name in {"write-paper.md", "literature-review.md"}:
        return workflow_authority_text(WORKFLOWS_DIR, name)
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def test_write_paper_bibliographer_step_routes_on_typed_return_contract() -> None:
    workflow = _workflow("write-paper.md")

    assert "Return BIBLIOGRAPHY UPDATED or CITATION ISSUES FOUND." not in workflow
    assert "Return a typed `gpd_return` envelope for the `write_paper_bibliographer` child_gate." in workflow
    assert "Do not mark bibliography verification complete" in workflow
    assert "strict review" in workflow
    assert "reproducibility-manifest generation" in workflow
    assert "Bibliography: `{ACTIVE_BIBLIOGRAPHY_PATH}`" in workflow
    assert (
        "Always list `${PAPER_DIR}/CITATION-AUDIT.md` and `GPD/references-status.json` in `gpd_return.files_written`"
        in workflow
    )
    assert re.search(
        r"If the bibliographer completed with issues recorded[\s\S]{0,80}`GPD/references-status.json`", workflow
    )
    assert re.search(r"If the\s+bibliographer completed cleanly with no remaining citation issues", workflow)


def test_literature_review_bibliographer_step_routes_on_typed_return_contract() -> None:
    workflow = _workflow("literature-review.md")

    assert "Return BIBLIOGRAPHY UPDATED or CITATION ISSUES FOUND." not in workflow
    assert "Return through the typed handoff." in workflow
    assert "completed must name it in files_written" in workflow
    assert "Use checkpoint only when researcher input is required to continue." in workflow
    assert "**If the bibliographer completed with issues recorded in the audit report:**" in workflow
    assert "apply the citation-audit artifact" in workflow
    assert "before continuing" in workflow
    assert "**If BIBLIOGRAPHY UPDATED:**" not in workflow


def test_explain_bibliographer_step_routes_on_typed_return_contract() -> None:
    workflow = _workflow("explain.md")

    assert "Return `BIBLIOGRAPHY UPDATED` if all references are verified or corrected." not in workflow
    assert "Return `CITATION ISSUES FOUND` if any references remain uncertain or invalid." not in workflow
    assert "Return a typed `gpd_return` envelope." in workflow
    assert "Use `status: completed` when the audit finished" in workflow
    assert "If the bibliographer completed with issues recorded in the audit report:" in workflow
