"""Focused tests for child gate tuple schema and parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from gpd.core.child_gate_snippets import (
    AggregateChildGateTuple,
    aggregate_child_gate_tuple_from_payload,
    expand_child_gate_profile_payload,
    list_child_gate_profiles,
    normalize_child_gate_profile_id,
    parse_aggregate_child_gate_markdown,
    render_child_gate_inline_summary,
    render_child_gate_markdown,
)
from gpd.core.child_handoff import (
    ChildGateApplicator,
    ChildGateArtifact,
    ChildGateFreshness,
    ChildGateTuple,
    child_gate_tuple_from_payload,
    parse_child_gate_markdown,
)
from gpd.core.handoff_artifacts import HandoffFailureClass

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
_YAML_BLOCK_RE = re.compile(r"```ya?ml\n(?P<body>.*?)\n```", re.DOTALL)


@dataclass(frozen=True)
class WorkflowChildGate:
    source: str
    line: int
    gate: ChildGateTuple


@dataclass(frozen=True)
class WorkflowAggregateChildGate:
    source: str
    line: int
    gate: AggregateChildGateTuple


def _planner_gate() -> ChildGateTuple:
    return ChildGateTuple(
        id="planner_initial_plan",
        role="gpd-planner",
        required_status="completed",
        expected_artifacts=(
            ChildGateArtifact(
                path="${PHASE_DIR}/*-PLAN.md",
                kind="glob",
            ),
        ),
        allowed_roots=("${PHASE_DIR}",),
        freshness=ChildGateFreshness(
            marker="$PLANNER_HANDOFF_STARTED_AT",
            require_mtime_at_or_after_marker=True,
        ),
        validators=(
            "gpd validate handoff-artifacts - --expected-glob '${PHASE_DIR}/*-PLAN.md' --allowed-root '${PHASE_DIR}' --require-files-written --require-status completed --fresh-after \"$PLANNER_HANDOFF_STARTED_AT\"",
            "gpd validate plan-contract <each fresh plan>",
            "gpd validate plan-preflight <each fresh plan>",
        ),
        applicator=ChildGateApplicator(command="none", require_passed_true=False),
    )


def _gate_markdown(gate: ChildGateTuple) -> str:
    return render_child_gate_markdown(gate)


def _workflow_child_gate(relative_path: str, gate_id: str) -> ChildGateTuple:
    for item in _workflow_child_gates():
        if item.source == relative_path and item.gate.id == gate_id:
            return item.gate
    raise AssertionError(f"missing child_gate {gate_id} in {relative_path}")


def _workflow_child_gates() -> tuple[WorkflowChildGate, ...]:
    gates: list[WorkflowChildGate] = []
    errors: list[str] = []

    for path in sorted(WORKFLOWS_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in _YAML_BLOCK_RE.finditer(text):
            body = match.group("body")
            if "child_gate" not in body:
                continue
            line = text[: match.start()].count("\n") + 1
            source = str(path.relative_to(WORKFLOWS_DIR))
            try:
                payload = yaml.safe_load(body)
            except Exception as exc:
                if re.search(r"(?m)^child_gates?\s*:", body):
                    errors.append(f"{path.relative_to(REPO_ROOT)}:{line}: {exc}")
                continue
            if not isinstance(payload, dict):
                if re.search(r"(?m)^child_gates?\s*:", body):
                    errors.append(f"{path.relative_to(REPO_ROOT)}:{line}: child_gate payload must be a mapping")
                continue

            try:
                if "child_gate" in payload:
                    gates.append(
                        WorkflowChildGate(
                            source=source,
                            line=line,
                            gate=parse_child_gate_markdown(f"```yaml\n{body}\n```"),
                        )
                    )
                if isinstance(payload.get("child_gates"), list):
                    for gate_payload in payload["child_gates"]:
                        gates.append(
                            WorkflowChildGate(
                                source=source,
                                line=line,
                                gate=child_gate_tuple_from_payload(gate_payload),
                            )
                        )
            except Exception as exc:  # pragma: no cover - assertion reports exact prompt location
                errors.append(f"{path.relative_to(REPO_ROOT)}:{line}: {exc}")

    assert errors == []
    return tuple(gates)


def _workflow_aggregate_child_gates() -> tuple[WorkflowAggregateChildGate, ...]:
    gates: list[WorkflowAggregateChildGate] = []
    errors: list[str] = []

    for path in sorted(WORKFLOWS_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in _YAML_BLOCK_RE.finditer(text):
            body = match.group("body")
            if "aggregate_child_gate" not in body:
                continue
            line = text[: match.start()].count("\n") + 1
            source = str(path.relative_to(WORKFLOWS_DIR))
            try:
                gates.append(
                    WorkflowAggregateChildGate(
                        source=source,
                        line=line,
                        gate=parse_aggregate_child_gate_markdown(f"```yaml\n{body}\n```"),
                    )
                )
            except Exception as exc:  # pragma: no cover - assertion reports exact prompt location
                errors.append(f"{path.relative_to(REPO_ROOT)}:{line}: {exc}")

    assert errors == []
    return tuple(gates)


def _renderer_gate() -> ChildGateTuple:
    return ChildGateTuple(
        id="renderer_gate",
        role="gpd-planner",
        required_status="completed",
        expected_artifacts=(
            ChildGateArtifact(path="GPD/plan.md"),
            ChildGateArtifact(
                path="GPD/reports/*.md",
                kind="glob",
                required=False,
                must_be_named_in_files_written=False,
            ),
        ),
        allowed_roots=("GPD",),
        freshness=ChildGateFreshness(
            marker="$HANDOFF_STARTED_AT",
            require_mtime_at_or_after_marker=True,
        ),
        validators=("readable", "plan-contract"),
        applicator=ChildGateApplicator(
            command="gpd --raw apply-return-updates GPD/plan.md",
            require_passed_true=True,
        ),
        write_allowlist=("GPD/plan.md", "GPD/reports/*.md"),
        status_route={
            "checkpoint": "present_checkpoint",
            "blocked": "surface_blocker",
        },
    )


_EXPECTED_WORKFLOW_CHILD_GATE_SOURCES = {
    "gap_closure_reverification": "execute-phase/gap-reverification.md",
    "literature_scouts": "new-project/literature-survey.md",
    "literature_synthesizer": "new-project/literature-survey.md",
    "milestone_literature_scouts": "new-milestone/survey-objectives.md",
    "milestone_literature_synthesizer": "new-milestone/survey-objectives.md",
    "milestone_roadmapper": "new-milestone/roadmap-authoring.md",
    "notation_conventions": "new-project/conventions-handoff.md",
    "peer_review_stage6_referee": "peer-review/final-adjudication.md",
    "phase_researcher_context_refresh": "plan-phase/research-routing.md",
    "plan_checker_review": "plan-phase/checker-revision.md",
    "planner_initial_plan": "plan-phase/planner-authoring.md",
    "planner_revision": "plan-phase/revision-planner-handoff.md",
    "post_execution_verifier": "execute-phase/verification-handoff.md",
    "project_roadmapper": "new-project/roadmap-authoring.md",
    "proof_critic_wave_audit": "execute-phase/proof-critic-dispatch.md",
    "quick_executor_summary": ("quick/task-authoring.md", "quick/reference-context.md"),
    "quick_planner_plan": ("quick/task-authoring.md", "quick/reference-context.md"),
    "rapid_consistency_check": "execute-phase/consistency-check.md",
    "respond_to_referees_revision_section": "respond-to-referees/response-authoring.md",
    "verify_work_gap_plan_checker": "verify-work/gap-repair.md",
    "verify_work_gap_planner": "verify-work/gap-repair.md",
    "verify_work_proof_critic": "verify-work/phase-bootstrap.md",
    "verify_work_verifier_report": "verify-work/inventory-build.md",
    "wave_executor_plan_result": "execute-phase/wave-return-checkpoint.md",
    "write_paper_bibliographer": "write-paper/consistency-references.md",
    "write_paper_response_pair": "write-paper/publication-review-finalization.md",
    "write_paper_section_writer": "write-paper/authoring.md",
}


def _expected_sources_for_gate(gate_id: str) -> tuple[str, ...]:
    sources = _EXPECTED_WORKFLOW_CHILD_GATE_SOURCES[gate_id]
    if isinstance(sources, str):
        return (sources,)
    return sources


def _expected_workflow_child_gate_keys() -> tuple[tuple[str, str], ...]:
    return tuple(
        (source, gate_id)
        for gate_id in sorted(_EXPECTED_WORKFLOW_CHILD_GATE_SOURCES)
        for source in sorted(_expected_sources_for_gate(gate_id))
    )


_EXPECTED_WORKFLOW_CHILD_GATE_ROLE_PROFILE = {
    "gap_closure_reverification": ("gpd-verifier", "verifier"),
    "literature_scouts": ("gpd-project-researcher", "researcher"),
    "literature_synthesizer": ("gpd-research-synthesizer", "synthesizer"),
    "milestone_literature_scouts": ("gpd-project-researcher", "researcher"),
    "milestone_literature_synthesizer": ("gpd-research-synthesizer", "synthesizer"),
    "milestone_roadmapper": ("gpd-roadmapper", "roadmapper"),
    "notation_conventions": ("gpd-notation-coordinator", "roadmapper"),
    "peer_review_stage6_referee": ("gpd-referee", "referee"),
    "phase_researcher_context_refresh": ("gpd-phase-researcher", "researcher"),
    "plan_checker_review": ("gpd-plan-checker", "checker"),
    "planner_initial_plan": ("gpd-planner", "planner"),
    "planner_revision": ("gpd-planner", "planner"),
    "post_execution_verifier": ("gpd-verifier", "verifier"),
    "project_roadmapper": ("gpd-roadmapper", "roadmapper"),
    "proof_critic_wave_audit": ("gpd-check-proof", "verifier"),
    "quick_executor_summary": ("gpd-executor", "executor"),
    "quick_planner_plan": ("gpd-planner", "planner"),
    "rapid_consistency_check": ("gpd-consistency-checker", "checker"),
    "respond_to_referees_revision_section": ("gpd-paper-writer", "executor"),
    "verify_work_gap_plan_checker": ("gpd-plan-checker", "checker"),
    "verify_work_gap_planner": ("gpd-planner", "planner"),
    "verify_work_proof_critic": ("gpd-check-proof", "verifier"),
    "verify_work_verifier_report": ("gpd-verifier", "verifier"),
    "wave_executor_plan_result": ("gpd-executor", "executor"),
    "write_paper_bibliographer": ("gpd-bibliographer", "bibliographer"),
    "write_paper_response_pair": ("gpd-paper-writer", "paper_writer"),
    "write_paper_section_writer": ("gpd-paper-writer", "paper_writer"),
}

_EXPECTED_WORKFLOW_CHILD_GATE_ARTIFACTS = {
    "gap_closure_reverification": (("{phase_dir}/{phase_number}-VERIFICATION.md", "path", True, True),),
    "literature_scouts": (
        ("GPD/literature/PRIOR-WORK.md", "path", True, True),
        ("GPD/literature/METHODS.md", "path", True, True),
        ("GPD/literature/COMPUTATIONAL.md", "path", True, True),
        ("GPD/literature/PITFALLS.md", "path", True, True),
    ),
    "literature_synthesizer": (("GPD/literature/SUMMARY.md", "path", True, True),),
    "milestone_literature_scouts": (
        ("GPD/literature/PRIOR-WORK.md", "path", True, True),
        ("GPD/literature/METHODS.md", "path", True, True),
        ("GPD/literature/COMPUTATIONAL.md", "path", True, True),
        ("GPD/literature/PITFALLS.md", "path", True, True),
    ),
    "milestone_literature_synthesizer": (("GPD/literature/SUMMARY.md", "path", True, True),),
    "milestone_roadmapper": (("GPD/ROADMAP.md", "path", True, True), ("GPD/REQUIREMENTS.md", "path", True, True)),
    "notation_conventions": (("GPD/CONVENTIONS.md", "path", True, True),),
    "peer_review_stage6_referee": (
        ("${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md", "path", True, True),
        ("${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex", "path", True, True),
        ("${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json", "path", True, True),
        ("${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json", "path", True, True),
        ("${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md when produced", "path", True, True),
    ),
    "phase_researcher_context_refresh": (("${PHASE_DIR}/${PHASE_NUMBER}-RESEARCH.md", "path", True, True),),
    "plan_checker_review": (),
    "planner_initial_plan": (("${PHASE_DIR}/*-PLAN.md", "glob", True, True),),
    "planner_revision": (("${PHASE_DIR}/*-PLAN.md", "glob", True, True),),
    "post_execution_verifier": (("{phase_dir}/{phase_number}-VERIFICATION.md", "path", True, True),),
    "project_roadmapper": (
        ("GPD/ROADMAP.md", "path", True, True),
        ("GPD/STATE.md", "path", True, True),
        ("GPD/REQUIREMENTS.md", "path", True, True),
    ),
    "proof_critic_wave_audit": (("{phase_dir}/{plan_id}-PROOF-REDTEAM.md", "path", True, True),),
    "quick_executor_summary": (("${QUICK_DIR}/${next_num}-SUMMARY.md", "path", True, True),),
    "quick_planner_plan": (("${QUICK_DIR}/${next_num}-PLAN.md", "path", True, True),),
    "rapid_consistency_check": (("{phase_dir}/CONSISTENCY-CHECK.md", "path", True, True),),
    "respond_to_referees_revision_section": (
        ("${PAPER_DIR}/{resolved_section_file}", "path", True, True),
        ("${RESPONSE_AUTHOR_PATH}", "path", True, True),
        ("${RESPONSE_REFEREE_PATH}", "path", True, True),
    ),
    "verify_work_gap_plan_checker": (),
    "verify_work_gap_planner": (("${PHASE_DIR_ABS}/*-PLAN.md", "glob", True, True),),
    "verify_work_proof_critic": (("${PHASE_DIR_ABS}/${phase_number}-PROOF-REDTEAM.md", "path", True, True),),
    "verify_work_verifier_report": (("${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md", "path", True, True),),
    "wave_executor_plan_result": (("${SUMMARY_FILE}", "path", True, True),),
    "write_paper_bibliographer": (
        ("${PAPER_DIR}/CITATION-AUDIT.md", "path", True, True),
        ("GPD/references-status.json", "path", True, True),
        ("{ACTIVE_BIBLIOGRAPHY_PATH} only when changed", "path", True, True),
        ("${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json after paper-build refresh", "path", True, True),
    ),
    "write_paper_response_pair": (
        ("${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md", "path", True, True),
        ("${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md", "path", True, True),
    ),
    "write_paper_section_writer": (("${PAPER_DIR}/{section_path}.tex", "path", True, True),),
}

_EXPECTED_WORKFLOW_CHILD_GATE_ROOTS = {
    "gap_closure_reverification": ("{phase_dir}",),
    "literature_scouts": ("GPD/literature",),
    "literature_synthesizer": ("GPD/literature",),
    "milestone_literature_scouts": ("GPD/literature",),
    "milestone_literature_synthesizer": ("GPD/literature",),
    "milestone_roadmapper": ("GPD",),
    "notation_conventions": ("GPD",),
    "peer_review_stage6_referee": (),
    "phase_researcher_context_refresh": ("${PHASE_DIR}",),
    "plan_checker_review": (),
    "planner_initial_plan": ("${PHASE_DIR}",),
    "planner_revision": ("${PHASE_DIR}",),
    "post_execution_verifier": ("{phase_dir}",),
    "project_roadmapper": ("GPD",),
    "proof_critic_wave_audit": ("{phase_dir}",),
    "quick_executor_summary": ("${QUICK_DIR}",),
    "quick_planner_plan": ("${QUICK_DIR}",),
    "rapid_consistency_check": ("{phase_dir}",),
    "respond_to_referees_revision_section": ("${PAPER_DIR}", "${selected_publication_root}", "${selected_review_root}"),
    "verify_work_gap_plan_checker": (),
    "verify_work_gap_planner": ("${PHASE_DIR_ABS}",),
    "verify_work_proof_critic": ("${PHASE_DIR_ABS}",),
    "verify_work_verifier_report": ("${PHASE_DIR_ABS}",),
    "wave_executor_plan_result": ("{phase_dir}",),
    "write_paper_bibliographer": ("${PAPER_DIR}", "GPD"),
    "write_paper_response_pair": ("${selected_publication_root}", "${selected_review_root}"),
    "write_paper_section_writer": ("${PAPER_DIR}",),
}

_EXPECTED_WORKFLOW_CHILD_GATE_FRESHNESS_MARKERS = {
    "gap_closure_reverification": "$REVERIFY_HANDOFF_STARTED_AT",
    "literature_scouts": "$SCOUT_HANDOFF_STARTED_AT per scout",
    "literature_synthesizer": "$SYNTHESIZER_HANDOFF_STARTED_AT",
    "milestone_literature_scouts": "$SCOUT_HANDOFF_STARTED_AT per scout",
    "milestone_literature_synthesizer": "$SYNTHESIZER_HANDOFF_STARTED_AT",
    "milestone_roadmapper": "$MILESTONE_ROADMAPPER_HANDOFF_STARTED_AT",
    "notation_conventions": "$NOTATION_HANDOFF_STARTED_AT",
    "peer_review_stage6_referee": None,
    "phase_researcher_context_refresh": "$RESEARCH_HANDOFF_STARTED_AT",
    "plan_checker_review": None,
    "planner_initial_plan": "$PLANNER_HANDOFF_STARTED_AT",
    "planner_revision": "$PLANNER_HANDOFF_STARTED_AT",
    "post_execution_verifier": "$VERIFIER_HANDOFF_STARTED_AT",
    "project_roadmapper": "$ROADMAPPER_HANDOFF_STARTED_AT",
    "proof_critic_wave_audit": "$PROOF_HANDOFF_STARTED_AT",
    "quick_executor_summary": "$QUICK_EXECUTOR_HANDOFF_STARTED_AT",
    "quick_planner_plan": "$QUICK_PLANNER_HANDOFF_STARTED_AT",
    "rapid_consistency_check": "$CONSISTENCY_HANDOFF_STARTED_AT",
    "respond_to_referees_revision_section": "$REVISION_SECTION_HANDOFF_STARTED_AT",
    "verify_work_gap_plan_checker": None,
    "verify_work_gap_planner": "$GAP_PLANNER_HANDOFF_STARTED_AT",
    "verify_work_proof_critic": "$PROOF_HANDOFF_STARTED_AT",
    "verify_work_verifier_report": "$VERIFIER_HANDOFF_STARTED_AT",
    "wave_executor_plan_result": "$EXECUTOR_HANDOFF_STARTED_AT",
    "write_paper_bibliographer": "$BIBLIO_HANDOFF_STARTED_AT",
    "write_paper_response_pair": "$RESPONSE_HANDOFF_STARTED_AT",
    "write_paper_section_writer": "$SECTION_WRITER_HANDOFF_STARTED_AT",
}

_EXPECTED_WORKFLOW_CHILD_GATE_VALIDATOR_COUNTS = {
    "gap_closure_reverification": 4,
    "literature_scouts": 2,
    "literature_synthesizer": 2,
    "milestone_literature_scouts": 2,
    "milestone_literature_synthesizer": 2,
    "milestone_roadmapper": 2,
    "notation_conventions": 3,
    "peer_review_stage6_referee": 2,
    "phase_researcher_context_refresh": 2,
    "plan_checker_review": 3,
    "planner_initial_plan": 3,
    "planner_revision": 3,
    "post_execution_verifier": 4,
    "project_roadmapper": 3,
    "proof_critic_wave_audit": 3,
    "quick_executor_summary": 1,
    "quick_planner_plan": 2,
    "rapid_consistency_check": 2,
    "respond_to_referees_revision_section": 4,
    "verify_work_gap_plan_checker": 3,
    "verify_work_gap_planner": 3,
    "verify_work_proof_critic": 3,
    "verify_work_verifier_report": 4,
    "wave_executor_plan_result": 4,
    "write_paper_bibliographer": 3,
    "write_paper_response_pair": 2,
    "write_paper_section_writer": 3,
}

_EXPECTED_WORKFLOW_CHILD_GATE_APPLICATORS = {
    "gap_closure_reverification": (
        "none; closeout/update_roadmap is allowed only after re-verifier and consistency gates pass",
        False,
    ),
    "literature_scouts": ("none", False),
    "literature_synthesizer": ("none", False),
    "milestone_literature_scouts": ("none", False),
    "milestone_literature_synthesizer": ("none", False),
    "milestone_roadmapper": (
        "main workflow applies accepted state changes with gpd state patch / gpd state add-decision after the artifact gate",
        False,
    ),
    "notation_conventions": ("child direct gpd convention set in auto/approved continuation", False),
    "peer_review_stage6_referee": ("none", False),
    "phase_researcher_context_refresh": ("none", False),
    "plan_checker_review": ("none", False),
    "planner_initial_plan": ("none", False),
    "planner_revision": ("none", False),
    "post_execution_verifier": (
        "none; closeout/update_roadmap is allowed only after verifier and consistency gates pass",
        False,
    ),
    "project_roadmapper": ("shared_state_policy=direct for this legacy init handoff", False),
    "proof_critic_wave_audit": ("none", False),
    "quick_executor_summary": ('gpd apply-return-updates "${QUICK_DIR}/${next_num}-SUMMARY.md"', True),
    "quick_planner_plan": ("none", False),
    "rapid_consistency_check": ("none", False),
    "respond_to_referees_revision_section": ("none", False),
    "verify_work_gap_plan_checker": ("none", False),
    "verify_work_gap_planner": ("none", False),
    "verify_work_proof_critic": ("none", False),
    "verify_work_verifier_report": ("sync_verifier_output only after tuple passes", False),
    "wave_executor_plan_result": ("gpd --raw apply-return-updates ${SUMMARY_FILE}", True),
    "write_paper_bibliographer": ("none", False),
    "write_paper_response_pair": ("none", False),
    "write_paper_section_writer": ("none", False),
}

_EXPECTED_WORKFLOW_CHILD_GATE_WRITE_ALLOWLIST = {
    "proof_critic_wave_audit": ("{phase_dir}/{plan_id}-PROOF-REDTEAM.md",),
    "wave_executor_plan_result": ("${SUMMARY_FILE}", "{phase_dir}/**"),
}

_EXPECTED_WORKFLOW_CHILD_GATE_STATUS_ROUTE_KEYS = {
    "phase_researcher_context_refresh": ("checkpoint", "blocked", "failed"),
    "plan_checker_review": ("checkpoint", "blocked", "failed"),
    "planner_initial_plan": ("checkpoint", "blocked", "failed"),
    "planner_revision": ("checkpoint", "blocked", "failed"),
    "proof_critic_wave_audit": ("checkpoint", "blocked", "failed"),
    "quick_executor_summary": ("checkpoint", "blocked", "failed"),
    "quick_planner_plan": ("checkpoint", "blocked", "failed"),
    "verify_work_gap_plan_checker": ("checkpoint", "blocked", "failed"),
    "verify_work_gap_planner": ("checkpoint", "blocked", "failed"),
    "verify_work_proof_critic": ("checkpoint", "blocked", "failed"),
    "verify_work_verifier_report": ("checkpoint", "blocked", "failed"),
    "wave_executor_plan_result": ("checkpoint", "blocked", "failed"),
}

_EXPECTED_WORKFLOW_AGGREGATE_CHILD_GATE = {
    "respond_to_referees_response_pair_current": {
        "source": "respond-to-referees/response-authoring.md",
        "required_child_gates": ("respond_to_referees_revision_section for every launched Group B section",),
        "expected_artifacts": (
            "every required revised section under ${PAPER_DIR}",
            "${RESPONSE_AUTHOR_PATH}",
            "${RESPONSE_REFEREE_PATH}",
        ),
        "validator_count": 3,
        "failure_route": "retry failed sections | main-context targeted revision | leave response pair incomplete",
    },
}

_EXECUTE_PHASE_PROFILE_CASES = (
    (
        "execute-phase/wave-return-checkpoint.md",
        "wave_executor_plan_result",
        {
            "id": "wave_executor_plan_result",
            "profile": "execute.executor_summary.v1",
            "artifact": "${SUMMARY_FILE}",
            "allowed_root": "{phase_dir}",
            "freshness_marker": "$EXECUTOR_HANDOFF_STARTED_AT",
        },
    ),
    (
        "execute-phase/proof-critic-dispatch.md",
        "proof_critic_wave_audit",
        {
            "id": "proof_critic_wave_audit",
            "profile": "execute.proof_critic_report.v1",
            "artifact": "{phase_dir}/{plan_id}-PROOF-REDTEAM.md",
            "allowed_root": "{phase_dir}",
            "freshness_marker": "$PROOF_HANDOFF_STARTED_AT",
        },
    ),
    (
        "execute-phase/verification-handoff.md",
        "post_execution_verifier",
        {
            "id": "post_execution_verifier",
            "profile": "execute.verification_report.v1",
            "artifact": "{phase_dir}/{phase_number}-VERIFICATION.md",
            "allowed_root": "{phase_dir}",
            "freshness_marker": "after $VERIFIER_HANDOFF_STARTED_AT",
        },
    ),
    (
        "execute-phase/gap-reverification.md",
        "gap_closure_reverification",
        {
            "id": "gap_closure_reverification",
            "profile": "execute.gap_reverification_report.v1",
            "artifact": "{phase_dir}/{phase_number}-VERIFICATION.md",
            "allowed_root": "{phase_dir}",
            "freshness_marker": "after $REVERIFY_HANDOFF_STARTED_AT",
        },
    ),
    (
        "execute-phase/consistency-check.md",
        "rapid_consistency_check",
        {
            "id": "rapid_consistency_check",
            "profile": "execute.consistency_report.v1",
            "artifact": "{phase_dir}/CONSISTENCY-CHECK.md",
            "allowed_root": "{phase_dir}",
            "freshness_marker": "after $CONSISTENCY_HANDOFF_STARTED_AT",
        },
    ),
)


def test_child_gate_tuple_renders_compact_yaml_with_inferred_return_profile() -> None:
    rendered = _gate_markdown(_planner_gate())

    payload = yaml.safe_load(rendered.removeprefix("```yaml\n").removesuffix("```\n"))
    child_gate = payload["child_gate"]

    assert child_gate["id"] == "planner_initial_plan"
    assert child_gate["role"] == "gpd-planner"
    assert child_gate["return_profile"] == "planner"
    assert child_gate["required_status"] == "completed"
    assert child_gate["expected_artifacts"] == [
        {
            "path": "${PHASE_DIR}/*-PLAN.md",
            "kind": "glob",
            "required": True,
            "must_be_named_in_files_written": True,
        }
    ]
    assert child_gate["allowed_roots"] == ["${PHASE_DIR}"]
    assert child_gate["freshness"] == {
        "marker": "$PLANNER_HANDOFF_STARTED_AT",
        "require_mtime_at_or_after_marker": True,
        "preexisting_artifacts": "recovery_evidence_only",
    }
    assert child_gate["applicator"] == {"command": "none", "require_passed_true": False}
    assert list(child_gate["failure_route"]) == [failure_class.value for failure_class in HandoffFailureClass]


def test_render_child_gate_markdown_round_trips_full_tuple_payload() -> None:
    gate = _renderer_gate()

    rendered = render_child_gate_markdown(gate)
    payload = yaml.safe_load(rendered.removeprefix("```yaml\n").removesuffix("```\n"))

    assert payload == {"child_gate": gate.to_payload()}
    assert parse_child_gate_markdown(rendered) == gate
    assert render_child_gate_markdown(payload) == rendered
    for key in (
        "expected_artifacts",
        "allowed_roots",
        "freshness",
        "validators",
        "applicator",
        "write_allowlist",
        "status_route",
        "failure_route",
    ):
        assert key in payload["child_gate"]


def test_render_child_gate_inline_summary_names_gate_anchors() -> None:
    summary = render_child_gate_inline_summary(_renderer_gate())

    assert "child_gate=renderer_gate" in summary
    assert "role=gpd-planner" in summary
    assert "required_status=completed" in summary
    assert "artifacts=GPD/plan.md[kind=path, required=true, files_written=true]" in summary
    assert "GPD/reports/*.md[kind=glob, required=false, files_written=false]" in summary
    assert "allowed_roots=GPD" in summary
    assert (
        "freshness=marker=$HANDOFF_STARTED_AT, "
        "mtime_at_or_after_marker=true, preexisting_artifacts=recovery_evidence_only"
    ) in summary
    assert "validators=readable, plan-contract" in summary
    assert "applicator=gpd --raw apply-return-updates GPD/plan.md require_passed_true=true" in summary
    assert "write_allowlist=GPD/plan.md, GPD/reports/*.md" in summary
    assert "status_route=checkpoint->present_checkpoint, blocked->surface_blocker" in summary
    assert "failure_route=return_missing->retry_once" in summary


def test_child_gate_tuple_from_payload_accepts_wrapped_payload_and_failure_class_strings() -> None:
    gate = child_gate_tuple_from_payload(
        {
            "child_gate": {
                "id": "verifier_gate",
                "role": "gpd-verifier",
                "return_profile": "verifier",
                "required_status": "completed",
                "failure_route": {
                    "return_missing": "retry_once",
                    "validator_failed": "revision_loop",
                },
            }
        }
    )

    assert gate.return_profile == "verifier"
    assert gate.failure_route == {
        HandoffFailureClass.RETURN_MISSING: "retry_once",
        HandoffFailureClass.VALIDATOR_FAILED: "revision_loop",
    }


def test_child_gate_tuple_accepts_compact_prompt_tuple_shape() -> None:
    gate = child_gate_tuple_from_payload(
        {
            "child_gate": {
                "id": "paper_section",
                "role": "gpd-paper-writer",
                "return_profile": "paper_writer",
                "required_status": "completed",
                "expected_artifacts": ["${PAPER_DIR}/intro.tex"],
                "allowed_roots": ["${PAPER_DIR}"],
                "freshness_marker": "after $SECTION_HANDOFF_STARTED_AT",
                "validators": ["gpd validate handoff-artifacts ..."],
                "applicator": "none",
                "failure_route": "stage-recovery-gate -> retry writer | stop",
                "allowed_write_paths": ["${PAPER_DIR}/intro.tex"],
            }
        }
    )

    assert gate.return_profile == "paper_writer"
    assert gate.expected_artifacts[0].path == "${PAPER_DIR}/intro.tex"
    assert gate.freshness is not None
    assert gate.freshness.marker == "$SECTION_HANDOFF_STARTED_AT"
    assert gate.applicator.command == "none"
    assert gate.write_allowlist == ("${PAPER_DIR}/intro.tex",)
    assert set(gate.failure_route) == set(HandoffFailureClass)


def test_child_gate_tuple_from_payload_preserves_raw_tuple_when_profiles_exist() -> None:
    expected = _workflow_child_gate("execute-phase/wave-return-checkpoint.md", "wave_executor_plan_result")
    raw_payload = expected.to_payload()

    assert "profile" not in raw_payload
    assert child_gate_tuple_from_payload(raw_payload) == expected
    assert child_gate_tuple_from_payload({"child_gate": raw_payload}) == expected


@pytest.mark.parametrize(("source", "gate_id", "profile_payload"), _EXECUTE_PHASE_PROFILE_CASES)
def test_execute_phase_child_gate_profiles_expand_to_current_effective_tuples(
    source: str,
    gate_id: str,
    profile_payload: dict[str, object],
) -> None:
    expected = _workflow_child_gate(source, gate_id)

    assert child_gate_tuple_from_payload(profile_payload) == expected
    assert child_gate_tuple_from_payload({"child_gate": profile_payload}) == expected


def test_execute_phase_child_gate_profile_aliases_expand_to_current_effective_tuples() -> None:
    aliases = {
        "wave_executor_plan_result": "execute_phase_executor_summary_v1",
        "proof_critic_wave_audit": "execute_phase_proof_critic_report_v1",
        "post_execution_verifier": "execute_phase_verification_report_v1",
        "gap_closure_reverification": "execute_phase_gap_reverification_report_v1",
        "rapid_consistency_check": "execute_phase_consistency_report_v1",
    }

    for source, gate_id, profile_payload in _EXECUTE_PHASE_PROFILE_CASES:
        payload = dict(profile_payload)
        payload["profile"] = aliases[gate_id]
        assert normalize_child_gate_profile_id(payload["profile"]) == normalize_child_gate_profile_id(
            profile_payload["profile"]
        )
        assert child_gate_tuple_from_payload(payload) == _workflow_child_gate(source, gate_id)


def test_child_gate_profile_payload_rejects_unknown_profile_and_owned_field_drift() -> None:
    payload = {
        "id": "post_execution_verifier",
        "profile": "execute.verification_report.v1",
        "artifact": "{phase_dir}/{phase_number}-VERIFICATION.md",
        "allowed_root": "{phase_dir}",
        "freshness_marker": "$VERIFIER_HANDOFF_STARTED_AT",
    }

    with pytest.raises(ValueError, match="unknown child_gate profile"):
        child_gate_tuple_from_payload({**payload, "profile": "execute.unknown_report.v1"})

    with pytest.raises(ValueError, match="requires return_profile"):
        child_gate_tuple_from_payload({**payload, "return_profile": "executor"})

    with pytest.raises(ValueError, match="owns status_route"):
        child_gate_tuple_from_payload({**payload, "status_route": {"checkpoint": "checkpoint_resume"}})

    invalid_roots_payload = dict(payload)
    invalid_roots_payload.pop("allowed_root")
    invalid_roots_payload["allowed_roots"] = ["{phase_dir}", "GPD"]
    with pytest.raises(ValueError, match="allowed_roots must contain exactly one root"):
        child_gate_tuple_from_payload(invalid_roots_payload)


def test_execute_phase_child_gate_profiles_preserve_status_route_applicator_and_write_policy() -> None:
    gates = {
        gate_id: child_gate_tuple_from_payload(profile_payload)
        for _, gate_id, profile_payload in _EXECUTE_PHASE_PROFILE_CASES
    }

    assert tuple(gates["wave_executor_plan_result"].status_route) == ("checkpoint", "blocked", "failed")
    assert tuple(gates["proof_critic_wave_audit"].status_route) == ("checkpoint", "blocked", "failed")
    assert gates["post_execution_verifier"].status_route == {}
    assert gates["gap_closure_reverification"].status_route == {}
    assert gates["rapid_consistency_check"].status_route == {}

    assert gates["wave_executor_plan_result"].applicator.command == "gpd --raw apply-return-updates ${SUMMARY_FILE}"
    assert gates["wave_executor_plan_result"].applicator.require_passed_true is True
    assert gates["proof_critic_wave_audit"].applicator.command == "none"
    assert gates["rapid_consistency_check"].applicator.command == "none"
    assert gates["post_execution_verifier"].applicator.command.startswith("none; closeout/update_roadmap")
    assert gates["gap_closure_reverification"].applicator.command.startswith("none; closeout/update_roadmap")

    assert gates["wave_executor_plan_result"].write_allowlist == ("${SUMMARY_FILE}", "{phase_dir}/**")
    assert gates["proof_critic_wave_audit"].write_allowlist == ("{phase_dir}/{plan_id}-PROOF-REDTEAM.md",)
    assert gates["post_execution_verifier"].write_allowlist == ()
    assert gates["gap_closure_reverification"].write_allowlist == ()
    assert gates["rapid_consistency_check"].write_allowlist == ()


def test_child_gate_profile_list_payload_is_detached_and_defaults_validate() -> None:
    registry = list_child_gate_profiles()
    assert sorted(registry["profiles"]) == [
        "execute.consistency_report.v1",
        "execute.executor_summary.v1",
        "execute.gap_reverification_report.v1",
        "execute.proof_critic_report.v1",
        "execute.verification_report.v1",
    ]
    registry["profiles"]["execute.executor_summary.v1"]["role"] = "mutated"
    assert list_child_gate_profiles()["profiles"]["execute.executor_summary.v1"]["role"] == "gpd-executor"

    for _, _, profile_payload in _EXECUTE_PHASE_PROFILE_CASES:
        expanded = expand_child_gate_profile_payload(profile_payload)
        gate = child_gate_tuple_from_payload(expanded)
        assert gate.required_status == "completed"
        assert gate.expected_artifacts[0].must_be_named_in_files_written is True
        assert gate.freshness is not None
        assert gate.freshness.require_mtime_at_or_after_marker is True


def test_aggregate_child_gate_tuple_accepts_wrapped_payload_and_round_trips_fields() -> None:
    gate = aggregate_child_gate_tuple_from_payload(
        {
            "aggregate_child_gate": {
                "id": "response_pair_current",
                "required_child_gates": ["revision_section for every launched section"],
                "expected_artifacts": ["${RESPONSE_AUTHOR_PATH}", "${RESPONSE_REFEREE_PATH}"],
                "validators": ["mirrored artifacts exist on disk"],
                "failure_route": "retry failed sections | leave response pair incomplete",
            }
        }
    )

    assert gate.required_child_gates == ("revision_section for every launched section",)
    assert gate.expected_artifacts == ("${RESPONSE_AUTHOR_PATH}", "${RESPONSE_REFEREE_PATH}")
    assert gate.validators == ("mirrored artifacts exist on disk",)
    assert gate.to_payload() == {
        "id": "response_pair_current",
        "required_child_gates": ["revision_section for every launched section"],
        "expected_artifacts": ["${RESPONSE_AUTHOR_PATH}", "${RESPONSE_REFEREE_PATH}"],
        "validators": ["mirrored artifacts exist on disk"],
        "failure_route": "retry failed sections | leave response pair incomplete",
    }


def test_execute_phase_split_child_gates_use_canonical_tuple_fields() -> None:
    proof_text = (WORKFLOWS_DIR / "execute-phase/proof-critic-dispatch.md").read_text(encoding="utf-8")
    return_text = (WORKFLOWS_DIR / "execute-phase/wave-return-checkpoint.md").read_text(encoding="utf-8")
    proof_gate = _workflow_child_gate("execute-phase/proof-critic-dispatch.md", "proof_critic_wave_audit")
    executor_gate = _workflow_child_gate("execute-phase/wave-return-checkpoint.md", "wave_executor_plan_result")

    assert "freshness_marker" not in proof_text
    assert "freshness_marker" not in return_text
    assert "allowed_write_paths" not in proof_text
    assert "allowed_write_paths" not in return_text

    assert proof_gate.expected_artifacts[0].path == "{phase_dir}/{plan_id}-PROOF-REDTEAM.md"
    assert proof_gate.expected_artifacts[0].must_be_named_in_files_written is True
    assert proof_gate.freshness is not None
    assert proof_gate.freshness.marker == "$PROOF_HANDOFF_STARTED_AT"
    assert proof_gate.write_allowlist == ("{phase_dir}/{plan_id}-PROOF-REDTEAM.md",)
    assert proof_gate.status_route["checkpoint"] == "checkpoint_resume"

    assert executor_gate.expected_artifacts[0].path == "${SUMMARY_FILE}"
    assert executor_gate.expected_artifacts[0].must_be_named_in_files_written is True
    assert executor_gate.freshness is not None
    assert executor_gate.freshness.marker == "$EXECUTOR_HANDOFF_STARTED_AT"
    assert executor_gate.applicator.require_passed_true is True
    assert executor_gate.write_allowlist == ("${SUMMARY_FILE}", "{phase_dir}/**")
    assert executor_gate.status_route["checkpoint"] == "checkpoint_resume"


def test_parse_child_gate_markdown_accepts_raw_and_fenced_payloads() -> None:
    raw = """
