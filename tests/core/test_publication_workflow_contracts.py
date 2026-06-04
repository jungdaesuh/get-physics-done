from __future__ import annotations

import re
from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
WRITE_PAPER_STAGE_DIR = WORKFLOWS_DIR / "write-paper"


def _assert_all_present(text: str, fragments: tuple[str, ...]) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    assert missing == []


def _assert_all_absent(text: str, fragments: tuple[str, ...]) -> None:
    present = [fragment for fragment in fragments if fragment in text]
    assert present == []


def _read_write_paper_staged_authorities() -> str:
    stage_names = (
        "paper-bootstrap.md",
        "outline-scaffold.md",
        "authoring.md",
        "consistency-references.md",
        "publication-review-finalization.md",
    )
    return "\n\n".join((WRITE_PAPER_STAGE_DIR / name).read_text(encoding="utf-8") for name in stage_names)


def test_write_paper_balanced_mode_keeps_outline_as_working_draft_and_threads_mode_context() -> None:
    workflow = _read_write_paper_staged_authorities()
    bootstrap_field_line = next(
        line for line in workflow.splitlines() if line.startswith("Apply `PAPER_BOOTSTRAP_INIT")
    )

    _assert_all_present(
        bootstrap_field_line,
        (
            "PAPER_BOOTSTRAP_INIT.staged_loading.field_access_instruction",
            "before",
        ),
    )
    _assert_all_absent(
        bootstrap_field_line,
        ("selected_publication_root", "selected_review_root"),
    )
    _assert_all_present(
        workflow,
        (
            "If `autonomy=balanced`, treat the outline as a working draft",
            'WRITE_PAPER_ARGUMENTS="${ARGUMENTS:-}"',
            'gpd --raw init write-paper --stage paper_bootstrap -- "$WRITE_PAPER_ARGUMENTS"',
            'WRITE_PAPER_ARGUMENTS=$(echo "$INIT" | gpd json get .write_paper_argument_input',
            'PAPER_DIR=$(echo "$INIT" | gpd json get .publication_bootstrap_root',
            'MANUSCRIPT_BASENAME="${MANUSCRIPT_ENTRYPOINT##*/}"',
        ),
    )
    for stage in (
        "outline_and_scaffold",
        "figure_and_section_authoring",
        "consistency_and_references",
        "publication_review",
    ):
        assert f"gpd --raw init write-paper --stage {stage}" in workflow
    _assert_all_present(
        workflow,
        (
            "`--intake path/to/write-paper-authoring-input.json`",
            "For `external_authoring_intake`, use the strict command preflight's managed subject handoff",
            "If `autonomy=supervised`, present the outline for approval before proceeding. "
            "If `autonomy=balanced`, treat the outline as a working draft",
            "<autonomy_mode>{AUTONOMY}</autonomy_mode>",
            "<research_mode>{RESEARCH_MODE}</research_mode>",
        ),
    )
    _assert_all_absent(workflow, ("Present outline for approval before proceeding.",))
    assert workflow.count("<autonomy_mode>{AUTONOMY}</autonomy_mode>") >= 3
    assert workflow.count("<research_mode>{RESEARCH_MODE}</research_mode>") >= 3
    _assert_all_present(
        workflow,
        (
            "Treat the emitted `.tex` file as the success artifact gate\nfor each section only after the tuple passes.",
            'id: "write_paper_bibliographer"',
            "Always list `${PAPER_DIR}/CITATION-AUDIT.md` and `GPD/references-status.json` in `gpd_return.files_written`; list `{ACTIVE_BIBLIOGRAPHY_PATH}` only when the bibliography file changed.",
            "Confirm `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`",
            "exists after the refresh before proceeding to reproducibility or strict review.",
            'id: "write_paper_section_writer"',
            'id: "write_paper_response_pair"',
            "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md",
            "Embedded `write-paper` review parity for the bounded external-authoring lane is deferred",
            "route the user to standalone `gpd:peer-review`",
            "do not recommend `gpd:arxiv-submission` directly from this lane.",
        ),
    )


