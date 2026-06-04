"""Semantic assertions for spawned-agent workflow contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from tests.lifecycle_contract_test_support import (
    artifact_paths as _gate_artifact_paths,
)
from tests.lifecycle_contract_test_support import (
    assert_forbidden_contract as _assert_forbidden,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)
from tests.lifecycle_contract_test_support import (
    child_gate_from_text,
)
from tests.workflow_authority_support import STAGED_WORKFLOW_AUTHORITY_NAMES, workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
WORKFLOW_PATHS = (
    WORKFLOWS_DIR / "quick.md",
    WORKFLOWS_DIR / "map-research.md",
    WORKFLOWS_DIR / "plan-phase.md",
    WORKFLOWS_DIR / "research-phase.md",
    WORKFLOWS_DIR / "execute-phase.md",
    WORKFLOWS_DIR / "verify-work.md",
    WORKFLOWS_DIR / "write-paper.md",
    WORKFLOWS_DIR / "respond-to-referees.md",
    WORKFLOWS_DIR / "new-project.md",
    WORKFLOWS_DIR / "new-milestone.md",
    WORKFLOWS_DIR / "parameter-sweep.md",
    WORKFLOWS_DIR / "literature-review.md",
    WORKFLOWS_DIR / "peer-review.md",
    WORKFLOWS_DIR / "validate-conventions.md",
    WORKFLOWS_DIR / "derive-equation.md",
    WORKFLOWS_DIR / "explain.md",
    WORKFLOWS_DIR / "audit-milestone.md",
    WORKFLOWS_DIR / "debug.md",
)

RUNTIME_NOTE_INCLUDE_FRAGMENT = "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md"
RUNTIME_NOTE_BODY_FRAGMENT = "Spawn a fresh subagent for the task below."
MODEL_OMISSION_FRAGMENT = (
    "If `model` resolves to `null` or an empty string, omit it so the runtime uses its default model."
)
READONLY_FALSE_FRAGMENT = "readonly=false"
READONLY_RUNTIME_NOTE_FRAGMENT = "Always pass `readonly=false` for file-producing agents."


@dataclass(frozen=True, slots=True)
class TaskBlock:
    start: int
    text: str


def _read(path: Path) -> str:
    if path.parent == WORKFLOWS_DIR and path.stem in STAGED_WORKFLOW_AUTHORITY_NAMES:
        return workflow_authority_text(WORKFLOWS_DIR, path.stem)
    return path.read_text(encoding="utf-8")


def _child_gate(text: str, gate_id: str):
    return child_gate_from_text(text, gate_id)


def _artifact_paths(gate) -> tuple[str, ...]:
    return _gate_artifact_paths(gate)


def _extract_task_blocks(text: str) -> list[TaskBlock]:
    blocks: list[TaskBlock] = []
    cursor = 0

    while True:
        start = text.find("task(", cursor)
        if start == -1:
            return blocks

        line_start = text.rfind("\n", 0, start) + 1
        if text[line_start:start].lstrip().startswith("#"):
            cursor = start + len("task(")
            continue

        index = start + len("task(")
        depth = 1
        quote: str | None = None
        escaped = False

        while index < len(text):
            char = text[index]

            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            else:
                if char in {'"', "'"}:
                    quote = char
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        blocks.append(TaskBlock(start=start, text=text[start : index + 1]))
                        cursor = index + 1
                        break

            index += 1
        else:
            raise AssertionError("Unterminated task() block")


def _task_agent_name(task_text: str) -> str:
    match = re.search(r'subagent_type="([^"]+)"', task_text)
    assert match is not None, f"task() block missing subagent_type:\n{task_text}"
    return match.group(1)


def _task_is_commented_out(text: str, start: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    line_prefix = text[line_start:start].lstrip()
    return line_prefix.startswith("#")


def _task_blocks_by_agent(path: Path, agent_name: str) -> list[TaskBlock]:
    return [block for block in _extract_task_blocks(_read(path)) if f'subagent_type="{agent_name}"' in block.text]


def _find_single_task(path: Path, agent_name: str) -> TaskBlock:
    matches = _task_blocks_by_agent(path, agent_name)
    assert matches, f"{path.relative_to(REPO_ROOT)} missing task() for {agent_name}"
    return matches[0]


def _assert_runtime_note_include(path: Path) -> None:
    content = _read(path)
    if RUNTIME_NOTE_INCLUDE_FRAGMENT not in content and _manifest_owns_runtime_note(path):
        return
    _assert_machine(content, f"{path.relative_to(REPO_ROOT)} runtime note include", RUNTIME_NOTE_INCLUDE_FRAGMENT)
    _assert_forbidden(
        content,
        f"{path.relative_to(REPO_ROOT)} no duplicated runtime note body",
        RUNTIME_NOTE_BODY_FRAGMENT,
    )


def _assert_expanded_runtime_note(path: Path) -> None:
    if RUNTIME_NOTE_INCLUDE_FRAGMENT not in _read(path) and _manifest_owns_runtime_note(path):
        return
    content = expand_at_includes(_read(path), REPO_ROOT / "src/gpd", "/runtime/")
    _assert_machine(
        content,
        f"{path.relative_to(REPO_ROOT)} expanded runtime note",
        RUNTIME_NOTE_BODY_FRAGMENT,
        MODEL_OMISSION_FRAGMENT,
        READONLY_RUNTIME_NOTE_FRAGMENT,
    )


def _manifest_owns_runtime_note(path: Path) -> bool:
    manifest_path = path.with_name(f"{path.stem}-stage-manifest.json")
    if not manifest_path.exists():
        return False
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for stage in payload.get("stages", ()):
        if RUNTIME_NOTE_INCLUDE_FRAGMENT.removeprefix("@{GPD_INSTALL_DIR}/") in stage.get("loaded_authorities", ()):
            return True
        for conditional in stage.get("conditional_authorities", ()):
            if RUNTIME_NOTE_INCLUDE_FRAGMENT.removeprefix("@{GPD_INSTALL_DIR}/") in conditional.get("authorities", ()):
                return True
    return False


def _assert_prompt_bootstrap_in_content(content: str, agent_name: str) -> None:
    _assert_machine(
        content,
        f"{agent_name} role prompt bootstrap",
        f"First, read {{GPD_AGENTS_DIR}}/{agent_name}.md for your role and instructions.",
    )


def _extract_output_paths(task: TaskBlock) -> list[str]:
    return re.findall(r"Write to:\s*([^\s`]+)", task.text)


def _assert_spawn_contract(
    task: TaskBlock | str,
    expected_outputs: tuple[str, ...],
    *,
    shared_state_policy: str = "return_only",
    expected_write_paths: tuple[str, ...] = (),
) -> None:
    text = task.text if isinstance(task, TaskBlock) else task

    _assert_machine(
        text,
        "spawn contract structured fields",
        "<spawn_contract>",
        "write_scope:",
        "expected_artifacts:",
        f"shared_state_policy: {shared_state_policy}",
    )
    for output in expected_outputs:
        _assert_machine(text, f"spawn contract expected output {output}", output)
    for path in expected_write_paths:
        _assert_machine(text, f"spawn contract write path {path}", path)


def test_agent_delegation_reference_defines_canonical_task_contract() -> None:
    path = REFERENCES_DIR / "orchestration" / "agent-delegation.md"
    content = _read(path)
    blocks = [
        block
        for block in _extract_task_blocks(content)
        if 'subagent_type="gpd-{agent}"' in block.text and 'description="{short description}"' in block.text
    ]

    assert len(blocks) == 1
    canonical = blocks[0].text

    _assert_machine(
        canonical,
        "canonical agent delegation task parameters",
        'subagent_type="gpd-{agent}"',
        'model="{AGENT_MODEL}"',
        READONLY_FALSE_FRAGMENT,
        'description="{short description}"',
        "First, read {GPD_AGENTS_DIR}/gpd-{agent}.md for your role and instructions.",
    )
    _assert_semantic(
        content,
        "agent-delegation task and write-scope contract",
        "Do not use `@...` references inside task() prompt strings.",
        "Assign an explicit write scope for every subagent.",
        "Always set `readonly=false` for file-producing agents.",
        "Fresh context:",
        "Write-scope isolation:",
    )
    _assert_semantic(
        content,
        "agent-delegation lifecycle gates",
        "Blocking completion semantics:",
        "Success-path artifact gate:",
        "Return-envelope parity:",
    )
    _assert_machine(
        content,
        "agent delegation child artifact gate fields",
        "child-artifact-gate.md",
        "write_scope:",
        "expected_artifacts:",
        "shared_state_policy:",
    )
    _assert_semantic(content, "agent delegation runtime wording", "effective installed runtime")
    _assert_forbidden(content, "agent delegation no skill file runtime reference", "SKILL.md")
    _assert_semantic(
        content,
        "agent-delegation no synthesized child return recovery",
        "Artifact Recovery Protocol",
        "literal child-authored file contents",
        "main orchestrator context",
        "Do not synthesize, patch, or paste a child `gpd_return`",
        "missing or invalid `gpd_return` envelope",
        "Re-run the child artifact gate before accepting success",
        "Never silently proceed",
    )


def test_representative_workflows_keep_runtime_note_and_agent_prompt_bootstrap() -> None:
    coverage = {
        "quick.md": ["gpd-planner", "gpd-executor"],
        "map-research.md": ["gpd-research-mapper"],
        "write-paper.md": ["gpd-paper-writer", "gpd-bibliographer"],
        "respond-to-referees.md": ["gpd-paper-writer"],
        "validate-conventions.md": ["gpd-consistency-checker"],
        "new-project.md": [
            "gpd-project-researcher",
            "gpd-research-synthesizer",
            "gpd-roadmapper",
            "gpd-notation-coordinator",
        ],
        "verify-work.md": ["gpd-check-proof", "gpd-verifier"],
        "derive-equation.md": ["gpd-check-proof"],
        "explain.md": ["gpd-explainer"],
        "audit-milestone.md": ["gpd-consistency-checker", "gpd-referee"],
        "debug.md": ["gpd-debugger"],
    }

    for workflow_name, agent_names in coverage.items():
        path = WORKFLOWS_DIR / workflow_name
        content = _read(path)
        _assert_runtime_note_include(path)
        _assert_expanded_runtime_note(path)
        expanded_content = expand_at_includes(content, REPO_ROOT / "src/gpd", "/runtime/")
        if workflow_name == "explain.md":
            _assert_machine(
                content,
                "explain workflow filled prompt task parameters",
                "prompt=filled_prompt",
                'subagent_type="gpd-explainer"',
                'description="Explain {slug}"',
            )
            continue
        for agent_name in agent_names:
            _assert_prompt_bootstrap_in_content(expanded_content, agent_name)


def test_every_workflow_task_block_carries_runtime_delegation_note_and_bootstrap() -> None:
    for path in WORKFLOW_PATHS:
        if "task(" in _read(path):
            _assert_runtime_note_include(path)


def test_new_project_roadmapper_spawn_contract_uses_direct_shared_state_and_artifact_gate() -> None:
    content = _read(WORKFLOWS_DIR / "new-project.md")
    task = _find_single_task(WORKFLOWS_DIR / "new-project.md", "gpd-roadmapper")
    gate = _child_gate(content, "project_roadmapper")

    _assert_spawn_contract(
        content,
        (
            "GPD/ROADMAP.md",
            "GPD/STATE.md",
        ),
        shared_state_policy="direct",
        expected_write_paths=(
            "GPD/ROADMAP.md",
            "GPD/STATE.md",
            "GPD/REQUIREMENTS.md",
        ),
    )
    assert _artifact_paths(gate) == ("GPD/ROADMAP.md", "GPD/STATE.md", "GPD/REQUIREMENTS.md")
    assert gate.allowed_roots == ("GPD",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$ROADMAPPER_HANDOFF_STARTED_AT"
    _assert_semantic(
        content,
        "new-project roadmapper child gate before roadmap acceptance",
        "Run the child gate before displaying, approving, or committing the roadmap.",
    )
    _assert_machine(
        task.text,
        "new-project roadmapper task parameters and state contract",
        'subagent_type="gpd-roadmapper"',
        'model="{roadmapper_model}"',
        "gpd_return.files_written",
        "GPD/REQUIREMENTS.md",
    )
    _assert_semantic(
        task.text,
        "new-project roadmapper direct write and completion gate",
        "Write files immediately (ROADMAP.md, STATE.md, update REQUIREMENTS.md traceability)",
        "do not rely on runtime completion text alone.",
    )
    _assert_machine(
        content,
        "new-project roadmapper handoff artifacts validation command",
        "gpd validate handoff-artifacts - --expected GPD/ROADMAP.md --expected GPD/STATE.md --expected GPD/REQUIREMENTS.md",
    )


def test_new_milestone_roadmapper_spawn_contract_keeps_return_only_shared_state_and_explicit_contract_inputs() -> None:
    content = _read(WORKFLOWS_DIR / "new-milestone.md")
    task = _find_single_task(WORKFLOWS_DIR / "new-milestone.md", "gpd-roadmapper")
    gate = _child_gate(content, "milestone_roadmapper")

    _assert_spawn_contract(
        content,
        (
            "GPD/ROADMAP.md",
            "GPD/REQUIREMENTS.md",
        ),
        shared_state_policy="return_only",
        expected_write_paths=(
            "GPD/ROADMAP.md",
            "GPD/REQUIREMENTS.md",
        ),
    )
    assert _artifact_paths(gate) == ("GPD/ROADMAP.md", "GPD/REQUIREMENTS.md")
    assert gate.allowed_roots == ("GPD",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$MILESTONE_ROADMAPPER_HANDOFF_STARTED_AT"
    _assert_machine(
        task.text,
        "new-milestone roadmapper contract context placeholders",
        "<contract_context>",
        "Project contract gate: {project_contract_gate}",
        "Project contract load info: {project_contract_load_info}",
        "Project contract validation: {project_contract_validation}",
        "Contract intake: {contract_intake}",
        "Effective reference intake: {effective_reference_intake}",
        "Reference artifact file handles: {reference_artifact_files}",
        "Do not write STATE.md directly",
    )
    _assert_machine(
        content,
        "new-milestone roadmapper artifact gate fields",
        "expected_artifacts:",
        'freshness_marker: "after $MILESTONE_ROADMAPPER_HANDOFF_STARTED_AT"',
        "GPD/REQUIREMENTS.md",
        "gpd validate handoff-artifacts - --expected GPD/ROADMAP.md --expected GPD/REQUIREMENTS.md",
    )
    _assert_semantic(
        content,
        "new-milestone roadmapper applies state after artifact gate",
        "artifact gate passes, apply accepted state changes in the main workflow",
    )


def test_debug_workflow_and_command_share_the_same_one_shot_debugger_contract() -> None:
    workflow = _read(WORKFLOWS_DIR / "debug.md")
    command = _read(COMMANDS_DIR / "debug.md")
    expanded_workflow = expand_at_includes(workflow, REPO_ROOT / "src/gpd", "/runtime/")

    assert workflow.count('subagent_type="gpd-debugger"') == 1
    assert workflow.count("readonly=false") == 1
    _assert_machine(workflow, "debug workflow task description", 'description="Investigate: {truth_short}"')
    _assert_semantic(
        expanded_workflow,
        "debug workflow expanded one-shot runtime handoff",
        "Spawn a fresh subagent for the task below.",
        "one-shot handoff",
        "Always pass `readonly=false` for file-producing agents.",
    )

    assert command.count('subagent_type="gpd-debugger"') == 1
    _assert_forbidden(
        command,
        "debug command wrapper no raw task fields",
        "readonly=false",
        'description="Debug {slug}"',
        'description="Continue debug {slug}"',
    )
    _assert_machine(command, "debug command session artifact path", "Debug session artifact: `GPD/debug/{slug}.md`")
    _assert_semantic(
        command,
        "debug command verifies session artifact before confirmed root cause",
        "verifies the debug session artifact before treating a root cause as confirmed",
    )


def test_quick_and_write_paper_gate_handoffs_on_expected_artifacts() -> None:
    quick = _read(WORKFLOWS_DIR / "quick.md")
    write_paper = _read(WORKFLOWS_DIR / "write-paper.md")

    _assert_machine(
        quick,
        "quick planner and executor artifact gate fields",
        "role=`gpd-planner`",
        "expected=`${QUICK_DIR}/${next_num}-PLAN.md`",
        "Verify summary exists at `${QUICK_DIR}/${next_num}-SUMMARY.md`",
        "role=`gpd-executor`",
        "expected=`${QUICK_DIR}/${next_num}-SUMMARY.md`",
    )
    _assert_semantic(
        quick,
        "quick executor child artifact gate semantics",
        "recovery evidence only",
        "Apply the executor child artifact gate before success",
    )
    _assert_machine(
        write_paper,
        "write-paper section writer artifact path",
        'id: "write_paper_section_writer"',
        "${PAPER_DIR}/{section_path}.tex",
    )
    _assert_semantic(
        write_paper,
        "write-paper section writer artifact gate semantics",
        "success artifact gate\nfor each section only after the tuple passes",
    )


def test_plan_phase_reloads_research_from_disk_and_keeps_checker_advisory() -> None:
    content = workflow_authority_text(WORKFLOWS_DIR, "plan-phase")

    _assert_semantic(
        content,
        "plan-phase research reload and advisory checker semantics",
        "Verify RESEARCH.md was written (guard against silent researcher failure):",
        "After it passes, re-read the research file from disk",
        "the earlier init `research_content` is no longer current",
        "Proceed without plan verification only for non-proof-bearing plan sets",
        "Approved plans from partial approval are final",
    )


def test_execute_phase_requires_state_return_envelope_and_handoff_spot_checks() -> None:
    content = _read(WORKFLOWS_DIR / "execute-phase.md")
    executor = _find_single_task(WORKFLOWS_DIR / "execute-phase.md", "gpd-executor")

    _assert_semantic(
        executor.text,
        "execute-phase executor return-only state update envelope",
        "Return state updates (position, decisions, metrics) in your response -- do NOT write STATE.md directly.",
        "State updates returned (NOT written to STATE.md directly)",
    )
    _assert_semantic(
        content,
        "execute-phase executor artifact gate and partial evidence",
        "Executor subagents must not write `GPD/STATE.md` directly.",
        "run the local child artifact gate before success",
        "git commits are partial evidence only",
    )
    _assert_machine(content, "execute-phase pre-execution specialist gate", "pre_execution_specialists")
    _assert_forbidden(
        content,
        "execute-phase no commented specialist task scaffolds",
        '# task(subagent_type="gpd-notation-coordinator"',
        '# task(subagent_type="gpd-experiment-designer"',
    )


def test_execute_phase_initial_verification_spawns_verifier_agent() -> None:
    content = _read(WORKFLOWS_DIR / "execute-phase.md")
    start = content.index('<step name="spawn_verifier">')
    end = content.index('<step name="verifier_child_gate">', start)
    verification_step = content[start:end]
    verifier_tasks = [
        block for block in _extract_task_blocks(verification_step) if 'subagent_type="gpd-verifier"' in block.text
    ]

    assert len(verifier_tasks) == 1
    verifier = verifier_tasks[0].text
    _assert_machine(
        verifier,
        "execute-phase verifier spawn parameters",
        "readonly=false",
        'description="Verify Phase {PHASE_NUMBER} goal"',
        "{phase_dir}/{phase_number}-VERIFICATION.md",
        "<spawn_contract>",
        "gpd_return` envelope",
    )
    _assert_forbidden(verifier, "execute-phase verifier no reverification description", "Re-verify Phase")


def test_parameter_sweep_executor_uses_spawn_contract_and_return_only_state_updates() -> None:
    path = WORKFLOWS_DIR / "parameter-sweep.md"
    executor = _find_single_task(path, "gpd-executor")

    _assert_semantic(
        executor.text,
        "parameter-sweep executor return-only state update",
        "Return state updates in your response -- do NOT write STATE.md directly.",
        "State updates returned (NOT written to STATE.md directly) only when authoritative phase-backed persistence is actually in scope",
    )
    _assert_machine(
        executor.text,
        "parameter-sweep executor spawn contract artifacts",
        "<spawn_contract>",
        "write_scope:",
        "expected_artifacts:",
        "shared_state_policy: return_only",
        "${SWEEP_RESULTS_DIR}/point-{PADDED_INDEX}.json",
        "${SWEEP_DOC_DIR}/sweep-{PADDED_INDEX}-SUMMARY.md",
    )
    _assert_forbidden(
        executor.text,
        "parameter-sweep executor stale artifact root",
        "${SWEEP_ARTIFACT_DIR}/results/point-{PADDED_INDEX}.json",
    )


def test_research_phase_verifies_research_artifact_before_accepting_handoff() -> None:
    content = _read(WORKFLOWS_DIR / "research-phase.md")

    _assert_machine(
        content,
        "research-phase child artifact gate fields",
        "Child artifact gate: apply `references/orchestration/child-artifact-gate.md`",
        "role=`gpd-phase-researcher`",
        "expected=`{phase_dir}/{phase_number}-RESEARCH.md`",
        "allowed_root=`{phase_dir}`",
        "<spawn_contract>",
        "expected_artifacts:",
        "shared_state_policy: return_only",
    )
    _assert_semantic(
        content,
        "research-phase artifact gate before accepting handoff",
        "Artifact gate:",
        "If the artifact is missing, unreadable, or absent from `gpd_return.files_written`",
    )


def test_new_project_parallel_researchers_write_to_disjoint_artifacts() -> None:
    path = WORKFLOWS_DIR / "new-project.md"
    tasks = _task_blocks_by_agent(path, "gpd-project-researcher")
    outputs = {output for task in tasks for output in _extract_output_paths(task)}

    expected = {
        "GPD/literature/PRIOR-WORK.md",
        "GPD/literature/METHODS.md",
        "GPD/literature/COMPUTATIONAL.md",
        "GPD/literature/PITFALLS.md",
    }

    assert expected <= outputs
    assert len(outputs) == len(set(outputs))
    assert len(tasks) == 4

    for task in tasks:
        task_outputs = tuple(_extract_output_paths(task))
        assert len(task_outputs) == 1
        _assert_spawn_contract(task, task_outputs)

    content = _read(path)
    synth = _find_single_task(path, "gpd-research-synthesizer")
    _assert_spawn_contract(synth, ("GPD/literature/SUMMARY.md",))
    _assert_machine(
        synth.text,
        "new-project synthesizer source and output paths",
        "GPD/PROJECT.md",
        "GPD/config.json",
        "GPD/literature/SUMMARY.md (if re-synthesizing an existing survey)",
    )
    _assert_machine(
        content,
        "new-project literature child gates",
        'child_gate:\n  id: "literature_scouts"',
        'child_gate:\n  id: "literature_synthesizer"',
        "gpd validate handoff-artifacts - --expected GPD/literature/SUMMARY.md",
    )
    _assert_semantic(
        content,
        "new-project literature survey no partial success",
        "Do not proceed with a partial literature survey",
    )


def test_map_research_parallel_mappers_use_spawn_contracts_and_return_only_artifacts() -> None:
    path = WORKFLOWS_DIR / "map-research.md"
    content = _read(path)
    tasks = _task_blocks_by_agent(path, "gpd-research-mapper")
    outputs = {output for task in tasks for output in _extract_output_paths(task)}

    expected = {
        "GPD/research-map/FORMALISM.md",
        "GPD/research-map/REFERENCES.md",
        "GPD/research-map/ARCHITECTURE.md",
        "GPD/research-map/STRUCTURE.md",
        "GPD/research-map/CONVENTIONS.md",
        "GPD/research-map/VALIDATION.md",
        "GPD/research-map/CONCERNS.md",
    }

    assert expected <= outputs
    assert len(outputs) == len(set(outputs))
    assert len(tasks) == 4
    assert content.count("<spawn_contract>") >= 4
    _assert_forbidden(content, "map-research no stale task prompt prose", "task tool parameters:", "Prompt:")
    _assert_semantic(
        content,
        "map-research routes on status and files-written artifacts",
        "gpd_return.status",
        "gpd_return.files_written",
        "expected artifacts",
        "before accepting the run",
    )
    _assert_forbidden(content, "map-research no direct config lookup", "gpd --raw config get research_mode")
    _assert_machine(
        content,
        "map-research research mode from bootstrap init",
        'RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)',
    )

    for task in tasks:
        assert task.text.startswith("task(\n  subagent_type=")
        _assert_machine(task.text, "map-research task background flag", "run_in_background=true")
        task_outputs = tuple(_extract_output_paths(task))
        assert len(task_outputs) in (1, 2)
        _assert_spawn_contract(task, task_outputs)


def test_new_project_roadmapper_uses_spawn_contract_and_artifact_gate() -> None:
    path = WORKFLOWS_DIR / "new-project.md"
    content = _read(path)
    roadmapper = _find_single_task(path, "gpd-roadmapper")
    gate = _child_gate(content, "project_roadmapper")

    _assert_spawn_contract(roadmapper, ("GPD/ROADMAP.md", "GPD/STATE.md"), shared_state_policy="direct")
    _assert_machine(
        roadmapper.text,
        "new-project roadmapper state and reference paths",
        "GPD/REQUIREMENTS.md",
        "gpd_return.files_written",
        "GPD/literature/SUMMARY.md",
        "allowed_paths:",
    )
    assert _artifact_paths(gate) == ("GPD/ROADMAP.md", "GPD/STATE.md", "GPD/REQUIREMENTS.md")
    _assert_semantic(
        content,
        "new-project roadmapper gate and retry semantics",
        "Run the child gate before displaying, approving, or committing the roadmap.",
        "retry once; partial writes are diagnostics only",
    )


def test_new_project_notation_coordinator_uses_explicit_model_and_spawn_contract() -> None:
    path = WORKFLOWS_DIR / "new-project.md"
    content = _read(path)
    start = content.index("## 8.5. Establish Conventions")
    end = content.index("**Notation-coordinator child gate:**", start)
    notation_section = content[start:end]

    assert _find_single_task(path, "gpd-notation-coordinator")
    _assert_spawn_contract(notation_section, ("GPD/CONVENTIONS.md",), shared_state_policy="direct")
    _assert_machine(
        notation_section,
        "new-project notation coordinator auto spawn contract",
        "activation: mode == auto",
        'model="$NOTATION_MODEL"',
        "<spawn_contract_interactive>",
        "write_scope:\n  mode: no_write",
        "status: checkpoint",
        "gpd convention set",
    )
    _assert_forbidden(
        notation_section, "new-project notation coordinator stale model placeholder", 'model="{NOTATION_MODEL}"'
    )
    _assert_machine(
        content,
        "new-project notation convention set commands",
        "`natural` or `mostly_minus`",
        'gpd convention set units "$RESOLVED_UNITS"',
        'gpd convention set metric_signature "$RESOLVED_METRIC"',
    )
    _assert_semantic(content, "new-project notation no hardcoded conventions", "Do not hardcode")


def test_validate_conventions_uses_one_shot_delegation_and_artifact_gating_for_resolution() -> None:
    content = _read(WORKFLOWS_DIR / "validate-conventions.md")

    assert content.count('subagent_type="gpd-consistency-checker"') == 1
    assert content.count('subagent_type="gpd-notation-coordinator"') == 0
    _assert_semantic(
        content,
        "validate-conventions one-shot checker lifecycle",
        "Thin wrapper around `gpd-consistency-checker`",
        "Spawn `gpd-consistency-checker` once",
        "one-shot handoff",
        "canonical `gpd_return.status`",
        "Do not route on checker-local text markers or headings.",
    )
    _assert_machine(content, "validate-conventions coordinator agent visible", "gpd-notation-coordinator")
    _assert_semantic(
        content,
        "validate-conventions coordinator and files-written gate",
        "next_actions",
        "gpd-notation-coordinator",
        "same scope",
        "coordinator owns the repair policy",
        "gpd_return.status: completed",
        "gpd_return.files_written",
    )


def test_new_milestone_research_and_roadmapper_gate_success_path_artifacts() -> None:
    content = _read(WORKFLOWS_DIR / "new-milestone.md")
    gate = _child_gate(content, "milestone_roadmapper")

    assert content.count("<spawn_contract>") >= 3
    assert _artifact_paths(gate) == ("GPD/ROADMAP.md", "GPD/REQUIREMENTS.md")
    _assert_machine(
        content,
        "new-milestone literature and roadmapper gates",
        'child_gate:\n  id: "milestone_literature_scouts"',
        'child_gate:\n  id: "milestone_literature_synthesizer"',
        "gpd validate handoff-artifacts - --expected GPD/ROADMAP.md --expected GPD/REQUIREMENTS.md",
        "GPD/REQUIREMENTS.md",
        "require-files-written",
        "shared_state_policy: return_only",
    )
    _assert_semantic(
        content,
        "new-milestone applies state after artifact gate",
        "artifact gate passes, apply accepted state changes in the main workflow",
    )

    _assert_machine(
        content,
        "new-milestone subagent and artifact paths",
        'subagent_type="gpd-project-researcher"',
        "GPD/literature/{FILE}",
        "expected_artifacts:",
        "PRIOR-WORK.md",
        "METHODS.md",
        "COMPUTATIONAL.md",
        "PITFALLS.md",
        'subagent_type="gpd-research-synthesizer"',
        "GPD/literature/SUMMARY.md",
        'subagent_type="gpd-roadmapper"',
        "GPD/ROADMAP.md",
        "GPD/STATE.md",
    )
    _assert_semantic(
        content,
        "new-milestone direct state write not success proof",
        "direct roadmapper edit to\n`GPD/STATE.md` is not success proof.",
    )


def test_peer_review_stages_use_fresh_context_and_stage_artifacts() -> None:
    path = WORKFLOWS_DIR / "peer-review.md"
    content = _read(path)

    _assert_semantic(content, "peer-review fresh stage contexts", "Each stage runs in a fresh subagent context")
    for agent_name in (
        "gpd-review-reader",
        "gpd-review-literature",
        "gpd-review-math",
        "gpd-check-proof",
        "gpd-review-physics",
        "gpd-review-significance",
    ):
        _assert_machine(content, f"peer-review role {agent_name}", f"role: {agent_name}")
    _assert_machine(content, "peer-review referee spawn", "Spawn `gpd-referee`")
    for artifact in (
        "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-reader{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-literature{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-math{round_suffix}.json",
        "${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md",
        "${REVIEW_ROOT}/STAGE-physics{round_suffix}.json",
        "${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json",
        "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
        "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md",
        "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex",
    ):
        _assert_machine(content, f"peer-review artifact {artifact}", artifact)


def test_referee_response_template_uses_round_suffixed_decision_artifacts() -> None:
    content = _read(TEMPLATES_DIR / "paper" / "referee-response.md")

    _assert_machine(
        content,
        "referee response round-suffixed artifacts",
        "REFEREE-DECISION{round_suffix}.json",
        "REVIEW-LEDGER{round_suffix}.json",
        "REFEREE-REPORT{round_suffix}.md",
    )
    _assert_forbidden(content, "referee response no unsuffixed report", "REFEREE-REPORT.md")


def test_all_workflow_task_blocks_include_readonly_false() -> None:
    """Every task() block that spawns a GPD agent must include readonly=false.

    Without this, some runtimes default subagents to read-only mode where
    file writes silently fail -- the agent reports success but no files are
    persisted to disk.
    """
    exclusions = {"execute-plan.md"}
    failures: list[str] = []
    for workflow_path in sorted(WORKFLOWS_DIR.glob("*.md")):
        if workflow_path.name in exclusions:
            continue
        blocks = _extract_task_blocks(_read(workflow_path))
        for block in blocks:
            if 'subagent_type="gpd-' not in block.text:
                continue
            if READONLY_FALSE_FRAGMENT not in block.text:
                agent = "unknown"
                match = re.search(r'subagent_type="(gpd-[^"]+)"', block.text)
                if match:
                    agent = match.group(1)
                failures.append(f"{workflow_path.name}:{block.start} ({agent})")

    assert not failures, "task() blocks missing readonly=false:\n  " + "\n  ".join(failures)


def test_debug_subagent_template_continuations_use_explicit_file_reads() -> None:
    content = _read(TEMPLATES_DIR / "debug-subagent-prompt.md")

    _assert_machine(content, "debug continuation explicit file read", "Read the file at GPD/debug/{slug}.md")
    _assert_forbidden(content, "debug continuation no at-reference file read", "@GPD/debug/{slug}.md")
    assert content.count("readonly=false") == 2


def test_continuation_template_file_producing_example_sets_readonly_false() -> None:
    content = _read(TEMPLATES_DIR / "continuation-prompt.md")

    _assert_machine(
        content, "continuation template file-producing task readonly", 'subagent_type="gpd-executor"', "readonly=false"
    )