id: planner_initial_plan
role: gpd-planner
required_status: completed
"""
    fenced = f"```yaml\nchild_gate:\n  {raw.strip().replace(chr(10), chr(10) + '  ')}\n```\n"

    assert parse_child_gate_markdown(raw).return_profile == "planner"
    assert parse_child_gate_markdown(fenced).return_profile == "planner"


def test_parse_aggregate_child_gate_markdown_accepts_raw_and_fenced_payloads() -> None:
    raw = """
id: response_pair_current
required_child_gates:
  - revision_section
expected_artifacts:
  - ${RESPONSE_AUTHOR_PATH}
validators:
  - mirrored artifacts exist
failure_route: retry failed sections
"""
    fenced = f"```yaml\naggregate_child_gate:\n  {raw.strip().replace(chr(10), chr(10) + '  ')}\n```\n"

    assert parse_aggregate_child_gate_markdown(raw).id == "response_pair_current"
    assert parse_aggregate_child_gate_markdown(fenced).required_child_gates == ("revision_section",)


def test_child_gate_tuple_rejects_unknown_profile_status_route_and_invalid_freshness() -> None:
    with pytest.raises(ValueError, match="unknown gpd_return role profile"):
        ChildGateTuple(id="bad", role="gpd-unknown", required_status="completed")

    with pytest.raises(ValueError, match="unknown gpd_return status"):
        ChildGateTuple(id="bad", role="gpd-planner", required_status="done")

    with pytest.raises(ValueError, match="unknown gpd_return status"):
        ChildGateTuple(id="bad", role="gpd-planner", status_route={"waiting": "pause"})

    with pytest.raises(ValueError, match="unknown handoff failure class"):
        ChildGateTuple(
            id="bad",
            role="gpd-planner",
            failure_route={"not_a_failure": "retry"},
        )

    with pytest.raises(ValueError, match="freshness marker is required"):
        ChildGateFreshness(require_mtime_at_or_after_marker=True)


def test_aggregate_child_gate_tuple_rejects_empty_required_fields() -> None:
    with pytest.raises(ValueError, match="required_child_gates must include at least one item"):
        AggregateChildGateTuple(
            id="bad",
            required_child_gates=[],
            expected_artifacts=["${RESPONSE_AUTHOR_PATH}"],
            failure_route="retry",
        )

    with pytest.raises(ValueError, match="expected_artifacts must include at least one item"):
        AggregateChildGateTuple(
            id="bad",
            required_child_gates=["revision_section"],
            expected_artifacts=[],
            failure_route="retry",
        )


def test_workflow_child_gate_yaml_blocks_parse_as_child_gate_tuples() -> None:
    gates = _workflow_child_gates()

    assert len(gates) == len(_expected_workflow_child_gate_keys())
    assert sorted((item.source, item.gate.id) for item in gates) == sorted(_expected_workflow_child_gate_keys())


def test_workflow_child_gate_inventory_preserves_tuple_contract_fields() -> None:
    gates = _workflow_child_gates()
    by_key = {(item.source, item.gate.id): item for item in gates}

    assert len(by_key) == len(gates)
    assert sorted(by_key) == sorted(_expected_workflow_child_gate_keys())
    for item in gates:
        gate = item.gate
        gate_id = gate.id
        expected_role, expected_profile = _EXPECTED_WORKFLOW_CHILD_GATE_ROLE_PROFILE[gate_id]
        expected_marker = _EXPECTED_WORKFLOW_CHILD_GATE_FRESHNESS_MARKERS[gate_id]
        expected_applicator = _EXPECTED_WORKFLOW_CHILD_GATE_APPLICATORS[gate_id]

        assert item.source in _expected_sources_for_gate(gate_id)
        assert gate.role == expected_role
        assert gate.return_profile == expected_profile
        assert gate.required_status == "completed"
        assert (
            tuple(
                (artifact.path, artifact.kind, artifact.required, artifact.must_be_named_in_files_written)
                for artifact in gate.expected_artifacts
            )
            == _EXPECTED_WORKFLOW_CHILD_GATE_ARTIFACTS[gate_id]
        )
        assert gate.allowed_roots == _EXPECTED_WORKFLOW_CHILD_GATE_ROOTS[gate_id]
        if expected_marker is None:
            assert gate.freshness is None
        else:
            assert gate.freshness is not None
            assert gate.freshness.marker == expected_marker
            assert gate.freshness.require_mtime_at_or_after_marker is True
            assert gate.freshness.preexisting_artifacts == "recovery_evidence_only"
        assert len(gate.validators) == _EXPECTED_WORKFLOW_CHILD_GATE_VALIDATOR_COUNTS[gate_id]
        assert all(validator.strip() for validator in gate.validators)
        assert (gate.applicator.command, gate.applicator.require_passed_true) == expected_applicator
        assert gate.write_allowlist == _EXPECTED_WORKFLOW_CHILD_GATE_WRITE_ALLOWLIST.get(gate_id, ())
        assert tuple(gate.status_route) == _EXPECTED_WORKFLOW_CHILD_GATE_STATUS_ROUTE_KEYS.get(gate_id, ())
        assert set(gate.failure_route) == set(HandoffFailureClass)
        assert all(route.strip() for route in gate.failure_route.values())
        assert all(route.strip() for route in gate.status_route.values())


def test_workflow_aggregate_child_gate_yaml_blocks_parse_as_separate_aggregate_tuples() -> None:
    gates = _workflow_aggregate_child_gates()

    assert len(gates) == len(_EXPECTED_WORKFLOW_AGGREGATE_CHILD_GATE)
    assert sorted(item.gate.id for item in gates) == sorted(_EXPECTED_WORKFLOW_AGGREGATE_CHILD_GATE)


def test_workflow_aggregate_child_gate_inventory_preserves_tuple_contract_fields() -> None:
    gates = _workflow_aggregate_child_gates()

    for item in gates:
        gate = item.gate
        expected = _EXPECTED_WORKFLOW_AGGREGATE_CHILD_GATE[gate.id]

        assert item.source == expected["source"]
        assert gate.required_child_gates == expected["required_child_gates"]
        assert gate.expected_artifacts == expected["expected_artifacts"]
        assert len(gate.validators) == expected["validator_count"]
        assert all(validator.strip() for validator in gate.validators)
        assert gate.failure_route == expected["failure_route"]
