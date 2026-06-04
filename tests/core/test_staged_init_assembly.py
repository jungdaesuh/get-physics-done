"""Unit tests for workflow-neutral staged-init assembly."""

from __future__ import annotations

from pathlib import Path

import pytest

from gpd.core.staged_init_assembly import (
    StagedInitAssemblyContext,
    StagedInitProvider,
    assemble_staged_init_payload,
)
from gpd.core.workflow_staging import WorkflowStage, WorkflowStageManifest


def _stage(
    stage_id: str,
    fields: tuple[str, ...],
    *,
    order: int = 1,
    init_spec_id: str | None = None,
) -> WorkflowStage:
    return WorkflowStage(
        id=stage_id,
        order=order,
        purpose=f"{stage_id} purpose",
        mode_paths=(),
        required_init_fields=fields,
        loaded_authorities=(),
        conditional_authorities=(),
        must_not_eager_load=(),
        allowed_tools=(),
        writes_allowed=(),
        produced_state=(),
        next_stages=(),
        checkpoints=(),
        init_spec_id=init_spec_id,
    )


def _manifest(*stages: WorkflowStage, workflow_id: str = "demo") -> WorkflowStageManifest:
    return WorkflowStageManifest(schema_version=1, workflow_id=workflow_id, stages=stages)


def test_assemble_dispatches_only_intersecting_providers_and_emits_manifest_order(tmp_path: Path) -> None:
    manifest = _manifest(
        _stage("bootstrap", ("base", "provided", "tail")),
        _stage("later", ("base", "late_only"), order=2),
    )
    base_payload = {"base": 1, "tail": 3, "base_extra": "hidden"}
    calls: list[str] = []

    def build_needed(context: StagedInitAssemblyContext) -> dict[str, object]:
        calls.append("needed")
        assert context.workflow_id == "demo"
        assert context.stage.id == "bootstrap"
        assert context.required_fields == frozenset({"base", "provided", "tail"})
        assert context.cwd == tmp_path
        assert context.base_payload is base_payload
        return {"provided": 2, "provider_extra": "hidden"}

    def build_unneeded(context: StagedInitAssemblyContext) -> dict[str, object]:
        raise AssertionError(f"provider should be lazy for {context.stage.id}")

    payload = assemble_staged_init_payload(
        workflow_id="demo",
        stage_id="bootstrap",
        cwd=tmp_path,
        base_payload=base_payload,
        manifest=manifest,
        providers=(
            StagedInitProvider(
                name="needed",
                trigger_fields=frozenset({"provided"}),
                build=build_needed,
            ),
            StagedInitProvider(
                name="unneeded",
                trigger_fields=frozenset({"late_only"}),
                build=build_unneeded,
            ),
        ),
    )

    assert calls == ["needed"]
    assert tuple(payload) == ("base", "provided", "tail", "staged_loading")
    assert payload["base"] == 1
    assert payload["provided"] == 2
    assert payload["tail"] == 3
    assert "base_extra" not in payload
    assert "provider_extra" not in payload
    assert payload["staged_loading"] == manifest.staged_loading_payload("bootstrap")


def test_nested_field_access_instruction_does_not_change_top_level_payload_keys(tmp_path: Path) -> None:
    manifest = _manifest(_stage("bootstrap", ("base", "tail")))

    payload = assemble_staged_init_payload(
        workflow_id="demo",
        stage_id="bootstrap",
        cwd=tmp_path,
        base_payload={"base": 1, "tail": 2},
        manifest=manifest,
    )

    stage = manifest.stage("bootstrap")
    assert tuple(payload) == (*stage.required_init_fields, "staged_loading")
    assert set(payload) == set(stage.required_init_fields) | {"staged_loading"}
    assert "field_access_instruction" not in payload
    staged_loading = payload["staged_loading"]
    assert [key for key in staged_loading if key == "field_access_instruction"] == ["field_access_instruction"]
    assert (
        staged_loading["field_access_instruction"]
        == manifest.staged_loading_payload("bootstrap")["field_access_instruction"]
    )
    assert staged_loading["field_access_instruction"].startswith("Field access (demo.bootstrap):")
    assert ", ".join(stage.required_init_fields) not in staged_loading["field_access_instruction"]


