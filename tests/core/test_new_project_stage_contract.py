"""Assertions for the staged `new-project` contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from gpd.core.child_handoff import ChildGateTuple, child_gate_tuple_from_payload
from tests import new_project_stage_contract_support as stage_contract_module
from tests.assertion_taxonomy_support import (
    FragmentMode,
    assert_prompt_contracts,
    machine_exact,
    semantic_anchor,
)
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
NEW_PROJECT_COMMAND_PATH = REPO_ROOT / "src" / "gpd" / "commands" / "new-project.md"
NEW_PROJECT_WORKFLOW_PATH = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "new-project.md"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXPECTED_STAGE_IDS = (
    "scope_intake",
    "scope_approval",
    "minimal_artifacts",
    "workflow_preferences",
    "project_artifacts",
    "literature_survey",
    "requirements_authoring",
    "roadmap_authoring",
    "conventions_handoff",
    "completion",
)


def _read_new_project_command() -> str:
    return NEW_PROJECT_COMMAND_PATH.read_text(encoding="utf-8")


def _read_new_project_workflow() -> str:
    return NEW_PROJECT_WORKFLOW_PATH.read_text(encoding="utf-8")


def _read_new_project_authority() -> str:
    return workflow_authority_text(WORKFLOWS_DIR, "new-project")


def _read_stage_authority(stage_file: str) -> str:
    return (WORKFLOWS_DIR / "new-project" / stage_file).read_text(encoding="utf-8")


def _tagged_block(text: str, tag: str) -> str:
    start = text.index(f"<{tag}>")
    end = text.index(f"</{tag}>", start)
    return text[start:end]


def _tagged_blocks(text: str, tag: str) -> list[str]:
    blocks: list[str] = []
    cursor = 0
    while True:
        start = text.find(f"<{tag}>", cursor)
        if start == -1:
            return blocks
        end = text.index(f"</{tag}>", start)
        blocks.append(text[start:end])
        cursor = end + len(f"</{tag}>")


def _child_gate(source: str, gate_id: str) -> ChildGateTuple:
    for block in source.split("```yaml")[1:]:
        yaml_text = block.split("```", 1)[0]
        payload = yaml.safe_load(yaml_text)
        if not isinstance(payload, dict):
            continue
        child_gate = payload.get("child_gate")
        if isinstance(child_gate, dict) and child_gate.get("id") == gate_id:
            return child_gate_tuple_from_payload(payload)
    raise AssertionError(f"missing child gate {gate_id}")


def _artifact_paths(gate: ChildGateTuple) -> tuple[str, ...]:
    return tuple(artifact.path for artifact in gate.expected_artifacts)


def test_new_project_stage_contract_loads_and_preserves_stage_order() -> None:
    contract = stage_contract_module.load_new_project_stage_contract()

    assert contract.schema_version == 1
    assert contract.workflow_id == "new-project"
    assert contract.stage_ids() == EXPECTED_STAGE_IDS
    assert tuple(stage.order for stage in contract.stages) == tuple(range(1, len(EXPECTED_STAGE_IDS) + 1))

    root_authority = "workflows/new-project.md"
    for stage in contract.stages:
        assert root_authority not in stage.mode_paths
        assert root_authority not in stage.loaded_authorities
        assert all(path.startswith("workflows/new-project/") for path in stage.mode_paths), (
            f"{stage.id} must use split stage authority files"
        )

    scope_intake = contract.stage("scope_intake")
    scope_approval = contract.stage("scope_approval")
    minimal_artifacts = contract.stage("minimal_artifacts")
    workflow_preferences = contract.stage("workflow_preferences")
    project_artifacts = contract.stage("project_artifacts")
    literature_survey = contract.stage("literature_survey")
    requirements_authoring = contract.stage("requirements_authoring")
    roadmap_authoring = contract.stage("roadmap_authoring")
    conventions_handoff = contract.stage("conventions_handoff")
    completion = contract.stage("completion")

    assert scope_intake.mode_paths == ("workflows/new-project/scope-intake.md",)
    assert scope_intake.loaded_authorities == ("workflows/new-project/scope-intake.md",)
    assert scope_intake.required_init_fields[:3] == ("commit_docs", "autonomy", "research_mode")
    assert "researcher_model" not in scope_intake.required_init_fields
    assert "synthesizer_model" not in scope_intake.required_init_fields
    assert "roadmapper_model" not in scope_intake.required_init_fields
    assert "project_contract_gate" in scope_intake.required_init_fields
    assert "needs_research_map" in scope_intake.required_init_fields
    assert "init_progress_status" in scope_intake.required_init_fields
    assert scope_intake.required_init_fields.index("needs_research_map") < scope_intake.required_init_fields.index(
        "has_git"
    )
    assert scope_intake.required_init_fields.index("platform") < scope_intake.required_init_fields.index(
        "project_contract"
    )
    assert scope_intake.conditional_authorities[0].when == "full_questioning_path"
    assert scope_intake.conditional_authorities[0].authorities == ("references/research/questioning.md",)
    assert "workflows/new-project/scope-approval.md" in scope_intake.must_not_eager_load
    assert "references/research/questioning.md" in scope_intake.must_not_eager_load
    assert "references/shared/canonical-schema-discipline.md" in scope_intake.must_not_eager_load
    assert "templates/state.md" in scope_intake.must_not_eager_load
    assert "templates/project-contract-schema.md" in scope_intake.must_not_eager_load
    assert "templates/project-contract-grounding-linkage.md" in scope_intake.must_not_eager_load
    assert scope_intake.allowed_tools == ("file_read", "ask_user", "shell")
    assert scope_intake.produced_state == ("intake routing state", "scoping-contract gate state")
    assert scope_intake.checkpoints == (
        "detect existing workspace state",
        "surface the first scoping question",
        "preserve contract gate visibility without assuming approval-stage authority",
    )
    assert scope_intake.writes_allowed == ()
    assert scope_intake.next_stages == ("scope_approval",)

    assert scope_approval.required_init_fields[0] == "project_contract"
    assert "project_contract_gate" in scope_approval.required_init_fields
    assert "project_contract_load_info" in scope_approval.required_init_fields
    assert "project_contract_validation" in scope_approval.required_init_fields
    assert len(scope_approval.required_init_fields) == 4
    assert scope_approval.mode_paths == ("workflows/new-project/scope-approval.md",)
    assert scope_approval.loaded_authorities == ("workflows/new-project/scope-approval.md",)
    assert {conditional.when: conditional.authorities for conditional in scope_approval.conditional_authorities} == {
        "contract_schema_validation_or_linkage_repair": (
            "templates/project-contract-schema.md",
            "templates/project-contract-grounding-linkage.md",
            "references/shared/canonical-schema-discipline.md",
        )
    }
    assert "templates/project-contract-schema.md" in scope_approval.must_not_eager_load
    assert "templates/project-contract-grounding-linkage.md" in scope_approval.must_not_eager_load
    assert "references/shared/canonical-schema-discipline.md" in scope_approval.must_not_eager_load
    assert scope_approval.produced_state == ("approved project contract", "approval-state persistence")
    assert scope_approval.checkpoints == (
        "approval gate has passed",
        "project contract is ready for persistence",
    )
    assert scope_approval.writes_allowed == (
        "GPD/state.json",
        "GPD/STATE.md",
        "GPD/state.json.bak",
        "GPD/state.json.lock",
    )
    assert scope_approval.next_stages == ("minimal_artifacts", "workflow_preferences")

    assert minimal_artifacts.loaded_authorities == ("workflows/new-project/minimal-artifacts.md",)
    assert minimal_artifacts.writes_allowed == (
        "GPD/PROJECT.md",
        "GPD/config.json",
        "GPD/REQUIREMENTS.md",
        "GPD/ROADMAP.md",
        "GPD/STATE.md",
        "GPD/state.json",
        "GPD/state.json.bak",
        "GPD/state.json.lock",
    )
    assert "workflows/new-project/literature-survey.md" in minimal_artifacts.must_not_eager_load
    assert "workflows/new-project/roadmap-authoring.md" in minimal_artifacts.must_not_eager_load
    assert "workflows/new-project/conventions-handoff.md" in minimal_artifacts.must_not_eager_load
    assert "GPD/literature/SUMMARY.md" not in minimal_artifacts.writes_allowed
    assert "GPD/CONVENTIONS.md" not in minimal_artifacts.writes_allowed
    assert minimal_artifacts.next_stages == ("completion",)

    assert workflow_preferences.loaded_authorities == ("workflows/new-project/workflow-preferences.md",)
    assert workflow_preferences.writes_allowed == ("GPD/config.json",)
    assert "workflows/new-project/roadmap-authoring.md" in workflow_preferences.must_not_eager_load
    assert "workflows/new-project/conventions-handoff.md" in workflow_preferences.must_not_eager_load
    assert workflow_preferences.next_stages == ("project_artifacts",)

    assert project_artifacts.loaded_authorities == ("workflows/new-project/project-artifacts.md",)
    assert project_artifacts.writes_allowed == (
        "GPD/PROJECT.md",
        "GPD/state.json",
        "GPD/state.json.bak",
        "GPD/state.json.lock",
        "GPD/init-progress.json",
    )
    assert "workflows/new-project/roadmap-authoring.md" in project_artifacts.must_not_eager_load
    assert "workflows/new-project/conventions-handoff.md" in project_artifacts.must_not_eager_load
    assert project_artifacts.next_stages == ("literature_survey",)

    assert literature_survey.loaded_authorities == ("workflows/new-project/literature-survey.md",)
    assert "researcher_model" in literature_survey.required_init_fields
    assert "synthesizer_model" in literature_survey.required_init_fields
    assert "roadmapper_model" not in literature_survey.required_init_fields
    assert literature_survey.writes_allowed == (
        "GPD/literature/PRIOR-WORK.md",
        "GPD/literature/METHODS.md",
        "GPD/literature/COMPUTATIONAL.md",
        "GPD/literature/PITFALLS.md",
        "GPD/literature/SUMMARY.md",
        "GPD/init-progress.json",
    )
    assert "workflows/new-project/roadmap-authoring.md" in literature_survey.must_not_eager_load
    assert "workflows/new-project/conventions-handoff.md" in literature_survey.must_not_eager_load
    assert literature_survey.next_stages == ("requirements_authoring",)

    assert requirements_authoring.loaded_authorities == ("workflows/new-project/requirements-authoring.md",)
    assert requirements_authoring.writes_allowed == ("GPD/REQUIREMENTS.md", "GPD/init-progress.json")
    assert "roadmapper_model" not in requirements_authoring.required_init_fields
    assert "workflows/new-project/roadmap-authoring.md" in requirements_authoring.must_not_eager_load
    assert "workflows/new-project/conventions-handoff.md" in requirements_authoring.must_not_eager_load
    assert requirements_authoring.next_stages == ("roadmap_authoring",)

    assert roadmap_authoring.loaded_authorities == ("workflows/new-project/roadmap-authoring.md",)
    assert "roadmapper_model" in roadmap_authoring.required_init_fields
    assert roadmap_authoring.writes_allowed == (
        "GPD/ROADMAP.md",
        "GPD/STATE.md",
        "GPD/state.json",
        "GPD/state.json.bak",
        "GPD/state.json.lock",
        "GPD/init-progress.json",
    )
    assert "workflows/new-project/conventions-handoff.md" in roadmap_authoring.must_not_eager_load
    assert roadmap_authoring.next_stages == ("conventions_handoff",)

    assert conventions_handoff.loaded_authorities == ("workflows/new-project/conventions-handoff.md",)
    assert "notation_model" not in conventions_handoff.required_init_fields
    assert conventions_handoff.writes_allowed == (
        "GPD/CONVENTIONS.md",
        "GPD/state.json",
        "GPD/state.json.bak",
        "GPD/state.json.lock",
        "GPD/init-progress.json",
    )
    assert conventions_handoff.next_stages == ("completion",)

    assert completion.loaded_authorities == ("workflows/new-project/completion.md",)
    assert completion.writes_allowed == ("GPD/init-progress.json",)
    assert completion.next_stages == ()


def test_new_project_split_stages_load_templates_at_write_boundaries() -> None:
    contract = stage_contract_module.load_new_project_stage_contract()
    command_text = _read_new_project_command()
    minimal = contract.stage("minimal_artifacts")
    project_artifacts = contract.stage("project_artifacts")
    requirements = contract.stage("requirements_authoring")

    assert "GPD/PROJECT.md" in minimal.writes_allowed
    assert "GPD/STATE.md" in minimal.writes_allowed
    minimal_text = _read_stage_authority("minimal-artifacts.md")
    assert "templates/project.md" in minimal_text
    assert "templates/state.md" in minimal_text

    assert "GPD/PROJECT.md" in project_artifacts.writes_allowed
    assert "templates/project.md" in _read_stage_authority("project-artifacts.md")

    assert "GPD/REQUIREMENTS.md" in requirements.writes_allowed
    assert "templates/requirements.md" in _read_stage_authority("requirements-authoring.md")

    for output_path, template_path in {
        "GPD/PROJECT.md": "templates/project.md",
        "GPD/REQUIREMENTS.md": "templates/requirements.md",
        "GPD/STATE.md": "templates/state.md",
    }.items():
        assert f"Load `{template_path}` only when writing `{output_path}`." not in command_text


def test_new_project_stage_contract_loader_is_cached() -> None:
    first = stage_contract_module.load_new_project_stage_contract()
    second = stage_contract_module.load_new_project_stage_contract()

    assert first is second


def test_new_project_approval_stage_owns_grounding_linkage_authorities() -> None:
    contract = stage_contract_module.load_new_project_stage_contract()
    command_text = _read_new_project_command()
    scope_approval = contract.stage("scope_approval")
    scope_approval_text = _read_stage_authority("scope-approval.md")

    conditionals = {conditional.when: conditional.authorities for conditional in scope_approval.conditional_authorities}
    assert conditionals == {
        "contract_schema_validation_or_linkage_repair": (
            "templates/project-contract-schema.md",
            "templates/project-contract-grounding-linkage.md",
            "references/shared/canonical-schema-discipline.md",
        )
    }
    assert "templates/project-contract-schema.md" in scope_approval.must_not_eager_load
    assert "templates/project-contract-grounding-linkage.md" in scope_approval.must_not_eager_load
    assert "references/shared/canonical-schema-discipline.md" in scope_approval.must_not_eager_load
    assert "templates/project-contract-schema.md" in scope_approval_text
    assert "@{GPD_INSTALL_DIR}/templates/project-contract-schema.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/project-contract-grounding-linkage.md" not in command_text


def test_new_project_defines_auto_minimal_conflict_as_prewrite_gate() -> None:
    command_text = _read_new_project_command()
    scope_intake = _read_stage_authority("scope-intake.md")

    expected_error = "Error: --auto and --minimal cannot be combined."
    assert expected_error in command_text
    assert_prompt_contracts(
        command_text,
        semantic_anchor(
            "auto/minimal conflict stops before mutation",
            ("conflict stop", "before git initialization"),
        ),
    )
    assert_prompt_contracts(
        scope_intake,
        semantic_anchor(
            "scope intake forbids prewrite mutation",
            ("Do not initialize git", "create `GPD/`", "write state"),
        ),
    )
    assert "writes_allowed" not in scope_intake


def test_new_project_recovery_gate_precedes_generic_project_hard_stops() -> None:
    workflow_text = _read_stage_authority("scope-intake.md")

    progress_gate = workflow_text.index("<recovery_routing>")
    project_stop = workflow_text.index("`project_exists=true`")
    recoverable_stop = workflow_text.index("`recoverable_project_exists=true`")

    assert progress_gate < project_stop
    assert progress_gate < recoverable_stop
    assert_prompt_contracts(
        workflow_text,
        machine_exact(
            "new-project recovery path and status stay exact",
            ("`GPD/init-progress.json`", 'init_progress_status="interrupted_init_progress"'),
            owner="new-project staged contract",
            rationale="recovery routing consumes this artifact path and status literal",
        ),
        semantic_anchor(
            "new-project recovery uses staged setup fields",
            ("structured setup fields", "`SCOPE_INIT`", "explicit start-fresh choice"),
        ),
    )
    assert "cat GPD/init-progress.json" not in workflow_text


def test_new_project_minimal_roadmap_contract_is_direct_not_staged_handoff() -> None:
    workflow_text = _read_stage_authority("minimal-artifacts.md")
    minimal_m4 = workflow_text[
        workflow_text.index("## M4. Create ROADMAP.md") : workflow_text.index("## M5. Create STATE.md")
    ]

    assert_prompt_contracts(
        minimal_m4,
        semantic_anchor(
            "minimal roadmap is written directly",
            ("lightweight local `GPD/ROADMAP.md`", "directly", "approved contract", "minimal mode"),
        ),
        semantic_anchor(
            "minimal roadmap skips later roadmap delegation",
            ("Do not delegate", "later roadmap authority"),
        ),
    )
    assert "gpd-roadmapper" not in workflow_text


def test_new_project_post_scope_child_gates_preserve_artifact_contracts() -> None:
    workflow_text = _read_new_project_authority()
    scouts = _child_gate(workflow_text, "literature_scouts")
    synthesizer = _child_gate(workflow_text, "literature_synthesizer")
    roadmapper = _child_gate(workflow_text, "project_roadmapper")
    notation = _child_gate(workflow_text, "notation_conventions")

    assert _artifact_paths(scouts) == (
        "GPD/literature/PRIOR-WORK.md",
        "GPD/literature/METHODS.md",
        "GPD/literature/COMPUTATIONAL.md",
        "GPD/literature/PITFALLS.md",
    )
    assert scouts.allowed_roots == ("GPD/literature",)
    assert scouts.freshness is not None
    assert scouts.freshness.marker == "$SCOUT_HANDOFF_STARTED_AT per scout"

    assert _artifact_paths(synthesizer) == ("GPD/literature/SUMMARY.md",)
    assert synthesizer.allowed_roots == ("GPD/literature",)
    assert synthesizer.freshness is not None
    assert synthesizer.freshness.marker == "$SYNTHESIZER_HANDOFF_STARTED_AT"

    assert _artifact_paths(roadmapper) == ("GPD/ROADMAP.md", "GPD/STATE.md", "GPD/REQUIREMENTS.md")
    assert roadmapper.allowed_roots == ("GPD",)
    assert roadmapper.applicator.command == "shared_state_policy=direct for this legacy init handoff"
    assert roadmapper.applicator.require_passed_true is False

    assert _artifact_paths(notation) == ("GPD/CONVENTIONS.md",)
    assert notation.allowed_roots == ("GPD",)
    assert notation.applicator.command == "child direct gpd convention set in auto/approved continuation"
    assert notation.applicator.require_passed_true is False


def test_new_project_defers_git_until_first_mutation_gate() -> None:
    command_text = _read_new_project_command()
    scope_intake = _read_stage_authority("scope-intake.md")
    scope_approval = _read_stage_authority("scope-approval.md")
    minimal = _read_stage_authority("minimal-artifacts.md")
    project_artifacts = _read_stage_authority("project-artifacts.md")

    assert_prompt_contracts(
        command_text,
        semantic_anchor(
            "new-project setup defers git initialization",
            ("conflict stop", "before git initialization", "Do not initialize git", "Setup"),
        ),
    )
    assert_prompt_contracts(
        scope_intake,
        semantic_anchor(
            "scope intake forbids setup writes",
            ("Do not initialize git", "create `GPD/`", "write state"),
        ),
    )
    assert "git init" not in scope_intake
    assert "git init" not in scope_approval
    assert "gpd state set-project-contract -" in scope_approval
    for mutation_stage in (minimal, project_artifacts):
        assert_prompt_contracts(
            mutation_stage,
            semantic_anchor(
                "git initialization is deferred to mutation stages",
                ("`has_git` is false", "initialize git before the commit"),
            ),
        )


def test_new_project_notation_contracts_split_checkpoint_from_artifact_write() -> None:
    workflow_text = _read_stage_authority("conventions-handoff.md")
    auto_contract = next(
        block for block in _tagged_blocks(workflow_text, "spawn_contract") if "GPD/CONVENTIONS.md" in block
    )
    interactive_contract = _tagged_block(workflow_text, "spawn_contract_interactive")

    assert "GPD/CONVENTIONS.md" in auto_contract
    assert "expected_artifacts: []" in interactive_contract
    assert "status: checkpoint" in interactive_contract
    assert "GPD/CONVENTIONS.md" not in interactive_contract
    assert "CHECKPOINT REACHED" not in workflow_text
    assert "Return `status: checkpoint`" in workflow_text


def test_new_project_notation_spawn_model_and_recovery_contract_are_conditional() -> None:
    workflow_text = _read_stage_authority("conventions-handoff.md")

    assert 'model="{NOTATION_MODEL}"' not in workflow_text
    assert 'model="$NOTATION_MODEL"' in workflow_text
    assert 'task(prompt=NOTATION_PROMPT, subagent_type="gpd-notation-coordinator", readonly=false' in workflow_text
    assert_prompt_contracts(
        workflow_text,
        semantic_anchor(
            "notation recovery respawns coordinator and fails closed",
            (
                "spawn one fresh `gpd-notation-coordinator`",
                "continuation that writes `GPD/CONVENTIONS.md`",
                "fail closed",
            ),
        ),
        semantic_anchor(
            "stale notation recovery main-context write stays absent",
            (
                "write the returned content in the main context",
                "re-execute the convention-establishment task in the main context",
            ),
            mode=FragmentMode.ABSENT,
        ),
    )


def test_new_project_stage_contract_rejects_unknown_top_level_keys() -> None:
    payload = {
        "schema_version": 1,
        "workflow_id": "new-project",
        "stages": [],
        "unexpected": True,
    }

    with pytest.raises(ValueError, match="unexpected key"):
        stage_contract_module.validate_new_project_stage_contract_payload(payload)


def test_new_project_stage_contract_rejects_unknown_stage_keys() -> None:
    payload = json.loads(stage_contract_module.NEW_PROJECT_STAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    payload["stages"][0]["unexpected"] = "boom"

    with pytest.raises(ValueError, match="unexpected key"):
        stage_contract_module.validate_new_project_stage_contract_payload(payload)


def test_new_project_stage_contract_rejects_invalid_ordering(tmp_path: Path) -> None:
    payload = json.loads(stage_contract_module.NEW_PROJECT_STAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    payload["stages"][0]["order"] = 2
    payload["stages"][1]["order"] = 1
    path = tmp_path / "new-project-stage-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="stage order values"):
        stage_contract_module.load_new_project_stage_contract_from_path(path)


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda payload: payload["stages"][0]["loaded_authorities"].__setitem__(0, "references/missing.md"),
            "markdown file",
        ),
        (lambda payload: payload["stages"][0]["allowed_tools"].__setitem__(0, "network"), "unknown tool name"),
        (
            lambda payload: payload["stages"][1].__setitem__("required_init_fields", ["bogus_field"]),
            "unknown field name",
        ),
        (
            lambda payload: payload["stages"][0]["must_not_eager_load"].append("workflows/new-project/scope-intake.md"),
            "overlap with must_not_eager_load",
        ),
        (
            lambda payload: payload["stages"][0]["writes_allowed"].append("../state.json"),
            "normalized relative POSIX path",
        ),
    ],
)
def test_new_project_stage_contract_rejects_validation_drift(mutator, expected: str) -> None:
    payload = json.loads(stage_contract_module.NEW_PROJECT_STAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    mutator(payload)

    with pytest.raises(ValueError, match=expected):
        stage_contract_module.validate_new_project_stage_contract_payload(payload)
