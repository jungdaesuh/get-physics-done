"""Focused assertions for plan-checker and bibliographer prompt cleanup."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import FragmentMode, assert_prompt_contracts, machine_exact

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_CHECKER = REPO_ROOT / "src/gpd/agents/gpd-plan-checker.md"
BIBLIOGRAPHER = REPO_ROOT / "src/gpd/agents/gpd-bibliographer.md"
CHECKER_RETURN_PROTOCOL = REPO_ROOT / "src/gpd/specs/references/verification/plan-checker/checker-return-protocol.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _gpd_return_block(source: str) -> str:
    return source.split("gpd_return:\n", 1)[1].split("```", 1)[0]


def test_plan_checker_prompt_uses_typed_status_and_concise_presentation_language() -> None:
    source = _read(PLAN_CHECKER)
    return_protocol = _read(CHECKER_RETURN_PROTOCOL)
    envelope = _gpd_return_block(source)

    assert_prompt_contracts(
        source,
        machine_exact(
            "plan checker concise typed status routing",
            (
                "Apply `{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md` for one-shot handoff semantics.",
                "If user input is needed, return the typed checkpoint and stop.",
                "Shared protocols live at `{GPD_INSTALL_DIR}/references/shared/shared-protocols.md`",
                "For UI label handling, follow `checker-return-protocol.md`",
                "the machine decision comes from `gpd_return.status`, approved/blocked plan lists, and `issues`.",
            ),
        ),
    )
    assert "artifact_write_authority: read_only" in source
    assert "file_write" not in source
    assert "\n{GPD_INSTALL_DIR}/references/shared/shared-protocols.md\n" not in source
    assert_prompt_contracts(
        return_protocol,
        machine_exact(
            "plan checker protocol headings route on typed status",
            "Headings above are presentation only. Route on `gpd_return.status`, the approved/blocked plan lists, and `issues`.",
        ),
    )
    assert_prompt_contracts(
        source,
        machine_exact(
            "plan checker stale prose route absent",
            "Headings above are presentation only; route on gpd_return.status.",
            mode=FragmentMode.ABSENT,
        ),
    )
    assert "  status: completed" in envelope
    assert "  files_written: []" in envelope
    assert "  issues: []" in envelope
    assert '  next_actions:\n    - "gpd:execute-phase 04"' in envelope
    assert 'approved_plans:\n    - "04-01"\n    - "04-02"' in envelope
    assert "blocked_plans: []" in envelope


def test_bibliographer_prompt_uses_typed_checkpoint_language_and_shorter_heading_note() -> None:
    source = _read(BIBLIOGRAPHER)
    envelope = _gpd_return_block(source)

    assert (
        "Use agent-infrastructure.md for checkpoint ownership, return-envelope base fields, and one-shot handoff semantics."
        in source
    )
    assert "Route on `gpd_return.status`, not presentation headings." in source
    assert "Use `gpd_return.status: checkpoint` as the control surface." not in source
    assert (
        "The markdown headings in this section, including `## BIBLIOGRAPHY UPDATED`, `## CITATION ISSUES FOUND`, and `## CHECKPOINT REACHED`, are presentation only."
        not in source
    )
    assert "  status: completed" in envelope
    assert "  files_written:\n    - paper/references.bib\n    - GPD/references-status.json" in envelope
    assert "  issues: []" in envelope
    assert "  next_actions: []" in envelope
    assert "entries_added: 3" in envelope
    assert "{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md" in source
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md" not in source
