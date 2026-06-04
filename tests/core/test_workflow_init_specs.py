"""Assertions for typed staged-init payload specs."""

from __future__ import annotations

import pytest

from gpd.core.workflow_init_specs import (
    WORKFLOW_INIT_SPECS,
    StagedInitPayloadValidationError,
    StagedInitSpecLookupError,
    get_staged_init_spec,
    validate_staged_init_payload,
)
from gpd.core.workflow_staging import (
    WORKFLOW_STAGE_MANIFEST_DIR,
    WORKFLOW_STAGE_MANIFEST_SUFFIX,
    load_workflow_stage_manifest,
)


def _manifest_workflow_ids() -> tuple[str, ...]:
    return tuple(
        sorted(
            path.name.removesuffix(WORKFLOW_STAGE_MANIFEST_SUFFIX)
            for path in WORKFLOW_STAGE_MANIFEST_DIR.glob(f"*{WORKFLOW_STAGE_MANIFEST_SUFFIX}")
        )
    )


def _quick_task_payload() -> dict[str, object]:
    return {
        "planner_model": "gpt-5",
        "executor_model": "gpt-5",
        "commit_docs": True,
        "autonomy": "supervised",
        "research_mode": "standard",
        "next_num": 1,
        "slug": "check-units",
        "description": "Check a units calculation",
        "date": "2026-05-08",
        "timestamp": "2026-05-08T12:00:00+00:00",
        "quick_dir": "GPD/quick",
        "task_dir": "GPD/quick/1-check-units",
        "roadmap_exists": True,
        "project_exists": True,
        "planning_exists": True,
        "platform": "runtime-under-test",
        "project_contract": None,
        "project_contract_gate": {"visible": True, "authoritative": False},
        "project_contract_load_info": {"status": "missing"},
        "project_contract_validation": {"valid": False, "issues": []},
    }


def _quick_reference_payload() -> dict[str, object]:
    payload = _quick_task_payload()
    payload.update(
        {
            "contract_intake": None,
            "effective_reference_intake": {"must_read_refs": ["ref-a"]},
            "selected_protocol_bundle_ids": ["core"],
            "protocol_bundle_count": 1,
            "protocol_bundle_load_manifest": {"selected_bundle_ids": ["core"], "bundle_count": 1},
            "protocol_bundle_verifier_extensions": [{"bundle_id": "core"}],
            "reference_artifact_files": ["GPD/research-map/REFERENCES.md"],
            "literature_review_files": ["GPD/literature/SUMMARY.md"],
            "literature_review_count": 1,
            "research_map_reference_files": ["GPD/research-map/REFERENCES.md"],
            "research_map_reference_count": 1,
            "derived_manuscript_proof_review_status": {"status": "not_applicable"},
        }
    )
    return payload


@pytest.mark.parametrize(
    ("stage_id", "init_spec_id"),
    [
        ("task_bootstrap", "quick.task_bootstrap.v1"),
        ("task_authoring", "quick.task_authoring.v1"),
        ("reference_context", "quick.reference_context.v1"),
    ],
)
def test_quick_registry_lookup_matches_manifest_active_fields(stage_id: str, init_spec_id: str) -> None:
    spec = get_staged_init_spec("quick", stage_id, init_spec_id)
    manifest = load_workflow_stage_manifest("quick")

    assert spec.workflow_id == "quick"
    assert spec.stage_id == stage_id
    assert spec.init_spec_id == init_spec_id
    assert spec.field_names == manifest.stage(stage_id).required_init_fields
    assert "staged_loading" not in spec.field_names


def test_registered_specs_match_manifest_init_spec_ids() -> None:
    registry_keys = [(spec.workflow_id, spec.stage_id, spec.init_spec_id) for spec in WORKFLOW_INIT_SPECS]
    manifest_spec_fields: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for workflow_id in _manifest_workflow_ids():
        manifest = load_workflow_stage_manifest(workflow_id)
        for stage_id in manifest.stage_ids():
            stage = manifest.stage(stage_id)
            if stage.init_spec_id is not None:
                manifest_spec_fields[(workflow_id, stage_id, stage.init_spec_id)] = stage.required_init_fields

    assert len(registry_keys) == len(set(registry_keys))
    assert set(registry_keys) == set(manifest_spec_fields)
    for spec in WORKFLOW_INIT_SPECS:
        assert spec.field_names == manifest_spec_fields[(spec.workflow_id, spec.stage_id, spec.init_spec_id)]
        assert "staged_loading" not in spec.field_names


def test_registry_lookup_rejects_unknown_spec_ids() -> None:
    with pytest.raises(StagedInitSpecLookupError, match="quick.unknown.v1"):
        get_staged_init_spec("quick", "task_authoring", "quick.unknown.v1")


@pytest.mark.parametrize(
    ("stage_id", "init_spec_id", "payload"),
    [
        ("task_bootstrap", "quick.task_bootstrap.v1", _quick_task_payload()),
        ("task_authoring", "quick.task_authoring.v1", _quick_task_payload()),
        ("reference_context", "quick.reference_context.v1", _quick_reference_payload()),
    ],
)
def test_validate_accepts_quick_shaped_payloads(
    stage_id: str,
    init_spec_id: str,
    payload: dict[str, object],
) -> None:
    original = dict(payload)

    validated = validate_staged_init_payload("quick", stage_id, init_spec_id, payload)

    assert validated is payload
    assert payload == original


def test_validate_rejects_missing_active_fields() -> None:
    payload = _quick_task_payload()
    del payload["executor_model"]

    with pytest.raises(StagedInitPayloadValidationError, match="missing field\\(s\\): executor_model"):
        validate_staged_init_payload("quick", "task_authoring", "quick.task_authoring.v1", payload)


def test_validate_rejects_extra_active_fields() -> None:
    payload = _quick_task_payload()
    payload["active_reference_context"] = "not selected by task_authoring"

    with pytest.raises(StagedInitPayloadValidationError, match="extra field\\(s\\): active_reference_context"):
        validate_staged_init_payload("quick", "task_authoring", "quick.task_authoring.v1", payload)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected_kind", "actual_kind"),
    [
        ("planner_model", {"name": "gpt-5"}, "scalar", "dict"),
        ("project_contract_gate", ["visible"], "dict", "list"),
        ("selected_protocol_bundle_ids", "core", "list", "scalar"),
    ],
)
def test_validate_rejects_obvious_scalar_list_dict_drift(
    field_name: str,
    bad_value: object,
    expected_kind: str,
    actual_kind: str,
) -> None:
    payload = _quick_reference_payload()
    payload[field_name] = bad_value

    with pytest.raises(
        StagedInitPayloadValidationError,
        match=f"field {field_name!r} expected {expected_kind}, got {actual_kind}",
    ):
        validate_staged_init_payload("quick", "reference_context", "quick.reference_context.v1", payload)


def test_validate_ignores_staged_loading_shape_and_does_not_mutate_payload() -> None:
    staged_loading = {
        "required_init_fields": "wrong shape on purpose",
        "unexpected": {"nested": ["payload"]},
    }
    payload = _quick_task_payload()
    payload["staged_loading"] = staged_loading

    validated = validate_staged_init_payload("quick", "task_bootstrap", "quick.task_bootstrap.v1", payload)

    assert validated is payload
    assert payload["staged_loading"] is staged_loading
    assert payload["project_contract_gate"] == {"visible": True, "authoritative": False}
