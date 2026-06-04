"""Late prompt-wiring lifecycle and route contracts split from test_prompt_wiring."""

from __future__ import annotations

from tests.core.test_prompt_wiring import (
    AGENTS_DIR,
    COMMANDS_DIR,
    REFERENCES_DIR,
    TEMPLATES_DIR,
    WORKFLOWS_DIR,
    _assert_semantic_concept,
    _autonomous_authority_text,
    _extract_between,
    _f,
    _ff,
    _m,
    _mf,
    _s,
    _sf,
    _success_criteria_sections,
    _workflow_authority_text,
)


def test_peer_review_and_arxiv_use_subject_aware_publication_roots() -> None:
    peer_review = _workflow_authority_text("peer-review")
    arxiv_submission = _workflow_authority_text("arxiv-submission")

    for field in (
        "publication_subject_slug",
        "publication_lane_kind",
        "managed_publication_root",
        "selected_publication_root",
        "selected_review_root",
    ):
        _m(peer_review, "peer-review subject-aware publication root fields", field)
        _m(arxiv_submission, "arxiv subject-aware publication root fields", field)
    _sf(
        peer_review,
        "`REVIEW_ROOT`",
        "`selected_review_root`",
        "${REVIEW_ROOT}/STAGE-reader{round_suffix}.json",
        'gpd validate artifact-text "$RESOLVED_MANUSCRIPT" --output ${REVIEW_ROOT}/MANUSCRIPT-TEXT.txt',
        context="peer-review subject-aware review root",
    )
    _f(peer_review, "peer-review subject-aware review root", "GPD/review/STAGE-reader{round_suffix}.json")

    _mf(
        arxiv_submission,
        "REVIEW_PREFLIGHT=$(gpd --raw validate review-preflight arxiv-submission",
        "BOOTSTRAP_INIT=$(gpd --raw init arxiv-submission --stage bootstrap)",
        'gpd --raw validate command-context arxiv-submission -- "${ARGUMENTS}"',
        'gpd --raw validate review-preflight arxiv-submission --strict -- "${ARGUMENTS}"',
        'PUBLICATION_ROOT="GPD/publication/${SUBJECT_SLUG}"',
        'PACKAGE_ROOT="${PUBLICATION_ROOT}/arxiv"',
        context="arxiv subject-aware publication root commands",
    )
    _s(
        arxiv_submission,
        "arxiv subject-aware publication root commands",
        "Set `subject_slug`",
        "publication_subject_slug",
    )
    _ff(
        arxiv_submission,
        'gpd --raw init arxiv-submission --stage bootstrap -- "${ARGUMENTS}"',
        'PUBLICATION_ROOT="${selected_publication_root:-GPD/publication/${subject_slug}}"',
        "Derive a stable ASCII `subject_slug`",
        context="arxiv subject-aware publication root commands",
    )


def test_generated_peer_review_skill_surface_uses_artifact_text_helper_for_non_plaintext_intake() -> None:
    from gpd.mcp.servers.skills_server import get_skill

    peer_review_skill = get_skill("gpd-peer-review")
    peer_review_skill_content = peer_review_skill["content"]
    peer_review_workflow = _workflow_authority_text("peer-review")

    _s(peer_review_skill_content, "generated peer-review skill staged routing", "artifact_discovery", "staged_loading")
    _sf(
        peer_review_workflow,
        "If none exists",
        "${REVIEW_ROOT}/",
        "gpd validate artifact-text",
        "$RESOLVED_MANUSCRIPT",
        "${REVIEW_ROOT}/MANUSCRIPT-TEXT.txt",
        "extracted file",
        "canonical",
        "`RESOLVED_MANUSCRIPT`",
        context="generated peer-review skill artifact text helper",
    )

    _sf(
        peer_review_workflow,
        "If extraction fails",
        "STOP",
        "`.txt`",
        "`.md`",
        "`.tex`",
        "`.csv`",
        "`.tsv`",
        "matching extracted `.txt` companion file",
        context="generated peer-review skill artifact text helper",
    )
    _f(peer_review_skill_content, "generated peer-review skill artifact text helper", "pdftotext")


