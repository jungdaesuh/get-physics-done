"""Prompt-visible Next Up heading invariants."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"
STAGE_STOP_STRICT_NEXT_UP_PATHS = (
    REFERENCES_DIR / "orchestration/stage-stop-envelope.md",
    WORKFLOWS_DIR / "execute-phase/checkpoint-resume.md",
    WORKFLOWS_DIR / "execute-phase/verification-handoff.md",
    WORKFLOWS_DIR / "execute-phase/gap-reverification.md",
    WORKFLOWS_DIR / "execute-phase/wave-dispatch.md",
    WORKFLOWS_DIR / "execute-phase/executor-dispatch.md",
    WORKFLOWS_DIR / "autonomous/blocked-recovery.md",
    WORKFLOWS_DIR / "autonomous/plan-execute-child-cycle.md",
    WORKFLOWS_DIR / "verify-work/session-router.md",
)
WORKER4_RENDERER_STRICT_NEXT_UP_PATHS = (
    REFERENCES_DIR / "orchestration/stage-stop-envelope.md",
    WORKFLOWS_DIR / "resume-work/resume-routing.md",
    WORKFLOWS_DIR / "verify-work/session-router.md",
    WORKFLOWS_DIR / "verify-work/gap-repair.md",
)
PRIMARY_COMMAND_RE = re.compile(r"(?m)^[ \t]*Primary(?P<label> local transition)?: `(?P<command>[^`]+)`$")
SECONDARY_COMMAND_RE = re.compile(
    r"(?m)^[ \t]*Secondary (?P<label>runtime|local helper|local finalizer|local transition): `(?P<command>[^`]+)`$"
)
AFTER_COMMAND_RE = re.compile(r"(?m)^[ \t]*\*\*After this completes:\*\* `(?P<command>[^`]+)`$")
PUBLIC_RUNTIME_COMMAND_RE = re.compile(r"^gpd:[^\s`]+(?:\s+.*)?$")
LOCAL_TRANSITION_COMMAND_RE = re.compile(r"^gpd phase complete\b")


def _prompt_markdown_paths(*, include_references: bool = False) -> list[Path]:
    roots = [
        COMMANDS_DIR,
        AGENTS_DIR,
        WORKFLOWS_DIR,
        TEMPLATES_DIR,
    ]
    if include_references:
        roots.extend(
            [
                REFERENCES_DIR / "orchestration",
                REFERENCES_DIR / "ui",
            ]
        )
    return [path for root in roots for path in sorted(root.rglob("*.md"))]


def _next_up_blocks(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if line.strip() != "## > Next Up":
            continue

        in_fenced_block = sum(1 for previous in lines[:index] if previous.strip().startswith("```")) % 2 == 1
        block_lines = [line]
        for following in lines[index + 1 :]:
            stripped = following.strip()
            if in_fenced_block and stripped == "```":
                break
            if not in_fenced_block and stripped.startswith("## "):
                break
            block_lines.append(following)
        blocks.append((index + 1, "\n".join(block_lines)))
    return blocks


def _primary_line_error(block: str) -> str | None:
    matches = list(PRIMARY_COMMAND_RE.finditer(block))
    if len(matches) != 1:
        return "expected exactly one command-only Primary line"

    label = matches[0].group("label")
    command = matches[0].group("command")
    if label == " local transition":
        if not LOCAL_TRANSITION_COMMAND_RE.match(command):
            return f"invalid local transition primary: {command}"
        if "**After this completes:**" not in block:
            return "local transition primary missing After this completes route"
        return None

    if not PUBLIC_RUNTIME_COMMAND_RE.match(command):
        return f"invalid runtime primary: {command}"
    return None


def _renderer_shape_error(block: str) -> str | None:
    if "Primary runtime:" in block:
        return "legacy Primary runtime label"
    if "**Also available:**" in block:
        return "legacy Also available block inside Next Up"

    primary_error = _primary_line_error(block)
    if primary_error is not None:
        return primary_error

    has_local_transition_primary = "Primary local transition:" in block
    after_matches = list(AFTER_COMMAND_RE.finditer(block))
    if "**After this completes:**" in block:
        if not has_local_transition_primary:
            return "After this completes used without a local transition primary"
        if len(after_matches) != 1:
            return "After this completes must be one inline runtime command"
        after_command = after_matches[0].group("command")
        if not PUBLIC_RUNTIME_COMMAND_RE.match(after_command):
            return f"invalid After this completes runtime command: {after_command}"

    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("Secondary "):
            continue
        match = SECONDARY_COMMAND_RE.match(line)
        if match is None:
            return f"invalid secondary renderer label: {stripped}"
        label = match.group("label")
        command = match.group("command")
        if label == "runtime" and not PUBLIC_RUNTIME_COMMAND_RE.match(command):
            return f"invalid secondary runtime command: {command}"
        if label == "local transition" and not LOCAL_TRANSITION_COMMAND_RE.match(command):
            return f"invalid secondary local transition command: {command}"

    return None


def test_prompt_markdown_uses_canonical_next_up_heading() -> None:
    offenders: list[str] = []

    for path in _prompt_markdown_paths():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("##") and "Next Up" in stripped and stripped != "## > Next Up":
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{line}")

    assert offenders == []


def test_prompt_markdown_avoids_bang_bang_headings() -> None:
    offenders: list[str] = []

    for path in _prompt_markdown_paths():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip().startswith("## !!"):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{line}")

    assert offenders == []


def test_next_up_blocks_do_not_expose_raw_stage_reload_commands() -> None:
    forbidden_fragments = (
        "gpd --raw init",
        "--raw init",
        "gpd --raw stage field-access",
        "--raw stage field-access",
    )
    offenders: list[str] = []

    for path in _prompt_markdown_paths(include_references=True):
        for line_number, block in _next_up_blocks(path):
            for fragment in forbidden_fragments:
                if fragment in block:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{fragment}")

    assert offenders == []


def test_next_up_blocks_use_runtime_verify_work_not_structural_verify_commands() -> None:
    forbidden_fragments = (
        "gpd verify phase",
        "gpd:verify-phase",
        "gpd-verify-work",
    )
    offenders: list[str] = []

    for path in _prompt_markdown_paths(include_references=True):
        for line_number, block in _next_up_blocks(path):
            for fragment in forbidden_fragments:
                if fragment in block:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{fragment}")

    assert offenders == []


def test_stage_stop_owned_next_up_primary_lines_are_command_only() -> None:
    offenders: list[str] = []

    for path in STAGE_STOP_STRICT_NEXT_UP_PATHS:
        blocks = _next_up_blocks(path)
        assert blocks, path
        for line_number, block in blocks:
            error = _primary_line_error(block)
            if error is not None:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{error}")

    assert offenders == []


def test_worker4_next_up_examples_use_renderer_shape() -> None:
    offenders: list[str] = []

    for path in WORKER4_RENDERER_STRICT_NEXT_UP_PATHS:
        blocks = _next_up_blocks(path)
        assert blocks, path
        for line_number, block in blocks:
            error = _renderer_shape_error(block)
            if error is not None:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}:{error}")

    assert offenders == []


def test_suggest_next_single_result_uses_shared_renderer_shape() -> None:
    text = (COMMANDS_DIR / "suggest-next.md").read_text(encoding="utf-8")

    assert "typed `NextCommand` decision" in text
    assert "shared renderer shape" in text
    assert "Primary: `{command}`" in text
    assert "Primary local transition:" in text
    assert "**After this completes:**" in text
    assert "**{command}**" not in text
    assert "Do not use a separate bold-only command block." in text
