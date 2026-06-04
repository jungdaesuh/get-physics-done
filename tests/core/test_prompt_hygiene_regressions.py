from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.core.model_visible_text import (
    agent_visibility_note,
    command_visibility_note,
    review_contract_visibility_note,
    skeptical_rigor_guardrails_section,
)
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.lifecycle_contract_test_support import (
    assert_forbidden_contract as _assert_forbidden,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import assert_semantic_contract as _assert_semantic
from tests.workflow_authority_support import workflow_authority_text

WORKFLOWS_DIR = Path("src/gpd/specs/workflows")
COMMANDS_DIR = Path("src/gpd/commands")
AGENTS_DIR = Path("src/gpd/agents")
REFERENCES_DIR = Path("src/gpd/specs/references")
TEMPLATES_DIR = Path("src/gpd/specs/templates")
PUBLICATION_SHARED_PREFLIGHT = TEMPLATES_DIR / "paper" / "publication-manuscript-root-preflight.md"
PUBLICATION_BOOTSTRAP_PREFLIGHT = REFERENCES_DIR / "publication" / "publication-bootstrap-preflight.md"
PUBLICATION_PIPELINE_MODES_INCLUDE = "@{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md"
PUBLICATION_PIPELINE_MODES_INLINE = "{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md"
PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE = "@{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md"
PUBLICATION_BOOTSTRAP_PREFLIGHT_PATH = "{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md"
PUBLICATION_ROUND_ARTIFACTS_INCLUDE = "{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md"
PUBLICATION_RESPONSE_ARTIFACTS_INCLUDE = "@{GPD_INSTALL_DIR}/references/publication/publication-response-artifacts.md"
PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE = (
    "{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md"
)
PUBLICATION_REVIEW_RELIABILITY_INCLUDE = "{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md"
PUBLICATION_REVIEW_RELIABILITY_INLINE = "{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md"
OWNED_COMMANDS = (
    COMMANDS_DIR / "debug.md",
    COMMANDS_DIR / "research-phase.md",
    COMMANDS_DIR / "literature-review.md",
    COMMANDS_DIR / "explain.md",
    COMMANDS_DIR / "respond-to-referees.md",
    COMMANDS_DIR / "write-paper.md",
)
FRESH_CONTEXT_PHRASE_EXEMPTIONS = {
    COMMANDS_DIR / "write-paper.md",
}
THIN_WORKFLOW_DELEGATOR_COMMANDS = {
    COMMANDS_DIR / "debug.md",
}


def test_help_resume_boundary_note_is_concise_and_contract_aligned() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8").lower()
    expanded_help_workflow = expand_at_includes(
        (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8"),
        Path("src/gpd"),
        "/runtime/",
    ).lower()

    _assert_semantic(
        expanded_help_workflow,
        "help resume boundary uses canonical public vocabulary",
        "canonical continuation fields",
        "public resume vocabulary",
    )
    _assert_forbidden(help_workflow, "help resume stale public vocabulary prose", "public top-level resume vocabulary")


def test_transition_workflow_stays_runtime_neutral() -> None:
    transition_workflow = (WORKFLOWS_DIR / "transition.md").read_text(encoding="utf-8")

    _assert_forbidden(transition_workflow, "transition workflow no runtime-specific slash commands", "slash_command(")
    _assert_semantic(
        transition_workflow,
        "transition workflow stays on installed runtime command surface",
        "installed runtime command surface",
    )


def test_quick_command_and_workflow_keep_the_project_gate_and_drop_the_custom_state_table() -> None:
    quick_command = (COMMANDS_DIR / "quick.md").read_text(encoding="utf-8")
    quick_workflow = workflow_authority_text(WORKFLOWS_DIR, "quick")

    _assert_machine(quick_command, "quick command context mode", "context_mode: project-required")
    _assert_forbidden(quick_command, "quick command no custom completion table", "Quick Tasks Completed")
    _assert_forbidden(quick_workflow, "quick workflow no custom completion table", "Quick Tasks Completed")
    _assert_semantic(
        quick_command,
        "quick command records completion through structured state commands",
        "Records completion",
        "structured `gpd state` commands",
    )
    _assert_machine(
        quick_workflow, "quick workflow project gate field", "project_exists", "**Project Exists:** {project_exists}"
    )
    _assert_semantic(
        quick_workflow,
        "quick workflow project gate without roadmap requirement",
        "Quick tasks can run mid-phase",
        "do NOT require ROADMAP.md",
        "initialized project workspace",
        "GPD/PROJECT.md",
        "GPD/",
    )
    _assert_forbidden(
        quick_workflow,
        "quick workflow stale directory-only project gate",
        "They only need `GPD/` to exist for directory structure.",
    )


def test_peer_review_init_fields_are_manifest_owned_and_interestingness_stage_bullets_are_space_indented() -> None:
    peer_review = workflow_authority_text(WORKFLOWS_DIR, "peer-review")
    manifest = load_workflow_stage_manifest("peer-review")

    _assert_semantic(
        peer_review,
        "peer-review init fields are manifest-owned",
        "Apply `BOOTSTRAP_INIT.staged_loading.field_access_instruction`",
        "keep `project_contract_gate`",
    )
    assert "project_contract_gate" in manifest.stage("bootstrap").required_init_fields
    _assert_semantic(
        peer_review,
        "peer-review stage access is manifest-owned",
        "staged manifest",
        "stage-specific files",
        "stage loading is manifest-owned",
    )
    _assert_forbidden(
        peer_review,
        "peer-review stale project_exists init parsing",
        "Parse bootstrap JSON for: `project_exists`",
        "Parse target-aware init JSON for: `project_exists`",
    )

    stage_5_start = peer_review.index("Stage 5 judges")
    stage_5_end = peer_review.index("Stage 6", stage_5_start)
    stage_5 = peer_review[stage_5_start:stage_5_end]
    assert "\t-" not in stage_5


def test_paper_writer_response_paths_are_orchestrator_supplied_not_global_authority() -> None:
    paper_writer = (AGENTS_DIR / "gpd-paper-writer.md").read_text(encoding="utf-8")
    author_response = paper_writer[paper_writer.index("<author_response>") : paper_writer.index("</author_response>")]

    for token in (
        "referee_report_path",
        "review_ledger_path",
        "referee_decision_path",
        "author_response_path",
        "referee_response_path",
        "selected_publication_root",
        "selected_review_root",
    ):
        _assert_machine(author_response, f"paper writer author response token {token}", token)

    _assert_forbidden(
        author_response,
        "paper writer no globally anchored response artifacts",
        "`GPD/AUTHOR-RESPONSE{round_suffix}.md` is the canonical internal tracker",
        "`GPD/review/REFEREE_RESPONSE{round_suffix}.md` is the synchronized journal-facing sibling",
        "GPD/review/REVIEW-LEDGER{round_suffix}.json",
        "GPD/review/REFEREE-DECISION{round_suffix}.json",
    )


def test_research_project_templates_point_existing_artifact_analysis_to_map_research() -> None:
    for path in sorted((TEMPLATES_DIR / "research-project").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        _assert_forbidden(content, f"{path.name} stale analysis paths", "templates/analysis/", "GPD/research/")
        _assert_machine(
            content,
            f"{path.name} map-research artifact paths",
            f"`GPD/literature/{path.name}`",
            "use `map-research`",
            "`GPD/research-map/`",
            "`references/templates/research-mapper/`",
        )

    shared_protocols = (REFERENCES_DIR / "shared" / "shared-protocols.md").read_text(encoding="utf-8")
    _assert_forbidden(shared_protocols, "shared protocols stale research artifact path", "GPD/research/ (5 files)")
    _assert_machine(shared_protocols, "shared protocols literature artifact path", "GPD/literature/ (5 files)")


def test_knowledge_schema_uses_existing_knowledge_review_workflow_id() -> None:
    knowledge_schema = (TEMPLATES_DIR / "knowledge-schema.md").read_text(encoding="utf-8")

    _assert_machine(
        knowledge_schema,
        "knowledge schema review workflow id",
        "reviewer_kind: workflow",
        "reviewer_id: gpd-review-knowledge",
    )
    _assert_forbidden(knowledge_schema, "knowledge schema stale agent reviewer id", "gpd-knowledge-reviewer")


def test_branch_hypothesis_and_transition_workflows_keep_state_updates_structured() -> None:
    branch_hypothesis = (WORKFLOWS_DIR / "branch-hypothesis.md").read_text(encoding="utf-8")
    transition_workflow = (WORKFLOWS_DIR / "transition.md").read_text(encoding="utf-8")

    _assert_forbidden(branch_hypothesis, "branch hypothesis stale state editing", "Active Hypothesis", "file_edit tool")
    _assert_machine(branch_hypothesis, "branch hypothesis structured state command", "gpd state add-decision")
    _assert_forbidden(
        transition_workflow, "transition workflow no direct state save", "save_state_markdown", "STATE.md directly"
    )
    _assert_machine(
        transition_workflow,
        "transition workflow structured state commands",
        "gpd state update-progress",
        "gpd state update",
        "gpd state patch",
    )


def test_write_paper_workflow_drops_authoring_note_placeholders() -> None:
    write_paper = workflow_authority_text(WORKFLOWS_DIR, "write-paper")

    _assert_forbidden(write_paper, "write-paper workflow no bootstrap note placeholders", "Default bootstrap wording:")


def test_publication_commands_keep_shared_manuscript_root_preflight_out_of_wrappers() -> None:
    shared_preflight = PUBLICATION_SHARED_PREFLIGHT.read_text(encoding="utf-8")
    bootstrap_preflight = PUBLICATION_BOOTSTRAP_PREFLIGHT.read_text(encoding="utf-8")
    publication_artifact_gates = (REFERENCES_DIR / "publication" / "publication-artifact-gates.md").read_text(
        encoding="utf-8"
    )

    _assert_semantic(
        shared_preflight,
        "publication preflight resolved manuscript directory strictness",
        "strict preflight reads `ARTIFACT-MANIFEST.json`, `BIBLIOGRAPHY-AUDIT.json`, and "
        "`reproducibility-manifest.json` from the resolved manuscript directory itself.",
        "Do not use ad hoc wildcard discovery or first-match filename scans.",
    )
    _assert_machine(
        shared_preflight, "publication preflight blocker keys", "bibliography_audit_clean", "reproducibility_ready"
    )
    _assert_machine(
        bootstrap_preflight,
        "publication bootstrap preflight references",
        "publication-manuscript-root-preflight.md",
        "publication-review-round-artifacts.md",
        "publication-response-artifacts.md",
    )
    _assert_machine(
        publication_artifact_gates, "publication artifact gates pipeline modes path", PUBLICATION_PIPELINE_MODES_INLINE
    )
    _assert_forbidden(
        publication_artifact_gates,
        "publication artifact gates no at include or migration claim",
        PUBLICATION_PIPELINE_MODES_INCLUDE,
        "claim full publication-root migration",
        "current global `gpd/` / `gpd/review/` round-artifact layout",
    )

    for path in (
        COMMANDS_DIR / "write-paper.md",
        COMMANDS_DIR / "peer-review.md",
        COMMANDS_DIR / "respond-to-referees.md",
        COMMANDS_DIR / "arxiv-submission.md",
    ):
        text = path.read_text(encoding="utf-8")
        assert text.count(PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE) == 0, path
        assert text.count(PUBLICATION_ROUND_ARTIFACTS_INCLUDE) == 0, path
        assert text.count(PUBLICATION_RESPONSE_ARTIFACTS_INCLUDE) == 0, path
        assert text.count(PUBLICATION_REVIEW_RELIABILITY_INCLUDE) == 0, path
        if path.name in {"write-paper.md", "peer-review.md"}:
            _assert_machine(text, f"{path.name} publication pipeline modes path", "publication-pipeline-modes.md")
            _assert_forbidden(
                text,
                f"{path.name} no embedded review parity or global layout prose",
                "embedded review/submission parity",
                "current global `GPD/` / `GPD/review/` round-artifact layout",
            )

    for path in (
        WORKFLOWS_DIR / "write-paper.md",
        WORKFLOWS_DIR / "peer-review.md",
        WORKFLOWS_DIR / "respond-to-referees.md",
        WORKFLOWS_DIR / "arxiv-submission.md",
    ):
        text = workflow_authority_text(WORKFLOWS_DIR, path.stem)
        assert text.count(PUBLICATION_BOOTSTRAP_PREFLIGHT_INCLUDE) == 0, path
        expected_bootstrap_path_counts = {
            "write-paper.md": 1,
            "peer-review.md": 0,
            "respond-to-referees.md": 1,
            "arxiv-submission.md": 1,
        }
        assert text.count(PUBLICATION_BOOTSTRAP_PREFLIGHT_PATH) >= expected_bootstrap_path_counts[path.name], path
        if path.name == "write-paper.md":
            _assert_machine(text, "write-paper publication bootstrap reference", "publication-bootstrap-preflight.md")
        expected_round_counts = {
            "write-paper.md": 0,
            "peer-review.md": 0,
            "respond-to-referees.md": 0,
            "arxiv-submission.md": 1,
        }
        expected_response_artifact_counts = {}
        expected_response_handoff_counts = {
            "write-paper.md": 1,
            "respond-to-referees.md": 1,
        }

        assert text.count(PUBLICATION_ROUND_ARTIFACTS_INCLUDE) >= expected_round_counts[path.name], path
        if path.name == "write-paper.md":
            _assert_machine(
                text, "write-paper publication round artifacts reference", "publication-review-round-artifacts.md"
            )
        if path.name in expected_response_artifact_counts:
            assert text.count(PUBLICATION_RESPONSE_ARTIFACTS_INCLUDE) >= expected_response_artifact_counts[path.name], (
                path
            )
        else:
            assert PUBLICATION_RESPONSE_ARTIFACTS_INCLUDE not in text, path
        if path.name in expected_response_handoff_counts:
            assert (
                text.count(PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE) >= expected_response_handoff_counts[path.name]
            ), path
        else:
            assert PUBLICATION_RESPONSE_WRITER_HANDOFF_INCLUDE not in text, path
        if path.name == "arxiv-submission.md":
            _assert_forbidden(
                text, "arxiv submission no inline reliability include", PUBLICATION_REVIEW_RELIABILITY_INCLUDE
            )
            _assert_semantic(
                text, "arxiv submission staged reliability reference", "staged `peer-review-reliability.md` reference"
            )
        elif path.name in {"peer-review.md", "respond-to-referees.md"}:
            assert text.count(PUBLICATION_REVIEW_RELIABILITY_INLINE) >= 1, path
        else:
            assert PUBLICATION_REVIEW_RELIABILITY_INCLUDE not in text, path


def test_literature_and_research_commands_trim_inline_methodology_blocks() -> None:
    literature = (COMMANDS_DIR / "literature-review.md").read_text(encoding="utf-8")
    research_phase = (COMMANDS_DIR / "research-phase.md").read_text(encoding="utf-8")

    _assert_semantic(
        literature,
        "literature command thin staged workflow wrapper",
        "Run the literature-review workflow as a thin wrapper",
        "Read the included literature-review bootstrap authority first.",
        "The staged workflow owns scope fixing, artifact gating, citation verification",
    )
    _assert_forbidden(
        literature,
        "literature command no inline methodology block",
        "A physics literature review is not a bibliography.",
        "Method A lineage: paper1 -> paper2 -> paper3",
        "Active Anchor Registry",
    )
    _assert_forbidden(
        research_phase,
        "research phase no inline literature-review question block",
        "What do I not know that I don't know?",
        "What mathematical methods and computational tools form the standard approach?",
    )
    _assert_semantic(
        research_phase,
        "research phase workflow-owned depth",
        "Research depth follows the workflow-owned `research_mode`.",
    )


def test_shared_context_budget_guidance_stays_runtime_neutral() -> None:
    owned_surfaces = (
        COMMANDS_DIR / "debug.md",
        COMMANDS_DIR / "research-phase.md",
        COMMANDS_DIR / "literature-review.md",
        COMMANDS_DIR / "respond-to-referees.md",
        WORKFLOWS_DIR / "plan-phase.md",
        WORKFLOWS_DIR / "execute-phase.md",
        WORKFLOWS_DIR / "execute-plan.md",
        REFERENCES_DIR / "orchestration" / "context-budget.md",
    )

    for path in owned_surfaces:
        text = path.read_text(encoding="utf-8").lower()
        assert "200k" not in text, path


def test_owned_commands_keep_a_single_concise_subagent_rationale() -> None:
    for path in OWNED_COMMANDS:
        text = path.read_text(encoding="utf-8")
        if path in THIN_WORKFLOW_DELEGATOR_COMMANDS:
            _assert_forbidden(text, f"{path.name} thin delegator no subagent rationale", "Why subagent:")
            _assert_machine(text, f"{path.name} thin delegator include instruction", "Follow the included ")
            continue
        assert text.count("Why subagent:") == 1, path
        if path in FRESH_CONTEXT_PHRASE_EXEMPTIONS:
            _assert_forbidden(text, f"{path.name} fresh context exemption", "Fresh context")
        else:
            assert text.count("Fresh context") == 1, path


def test_research_phase_command_drops_dead_command_local_mode_labels() -> None:
    research_phase = (COMMANDS_DIR / "research-phase.md").read_text(encoding="utf-8")

    _assert_forbidden(
        research_phase,
        "research phase no command-local mode labels",
        "Research modes: literature (default), feasibility, methodology, comparison.",
        "Mode: literature",
    )
    _assert_semantic(
        research_phase,
        "research phase workflow-owned mode depth",
        "Research depth follows the workflow-owned `research_mode`.",
    )


def test_write_paper_command_defers_the_route_list_to_the_workflow() -> None:
    write_paper = (COMMANDS_DIR / "write-paper.md").read_text(encoding="utf-8")
    write_paper_workflow = workflow_authority_text(WORKFLOWS_DIR, "write-paper")

    _assert_forbidden(write_paper, "write-paper command no route list", "Routes to the write-paper workflow:")
    _assert_machine(
        write_paper,
        "write-paper command staged bootstrap include",
        "@{GPD_INSTALL_DIR}/workflows/write-paper/paper-bootstrap.md",
    )
    _assert_forbidden(
        write_paper, "write-paper command no monolithic workflow include", "@{GPD_INSTALL_DIR}/workflows/write-paper.md"
    )
    _assert_machine(
        write_paper_workflow,
        "write-paper workflow publication references",
        "publication-bootstrap-preflight.md",
        "publication-review-round-artifacts.md",
        "{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md",
    )
    _assert_forbidden(
        write_paper_workflow,
        "write-paper workflow no response writer at include",
        "@{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md",
    )


def test_debug_workflow_path_note_is_not_self_contradictory() -> None:
    debug_workflow = (WORKFLOWS_DIR / "debug.md").read_text(encoding="utf-8")

    _assert_machine(debug_workflow, "debug workflow GPD debug path", "Debug files use the `GPD/debug/` path.")
    _assert_forbidden(
        debug_workflow, "debug workflow no hidden directory contradiction", "hidden directory with leading dot"
    )


def test_debugger_session_paths_keep_the_active_and_resolved_lifecycles_separate() -> None:
    debug_command = (COMMANDS_DIR / "debug.md").read_text(encoding="utf-8")
    debug_agent = (AGENTS_DIR / "gpd-debugger.md").read_text(encoding="utf-8")
    debug_workflow = (WORKFLOWS_DIR / "debug.md").read_text(encoding="utf-8")

    _assert_machine(
        debug_command,
        "debug command active session path",
        "Debug session artifact: `GPD/debug/{slug}.md`",
        "the child reads `GPD/debug/{slug}.md` before continuing",
    )
    _assert_machine(
        debug_agent,
        "debug agent active and resolved session paths",
        "files_written:\n    - GPD/debug/root-cause.md",
        "session_file: GPD/debug/root-cause.md",
        "**Troubleshooting Session:** GPD/debug/resolved/{slug}.md",
    )
    _assert_machine(debug_workflow, "debug workflow session status field", "session_status: diagnosed")
    _assert_semantic(
        debug_workflow,
        "debug workflow typed return routing",
        "Do not route on heading markers in the returned text",
        "typed `gpd_return` envelope and the session file instead",
    )


def test_settings_workflow_reuses_one_terminal_follow_up_list() -> None:
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    terminal_follow_up_marker = "For normal-terminal follow-up around these settings:"

    assert settings_workflow.count(terminal_follow_up_marker) == 1
    _assert_semantic(
        settings_workflow,
        "settings workflow terminal follow-up reuse",
        "reuse the normal-terminal follow-up list from the `present_settings` step",
    )
    assert settings_workflow.count("gpd validate unattended-readiness --runtime <runtime> --autonomy <mode>") == 1


def test_sync_state_workflow_keeps_optional_commit_outside_core_reconcile_path() -> None:
    sync_state = workflow_authority_text(WORKFLOWS_DIR, "sync-state")

    _assert_semantic(
        sync_state,
        "sync-state fail-closed optional commit path",
        "This workflow is intentionally fail-closed",
        "Only if the operator explicitly asks to commit the reconciled state",
    )
    _assert_machine(sync_state, "sync-state no-state recovery command", "No state files found. Run gpd:new-project")
    _assert_forbidden(
        sync_state,
        "sync-state no interactive recency reconciliation",
        "Proceed with reconciliation? (y/n)",
        "determine which source is more recent",
    )
    assert sync_state.index('<step name="reconcile">') < sync_state.index('<step name="optional_commit">')
    assert sync_state.index('gpd --raw --cwd "$PROJECT_ROOT" state validate') < sync_state.index(
        '<step name="optional_commit">'
    )


def test_model_visible_yaml_notes_do_not_duplicate_scientific_rigor_guardrails() -> None:
    guardrail_section = skeptical_rigor_guardrails_section()
    yaml_notes = (
        agent_visibility_note(),
        command_visibility_note(),
        review_contract_visibility_note(),
    )

    _assert_machine(guardrail_section, "scientific rigor guardrail heading", "## Scientific Rigor Guardrails")
    _assert_semantic(
        guardrail_section,
        "scientific rigor guardrail skepticism wording",
        "Use scientific skepticism and critical thinking",
    )
    for note in yaml_notes:
        _assert_forbidden(
            note,
            "model-visible yaml note no duplicated rigor guardrail prose",
            "Use scientific skepticism and critical thinking",
            "Prefer skeptical verification",
            "inventing fallback content",
        )
