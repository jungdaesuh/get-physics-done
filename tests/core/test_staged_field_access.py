from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.context import init_execute_phase, init_new_project, init_plan_phase, init_write_paper
from gpd.core.staged_field_access import build_staged_field_access
from gpd.core.state import default_state_dict
from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    WORKFLOW_STAGE_MANIFEST_SUFFIX,
    load_workflow_stage_manifest,
)
from tests.workflow_authority_support import workflow_authority_paths, workflow_authority_text

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "stage0"


def _manifest_workflow_ids() -> tuple[str, ...]:
    return tuple(
        sorted(
            path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
            for path in WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")
        )
    )


FIELD_ACCESS_WORKFLOWS = _manifest_workflow_ids()
FIELD_ACCESS_REQUIRED_MARKER = "`<INIT>.staged_loading.required_init_fields`"
FIELD_ACCESS_UNLISTED_POLICY = "Treat unlisted init/body fields as unavailable"
FIELD_ACCESS_STALE_POLICY = "Reject stale/older init payloads"
FIELD_ACCESS_BODY_PREFIX = "Body fields:"
FIELD_ACCESS_TARGET_POLICY = "Body fields: selected body fields are target-scoped"
FIELD_ACCESS_TARGET_SELECTION_POLICY = (
    "after choosing the concrete section, issue, artifact, gap, handoff, or reference target"
)
FIELD_ACCESS_HANDLE_FIRST_POLICY = "use handles/status/load manifests first"
FIELD_ACCESS_HANDLE_ONLY_POLICY = "selected handle/status fields are handles only"
FIELD_ACCESS_NO_BODY_POLICY = "no staged body fields are selected"
FIELD_ACCESS_RENDERED_CONTEXT_POLICY = "do not make unselected body fields available"
FIELD_ACCESS_PROTOCOL_HANDLE_FIELDS = {"selected_protocol_bundle_ids", "protocol_bundle_load_manifest"}
FIELD_ACCESS_PROTOCOL_HANDLE_POLICY = "Protocol bundles: selected IDs/load manifests are handles until needed"
FIELD_ACCESS_PROTOCOL_DOMAIN_POLICY = (
    "open only relevant verification_domains/execution_guides portable_path entries from protocol_bundle_load_manifest"
)
FIELD_ACCESS_PROTOCOL_UNSELECTED_POLICY = "keep unselected assets absent"
GPD_JSON_GET_TOKEN = "gpd json get"
PAYLOAD_WORKFLOWS = (
    "plan-phase",
    "execute-phase",
    "new-project",
    "write-paper",
)
STAGED_PROMPT_HYGIENE_WORKFLOWS = (
    "new-milestone",
    "quick",
    "map-research",
    "literature-review",
    "respond-to-referees",
    "resume-work",
    "verify-work",
    "new-project",
    "sync-state",
)
PUBLICATION_STAGED_PROMPT_WORKFLOWS = frozenset(
    {
        "arxiv-submission",
        "peer-review",
        "respond-to-referees",
        "write-paper",
    }
)
RAW_INIT_WORKFLOW_ALIASES = {
    "resume": "resume-work",
}
STAGED_RAW_INIT_COMMAND_PATTERN = re.compile(
    r"\bgpd\s+--raw\s+init\s+(?P<workflow>[a-z][a-z0-9-]*)\b[^\n`)]*--stage\b"
)
STAGED_RAW_INIT_ASSIGNMENT_PATTERN = re.compile(
    r"(?m)^\s*(?P<var>[A-Z][A-Z0-9_]*)=\$\(gpd\s+--raw\s+init\s+"
    r"(?P<workflow>[a-z][a-z0-9-]*)\b[^\n)]*--stage\b[^\n)]*\)"
)
STALE_REQUIRED_INIT_FIELDS_PATTERN = re.compile(
    r"\b(?!staged_loading\b)[a-z][a-z0-9_]*\.required_init_fields\b"
)
EXPECTED_FIELD_ACCESS_STAGE_MENTIONS = {
    "plan-phase": ("phase_bootstrap", "research_routing", "planner_authoring", "checker_revision"),
    "execute-phase": (
        "phase_bootstrap",
        "phase_classification",
        "wave_planning",
        "pre_execution_specialists",
        "wave_dispatch",
        "checkpoint_resume",
        "aggregate_and_verify",
        "closeout",
    ),
    "new-project": (
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
    ),
    "write-paper": (
        "paper_bootstrap",
        "outline_and_scaffold",
        "figure_and_section_authoring",
        "consistency_and_references",
        "publication_review",
    ),
    "new-milestone": ("milestone_bootstrap", "survey_objectives", "roadmap_authoring"),
    "quick": ("task_bootstrap", "task_authoring", "reference_context"),
    "map-research": ("map_bootstrap", "mapper_authoring"),
    "literature-review": ("review_bootstrap", "scope_locked", "review_handoff", "completion_gate"),
    "respond-to-referees": (
        "bootstrap",
        "report_triage",
        "revision_planning",
        "response_authoring",
        "finalize",
    ),
    "resume-work": ("resume_bootstrap", "state_restore", "derivation_restore", "resume_routing"),
    "verify-work": (
        "session_router",
        "phase_bootstrap",
        "inventory_build",
        "interactive_validation",
        "gap_repair",
    ),
}
STAGED_FIELD_INVENTORY_PATTERNS = (
    re.compile(r"\bParse JSON for\s*:?\s*`", re.IGNORECASE),
    re.compile(r"\bExtract from init JSON\s*:?\s*`", re.IGNORECASE),
    re.compile(r"\bExtract from the staged refresh\s*:?\s*`", re.IGNORECASE),
    re.compile(r"\bParse the staged refresh for\s*`", re.IGNORECASE),
    re.compile(r"\bParse the completion refresh for\s*`", re.IGNORECASE),
    re.compile(
        r"\bUse\s+`?(?!staged_loading\b)[a-z][a-z0-9_]*\.required_init_fields`?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bTreat\s+`?(?!staged_loading\b)[a-z][a-z0-9_]*\.required_init_fields`?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bRead only\s+`?(?!staged_loading\b)[a-z][a-z0-9_]*\.required_init_fields`?",
        re.IGNORECASE,
    ),
)


