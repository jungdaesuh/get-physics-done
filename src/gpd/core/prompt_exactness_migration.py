"""Exactness migration ledger helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from gpd.core.prompt_markdown_scan import top_limit as _top_limit

_EXACTNESS_MIGRATION_SCHEMA_VERSION = "exactness_migration.v1"
_SEMANTIC_TAXONOMY_HELPER_NAMES = frozenset(("semantic_anchor", "semantic_concept"))
_PROMPT_CONTRACT_TEST_PATH_RE = re.compile(
    r"(?:^|/)tests/(?:core/)?test_.*(?:prompt|contract|workflow|stage|review|planner|executor|agent).*\.py$"
)


def exactness_migration_diagnostics(file_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    sorted_rows = tuple(sorted(file_rows, key=_exactness_migration_sort_key))
    totals = {
        "file_count": len(sorted_rows),
        "machine_exact_keep_assertions": sum(cast(int, row["machine_exact_keep_assertions"]) for row in sorted_rows),
        "public_exact_keep_assertions": sum(cast(int, row["public_exact_keep_assertions"]) for row in sorted_rows),
        "semantic_concept_candidate_assertions": sum(
            cast(int, row["semantic_concept_candidate_assertions"]) for row in sorted_rows
        ),
        "raw_brittle_prose_assertions": sum(cast(int, row["raw_brittle_prose_assertions"]) for row in sorted_rows),
        "taxonomy_helper_file_count": sum(1 for row in sorted_rows if cast(bool, row["uses_taxonomy_helpers"])),
        "taxonomy_helper_call_count": sum(cast(int, row["taxonomy_helper_call_count"]) for row in sorted_rows),
        "taxonomy_helper_brittle_file_count": sum(
            1
            for row in sorted_rows
            if cast(bool, row["uses_taxonomy_helpers"]) and cast(int, row["raw_brittle_prose_assertions"]) > 0
        ),
        "taxonomy_helper_brittle_assertions": sum(
            cast(int, row["raw_brittle_prose_assertions"])
            for row in sorted_rows
            if cast(bool, row["uses_taxonomy_helpers"])
        ),
    }
    return {
        "schema_version": _EXACTNESS_MIGRATION_SCHEMA_VERSION,
        "totals": totals,
        "files": [dict(row) for row in sorted_rows],
    }


def exactness_migration_file_row(
    path: str,
    classified_assertions: Sequence[Mapping[str, object]],
    taxonomy_usage: Mapping[str, object] | None,
    *,
    examples_per_category: int,
) -> dict[str, object]:
    by_category = {
        category: [entry for entry in classified_assertions if entry["category"] == category]
        for category in ("machine_contract", "public_ux", "brittle_prose")
    }
    helper_counts = dict(cast(Mapping[str, int], taxonomy_usage.get("helpers", {}))) if taxonomy_usage else {}
    helper_call_count = int(taxonomy_usage.get("helper_call_count", 0)) if taxonomy_usage else 0
    uses_taxonomy_helpers = bool(helper_counts)
    semantic_helper_call_count = sum(
        helper_counts.get(helper_name, 0) for helper_name in _SEMANTIC_TAXONOMY_HELPER_NAMES
    )
    semantic_candidates = [
        candidate
        for entry in by_category["brittle_prose"]
        if (
            candidate := _semantic_concept_candidate_entry(
                entry, path=path, uses_taxonomy_helpers=uses_taxonomy_helpers
            )
        )
        is not None
    ]
    raw_brittle_count = len(by_category["brittle_prose"])
    taxonomy_helper_brittle_warning = uses_taxonomy_helpers and raw_brittle_count > 0
    return {
        "path": path,
        "machine_exact_keep_assertions": len(by_category["machine_contract"]),
        "public_exact_keep_assertions": len(by_category["public_ux"]),
        "semantic_concept_candidate_assertions": len(semantic_candidates),
        "raw_brittle_prose_assertions": raw_brittle_count,
        "uses_taxonomy_helpers": uses_taxonomy_helpers,
        "taxonomy_helper_call_count": helper_call_count,
        "taxonomy_helpers": helper_counts,
        "semantic_helper_call_count": semantic_helper_call_count,
        "uses_semantic_helpers": semantic_helper_call_count > 0,
        "taxonomy_helper_brittle_warning": taxonomy_helper_brittle_warning,
        "taxonomy_helper_brittle_gate": "soft_warn" if taxonomy_helper_brittle_warning else "ok",
        "examples": {
            "machine_exact_keep": by_category["machine_contract"][:examples_per_category],
            "public_exact_keep": by_category["public_ux"][:examples_per_category],
            "semantic_concept_candidate": semantic_candidates[:examples_per_category],
            "raw_brittle_prose": by_category["brittle_prose"][:examples_per_category],
        },
    }


def bounded_exactness_migration(
    diagnostics: Mapping[str, object],
    top: int | None,
) -> Mapping[str, object]:
    limit = _top_limit(top)
    if limit is None:
        return diagnostics

    files = tuple(cast(Sequence[Mapping[str, object]], diagnostics.get("files", ())))
    payload = dict(diagnostics)
    payload["files"] = [dict(row) for row in files[:limit]]
    return payload


def _semantic_concept_candidate_entry(
    entry: Mapping[str, object],
    *,
    path: str,
    uses_taxonomy_helpers: bool,
) -> dict[str, object] | None:
    if entry.get("category") != "brittle_prose":
        return None

    polarity = entry.get("polarity")
    reason: str | None = None
    if polarity == "forbidden":
        reason = "forbidden_stale_prose"
    elif uses_taxonomy_helpers:
        reason = "taxonomy_helper_file_brittle_prose"
    elif _PROMPT_CONTRACT_TEST_PATH_RE.search(path):
        reason = "prompt_contract_file_brittle_prose"
    elif polarity == "required":
        reason = "required_internal_prompt_prose"

    if reason is None:
        return None
    candidate = dict(entry)
    candidate["migration_reason"] = reason
    return candidate


def _exactness_migration_sort_key(row: Mapping[str, object]) -> tuple[object, ...]:
    gate = row.get("taxonomy_helper_brittle_gate")
    gate_rank = 0 if gate == "soft_warn" else 1
    raw_brittle_count = cast(int, row["raw_brittle_prose_assertions"])
    semantic_candidate_count = cast(int, row["semantic_concept_candidate_assertions"])
    helper_call_count = cast(int, row["taxonomy_helper_call_count"])
    keep_count = cast(int, row["machine_exact_keep_assertions"]) + cast(int, row["public_exact_keep_assertions"])
    return (
        gate_rank,
        -raw_brittle_count,
        -semantic_candidate_count,
        -helper_call_count,
        -keep_count,
        cast(str, row["path"]),
    )
