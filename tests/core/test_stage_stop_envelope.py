"""Semantic checks for the stage-stop Next Up contract."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"
STAGE_STOP_PATH = REPO_ROOT / "src/gpd/specs/references/orchestration/stage-stop-envelope.md"
CLOSEOUT_PATH = REPO_ROOT / "src/gpd/specs/workflows/execute-phase/closeout.md"
RESUME_ROUTING_PATH = REPO_ROOT / "src/gpd/specs/workflows/resume-work/resume-routing.md"
GAP_REPAIR_PATH = REPO_ROOT / "src/gpd/specs/workflows/verify-work/gap-repair.md"
CHECKPOINT_RESUME_PATH = REPO_ROOT / "src/gpd/specs/workflows/execute-phase/checkpoint-resume.md"
VERIFICATION_HANDOFF_PATH = REPO_ROOT / "src/gpd/specs/workflows/execute-phase/verification-handoff.md"
GAP_REVERIFICATION_PATH = REPO_ROOT / "src/gpd/specs/workflows/execute-phase/gap-reverification.md"
WAVE_DISPATCH_PATH = REPO_ROOT / "src/gpd/specs/workflows/execute-phase/wave-dispatch.md"
EXECUTOR_DISPATCH_PATH = REPO_ROOT / "src/gpd/specs/workflows/execute-phase/executor-dispatch.md"
BLOCKED_RECOVERY_PATH = REPO_ROOT / "src/gpd/specs/workflows/autonomous/blocked-recovery.md"
PLAN_EXECUTE_CHILD_CYCLE_PATH = REPO_ROOT / "src/gpd/specs/workflows/autonomous/plan-execute-child-cycle.md"
SESSION_ROUTER_PATH = REPO_ROOT / "src/gpd/specs/workflows/verify-work/session-router.md"
STAGE_STOP_ROOTS = (WORKFLOWS_DIR, REFERENCES_DIR / "orchestration")
STAGE_STOP_VISIBLE_NEXT_UP_PATHS = (
    STAGE_STOP_PATH,
    CHECKPOINT_RESUME_PATH,
    VERIFICATION_HANDOFF_PATH,
    GAP_REVERIFICATION_PATH,
    WAVE_DISPATCH_PATH,
    EXECUTOR_DISPATCH_PATH,
    BLOCKED_RECOVERY_PATH,
    PLAN_EXECUTE_CHILD_CYCLE_PATH,
    SESSION_ROUTER_PATH,
    GAP_REPAIR_PATH,
    RESUME_ROUTING_PATH,
)

PRIMARY_COMMAND_RE = re.compile(r"(?m)^[ \t]*Primary(?P<label> local transition)?: `(?P<command>[^`]+)`$")
AFTER_COMMAND_RE = re.compile(r"(?m)^[ \t]*\*\*After this completes:\*\* `(?P<command>[^`]+)`$")
PUBLIC_RUNTIME_COMMAND_RE = re.compile(r"^gpd:[^\s`]+(?:\s+.*)?$")
LOCAL_TRANSITION_COMMAND_RE = re.compile(r"^gpd phase complete\b")
FORBIDDEN_RUNTIME_FIELD_FRAGMENTS = (
    "cat ",
    "git ",
    "gpd --raw",
    "gpd phase complete",
    "gpd verify phase",
    "gpd:verify-phase",
    "gpd-verify-work",
)


def _fenced_blocks(text: str, language: str) -> list[str]:
    language_pattern = "ya?ml" if language == "yaml" else re.escape(language)
    pattern = re.compile(rf"(?ms)^[ \t]*```{language_pattern}\n(?P<body>.*?)\n[ \t]*```")
    return [textwrap.dedent(match.group("body")) for match in pattern.finditer(text)]


def _stage_stop_blocks(path: Path) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for block in _fenced_blocks(path.read_text(encoding="utf-8"), "yaml"):
        if "stage_stop:" not in block:
            continue
        payload = yaml.safe_load(block)
        if isinstance(payload, dict) and isinstance(payload.get("stage_stop"), dict):
            blocks.append(payload["stage_stop"])
    return blocks


def _stage_stop_owner_paths() -> list[Path]:
    paths: list[Path] = []
    for root in STAGE_STOP_ROOTS:
        for path in sorted(root.rglob("*.md")):
            if _stage_stop_blocks(path):
                paths.append(path)
    return paths


def _next_up_blocks(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
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
        blocks.append("\n".join(block_lines))
    return blocks


def _assert_public_runtime_command(command: object) -> None:
    assert isinstance(command, str)
    assert PUBLIC_RUNTIME_COMMAND_RE.match(command), command
    assert not any(fragment in command for fragment in FORBIDDEN_RUNTIME_FIELD_FRAGMENTS), command


def _assert_primary_line_shape(block: str) -> None:
    matches = list(PRIMARY_COMMAND_RE.finditer(block))
    assert len(matches) == 1, block
    label = matches[0].group("label")
    command = matches[0].group("command")
    if label == " local transition":
        assert LOCAL_TRANSITION_COMMAND_RE.match(command), command
        after_matches = list(AFTER_COMMAND_RE.finditer(block))
        assert len(after_matches) == 1, block
        _assert_public_runtime_command(after_matches[0].group("command"))
        return
    assert "**After this completes:**" not in block
    _assert_public_runtime_command(command)


def test_stage_stop_envelope_reference_defines_contract() -> None:
    assert STAGE_STOP_PATH.exists()
    text = STAGE_STOP_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    required_fragments = [
        "stage_stop:",
        "next_runtime_command",
        "NextCommand",
        "render_next_up_block",
        "exactly one public `gpd:` runtime command",
        "gpd:suggest-next",
        "raw-init boundary",
        "gpd --raw init",
        "gpd --raw stage field-access",
        "owner labels",
        "local_transition",
        "local_helper",
        "local_finalizer",
        "non-runtime stage-stop owner",
        "Secondary runtime:",
        "Secondary local helper:",
    ]
    missing = [fragment for fragment in required_fragments if fragment.lower() not in lowered]
    assert missing == []


def test_stage_stop_yaml_example_uses_accepted_status_and_public_commands() -> None:
    text = STAGE_STOP_PATH.read_text(encoding="utf-8")
    yaml_blocks = _fenced_blocks(text, "yaml")
    assert yaml_blocks

    payload = yaml.safe_load(yaml_blocks[0])
    assert set(payload) == {"stage_stop"}

    stage_stop = payload["stage_stop"]
    assert stage_stop["status"] in {"checkpoint", "blocked", "completed", "failed"}
    assert stage_stop["next_runtime_command"].startswith("gpd:")
    assert all(command.startswith("gpd:") for command in stage_stop["also_available"])


def test_stage_stop_reference_next_up_blocks_have_one_owned_primary() -> None:
    text = STAGE_STOP_PATH.read_text(encoding="utf-8")
    markdown_blocks = [block for block in _fenced_blocks(text, "markdown") if "## > Next Up" in block]
    assert markdown_blocks

    forbidden_fragments = (
        "gpd --raw init",
        "--raw init",
        "gpd --raw stage field-access",
        "--raw stage field-access",
    )
    for block in markdown_blocks:
        _assert_primary_line_shape(block)
        assert all(fragment not in block for fragment in forbidden_fragments)


def test_closeout_uses_readiness_payload_renderer_contract() -> None:
    text = CLOSEOUT_PATH.read_text(encoding="utf-8")

    assert "gpd next-up render" not in text
    assert ".next_up.rendered_markdown" in text
    assert "next_up.stage_stop_*" in text
    assert "surface the helper JSON instead of" in text
    assert "hand-rendering" in text
    assert "lifecycle_next_up.rendered_markdown" in text
    assert "The prompt must not decide" in text
    assert "Primary: `gpd:discuss-phase" not in text
    assert "Primary: `gpd:plan-phase" not in text
    assert "Primary: `gpd:audit-milestone`" not in text
    assert _stage_stop_blocks(CLOSEOUT_PATH) == []


def test_stage_stop_owned_yaml_blocks_use_public_runtime_secondaries() -> None:
    owner_paths = _stage_stop_owner_paths()
    assert STAGE_STOP_PATH in owner_paths
    assert CHECKPOINT_RESUME_PATH in owner_paths
    assert VERIFICATION_HANDOFF_PATH in owner_paths
    assert GAP_REVERIFICATION_PATH in owner_paths
    assert SESSION_ROUTER_PATH in owner_paths

    blocks_by_path = {path: _stage_stop_blocks(path) for path in owner_paths}
    assert all(blocks_by_path.values())

    for path, blocks in blocks_by_path.items():
        for stage_stop in blocks:
            assert stage_stop["status"] in {"checkpoint", "blocked", "completed", "failed"}, path
            assert "checkpoint" in stage_stop, path
            _assert_public_runtime_command(stage_stop["next_runtime_command"])
            also_available = stage_stop.get("also_available", [])
            assert isinstance(also_available, list), path
            for command in also_available:
                _assert_public_runtime_command(command)


def test_stage_stop_owned_next_up_blocks_have_one_primary_without_raw_reload() -> None:
    forbidden_fragments = (
        "gpd --raw init",
        "--raw init",
        "gpd --raw stage field-access",
        "--raw stage field-access",
    )

    for path in STAGE_STOP_VISIBLE_NEXT_UP_PATHS:
        blocks = _next_up_blocks(path)
        assert blocks, path
        for block in blocks:
            _assert_primary_line_shape(block)
            assert all(fragment not in block for fragment in forbidden_fragments), path
