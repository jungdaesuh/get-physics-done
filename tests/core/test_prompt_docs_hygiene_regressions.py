"""Focused prompt/docs hygiene regressions for duplicated instructions."""

from __future__ import annotations

import re
from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, fragment_count, semantic_concept

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
SPECS_DIR = REPO_ROOT / "src" / "gpd" / "specs"
WORKFLOWS_DIR = SPECS_DIR / "workflows"


def _prompt_markdown_files() -> tuple[Path, ...]:
    return tuple(sorted((*AGENTS_DIR.rglob("*.md"), *SPECS_DIR.rglob("*.md"))))


def test_prompt_docs_use_runtime_neutral_file_read_instructions() -> None:
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _prompt_markdown_files()
        if "cat {GPD_INSTALL_DIR}" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_shared_interactive_choice_fallback_is_not_reduplicated_in_workflows() -> None:
    include = "@{GPD_INSTALL_DIR}/references/shared/interactive-choice-fallback.md"
    disallowed = (
        "If `ask_user` is available",
        "If `ask_user` is not available",
        "> **Platform note:**",
        "plain-text fallback from the shared rule",
    )

    offenders: dict[str, list[str]] = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if include not in text:
            continue
        hits = [fragment for fragment in disallowed if fragment in text]
        if hits:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = hits

    assert offenders == {}


def test_runtime_delegation_fallback_boilerplate_stays_single_sourced() -> None:
    include = "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md"
    disallowed = (
        "Spawn a subagent for the task below. Adapt the `task()` call to your runtime's agent spawning mechanism.",
        "If subagent spawning is unavailable, execute these steps sequentially in the main context.",
        "sequential main-context fallback",
        "owns empty-model omission, file-producing `readonly=false`, artifact-gated completion",
    )

    offenders: dict[str, list[str]] = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if include not in text:
            continue
        hits = [fragment for fragment in disallowed if fragment in text]
        if hits:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = hits

    assert offenders == {}


def test_workflow_shell_stop_comments_use_short_form() -> None:
    verbose_stop_comment = re.compile(
        r"# STOP\s+(?:-|--|—)\s+display the error to the user and do not proceed"
        r"(?: with the workflow)?\."
    )

    offenders: dict[str, list[str]] = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        hits = verbose_stop_comment.findall(text)
        if hits:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = hits

    assert offenders == {}


def test_workflows_loading_runtime_delegation_note_do_not_duplicate_shortform_pointers() -> None:
    include = "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md"
    repeated_reference = "Apply the canonical runtime delegation convention already loaded above."
    offenders: dict[str, list[int]] = {}

    for path in sorted(WORKFLOWS_DIR.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if include not in "\n".join(lines):
            continue
        repeats: list[int] = []
        for index, line in enumerate(lines[:-2]):
            if repeated_reference not in line:
                continue
            next_lines = lines[index + 1 : index + 3]
            if any(repeated_reference in candidate for candidate in next_lines):
                repeats.append(index + 1)
        if repeats:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = repeats

    assert offenders == {}


def test_new_project_minimal_scope_block_delegates_missing_anchor_examples_to_schema() -> None:
    text = (WORKFLOWS_DIR / "new-project" / "scope-approval.md").read_text(encoding="utf-8")
    grounding_linkage = (SPECS_DIR / "templates" / "project-contract-grounding-linkage.md").read_text(
        encoding="utf-8"
    )

    assert_prompt_contracts(
        text,
        *semantic_concept(
            "scope approval delegates missing anchor examples",
            required=(
                "explicit missing-anchor uncertainty",
                "concrete anchor, reference, prior-output constraint, or baseline",
            ),
            forbidden=(
                "Prefer explicit missing-anchor wording such as",
                "Accepted shorthand like `need grounding`",
            ),
        ),
    )
    assert_prompt_contracts(
        grounding_linkage,
        fragment_count(
            "grounding linkage uncertainty note remains single sourced",
            "explicit missing-anchor notes preserve uncertainty but do not satisfy approval on their own",
            expected_count=1,
        ),
    )