def test_respond_to_referees_balanced_mode_does_not_force_parse_confirmation() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "respond-to-referees")

    _assert_all_present(
        workflow,
        (
            "research_mode",
            'RESEARCH_MODE=$(echo "$INIT" | gpd json get .research_mode --default balanced)',
            "This workflow is project-aware: it may revise the active manuscript from the current GPD project or an explicit manuscript subject",
            "Preferred explicit intake: `gpd:respond-to-referees --manuscript path/to/main.tex --report reviews/ref1.md --report reviews/ref2.md`",
            "Treat a bare positional path as a referee-report source only.",
            "Present the parsed structure. Ask for explicit user confirmation only in supervised mode or when the report source is ambiguous; "
            "balanced mode should treat the parse as working context",
            "<autonomy_mode>{AUTONOMY}</autonomy_mode>",
            "<research_mode>{RESEARCH_MODE}</research_mode>",
            "Treat `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}` as the response\nsuccess gate.",
            "Use `selected_publication_root` / `selected_review_root`.",
            'id: "respond_to_referees_revision_section"',
            "aggregate_child_gate:",
            "Confirm the refreshed\nJSON artifact exists before treating the round as complete.",
            "canonical GPD-authored response artifacts live under the selected publication/review roots",
        ),
    )
    _assert_all_absent(workflow, ("Present the parsed structure for user confirmation:",))


def test_peer_review_stage_six_requires_report_artifacts_and_threads_mode_context() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    _assert_all_present(
        workflow,
        (
            "BOOTSTRAP_INIT.staged_loading.field_access_instruction",
            "peer-review-stage-manifest.json",
            'REVIEW_TARGET=$(echo "$INIT" | gpd json get .review_target_input --default "")',
            'RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)',
            "<autonomy_mode>{AUTONOMY}</autonomy_mode>",
            "<research_mode>{RESEARCH_MODE}</research_mode>",
            "Stage 6 writes:",
        ),
    )
    _assert_all_present(
        workflow,
        (
            "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md",
            "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex",
            "not a substitute for same-round proof-redteam clearance plus strict\nreferee-decision validation",
        ),
    )
    assert re.search(
        r"without same-round\s+`\$\{REVIEW_ROOT\}/PROOF-REDTEAM\{round_suffix\}\.md` plus strict decision validation",
        workflow,
    )


def test_peer_review_finalize_uses_latest_payload_artifacts_before_path_fallbacks() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    _assert_all_present(
        workflow,
        (
            'REPORT_PATH=$(echo "$INIT" | gpd json get .latest_referee_report_md --default "")',
            'REPORT_TEX_PATH=$(echo "$INIT" | gpd json get .latest_referee_report_tex --default "")',
            'LATEST_RESPONSE_SUFFIX=$(echo "$INIT" | gpd json get .latest_response_round_suffix --default "")',
            'LATEST_AUTHOR_RESPONSE=$(echo "$INIT" | gpd json get .latest_author_response --default "")',
            'LATEST_REFEREE_RESPONSE=$(echo "$INIT" | gpd json get .latest_referee_response --default "")',
            "Treat `latest_referee_report_md` and\n`latest_referee_report_tex`",
            "latest_author_response` when set",
            "latest_referee_response` when set",
        ),
    )


def test_peer_review_panel_child_gates_are_tuple_shaped_and_stage_owned() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    for gate_id in (
        "peer_review_stage1_reader",
        "peer_review_stage2_literature",
        "peer_review_stage3_math",
        "peer_review_proof_redteam",
        "peer_review_stage4_physics",
        "peer_review_stage5_significance",
        "peer_review_stage6_referee",
    ):
        assert f"{gate_id}" in workflow
    assert re.search(r"Stage identity comes from tuple role", workflow)
    assert re.search(r"never trust a stage\s+label inside `gpd_return`", workflow)
    _assert_all_present(
        workflow,
        (
            "gpd validate review-claim-index ${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
            "gpd validate proof-redteam ${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md",
            "favorable_decisions_require_same_round_status_passed",
        ),
    )


