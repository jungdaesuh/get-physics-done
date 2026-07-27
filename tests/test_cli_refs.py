"""CLI parity tests for the read-only ``gpd refs`` reference catalogs.

Both oracles are the shared ``gpd.core`` catalogs wrapped in the published
envelope. The protocols oracles are bound below under their published tool
names; the pinned literal expectations (counts, error strings, envelope
``schema_version``) keep the assertions honest.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.envelopes import stable_mcp_response
from gpd.core.protocol_catalog import (
    available_protocol_names,
    get_protocol_store,
    protocol_checkpoints_payload,
    protocol_detail_payload,
    protocol_listing_payload,
    protocol_route_payload,
)

runner = CliRunner()


# ── Core oracles for the protocol catalog ───────────────────────────────────


def list_protocols(domain: str | None = None) -> dict:
    return stable_mcp_response(protocol_listing_payload(get_protocol_store(), domain))


def get_protocol(name: str) -> dict:
    store = get_protocol_store()
    payload = protocol_detail_payload(store, name)
    if payload is None:
        return stable_mcp_response(
            {"available": available_protocol_names(store)},
            error=f"Protocol '{name}' not found",
        )
    return stable_mcp_response(payload)


def get_protocol_checkpoints(name: str) -> dict:
    store = get_protocol_store()
    payload = protocol_checkpoints_payload(store, name)
    if payload is None:
        return stable_mcp_response(
            {"available": available_protocol_names(store)},
            error=f"Protocol '{name}' not found",
        )
    return stable_mcp_response(payload)


def route_protocol(computation_type: str) -> dict:
    return stable_mcp_response(protocol_route_payload(get_protocol_store(), computation_type))


def _invoke(args: list[str]) -> object:
    return runner.invoke(app, ["--raw", *args], catch_exceptions=False)


def _error_store() -> object:
    from gpd.core import error_catalog

    return error_catalog.get_error_store()


def test_refs_errors_list_matches_core_payload() -> None:
    from gpd.core import error_catalog

    expected = stable_mcp_response(error_catalog.list_error_classes(_error_store(), None))
    result = _invoke(["refs", "errors"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected
    assert expected["count"] > 0


def test_refs_errors_domain_filter_matches_core_payload() -> None:
    from gpd.core import error_catalog

    expected = stable_mcp_response(error_catalog.list_error_classes(_error_store(), "core"))
    result = _invoke(["refs", "errors", "--domain", "core"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == expected
    assert payload["count"] < json.loads(_invoke(["refs", "errors"]).output)["count"]


def test_refs_errors_by_id_matches_core_payload() -> None:
    from gpd.core import error_catalog

    expected = stable_mcp_response(error_catalog.get_error_class(_error_store(), 3))
    result = _invoke(["refs", "errors", "--id", "3"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected
    assert expected["id"] == 3
    assert expected["detection_strategy"]


def test_refs_errors_detection_and_traceability_match_core_payloads() -> None:
    from gpd.core import error_catalog

    expected_detection = stable_mcp_response(error_catalog.get_detection_strategy(_error_store(), 3))
    expected_traceability = stable_mcp_response(error_catalog.get_traceability(_error_store(), 3))

    detection_result = _invoke(["refs", "errors", "--id", "3", "--detection"])
    traceability_result = _invoke(["refs", "errors", "--id", "3", "--traceability"])

    assert detection_result.exit_code == 0, detection_result.output
    assert json.loads(detection_result.output) == expected_detection
    assert traceability_result.exit_code == 0, traceability_result.output
    assert json.loads(traceability_result.output) == expected_traceability
    assert expected_detection != expected_traceability


def test_refs_errors_unknown_id_emits_the_full_core_envelope_and_exits_one() -> None:
    from gpd.core import error_catalog

    expected = stable_mcp_response(error_catalog.get_error_class(_error_store(), 99999))
    result = _invoke(["refs", "errors", "--id", "99999"])

    assert result.exit_code == 1
    assert json.loads(result.output) == expected
    assert expected == {
        "valid_range": error_catalog.ERROR_ID_RANGE_LABEL,
        "total_classes": _error_store().count,
        "error": "Error class #99999 not found",
        "schema_version": 1,
    }


def test_refs_errors_rejects_domain_combined_with_id() -> None:
    result = _invoke(["refs", "errors", "--domain", "core", "--id", "3"])

    assert result.exit_code == 1
    assert "--domain" in result.output
    assert "--id" in result.output


def test_refs_errors_unknown_domain_emits_error_envelope_and_exits_one() -> None:
    result = _invoke(["refs", "errors", "--domain", "bogus"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert "unknown domain 'bogus'" in payload["error"]


def test_refs_errors_rejects_detection_without_id() -> None:
    result = _invoke(["refs", "errors", "--detection"])

    assert result.exit_code == 1
    assert "--id" in result.output


def test_refs_protocols_list_matches_core_payload() -> None:
    expected = list_protocols()
    result = _invoke(["refs", "protocols"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected
    assert expected["count"] > 0


def test_refs_protocols_domain_filter_matches_core_payload() -> None:
    unfiltered = list_protocols()
    domain = unfiltered["available_domains"][0]
    expected = list_protocols(domain)

    result = _invoke(["refs", "protocols", "--domain", domain])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected
    assert 0 < expected["count"] < unfiltered["count"]
    assert {protocol["domain"] for protocol in expected["protocols"]} == {domain}


def test_refs_protocols_unknown_domain_emits_error_envelope_and_exits_one() -> None:
    result = _invoke(["refs", "protocols", "--domain", "bogus"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload == {"error": "Unknown protocol domain: bogus", "schema_version": 1}


def test_refs_protocols_rejects_domain_combined_with_a_selector() -> None:
    result = _invoke(["refs", "protocols", "--domain", "qft", "--name", "perturbation-theory"])

    assert result.exit_code == 1
    assert "--domain" in result.output


def test_refs_protocols_rejects_blank_selector_values() -> None:
    for option in ("--name", "--route", "--checkpoints"):
        result = _invoke(["refs", "protocols", option, "   "])

        assert result.exit_code == 1, f"{option} accepted a whitespace-only value"
        assert "non-empty" in result.output


def test_refs_protocols_by_name_matches_core_payload() -> None:
    name = list_protocols()["protocols"][0]["name"]
    expected = get_protocol(name)

    result = _invoke(["refs", "protocols", "--name", name])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected
    assert expected["name"] == name


def test_refs_protocols_route_matches_core_payload() -> None:
    query = "perturbative expansion with renormalization"
    expected = route_protocol(query)

    result = _invoke(["refs", "protocols", "--route", query])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected
    assert expected["query"] == query


def test_refs_protocols_checkpoints_matches_core_payload() -> None:
    name = list_protocols()["protocols"][0]["name"]
    expected = get_protocol_checkpoints(name)

    result = _invoke(["refs", "protocols", "--checkpoints", name])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected
    assert expected["name"] == name


def test_refs_protocols_unknown_name_lists_available_and_exits_one() -> None:
    expected = get_protocol("not-a-protocol")
    result = _invoke(["refs", "protocols", "--name", "not-a-protocol"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload == expected
    assert payload["error"] == "Protocol 'not-a-protocol' not found"
    assert payload["schema_version"] == 1


def test_refs_protocols_rejects_multiple_selectors() -> None:
    result = _invoke(["refs", "protocols", "--name", "a", "--route", "b"])

    assert result.exit_code == 1
    assert "at most one" in result.output
