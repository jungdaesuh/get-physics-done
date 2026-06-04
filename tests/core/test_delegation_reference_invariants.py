"""Focused assertions for the shared delegation reference contract."""

from __future__ import annotations

from pathlib import Path

from tests.lifecycle_contract_test_support import (
    assert_forbidden_contract as _assert_forbidden,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATION_REFERENCES = REPO_ROOT / "src/gpd/specs/references/orchestration"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_agent_delegation_reference_makes_one_shot_checkpoint_and_artifact_gate_explicit() -> None:
    text = _read(ORCHESTRATION_REFERENCES / "agent-delegation.md")
    gate = _read(ORCHESTRATION_REFERENCES / "child-artifact-gate.md")

    _assert_semantic(
        text,
        "agent delegation owns lifecycle and checkpoint semantics",
        "canonical delegation contract",
        "Delegation Invariants",
        "One-shot handoff",
        "status: checkpoint",
        "stops",
        "Fresh continuation ownership",
        "orchestrator",
    )
    _assert_semantic(
        text,
        "agent delegation treats files and commits as recovery evidence",
        "Return gate",
        "Files and commits",
        "recovery evidence",
        "child artifact gate passes",
    )
    _assert_semantic(
        text,
        "agent delegation recovery is limited to child-authored contents",
        "literal child-authored file contents",
        "Re-run the child artifact gate",
        "before accepting success",
    )
    _assert_semantic(
        text,
        "agent delegation spawn contract is inline unless explicitly exempted",
        "File-producing or state-sensitive",
        "include this block directly",
        "adjacent documented exemption",
    )
    _assert_machine(
        text,
        "agent delegation exact machine tokens",
        "references/orchestration/child-artifact-gate.md",
        "child-artifact-gate.md",
        "Do not synthesize, patch, or paste a child `gpd_return`",
        "<spawn_contract>",
        "write_scope",
        "allowed_paths",
        "expected_artifacts",
        "shared_state_policy",
        "readonly=false",
    )

    _assert_semantic(
        gate,
        "child artifact gate owns local tuple acceptance semantics",
        "Canonical child-return acceptance gate",
        "local `child_gate` tuple",
        "avoid restating this protocol",
    )
    _assert_machine(
        gate,
        "child artifact gate tuple fields",
        "`id`",
        "`role`",
        "`return_profile`",
        "`required_status`",
        "`expected_artifacts`",
        "`allowed_roots`",
        "`freshness`",
        "`validators`",
        "`applicator`",
        "`failure_route`",
        "`status_route`",
        "`write_allowlist`",
    )
    _assert_machine(
        gate,
        "child artifact gate exact return and validator tokens",
        "`gpd_return.status`",
        "`completed`",
        "`checkpoint`",
        "`blocked`",
        "`failed`",
        "`gpd_return.files_written`",
        "gpd validate child-handoff --gate ... --return-file ...",
        "gpd validate handoff-artifacts ... --require-status completed",
    )
    _assert_machine(
        gate,
        "child artifact gate result fields and failure classes",
        "`primary_failure_class`",
        "`selected_route`",
        "`return_missing`",
        "`artifact_path_repairable`",
        "`applicator_failed`",
        "mutated: false",
    )
    _assert_semantic(
        gate,
        "child artifact gate does not route from prose or recovery evidence alone",
        "Route on a valid fenced",
        "not headings",
        "Recovery evidence limit",
        "preexisting artifacts never prove success",
        "Do not synthesize, patch, or paste",
    )


def test_runtime_delegation_note_reuses_the_same_one_shot_and_artifact_language() -> None:
    text = _read(ORCHESTRATION_REFERENCES / "runtime-delegation-note.md")

    _assert_machine(
        text,
        "runtime delegation canonical reference and runtime tokens",
        "agent-delegation.md",
        "child-artifact-gate.md",
        "`gpd_return`",
        "`readonly=false`",
    )
    _assert_semantic(
        text,
        "runtime delegation note preserves one-shot and continuation ownership",
        "one-shot handoff",
        "status: checkpoint",
        "child wait in place",
        "Fresh-continuation ownership",
        "main orchestrator",
    )
    _assert_semantic(
        text,
        "runtime delegation note preserves artifact and recovery boundaries",
        "local callsite names expected artifacts",
        "validators",
        "applicator",
        "failure route",
        "missing or invalid",
        "incomplete",
        "recovery evidence only",
    )
    _assert_semantic(
        text,
        "runtime delegation note preserves fallback and empty-model behavior",
        "Empty-model omission",
        "execute sequentially in the main context",
        "same gates",
    )


def test_agent_infrastructure_points_spawned_write_contract_to_canonical_delegation_reference() -> None:
    text = _read(ORCHESTRATION_REFERENCES / "agent-infrastructure.md")
    write_contract = text.split("## Spawned Agent Write Contract", maxsplit=1)[1].split(
        "## gpd CLI State Commands", maxsplit=1
    )[0]

    _assert_machine(
        write_contract,
        "spawned write contract canonical references and fields",
        "references/orchestration/agent-delegation.md",
        "references/orchestration/child-artifact-gate.md",
        "commit_authority",
        "write_scope",
        "shared_state_policy",
    )
    _assert_semantic(
        write_contract,
        "spawned write contract treats orchestrator-owned outputs as recovery clues",
        "Files or commits",
        "orchestrator-owned agent",
        "recovery clues",
        "local child artifact gate",
        "passes",
    )
    _assert_forbidden(
        write_contract, "spawned write contract does not restate spawn contract block", "<spawn_contract>"
    )


def test_continuation_prompt_frames_the_spawn_as_a_fresh_continuation_not_an_in_run_wait() -> None:
    text = _read(TEMPLATES_DIR / "continuation-prompt.md")

    _assert_semantic(
        text,
        "continuation prompt frames fresh handoff ownership",
        "fresh continuation handoff",
        "owned by the orchestrator",
        "not an in-run wait",
        "continuation-boundary.md",
    )
    _assert_semantic(
        text,
        "continuation prompt verifies prior state and named artifacts",
        "verify prior commits exist",
        "User response",
        "expected artifacts",
        "verify them on disk",
        "before continuing",
    )
    _assert_forbidden(
        text,
        "continuation prompt avoids stale same-run wait wording",
        "wait here for the user",
        "wait for the user inside the same handoff",
    )
