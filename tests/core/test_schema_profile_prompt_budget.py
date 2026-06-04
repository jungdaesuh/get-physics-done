"""Prompt footprint guardrails for schema/profile authority docs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.prompt_metrics_support import (
    budget_from_baseline,
    expanded_include_markers,
    expanded_prompt_text,
    measure_prompt_surface,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"

MIN_LINE_MARGIN = 20
MIN_CHAR_MARGIN = 1_000
AGGREGATE_MIN_LINE_MARGIN = 75
AGGREGATE_MIN_CHAR_MARGIN = 5_000


@dataclass(frozen=True, slots=True)
class AuthorityDocBudget:
    rel_path: str
    baseline_lines: int
    baseline_chars: int
    max_raw_includes: int
    semantic_anchors: tuple[str, ...]
    required_include_markers: tuple[str, ...] = ()
    allowed_include_markers: tuple[str, ...] = ()

    @property
    def path(self) -> Path:
        return SOURCE_ROOT / self.rel_path


SELECTED_AUTHORITY_DOCS = (
    "specs/templates/state-json-schema.md",
    "specs/references/orchestration/model-profiles.md",
    "specs/references/publication/peer-review-panel.md",
    "specs/references/verification/meta/verifier-profile-checks.md",
    "specs/templates/plan-contract-schema.md",
    "specs/templates/project-contract-schema.md",
    "specs/templates/contract-results-schema.md",
)

AUTHORITY_DOC_BUDGETS = (
    AuthorityDocBudget(
        rel_path="specs/templates/state-json-schema.md",
        baseline_lines=748,
        baseline_chars=39_981,
        max_raw_includes=1,
        semantic_anchors=("GPD/state.json", "project_contract", "continuation", "contract_alignment"),
        required_include_markers=("project-contract-schema.md",),
        allowed_include_markers=(
            "project-contract-schema.md",
            "contract-proof-obligation-rules.md",
            "project-contract-grounding-linkage.md",
        ),
    ),
    AuthorityDocBudget(
        rel_path="specs/references/orchestration/model-profiles.md",
        baseline_lines=285,
        baseline_chars=32_850,
        max_raw_includes=0,
        semantic_anchors=("deep-theory", "numerical", "exploratory", "review", "paper-writing"),
    ),
    AuthorityDocBudget(
        rel_path="specs/references/publication/peer-review-panel.md",
        baseline_lines=190,
        baseline_chars=9_500,
        max_raw_includes=0,
        semantic_anchors=("Peer Review Panel Protocol", "ClaimIndex", "StageReviewReport", "gpd-referee"),
    ),
    AuthorityDocBudget(
        rel_path="specs/references/verification/meta/verifier-profile-checks.md",
        baseline_lines=517,
        baseline_chars=23_837,
        max_raw_includes=0,
        semantic_anchors=("Verifier Profile-Specific Checks", "Domain Loading Map", "CHECK", "COMPUTE"),
    ),
    AuthorityDocBudget(
        rel_path="specs/templates/plan-contract-schema.md",
        baseline_lines=357,
        baseline_chars=19_217,
        max_raw_includes=1,
        semantic_anchors=("PLAN Contract Schema", "claims[]", "acceptance_tests", "forbidden_proxies"),
        required_include_markers=("contract-proof-obligation-rules.md",),
        allowed_include_markers=("contract-proof-obligation-rules.md",),
    ),
    AuthorityDocBudget(
        rel_path="specs/templates/project-contract-schema.md",
        baseline_lines=299,
        baseline_chars=18_239,
        max_raw_includes=2,
        semantic_anchors=("Project Contract Schema", "project_contract", "context_intake", "approach_policy"),
        required_include_markers=("contract-proof-obligation-rules.md", "project-contract-grounding-linkage.md"),
        allowed_include_markers=("contract-proof-obligation-rules.md", "project-contract-grounding-linkage.md"),
    ),
    AuthorityDocBudget(
        rel_path="specs/templates/contract-results-schema.md",
        baseline_lines=253,
        baseline_chars=17_464,
        max_raw_includes=0,
        semantic_anchors=("Contract Results Schema", "plan_contract_ref", "contract_results", "proof_audit"),
    ),
)

AGGREGATE_BASELINE_LINES = 2_650
AGGREGATE_BASELINE_CHARS = 165_000


def _assert_prompt_baseline_is_current(
    *,
    baseline_lines: int,
    baseline_chars: int,
    measured_lines: int,
    measured_chars: int,
    min_line_margin: int,
    min_char_margin: int,
) -> None:
    assert baseline_lines <= budget_from_baseline(measured_lines, minimum_margin=min_line_margin)
    assert baseline_chars <= budget_from_baseline(measured_chars, minimum_margin=min_char_margin)


def test_schema_profile_budget_covers_report_selected_authority_docs() -> None:
    assert tuple(doc.rel_path for doc in AUTHORITY_DOC_BUDGETS) == SELECTED_AUTHORITY_DOCS


@pytest.mark.parametrize("doc", AUTHORITY_DOC_BUDGETS, ids=lambda doc: doc.rel_path)
def test_schema_profile_authority_doc_stays_under_expanded_budget(doc: AuthorityDocBudget) -> None:
    metrics = measure_prompt_surface(doc.path, src_root=SOURCE_ROOT, path_prefix=PATH_PREFIX)

    assert metrics.raw_include_count <= doc.max_raw_includes
    _assert_prompt_baseline_is_current(
        baseline_lines=doc.baseline_lines,
        baseline_chars=doc.baseline_chars,
        measured_lines=metrics.expanded_line_count,
        measured_chars=metrics.expanded_char_count,
        min_line_margin=MIN_LINE_MARGIN,
        min_char_margin=MIN_CHAR_MARGIN,
    )
    assert metrics.expanded_line_count <= budget_from_baseline(
        doc.baseline_lines,
        minimum_margin=MIN_LINE_MARGIN,
    )
    assert metrics.expanded_char_count <= budget_from_baseline(
        doc.baseline_chars,
        minimum_margin=MIN_CHAR_MARGIN,
    )


def test_schema_profile_authority_bundle_stays_under_expanded_budget() -> None:
    total_lines = 0
    total_chars = 0
    for doc in AUTHORITY_DOC_BUDGETS:
        metrics = measure_prompt_surface(doc.path, src_root=SOURCE_ROOT, path_prefix=PATH_PREFIX)
        total_lines += metrics.expanded_line_count
        total_chars += metrics.expanded_char_count

    _assert_prompt_baseline_is_current(
        baseline_lines=AGGREGATE_BASELINE_LINES,
        baseline_chars=AGGREGATE_BASELINE_CHARS,
        measured_lines=total_lines,
        measured_chars=total_chars,
        min_line_margin=AGGREGATE_MIN_LINE_MARGIN,
        min_char_margin=AGGREGATE_MIN_CHAR_MARGIN,
    )
    assert total_lines <= budget_from_baseline(
        AGGREGATE_BASELINE_LINES,
        minimum_margin=AGGREGATE_MIN_LINE_MARGIN,
    )
    assert total_chars <= budget_from_baseline(
        AGGREGATE_BASELINE_CHARS,
        minimum_margin=AGGREGATE_MIN_CHAR_MARGIN,
    )


@pytest.mark.parametrize("doc", AUTHORITY_DOC_BUDGETS, ids=lambda doc: doc.rel_path)
def test_schema_profile_authority_docs_keep_semantic_anchors(doc: AuthorityDocBudget) -> None:
    expanded_text = expanded_prompt_text(doc.path, src_root=SOURCE_ROOT, path_prefix=PATH_PREFIX)

    for anchor in doc.semantic_anchors:
        assert anchor in expanded_text


@pytest.mark.parametrize("doc", AUTHORITY_DOC_BUDGETS, ids=lambda doc: doc.rel_path)
def test_schema_profile_authority_docs_keep_expected_include_boundaries(doc: AuthorityDocBudget) -> None:
    expanded_text = expanded_prompt_text(doc.path, src_root=SOURCE_ROOT, path_prefix=PATH_PREFIX)
    include_markers = set(expanded_include_markers(expanded_text))

    assert set(doc.required_include_markers) <= include_markers
    assert include_markers <= set(doc.allowed_include_markers)