def test_postprocessors_fill_fields_before_missing_field_detection(tmp_path: Path) -> None:
    manifest = _manifest(_stage("bootstrap", ("base", "derived")))

    def add_derived(context: StagedInitAssemblyContext, staged_source: dict[str, object]) -> None:
        assert context.required_fields == frozenset({"base", "derived"})
        staged_source["derived"] = "from postprocessor"
        staged_source["unselected"] = "hidden"

    payload = assemble_staged_init_payload(
        workflow_id="demo",
        stage_id="bootstrap",
        cwd=tmp_path,
        base_payload={"base": "value"},
        manifest=manifest,
        postprocessors=(add_derived,),
    )

    assert tuple(payload) == ("base", "derived", "staged_loading")
    assert payload["derived"] == "from postprocessor"
    assert "unselected" not in payload


def test_missing_fields_keep_workflow_stage_and_manifest_order(tmp_path: Path) -> None:
    manifest = _manifest(_stage("bootstrap", ("present", "missing_a", "missing_b")))

    with pytest.raises(ValueError) as exc_info:
        assemble_staged_init_payload(
            workflow_id="demo",
            stage_id="bootstrap",
            cwd=tmp_path,
            base_payload={"present": True},
            manifest=manifest,
        )

    assert str(exc_info.value) == ("demo stage 'bootstrap' requires unavailable init field(s): missing_a, missing_b")


def test_unknown_stage_keeps_allowed_stage_guidance(tmp_path: Path) -> None:
    manifest = _manifest(
        _stage("bootstrap", ("base",)),
        _stage("authoring", ("base", "draft"), order=2),
    )

    with pytest.raises(ValueError) as exc_info:
        assemble_staged_init_payload(
            workflow_id="demo",
            stage_id="bogus",
            cwd=tmp_path,
            base_payload={"base": True},
            manifest=manifest,
        )

    assert str(exc_info.value) == "Unknown demo stage 'bogus'. Allowed values: bootstrap, authoring."


def test_error_label_overrides_user_facing_stage_messages(tmp_path: Path) -> None:
    manifest = _manifest(_stage("bootstrap", ("missing",)), workflow_id="manifest-demo")

    with pytest.raises(ValueError, match="custom flow stage 'bootstrap' requires unavailable init field"):
        assemble_staged_init_payload(
            workflow_id="runtime-demo",
            stage_id="bootstrap",
            cwd=tmp_path,
            base_payload={},
            manifest=manifest,
            error_label="custom flow",
        )


def test_init_spec_validation_receives_only_active_fields_before_staged_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(_stage("typed", ("base",), init_spec_id="demo.typed.v1"))
    calls: list[tuple[str, str, str, dict[str, object], tuple[str, ...]]] = []

    def validate_staged_init_payload(
        workflow_id: str,
        stage_id: str,
        init_spec_id: str,
        payload: dict[str, object],
    ) -> None:
        calls.append((workflow_id, stage_id, init_spec_id, dict(payload), tuple(payload)))
        assert "staged_loading" not in payload
        raise ValueError("bad shape")

    monkeypatch.setattr(
        "gpd.core.workflow_init_specs.validate_staged_init_payload",
        validate_staged_init_payload,
    )

    with pytest.raises(ValueError) as exc_info:
        assemble_staged_init_payload(
            workflow_id="demo",
            stage_id="typed",
            cwd=tmp_path,
            base_payload={"base": "value", "extra": "hidden"},
            manifest=manifest,
        )

    assert calls == [("demo", "typed", "demo.typed.v1", {"base": "value"}, ("base",))]
    message = str(exc_info.value)
    assert "demo staged init payload validation failed" in message
    assert "workflow=demo" in message
    assert "stage=typed" in message
    assert "init_spec_id=demo.typed.v1" in message
    assert "bad shape" in message


def test_helper_stays_workflow_neutral() -> None:
    source = (Path(__file__).resolve().parents[2] / "src/gpd/core/staged_init_assembly.py").read_text(encoding="utf-8")

    forbidden_fragments = (
        "gpd.core.context",
        "gpd.cli",
        "gpd.registry",
        "gpd.core.prompt_diagnostics",
        "gpd.core.stage_prompt_diagnostics",
        "gpd.adapters.",
        "gpd.core.publication",
        "publication_runtime",
        "manuscript_artifacts",
        "workflow_id ==",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source