def test_verification_and_publication_prompts_keep_decisive_contract_targets_reader_visible() -> None:
    verify_work = _workflow_authority_text("verify-work")
    write_paper = _workflow_authority_text("write-paper")
    peer_review = _workflow_authority_text("peer-review")
    respond = _workflow_authority_text("respond-to-referees")

    _sf(
        verify_work,
        "researcher",
        "Project contract",
        "claim",
        "acceptance-test",
        "decisive comparison gaps",
        context="verify-work decisive contract targets",
    )
    _sf(
        write_paper,
        "contract_results",
        "comparison_verdicts",
        "paper-support artifacts",
        "not as proof",
        "pre_submission_review",
        "reproducibility manifest",
        context="write-paper decisive contract targets",
    )
    _s(peer_review, "peer-review decisive contract targets", "review-support artifacts", "scaffolding")
    _s(respond, "respond decisive contract targets", "referee requests", "honest scope", "optional", "real support gap")


def test_new_project_spawns_roadmapper_with_shallow_mode_in_standard_mode() -> None:
    new_project = _workflow_authority_text("new-project")
    assert "<shallow_mode>true</shallow_mode>" in new_project


def test_new_milestone_keeps_full_roadmap_detail_shallow_mode_false() -> None:
    new_milestone = _workflow_authority_text("new-milestone")
    assert "<shallow_mode>false</shallow_mode>" in new_milestone


def test_new_project_next_up_recommends_discuss_phase_1_primary() -> None:
    new_project = (WORKFLOWS_DIR / "new-project" / "completion.md").read_text(encoding="utf-8")
    # The standard-mode Next Up block is the final occurrence; the first is the --minimal path.
    next_up_block = new_project[new_project.rindex("## > Next Up") :]
    # discuss-phase 1 should appear before plan-phase 1 in that block.
    discuss_idx = next_up_block.index("`gpd:discuss-phase 1`")
    plan_idx = next_up_block.index("`gpd:plan-phase 1`")
    assert discuss_idx < plan_idx, "discuss-phase 1 must be the primary Next Up recommendation, not plan-phase"


def test_roadmapper_documents_shallow_mode_behavior() -> None:
    roadmapper = (AGENTS_DIR / "gpd-roadmapper.md").read_text(encoding="utf-8")
    assert "shallow_mode" in roadmapper
    assert "Phase 1" in roadmapper
    assert "stub" in roadmapper.lower()


def test_route_workflow_uses_physics_scope_examples_and_ordered_compound_contract() -> None:
    route_workflow = (WORKFLOWS_DIR / "route.md").read_text(encoding="utf-8")
    route_command = (COMMANDS_DIR / "route.md").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    _mf(
        route_workflow,
        "STATE=$(gpd --raw state get --include position,continuation)",
        "fail_closed_on_state_conflict",
        "state/roadmap phase mismatch or missing active phase directory -> `gpd:sync-state`",
        "convention-lock or `GPD/CONVENTIONS.md` mismatch -> `gpd:validate-conventions`",
        context="route workflow state and conflict contracts",
    )
    _f(
        route_workflow,
        "route workflow stale command examples",
        "position,session,continuation",
        "TAM/revenue/impact analysis",
    )
    _sf(
        route_workflow,
        "parameter sweep",
        "derived model",
        "active milestone override",
        "generic health checks",
        "Exactly one recommendation",
        "compound",
        "ordered command sequence",
        context="route workflow physics and compound recommendation semantics",
    )

    _mf(
        route_command,
        'argument-hint: "[--frozen=yes|no] [--change=extend|revise] [--layer=new|change]"',
        context="route command public argument hint",
    )
    _sf(
        route_command,
        "included route workflow",
        "One recommendation",
        "compound recommendations",
        "required commands in order",
        context="route command workflow delegation",
    )
    _mf(
        help_workflow,
        "ordered compound sequence `gpd:complete-milestone` then `gpd:new-milestone`",
        context="help route compound recommendation example",
    )


def test_phase_lifecycle_workflows_fail_closed_on_dirty_state_and_stale_verification() -> None:
    plan_phase = _workflow_authority_text("plan-phase")
    autonomous = _autonomous_authority_text()

    _sf(
        plan_phase,
        "Dirty worktree safety gate",
        "project worktree",
        "dirty paths",
        "never stashes",
        "resets",
        "cleans",
        "overwrites",
        "fail_closed_on_state_conflict",
        "Canonical conflict-stop labels",
        "convention check",
        "route failures",
        "convention validation",
        context="plan-phase lifecycle gate",
    )

    _sf(
        autonomous,
        "Missing, stale",
        "non-passing",
        "blocks lifecycle",
        "gpd:verify-work",
        "COMPLETE_PHASE",
        "missing plan authority",
        context="autonomous lifecycle verification gate",
    )
    _m(
        autonomous,
        "autonomous lifecycle verification validator",
        "gpd --raw validate lifecycle-contract-gate plan-phase",
    )


