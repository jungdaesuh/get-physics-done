"""Focused tests for the ``gpd_return`` field metadata registry."""

from __future__ import annotations

import pytest

from gpd.core import return_fields
from gpd.core.return_contract import (
    ALLOWED_RETURN_EXTENSION_FIELDS,
    KNOWN_RETURN_FIELD_NAMES,
    RETURN_ENVELOPE_STATUS_CONTRACTS,
    RETURN_STATUS_ORDER,
    GpdReturnEnvelope,
    return_field_allowed_for_status,
    return_field_allowed_source,
    return_fields_allowed_for_status,
    validate_gpd_return_markdown,
)


def _wrap_return_block(yaml_body: str) -> str:
    return f"```yaml\ngpd_return:\n{yaml_body}```\n"


def test_allowed_extension_fields_derive_from_registry_specs() -> None:
    assert ALLOWED_RETURN_EXTENSION_FIELDS == return_fields.allowed_return_extension_fields()
    assert set(return_fields.RETURN_EXTENSION_FIELD_SPECS) == set(ALLOWED_RETURN_EXTENSION_FIELDS)
    assert {
        spec.name for spec in return_fields.RETURN_EXTENSION_FIELD_SPECS.values()
    } == ALLOWED_RETURN_EXTENSION_FIELDS
    assert {spec.source for spec in return_fields.RETURN_EXTENSION_FIELD_SPECS.values()} == {"extension"}


def test_known_field_helpers_remain_model_fields_plus_registered_extensions() -> None:
    model_fields = tuple(GpdReturnEnvelope.model_fields)

    assert KNOWN_RETURN_FIELD_NAMES == return_fields.known_return_field_names(model_fields)
    assert KNOWN_RETURN_FIELD_NAMES == frozenset(model_fields) | ALLOWED_RETURN_EXTENSION_FIELDS
    assert return_field_allowed_source("status") == "base"
    assert return_field_allowed_source("confidence") == "extension"
    assert return_field_allowed_source("file_written") == "unknown"
    assert return_fields.return_field_source("confidence", base_fields=model_fields) == "extension"


def test_registry_status_applicability_matches_return_contract_helpers() -> None:
    model_fields = tuple(GpdReturnEnvelope.model_fields)

    for field_name in sorted(KNOWN_RETURN_FIELD_NAMES | {"file_written"}):
        for status in RETURN_STATUS_ORDER:
            assert return_field_allowed_for_status(field_name, status) is return_fields.return_field_status_allowed(
                field_name,
                status,
                base_fields=model_fields,
                status_contracts=RETURN_ENVELOPE_STATUS_CONTRACTS,
            )

    assert return_fields.return_field_status_applicability(
        "state_updates",
        base_fields=model_fields,
        status_contracts=RETURN_ENVELOPE_STATUS_CONTRACTS,
        all_statuses=RETURN_STATUS_ORDER,
    ) == ("completed", "checkpoint")
    assert return_fields.return_field_status_applicability(
        "checkpoint_intent",
        base_fields=model_fields,
        status_contracts=RETURN_ENVELOPE_STATUS_CONTRACTS,
        all_statuses=RETURN_STATUS_ORDER,
    ) == ("checkpoint",)
    assert (
        return_fields.return_field_status_applicability(
            "confidence",
            base_fields=model_fields,
            status_contracts=RETURN_ENVELOPE_STATUS_CONTRACTS,
            all_statuses=RETURN_STATUS_ORDER,
        )
        == RETURN_STATUS_ORDER
    )
    assert (
        return_fields.return_field_status_applicability(
            "file_written",
            base_fields=model_fields,
            status_contracts=RETURN_ENVELOPE_STATUS_CONTRACTS,
            all_statuses=RETURN_STATUS_ORDER,
        )
        == ()
    )


def test_status_allowed_field_lists_are_registry_backed_and_stable() -> None:
    model_fields = tuple(GpdReturnEnvelope.model_fields)

    for status in RETURN_STATUS_ORDER:
        assert return_fields_allowed_for_status(status) == return_fields.return_fields_allowed_for_status(
            status,
            base_fields=model_fields,
            status_contracts=RETURN_ENVELOPE_STATUS_CONTRACTS,
        )

    assert "checkpoint_intent" not in return_fields_allowed_for_status("completed")
    assert "checkpoint_intent" in return_fields_allowed_for_status("checkpoint")
    assert "confidence" in return_fields_allowed_for_status("failed")


def test_registry_validation_and_default_metadata_hooks_are_copy_safe() -> None:
    assert return_fields.return_field_validation_owner("confidence") == "return_contract.extension_yaml_native"
    assert return_fields.return_field_validation_owner("continuation_update") == "return_contract.continuation_update"
    assert return_fields.return_field_validation_owner("file_written") is None

    first_plans_default = return_fields.return_field_default("plans")
    second_plans_default = return_fields.return_field_default("plans")

    assert first_plans_default == []
    assert second_plans_default == []
    assert first_plans_default is not second_plans_default
    assert return_fields.return_field_default("phase", phase="03") == "03"
    assert return_fields.return_field_default("plan") == "unknown"

    with pytest.raises(KeyError, match="affected_quantities"):
        return_fields.return_field_default("affected_quantities")


def test_registry_backed_contract_still_rejects_unknown_top_level_fields() -> None:
    content = _wrap_return_block(
        "  status: completed\n"
        "  files_written: [src/main.py]\n"
        "  issues: []\n"
        "  next_actions: []\n"
        "  file_written: [src/main.py]\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any("Unknown gpd_return top-level field" in error and "file_written" in error for error in result.errors)


@pytest.mark.parametrize("status", ["blocked", "failed"])
def test_status_disallowed_structured_fields_still_fail_for_blocking_statuses(status: str) -> None:
    content = _wrap_return_block(
        f"  status: {status}\n"
        "  files_written: []\n"
        "  issues: [waiting]\n"
        "  next_actions: [gpd:resume-work]\n"
        "  state_updates:\n"
        "    advance_plan: true\n"
    )

    result = validate_gpd_return_markdown(content)

    assert result.passed is False
    assert any(f"status '{status}'" in error and "state_updates" in error for error in result.errors)
