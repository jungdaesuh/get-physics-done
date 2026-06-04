from __future__ import annotations

from pathlib import Path

import pytest

from gpd.core.context import init_execute_phase
from gpd.core.task_overlays import (
    TASK_OVERLAY_REFERENCE_PATH,
    TaskOverlaySelectionError,
    build_task_overlay_load_manifest,
    list_task_overlays,
    validate_task_overlay_selection,
)
from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    WORKFLOW_STAGE_MANIFEST_SUFFIX,
    load_workflow_stage_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = REPO_ROOT / "src" / "gpd" / "specs" / TASK_OVERLAY_REFERENCE_PATH
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"

ALLOWED_TASK_OVERLAY_INIT_FIELDS = {
    "selected_task_overlay_ids",
    "task_overlay_load_manifest",
    "task_overlay_policy_summary",
}
DISALLOWED_TASK_OVERLAY_BODY_KEYS = {
    "overlay_body",
    "overlay_bodies",
    "overlay_content",
    "overlay_contents",
    "overlay_markdown",
    "overlay_payload",
    "overlay_payloads",
    "overlay_text",
    "rendered_overlay",
    "rendered_overlay_body",
    "rendered_overlay_content",
    "task_overlay_body",
    "task_overlay_bodies",
    "task_overlay_content",
    "task_overlay_markdown",
    "task_overlay_text",
}
BASE_AGENT_OVERLAY_ROLES = {
    "gpd-executor",
    "gpd-planner",
    "gpd-plan-checker",
    "gpd-paper-writer",
}