def _field_access_command(workflow_id: str, stage_id: str) -> str:
    return f"gpd --raw stage field-access {workflow_id} --stage {stage_id} --style instruction"


def _raw_init_manifest_workflow_id(workflow_id: str) -> str:
    return RAW_INIT_WORKFLOW_ALIASES.get(workflow_id, workflow_id)


def _non_publication_staged_prompt_paths() -> tuple[tuple[str, Path], ...]:
    paths: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for workflow_id in FIELD_ACCESS_WORKFLOWS:
        if workflow_id in PUBLICATION_STAGED_PROMPT_WORKFLOWS:
            continue
        for path in workflow_authority_paths(WORKFLOWS_DIR, workflow_id):
            if path in seen:
                continue
            seen.add(path)
            paths.append((workflow_id, path))
    return tuple(paths)


def _manifest_backed_raw_init_workflows(text: str) -> set[str]:
    manifest_workflows = set(FIELD_ACCESS_WORKFLOWS)
    return {
        mapped_workflow_id
        for match in STAGED_RAW_INIT_COMMAND_PATTERN.finditer(text)
        if (mapped_workflow_id := _raw_init_manifest_workflow_id(match.group("workflow"))) in manifest_workflows
    }


def _assert_instruction_omits_full_selected_field_inventory(
    instruction_text: str, selected_fields: tuple[str, ...]
) -> None:
    if len(selected_fields) < 2:
        return
    forbidden_inventories = {
        ", ".join(selected_fields),
        "\n".join(selected_fields),
        json.dumps(list(selected_fields)),
    }
    for inventory in forbidden_inventories:
        assert inventory not in instruction_text