def test_paper_writer_prompt_supports_bounded_external_authoring_without_workspace_mining() -> None:
    agent = (AGENTS_DIR / "gpd-paper-writer.md").read_text(encoding="utf-8")

    _assert_all_present(
        agent,
        (
            "for bounded external authoring, an explicit intake-manifest handoff",
            "When the orchestrator says this is `external_authoring_intake`",
            "the only supported non-project intake is explicit `--intake path/to/write-paper-authoring-input.json`",
            "Do not scan `GPD/phases/*`, `GPD/milestones/*`, `GPD/STATE.md`, or unrelated folders to fill gaps.",
            "missing evidence bindings are hard blocks",
        ),
    )


def test_peer_review_workflow_retires_finished_handoffs_and_clears_transient_state() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    _assert_all_present(workflow, ("{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md",))
    assert "Launching the six-stage review panel" in workflow
    assert re.search(r"checkpoint continuation,[\s\S]{0,80}sequential fallback", workflow)
    assert re.search(
        r"downstream work restarts only from persisted artifacts plus declared\s+carry-forward inputs", workflow
    )


def test_peer_review_workflow_requires_barriers_and_cleanup_before_downstream_stage_spawns() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    assert re.search(
        r"Run Stage 2, Stage 3, and proof critique in parallel when the runtime supports\s+it; otherwise run literature, math, proof\. Treat them as one barriered wave",
        workflow,
    )
    assert re.search(
        r"Before Stage 4, every launched\s+child must have a typed return, every promised artifact must exist and validate,\s+and downstream work restarts only from persisted artifacts plus declared\s+carry-forward inputs",
        workflow,
    )
    assert "Retry once from the same persisted inputs; if still\ninvalid, STOP before Stage 5." in workflow
    assert re.search(
        r"After validation, Stage 6 must begin from persisted stage artifacts and declared\s+carry-forward inputs only",
        workflow,
    )
    assert re.search(
        r"Apply the `peer_review_stage6_referee` tuple and publication stage-recovery gate\s+before classifying outcome as recovery-eligible, upstream-blocked, or complete",
        workflow,
    )


def test_peer_review_stage_six_limits_writes_to_stage_six_owned_artifacts() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    _assert_all_present(
        workflow,
        (
            "Stage 6 writes:",
            "Writable scope is limited to Stage 6-owned report `.md`/`.tex`, ledger,\ndecision, and optional consistency report.",
            "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
            "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
            "${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md",
            "Do not modify\n`${REVIEW_ROOT}/CLAIMS{round_suffix}.json`, any `${REVIEW_ROOT}/STAGE-*.json`,\nor `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md`.",
            "any upstream\npath is a failed handoff",
            "peer_review_stage6_referee",
            "`gpd_return.files_written` stays within the Stage 6 write allowlist",
        ),
    )


def test_peer_review_stage_six_fails_back_to_earliest_upstream_stage_on_inconsistent_inputs() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "peer-review")

    assert re.search(
        r"return `gpd_return.status:\s+blocked` and hand failure back instead of repairing it inside Stage 6",
        workflow,
    )
    _assert_all_present(
        workflow,
        (
            "STOP fail-closed and rerun the earliest failing\nupstream stage.",
            "Upstream fail-back table:",
            "`CLAIMS{round_suffix}.json` or `STAGE-reader{round_suffix}.json` -> rerun Stage 1",
            "`STAGE-math{round_suffix}.json` or `PROOF-REDTEAM{round_suffix}.md` -> rerun Stage 3",
            "`STAGE-interestingness{round_suffix}.json` -> rerun Stage 5",
            "earliest failing\nupstream stage",
        ),
    )
