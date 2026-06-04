"""Focused assertions for transition and milestone closeout authority cuts."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_all_present(text: str, fragments: tuple[str, ...]) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    assert missing == []


def _assert_all_absent(text: str, fragments: tuple[str, ...]) -> None:
    present = [fragment for fragment in fragments if fragment in text]
    assert present == []


def test_transition_delegates_closeout_to_readiness_and_phase_complete() -> None:
    workflow = _read(WORKFLOWS_DIR / "transition.md")

    readiness = 'gpd --raw phase closeout-readiness "${phase_number}" --require-verification'
    transition = 'gpd phase complete "${phase_number}"'
    _assert_all_present(workflow, (readiness, transition))
    assert workflow.index(readiness) < workflow.index(transition)
    _assert_all_present(
        workflow,
        (
            "The helper owns the ROADMAP/STATE transition",
            "gpd state update-progress",
            "gpd state update",
            "gpd state patch",
        ),
    )


def test_transition_drops_legacy_state_parsing_and_manual_continuation_cleanup() -> None:
    workflow = _read(WORKFLOWS_DIR / "transition.md")

    legacy_fragments = (
        "CURRENT_PHASE=$(grep",
        "PHASE_DIR=$(ls -d",
        "ls ${PHASE_DIR}/.continue-here",
        "If found, delete them",
        "Update Session Continuity section",
    )
    _assert_all_absent(workflow, legacy_fragments)

    _assert_all_present(
        workflow,
        (
            "Skipping incomplete plans is destructive",
            "1. Continue current phase",
            "2. Stop and discuss a scope change",
        ),
    )


def test_complete_milestone_delegates_archive_and_drops_branch_shell_parser() -> None:
    workflow = _read(WORKFLOWS_DIR / "complete-milestone.md")

    _assert_all_present(
        workflow,
        (
            'ARCHIVE=$(gpd milestone complete "v[X.Y]" --name "[Milestone Name]")',
            "roadmap-plus-disk union",
            "Do not manually append a MILESTONES.md entry",
            "Archive-before-delete is mandatory",
            "re-present the updated `[Y/n/e]` prompt once",
        ),
    )

    legacy_branch_fragments = (
        "git branch --list",
        "sed 's/^\\*//'",
        "for branch in",
        "git branch -d",
        "git merge --squash",
        "git merge --no-ff",
    )
    _assert_all_absent(workflow, legacy_branch_fragments)


def test_complete_milestone_wrapper_stays_public_surface_only() -> None:
    command = _read(COMMANDS_DIR / "complete-milestone.md")

    _assert_all_present(
        command,
        (
            "{GPD_INSTALL_DIR}/workflows/complete-milestone.md",
            "The workflow owns audit/readiness checks",
        ),
    )
    _assert_all_absent(command, ("<success_criteria>", "<critical_rules>", "Stage: MILESTONES.md"))
