"""Provider-free physics false-claim canary tests."""

from __future__ import annotations

import json
from dataclasses import fields, replace

import pytest

from tests.helpers.physics_false_claim_canaries import (
    PHYSICS_FALSE_CLAIM_CANARIES_PATH,
    REQUIRED_PHYSICS_FALSE_CLAIM_ROW_IDS,
    PhysicsFalseClaimCanaryRow,
    assert_no_provider_network_raw_fields,
    load_physics_false_claim_canary_rows,
    score_physics_false_claim_canary_row,
    score_physics_false_claim_canary_rows,
)


def test_physics_false_claim_fixture_contains_required_class_only_rows() -> None:
    rows = load_physics_false_claim_canary_rows()

    assert {row.row_id for row in rows} == REQUIRED_PHYSICS_FALSE_CLAIM_ROW_IDS
    assert all(row.fixture_family == "false_claim_class" for row in rows)
    assert all(row.variant_class == "class_only" for row in rows)
    assert all(row.domain_opening_classes for row in rows)
    assert all(row.concrete_check_classes for row in rows)


def test_physics_false_claim_fixture_has_no_provider_network_or_raw_fields() -> None:
    payload = json.loads(PHYSICS_FALSE_CLAIM_CANARIES_PATH.read_text(encoding="utf-8"))
    row_field_names = {field.name: "class_only" for field in fields(PhysicsFalseClaimCanaryRow)}

    assert_no_provider_network_raw_fields(payload)
    assert_no_provider_network_raw_fields(row_field_names)
    with pytest.raises(AssertionError, match="forbidden provider/network/raw field"):
        assert_no_provider_network_raw_fields({"provider_stdout": "class_only"})
    with pytest.raises(AssertionError, match="forbidden provider/network/raw field"):
        assert_no_provider_network_raw_fields({"network_allowed": "class_only"})
    with pytest.raises(AssertionError, match="forbidden provider/network/raw field"):
        assert_no_provider_network_raw_fields({"raw_transcript": "class_only"})


def test_physics_false_claim_rows_pass_metric_bounds() -> None:
    scores = score_physics_false_claim_canary_rows(load_physics_false_claim_canary_rows())

    assert {score.row.row_id for score in scores} == REQUIRED_PHYSICS_FALSE_CLAIM_ROW_IDS
    for score in scores:
        assert score.passed
        assert score.hard_budget_failures == ()
        assert score.metric_counts["domain_check_opened"] >= 1
        assert score.metric_counts["concrete_physics_check_count"] >= 2


@pytest.mark.parametrize(
    ("row_override", "expected_metric"),
    (
        ({"domain_opening_classes": ()}, "domain_check_opened"),
        ({"concrete_check_classes": ()}, "concrete_physics_check_count"),
        ({"handle_ack_classes": ("unopened_handle_ack",)}, "unopened_handle_ack_count"),
        ({"schema_surface_classes": ("return_schema_wall",)}, "schema_surface_count"),
    ),
)
def test_physics_false_claim_metric_failures_are_independent(
    row_override: dict[str, tuple[str, ...]],
    expected_metric: str,
) -> None:
    base_row = _row("EXEC-NR-01")
    bad_row = replace(base_row, **row_override)

    score = score_physics_false_claim_canary_row(bad_row)

    assert not score.passed
    assert score.hard_budget_failures == (expected_metric,)
    assert (
        score.metric_counts[expected_metric]
        != score_physics_false_claim_canary_row(base_row).metric_counts[expected_metric]
    )


def _row(row_id: str) -> PhysicsFalseClaimCanaryRow:
    rows = {row.row_id: row for row in load_physics_false_claim_canary_rows()}
    return rows[row_id]
