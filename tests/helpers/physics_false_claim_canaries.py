"""Provider-free physics false-claim canary rows."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PHYSICS_FALSE_CLAIM_CANARIES_PATH = REPO_ROOT / "tests" / "fixtures" / "physics_false_claim_canaries.json"
PHYSICS_FALSE_CLAIM_SCHEMA_VERSION = "physics_false_claim_canaries.v1"
REQUIRED_PHYSICS_FALSE_CLAIM_ROW_IDS = frozenset(
    {
        "NP-CICY-01",
        "MAP-MHD-01",
        "PLAN-LGT-01",
        "EXEC-NR-01",
        "VERIFY-QFT-01",
        "VERIFY-MATH-01",
        "PEER-COND-01",
        "WRITE-TN-01",
    }
)

_ROW_ID_RE = re.compile(r"^(?:NP|MAP|PLAN|EXEC|VERIFY|PEER|WRITE)-[A-Z0-9]+-[0-9]{2}$")
_CLASS_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_FORBIDDEN_FIELD_FRAGMENTS = frozenset(
    {
        "account",
        "api_key",
        "argv",
        "body",
        "command",
        "content",
        "env",
        "launch",
        "markdown",
        "network",
        "path",
        "prompt",
        "provider",
        "raw",
        "reply",
        "secret",
        "stderr",
        "stdout",
        "text",
        "token",
        "transcript",
    }
)
_FORBIDDEN_VALUE_FRAGMENTS = frozenset(
    {
        "api_key",
        "auth_token",
        "provider_stdout",
        "provider_stderr",
        "raw_prompt",
        "raw_reply",
        "raw_transcript",
        "subprocess",
        "transcript_excerpt",
    }
)
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:/(?:Users|home|private|tmp|var|etc|Volumes|opt|mnt|root)\b|~[/\\])"
)
_ACCOUNT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_HASH_RE = re.compile(r"\b(?:[A-Fa-f0-9]{32}|[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})\b")
_SECRET_ENV_RE = re.compile(r"\b[A-Z][A-Z0-9_]*(?:API_KEY|AUTH_TOKEN|ACCESS_TOKEN|SECRET|TOKEN)\b")
_DOMAIN_OPENING_SUFFIXES = (
    "_bundle_checklist_opened",
    "_domain_check_opened",
    "_execution_guard_opened",
    "_execution_guide_opened",
    "_verification_domain_opened",
)
_HANDLE_ACK_CLASSES = frozenset({"unopened_handle_ack"})
_METRIC_KEYS = (
    "domain_check_opened",
    "concrete_physics_check_count",
    "unopened_handle_ack_count",
    "schema_surface_count",
)


@dataclass(frozen=True, slots=True)
class PhysicsFalseClaimCanaryRow:
    row_id: str
    workflow_class: str
    fixture_family: str
    variant_class: str
    bundle_ids: tuple[str, ...]
    fallback_domain_classes: tuple[str, ...]
    domain_opening_classes: tuple[str, ...]
    concrete_check_classes: tuple[str, ...]
    handle_ack_classes: tuple[str, ...]
    schema_surface_classes: tuple[str, ...]
    metric_bounds: Mapping[str, Mapping[str, int]]
    schema_version: str = PHYSICS_FALSE_CLAIM_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class PhysicsFalseClaimCanaryScore:
    row: PhysicsFalseClaimCanaryRow
    metric_counts: Mapping[str, int]
    hard_budget_failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.hard_budget_failures


def load_physics_false_claim_canary_rows(
    path: Path = PHYSICS_FALSE_CLAIM_CANARIES_PATH,
) -> tuple[PhysicsFalseClaimCanaryRow, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert_no_provider_network_raw_fields(payload)
    schema_version = str(payload.get("schema_version", ""))
    if schema_version != PHYSICS_FALSE_CLAIM_SCHEMA_VERSION:
        raise AssertionError(f"unexpected schema_version {schema_version}")

    rows = tuple(_row_from_mapping(row, schema_version) for row in payload["rows"])
    row_ids = {row.row_id for row in rows}
    if row_ids != REQUIRED_PHYSICS_FALSE_CLAIM_ROW_IDS:
        missing = sorted(REQUIRED_PHYSICS_FALSE_CLAIM_ROW_IDS - row_ids)
        unexpected = sorted(row_ids - REQUIRED_PHYSICS_FALSE_CLAIM_ROW_IDS)
        raise AssertionError(f"unexpected physics false-claim row ids missing={missing} unexpected={unexpected}")
    if len(row_ids) != len(rows):
        raise AssertionError("physics false-claim row ids must be unique")
    for row in rows:
        _validate_row(row)
    return rows


def score_physics_false_claim_canary_row(
    row: PhysicsFalseClaimCanaryRow,
) -> PhysicsFalseClaimCanaryScore:
    counts = {
        "domain_check_opened": len({token for token in row.domain_opening_classes if _is_domain_opening_class(token)}),
        "concrete_physics_check_count": len(
            {token for token in row.concrete_check_classes if token.endswith("_check")}
        ),
        "unopened_handle_ack_count": sum(token in _HANDLE_ACK_CLASSES for token in row.handle_ack_classes),
        "schema_surface_count": len(row.schema_surface_classes),
    }
    failures = _metric_bound_failures(row.metric_bounds, counts)
    return PhysicsFalseClaimCanaryScore(row=row, metric_counts=counts, hard_budget_failures=failures)


def score_physics_false_claim_canary_rows(
    rows: Sequence[PhysicsFalseClaimCanaryRow],
) -> tuple[PhysicsFalseClaimCanaryScore, ...]:
    return tuple(score_physics_false_claim_canary_row(row) for row in rows)


def assert_no_provider_network_raw_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            lowered_key = key_text.lower()
            if any(fragment in lowered_key for fragment in _FORBIDDEN_FIELD_FRAGMENTS):
                raise AssertionError(f"forbidden provider/network/raw field {key_text}")
            assert_no_provider_network_raw_fields(child)
        return
    if isinstance(value, list):
        for child in value:
            assert_no_provider_network_raw_fields(child)
        return
    if isinstance(value, str):
        _assert_provider_free_string(value)


def _row_from_mapping(
    row: Mapping[str, object],
    schema_version: str,
) -> PhysicsFalseClaimCanaryRow:
    return PhysicsFalseClaimCanaryRow(
        row_id=str(row["row_id"]),
        workflow_class=str(row["workflow_class"]),
        fixture_family=str(row["fixture_family"]),
        variant_class=str(row["variant_class"]),
        bundle_ids=_str_tuple(row.get("bundle_ids", ())),
        fallback_domain_classes=_str_tuple(row.get("fallback_domain_classes", ())),
        domain_opening_classes=_str_tuple(row["domain_opening_classes"]),
        concrete_check_classes=_str_tuple(row["concrete_check_classes"]),
        handle_ack_classes=_str_tuple(row.get("handle_ack_classes", ())),
        schema_surface_classes=_str_tuple(row.get("schema_surface_classes", ())),
        metric_bounds=_metric_bounds(row["metric_bounds"]),
        schema_version=schema_version,
    )


def _validate_row(row: PhysicsFalseClaimCanaryRow) -> None:
    if not _ROW_ID_RE.fullmatch(row.row_id):
        raise AssertionError(f"{row.row_id} has invalid row id")
    for field_name in (
        "workflow_class",
        "fixture_family",
        "variant_class",
    ):
        _assert_class_token(getattr(row, field_name), f"{row.row_id}.{field_name}")
    if row.fixture_family != "false_claim_class":
        raise AssertionError(f"{row.row_id} fixture_family must be false_claim_class")
    if row.variant_class != "class_only":
        raise AssertionError(f"{row.row_id} variant_class must be class_only")
    for field_name in (
        "bundle_ids",
        "fallback_domain_classes",
        "domain_opening_classes",
        "concrete_check_classes",
        "handle_ack_classes",
        "schema_surface_classes",
    ):
        for token in getattr(row, field_name):
            _assert_class_token(token, f"{row.row_id}.{field_name}")
    if not row.domain_opening_classes:
        raise AssertionError(f"{row.row_id} must name at least one opened domain/check surface")
    if not all(_is_domain_opening_class(token) for token in row.domain_opening_classes):
        raise AssertionError(f"{row.row_id} has a non-opening domain class")
    if not row.concrete_check_classes:
        raise AssertionError(f"{row.row_id} must name at least one concrete check")
    if not all(token.endswith("_check") for token in row.concrete_check_classes):
        raise AssertionError(f"{row.row_id} concrete checks must end in _check")
    if not set(row.handle_ack_classes) <= _HANDLE_ACK_CLASSES:
        raise AssertionError(f"{row.row_id} has an unsupported handle ack class")
    if set(row.metric_bounds) != set(_METRIC_KEYS):
        raise AssertionError(f"{row.row_id} must bound exactly {', '.join(_METRIC_KEYS)}")


def _metric_bounds(raw_bounds: object) -> dict[str, dict[str, int]]:
    if not isinstance(raw_bounds, Mapping):
        raise AssertionError("metric_bounds must be a mapping")
    return {str(metric_key): _metric_bound(raw_bound) for metric_key, raw_bound in raw_bounds.items()}


def _metric_bound(raw_bound: object) -> dict[str, int]:
    if not isinstance(raw_bound, Mapping):
        raise AssertionError("metric bound must be a mapping")
    bound: dict[str, int] = {}
    for key in ("exact", "min", "max"):
        if key not in raw_bound:
            continue
        value = int(raw_bound[key])
        if value < 0:
            raise AssertionError("metric bounds must be non-negative")
        bound[key] = value
    if not bound:
        raise AssertionError("metric bound must include exact, min, or max")
    return bound


def _metric_bound_failures(
    bounds: Mapping[str, Mapping[str, int]],
    counts: Mapping[str, int],
) -> tuple[str, ...]:
    failures: list[str] = []
    for metric_key in _METRIC_KEYS:
        bound = bounds[metric_key]
        observed = counts[metric_key]
        if "exact" in bound and observed != bound["exact"]:
            failures.append(metric_key)
            continue
        if "min" in bound and observed < bound["min"]:
            failures.append(metric_key)
            continue
        if "max" in bound and observed > bound["max"]:
            failures.append(metric_key)
    return tuple(failures)


def _assert_class_token(value: str, field_name: str) -> None:
    if not _CLASS_TOKEN_RE.fullmatch(value):
        raise AssertionError(f"{field_name} must be a class token")


def _assert_provider_free_string(value: str) -> None:
    lowered = value.lower()
    if any(fragment in lowered for fragment in _FORBIDDEN_VALUE_FRAGMENTS):
        raise AssertionError(f"forbidden provider/network/raw value {value}")
    if _ABSOLUTE_PATH_RE.search(value) is not None:
        raise AssertionError(f"absolute path is not allowed in class-only fixture value {value}")
    if _ACCOUNT_RE.search(value) is not None:
        raise AssertionError(f"account identifier is not allowed in class-only fixture value {value}")
    if _HASH_RE.search(value) is not None:
        raise AssertionError(f"hash-like value is not allowed in class-only fixture value {value}")
    if _SECRET_ENV_RE.search(value) is not None:
        raise AssertionError(f"secret env var is not allowed in class-only fixture value {value}")


def _is_domain_opening_class(token: str) -> bool:
    return token == "domain_check_opened" or token.endswith(_DOMAIN_OPENING_SUFFIXES)


def _str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


__all__ = [
    "PHYSICS_FALSE_CLAIM_CANARIES_PATH",
    "REQUIRED_PHYSICS_FALSE_CLAIM_ROW_IDS",
    "PhysicsFalseClaimCanaryRow",
    "PhysicsFalseClaimCanaryScore",
    "assert_no_provider_network_raw_fields",
    "load_physics_false_claim_canary_rows",
    "score_physics_false_claim_canary_row",
    "score_physics_false_claim_canary_rows",
]
