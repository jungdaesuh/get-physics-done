"""Contracts for compact workflow-stage manifest source canonicalization."""

from __future__ import annotations

from copy import deepcopy
from typing import cast

import pytest

from gpd.core.workflow_manifest_compaction import canonicalize_workflow_stage_manifest_payload
from gpd.core.workflow_staging import (
    staged_loading_payload_contract_keys,
    staged_protocol_bundle_required_init_fields,
    validate_workflow_stage_manifest_payload,
)

_KNOWN_INIT_FIELDS = {
    "autonomy",
    "project_root",
    "protocol_bundle_context",
    "protocol_bundle_count",
    "protocol_bundle_load_manifest",
    "selected_protocol_bundle_ids",
}
_COMPACT_ONLY_STAGE_KEYS = {
    "must_not_eager_load_groups",
    "required_init_field_groups",
}
_COMPACT_ONLY_TOP_LEVEL_KEYS = {
    "authority_groups",
    "cold_authority_policy",
    "derived_init_field_rules",
    "required_init_field_groups",
    "stage_defaults",
}


def _explicit_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "quick",
        "stages": [
            {
                "id": "task_bootstrap",
                "order": 1,
                "purpose": "Load task bootstrap context.",
                "mode_paths": ["workflows/quick/task-bootstrap.md"],
                "required_init_fields": ["project_root", "autonomy"],
                "loaded_authorities": ["workflows/quick/task-bootstrap.md"],
                "conditional_authorities": [],
                "must_not_eager_load": [
                    "references/shared/canonical-schema-discipline.md",
                    "workflows/quick/reference-context.md",
                    "workflows/quick/task-authoring.md",
                ],
                "allowed_tools": ["file_read"],
                "writes_allowed": [],
                "produced_state": [],
                "next_stages": ["reference_context"],
                "checkpoints": [],
            },
            {
                "id": "reference_context",
                "order": 2,
                "purpose": "Load reference context.",
                "mode_paths": ["workflows/quick/reference-context.md"],
                "required_init_fields": [
                    "selected_protocol_bundle_ids",
                    "protocol_bundle_count",
                    "protocol_bundle_load_manifest",
                    "protocol_bundle_context",
                ],
                "loaded_authorities": [
                    "workflows/quick/reference-context.md",
                    "references/orchestration/context-budget.md",
                ],
                "conditional_authorities": [],
                "must_not_eager_load": [
                    "workflows/quick/task-bootstrap.md",
                    "workflows/quick/task-authoring.md",
                ],
                "allowed_tools": ["file_read"],
                "writes_allowed": [],
                "produced_state": [],
                "next_stages": ["task_authoring"],
                "checkpoints": [],
            },
            {
                "id": "task_authoring",
                "order": 3,
                "purpose": "Author the task response.",
                "mode_paths": ["workflows/quick/task-authoring.md"],
                "required_init_fields": ["project_root"],
                "loaded_authorities": ["workflows/quick/task-authoring.md"],
                "conditional_authorities": [],
                "must_not_eager_load": [
                    "workflows/quick/task-bootstrap.md",
                    "workflows/quick/reference-context.md",
                ],
                "allowed_tools": ["file_read"],
                "writes_allowed": [],
                "produced_state": [],
                "next_stages": [],
                "checkpoints": [],
            },
        ],
    }


def _compact_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "quick",
        "required_init_field_groups": {
            "bootstrap": ["project_root", "autonomy"],
            "protocol_context": [
                "selected_protocol_bundle_ids",
                "protocol_bundle_count",
                "protocol_bundle_context",
            ],
        },
        "authority_groups": {
            "shared_deferred": ["references/shared/canonical-schema-discipline.md"],
        },
        "stage_defaults": {
            "allowed_tools": ["file_read"],
            "conditional_authorities": [],
            "must_not_eager_load": [],
            "writes_allowed": [],
            "produced_state": [],
            "checkpoints": [],
        },
        "cold_authority_policy": "workflow_stage_authorities_cold_except_eager",
        "derived_init_field_rules": ["protocol_bundle_load_manifest_for_protocol_context"],
        "stages": [
            {
                "id": "task_bootstrap",
                "order": 1,
                "purpose": "Load task bootstrap context.",
                "mode_paths": ["workflows/quick/task-bootstrap.md"],
                "required_init_field_groups": ["bootstrap"],
                "loaded_authorities": ["workflows/quick/task-bootstrap.md"],
                "must_not_eager_load_groups": ["shared_deferred"],
                "next_stages": ["reference_context"],
            },
            {
                "id": "reference_context",
                "order": 2,
                "purpose": "Load reference context.",
                "mode_paths": ["workflows/quick/reference-context.md"],
                "required_init_field_groups": ["protocol_context"],
                "loaded_authorities": [
                    "workflows/quick/reference-context.md",
                    "references/orchestration/context-budget.md",
                ],
                "next_stages": ["task_authoring"],
            },
            {
                "id": "task_authoring",
                "order": 3,
                "purpose": "Author the task response.",
                "mode_paths": ["workflows/quick/task-authoring.md"],
                "required_init_fields": ["project_root"],
                "loaded_authorities": ["workflows/quick/task-authoring.md"],
                "next_stages": [],
            },
        ],
    }


