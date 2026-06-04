"""Stage-aware prompt diagnostics for staged workflow manifests."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal, Protocol, cast

from gpd.adapters.install_utils import (
    expand_at_includes,
    parse_at_include_path,
)
from gpd.core import prompt_markdown_scan as _prompt_markdown_scan
from gpd.core.workflow_staging import (
    WorkflowStage,
    WorkflowStageManifest,
    known_init_fields_for_workflow,
    load_workflow_stage_manifest_from_path,
)

if TYPE_CHECKING:
    pass

_body_without_frontmatter = _prompt_markdown_scan.body_without_frontmatter
_count_raw_includes = _prompt_markdown_scan.count_raw_includes
_iter_unfenced_lines = _prompt_markdown_scan.iter_unfenced_lines
_line_count = _prompt_markdown_scan.line_count
_relative_path = _prompt_markdown_scan.relative_path
_top_limit = _prompt_markdown_scan.top_limit

StageAuthorityRole = Literal["stage_eager", "conditional", "lazy"]
FirstTurnAuthorityRole = Literal["active", "prior_stage_residue", "unexpected", "not_first_turn"]
MustNotEagerLoadViolationClassification = Literal["eager_load_violation", "prior_stage_residue"]
MustNotEagerLoadViolationSource = Literal[
    "manifest_overlap", "first_turn_direct_include", "first_turn_transitive_include", "stage_eager_transitive_include"
]
StageInitFieldKind = Literal[
    "content", "context", "contract", "report", "schema_bridge", "artifacts", "file_list", "status_payload", "scalar"
]
StageInitFieldPressureClass = Literal["likely_bulky", "ordinary"]


class StagePromptSource(Protocol): ...


class RuntimeProjectionLike(Protocol): ...


class StageCommandMetric(Protocol): ...


@dataclass(frozen=True, slots=True)
class AuthorityPromptMetric:
    authority: str
    path: str
    raw_line_count: int
    raw_char_count: int
    raw_include_count: int
    expanded_line_count: int
    expanded_char_count: int
    transitive_include_authorities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StageAuthorityUsageMetric:
    workflow_id: str
    stage_id: str
    order: int
    authority: str
    path: str
    roles: tuple[StageAuthorityRole, ...]
    conditional_when: tuple[str, ...]
    first_turn_role: FirstTurnAuthorityRole
    first_turn_chains: tuple[tuple[str, ...], ...]
    raw_line_count: int
    raw_char_count: int
    raw_include_count: int
    expanded_line_count: int
    expanded_char_count: int
    transitive_include_authorities: tuple[str, ...]
    violation_count: int


@dataclass(frozen=True, slots=True)
class StageInitFieldUsageMetric:
    field_name: str
    field_kind_guess: StageInitFieldKind
    field_pressure_class: StageInitFieldPressureClass
    likely_bulky: bool


@dataclass(frozen=True, slots=True)
class MustNotEagerLoadViolation:
    workflow_id: str
    stage_id: str
    authority: str
    violation_source: MustNotEagerLoadViolationSource
    eager_via: tuple[str, ...]
    classification: MustNotEagerLoadViolationClassification = "eager_load_violation"


@dataclass(frozen=True, slots=True)
class WorkflowStagePromptMetric:
    workflow_id: str
    stage_id: str
    order: int
    eager_authorities: tuple[str, ...]
    eager_authority_metrics: tuple[AuthorityPromptMetric, ...]
    eager_line_count: int
    eager_char_count: int
    lazy_authorities: tuple[str, ...]
    lazy_authority_metrics: tuple[AuthorityPromptMetric, ...]
    lazy_line_count: int
    lazy_char_count: int
    must_not_eager_load_violations: tuple[MustNotEagerLoadViolation, ...]
    conditional_authorities: tuple[str, ...] = ()
    conditional_authority_groups: tuple[tuple[str, tuple[str, ...]], ...] = ()
    conditional_authority_metrics: tuple[AuthorityPromptMetric, ...] = ()
    conditional_line_count: int = 0
    conditional_char_count: int = 0
    authority_usage_metrics: tuple[StageAuthorityUsageMetric, ...] = ()
    first_turn_active_line_count: int = 0
    first_turn_active_char_count: int = 0
    prior_stage_residue_line_count: int = 0
    prior_stage_residue_char_count: int = 0
    must_not_eager_load_actionable_violation_count: int = 0
    must_not_eager_load_prior_stage_residue_count: int = 0
    required_init_fields: tuple[str, ...] = ()
    required_init_field_metrics: tuple[StageInitFieldUsageMetric, ...] = ()
    required_init_field_count: int = 0
    high_pressure_init_field_count: int = 0
    likely_bulky_init_field_count: int = 0


@dataclass(frozen=True, slots=True)
class StageAwareWorkflowPromptMetric:
    workflow_id: str
    command_name: str
    command_path: str
    manifest_path: str
    stage_count: int
    first_turn_line_count: int
    first_turn_char_count: int
    first_turn_raw_include_count: int
    runtime_projection: tuple[RuntimeProjectionLike, ...]
    stages: tuple[WorkflowStagePromptMetric, ...]
    violation_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _IncludeTrace:
    authorities: tuple[str, ...]
    chains_by_authority: Mapping[str, tuple[tuple[str, ...], ...]]


def build_stage_diagnostics(
    sources: Sequence[StagePromptSource],
    items: Sequence[StageCommandMetric],
    *,
    report_warnings: list[str],
    path_prefix: str,
) -> tuple[StageAwareWorkflowPromptMetric, ...]:
    items_by_command = {(item.kind, item.name): item for item in items if item.kind == "command"}
    diagnostics: list[StageAwareWorkflowPromptMetric] = []
    for source in sources:
        if source.kind != "command":
            continue
        command_item = items_by_command.get((source.kind, source.name))
        if command_item is None:
            continue
        manifest_path = _stage_manifest_path_for_command(source)
        if not manifest_path.is_file():
            continue
        warning_count = len(report_warnings)
        metric = _build_stage_diagnostic_for_command(
            source,
            command_item,
            manifest_path,
            report_warnings=report_warnings,
            path_prefix=path_prefix,
        )
        if metric is None:
            if len(report_warnings) == warning_count:
                report_warnings.append(
                    f"could not load stage diagnostics for {source.name}: "
                    f"{_relative_path(manifest_path, source.repo_root)}"
                )
            continue
        diagnostics.append(metric)
    return tuple(sorted(diagnostics, key=lambda metric: (metric.workflow_id, metric.command_name)))


def top_stage_diagnostics(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[StageAwareWorkflowPromptMetric, ...]:
    limit = _top_limit(top)
    if limit is None:
        return tuple(stage_diagnostics)
    return tuple(
        sorted(
            stage_diagnostics,
            key=lambda metric: (
                -sum(stage.eager_char_count for stage in metric.stages),
                -sum(stage.lazy_char_count for stage in metric.stages),
                -metric.first_turn_char_count,
                -metric.violation_count,
                metric.workflow_id,
                metric.command_name,
            ),
        )[:limit]
    )


def stage_top_prompt_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for workflow in stage_diagnostics:
        for stage in workflow.stages:
            rows.append(
                {
                    "workflow_id": workflow.workflow_id,
                    "command_name": workflow.command_name,
                    "stage_id": stage.stage_id,
                    "first_turn_char_count": workflow.first_turn_char_count,
                    "first_turn_line_count": workflow.first_turn_line_count,
                    "first_turn_active_char_count": stage.first_turn_active_char_count,
                    "first_turn_active_line_count": stage.first_turn_active_line_count,
                    "prior_stage_residue_char_count": stage.prior_stage_residue_char_count,
                    "prior_stage_residue_line_count": stage.prior_stage_residue_line_count,
                    "eager_char_count": stage.eager_char_count,
                    "eager_line_count": stage.eager_line_count,
                    "stage_eager_char_count": stage.eager_char_count,
                    "stage_eager_line_count": stage.eager_line_count,
                    "conditional_char_count": stage.conditional_char_count,
                    "conditional_line_count": stage.conditional_line_count,
                    "lazy_char_count": stage.lazy_char_count,
                    "lazy_line_count": stage.lazy_line_count,
                    "violation_count": stage.must_not_eager_load_actionable_violation_count,
                    "actionable_violation_count": stage.must_not_eager_load_actionable_violation_count,
                    "prior_stage_residue_count": stage.must_not_eager_load_prior_stage_residue_count,
                    "required_init_field_count": stage.required_init_field_count,
                    "high_pressure_init_field_count": stage.high_pressure_init_field_count,
                    "likely_bulky_init_field_count": stage.likely_bulky_init_field_count,
                }
            )
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -cast(int, row["eager_char_count"]),
            -cast(int, row["lazy_char_count"]),
            -cast(int, row["violation_count"]),
            cast(str, row["workflow_id"]),
            cast(str, row["stage_id"]),
        ),
    )
    limit = _top_limit(top)
    return tuple(sorted_rows[:limit])


def stage_authority_top_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for workflow in stage_diagnostics:
        for stage in workflow.stages:
            for metric in stage.authority_usage_metrics:
                row = _stage_authority_usage_metric_to_dict(metric)
                row["workflow_id"] = workflow.workflow_id
                row["command_name"] = workflow.command_name
                row["stage_id"] = stage.stage_id
                rows.append(row)
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -cast(int, row["expanded_char_count"]),
            -cast(int, row["violation_count"]),
            cast(str, row["workflow_id"]),
            cast(str, row["stage_id"]),
            cast(str, row["authority"]),
        ),
    )
    limit = _top_limit(top)
    return tuple(sorted_rows[:limit])


def repeated_prior_stage_residue_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    totals_by_authority: dict[str, dict[str, int]] = {}
    workflows_by_authority: dict[str, set[str]] = defaultdict(set)
    stages_by_authority: dict[str, set[str]] = defaultdict(set)
    eager_via_by_authority: dict[str, set[str]] = defaultdict(set)

    for workflow in stage_diagnostics:
        for stage in workflow.stages:
            residue_violations = {
                violation.authority: violation
                for violation in stage.must_not_eager_load_violations
                if violation.classification == "prior_stage_residue"
            }
            for metric in stage.authority_usage_metrics:
                if metric.first_turn_role != "prior_stage_residue":
                    continue
                authority = metric.authority
                totals = totals_by_authority.setdefault(
                    authority,
                    {
                        "occurrence_count": 0,
                        "expanded_char_count": 0,
                        "expanded_line_count": 0,
                        "first_turn_chain_count": 0,
                        "transitive_include_count": 0,
                    },
                )
                totals["occurrence_count"] += 1
                totals["expanded_char_count"] += metric.expanded_char_count
                totals["expanded_line_count"] += metric.expanded_line_count
                totals["first_turn_chain_count"] += len(metric.first_turn_chains)
                totals["transitive_include_count"] += len(metric.transitive_include_authorities)
                workflows_by_authority[authority].add(workflow.workflow_id)
                stages_by_authority[authority].add(f"{workflow.workflow_id}.{stage.stage_id}")

                violation = residue_violations.get(authority)
                eager_via = violation.eager_via if violation is not None else _authority_usage_eager_via(metric)
                eager_via_by_authority[authority].update(eager_via)

    rows = [
        {
            "authority": authority,
            "occurrence_count": totals["occurrence_count"],
            "workflow_count": len(workflows_by_authority[authority]),
            "stage_count": len(stages_by_authority[authority]),
            "expanded_char_count": totals["expanded_char_count"],
            "expanded_line_count": totals["expanded_line_count"],
            "first_turn_chain_count": totals["first_turn_chain_count"],
            "transitive_include_count": totals["transitive_include_count"],
            "workflows": sorted(workflows_by_authority[authority]),
            "stages": sorted(stages_by_authority[authority]),
            "eager_via": sorted(eager_via_by_authority[authority]),
        }
        for authority, totals in totals_by_authority.items()
    ]
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -cast(int, row["occurrence_count"]),
            -cast(int, row["expanded_char_count"]),
            -cast(int, row["expanded_line_count"]),
            cast(str, row["authority"]),
        ),
    )
    limit = _top_limit(top)
    return tuple(sorted_rows[:limit])


def stage_init_field_top_rows(
    stage_diagnostics: Sequence[StageAwareWorkflowPromptMetric],
    top: int | None,
) -> tuple[dict[str, object], ...]:
    selection_counts: dict[str, int] = defaultdict(int)
    for workflow in stage_diagnostics:
        for stage in workflow.stages:
            for metric in stage.required_init_field_metrics:
                selection_counts[metric.field_name] += 1

    rows: list[dict[str, object]] = []
    for workflow in stage_diagnostics:
        for stage in workflow.stages:
            for metric in stage.required_init_field_metrics:
                rows.append(
                    {
                        "workflow_id": workflow.workflow_id,
                        "command_name": workflow.command_name,
                        "stage_id": stage.stage_id,
                        "order": stage.order,
                        "required_init_field_count": stage.required_init_field_count,
                        "high_pressure_init_field_count": stage.high_pressure_init_field_count,
                        "likely_bulky_field_count": stage.likely_bulky_init_field_count,
                        "field_payload_pressure_score": (
                            stage.required_init_field_count + 4 * stage.likely_bulky_init_field_count
                        ),
                        "field_name": metric.field_name,
                        "field_kind_guess": metric.field_kind_guess,
                        "field_pressure_class": metric.field_pressure_class,
                        "likely_bulky": metric.likely_bulky,
                        "selection_count": selection_counts[metric.field_name],
                    }
                )

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            _init_field_pressure_rank(cast(str, row["field_pressure_class"])),
            _init_field_kind_rank(cast(str, row["field_kind_guess"])),
            -cast(int, row["selection_count"]),
            cast(str, row["workflow_id"]),
            cast(str, row["stage_id"]),
            cast(str, row["field_name"]),
        ),
    )
    limit = _top_limit(top)
    return tuple(sorted_rows[:limit])


stage_authority_pressure_rows = stage_authority_top_rows
stage_init_field_pressure_rows = stage_init_field_top_rows


def stage_diagnostic_to_dict(metric: StageAwareWorkflowPromptMetric, top: int | None = None) -> dict[str, object]:
    return {
        "workflow_id": metric.workflow_id,
        "command_name": metric.command_name,
        "command_path": metric.command_path,
        "manifest_path": metric.manifest_path,
        "stage_count": metric.stage_count,
        "first_turn_line_count": metric.first_turn_line_count,
        "first_turn_char_count": metric.first_turn_char_count,
        "first_turn_raw_include_count": metric.first_turn_raw_include_count,
        "runtime_projection": [
            _runtime_projection_metric_to_dict(runtime_metric) for runtime_metric in metric.runtime_projection
        ],
        "stages": [_workflow_stage_metric_to_dict(stage, top=top) for stage in metric.stages],
        "violation_count": metric.violation_count,
        "prior_stage_residue_count": sum(
            stage.must_not_eager_load_prior_stage_residue_count for stage in metric.stages
        ),
        "must_not_eager_load_record_count": sum(len(stage.must_not_eager_load_violations) for stage in metric.stages),
        "warnings": list(metric.warnings),
    }


def _stage_manifest_path_for_command(source: StagePromptSource) -> Path:
    return source.src_root / "specs" / "workflows" / f"{source.name}-stage-manifest.json"


def _build_stage_diagnostic_for_command(
    source: StagePromptSource,
    command_item: StageCommandMetric,
    manifest_path: Path,
    *,
    report_warnings: list[str],
    path_prefix: str,
) -> StageAwareWorkflowPromptMetric | None:
    warnings: list[str] = []
    manifest = _load_stage_manifest_for_source(source, manifest_path, warnings)
    if manifest is None:
        report_warnings.extend(f"could not load stage diagnostics for {source.name}: {warning}" for warning in warnings)
        return None

    command_text = source.absolute_path.read_text(encoding="utf-8")
    first_turn_trace = _include_trace_from_text(
        command_text,
        source.src_root,
        active_authorities=frozenset(),
    )
    measured_stages: list[WorkflowStagePromptMetric] = []
    prior_stage_authorities: set[str] = set()
    for stage in sorted(manifest.stages, key=lambda candidate: candidate.order):
        measured_stages.append(
            _measure_workflow_stage(
                source=source,
                manifest=manifest,
                stage=stage,
                first_turn_trace=first_turn_trace,
                prior_stage_authorities=frozenset(prior_stage_authorities),
                path_prefix=path_prefix,
            )
        )
        prior_stage_authorities.update(stage.eager_authorities())
    stages = tuple(measured_stages)
    violation_count = sum(stage.must_not_eager_load_actionable_violation_count for stage in stages)
    return StageAwareWorkflowPromptMetric(
        workflow_id=manifest.workflow_id,
        command_name=source.name,
        command_path=source.path,
        manifest_path=_relative_path(manifest_path, source.repo_root),
        stage_count=len(stages),
        first_turn_line_count=command_item.expanded_line_count,
        first_turn_char_count=command_item.expanded_char_count,
        first_turn_raw_include_count=command_item.raw_include_count,
        runtime_projection=command_item.runtime_projection,
        stages=stages,
        violation_count=violation_count,
        warnings=tuple(warnings),
    )


def _load_stage_manifest_for_source(
    source: StagePromptSource,
    manifest_path: Path,
    warnings: list[str],
) -> WorkflowStageManifest | None:
    try:
        return load_workflow_stage_manifest_from_path(
            manifest_path,
            expected_workflow_id=source.name,
            known_init_fields=known_init_fields_for_workflow(source.name),
            specs_root=source.src_root / "specs",
        )
    except ValueError as exc:
        warnings.append(str(exc))
        return None


def _measure_workflow_stage(
    *,
    source: StagePromptSource,
    manifest: WorkflowStageManifest,
    stage: WorkflowStage,
    first_turn_trace: _IncludeTrace,
    prior_stage_authorities: frozenset[str],
    path_prefix: str,
) -> WorkflowStagePromptMetric:
    eager_authorities = stage.eager_authorities()
    lazy_authorities = stage.must_not_eager_load
    conditional_authorities = _conditional_authorities(stage)
    first_turn_authorities = tuple(
        authority for authority in first_turn_trace.authorities if _authority_path(source.src_root, authority).is_file()
    )
    authority_metric_index = _measure_authority_index(
        source,
        (*eager_authorities, *conditional_authorities, *lazy_authorities, *first_turn_authorities),
        path_prefix=path_prefix,
    )
    eager_metrics = tuple(authority_metric_index[authority] for authority in eager_authorities)
    lazy_metrics = tuple(authority_metric_index[authority] for authority in lazy_authorities)
    conditional_metrics = tuple(authority_metric_index[authority] for authority in conditional_authorities)
    violations = _must_not_eager_load_violations(
        source=source,
        workflow_id=manifest.workflow_id,
        stage=stage,
        eager_authorities=eager_authorities,
        first_turn_trace=first_turn_trace,
        prior_stage_authorities=prior_stage_authorities,
    )
    authority_usage_metrics = _stage_authority_usage_metrics(
        source=source,
        workflow_id=manifest.workflow_id,
        stage=stage,
        eager_authorities=eager_authorities,
        conditional_authorities=conditional_authorities,
        lazy_authorities=lazy_authorities,
        first_turn_trace=first_turn_trace,
        prior_stage_authorities=prior_stage_authorities,
        authority_metric_index=authority_metric_index,
        violations=violations,
    )
    first_turn_active_metrics = tuple(
        metric for metric in authority_usage_metrics if metric.first_turn_role == "active"
    )
    prior_stage_residue_metrics = tuple(
        metric for metric in authority_usage_metrics if metric.first_turn_role == "prior_stage_residue"
    )
    init_field_metrics = _stage_init_field_usage_metrics(stage)
    return WorkflowStagePromptMetric(
        workflow_id=manifest.workflow_id,
        stage_id=stage.id,
        order=stage.order,
        eager_authorities=eager_authorities,
        eager_authority_metrics=eager_metrics,
        eager_line_count=sum(metric.expanded_line_count for metric in eager_metrics),
        eager_char_count=sum(metric.expanded_char_count for metric in eager_metrics),
        lazy_authorities=lazy_authorities,
        lazy_authority_metrics=lazy_metrics,
        lazy_line_count=sum(metric.expanded_line_count for metric in lazy_metrics),
        lazy_char_count=sum(metric.expanded_char_count for metric in lazy_metrics),
        must_not_eager_load_violations=violations,
        conditional_authorities=conditional_authorities,
        conditional_authority_groups=_conditional_authority_groups(stage),
        conditional_authority_metrics=conditional_metrics,
        conditional_line_count=sum(metric.expanded_line_count for metric in conditional_metrics),
        conditional_char_count=sum(metric.expanded_char_count for metric in conditional_metrics),
        authority_usage_metrics=authority_usage_metrics,
        first_turn_active_line_count=sum(metric.expanded_line_count for metric in first_turn_active_metrics),
        first_turn_active_char_count=sum(metric.expanded_char_count for metric in first_turn_active_metrics),
        prior_stage_residue_line_count=sum(metric.expanded_line_count for metric in prior_stage_residue_metrics),
        prior_stage_residue_char_count=sum(metric.expanded_char_count for metric in prior_stage_residue_metrics),
        must_not_eager_load_actionable_violation_count=sum(
            1 for violation in violations if violation.classification == "eager_load_violation"
        ),
        must_not_eager_load_prior_stage_residue_count=sum(
            1 for violation in violations if violation.classification == "prior_stage_residue"
        ),
        required_init_fields=stage.required_init_fields,
        required_init_field_metrics=init_field_metrics,
        required_init_field_count=len(stage.required_init_fields),
        high_pressure_init_field_count=sum(1 for metric in init_field_metrics if metric.likely_bulky),
        likely_bulky_init_field_count=sum(1 for metric in init_field_metrics if metric.likely_bulky),
    )


def _measure_authority(
    source: StagePromptSource,
    authority: str,
    *,
    path_prefix: str,
) -> AuthorityPromptMetric:
    path = _authority_path(source.src_root, authority)
    raw_text = path.read_text(encoding="utf-8")
    expanded_text = expand_at_includes(raw_text, source.src_root, path_prefix)
    include_trace = _include_trace_from_text(
        raw_text,
        source.src_root,
        active_authorities=frozenset({authority}),
    )
    return AuthorityPromptMetric(
        authority=authority,
        path=_relative_path(path, source.repo_root),
        raw_line_count=_line_count(raw_text),
        raw_char_count=len(raw_text),
        raw_include_count=_count_raw_includes(raw_text),
        expanded_line_count=_line_count(expanded_text),
        expanded_char_count=len(expanded_text),
        transitive_include_authorities=include_trace.authorities,
    )


def _measure_authority_index(
    source: StagePromptSource,
    authorities: Sequence[str],
    *,
    path_prefix: str,
) -> dict[str, AuthorityPromptMetric]:
    metrics: dict[str, AuthorityPromptMetric] = {}
    for authority in _ordered_unique(authorities):
        if not _authority_path(source.src_root, authority).is_file():
            continue
        metrics[authority] = _measure_authority(source, authority, path_prefix=path_prefix)
    return metrics


def _stage_authority_usage_metrics(
    *,
    source: StagePromptSource,
    workflow_id: str,
    stage: WorkflowStage,
    eager_authorities: tuple[str, ...],
    conditional_authorities: tuple[str, ...],
    lazy_authorities: tuple[str, ...],
    first_turn_trace: _IncludeTrace,
    prior_stage_authorities: frozenset[str],
    authority_metric_index: Mapping[str, AuthorityPromptMetric],
    violations: tuple[MustNotEagerLoadViolation, ...],
) -> tuple[StageAuthorityUsageMetric, ...]:
    eager_authority_set = set(eager_authorities)
    conditional_authority_set = set(conditional_authorities)
    lazy_authority_set = set(lazy_authorities)
    conditional_whens = _conditional_authority_whens(stage)
    first_turn_authorities = tuple(
        authority for authority in first_turn_trace.authorities if _authority_path(source.src_root, authority).is_file()
    )
    violation_count_by_authority: dict[str, int] = defaultdict(int)
    for violation in violations:
        if violation.classification == "eager_load_violation":
            violation_count_by_authority[violation.authority] += 1

    usage_metrics: list[StageAuthorityUsageMetric] = []
    for authority in _ordered_unique(
        (*eager_authorities, *conditional_authorities, *lazy_authorities, *first_turn_authorities)
    ):
        authority_metric = authority_metric_index.get(authority)
        if authority_metric is None:
            continue
        roles: list[StageAuthorityRole] = []
        if authority in eager_authority_set:
            roles.append("stage_eager")
        if authority in conditional_authority_set:
            roles.append("conditional")
        if authority in lazy_authority_set:
            roles.append("lazy")
        usage_metrics.append(
            StageAuthorityUsageMetric(
                workflow_id=workflow_id,
                stage_id=stage.id,
                order=stage.order,
                authority=authority,
                path=authority_metric.path,
                roles=tuple(roles),
                conditional_when=conditional_whens.get(authority, ()),
                first_turn_role=_first_turn_role_for_authority(
                    authority=authority,
                    eager_authorities=eager_authority_set,
                    first_turn_trace=first_turn_trace,
                    prior_stage_authorities=prior_stage_authorities,
                ),
                first_turn_chains=first_turn_trace.chains_by_authority.get(authority, ()),
                raw_line_count=authority_metric.raw_line_count,
                raw_char_count=authority_metric.raw_char_count,
                raw_include_count=authority_metric.raw_include_count,
                expanded_line_count=authority_metric.expanded_line_count,
                expanded_char_count=authority_metric.expanded_char_count,
                transitive_include_authorities=authority_metric.transitive_include_authorities,
                violation_count=violation_count_by_authority[authority],
            )
        )
    return tuple(
        sorted(
            usage_metrics,
            key=lambda metric: (
                -metric.expanded_char_count,
                -metric.violation_count,
                metric.workflow_id,
                metric.stage_id,
                metric.authority,
            ),
        )
    )


def _conditional_authorities(stage: WorkflowStage) -> tuple[str, ...]:
    return _ordered_unique(
        authority for conditional in stage.conditional_authorities for authority in conditional.authorities
    )


def _conditional_authority_groups(stage: WorkflowStage) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple((conditional.when, conditional.authorities) for conditional in stage.conditional_authorities)


def _conditional_authority_whens(stage: WorkflowStage) -> dict[str, tuple[str, ...]]:
    whens_by_authority: dict[str, list[str]] = defaultdict(list)
    for conditional in stage.conditional_authorities:
        for authority in conditional.authorities:
            if conditional.when not in whens_by_authority[authority]:
                whens_by_authority[authority].append(conditional.when)
    return {authority: tuple(whens) for authority, whens in whens_by_authority.items()}


def _first_turn_role_for_authority(
    *,
    authority: str,
    eager_authorities: set[str],
    first_turn_trace: _IncludeTrace,
    prior_stage_authorities: frozenset[str],
) -> FirstTurnAuthorityRole:
    if authority not in first_turn_trace.chains_by_authority:
        return "not_first_turn"
    if authority in eager_authorities:
        return "active"
    if _is_prior_stage_first_turn_residue(authority, first_turn_trace, prior_stage_authorities):
        return "prior_stage_residue"
    return "unexpected"


def _is_prior_stage_first_turn_residue(
    authority: str,
    first_turn_trace: _IncludeTrace,
    prior_stage_authorities: frozenset[str],
) -> bool:
    if authority in prior_stage_authorities:
        return True
    return any(
        chain and chain[0] in prior_stage_authorities
        for chain in first_turn_trace.chains_by_authority.get(authority, ())
    )


def _stage_init_field_usage_metrics(stage: WorkflowStage) -> tuple[StageInitFieldUsageMetric, ...]:
    return tuple(
        StageInitFieldUsageMetric(
            field_name=field_name,
            field_kind_guess=_init_field_kind_guess(field_name),
            field_pressure_class=_init_field_pressure_class(field_name),
            likely_bulky=_is_likely_bulky_init_field(field_name),
        )
        for field_name in stage.required_init_fields
    )


def _init_field_kind_guess(field_name: str) -> StageInitFieldKind:
    if field_name.endswith("_content") or field_name in {
        "project_content",
        "state_content",
        "roadmap_content",
        "requirements_content",
        "reference_artifacts_content",
        "continuity_handoff_content",
    }:
        return "content"
    if field_name.endswith("_context") or field_name in {
        "active_reference_context",
        "protocol_bundle_context",
    }:
        return "context"
    if "contract" in field_name or field_name in {"contract_intake", "effective_reference_intake"}:
        return "contract"
    if "report" in field_name:
        return "report"
    if "schema_bridge" in field_name or field_name.endswith("_bridge"):
        return "schema_bridge"
    if "artifact" in field_name:
        return "artifacts"
    if field_name.endswith(("_files", "_artifacts", "_artifact_files")):
        return "file_list"
    if field_name.endswith(("_payload", "_status", "_validation", "_gate", "_load_info")):
        return "status_payload"
    return "scalar"


def _init_field_pressure_class(field_name: str) -> StageInitFieldPressureClass:
    if _is_likely_bulky_init_field(field_name):
        return "likely_bulky"
    return "ordinary"


def _is_likely_bulky_init_field(field_name: str) -> bool:
    if field_name.endswith(("_content", "_context")):
        return True
    bulky_tokens = ("artifact", "bridge", "contract", "reference", "report", "schema")
    return any(token in field_name for token in bulky_tokens)


def _init_field_pressure_rank(field_pressure_class: str) -> int:
    return {"likely_bulky": 0, "ordinary": 1}.get(field_pressure_class, 2)


def _init_field_kind_rank(field_kind_guess: str) -> int:
    return {
        "content": 0,
        "context": 1,
        "contract": 2,
        "report": 3,
        "schema_bridge": 4,
        "artifacts": 5,
        "file_list": 6,
        "status_payload": 7,
        "scalar": 8,
    }.get(field_kind_guess, 9)


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _must_not_eager_load_violations(
    *,
    source: StagePromptSource,
    workflow_id: str,
    stage: WorkflowStage,
    eager_authorities: tuple[str, ...],
    first_turn_trace: _IncludeTrace,
    prior_stage_authorities: frozenset[str],
) -> tuple[MustNotEagerLoadViolation, ...]:
    lazy_authorities = set(stage.must_not_eager_load)
    eager_authority_set = set(eager_authorities)
    violations: list[MustNotEagerLoadViolation] = []
    seen: set[tuple[str, str, tuple[str, ...], str]] = set()

    def add(
        authority: str,
        violation_source: str,
        eager_via: tuple[str, ...],
        *,
        classification: MustNotEagerLoadViolationClassification = "eager_load_violation",
    ) -> None:
        key = (authority, violation_source, eager_via, classification)
        if key in seen:
            return
        seen.add(key)
        violations.append(
            _must_not_violation(
                workflow_id,
                stage.id,
                authority,
                violation_source,
                eager_via=eager_via,
                classification=classification,
            )
        )

    for authority in sorted(lazy_authorities.intersection(eager_authority_set)):
        add(authority, "manifest_overlap", (authority,))

    for authority in sorted(lazy_authorities):
        for chain in first_turn_trace.chains_by_authority.get(authority, ()):
            classification: MustNotEagerLoadViolationClassification = (
                "prior_stage_residue"
                if _is_prior_stage_first_turn_residue(authority, first_turn_trace, prior_stage_authorities)
                and authority not in eager_authority_set
                else "eager_load_violation"
            )
            if len(chain) == 1:
                add(authority, "first_turn_direct_include", chain, classification=classification)
            elif len(chain) > 1:
                add(authority, "first_turn_transitive_include", chain[:-1], classification=classification)

    for eager_authority in eager_authorities:
        eager_path = _authority_path(source.src_root, eager_authority)
        if not eager_path.is_file():
            continue
        trace = _include_trace_from_path(
            eager_path,
            source.src_root,
            authority=eager_authority,
        )
        for authority in sorted(lazy_authorities):
            for chain in trace.chains_by_authority.get(authority, ()):
                add(authority, "stage_eager_transitive_include", (eager_authority, *chain[:-1]))

    return tuple(violations)


def _must_not_violation(
    workflow_id: str,
    stage_id: str,
    authority: str,
    violation_source: MustNotEagerLoadViolationSource | str,
    *,
    eager_via: tuple[str, ...],
    classification: MustNotEagerLoadViolationClassification = "eager_load_violation",
) -> MustNotEagerLoadViolation:
    return MustNotEagerLoadViolation(
        workflow_id=workflow_id,
        stage_id=stage_id,
        authority=authority,
        violation_source=cast(MustNotEagerLoadViolationSource, violation_source),
        eager_via=eager_via,
        classification=classification,
    )


def _include_trace_from_path(path: Path, src_root: Path, *, authority: str) -> _IncludeTrace:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _IncludeTrace(authorities=(), chains_by_authority={})
    return _include_trace_from_text(
        raw_text,
        src_root,
        active_authorities=frozenset({authority}),
    )


def _include_trace_from_text(
    text: str,
    src_root: Path,
    *,
    active_authorities: frozenset[str],
) -> _IncludeTrace:
    ordered: list[str] = []
    chains_by_authority: dict[str, list[tuple[str, ...]]] = defaultdict(list)

    def add_chain(authority: str, chain: tuple[str, ...]) -> None:
        if authority not in ordered:
            ordered.append(authority)
        if chain not in chains_by_authority[authority]:
            chains_by_authority[authority].append(chain)

    def visit(current_text: str, active: frozenset[str], prefix: tuple[str, ...]) -> None:
        for _line_number, line in _iter_unfenced_lines(_body_without_frontmatter(current_text)):
            include_path = parse_at_include_path(line.strip())
            authority = _authority_id_from_include_path(include_path)
            if authority is None:
                continue
            chain = (*prefix, authority)
            add_chain(authority, chain)
            if authority in active:
                continue
            authority_path = _authority_path(src_root, authority)
            if not authority_path.is_file():
                continue
            try:
                included_text = authority_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            visit(included_text, active | {authority}, chain)

    visit(text, active_authorities, ())
    return _IncludeTrace(
        authorities=tuple(ordered),
        chains_by_authority={authority: tuple(chains) for authority, chains in chains_by_authority.items()},
    )


def _authority_id_from_include_path(include_path: str | None) -> str | None:
    if include_path is None:
        return None
    for prefix in ("{GPD_INSTALL_DIR}/", "get-physics-done/"):
        if include_path.startswith(prefix):
            candidate = include_path[len(prefix) :]
            return _normalize_authority_id_or_none(candidate)
    return _normalize_authority_id_or_none(include_path)


def _normalize_authority_id_or_none(candidate: str) -> str | None:
    try:
        return _normalize_authority_id(candidate, label="include")
    except ValueError:
        return None


def _normalize_authority_id(raw: str, *, label: str) -> str:
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a normalized relative POSIX path")
    normalized = path.as_posix()
    if normalized != raw:
        raise ValueError(f"{label} must be a normalized relative POSIX path")
    if path.suffix != ".md":
        raise ValueError(f"{label} must reference a markdown file")
    if not normalized.startswith(("workflows/", "references/", "templates/")):
        raise ValueError(f"{label} must reference workflows/, references/, or templates/")
    return normalized


def _authority_path(src_root: Path, authority: str) -> Path:
    return src_root / "specs" / authority


def _workflow_stage_metric_to_dict(metric: WorkflowStagePromptMetric, top: int | None = None) -> dict[str, object]:
    return {
        "workflow_id": metric.workflow_id,
        "stage_id": metric.stage_id,
        "order": metric.order,
        "eager_authorities": list(metric.eager_authorities),
        "eager_authority_metrics": [
            _authority_prompt_metric_to_dict(authority_metric) for authority_metric in metric.eager_authority_metrics
        ],
        "eager_line_count": metric.eager_line_count,
        "eager_char_count": metric.eager_char_count,
        "conditional_authorities": [
            {"when": when, "authorities": list(authorities)}
            for when, authorities in metric.conditional_authority_groups
        ],
        "conditional_authority_metrics": [
            _authority_prompt_metric_to_dict(authority_metric)
            for authority_metric in metric.conditional_authority_metrics
        ],
        "conditional_line_count": metric.conditional_line_count,
        "conditional_char_count": metric.conditional_char_count,
        "lazy_authorities": list(metric.lazy_authorities),
        "lazy_authority_metrics": [
            _authority_prompt_metric_to_dict(authority_metric) for authority_metric in metric.lazy_authority_metrics
        ],
        "lazy_line_count": metric.lazy_line_count,
        "lazy_char_count": metric.lazy_char_count,
        "first_turn_active_line_count": metric.first_turn_active_line_count,
        "first_turn_active_char_count": metric.first_turn_active_char_count,
        "prior_stage_residue_line_count": metric.prior_stage_residue_line_count,
        "prior_stage_residue_char_count": metric.prior_stage_residue_char_count,
        "must_not_eager_load_actionable_violation_count": metric.must_not_eager_load_actionable_violation_count,
        "must_not_eager_load_prior_stage_residue_count": metric.must_not_eager_load_prior_stage_residue_count,
        "must_not_eager_load_violations": [
            _must_not_eager_load_violation_to_dict(violation)
            for violation in metric.must_not_eager_load_violations
            if violation.classification == "eager_load_violation"
        ],
        "prior_stage_residue_authority_metrics": _prior_stage_residue_authority_metrics_to_dict(metric),
        "authority_bucket_metrics": _authority_bucket_metrics_to_dict(metric),
        "top_authority_metrics": [
            _stage_authority_usage_metric_to_dict(authority_metric)
            for authority_metric in _top_stage_authority_usage_metrics(metric.authority_usage_metrics, top)
        ],
        "required_init_fields": list(metric.required_init_fields),
        "required_init_field_count": metric.required_init_field_count,
        "high_pressure_init_field_count": metric.high_pressure_init_field_count,
        "likely_bulky_init_field_count": metric.likely_bulky_init_field_count,
    }


def _top_stage_authority_usage_metrics(
    metrics: Sequence[StageAuthorityUsageMetric],
    top: int | None,
) -> tuple[StageAuthorityUsageMetric, ...]:
    sorted_metrics = sorted(
        metrics,
        key=lambda metric: (
            -metric.expanded_char_count,
            -metric.violation_count,
            metric.workflow_id,
            metric.stage_id,
            metric.authority,
        ),
    )
    limit = _top_limit(top)
    return tuple(sorted_metrics[:limit])


def _prior_stage_residue_authority_metrics_to_dict(
    metric: WorkflowStagePromptMetric,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    residue_violations = {
        violation.authority: violation
        for violation in metric.must_not_eager_load_violations
        if violation.classification == "prior_stage_residue"
    }
    for authority_metric in metric.authority_usage_metrics:
        if authority_metric.first_turn_role != "prior_stage_residue":
            continue
        row = _stage_authority_usage_metric_to_dict(authority_metric)
        violation = residue_violations.get(authority_metric.authority)
        row["bucket"] = "prior_stage_residue"
        row["violation_source"] = "prior_stage_residue"
        row["classification"] = "prior_stage_residue"
        if violation is not None:
            row["eager_via"] = list(violation.eager_via)
        rows.append(row)
    return rows


def _authority_bucket_metrics_to_dict(metric: WorkflowStagePromptMetric) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for authority_metric in metric.authority_usage_metrics:
        base = _stage_authority_usage_metric_to_dict(authority_metric)
        for bucket in _stage_authority_buckets(authority_metric):
            row = dict(base)
            row["bucket"] = bucket
            if bucket == "prior_stage_residue":
                row["violation_source"] = "prior_stage_residue"
                row["classification"] = "prior_stage_residue"
            rows.append(row)
    return rows


def _stage_authority_usage_metric_to_dict(metric: StageAuthorityUsageMetric) -> dict[str, object]:
    fields = (
        "workflow_id",
        "stage_id",
        "order",
        "authority",
        "path",
        "first_turn_role",
        "raw_line_count",
        "raw_char_count",
        "raw_include_count",
        "expanded_line_count",
        "expanded_char_count",
        "violation_count",
    )
    return {field: getattr(metric, field) for field in fields} | {
        "stage_order": metric.order,
        "bucket": _primary_stage_authority_bucket(metric),
        "loading_kind": _loading_kind_for_authority_metric(metric),
        "buckets": list(_stage_authority_buckets(metric)),
        "roles": list(metric.roles),
        "conditional_when": list(metric.conditional_when),
        "first_turn_chains": [list(chain) for chain in metric.first_turn_chains],
        "violation_source": _authority_usage_violation_source(metric),
        "eager_via": list(_authority_usage_eager_via(metric)),
        "classification": _authority_usage_classification(metric),
        "first_turn_chain_count": len(metric.first_turn_chains),
        "transitive_include_authorities": list(metric.transitive_include_authorities),
        "transitive_include_count": len(metric.transitive_include_authorities),
    }


def _stage_authority_buckets(metric: StageAuthorityUsageMetric) -> tuple[str, ...]:
    first_turn_bucket = {
        "active": "first_turn_active",
        "prior_stage_residue": "prior_stage_residue",
        "unexpected": "first_turn_unexpected",
    }.get(metric.first_turn_role)
    prefix = (first_turn_bucket,) if first_turn_bucket else ()
    return tuple(_ordered_unique((*prefix, *metric.roles)))


def _primary_stage_authority_bucket(metric: StageAuthorityUsageMetric) -> str:
    buckets = _stage_authority_buckets(metric)
    return buckets[0] if buckets else "unclassified"


def _loading_kind_for_authority_metric(metric: StageAuthorityUsageMetric) -> str:
    return next(
        (
            label
            for role, label in (("stage_eager", "eager"), ("conditional", "conditional"), ("lazy", "lazy"))
            if role in metric.roles
        ),
        _primary_stage_authority_bucket(metric),
    )


def _authority_usage_violation_source(metric: StageAuthorityUsageMetric) -> str:
    if metric.first_turn_role == "prior_stage_residue":
        return "prior_stage_residue"
    if metric.violation_count:
        return "violation"
    return (
        metric.first_turn_role
        if metric.first_turn_role != "not_first_turn"
        else _primary_stage_authority_bucket(metric)
    )


def _authority_usage_eager_via(metric: StageAuthorityUsageMetric) -> tuple[str, ...]:
    return metric.first_turn_chains[0] if metric.first_turn_chains else ()


def _authority_usage_classification(metric: StageAuthorityUsageMetric) -> str:
    return (
        "prior_stage_residue"
        if metric.first_turn_role == "prior_stage_residue"
        else "eager_load_violation"
        if metric.violation_count
        else ""
    )


def _authority_prompt_metric_to_dict(metric: AuthorityPromptMetric) -> dict[str, object]:
    fields = (
        "authority",
        "path",
        "raw_line_count",
        "raw_char_count",
        "raw_include_count",
        "expanded_line_count",
        "expanded_char_count",
    )
    return {field: getattr(metric, field) for field in fields} | {
        "transitive_include_authorities": list(metric.transitive_include_authorities)
    }


def _must_not_eager_load_violation_to_dict(violation: MustNotEagerLoadViolation) -> dict[str, object]:
    return {
        "workflow_id": violation.workflow_id,
        "stage_id": violation.stage_id,
        "authority": violation.authority,
        "violation_source": violation.violation_source,
        "eager_via": list(violation.eager_via),
        "classification": violation.classification,
    }


def _runtime_projection_metric_to_dict(metric: RuntimeProjectionLike) -> dict[str, object]:
    fields = (
        "runtime",
        "native_include_support",
        "expanded_line_count",
        "expanded_char_count",
        "line_count",
        "char_count",
        "line_delta",
        "char_delta",
        "char_delta_percent",
        "include_count",
        "runtime_note_count",
        "runtime_note_chars",
        "shell_fence_count",
        "shell_rewrite_count",
        "bridge_command_occurrences",
    )
    return {field: getattr(metric, field) for field in fields}
