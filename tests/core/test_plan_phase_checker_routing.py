"""Routing assertions for the `plan-phase` checker seam."""

from __future__ import annotations

from pathlib import Path

from tests.lifecycle_contract_test_support import (
    assert_forbidden_lifecycle_prose as _assert_absent,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PHASE = REPO_ROOT / "src/gpd/specs/workflows/plan-phase.md"
PLAN_PHASE_STAGE_DIR = REPO_ROOT / "src/gpd/specs/workflows/plan-phase"
CHECKER_LANE_FILES = (
    "checker-revision.md",
    "checker-return-routing.md",
    "blocked-plan-revision.md",
    "revision-planner-handoff.md",
    "planning-final-offer.md",
)


def _stage_text(name: str) -> str:
    return (PLAN_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def _checker_authority_text() -> str:
    return "\n\n".join(_stage_text(name) for name in CHECKER_LANE_FILES)


def _plan_phase_authority_text() -> str:
    return "\n\n".join(
        [
            PLAN_PHASE.read_text(encoding="utf-8"),
            _stage_text("phase-bootstrap.md"),
            _stage_text("research-routing.md"),
            _stage_text("planner-authoring.md"),
            _checker_authority_text(),
        ]
    )


def test_plan_phase_separates_planner_checkpoint_handling_from_checker_revision() -> None:
    source = _stage_text("planner-authoring.md")

    assert "## 9b. Handle Planner Checkpoint" in source
    _assert_semantic(
        source,
        "plan-phase planner checkpoint is fresh continuation not checker revision",
        "fresh `gpd-planner` continuation handoff",
        "Do not route planner checkpoints into the checker revision loop.",
        "planner returns `completed`",
        "advance to checker review",
    )
    _assert_absent(
        source,
        "plan-phase stale planner checkpoint continuation wording",
        "Present to user, get response, spawn continuation (step 12)",
    )


def test_plan_phase_routes_checker_statuses_through_structured_fields() -> None:
    source = _checker_authority_text()

    _assert_semantic(
        source,
        "plan-phase checker structured fields are authoritative",
        "`gpd_return.status: completed`",
        "`gpd_return.status: checkpoint`",
        "`gpd_return.status: blocked`",
        "`gpd_return.status: failed`",
        "structured `approved_plans` list only",
        "structured `blocked_plans` list only",
        "plan-ID reconciliation",
    )
    _assert_absent(
        source,
        "plan-phase checker presentation table is non-authority",
        "Approved Plans (ready for execution)",
        'Approved Plans" table',
    )


def test_plan_phase_checker_handoff_precedes_return_routing_and_late_events() -> None:
    source = _checker_authority_text()

    handoff = "## 10. Event: checker_handoff"
    routing = "## 11. Event: checker_return_routing"
    revision = "## 12. Event: blocked_plan_revision_branch"
    final_offer = "## 13. Event: planning_final_offer"

    assert source.index(handoff) < source.index(routing) < source.index(revision) < source.index(final_offer)

    initial_checker_event = source[source.index(handoff) : source.index(routing)]
    _assert_semantic(
        initial_checker_event,
        "plan-phase initial checker event excludes late machinery",
        "CHECKER_RETURN=$(\ntask(",
        'child_gate:\n  id: "plan_checker_review"',
        "Stop this event after the checker call",
        "do not display revision planner prompts",
        "max-iteration choices",
        "final planning offer",
    )
    _assert_absent(
        initial_checker_event,
        "plan-phase initial checker event omits late revision/final offer text",
        "Revision prompt:",
        "Max iterations reached",
        "PHASE PLANNED",
    )


def test_plan_phase_checker_routing_is_after_runtime_return_and_keeps_child_validity() -> None:
    source = _checker_authority_text()
    routing = "## 11. Event: checker_return_routing"
    revision = "## 12. Event: blocked_plan_revision_branch"
    routing_event = source[source.index(routing) : source.index(revision)]

    _assert_semantic(
        routing_event,
        "plan-phase checker routing preserves status routes and child-return validity",
        "valid fenced\n`gpd_return.status`",
        "file\nexistence, logs, headings, or old artifacts",
        "Plan-ID reconciliation is required before accepting any checker route",
        "`gpd_return.status: completed`",
        "`gpd_return.status: checkpoint`",
        "`gpd_return.status: blocked`",
        "`gpd_return.status: failed`",
        "structured `approved_plans`",
        "structured `blocked_plans`",
        "Reject any checker `files_written` value other than `[]`",
    )


def test_plan_phase_revision_planner_is_branch_local_after_blocked_plan_choice() -> None:
    source = _checker_authority_text()
    revision = "## 12. Event: blocked_plan_revision_branch"
    revision_handoff_marker = "## 12a. Event: revision_planner_handoff"
    final_offer = "## 13. Event: planning_final_offer"
    revision_branch = source[source.index(revision) : source.index(revision_handoff_marker)]
    revision_handoff = source[source.index(revision_handoff_marker) : source.index(final_offer)]

    assert revision_branch.index("If iteration_count >= 3") < revision_branch.index("Ask only now")
    _assert_semantic(
        revision_branch,
        "plan-phase revision branch reconciles blocked plans before planner machinery",
        "Confirm that every `plan_id` in `BLOCKED_PLANS` maps to exactly one readable",
        "Ask only now",
        "blocked plan IDs are reconciled",
        "user's exhaustion choice",
        "Do NOT loop indefinitely",
    )
    _assert_absent(
        revision_branch,
        "plan-phase blocked-plan revision branch omits planner machinery before choice",
        "Revision prompt:",
        "PLANNER_RETURN=$(\ntask(",
        'child_gate:\n  id: "planner_revision"',
    )

    _assert_semantic(
        revision_handoff,
        "plan-phase revision planner handoff owns planner machinery",
        "Revision prompt:",
        "PLANNER_RETURN=$(\ntask(",
        'child_gate:\n  id: "planner_revision"',
        "Load the `revision_template_rendering` conditional authority pack first",
    )


def test_plan_phase_final_offer_waits_for_green_override_or_skipped_status() -> None:
    source = _stage_text("planning-final-offer.md")
    final_offer = "## 13. Event: planning_final_offer"
    final_event = source[source.index(final_offer) :]

    _assert_semantic(
        final_event,
        "plan-phase final offer waits for final status",
        "Route here only after `checker_return_routing`",
        "`green`",
        "`override`",
        "`skipped`",
        "Do not render the final offer from initial checker handoff state",
        "Structured final status convention",
    )
    assert final_event.index("Route here only after") < final_event.index("Structured final status convention")


def test_plan_phase_fails_closed_on_plan_id_mismatch_before_accepting_checker_success() -> None:
    source = _stage_text("checker-return-routing.md")

    assert "`approved_plans` names only readable `*-PLAN.md` artifacts in `FRESH_PLAN_FILES`" in source
    assert "`blocked_plans` is empty" in source
    assert "every approved plan file still exists and matches the approved plan IDs" in source
    _assert_semantic(
        source,
        "plan-phase checker rejects plan id mismatch before success",
        "Reject the return",
        "plan ID",
        "readable `*-PLAN.md` file",
        "FRESH_PLAN_FILES",
        "fail-closed mismatch",
    )


def test_plan_phase_checker_base_defers_late_lanes_and_stale_success_criteria() -> None:
    base = _stage_text("checker-revision.md")
    joined = _checker_authority_text()

    _assert_semantic(
        base,
        "plan-phase checker base is initial handoff only",
        "## 10. Event: checker_handoff",
        "Load these only when their trigger is present",
        "checker_return_routing",
        "blocked_plan_revision",
        "revision_planner_handoff",
        "planning_final_offer",
    )
    _assert_absent(
        base,
        "plan-phase checker base omits late lane payloads",
        "## 11. Event: checker_return_routing",
        "## 12. Event: blocked_plan_revision_branch",
        "Revision prompt:",
        "Max iterations reached",
        "PHASE PLANNED",
    )
    _assert_absent(
        joined,
        "plan-phase checker success criteria no longer claim stale all-agent context loading",
        "CONTEXT.md loaded early",
        "passed to ALL agents",
    )


def test_plan_phase_reloads_each_stage_and_validates_only_fresh_plan_files() -> None:
    source = _plan_phase_authority_text()

    assert "bind_plan_phase_init" not in source
    assert "staged_loading.required_init_fields" not in source
    assert "BOOTSTRAP_INIT.staged_loading.field_access_instruction" in source
    assert "INIT.staged_loading.field_access_instruction" in source
    assert "gpd --raw stage field-access plan-phase --stage <stage_id> --style instruction" not in source
    assert "--alias ALIAS=field" in source
    assert "shell variables parsed from an older stage" in source
    assert 'BOOTSTRAP_INIT=$(gpd --raw init plan-phase "$PHASE" --stage phase_bootstrap)' in source
    assert 'gpd --raw init plan-phase "$PHASE" --stage research_routing' in source
    assert 'gpd --raw init plan-phase "$PHASE" --stage planner_authoring' in source
    assert 'gpd --raw init plan-phase "$PHASE" --stage checker_revision' in source
    assert source.count("INIT=$(gpd --raw init plan-phase") >= 3
    assert "PLANNER_RETURN=$(\ntask(" in source
    assert source.index("PLANNER_RETURN=$(") < source.index(
        "Before checker/final status, validate only fresh `FRESH_PLAN_FILES`"
    )
    _assert_semantic(
        source,
        "plan-phase uses typed planner return and skeleton for main-context fallback",
        "typed `PLANNER_RETURN`",
        "gpd return skeleton --role planner --status completed",
        "one `--file` entry per newly written plan",
        "planner child_gate tuple once",
    )
    _assert_absent(
        source,
        "plan-phase no synthetic files-only planner return",
        "printf '```yaml\\ngpd_return:\\n'",
        "printf '  status: completed\\n  files_written:\\n'",
        "printf '%s\\n' \"$PLAN_RETURN_MARKDOWN\"",
        'FRESH_PLAN_FILES="$FRESH_PLAN_FILES" python3 -c',
        'json.dumps({"gpd_return":{"files_written":os.getenv("FRESH_PLAN_FILES","").split()}})',
    )
    assert "gpd validate handoff-artifacts -" in source
    assert "allowed-root" in source
    assert "expected-glob" in source
    assert "--required-suffix=-PLAN.md" in source
    assert '[ -f "$plan_file" ] || continue' not in source
    _assert_semantic(
        source,
        "plan-phase fresh plan validators before checker or final status",
        "readable `${PHASE_DIR}/*-PLAN.md` paths",
        "gpd validate plan-contract",
        "structured plan preflight validator",
        "fresh plan artifact",
        "after the planner gate passes",
        "FRESH_PLAN_FILES",
    )


def test_plan_phase_does_not_synthesize_files_only_json_planner_return() -> None:
    source = _stage_text("planner-authoring.md")

    _assert_semantic(
        source,
        "plan-phase main-context return uses skeleton not synthetic child return",
        "shared child artifact gate",
        "no-synthetic-child-return rule",
        "complete orchestrator-owned fenced YAML `MAIN_CONTEXT_PLAN_RETURN`",
        "gpd return skeleton --role planner --status completed",
    )
    _assert_absent(
        source,
        "plan-phase does not synthesize files-only JSON planner return",
        "printf '```yaml\\ngpd_return:\\n'",
        '{"gpd_return":{"files_written"',
        "${PLANNER_RETURN:-$(",
    )


def test_plan_phase_manual_plan_fallback_cannot_skip_fresh_plan_validators() -> None:
    source = _plan_phase_authority_text()

    _assert_semantic(
        source,
        "plan-phase manual fallback still uses fresh plan gate",
        "Main-context plan",
        "manual bounded authoring branch",
        "FRESH_PLAN_FILES",
        "newly created path",
        "failing gate means `status: blocked`",
        "no `gpd:execute-phase` route",
    )
    assert "gpd validate plan-contract" in source
    assert "structured plan preflight validator" in source
    _assert_semantic(
        source,
        "plan-phase planned offer requires fresh plan validator gate",
        "PHASE PLANNED",
        "gpd:execute-phase",
        "fresh-plan validator gate",
    )


def test_plan_phase_captures_state_sensitive_spawn_returns() -> None:
    source = _plan_phase_authority_text()

    assert "PLANNER_RETURN=$(\ntask(" in source
    assert "CHECKER_RETURN=$(\ntask(" in source
    assert source.count("PLANNER_RETURN=$(\ntask(") >= 2


def test_plan_phase_researcher_checkpoint_path_is_a_fresh_continuation_handoff() -> None:
    source = _stage_text("research-routing.md")

    assert "## 5.1 Handle Researcher Checkpoint" in source
    _assert_semantic(
        source,
        "plan-phase researcher checkpoint fresh continuation",
        "fresh continuation handoff",
        "Phase {phase_number}: {phase_name}",
    )
    assert "<checkpoint_response>" in source
    assert 'description="Continue research Phase {phase_number}"' in source
    assert "{phase_dir}/{phase_number}-RESEARCH.md" in source
    assert "{phase_dir}/{phase}-RESEARCH.md" not in source
    _assert_semantic(
        source,
        "plan-phase researcher continuation reruns child gate",
        "After the continuation returns",
        "rerun the same researcher `child_gate`",
        "before advancing",
    )


def test_plan_phase_wrapper_stays_routing_only() -> None:
    command = (REPO_ROOT / "src/gpd/commands/plan-phase.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase/phase-bootstrap.md" in command
    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase.md" not in command
    assert (
        "Canonical contract schema and hard validation rules load later at the staged planner and checker handoffs"
        not in command
    )
    assert "For proof-bearing work, every proof-bearing plan must surface the theorem statement" not in command
