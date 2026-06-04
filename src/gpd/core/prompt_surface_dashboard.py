"""Report-only prompt-surface dashboard renderer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, TypeVar, cast

from gpd.core.prompt_markdown_scan import top_limit as _top_limit
from gpd.core.stage_prompt_diagnostics import (
    repeated_prior_stage_residue_rows as _repeated_prior_stage_residue_rows,
)
from gpd.core.stage_prompt_diagnostics import (
    stage_init_field_top_rows as _stage_init_field_top_rows,
)
from gpd.core.stage_prompt_diagnostics import (
    stage_top_prompt_rows as _stage_top_prompt_rows,
)

if TYPE_CHECKING:
    from gpd.core.prompt_diagnostics import PromptSurfaceReport


_T = TypeVar("_T")
_PROMPT_TOTAL_FIELDS = (
    "item_count",
    "expanded_line_count",
    "expanded_char_count",
    "raw_line_count",
    "raw_char_count",
    "raw_include_count",
    "expanded_include_count",
    "unresolved_include_count",
    "hard_gate_line_count",
    "shell_parsing_line_count",
    "visible_schema_example_count",
    "rigidity_index",
)
_PROMPT_KINDS = ("all", "command", "agent", "workflow")
_FALLBACK_VALIDATION_TIMING_LINES = (
    "dashboard target: < 10s locally",
    "local full-suite command: uv run pytest tests/ -q",
    "local xdist default: pyproject pytest options select local parallelism for full-suite runs",
    "focused diagnostics command: uv run pytest tests/core/test_prompt_surface_diagnostics.py "
    "tests/core/test_prompt_surface_diagnostics_cli.py tests/core/test_prompt_surface_diagnostics_budget.py "
    "tests/core/test_prompt_exactness_budget.py tests/core/test_staged_init_assembly_budget.py -q",
    "CI pytest shard budget: 180s",
    "CI pytest job timeout: 10 minutes",
    "CI shard target resolution timeout: 3 minutes",
)


def render_prompt_surface_dashboard(report: PromptSurfaceReport, top: int | None = None) -> str:
    """Render a deterministic human dashboard over an existing prompt report."""

    lines = [
        "# Prompt Surface Dashboard",
        "",
        f"- Schema version: `{report.schema_version}`",
        f"- Repo root: `{report.repo_root}`",
        f"- Top rows: {_top_label(top)}",
    ]
    lines.extend(_prompt_totals_section(report))
    lines.extend(_review_contract_frontload_section(report, top))
    lines.extend(_safety_floors_section(report))
    lines.extend(_stage_loading_totals_section(report))
    lines.extend(_stage_mechanics_prose_section(report, top))
    lines.extend(_top_stage_eager_loads_section(report, top))
    lines.extend(_prior_stage_residue_section(report, top))
    lines.extend(_repeated_prior_stage_residue_section(report, top))
    lines.extend(_staged_init_pressure_section(report, top))
    lines.extend(_manifest_must_not_duplicate_section(report, top))
    lines.extend(_exactness_section(report, top))
    lines.extend(_semantic_duplicate_counts_section(report, top))
    lines.extend(_runtime_projection_section(report))
    lines.extend(_validation_timing_section(report))
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {_cell(warning)}" for warning in report.warnings)
    return "\n".join(lines) + "\n"


def _prompt_totals_section(report: PromptSurfaceReport) -> list[str]:
    totals = report.totals
    by_kind = _mapping(totals.get("by_kind"))
    rows: list[Sequence[object]] = []
    for kind in _PROMPT_KINDS:
        source = totals if kind == "all" else _mapping(by_kind.get(kind))
        rows.append((kind, *(_int(source, field) for field in _PROMPT_TOTAL_FIELDS)))
    return _table(
        "Prompt totals by kind (Prompt Totals)",
        (
            "Kind (kind)",
            "Items (item_count)",
            "Expanded lines (expanded_line_count)",
            "Expanded chars (expanded_char_count)",
            "Raw lines (raw_line_count)",
            "Raw chars (raw_char_count)",
            "Raw includes (raw_include_count)",
            "Expanded includes (expanded_include_count)",
            "Unresolved includes (unresolved_include_count)",
            "Hard gates (hard_gate_line_count)",
            "Shell parse lines (shell_parsing_line_count)",
            "Visible schemas (visible_schema_example_count)",
            "Rigidity (rigidity_index)",
        ),
        rows,
    )


def _review_contract_frontload_section(report: PromptSurfaceReport, top: int | None) -> list[str]:
    totals = report.totals
    by_kind = _mapping(totals.get("by_kind"))
    total_rows: list[Sequence[object]] = []
    for kind in _PROMPT_KINDS:
        source = totals if kind == "all" else _mapping(by_kind.get(kind))
        total_rows.append(
            (
                kind,
                _int(source, "review_contract_frontload_section_count"),
                _int(source, "review_contract_frontload_line_count"),
                _int(source, "review_contract_frontload_char_count"),
            )
        )
    lines = _table(
        "Review-contract frontload (Review Contract Frontload)",
        (
            "Kind",
            "Sections (review_contract_frontload_section_count)",
            "Lines (review_contract_frontload_line_count)",
            "Chars (review_contract_frontload_char_count)",
        ),
        total_rows,
    )
    item_rows = [
        (
            item.kind,
            item.name,
            getattr(item, "review_contract_frontload_section_count", 0),
            getattr(item, "review_contract_frontload_line_count", 0),
            getattr(item, "review_contract_frontload_char_count", 0),
            item.path,
        )
        for item in _top_review_contract_frontload_items(report, top)
    ]
    if item_rows:
        lines.extend(
            _table(
                "Top review-contract frontload commands (Top Review Contract Frontload Commands)",
                ("Kind", "Name", "Sections", "Lines", "Chars", "Path"),
                item_rows,
            )
        )
    return lines


def _top_review_contract_frontload_items(report: PromptSurfaceReport, top: int | None):
    rows = [
        item
        for item in report.items
        if (
            getattr(item, "review_contract_frontload_section_count", 0)
            or getattr(item, "review_contract_frontload_line_count", 0)
            or getattr(item, "review_contract_frontload_char_count", 0)
        )
    ]
    sorted_rows = sorted(
        rows,
        key=lambda item: (
            -getattr(item, "review_contract_frontload_char_count", 0),
            -getattr(item, "review_contract_frontload_line_count", 0),
            item.kind,
            item.name,
        ),
    )
    return _limit_rows(sorted_rows, top)


def _safety_floors_section(report: PromptSurfaceReport) -> list[str]:
    totals = report.totals
    stage_totals = _mapping(totals.get("stage_diagnostics"))
    rows = (
        ("unresolved_includes", _int(totals, "unresolved_include_count")),
        ("invalid_gpd_return_examples", len(report.invalid_gpd_return_examples)),
        ("invalid_frontmatter_examples", len(report.invalid_frontmatter_examples)),
        ("disallowed_return_field_mentions", len(report.disallowed_return_field_mentions)),
        (
            "forbidden_child_return_synthesis_mentions",
            len(report.forbidden_child_return_synthesis_mentions),
        ),
        (
            "actionable_eager_load_violations",
            _int(stage_totals, "must_not_eager_load_actionable_violation_count"),
        ),
        (
            "prior_stage_residue_records",
            _int(stage_totals, "must_not_eager_load_prior_stage_residue_count", "prior_stage_residue_count"),
        ),
        (
            "manifest_must_not_duplicate_entries",
            _int(stage_totals, "manifest_must_not_duplicate_entry_count")
            or _int(totals, "manifest_must_not_duplicate_entry_count"),
        ),
        (
            "manifest_must_not_duplicate_stages",
            _int(stage_totals, "manifest_must_not_duplicate_stage_count")
            or _int(totals, "manifest_must_not_duplicate_stage_count"),
        ),
    )
    return _table("Safety floors (Safety Floors)", ("Floor", "Value"), rows)


def _stage_loading_totals_section(report: PromptSurfaceReport) -> list[str]:
    stage_totals = _mapping(report.totals.get("stage_diagnostics"))
    rows = (
        ("workflow_count", _int(stage_totals, "workflow_count")),
        ("stage_count", _int(stage_totals, "stage_count")),
        ("first_turn_line_count", _int(stage_totals, "first_turn_line_count")),
        ("first_turn_char_count", _int(stage_totals, "first_turn_char_count")),
        ("first_turn_active_line_count", _int(stage_totals, "first_turn_active_line_count")),
        ("first_turn_active_char_count", _int(stage_totals, "first_turn_active_char_count")),
        ("prior_stage_residue_line_count", _int(stage_totals, "prior_stage_residue_line_count")),
        ("prior_stage_residue_char_count", _int(stage_totals, "prior_stage_residue_char_count")),
        ("stage_eager_line_count", _int(stage_totals, "stage_eager_line_count", "eager_line_count")),
        ("stage_eager_char_count", _int(stage_totals, "stage_eager_char_count", "eager_char_count")),
        ("conditional_line_count", _int(stage_totals, "conditional_line_count")),
        ("conditional_char_count", _int(stage_totals, "conditional_char_count")),
        ("lazy_line_count", _int(stage_totals, "lazy_line_count")),
        ("lazy_char_count", _int(stage_totals, "lazy_char_count")),
        ("selected_init_field_count", _int(stage_totals, "selected_init_field_count", "required_init_field_count")),
        ("selected_init_content_field_count", _int(stage_totals, "selected_init_content_field_count")),
        ("high_pressure_init_field_count", _int(stage_totals, "high_pressure_init_field_count")),
        ("likely_bulky_init_field_count", _int(stage_totals, "likely_bulky_init_field_count")),
        ("must_not_eager_load_violation_count", _int(stage_totals, "must_not_eager_load_violation_count")),
        ("prior_stage_residue_count", _int(stage_totals, "prior_stage_residue_count")),
        ("stage_mechanics_prose_count", _int(report.totals, "stage_mechanics_prose_count")),
        (
            "manifest_must_not_duplicate_entry_count",
            _int(stage_totals, "manifest_must_not_duplicate_entry_count")
            or _int(report.totals, "manifest_must_not_duplicate_entry_count"),
        ),
        (
            "manifest_must_not_duplicate_stage_count",
            _int(stage_totals, "manifest_must_not_duplicate_stage_count")
            or _int(report.totals, "manifest_must_not_duplicate_stage_count"),
        ),
    )
    return _table("Stage loading totals (Stage Loading Totals)", ("Metric", "Value"), rows)


def _stage_mechanics_prose_section(report: PromptSurfaceReport, top: int | None) -> list[str]:
    rows = [
        (
            _object_text(mention, "path"),
            _object_int(mention, "line"),
            ", ".join(str(category) for category in _object_sequence(_object_get(mention, "categories", ()))),
            _object_text(mention, "severity"),
            _object_text(mention, "snippet"),
        )
        for mention in _limit_rows(_object_sequence(getattr(report, "stage_mechanics_prose_mentions", ())), top)
    ]
    if not rows:
        return []
    return _table(
        "Top stage mechanics prose (Top Stage Mechanics Prose)",
        ("Path", "Line", "Categories", "Severity", "Snippet"),
        rows,
    )


def _top_stage_eager_loads_section(report: PromptSurfaceReport, top: int | None) -> list[str]:
    rows = [
        (
            _text(row, "workflow_id"),
            _text(row, "stage_id"),
            _int(row, "eager_char_count", "stage_eager_char_count"),
            _int(row, "eager_line_count", "stage_eager_line_count"),
            _int(row, "first_turn_char_count"),
            _int(row, "first_turn_active_char_count"),
            _int(row, "prior_stage_residue_char_count"),
            _int(row, "prior_stage_residue_line_count"),
            _int(row, "conditional_char_count"),
            _int(row, "lazy_char_count"),
            _int(row, "actionable_violation_count", "violation_count"),
            _int(row, "prior_stage_residue_count"),
            _int(row, "required_init_field_count"),
            _int(row, "likely_bulky_init_field_count"),
        )
        for row in _stage_top_prompt_rows(report.stage_diagnostics, top)
    ]
    if not rows:
        return _empty_section(
            "Top stage eager loads (Top Stage Eager Loads)",
            "Stage diagnostics not collected or no staged workflows found.",
        )
    return _table(
        "Top stage eager loads (Top Stage Eager Loads)",
        (
            "Workflow",
            "Stage",
            "Eager chars",
            "Eager lines",
            "First-turn chars",
            "Active first-turn chars",
            "Residue chars",
            "Residue lines",
            "Conditional chars",
            "Lazy chars",
            "Actionable violations",
            "Residue records",
            "Required fields",
            "Likely bulky fields",
        ),
        rows,
    )


def _prior_stage_residue_section(report: PromptSurfaceReport, top: int | None) -> list[str]:
    rows = _prior_stage_residue_rows(report, top)
    if not rows:
        if not report.stage_diagnostics:
            message = "Stage diagnostics not collected; prior-stage residue contributors not collected."
        else:
            message = "No prior-stage residue contributors found."
        return _empty_section("Top prior-stage residue contributors (Top Prior-Stage Residue Contributors)", message)
    return _table(
        "Top prior-stage residue contributors (Top Prior-Stage Residue Contributors)",
        (
            "Workflow",
            "Stage",
            "Authority",
            "Classification",
            "Expanded chars",
            "Expanded lines",
            "First-turn chains",
            "Eager via",
            "Transitive includes",
        ),
        rows,
    )


def _prior_stage_residue_rows(
    report: PromptSurfaceReport,
    top: int | None,
) -> tuple[Sequence[object], ...]:
    rows: list[Sequence[object]] = []
    for workflow in report.stage_diagnostics:
        for stage in workflow.stages:
            residue_violations = {
                violation.authority: violation
                for violation in stage.must_not_eager_load_violations
                if violation.classification == "prior_stage_residue"
            }
            for metric in stage.authority_usage_metrics:
                if metric.first_turn_role != "prior_stage_residue":
                    continue
                violation = residue_violations.get(metric.authority)
                rows.append(
                    (
                        workflow.workflow_id,
                        stage.stage_id,
                        metric.authority,
                        "prior_stage_residue",
                        metric.expanded_char_count,
                        metric.expanded_line_count,
                        len(metric.first_turn_chains),
                        ", ".join(violation.eager_via) if violation else "",
                        len(metric.transitive_include_authorities),
                    )
                )
    sorted_rows = sorted(
        rows,
        key=lambda row: (-cast(int, row[4]), str(row[0]), str(row[1]), str(row[2])),
    )
    return tuple(_limit_rows(sorted_rows, top))


def _repeated_prior_stage_residue_section(report: PromptSurfaceReport, top: int | None) -> list[str]:
    rows = [
        (
            _text(row, "authority"),
            _int(row, "occurrence_count"),
            _int(row, "workflow_count"),
            _int(row, "stage_count"),
            _int(row, "expanded_char_count"),
            _int(row, "expanded_line_count"),
            _int(row, "first_turn_chain_count"),
            _int(row, "transitive_include_count"),
            _sequence_text(row, "workflows"),
            _sequence_text(row, "stages"),
            _sequence_text(row, "eager_via"),
        )
        for row in _repeated_prior_stage_residue_rows(report.stage_diagnostics, top)
    ]
    if not rows:
        if not report.stage_diagnostics:
            message = "Stage diagnostics not collected; repeated prior-stage residue not collected."
        else:
            message = "No prior-stage residue authorities found."
        return _empty_section("Repeated prior-stage residue (Repeated Prior-Stage Residue)", message)
    return _table(
        "Repeated prior-stage residue (Repeated Prior-Stage Residue)",
        (
            "Authority",
            "Occurrences",
            "Workflow count",
            "Stage count",
            "Expanded chars",
            "Expanded lines",
            "First-turn chains",
            "Transitive includes",
            "Workflows",
            "Stages",
            "Eager via",
        ),
        rows,
    )


def _staged_init_pressure_section(report: PromptSurfaceReport, top: int | None) -> list[str]:
    lines: list[str] = []
    stage_rows = _staged_init_pressure_stage_rows(report, top)
    if stage_rows:
        lines.extend(
            _table(
                "Staged-init pressure by stage (Staged-Init Pressure By Stage)",
                (
                    "Workflow",
                    "Stage",
                    "Required fields",
                    "Content fields",
                    "High-pressure fields",
                    "Likely bulky fields",
                    "Likely bulky names",
                ),
                stage_rows,
            )
        )
    else:
        lines.extend(
            _empty_section(
                "Staged-init pressure by stage (Staged-Init Pressure By Stage)",
                "No staged-init field pressure collected.",
            )
        )

    field_rows = [
        (
            _text(row, "workflow_id"),
            _text(row, "stage_id"),
            _text(row, "field_name"),
            _text(row, "field_kind_guess"),
            _text(row, "field_pressure_class"),
            _int(row, "selection_count"),
            _int(row, "required_init_field_count"),
            _int(row, "likely_bulky_field_count"),
            _int(row, "field_payload_pressure_score"),
        )
        for row in _stage_init_field_top_rows(report.stage_diagnostics, top)
    ]
    if field_rows:
        lines.extend(
            _table(
                "Top staged-init fields (Top Staged-Init Fields)",
                (
                    "Workflow",
                    "Stage",
                    "field_name",
                    "field_kind_guess",
                    "field_pressure_class",
                    "Selections",
                    "Required fields",
                    "Likely bulky fields",
                    "Pressure score",
                ),
                field_rows,
            )
        )
    else:
        lines.extend(
            _empty_section("Top staged-init fields (Top Staged-Init Fields)", "No staged-init field rows collected.")
        )
    return lines


def _staged_init_pressure_stage_rows(
    report: PromptSurfaceReport,
    top: int | None,
) -> tuple[Sequence[object], ...]:
    rows: list[Sequence[object]] = []
    for workflow in report.stage_diagnostics:
        for stage in workflow.stages:
            if stage.required_init_field_count <= 0:
                continue
            likely_names = sorted(
                metric.field_name for metric in stage.required_init_field_metrics if metric.likely_bulky
            )
            rows.append(
                (
                    workflow.workflow_id,
                    stage.stage_id,
                    stage.required_init_field_count,
                    sum(1 for metric in stage.required_init_field_metrics if metric.field_kind_guess == "content"),
                    stage.high_pressure_init_field_count,
                    stage.likely_bulky_init_field_count,
                    _compact_names(likely_names),
                )
            )
    sorted_rows = sorted(
        rows,
        key=lambda row: (-cast(int, row[5]), -cast(int, row[2]), str(row[0]), str(row[1])),
    )
    return tuple(_limit_rows(sorted_rows, top))


def _manifest_must_not_duplicate_section(report: PromptSurfaceReport, top: int | None) -> list[str]:
    rows = []
    for diagnostic in _limit_rows(_object_sequence(getattr(report, "manifest_must_not_duplicate_entries", ())), top):
        duplicate_values = ", ".join(
            _object_text(entry, "value") for entry in _object_sequence(_object_get(diagnostic, "duplicate_entries", ()))
        )
        rows.append(
            (
                _object_text(diagnostic, "workflow_id"),
                _object_text(diagnostic, "stage_id"),
                _object_int(diagnostic, "raw_entry_count"),
                _object_int(diagnostic, "effective_unique_entry_count"),
                _object_int(diagnostic, "duplicate_entry_count"),
                duplicate_values,
                _object_text(diagnostic, "manifest_path"),
            )
        )
    if not rows:
        return []
    return _table(
        "Manifest must_not_eager_load duplicates (Manifest Must Not Eager Load Duplicates)",
        ("Workflow", "Stage", "Raw entries", "Unique entries", "Duplicate entries", "Values", "Manifest"),
        rows,
    )


def _exactness_section(report: PromptSurfaceReport, top: int | None) -> list[str]:
    diagnostics = _mapping(report.exact_assertion_diagnostics)
    totals = _mapping(diagnostics.get("totals"))
    files = tuple(cast(Sequence[Mapping[str, object]], diagnostics.get("files", ())))
    files_scanned = _int(totals, "files_scanned")
    if files_scanned <= 0 and not files:
        return _empty_section(
            "Exactness totals (Exactness Totals)",
            "Exactness diagnostics not collected; rerun with --include-tests to populate prompt-test exactness totals.",
        )

    high_severity_file_count = sum(1 for row in files if row.get("severity") == "high")
    lines = _table(
        "Exactness totals (Exactness Totals)",
        ("Metric", "Value"),
        (
            ("files_scanned", files_scanned),
            ("exact_assertion_file_count", _int(totals, "exact_assertion_file_count")),
            ("exact_assertion_count", _int(totals, "exact_assertion_count")),
            ("machine_contract_exact_assertions", _int(totals, "machine_contract_exact_assertions")),
            ("public_ux_exact_assertions", _int(totals, "public_ux_exact_assertions")),
            ("brittle_prose_assertions", _int(totals, "brittle_prose_assertions")),
            ("brittle_prose_file_count", _int(totals, "brittle_prose_file_count")),
            ("high_severity_file_count", high_severity_file_count),
        ),
    )
    file_rows = [
        (
            str(row.get("path", "")),
            _int(row, "exact_assertion_count"),
            _int(row, "machine_contract_exact_assertions"),
            _int(row, "public_ux_exact_assertions"),
            _int(row, "brittle_prose_assertions"),
            f"{100 * _float(row, 'brittle_prose_density'):.1f}",
            str(row.get("severity", "info")),
        )
        for row in _limit_rows(files, top)
    ]
    if file_rows:
        lines.extend(
            _table(
                "Top exact/brittle files (Top Exact/Brittle Files)",
                ("File", "Exact", "Machine", "Public UX", "Brittle prose", "Brittle %", "Severity"),
                file_rows,
            )
        )
    else:
        lines.extend(
            _empty_section("Top exact/brittle files (Top Exact/Brittle Files)", "No exact assertion files found.")
        )
    lines.extend(_exactness_migration_section(diagnostics, top))
    return lines


def _exactness_migration_section(diagnostics: Mapping[str, object], top: int | None) -> list[str]:
    migration = _mapping(diagnostics.get("migration")) or _mapping(diagnostics.get("exactness_migration"))
    if not migration:
        return []

    rows = _exactness_migration_rows(migration, top)
    migration_totals = _mapping(migration.get("totals"))
    if not migration_totals and rows:
        migration_totals = {
            "machine_exact_assertions": sum(
                _int(row, "machine_exact_assertions", "machine_exact_keep_count", "machine_contract_exact_assertions")
                for row in rows
            ),
            "public_exact_assertions": sum(
                _int(row, "public_exact_assertions", "public_exact_keep_count", "public_ux_exact_assertions")
                for row in rows
            ),
            "semantic_concept_candidate_assertions": sum(
                _int(row, "semantic_concept_candidate_assertions", "semantic_concept_candidate_count") for row in rows
            ),
            "raw_brittle_prose_assertions": sum(
                _int(row, "raw_brittle_prose_assertions", "raw_brittle_prose_count", "brittle_prose_assertions")
                for row in rows
            ),
        }

    lines: list[str] = []
    if migration_totals:
        lines.extend(
            _table(
                "Exactness migration totals (Exactness Migration Totals)",
                ("Metric", "Value"),
                (
                    (
                        "machine_exact_assertions",
                        _int(
                            migration_totals,
                            "machine_exact_assertions",
                            "machine_exact_keep_count",
                            "machine_contract_exact_assertions",
                        ),
                    ),
                    (
                        "public_exact_assertions",
                        _int(
                            migration_totals,
                            "public_exact_assertions",
                            "public_exact_keep_count",
                            "public_ux_exact_assertions",
                        ),
                    ),
                    (
                        "semantic_concept_candidate_assertions",
                        _int(
                            migration_totals,
                            "semantic_concept_candidate_assertions",
                            "semantic_concept_candidate_count",
                        ),
                    ),
                    (
                        "raw_brittle_prose_assertions",
                        _int(
                            migration_totals,
                            "raw_brittle_prose_assertions",
                            "raw_brittle_prose_count",
                            "brittle_prose_assertions",
                        ),
                    ),
                    ("taxonomy_helper_file_count", _int(migration_totals, "taxonomy_helper_file_count")),
                    (
                        "taxonomy_helper_brittle_file_count",
                        _int(migration_totals, "taxonomy_helper_brittle_file_count"),
                    ),
                    (
                        "taxonomy_helper_brittle_assertions",
                        _int(migration_totals, "taxonomy_helper_brittle_assertions"),
                    ),
                ),
            )
        )
    if rows:
        lines.extend(
            _table(
                "Exactness migration rows (Exactness Migration Rows)",
                (
                    "File",
                    "Machine exact",
                    "Public exact",
                    "Semantic candidate",
                    "Raw brittle",
                    "Helper calls",
                    "Semantic helpers",
                    "Baseline",
                    "Delta",
                    "Gate",
                ),
                tuple(
                    (
                        _text(row, "path"),
                        _int(
                            row,
                            "machine_exact_assertions",
                            "machine_exact_keep_count",
                            "machine_contract_exact_assertions",
                        ),
                        _int(row, "public_exact_assertions", "public_exact_keep_count", "public_ux_exact_assertions"),
                        _int(row, "semantic_concept_candidate_assertions", "semantic_concept_candidate_count"),
                        _int(
                            row, "raw_brittle_prose_assertions", "raw_brittle_prose_count", "brittle_prose_assertions"
                        ),
                        _int(row, "taxonomy_helper_call_count"),
                        _int(row, "semantic_helper_call_count"),
                        _maybe_text(row, "taxonomy_helper_brittle_baseline"),
                        _maybe_text(row, "taxonomy_helper_brittle_delta"),
                        _text(row, "taxonomy_helper_brittle_gate", "gate"),
                    )
                    for row in rows
                ),
            )
        )
    return lines


def _semantic_duplicate_counts_section(report: PromptSurfaceReport, top: int | None) -> list[str]:
    groups = _limit_rows(report.semantic_duplicate_invariants, top)
    if not groups:
        return _empty_section(
            "Semantic duplicate non-reference counts (Semantic Duplicate Non-Reference Counts)",
            "No semantic duplicate invariants found.",
        )
    return _table(
        "Semantic duplicate non-reference counts (Semantic Duplicate Non-Reference Counts)",
        (
            "Category",
            "Non-ref occurrences",
            "Non-ref files (non_reference_file_count)",
            "Total occurrences",
            "Total files",
            "Severity",
            "Suggested action",
        ),
        tuple(
            (
                group.category,
                group.non_reference_occurrence_count,
                group.non_reference_file_count,
                group.occurrence_count,
                group.file_count,
                group.severity,
                group.suggested_action,
            )
            for group in groups
        ),
    )


def _runtime_projection_section(report: PromptSurfaceReport) -> list[str]:
    runtime_totals = _mapping(report.totals.get("runtime_projection"))
    if not runtime_totals:
        return _empty_section(
            "Runtime projection totals (Runtime Projection Totals)",
            "Runtime projections not collected; rerun without --no-runtime-projections and use --runtime or --runtime all.",
        )
    rows = []
    for runtime, raw_metric in sorted(runtime_totals.items()):
        metric = _mapping(raw_metric)
        rows.append(
            (
                runtime,
                str(bool(metric.get("native_include_support", False))).lower(),
                _int(metric, "item_count"),
                _int(metric, "char_count"),
                _int(metric, "line_count"),
                _int(metric, "expanded_char_count"),
                _int(metric, "expanded_line_count"),
                _int(metric, "char_delta"),
                _int(metric, "line_delta"),
                _int(metric, "include_count"),
                _int(metric, "runtime_note_count"),
                _int(metric, "shell_rewrite_count"),
                _int(metric, "bridge_command_occurrences"),
            )
        )
    return _table(
        "Runtime projection totals (Runtime Projection Totals)",
        (
            "Runtime",
            "Native includes",
            "Items",
            "Projected chars",
            "Projected lines",
            "Expanded chars",
            "Expanded lines",
            "Char delta",
            "Line delta",
            "Includes",
            "Runtime notes",
            "Shell rewrites",
            "Bridge calls",
        ),
        rows,
    )


def _validation_timing_section(report: PromptSurfaceReport) -> list[str]:
    lines = ["", "## Validation timing references (Validation Timing References)", ""]
    lines.extend(f"- {line}" for line in _FALLBACK_VALIDATION_TIMING_LINES)
    return lines


def _table(title: str, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    lines = ["", f"## {title}", ""]
    if not rows:
        lines.append("No rows.")
        return lines
    lines.append("| " + " | ".join(_cell(header) for header in headers) + " |")
    lines.append("| " + " | ".join(_alignment(header) for header in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return lines


def _empty_section(title: str, message: str) -> list[str]:
    return ["", f"## {title}", "", message]


def _alignment(header: str) -> str:
    return "---:" if _numeric_header(header) else "---"


def _numeric_header(header: str) -> bool:
    lowered = header.casefold()
    numeric_terms = (
        "count",
        "items",
        "lines",
        "chars",
        "includes",
        "gates",
        "fields",
        "violations",
        "records",
        "chains",
        "delta",
        "notes",
        "rewrites",
        "calls",
        "score",
        "exact",
        "machine",
        "public",
        "brittle",
        "%",
        "value",
        "rigidity",
        "schemas",
        "selections",
        "occurrences",
    )
    return any(term in lowered for term in numeric_terms)


def _cell(value: object) -> str:
    text = str(value)
    text = text.replace("\n", " ").replace("|", "\\|")
    return text


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _int(row: Mapping[str, object], *keys: str) -> int:
    for key in keys:
        value = row.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
    return 0


def _float(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _text(row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return str(value)
    return ""


def _maybe_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if value is None:
        return ""
    return str(value)


def _sequence_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return "" if value is None else str(value)
    return ", ".join(str(item) for item in value)


def _object_get(value: object, key: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _object_int(value: object, *keys: str) -> int:
    for key in keys:
        raw = _object_get(value, key)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
    return 0


def _object_text(value: object, *keys: str) -> str:
    for key in keys:
        raw = _object_get(value, key)
        if raw is not None:
            return str(raw)
    return ""


def _object_sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _exactness_migration_rows(
    migration: Mapping[str, object],
    top: int | None,
) -> tuple[Mapping[str, object], ...]:
    rows = _object_sequence(migration.get("files")) or _object_sequence(migration.get("rows"))
    normalized_rows = tuple(dict(row) for row in rows if isinstance(row, Mapping))
    return tuple(_limit_rows(normalized_rows, top))


def _limit_rows(rows: Sequence[_T], top: int | None) -> Sequence[_T]:
    limit = _top_limit(top)
    if limit is None:
        return rows
    return rows[:limit]


def _compact_names(names: Sequence[str], *, limit: int = 5) -> str:
    if not names:
        return ""
    visible = list(names[:limit])
    remainder = len(names) - len(visible)
    if remainder > 0:
        visible.append(f"+{remainder} more")
    return ", ".join(visible)


def _top_label(top: int | None) -> str:
    limit = _top_limit(top)
    return "all" if limit is None else str(limit)


__all__ = ["render_prompt_surface_dashboard"]
