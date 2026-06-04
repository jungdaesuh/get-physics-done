"""Contract tests for the shared strict JSON helper surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import gpd.core.strict_json_contract as strict_json


def test_load_json_file_and_require_object_preserve_labels(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"name": "alpha"}), encoding="utf-8")

    loaded = strict_json.load_json_file(payload_path, label="runtime catalog")
    assert strict_json.require_object(loaded, label="runtime catalog") == {"name": "alpha"}

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_object([], label="runtime catalog")
    message = str(exc_info.value)
    assert "runtime catalog" in message
    assert "JSON object" in message

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_object({}, label="runtime catalog", non_empty=True)
    message = str(exc_info.value)
    assert "runtime catalog" in message
    assert "non-empty JSON object" in message


def test_required_and_allowed_key_helpers_report_sorted_key_names() -> None:
    payload = {"beta": 1, "delta": 2}

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_required_keys(payload, label="surface.schema", keys=("alpha", "beta", "gamma"))
    message = str(exc_info.value)
    assert "surface.schema" in message
    assert "alpha, gamma" in message

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_allowed_keys(payload, label="surface.schema", keys=("alpha", "beta"))
    message = str(exc_info.value)
    assert "surface.schema" in message
    assert "delta" in message


def test_schema_version_and_numeric_helpers_reject_bool_as_int() -> None:
    assert strict_json.require_schema_version(1, label="runtime_catalog.schema_version", expected=1) == 1
    assert strict_json.require_bool(False, label="runtime.enabled") is False
    assert strict_json.require_int(3, label="runtime.order") == 3

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_schema_version(True, label="runtime_catalog.schema_version", expected=1)
    message = str(exc_info.value)
    assert "runtime_catalog.schema_version" in message
    assert "integer" in message
    assert "True" in message

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_int(True, label="runtime.order")
    message = str(exc_info.value)
    assert "runtime.order" in message
    assert "integer" in message

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_bool(1, label="runtime.enabled")
    message = str(exc_info.value)
    assert "runtime.enabled" in message
    assert "boolean" in message


def test_string_helpers_support_trimmed_and_no_trim_contracts() -> None:
    assert strict_json.require_string("value", label="public.name") == "value"
    assert strict_json.require_string(" value ", label="public.name", trim=True) == "value"

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_string(" value ", label="runtime.name")
    message = str(exc_info.value)
    assert "runtime.name" in message
    assert "non-empty string" in message

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_string("", label="runtime.name")
    message = str(exc_info.value)
    assert "runtime.name" in message
    assert "non-empty string" in message


def test_unique_string_tuple_and_literal_helpers_keep_domain_labels() -> None:
    assert strict_json.require_unique_string_tuple(
        [" alpha ", "beta"],
        label="public.commands",
        allow_empty=False,
        trim=True,
    ) == ("alpha", "beta")
    assert strict_json.require_literal("beta", label="public.mode", allowed=("alpha", "beta")) == "beta"

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_unique_string_tuple(["alpha", "alpha"], label="public.commands", allow_empty=False)
    message = str(exc_info.value)
    assert "public.commands" in message
    assert "duplicate" in message

    with pytest.raises(ValueError) as exc_info:
        strict_json.require_literal("gamma", label="public.mode", allowed=("alpha", "beta"))
    message = str(exc_info.value)
    assert "public.mode" in message
    assert "gamma" in message
    assert "alpha" in message
    assert "beta" in message


def test_key_coverage_helper_reports_missing_and_unknown_keys_together() -> None:
    with pytest.raises(ValueError) as exc_info:
        strict_json.require_key_coverage(
            {"known": 1, "extra": 2},
            label="surface.sections",
            allowed_keys=("known", "required"),
            required_keys=("known", "required"),
        )
    message = str(exc_info.value)
    assert "surface.sections" in message
    assert "required" in message
    assert "extra" in message