def _setup_manifest_owned_payload_project(project_root: Path) -> None:
    gpd_dir = project_root / "GPD"
    phase_dir = gpd_dir / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)

    (gpd_dir / "PROJECT.md").write_text("# Test Project\n\nPaper target.\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n## Phase 2: Analysis\n\n**Goal:** Compare the benchmark observable.\n",
        encoding="utf-8",
    )
    (gpd_dir / "REQUIREMENTS.md").write_text("# Requirements\n- Preserve benchmark anchors.\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text("# State\nCurrent phase: 02\n", encoding="utf-8")

    (phase_dir / "02-PLAN.md").write_text("objective: compare benchmark observable\n", encoding="utf-8")
    (phase_dir / "02-SUMMARY.md").write_text("# Summary\nExisting result.\n", encoding="utf-8")
    (phase_dir / "02-CONTEXT.md").write_text("# Context\nLocked scope.\n", encoding="utf-8")
    (phase_dir / "02-RESEARCH.md").write_text("# Research\nMethod comparison.\n", encoding="utf-8")
    (phase_dir / "02-EXPERIMENT-DESIGN.md").write_text("# Experiment Design\nGrid scan.\n", encoding="utf-8")
    (phase_dir / "02-VERIFICATION.md").write_text("# Verification\nGap notes.\n", encoding="utf-8")
    (phase_dir / "02-VALIDATION.md").write_text("# Validation\nChecks.\n", encoding="utf-8")

    state = default_state_dict()
    state["project_contract"] = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
    state["position"]["current_phase"] = "02"
    state["current_execution"] = {
        "session_id": "sess-stage-parity",
        "phase": "02",
        "plan": "01",
        "segment_status": "waiting_review",
        "resume_file": "GPD/phases/02-analysis/.continue-here.md",
        "pre_fanout_review_pending": True,
    }
    (gpd_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _staged_init_payload(workflow_id: str, project_root: Path, stage_id: str) -> dict[str, object]:
    builders: dict[str, Callable[[Path, str], dict[str, object]]] = {
        "plan-phase": lambda root, stage: init_plan_phase(root, "2", stage=stage),
        "execute-phase": lambda root, stage: init_execute_phase(root, "2", stage=stage),
        "new-project": lambda root, stage: init_new_project(root, stage=stage),
        "write-paper": lambda root, stage: init_write_paper(root, stage=stage),
    }
    return builders[workflow_id](project_root, stage_id)


def test_default_instruction_style_is_shell_free_and_manifest_backed() -> None:
    manifest = load_workflow_stage_manifest("plan-phase")
    stage = manifest.stage("planner_authoring")

    access = build_staged_field_access("plan-phase", stage_id="planner_authoring")
    payload = access.to_payload()

    assert payload["style"] == "instruction"
    assert payload["selected_fields"] == list(stage.required_init_fields)
    assert payload["aliases"] == []
    assert "shell_bindings" not in payload

    instruction_text = "\n".join(payload["instructions"])
    assert payload["instructions"] == [manifest.staged_loading_payload(stage.id)["field_access_instruction"]]
    assert GPD_JSON_GET_TOKEN not in instruction_text
    assert "$(" not in instruction_text
    assert _field_access_command("plan-phase", "planner_authoring") in instruction_text
    assert FIELD_ACCESS_REQUIRED_MARKER in instruction_text
    assert FIELD_ACCESS_UNLISTED_POLICY in instruction_text
    assert FIELD_ACCESS_STALE_POLICY in instruction_text
    _assert_instruction_omits_full_selected_field_inventory(instruction_text, stage.required_init_fields)
    assert "active_reference_context" in payload["selected_fields"]
    assert "staged_loading" not in payload["selected_fields"]


@pytest.mark.parametrize("workflow_id", FIELD_ACCESS_WORKFLOWS)
def test_instruction_style_matches_manifest_for_all_staged_workflow_stages(workflow_id: str) -> None:
    manifest = load_workflow_stage_manifest(workflow_id)

    for stage_id in manifest.stage_ids():
        stage = manifest.stage(stage_id)
        access = build_staged_field_access(workflow_id, stage_id=stage_id)
        payload = access.to_payload()

        assert payload["workflow_id"] == workflow_id
        assert payload["stage_id"] == stage_id
        assert payload["style"] == "instruction"
        assert payload["selected_fields"] == list(stage.required_init_fields)
        assert payload["aliases"] == []
        assert "shell_bindings" not in payload
        staged_loading = manifest.staged_loading_payload(stage_id)
        instruction_keys = [key for key in staged_loading if key == "field_access_instruction"]
        assert instruction_keys == ["field_access_instruction"]
        assert isinstance(staged_loading["field_access_instruction"], str)
        assert "field_access_instruction" not in payload
        assert len(payload["instructions"]) == 1
        assert payload["selected_fields"] == staged_loading["required_init_fields"]
        assert payload["instructions"] == [staged_loading["field_access_instruction"]]
        _assert_instruction_omits_full_selected_field_inventory(payload["instructions"][0], stage.required_init_fields)


@pytest.mark.parametrize("workflow_id", FIELD_ACCESS_WORKFLOWS)
def test_instruction_compact_policy_is_deterministic_for_all_staged_manifest_stages(workflow_id: str) -> None:
    manifest = load_workflow_stage_manifest(workflow_id)

    for stage_id in manifest.stage_ids():
        first = build_staged_field_access(workflow_id, stage_id=stage_id).to_payload()
        second = build_staged_field_access(workflow_id, stage_id=stage_id).to_payload()
        instruction_text = "\n".join(first["instructions"])

        assert first["instructions"] == second["instructions"]
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
        assert len(first["instructions"]) == 1
        assert instruction_text.count(f"Field access ({workflow_id}.{stage_id})") == 1
        assert _field_access_command(workflow_id, stage_id) in instruction_text
        assert FIELD_ACCESS_REQUIRED_MARKER in instruction_text
        assert FIELD_ACCESS_UNLISTED_POLICY in instruction_text
        assert FIELD_ACCESS_STALE_POLICY in instruction_text
        assert FIELD_ACCESS_BODY_PREFIX in instruction_text


def test_handle_only_stages_do_not_imply_body_availability() -> None:
    checked_stages: list[tuple[str, str]] = []

    for workflow_id in FIELD_ACCESS_WORKFLOWS:
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage_id in manifest.stage_ids():
            payload = build_staged_field_access(workflow_id, stage_id=stage_id).to_payload()
            selected_fields = payload["selected_fields"]
            body_fields = [field for field in selected_fields if field.endswith("_content")]
            if "reference_artifact_files" not in selected_fields or body_fields:
                continue
            instruction_text = "\n".join(payload["instructions"])

            checked_stages.append((workflow_id, stage_id))
            assert FIELD_ACCESS_HANDLE_ONLY_POLICY in instruction_text
            assert FIELD_ACCESS_NO_BODY_POLICY in instruction_text
            assert "reference_artifacts_content" not in instruction_text

    assert checked_stages


def test_body_selected_stages_are_target_scoped() -> None:
    checked_stages: list[tuple[str, str]] = []

    for workflow_id in FIELD_ACCESS_WORKFLOWS:
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage_id in manifest.stage_ids():
            payload = build_staged_field_access(workflow_id, stage_id=stage_id).to_payload()
            selected_fields = payload["selected_fields"]
            body_fields = [field for field in selected_fields if field.endswith("_content")]
            if not body_fields:
                continue
            instruction_text = "\n".join(payload["instructions"])

            checked_stages.append((workflow_id, stage_id))
            for body_field in body_fields:
                assert body_field in instruction_text
            assert FIELD_ACCESS_TARGET_POLICY in instruction_text
            assert FIELD_ACCESS_TARGET_SELECTION_POLICY in instruction_text
            assert FIELD_ACCESS_HANDLE_FIRST_POLICY in instruction_text

    assert checked_stages


def test_rendered_context_fields_do_not_unlock_unselected_body_fields() -> None:
    rendered_context_fields = {"active_reference_context", "protocol_bundle_context"}
    checked_stages: list[tuple[str, str]] = []

    for workflow_id in FIELD_ACCESS_WORKFLOWS:
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage_id in manifest.stage_ids():
            payload = build_staged_field_access(workflow_id, stage_id=stage_id).to_payload()
            selected_fields = set(payload["selected_fields"])
            rendered_selected = sorted(selected_fields & rendered_context_fields)
            if not rendered_selected:
                continue
            instruction_text = "\n".join(payload["instructions"])

            checked_stages.append((workflow_id, stage_id))
            for rendered_field in rendered_selected:
                assert rendered_field in instruction_text
            assert FIELD_ACCESS_RENDERED_CONTEXT_POLICY in instruction_text

    assert checked_stages


def test_protocol_bundle_handle_stages_include_domain_opening_invariant() -> None:
    checked_stages: list[tuple[str, str]] = []

    for workflow_id in FIELD_ACCESS_WORKFLOWS:
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage_id in manifest.stage_ids():
            payload = build_staged_field_access(workflow_id, stage_id=stage_id).to_payload()
            selected_fields = set(payload["selected_fields"])
            if not selected_fields & FIELD_ACCESS_PROTOCOL_HANDLE_FIELDS:
                continue
            instruction_text = "\n".join(payload["instructions"])

            checked_stages.append((workflow_id, stage_id))
            assert FIELD_ACCESS_PROTOCOL_HANDLE_POLICY in instruction_text
            assert FIELD_ACCESS_PROTOCOL_DOMAIN_POLICY in instruction_text
            assert FIELD_ACCESS_PROTOCOL_UNSELECTED_POLICY in instruction_text

    assert checked_stages


@pytest.mark.parametrize("workflow_id", PAYLOAD_WORKFLOWS)
def test_staged_payload_fields_remain_manifest_owned(tmp_path: Path, workflow_id: str) -> None:
    _setup_manifest_owned_payload_project(tmp_path)
    manifest = load_workflow_stage_manifest(workflow_id)

    for stage_id in manifest.stage_ids():
        stage = manifest.stage(stage_id)
        payload = _staged_init_payload(workflow_id, tmp_path, stage_id)
        access_payload = build_staged_field_access(workflow_id, stage_id=stage_id).to_payload()

        assert tuple(payload) == (*stage.required_init_fields, "staged_loading")
        assert set(payload) == set(stage.required_init_fields) | {"staged_loading"}
        assert payload["staged_loading"] == manifest.staged_loading_payload(stage_id)
        assert "field_access_instruction" not in payload
        assert [key for key in payload["staged_loading"] if key == "field_access_instruction"] == [
            "field_access_instruction"
        ]
        assert payload["staged_loading"]["field_access_instruction"] == access_payload["instructions"][0]
        assert access_payload["selected_fields"] == list(stage.required_init_fields)


def test_target_workflows_have_generated_field_access_for_staged_reloads() -> None:
    for workflow_id, stage_ids in EXPECTED_FIELD_ACCESS_STAGE_MENTIONS.items():
        for stage_id in stage_ids:
            manifest = load_workflow_stage_manifest(workflow_id)
            access_payload = build_staged_field_access(workflow_id, stage_id=stage_id).to_payload()
            staged_loading = manifest.staged_loading_payload(stage_id)
            instruction_text = access_payload["instructions"][0]

            assert staged_loading["field_access_instruction"] == instruction_text
            assert staged_loading["required_init_fields"] == access_payload["selected_fields"]
            assert _field_access_command(workflow_id, stage_id) in instruction_text
            assert FIELD_ACCESS_REQUIRED_MARKER in instruction_text
            assert FIELD_ACCESS_UNLISTED_POLICY in instruction_text


@pytest.mark.parametrize("workflow_id", STAGED_PROMPT_HYGIENE_WORKFLOWS)
def test_staged_workflow_prompts_do_not_reintroduce_hand_written_field_inventories(workflow_id: str) -> None:
    source = workflow_authority_text(WORKFLOWS_DIR, workflow_id)

    for pattern in STAGED_FIELD_INVENTORY_PATTERNS:
        assert pattern.search(source) is None


def test_non_publication_staged_raw_init_prompts_apply_field_access_instruction() -> None:
    failures: list[str] = []

    for _owner_workflow_id, path in _non_publication_staged_prompt_paths():
        text = path.read_text(encoding="utf-8")
        raw_init_workflows = _manifest_backed_raw_init_workflows(text)
        if not raw_init_workflows:
            continue

        if "staged_loading.field_access_instruction" not in text:
            failures.append(f"{path.relative_to(REPO_ROOT)}: missing staged_loading.field_access_instruction")

        for match in STAGED_RAW_INIT_ASSIGNMENT_PATTERN.finditer(text):
            command_workflow_id = _raw_init_manifest_workflow_id(match.group("workflow"))
            if command_workflow_id not in FIELD_ACCESS_WORKFLOWS:
                continue
            payload_var = match.group("var")
            marker = f"{payload_var}.staged_loading.field_access_instruction"
            if marker not in text:
                failures.append(f"{path.relative_to(REPO_ROOT)}: `{marker}` is required")

    assert failures == []


def test_non_publication_staged_raw_init_prompts_use_payload_required_fields_path() -> None:
    failures: list[str] = []

    for _owner_workflow_id, path in _non_publication_staged_prompt_paths():
        text = path.read_text(encoding="utf-8")
        if not _manifest_backed_raw_init_workflows(text):
            continue

        for match in STALE_REQUIRED_INIT_FIELDS_PATTERN.finditer(text):
            failures.append(f"{path.relative_to(REPO_ROOT)}: stale `{match.group(0)}`")

    assert failures == []


def test_json_style_exposes_exact_fields_and_requested_aliases() -> None:
    manifest = load_workflow_stage_manifest("plan-phase")
    stage = manifest.stage("planner_authoring")

    access = build_staged_field_access(
        "plan-phase",
        stage_id="planner_authoring",
        style="json",
        alias_specs=("PHASE=phase_number", "plan_count"),
    )
    payload = access.to_payload()

    assert payload["style"] == "json"
    assert payload["source"]["manifest_path"] == "workflows/plan-phase-stage-manifest.json"
    assert payload["selected_fields"] == list(stage.required_init_fields)
    assert payload["aliases"] == [
        {"alias": "PHASE", "field": "phase_number"},
        {"alias": "plan_count", "field": "plan_count"},
    ]
    assert "instructions" not in payload
    assert "shell_bindings" not in payload


def test_aliases_must_target_fields_selected_by_stage() -> None:
    with pytest.raises(ValueError, match="Field 'state_content' is not selected by plan-phase stage 'phase_bootstrap'"):
        build_staged_field_access(
            "plan-phase",
            stage_id="phase_bootstrap",
            style="json",
            alias_specs=("STATE=state_content",),
        )


def test_shell_style_binds_only_requested_aliases() -> None:
    access = build_staged_field_access(
        "plan-phase",
        stage_id="planner_authoring",
        style="shell",
        alias_specs=("PHASE=phase_number", "PHASE_DIR=phase_dir"),
    )
    payload = access.to_payload()

    assert payload["style"] == "shell"
    assert payload["aliases"] == [
        {"alias": "PHASE", "field": "phase_number"},
        {"alias": "PHASE_DIR", "field": "phase_dir"},
    ]
    assert payload["shell_bindings"] == [
        'PHASE=$(printf \'%s\\n\' "${INIT}" | gpd json get .phase_number --default "")',
        'PHASE_DIR=$(printf \'%s\\n\' "${INIT}" | gpd json get .phase_dir --default "")',
    ]
    assert all("researcher_model" not in line for line in payload["shell_bindings"])


def test_shell_style_without_aliases_binds_no_fields() -> None:
    access = build_staged_field_access("plan-phase", stage_id="planner_authoring", style="shell")
    payload = access.to_payload()

    assert payload["aliases"] == []
    assert payload["shell_bindings"] == []


def test_cli_raw_stage_field_access_instruction_exposes_compact_policy() -> None:
    result = runner.invoke(
        app,
        [
            "--raw",
            "stage",
            "field-access",
            "plan-phase",
            "--stage",
            "planner_authoring",
            "--style",
            "instruction",
        ],
        catch_exceptions=False,
        color=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    instruction_text = "\n".join(payload["instructions"])
    assert payload["selected_fields"]
    assert _field_access_command("plan-phase", "planner_authoring") in instruction_text
    assert FIELD_ACCESS_REQUIRED_MARKER in instruction_text
    assert FIELD_ACCESS_TARGET_POLICY in instruction_text


def test_cli_raw_stage_field_access_json() -> None:
    result = runner.invoke(
        app,
        [
            "--raw",
            "stage",
            "field-access",
            "plan-phase",
            "--stage",
            "planner_authoring",
            "--style",
            "json",
            "--alias",
            "PHASE=phase_number",
        ],
        catch_exceptions=False,
        color=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["workflow_id"] == "plan-phase"
    assert payload["stage_id"] == "planner_authoring"
    assert payload["style"] == "json"
    assert payload["aliases"] == [{"alias": "PHASE", "field": "phase_number"}]
    assert "phase_number" in payload["selected_fields"]


def test_cli_raw_stage_field_access_rejects_unselected_alias_field() -> None:
    result = runner.invoke(
        app,
        [
            "--raw",
            "stage",
            "field-access",
            "plan-phase",
            "--stage",
            "phase_bootstrap",
            "--style",
            "json",
            "--alias",
            "STATE=state_content",
        ],
        catch_exceptions=False,
        color=False,
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    expected_error = "Field 'state_content' is not selected by plan-phase stage 'phase_bootstrap'"
    assert expected_error in payload["error"]