def _validate(payload: dict[str, object]):
    return validate_workflow_stage_manifest_payload(
        payload,
        expected_workflow_id="quick",
        known_init_fields=_KNOWN_INIT_FIELDS,
    )


def test_old_explicit_manifest_payload_is_accepted_without_canonical_shape_drift() -> None:
    payload = _explicit_payload()

    assert canonicalize_workflow_stage_manifest_payload(payload) == payload
    assert _validate(payload).to_payload() == payload


def test_compact_manifest_payload_expands_to_explicit_manifest_payload() -> None:
    explicit_manifest = _validate(_explicit_payload())
    compact_manifest = _validate(_compact_payload())

    assert compact_manifest.to_payload() == explicit_manifest.to_payload()


def test_compact_manifest_keys_do_not_reach_runtime_payloads() -> None:
    manifest = _validate(_compact_payload())
    manifest_payload = manifest.to_payload()
    staged_loading = manifest.staged_loading_payload("reference_context")
    required_keys, optional_keys = staged_loading_payload_contract_keys(manifest)
    optional_payload = _explicit_payload()
    optional_stages = cast("list[dict[str, object]]", optional_payload["stages"])
    init_spec_key = "init_spec_id"
    optional_stages[0][init_spec_key] = "quick.task_bootstrap.v1"
    optional_required_keys, optional_stage_keys = staged_loading_payload_contract_keys(_validate(optional_payload))

    assert not (_COMPACT_ONLY_TOP_LEVEL_KEYS & set(manifest_payload))
    for stage_payload in manifest_payload["stages"]:
        assert not (_COMPACT_ONLY_STAGE_KEYS & set(stage_payload))
    assert not (_COMPACT_ONLY_TOP_LEVEL_KEYS & set(staged_loading))
    assert not (_COMPACT_ONLY_STAGE_KEYS & set(staged_loading))
    assert (
        staged_loading["required_init_fields"],
        required_keys,
        optional_keys,
        bool(_COMPACT_ONLY_STAGE_KEYS & set(required_keys)),
        bool(_COMPACT_ONLY_TOP_LEVEL_KEYS & set(required_keys)),
        staged_protocol_bundle_required_init_fields(manifest),
        init_spec_key in optional_required_keys,
        optional_stage_keys,
    ) == (
        [
            "selected_protocol_bundle_ids",
            "protocol_bundle_count",
            "protocol_bundle_load_manifest",
            "protocol_bundle_context",
        ],
        tuple(manifest.staged_loading_payload("task_bootstrap")),
        (),
        False,
        False,
        (
            "selected_protocol_bundle_ids",
            "protocol_bundle_count",
            "protocol_bundle_load_manifest",
            "protocol_bundle_context",
        ),
        False,
        ("init_spec_id",),
    )


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda payload: payload.__setitem__("derived_init_field_rules", ["missing_rule"]),
            "unknown rule",
        ),
        (
            lambda payload: payload.__setitem__("stage_defaults", {"id": "bad_default"}),
            "stage_defaults contains unexpected key",
        ),
        (
            lambda payload: payload["stages"][0].__setitem__("must_not_eager_load_groups", ["missing_group"]),
            "unknown group",
        ),
        (
            lambda payload: payload.__setitem__("authority_groupz", {"misspelled": []}),
            "unexpected key",
        ),
        (
            lambda payload: payload["required_init_field_groups"].__setitem__("bootstrap", []),
            "required_init_field_groups.bootstrap must not be empty",
        ),
    ],
)
def test_compact_manifest_rejects_unknown_compact_source(mutator, message: str) -> None:
    payload = _compact_payload()
    mutator(payload)

    with pytest.raises(ValueError, match=message):
        _validate(payload)


def test_compact_manifest_duplicate_failures_survive_expansion() -> None:
    payload = _compact_payload()
    payload["stages"][0]["must_not_eager_load"] = ["references/shared/canonical-schema-discipline.md"]

    with pytest.raises(ValueError, match="must_not_eager_load must not contain duplicate entries"):
        _validate(payload)


def test_compact_manifest_unknown_authority_paths_fail_after_group_expansion() -> None:
    payload = _compact_payload()
    payload["authority_groups"]["shared_deferred"] = ["references/shared/not-real.md"]

    with pytest.raises(ValueError, match="existing markdown file"):
        _validate(payload)


def test_compact_manifest_eager_lazy_overlap_fails_after_group_expansion() -> None:
    payload = _compact_payload()
    payload["authority_groups"]["shared_deferred"] = ["workflows/quick/task-bootstrap.md"]

    with pytest.raises(ValueError, match="overlap with must_not_eager_load"):
        _validate(payload)


def test_compact_manifest_source_payload_is_not_mutated() -> None:
    payload = _compact_payload()
    original = deepcopy(payload)

    canonicalize_workflow_stage_manifest_payload(payload)

    assert payload == original
