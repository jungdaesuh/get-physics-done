from __future__ import annotations

import re
from pathlib import Path

import pytest

from gpd.adapters.install_utils import expand_at_includes
from gpd.core.public_surface_contract import resume_authority_fields
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.doc_surface_contracts import resume_authority_public_vocabulary_intro, resume_backend_only_fields
from tests.lifecycle_contract_test_support import (
    assert_forbidden_contract as _assert_forbidden,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import assert_semantic_contract as _assert_semantic
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
ORCHESTRATION_REFS_DIR = REPO_ROOT / "src/gpd/specs/references/orchestration"
BLOCKED_LIFECYCLE_STOP_PROHIBITION = (
    "Do not plan, execute, verify, fingerprint, align, or pass `project_contract` to subagents"
)


def _workflow_text(name: str) -> str:
    return workflow_authority_text(WORKFLOWS_DIR, name)


def test_contract_authority_gate_reference_defines_shared_boundary() -> None:
    reference = (ORCHESTRATION_REFS_DIR / "contract-authority-gate.md").read_text(encoding="utf-8")

    _assert_machine(reference, "contract authority gate authoritative field", "project_contract_gate.authoritative")
    _assert_semantic(
        reference,
        "contract authority gate diagnostic-only lifecycle boundary",
        "diagnostic context",
        "not planning, execution, verification",
        "lifecycle preflight",
        "stop fail-closed",
        "do not infer approved scope",
        "local workflow still owns",
        "artifacts",
        "validators",
        "failure route",
    )
    _assert_machine(
        reference,
        "contract authority gate blocked lifecycle markers",
        "## Blocked Lifecycle Stop Phrase",
        BLOCKED_LIFECYCLE_STOP_PROHIBITION,
        "references/orchestration/stage-stop-envelope.md",
    )
    _assert_semantic(
        reference,
        "contract authority gate owns repair rerun command",
        "owning workflow",
        "rerun command",
        "after repair",
    )


def _assert_contract_gate_stop_tuple(
    workflow: str,
    *,
    workflow_id: str,
    stage_id: str,
    after_repair: str,
    triggers: tuple[str, ...],
) -> None:
    stop_tuple = next(
        line
        for line in workflow.splitlines()
        if "contract_gate_stop:" in line and f"workflow={workflow_id}" in line
    )
    _assert_machine(
        stop_tuple,
        f"{workflow_id}:{stage_id} contract gate stop tuple",
        f"stage={stage_id}",
        "status=blocked",
        "checkpoint=contract_gate",
        "primary=gpd:sync-state|gpd:new-project",
        f"rerun={after_repair}",
        "secondary=gpd:suggest-next",
    )
    for trigger in triggers:
        assert trigger in stop_tuple or trigger in workflow


def test_owned_contract_visibility_workflows_load_shared_authority_gate_once() -> None:
    include = "`{GPD_INSTALL_DIR}/references/orchestration/contract-authority-gate.md`"
    for workflow_name in (
        "audit-milestone.md",
        "new-milestone.md",
        "literature-review.md",
        "map-research.md",
        "compare-results.md",
        "compare-experiment.md",
    ):
        assert _workflow_text(workflow_name).count(include) == 1


@pytest.mark.parametrize(
    ("workflow_name", "surface_marker", "expected_token", "authoritative_marker", "stage_id"),
    [
        ("plan-phase.md", None, "project_contract_gate", "project_contract_gate.authoritative", "phase_bootstrap"),
        ("execute-phase.md", None, "project_contract_gate", "non-authoritative `project_contract_gate`", "phase_bootstrap"),
        ("execute-plan.md", None, "project_contract_gate", "project_contract_gate.authoritative", "execute-phase:phase_bootstrap"),
        ("compare-experiment.md", "Parse JSON for:", "project_contract_gate", "project_contract_gate.authoritative", None),
        ("compare-results.md", "Parse JSON for:", "project_contract_gate", "project_contract_gate.authoritative", None),
        ("new-project.md", None, "project_contract_gate", "project_contract_gate.authoritative", "scope_intake"),
        ("progress.md", "Extract from init JSON:", "project_contract_gate", "project_contract_gate.authoritative", None),
        ("audit-milestone.md", "Extract from init JSON:", "project_contract_gate", "project_contract_gate.authoritative", None),
        (
            "resume-work.md",
            "- **Availability and contract authority:**",
            "project_contract_gate",
            "project_contract_gate.authoritative",
            None,
        ),
        ("write-paper.md", None, "project_contract_gate", "project_contract_gate.authoritative", "write-paper:paper_bootstrap"),
        ("respond-to-referees.md", None, "project_contract_gate", "project_contract_gate.authoritative", "bootstrap"),
        ("peer-review.md", None, "project_contract_gate", "project_contract_gate.authoritative", "bootstrap"),
    ],
)
def test_contract_gate_is_visible_before_authoritative_use(
    workflow_name: str,
    surface_marker: str | None,
    expected_token: str,
    authoritative_marker: str,
    stage_id: str | None,
) -> None:
    workflow = _workflow_text(workflow_name)
    surface_line = (
        _stage_visibility_line(workflow, _manifest_stage_id(stage_id))
        if stage_id is not None
        else next(line for line in workflow.splitlines() if surface_marker and surface_marker in line)
    )

    if stage_id is None:
        _assert_machine(surface_line, f"{workflow_name} contract gate token", expected_token)
    else:
        workflow_id, manifest_stage_id = _manifest_ref(workflow_name, stage_id)
        assert expected_token in load_workflow_stage_manifest(workflow_id).stage(manifest_stage_id).required_init_fields
    assert workflow.index(surface_line) < workflow.index(authoritative_marker)


def _stage_visibility_line(workflow: str, stage_id: str) -> str:
    return next(line for line in workflow.splitlines() if f"`{stage_id}`" in line or f"--stage {stage_id}" in line)


def _manifest_ref(workflow_name: str, stage_id: str) -> tuple[str, str]:
    if ":" in stage_id:
        workflow_id, manifest_stage_id = stage_id.split(":", 1)
        return workflow_id, manifest_stage_id
    return workflow_name.removesuffix(".md"), stage_id


def _manifest_stage_id(stage_id: str) -> str:
    return stage_id.split(":", 1)[-1]


@pytest.mark.parametrize(
    ("workflow_id", "stage_id"),
    [
        ("quick", "task_bootstrap"),
        ("literature-review", "review_bootstrap"),
        ("new-milestone", "milestone_bootstrap"),
        ("map-research", "map_bootstrap"),
    ],
)
def test_manifest_owned_contract_gate_is_visible_before_authoritative_use(
    workflow_id: str,
    stage_id: str,
) -> None:
    workflow = _workflow_text(f"{workflow_id}.md")
    manifest = load_workflow_stage_manifest(workflow_id)
    stage_line = _stage_visibility_line(workflow, stage_id)

    assert "project_contract_gate" in manifest.stage(stage_id).required_init_fields
    assert workflow.index(stage_line) < workflow.index("project_contract_gate.authoritative")


def test_literature_review_workflow_surfaces_contract_gate_before_deferred_reference_artifacts() -> None:
    workflow = _workflow_text("literature-review.md")
    manifest = load_workflow_stage_manifest("literature-review")
    surface_line = _stage_visibility_line(workflow, "review_bootstrap")

    assert "project_contract_gate" in manifest.stage("review_bootstrap").required_init_fields
    assert workflow.index(surface_line) < workflow.index("project_contract_gate.authoritative")
    deferred_reference_marker = "Do not use `reference_artifact_files` or `reference_artifacts_content` yet."
    assert workflow.index(surface_line) < workflow.index(deferred_reference_marker)


@pytest.mark.parametrize(
    (
        "workflow_name",
        "workflow_id",
        "stage_id",
        "after_repair",
        "triggers",
        "gate_command",
        "first_forbidden_marker",
        "stop_line",
    ),
    [
        (
            "plan-phase.md",
            "plan-phase",
            "phase_bootstrap",
            "gpd:plan-phase {PHASE}",
            (
                "project_contract_load_info.status starts with blocked",
                "project_contract is empty or null",
                "project_contract_validation.valid is false",
                "project_contract_gate.authoritative is not true",
            ),
            "gpd --raw validate lifecycle-contract-gate plan-phase",
            "### Spawn gpd-phase-researcher",
            "project_contract_gate.authoritative is not true",
        ),
        (
            "execute-phase.md",
            "execute-phase",
            "phase_bootstrap",
            "gpd:execute-phase ${PHASE_ARG}",
            (
                "blocked contract load",
                "invalid contract validation",
                "non-authoritative `project_contract_gate`",
            ),
            "gpd --raw validate lifecycle-contract-gate execute-phase",
            '<step name="handle_branching">',
            "non-authoritative `project_contract_gate`",
        ),
        (
            "verify-work.md",
            "verify-work",
            "session_router",
            "gpd:verify-work ${PHASE_ARG}",
            (
                "contract load is blocked",
                "validation is invalid",
                "`project_contract_gate.authoritative` is not true",
            ),
            "gpd --raw validate lifecycle-contract-gate verify-work",
            "gpd-check-proof",
            "`project_contract_gate.authoritative` is not true",
        ),
    ],
)
def test_lifecycle_workflows_stop_on_non_authoritative_project_contract_gate(
    workflow_name: str,
    workflow_id: str,
    stage_id: str,
    after_repair: str,
    triggers: tuple[str, ...],
    gate_command: str,
    first_forbidden_marker: str,
    stop_line: str,
) -> None:
    workflow = _workflow_text(workflow_name)

    _assert_machine(workflow, f"{workflow_id} lifecycle stop line", stop_line)
    _assert_forbidden(workflow, f"{workflow_id} no raw blocked lifecycle prohibition prose", BLOCKED_LIFECYCLE_STOP_PROHIBITION)
    _assert_contract_gate_stop_tuple(
        workflow,
        workflow_id=workflow_id,
        stage_id=stage_id,
        after_repair=after_repair,
        triggers=triggers,
    )
    _assert_machine(workflow, f"{workflow_id} lifecycle gate command", gate_command)
    assert workflow.index(stop_line) < workflow.index(first_forbidden_marker)
    assert workflow.index(gate_command) < workflow.index(first_forbidden_marker)


def test_plan_phase_dirty_gate_stops_before_contract_and_authoring_surfaces() -> None:
    workflow = _workflow_text("plan-phase.md")

    _assert_machine(
        workflow,
        "plan-phase dirty gate and planner authoring markers",
        "**Dirty worktree safety gate:**",
        "If it is dirty, halt before planning",
        "**If `project_contract_load_info.status` starts with `blocked`",
        'INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)',
    )

    dirty_gate = workflow.index("**Dirty worktree safety gate:**")
    dirty_stop_marker = "If it is dirty, halt before planning"
    dirty_stop = workflow.index(dirty_stop_marker)
    contract_stop = workflow.index("**If `project_contract_load_info.status` starts with `blocked`")
    first_authoring_reload = workflow.index('INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)')

    _assert_semantic(
        workflow,
        "plan-phase dirty gate stops before hiding user work",
        "inspect only the project worktree",
        "show dirty paths",
        "git status --short",
        "gpd commit",
        "project-local cleanup path",
        "never stashes",
        "resets",
        "cleans",
        "overwrites",
        "hides user work",
    )
    assert dirty_gate < dirty_stop < contract_stop < first_authoring_reload


def test_plan_phase_missing_contract_gate_blocks_scope_substitution_and_authoring() -> None:
    workflow = _workflow_text("plan-phase.md")

    _assert_machine(
        workflow,
        "plan-phase missing contract gate markers",
        "**If `project_contract` is empty or null:**",
        "**If `project_contract_gate.authoritative` is not true:**",
        "LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate plan-phase",
        'INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)',
    )

    missing_contract_stop = workflow.index("**If `project_contract` is empty or null:**")
    authoritative_gate_stop = workflow.index("**If `project_contract_gate.authoritative` is not true:**")
    lifecycle_gate = workflow.index("LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate plan-phase")
    first_authoring_reload = workflow.index('INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)')

    _assert_semantic(
        workflow,
        "plan-phase missing contract cannot infer scope from roadmap",
        "approved scoping contract",
        "GPD/state.json",
        "do not infer phase scope",
        "ROADMAP.md",
        "REQUIREMENTS.md",
    )
    _assert_contract_gate_stop_tuple(
        workflow,
        workflow_id="plan-phase",
        stage_id="phase_bootstrap",
        after_repair="gpd:plan-phase {PHASE}",
        triggers=(
            "project_contract_load_info.status starts with blocked",
            "project_contract is empty or null",
            "project_contract_validation.valid is false",
            "project_contract_gate.authoritative is not true",
        ),
    )
    _assert_forbidden(workflow, "plan-phase no raw blocked lifecycle prohibition prose", BLOCKED_LIFECYCLE_STOP_PROHIBITION)
    assert missing_contract_stop < authoritative_gate_stop < lifecycle_gate < first_authoring_reload


def test_write_paper_surfaces_manuscript_reference_status_before_using_it() -> None:
    workflow = _workflow_text("write-paper.md")
    surface_line = next(
        line for line in workflow.splitlines() if "PAPER_BOOTSTRAP_INIT.staged_loading.field_access_instruction" in line
    )
    gate_line = next(line for line in workflow.splitlines() if "Keep `project_contract_gate`" in line)
    status_line = next(line for line in workflow.splitlines() if "Use derived manuscript review statuses from init" in line)

    _assert_semantic(
        surface_line,
        "write-paper manifest owns bootstrap field access",
        "staged_loading.field_access_instruction",
    )
    _assert_forbidden(gate_line, "write-paper bootstrap surface no selected root use", "selected_publication_root")
    assert workflow.index(surface_line) <= workflow.index(gate_line) < workflow.index(status_line)
    assert workflow.index(status_line) < workflow.index("source ordering or prose")
    _assert_semantic(
        workflow,
        "write-paper resolved manuscript reference status",
        "`derived_manuscript_reference_status` for the resolved",
    )


def test_execute_phase_latex_compile_guidance_uses_resolved_manuscript_root() -> None:
    workflow = _workflow_text("execute-phase.md")

    _assert_forbidden(workflow, "execute-phase no hardcoded paper cwd", "paper/ARTIFACT-MANIFEST.json", "cd paper")
    _assert_machine(workflow, "execute-phase resolved manuscript latex fields", "MANUSCRIPT_ROOT", "latex_compile")
    _assert_semantic(workflow, "execute-phase manifest recorded tex entrypoint", "manifest-recorded TeX entrypoint")


def test_peer_review_reliability_reference_matches_peer_review_workflow_invocation() -> None:
    workflow = _workflow_text("peer-review.md")
    reliability = (REPO_ROOT / "src/gpd/specs/references/publication/peer-review-reliability.md").read_text(
        encoding="utf-8"
    )

    expected = 'gpd validate review-preflight peer-review --strict -- "$REVIEW_TARGET"'

    _assert_machine(workflow, "peer-review review-preflight strict command", expected)
    _assert_machine(reliability, "peer-review reliability review-preflight strict command", expected)
    _assert_forbidden(
        reliability,
        "peer-review reliability no targetless review-preflight strict command",
        "gpd validate review-preflight peer-review --strict)",
    )


def test_reapply_patches_keeps_manifest_regeneration_contract_honest() -> None:
    workflow = _workflow_text("reapply-patches.md")

    _assert_semantic(
        workflow,
        "reapply-patches manifest regeneration contract",
        "do not invent a manual manifest-regeneration step",
        "The managed file manifest is rebuilt by the next `gpd:update`",
    )
    _assert_forbidden(workflow, "reapply-patches stale manifest regeneration wording", "regenerate the file manifest")


def test_help_update_describes_bootstrap_update_surface_not_repo_pull() -> None:
    workflow = _workflow_text("help.md")

    _assert_semantic(
        workflow,
        "help update bootstrap surface",
        "Runs the public bootstrap update command for the active runtime",
        "Preserves local modifications via patch backups",
    )
    _assert_forbidden(workflow, "help update no repo-pull wording", "Pulls latest GPD files from the repository")


def test_new_milestone_roadmapper_prompt_surfaces_contract_gate_inputs() -> None:
    workflow = _workflow_text("new-milestone.md")
    contract_context = workflow[workflow.index("<contract_context>") : workflow.index("</contract_context>")]

    _assert_machine(
        contract_context,
        "new-milestone roadmapper contract gate placeholders",
        "Project contract gate: {project_contract_gate}",
        "Project contract validation: {project_contract_validation}",
        "Project contract load info: {project_contract_load_info}",
        "Contract intake: {contract_intake}",
        "Effective reference intake: {effective_reference_intake}",
        "Reference artifact file handles: {reference_artifact_files}",
    )
    _assert_semantic(
        workflow,
        "new-milestone effective reference artifact files",
        "Files named in `effective_reference_intake.must_include_prior_outputs`",
    )
    project_contract_gate_marker = "Project contract gate: {project_contract_gate}"
    assert workflow.index(project_contract_gate_marker) < workflow.index("approved project contract")
    _assert_machine(
        workflow,
        "new-milestone roadmapper contract state policy",
        "`project_contract_gate.authoritative` is true",
        "shared_state_policy: return_only",
        "expected_artifacts:",
    )


def test_help_resume_surface_stays_user_facing() -> None:
    workflow = expand_at_includes(_workflow_text("help.md"), REPO_ROOT / "src/gpd", "/runtime/").lower()

    _assert_semantic(
        workflow,
        "help resume public vocabulary",
        "canonical continuation fields define the public resume vocabulary",
    )
    _assert_forbidden(
        workflow,
        "help resume no backend vocabulary",
        "`resume_surface`",
        "session.resume_file",
        "shared resume-surface resolver owns canonical candidate kind/origin semantics",
    )


def test_resume_work_keeps_public_resume_vocabulary_canonical() -> None:
    resume_work_command = expand_at_includes(
        (COMMANDS_DIR / "resume-work.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )
    resume_work_workflow = expand_at_includes(_workflow_text("resume-work.md"), REPO_ROOT / "src/gpd", "/runtime/")

    _assert_semantic(
        resume_work_command,
        "resume-work command public vocabulary intro",
        resume_authority_public_vocabulary_intro(),
    )
    _assert_semantic(
        resume_work_workflow,
        "resume-work workflow public vocabulary intro",
        resume_authority_public_vocabulary_intro(),
    )
    _assert_forbidden(resume_work_command, "resume-work command backend vocabulary", "`resume_surface`", "handoff_resume_file")
    _assert_forbidden(resume_work_workflow, "resume-work workflow backend vocabulary", "`resume_surface`", "handoff_resume_file")
    assert resume_authority_fields() == (
        "active_resume_kind",
        "active_resume_origin",
        "active_resume_pointer",
        "active_bounded_segment",
        "derived_execution_head",
        "active_resume_result",
        "continuity_handoff_file",
        "recorded_continuity_handoff_file",
        "missing_continuity_handoff_file",
        "resume_candidates",
    )
    assert not any(alias in resume_authority_fields() for alias in resume_backend_only_fields())


def test_sync_state_keeps_state_json_authority_before_markdown_repair() -> None:
    raw_sync_state_command = (COMMANDS_DIR / "sync-state.md").read_text(encoding="utf-8")
    raw_sync_state_workflow = _workflow_text("sync-state.md")
    sync_state_command = expand_at_includes(
        raw_sync_state_command,
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )
    sync_state_workflow = expand_at_includes(raw_sync_state_workflow, REPO_ROOT / "src/gpd", "/runtime/")

    _assert_machine(raw_sync_state_command, "sync-state command staged bootstrap include", "@{GPD_INSTALL_DIR}/workflows/sync-state/sync-bootstrap.md")
    _assert_forbidden(raw_sync_state_command, "sync-state command no state schema at include", "@{GPD_INSTALL_DIR}/templates/state-json-schema.md")
    _assert_machine(raw_sync_state_workflow, "sync-state workflow state schema path", "{GPD_INSTALL_DIR}/templates/state-json-schema.md")
    _assert_forbidden(raw_sync_state_workflow, "sync-state workflow no state schema at include", "@{GPD_INSTALL_DIR}/templates/state-json-schema.md")
    _assert_semantic(
        raw_sync_state_workflow,
        "sync-state state json authority",
        "`state.json` is authoritative",
        "`STATE.md` is the projection",
    )

    for content in (sync_state_command, sync_state_workflow):
        _assert_machine(content, "sync-state expanded state schema path", "state-json-schema.md")
        _assert_forbidden(content, "sync-state no expanded state schema body", "# state.json Schema")

    assert re.search(r"`STATE\.md` is the projection and only becomes a recovery\s+source", sync_state_command)
    _assert_semantic(
        sync_state_workflow,
        "sync-state backend repair command ownership",
        "backend repair command owns",
        "Use `state.json` for structured fields and regenerate `STATE.md` from it unless `state.json` is unreadable.",
    )

    _assert_forbidden(sync_state_command, "sync-state command no field merge instruction", "do not invent a field-by-field merge")
    _assert_semantic(sync_state_workflow, "sync-state workflow field merge prohibition", "do not invent a field-by-field merge")


def test_resume_workflow_routes_recent_project_ambiguity_before_new_projects_and_state_reconstruction() -> None:
    workflow = _workflow_text("resume-work.md")

    ambiguity_line = (
        '**If `project_reentry_requires_selection` is true or `project_reentry_mode="ambiguous-recent-projects"`:**'
    )
    auto_recent_line = '**If `project_root_auto_selected` is true or `project_root_source="recent_project"`:**'
    new_project_line = "**If `planning_exists` is false and no recent-project selection is required:** If recoverable state exists, repair first. Otherwise route to gpd:new-project and do not attempt STATE.md reconstruction."
    reconstruction_line = "If STATE.md is missing but other artifacts exist and `planning_exists` is true:"

    _assert_machine(
        workflow,
        "resume-work recent project routing lines",
        ambiguity_line,
        auto_recent_line,
        new_project_line,
        reconstruction_line,
    )
    assert workflow.index(ambiguity_line) < workflow.index(new_project_line)
    assert workflow.index(auto_recent_line) < workflow.index(new_project_line)
    assert workflow.index(new_project_line) < workflow.index(reconstruction_line)


def test_resume_workflow_prioritizes_blocked_contract_repair_before_resume_targets_and_incomplete_plan() -> None:
    workflow = _workflow_text("resume-work.md")

    blocked_contract_line = "**If `project_contract_gate.authoritative` is false:**"
    bounded_segment_line = '**If `active_resume_kind="bounded_segment"` and `active_bounded_segment` exists:**'
    incomplete_plan_line = "**If incomplete plan (PLAN without SUMMARY) and no higher-priority blocker is active:**"

    _assert_machine(
        workflow,
        "resume-work blocked contract before resume targets",
        blocked_contract_line,
        bounded_segment_line,
        incomplete_plan_line,
    )
    assert workflow.index(blocked_contract_line) < workflow.index(bounded_segment_line)
    assert workflow.index(blocked_contract_line) < workflow.index(incomplete_plan_line)


def test_arxiv_submission_does_not_instruct_unsupported_explicit_submission_root() -> None:
    workflow = _workflow_text("arxiv-submission.md")

    _assert_forbidden(workflow, "arxiv submission no unsupported explicit root example", "submission/topic_stem.tex")
    manuscript_resolution_marker = "Resolve manuscript target from raw preflight"
    root_policy = workflow[workflow.index(manuscript_resolution_marker) :]
    for supported_root in (
        "`paper/`",
        "`manuscript/`",
        "`draft/`",
        "`GPD/publication/<subject_slug>/manuscript/`",
    ):
        _assert_machine(root_policy, f"arxiv submission supported root {supported_root}", supported_root)
    _assert_semantic(
        root_policy,
        "arxiv submission strict supported roots",
        "Do not accept arbitrary external directories",
        "Do not fall back to `find` or arbitrary wildcard matching",
    )


def test_paper_quality_scoring_reference_tracks_per_journal_gate_and_generic_fallback() -> None:
    scoring = (REPO_ROOT / "src/gpd/specs/references/publication/paper-quality-scoring.md").read_text(encoding="utf-8")

    _assert_machine(scoring, "paper scoring minimum submission score field", "minimum_submission_score")
    _assert_forbidden(scoring, "paper scoring no hardcoded score threshold", "score ≥ 80")
    _assert_semantic(scoring, "paper scoring generic profile fallback", "`mnras` and `jfm` currently use the generic weighting profile")


def test_write_paper_and_scoring_docs_distinguish_builder_supported_vs_manual_only_journals() -> None:
    workflow = _workflow_text("write-paper.md")
    scoring = (REPO_ROOT / "src/gpd/specs/references/publication/paper-quality-scoring.md").read_text(encoding="utf-8")

    _assert_semantic(workflow, "write-paper journal vocabulary source", "These are the only valid `journal` values")
    _assert_machine(workflow, "write-paper journal config artifact paths", "`PAPER-CONFIG.json`", "`${PAPER_DIR}/ARTIFACT-MANIFEST.json`")
    _assert_machine(scoring, "paper scoring artifact-driven from project path", "artifact-driven `--from-project` path")
    _assert_semantic(
        scoring,
        "paper scoring manual profiles",
        "Manual JSON is also the only supported path today for scoring-only profiles",
        "`prd`, `prb`, `prc`, and `nature_physics`",
    )


def test_settings_publication_manuscript_preset_surfaces_real_latex_readiness_gates() -> None:
    settings = _workflow_text("settings.md")

    _assert_forbidden(settings, "settings manuscript preset no smoke-only wording", "only affects local smoke checks")
    _assert_semantic(
        settings,
        "settings manuscript preset latex readiness gates",
        "can degrade or block `paper-build` / `arxiv-submission`",
    )
