"""Focused assertions for typed-return prompt cleanup."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import (
    FragmentMode,
    MatchMode,
    assert_prompt_contracts,
    machine_exact,
    semantic_anchor,
    semantic_concept,
)
from tests.core.test_spawn_contracts import _find_single_task
from tests.markdown_test_support import yaml_fence_bodies

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
ROADMAPPER = REPO_ROOT / "src/gpd/agents/gpd-roadmapper.md"
PLANNER = REPO_ROOT / "src/gpd/agents/gpd-planner.md"
PHASE_RESEARCHER = REPO_ROOT / "src/gpd/agents/gpd-phase-researcher.md"
EXECUTOR_COMPLETION = REPO_ROOT / "src/gpd/specs/references/execution/executor-completion.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_roadmapper_prompt_example_includes_complete_base_return_fields() -> None:
    roadmapper = _read(ROADMAPPER)
    envelope = yaml_fence_bodies(roadmapper)[0]

    assert_prompt_contracts(
        envelope,
        machine_exact(
            "roadmapper base return fields and extensions",
            (
                "gpd_return:",
                "status: completed",
                "files_written:\n    - GPD/ROADMAP.md\n    - GPD/STATE.md\n    - GPD/REQUIREMENTS.md",
                "issues: []",
                'next_actions:\n    - "gpd:plan-phase 01"',
                "phases_created: 4",
            ),
            mode=FragmentMode.ORDERED,
        ),
    )


def test_new_project_roadmapper_task_block_requires_requirements_freshness_and_named_files_written() -> None:
    roadmapper_task = _find_single_task(WORKFLOWS_DIR / "new-project.md", "gpd-roadmapper")

    assert_prompt_contracts(
        roadmapper_task.text,
        machine_exact(
            "new-project roadmapper freshness fields",
            ("gpd_return.files_written", "GPD/REQUIREMENTS.md"),
        ),
        semantic_anchor(
            "new-project roadmapper artifact freshness semantics",
            ("do not rely on runtime completion text alone.", "Write files first, then return."),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )


def test_planner_tangent_guidance_routes_on_typed_checkpoint_status() -> None:
    planner = _read(PLANNER)

    assert_prompt_contracts(
        planner,
        *semantic_concept(
            "planner tangent checkpoint routing",
            required=(
                "return `gpd_return.status: checkpoint` with the four options above instead of silently branching.",
                "create the recommended main-line plan only and set `gpd_return.status: checkpoint` when multiple live alternatives still matter.",
            ),
            forbidden=(
                "return `## CHECKPOINT REACHED` with the four options above instead of silently branching.",
                "return `## CHECKPOINT REACHED` when multiple live alternatives still matter.",
            ),
        ),
    )


def test_phase_researcher_machine_readable_return_is_typed_first() -> None:
    researcher = _read(PHASE_RESEARCHER)

    assert_prompt_contracts(
        researcher,
        machine_exact(
            "phase researcher typed return fields",
            (
                "gpd_return:",
                "status: completed",
                "files_written:\n    - GPD/phases/03-spectral-form-factor/03-RESEARCH.md",
                "issues: []",
                'next_actions:\n    - "gpd:plan-phase 03-spectral-form-factor"',
                "confidence: HIGH",
            ),
        ),
        *semantic_concept(
            "phase researcher presentation headings are not routing",
            required="Headings above are presentation only; route on gpd_return.status.",
            forbidden="Mapping: RESEARCH COMPLETE → completed, RESEARCH BLOCKED → blocked",
        ),
    )


def test_executor_completion_spawned_handoff_example_keeps_base_fields_and_extensions() -> None:
    completion = _read(EXECUTOR_COMPLETION)

    assert_prompt_contracts(
        completion,
        machine_exact(
            "executor completion base fields and extensions",
            (
                "status: completed",
                '    - "GPD/phases/XX-name/{phase}-{plan}-SUMMARY.md"',
                "issues:",
                "next_actions:",
                "state_updates:",
                "advance_plan: true",
                "update_progress: true",
                "record_metric:",
                "contract_updates:",
                "decisions:",
                "blockers:",
                "continuation_update:",
                "handoff:",
                "bounded_segment:",
            ),
        ),
        semantic_anchor(
            "executor completion omits orchestrator bookkeeping",
            "omit `recorded_at` and `recorded_by` from child returns",
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        machine_exact(
            "executor completion stale placeholders absent",
            ('recorded_at: "{timestamp}"', 'recorded_by: "gpd-executor"', "state_updates: [...]"),
            mode=FragmentMode.ABSENT,
        ),
        machine_exact(
            "executor completion continuation placeholder absent",
            "continuation_update: {...}",
            mode=FragmentMode.ABSENT,
        ),
    )
