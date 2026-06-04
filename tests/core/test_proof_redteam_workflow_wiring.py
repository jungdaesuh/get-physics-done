"""Assertions for fail-closed proof redteam workflow wiring."""

from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from tests.lifecycle_contract_test_support import artifact_paths, child_gate_from_text
from tests.lifecycle_contract_test_support import (
    assert_forbidden_lifecycle_prose as _assert_absent,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
SPECS_DIR = REPO_ROOT / "src/gpd/specs"
PROOF_GATE_REF = "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md"
PROOF_GATE_PATH = "{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md"
REPEATED_PROOF_CHECKPOINT_LINES = (
    "If the runtime needs user input, return `status: checkpoint` instead of waiting inside this run.",
    "If the runtime needs user input, return `status: checkpoint` instead of waiting inside the spawned run.",
    "Return `status: checkpoint` if the runtime needs user input instead of waiting inside the spawned run.",
    "Return `status: checkpoint` instead of waiting for user input inside this run.",
)


def _read(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def _expanded(name: str) -> str:
    return expand_at_includes(_read(name), SPECS_DIR, "/runtime/")


def _peer_review_stage_text(*names: str) -> str:
    stage_names = names or (
        "artifact-discovery.md",
        "panel-stages.md",
        "final-adjudication.md",
    )
    return "\n".join((WORKFLOWS_DIR / "peer-review" / name).read_text(encoding="utf-8") for name in stage_names)


def _expanded_peer_review_stage_text(*names: str) -> str:
    return expand_at_includes(_peer_review_stage_text(*names), SPECS_DIR, "/runtime/")


def _execute_phase_stage_text(name: str) -> str:
    return (WORKFLOWS_DIR / "execute-phase" / name).read_text(encoding="utf-8")


def test_plan_and_execute_phase_require_proof_redteam_gates() -> None:
    plan_phase = _read("plan-phase.md")
    execute_phase = _read("execute-phase.md")

    _assert_machine(
        plan_phase,
        "plan-phase proof redteam planning gate tokens",
        "## 1.5 Proof-Obligation Planning Gate",
        "`--skip-verify`",
        "{plan_id}-PROOF-REDTEAM.md",
    )

    _assert_machine(
        execute_phase,
        "execute-phase proof redteam gate machine tokens",
        '<step name="detect_proof_obligation_work">',
        PROOF_GATE_PATH,
        "autonomy=yolo",
        "{plan_id}-PROOF-REDTEAM.md",
        "`gpd-check-proof`",
        'subagent_type="gpd-check-proof"',
    )
    _assert_semantic(
        execute_phase,
        "execute-phase proof bypass settings do not waive proof verification",
        "proof-bearing",
        "generic post-execution verifier is disabled",
        "proof verification still runs",
        "fail-closed gate before wave success",
    )


def test_verification_workflows_fail_closed_on_missing_proof_coverage() -> None:
    verify_phase_raw = _read("verify-phase.md")
    verify_work_raw = _read("verify-work.md")
    derive_equation_raw = _read("derive-equation.md")
    verify_phase = _expanded("verify-phase.md")
    verify_work = _expanded("verify-work.md")
    derive_equation = _expanded("derive-equation.md")

    assert PROOF_GATE_REF not in verify_phase_raw
    assert PROOF_GATE_PATH in verify_phase_raw
    assert PROOF_GATE_REF in verify_work_raw
    assert PROOF_GATE_REF in derive_equation_raw

    _assert_semantic(
        verify_phase,
        "verify-phase proof obligation gate requires theorem audit and adversarial case",
        "theorem-to-proof audit",
        "adversarial special-case",
    )
    _assert_machine(verify_phase, "verify-phase proof obligation gate marker", '<step name="proof_obligation_gate">')
    _assert_semantic(
        verify_phase,
        "verify-phase missing proof coverage is blocking and repair is one-shot",
        "Missing artifact",
        "missing theorem inventory",
        "status != passed",
        "blocking gap",
        "spawn `gpd-check-proof` once",
    )
    _assert_absent(
        verify_phase,
        "verify-phase no inline user waiting for proof repair",
        "wait for user confirmation",
        "ask the user then continue",
        "pause here for approval",
    )

    _assert_semantic(
        verify_work,
        "verify-work proof flags cannot waive canonical artifact",
        "For proof-bearing work",
        "canonical `*-PROOF-REDTEAM.md` artifact",
        "missing/stale/malformed/not `passed`",
    )
    _assert_machine(
        verify_work,
        "verify-work proof critic handoff tokens",
        "CHECK_PROOF_MODEL=$(gpd resolve-model gpd-check-proof)",
        'task(\n  subagent_type="gpd-check-proof"',
    )
    _assert_semantic(verify_work, "verify-work proof floor remains mandatory", "additional mandatory floor applies")

    _assert_machine(
        derive_equation,
        "derive-equation proof critic handoff tokens",
        '<step name="proof_obligation_screen">',
        "DERIVATION-{slug}-PROOF-REDTEAM.md",
        "gpd-check-proof",
        "CHECK_PROOF_MODEL=$(gpd resolve-model gpd-check-proof)",
        'task(\n  subagent_type="gpd-check-proof"',
    )
    _assert_semantic(
        derive_equation,
        "derive-equation proof-bearing derivations fail closed",
        "Proof-bearing derivations",
        "fail closed",
    )


def test_execute_phase_proof_critic_child_gate_preserves_local_machine_contract() -> None:
    proof_dispatch = _execute_phase_stage_text("proof-critic-dispatch.md")
    gate = child_gate_from_text(proof_dispatch, "proof_critic_wave_audit")
    failure_route = {failure.value: route for failure, route in gate.failure_route.items()}

    _assert_machine(
        proof_dispatch,
        "proof critic child gate profile source token",
        'profile: "execute.proof_critic_report.v1"',
    )
    assert gate.role == "gpd-check-proof"
    assert gate.return_profile == "verifier"
    assert gate.required_status == "completed"
    assert artifact_paths(gate) == ("{phase_dir}/{plan_id}-PROOF-REDTEAM.md",)
    assert gate.allowed_roots == ("{phase_dir}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$PROOF_HANDOFF_STARTED_AT"
    assert gate.write_allowlist == ("{phase_dir}/{plan_id}-PROOF-REDTEAM.md",)
    assert gate.status_route["checkpoint"] == "checkpoint_resume"
    assert gate.status_route["blocked"] == "wave_failure_menu"
    assert gate.status_route["failed"] == "wave_failure_menu"
    assert failure_route["return_missing"] == "repair_prompt_once"
    assert failure_route["artifact_path_repairable"] == "repair_path_once"
    assert failure_route["applicator_failed"] == "wave_failure_menu"
    assert any(
        "gpd validate proof-redteam {phase_dir}/{plan_id}-PROOF-REDTEAM.md" in validator
        for validator in gate.validators
    )
    assert any("--require-files-written" in validator for validator in gate.validators)


def test_proof_redteam_handoffs_delegate_checkpoint_semantics_to_shared_contracts() -> None:
    workflow_names = ("derive-equation.md", "execute-phase.md", "verify-phase.md", "verify-work.md")

    combined = "\n".join((*(_read(name) for name in workflow_names), _peer_review_stage_text("panel-stages.md")))

    _assert_absent(
        combined,
        "proof-redteam handoffs use shared checkpoint semantics",
        *REPEATED_PROOF_CHECKPOINT_LINES,
    )

    _assert_semantic(
        combined,
        "proof-redteam handoffs use shared child return semantics",
        "proof-redteam protocol",
        "one-shot return semantics",
        "typed proof-redteam handoff contract",
        "shared verification child-return contract",
    )


def test_quick_publication_and_settings_surfaces_block_proof_bypass() -> None:
    quick = _read("quick.md")
    write_paper = _read("write-paper.md")
    peer_review = _expanded_peer_review_stage_text()
    peer_review_raw = _peer_review_stage_text()
    settings = _read("settings.md")

    _assert_semantic(
        quick,
        "quick blocks proof obligation bypass",
        "Quick mode",
        "must not produce",
        "theorem-style",
        "proof_obligation",
        "blocked pending the full proof-redteam workflow",
    )

    _assert_semantic(
        write_paper,
        "write-paper proof support gate requires passed proof-redteam artifacts",
        "proof obligations",
        "passed proof-redteam artifacts",
        "claim/proof scope",
    )
    _assert_semantic(
        write_paper,
        "write-paper cannot smooth beyond proof-redteam scope",
        "must not strengthen",
        "generalize",
        "rhetorically smooth",
        "theorem-style claims",
        "passed proof-redteam scope",
    )

    _assert_machine(peer_review, "peer review proof-bearing routing marker", "<proof_bearing_routing>")
    assert PROOF_GATE_PATH not in peer_review_raw
    _assert_machine(
        (WORKFLOWS_DIR / "peer-review-stage-manifest.json").read_text(encoding="utf-8"),
        "peer review manifest proof gate reference",
        "references/verification/core/proof-redteam-workflow-gate.md",
    )
    _assert_machine(
        peer_review,
        "peer review proof-redteam artifact and role tokens",
        "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md",
        "gpd-check-proof",
        "major_revision",
        "reject",
    )
    _assert_semantic(
        peer_review,
        "peer review stage 2/3/proof wave barriers before stage 4",
        "Stage 2",
        "Stage 3",
        "proof critique",
        "parallel",
        "barriered wave",
        "Before Stage 4",
        "typed return",
    )
    _assert_absent(
        peer_review,
        "peer review no stale hard-coded review-root proof sibling",
        "expect a sibling `GPD/review/PROOF-REDTEAM{round_suffix}.md` artifact",
    )

    _assert_machine(
        settings,
        "settings proof-redteam config tokens",
        "workflow.verifier=false",
        "execution.review_cadence",
        "autonomy=yolo",
    )
    _assert_semantic(
        settings,
        "settings cannot waive proof-redteam",
        "does NOT disable mandatory proof red-teaming",
        "Sparse cadence",
        "does not waive proof red-teaming",
    )


def test_peer_review_final_decision_guardrail_requires_same_round_proof_redteam() -> None:
    peer_review = _expanded_peer_review_stage_text("panel-stages.md", "final-adjudication.md")
    reliability = (SPECS_DIR / "references/publication/peer-review-reliability.md").read_text(encoding="utf-8")

    _assert_machine(
        peer_review,
        "peer review final decision artifacts validators and proof fields",
        "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md",
        "aligned `proof_audits[]`",
        "gpd validate referee-decision ${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json --strict "
        "--ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
    )
    _assert_semantic(
        peer_review,
        "peer review final decision blocks favorable recommendations without same-round proof clearance",
        "wrong-round",
        "wrong-root",
        "non-passing same-round",
        "blocks any favorable recommendation",
        "not a substitute",
        "same-round proof-redteam clearance",
        "strict final-decision validator",
        "favorable decision guardrail",
    )
    _assert_semantic(
        reliability,
        "peer review reliability requires selected root and strict final-decision proof clearance",
        "same selected review root",
        "stage-review validation alone",
        "does not clear",
        "same-round proof-redteam policy",
    )


def test_proof_obligation_detection_distinguishes_generic_manuscript_claims() -> None:
    proof_gate = (SPECS_DIR / "references/verification/core/proof-redteam-workflow-gate.md").read_text(encoding="utf-8")
    quick = _read("quick.md")
    peer_review = _expanded_peer_review_stage_text("artifact-discovery.md")

    _assert_machine(
        proof_gate,
        "proof gate schema tokens for claim classification",
        "ProjectContract",
        "claim_kind: theorem | lemma | corollary | proposition | claim",
    )
    _assert_semantic(
        proof_gate,
        "proof gate distinguishes generic claims from proof-bearing metadata",
        "generic manuscript claim",
        "bare word `claim`",
        "not proof-bearing by itself",
        "Require theorem/proof/formal metadata",
    )

    _assert_machine(
        "\n".join((quick, peer_review)),
        "quick and peer-review claim classification field tokens",
        "ProjectContract `claim_kind: claim`",
        "Paper `ClaimRecord.claim_kind: claim`",
    )
    _assert_semantic(
        quick,
        "quick reroute distinguishes generic claims from proof obligations",
        "generic manuscript or task",
        "claim",
        "not enough by itself",
        "theorem/proof/formal metadata",
        "proof_obligation",
    )