def test_new_project_customize_settings_matches_supervised_dense_defaults() -> None:
    new_project = (WORKFLOWS_DIR / "new-project" / "workflow-preferences.md").read_text(encoding="utf-8")

    customize = _extract_between(new_project, "<customize_settings>", "</customize_settings>")

    _assert_semantic_concept(
        customize,
        "new-project customize choices keep supervised dense defaults",
        required=(
            "Autonomy: supervised / balanced / yolo",
            "Review cadence: dense / adaptive / sparse",
            "Planning commit docs: true / false",
        ),
        forbidden='Balanced (Recommended)", description: "Routine work is automatic',
        context="new-project customize round-one shape",
    )
    _mf(
        new_project,
        '"autonomy": "supervised"',
        '"review_cadence": "dense"',
        '"commit_docs": true',
        context="new-project customize supervised dense defaults",
    )


def test_undo_backtrack_hook_collects_complete_backtrack_row_fields() -> None:
    undo_workflow = (WORKFLOWS_DIR / "undo.md").read_text(encoding="utf-8")
    record_workflow = (WORKFLOWS_DIR / "record-backtrack.md").read_text(encoding="utf-8")
    record_command = (COMMANDS_DIR / "record-backtrack.md").read_text(encoding="utf-8")

    assert "--phase=<NN-slug>" in record_command

    record_parse_step = _extract_between(
        record_workflow,
        '<step name="parse_prefill_args">',
        "</step>",
    )
    record_dedupe_step = _extract_between(
        record_workflow,
        '<step name="check_duplicates">',
        "</step>",
    )
    undo_backtrack_step = _extract_between(
        undo_workflow,
        '<step name="offer_record_backtrack">',
        "</step>",
    )

    _m(record_parse_step, "record-mistake phase parse option", "--phase=<NN-slug>")
    _m(record_dedupe_step, "record-mistake dedupe key fields", "`phase`", "`trigger`", "`why_wrong`")
    _s(record_dedupe_step, "record-mistake dedupe semantics", "Dedupe by exact normalized matching of finalized")
    _mf(
        undo_backtrack_step,
        "reverted_commit",
        "TARGET_HASH",
        "trigger",
        "TARGET_MSG",
        "phase",
        "INFERRED_PHASE_OR_NULL",
        "`stage`",
        "`produced`",
        "`why_wrong`",
        "`counter_action`",
        "`category`",
        "`confidence`",
        "`promote`",
        context="undo backtrack structured row fields",
    )
    _sf(
        undo_backtrack_step,
        "structured arguments",
        "not a shell-shaped string",
        "do not interpolate it into shell-shaped args",
        "remaining required row fields",
        context="undo backtrack shell-safe structured args",
    )
    _f(
        undo_backtrack_step,
        "undo-mistake backtrack stale user prompt boundary",
        "prompts the user only for `why_wrong`",
    )


def test_changed_continuation_surfaces_do_not_reintroduce_session_as_authority() -> None:
    checked_surfaces = {
        "execute-plan": (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8"),
        "resume-work": _workflow_authority_text("resume-work"),
        "checkpoints": (REFERENCES_DIR / "orchestration" / "checkpoints.md").read_text(encoding="utf-8"),
        "github-lifecycle": (REFERENCES_DIR / "execution" / "github-lifecycle.md").read_text(encoding="utf-8"),
        "state-machine": (TEMPLATES_DIR / "state-machine.md").read_text(encoding="utf-8"),
        "help": (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8"),
    }
    stale_phrases = (
        "`session` record are discovery surfaces",
        "`session` and STATE.md are projection surfaces",
        "`session` continuity mirror",
        "`session` fields should mirror",
        "session info reflect the latest work",
        "session fields, or the derived head",
        "canonical session handoff",
        "STATE.md (Session section)",
        "mirrored STATE.md session continuity entry",
    )

    for name, text in checked_surfaces.items():
        for phrase in stale_phrases:
            assert phrase not in text, f"{name} reintroduced stale session-authority wording: {phrase}"


def test_autonomous_success_criteria_stay_provider_neutral_and_current() -> None:
    autonomous = _autonomous_authority_text()
    success_criteria = _success_criteria_sections(autonomous)

    assert "current `gpd` surfaces" in success_criteria or "runtime-installed child commands" in success_criteria
    assert "canonical `GPD/` paths" in success_criteria or "GPD/CONVENTIONS.md" in autonomous
    assert "runtime/provider-neutral" in success_criteria

    for stale_fragment in ("gsd-tools.cjs", ".planning/", "provider-specific features"):
        assert stale_fragment not in success_criteria
    for provider_literal in ("Anthropic", "OpenAI"):
        assert provider_literal not in success_criteria