def _setup_execute_phase_project(cwd: Path) -> None:
    gpd_dir = cwd / "GPD"
    phase_dir = gpd_dir / "phases" / "01-test"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (gpd_dir / "config.json").write_text("{}", encoding="utf-8")
    (gpd_dir / "state.json").write_text("{}", encoding="utf-8")
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("## Milestone\n\n### Phase 1: Test\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text("# State\n", encoding="utf-8")
    (phase_dir / "a-PLAN.md").write_text("# Plan\n", encoding="utf-8")


def _assert_task_overlay_metadata_is_body_free(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            assert key_text not in DISALLOWED_TASK_OVERLAY_BODY_KEYS, path
            if key_text != "body_loaded":
                assert not (
                    ("overlay" in key_text)
                    and any(fragment in key_text for fragment in ("body", "content", "markdown", "text"))
                ), path
            _assert_task_overlay_metadata_is_body_free(child, path=f"{path}.{key_text}")
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_task_overlay_metadata_is_body_free(child, path=f"{path}[{index}]")
        return

    if isinstance(value, str):
        assert "\n" not in value, path


def test_task_overlay_reference_defines_spawn_first_metadata_only_contract() -> None:
    text = REFERENCE_PATH.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    required_fragments = (
        "Task overlays are spawn-time metadata pointers",
        "`selected_task_overlay_ids`",
        "`task_overlay_load_manifest`",
        "`task_overlay_policy_summary`",
        "must not include `overlay_body`",
        "String values in staged overlay metadata remain single-line scalars.",
        "Every selected overlay ID must resolve through `gpd.core.task_overlays`.",
        "Each selected overlay must be compatible with the child agent role",
    )

    for fragment in required_fragments:
        assert fragment in normalized_text

    duplicated_registry_ids = sorted(
        overlay.overlay_id for overlay in list_task_overlays() if overlay.overlay_id in text
    )
    assert duplicated_registry_ids == []


def test_task_overlay_registry_is_metadata_only_and_role_compatible() -> None:
    overlays = list_task_overlays()
    assert overlays

    overlay_ids = [overlay.overlay_id for overlay in overlays]
    assert len(overlay_ids) == len(set(overlay_ids))

    for overlay in overlays:
        assert overlay.path == TASK_OVERLAY_REFERENCE_PATH
        assert overlay.role.startswith("gpd-")
        assert "\n" not in overlay.summary
        _assert_task_overlay_metadata_is_body_free(overlay.as_manifest_entry(), path=overlay.overlay_id)

    selected = validate_task_overlay_selection(
        ["executor.proof_bearing", "executor.bounded_segment"],
        role="gpd-executor",
    )
    assert [overlay.overlay_id for overlay in selected] == ["executor.proof_bearing", "executor.bounded_segment"]


def test_task_overlay_selection_rejects_unknown_duplicate_and_role_mismatched_ids() -> None:
    with pytest.raises(TaskOverlaySelectionError, match="unknown task overlay ID"):
        validate_task_overlay_selection(["executor.missing"], role="gpd-executor")

    with pytest.raises(TaskOverlaySelectionError, match="duplicate task overlay IDs"):
        validate_task_overlay_selection(["executor.proof_bearing", "executor.proof_bearing"], role="gpd-executor")

    with pytest.raises(TaskOverlaySelectionError, match="not gpd-paper-writer"):
        validate_task_overlay_selection(["executor.proof_bearing"], role="gpd-paper-writer")


def test_task_overlay_load_manifest_is_body_free_metadata() -> None:
    manifest = build_task_overlay_load_manifest(
        ["paper_writer.section_results", "paper_writer.figure_sensitive"],
        role="gpd-paper-writer",
        selection_source="write-paper.authoring",
    )

    assert manifest["selected_task_overlay_ids"] == [
        "paper_writer.section_results",
        "paper_writer.figure_sensitive",
    ]
    assert manifest["overlay_count"] == 2
    assert [entry["body_loaded"] for entry in manifest["overlays"]] == [False, False]
    _assert_task_overlay_metadata_is_body_free(manifest, path="task_overlay_load_manifest")


def test_stage_manifests_do_not_request_task_overlay_body_init_fields() -> None:
    offenders: dict[str, list[str]] = {}

    for manifest_path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")):
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage in manifest.stages:
            overlay_fields = [
                field
                for field in stage.required_init_fields
                if field.startswith("task_overlay_") or field.startswith("selected_task_overlay")
            ]
            unexpected_fields = sorted(set(overlay_fields) - ALLOWED_TASK_OVERLAY_INIT_FIELDS)
            if "task_overlay_policy_summary" in overlay_fields and "task_overlay_load_manifest" not in overlay_fields:
                unexpected_fields.append("task_overlay_policy_summary_without_task_overlay_load_manifest")
            if unexpected_fields:
                offenders[f"{workflow_id}:{stage.id}"] = unexpected_fields

    assert offenders == {}


def test_execute_phase_executor_dispatch_is_only_stage_requesting_task_overlay_handles() -> None:
    overlay_stages: dict[str, list[str]] = {}

    for manifest_path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")):
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage in manifest.stages:
            overlay_fields = [
                field for field in stage.required_init_fields if field in ALLOWED_TASK_OVERLAY_INIT_FIELDS
            ]
            if overlay_fields:
                overlay_stages[f"{workflow_id}:{stage.id}"] = overlay_fields

    assert overlay_stages == {
        "execute-phase:executor_dispatch": [
            "selected_task_overlay_ids",
            "task_overlay_load_manifest",
            "task_overlay_policy_summary",
        ]
    }


def test_execute_phase_executor_dispatch_task_overlay_payload_is_body_free(tmp_path: Path) -> None:
    _setup_execute_phase_project(tmp_path)

    payload = init_execute_phase(tmp_path, "1", stage="executor_dispatch")
    load_manifest = payload["task_overlay_load_manifest"]

    assert payload["selected_task_overlay_ids"] == ["executor.bounded_segment"]
    assert isinstance(load_manifest, dict)
    assert load_manifest["selection_source"] == "execute-phase.executor_dispatch"
    assert load_manifest["role"] == "gpd-executor"
    assert load_manifest["selected_task_overlay_ids"] == ["executor.bounded_segment"]
    assert load_manifest["overlay_count"] == 1
    assert payload["task_overlay_policy_summary"] == (
        "Selected executor.bounded_segment for execute-phase executor_dispatch bounded fanout; "
        "selected entries stay metadata-only."
    )
    assert "executor.proof_bearing" not in payload["selected_task_overlay_ids"]

    overlays = load_manifest["overlays"]
    assert isinstance(overlays, list)
    assert len(overlays) == 1
    assert set(overlays[0]) == {"overlay_id", "role", "path", "summary", "portable_path", "body_loaded"}
    assert overlays[0]["overlay_id"] == "executor.bounded_segment"
    assert overlays[0]["path"] == TASK_OVERLAY_REFERENCE_PATH
    assert overlays[0]["portable_path"] == f"@{{GPD_INSTALL_DIR}}/{TASK_OVERLAY_REFERENCE_PATH}"
    assert overlays[0]["body_loaded"] is False
    _assert_task_overlay_metadata_is_body_free(
        {
            "selected_task_overlay_ids": payload["selected_task_overlay_ids"],
            "task_overlay_load_manifest": load_manifest,
            "task_overlay_policy_summary": payload["task_overlay_policy_summary"],
        },
        path="execute-phase:executor_dispatch.task_overlay_handles",
    )


def test_staged_loading_payloads_remain_task_overlay_body_free() -> None:
    for manifest_path in sorted(WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")):
        workflow_id = manifest_path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage_id in manifest.stage_ids():
            payload = manifest.staged_loading_payload(stage_id)
            _assert_task_overlay_metadata_is_body_free(payload, path=f"{workflow_id}:{stage_id}")


def test_base_agent_prompts_do_not_embed_task_overlay_metadata_or_bodies() -> None:
    overlay_ids = {overlay.overlay_id for overlay in list_task_overlays()}
    forbidden_tokens = {
        *overlay_ids,
        "selected_task_overlay_ids",
        "task_overlay_load_manifest",
        "task_overlay_policy_summary",
        "overlay_body",
        "overlay_markdown",
        "rendered_overlay_body",
    }

    for role in BASE_AGENT_OVERLAY_ROLES:
        prompt_path = AGENTS_DIR / f"{role}.md"
        text = prompt_path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, f"{prompt_path}:{token}"
