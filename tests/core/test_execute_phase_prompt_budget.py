"""Prompt budget assertions for the `execute-phase` startup surface."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from gpd.core.prompt_diagnostics import build_prompt_surface_report, report_to_dict
from tests.assertion_taxonomy_support import (
    assert_prompt_contracts,
    fragment_count,
    machine_exact,
    semantic_anchor,
    semantic_concept,
)
from tests.prompt_metrics_support import measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
EXECUTE_PHASE_FIRST_TURN_CHAR_BUDGET = 6_707
EXECUTE_PHASE_STAGE_EAGER_CHAR_BUDGET = 95_000
SPLIT_WAVE_AND_VERIFICATION_STAGES = (
    "wave_dispatch",
    "executor_dispatch",
    "proof_critic_dispatch",
    "wave_return_checkpoint",
    "wave_failure_menu",
    "aggregate_and_verify",
    "verification_handoff",
    "gap_reverification",
    "consistency_check",
)
EXECUTE_PHASE_STAGE_FILES = (
    "phase-bootstrap.md",
    "phase-classification.md",
    "wave-planning.md",
    "pre-execution-specialists.md",
    "wave-dispatch.md",
    "executor-dispatch.md",
    "proof-critic-dispatch.md",
    "wave-return-checkpoint.md",
    "wave-failure-menu.md",
    "checkpoint-resume.md",
    "aggregate-and-verify.md",
    "verification-handoff.md",
    "gap-reverification.md",
    "consistency-check.md",
    "closeout.md",
)
COMMAND_REQUIRED_MACHINE_FRAGMENTS = (
    "@{GPD_INSTALL_DIR}/workflows/execute-phase/phase-bootstrap.md",
    "<arguments>",
)
COMMAND_FORBIDDEN_MACHINE_FRAGMENTS = (
    "@{GPD_INSTALL_DIR}/workflows/execute-phase.md",
    "<inline_guidance>",
    "@{GPD_INSTALL_DIR}/references/ui/ui-brand.md",
    "@{GPD_INSTALL_DIR}/templates/summary.md",
    "@{GPD_INSTALL_DIR}/templates/contract-results-schema.md",
    "staged_loading.eager_authorities",
)
COMMAND_STAGE_GUIDANCE_FRAGMENTS = (
    "Read the included bootstrap authority first.",
    "Later stage loading and field",
    "manifest-owned by the staged workflow",
)


def _stage_text(stage_file: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / stage_file).read_text(encoding="utf-8")


def _combined_stage_text() -> str:
    return "\n\n".join(_stage_text(stage_file) for stage_file in EXECUTE_PHASE_STAGE_FILES)


@lru_cache
def _execute_phase_stage_diagnostics() -> dict[str, object]:
    payload = report_to_dict(
        build_prompt_surface_report(
            REPO_ROOT,
            surfaces=("command",),
            include_tests=False,
            include_runtime_projections=False,
        )
    )
    workflows = payload["stage_diagnostics"]
    assert isinstance(workflows, list)
    for workflow in workflows:
        assert isinstance(workflow, dict)
        if workflow.get("workflow_id") == "execute-phase":
            return workflow
    raise AssertionError("execute-phase staged diagnostics were not reported")


def test_execute_phase_command_stays_thin_and_only_eagerly_loads_bootstrap_authority() -> None:
    command_path = COMMANDS_DIR / "execute-phase.md"
    command_text = command_path.read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        command_path,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert metrics.expanded_char_count <= EXECUTE_PHASE_FIRST_TURN_CHAR_BUDGET
    assert_prompt_contracts(
        command_text,
        machine_exact("execute phase required command fragments", COMMAND_REQUIRED_MACHINE_FRAGMENTS),
        machine_exact("execute phase forbidden eager fragments", COMMAND_FORBIDDEN_MACHINE_FRAGMENTS, mode="absent"),
        semantic_anchor("execute phase staged command guidance", COMMAND_STAGE_GUIDANCE_FRAGMENTS),
    )


def test_execute_phase_stage_eager_budgets_stay_below_phase4_caps() -> None:
    workflow = _execute_phase_stage_diagnostics()
    assert workflow["first_turn_char_count"] <= EXECUTE_PHASE_FIRST_TURN_CHAR_BUDGET
    assert workflow["violation_count"] == 0

    stages = workflow["stages"]
    assert isinstance(stages, list)
    stage_by_id = {stage["stage_id"]: stage for stage in stages if isinstance(stage, dict)}

    for stage_id in SPLIT_WAVE_AND_VERIFICATION_STAGES:
        stage = stage_by_id[stage_id]
        observed = stage["eager_char_count"]
        assert isinstance(observed, int)
        assert observed < EXECUTE_PHASE_STAGE_EAGER_CHAR_BUDGET, (
            f"{stage_id} eager chars exceeded Phase 4 cap: "
            f"observed={observed} max<{EXECUTE_PHASE_STAGE_EAGER_CHAR_BUDGET}"
        )

    assert stage_by_id["wave_dispatch"]["eager_char_count"] < EXECUTE_PHASE_STAGE_EAGER_CHAR_BUDGET
    assert stage_by_id["aggregate_and_verify"]["eager_char_count"] < EXECUTE_PHASE_STAGE_EAGER_CHAR_BUDGET


def test_execute_phase_workflow_refreshes_stage_context_in_order() -> None:
    workflow_text = _combined_stage_text()

    assert 'PHASE_ARG=""' in workflow_text
    assert "EXECUTE_FLAGS=()" in workflow_text
    assert "GAPS_ONLY=false" in workflow_text
    assert '[ "$flag" = "--gaps-only" ] && GAPS_ONLY=true' in workflow_text
    assert '*) [ -z "$PHASE_ARG" ] && PHASE_ARG="$token" ;;' in workflow_text
    bootstrap_load = 'BOOTSTRAP_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage phase_bootstrap'
    wave_planning_load = 'WAVE_PLANNING_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_planning)'
    pre_execution_load = (
        'PRE_EXECUTION_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage pre_execution_specialists)'
    )
    wave_dispatch_load = 'WAVE_DISPATCH_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_dispatch)'
    executor_dispatch_load = 'EXECUTOR_DISPATCH_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage executor_dispatch)'
    checkpoint_resume_load = (
        'CHECKPOINT_RESUME_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage checkpoint_resume)'
    )
    aggregate_load = (
        'AGGREGATE_VERIFY_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage aggregate_and_verify)'
    )
    verification_handoff_load = (
        'VERIFICATION_HANDOFF_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage verification_handoff)'
    )
    gap_reverification_load = 'GAP_REVERIFY_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage gap_reverification)'
    consistency_check_load = (
        'CONSISTENCY_CHECK_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage consistency_check)'
    )
    closeout_load = 'CLOSEOUT_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage closeout)'
    assert workflow_text.index("<step name=\"normalize_arguments\"") < workflow_text.index(bootstrap_load)
    ordered_loads = (
        bootstrap_load,
        wave_planning_load,
        pre_execution_load,
        wave_dispatch_load,
        executor_dispatch_load,
        checkpoint_resume_load,
        aggregate_load,
        verification_handoff_load,
        gap_reverification_load,
        consistency_check_load,
        closeout_load,
    )
    for stage_load in ordered_loads:
        assert stage_load in workflow_text
    for earlier, later in zip(ordered_loads, ordered_loads[1:], strict=False):
        assert workflow_text.index(earlier) < workflow_text.index(later)
    assert 'gpd --raw init execute-phase "${PHASE_ARG}" --include state,config' not in workflow_text
    assert 'gpd --raw init execute-phase "${PHASE_ARG}" --stage "${stage_name}" 2>/dev/null' not in workflow_text
    assert 'echo "stderr: $(cat "$INIT_STDERR")"' in workflow_text
    assert "`gap_closure`" in next(
        line for line in workflow_text.splitlines() if line.startswith("Parse JSON for `phase`, `plans[]`")
    )
    assert "`execute-plan.md` owns plan-local execution." in workflow_text
    assert_prompt_contracts(
        workflow_text,
        semantic_anchor(
            "execute phase gap-only and routing ownership guidance",
            (
                "If `$GAPS_ONLY` is true, also skip non-gap_closure plans.",
                "Gap-only execution uses `gpd:execute-phase {PHASE_NUMBER} --gaps-only` after gap plans exist.",
                "This stage owns only phase-wide routing and wave risk.",
            ),
        ),
    )
    assert "# task(subagent_type=\"gpd-notation-coordinator\"" not in workflow_text
    assert "# task(subagent_type=\"gpd-experiment-designer\"" not in workflow_text


def test_execute_phase_single_sources_runtime_delegation_boilerplate() -> None:
    workflow_text = _combined_stage_text()

    assert_prompt_contracts(
        workflow_text,
        fragment_count(
            "runtime delegation note include",
            "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md",
            expected_count=1,
        ),
        fragment_count(
            "runtime delegation convention heading",
            "Canonical runtime delegation convention for every `task()` block in this workflow:",
            expected_count=1,
        ),
        semantic_anchor(
            "runtime delegation shared note ownership",
            "The shared note owns runtime-neutral task construction and handoff conventions.",
        ),
        *semantic_concept(
            "old inline runtime delegation boilerplate",
            forbidden=(
                "Spawn a subagent for the task below. Adapt the `task()` call to your runtime's agent spawning "
                "mechanism.",
            ),
            match="exact",
        ),
    )
