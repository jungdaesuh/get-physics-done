"""Aggregate totals for stage prompt diagnostics."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from gpd.core.stage_prompt_diagnostics import StageAwareWorkflowPromptMetric, repeated_prior_stage_residue_rows


def stage_diagnostics_totals(stage_diagnostics: Sequence[object]) -> dict[str, int]:
    stages = [stage for workflow in stage_diagnostics for stage in getattr(workflow, "stages", ())]
    actionable_violation_count = sum(_int(stage, "must_not_eager_load_actionable_violation_count") for stage in stages)
    prior_stage_residue_count = sum(_int(stage, "must_not_eager_load_prior_stage_residue_count") for stage in stages)
    repeated_residue_rows = repeated_prior_stage_residue_rows(
        cast(Sequence[StageAwareWorkflowPromptMetric], stage_diagnostics),
        top=None,
    )
    return {
        "workflow_count": len(stage_diagnostics),
        "stage_count": len(stages),
        "first_turn_char_count": sum(_int(workflow, "first_turn_char_count") for workflow in stage_diagnostics),
        "first_turn_line_count": sum(_int(workflow, "first_turn_line_count") for workflow in stage_diagnostics),
        "first_turn_active_char_count": sum(_int(stage, "first_turn_active_char_count") for stage in stages),
        "first_turn_active_line_count": sum(_int(stage, "first_turn_active_line_count") for stage in stages),
        "prior_stage_residue_char_count": sum(_int(stage, "prior_stage_residue_char_count") for stage in stages),
        "prior_stage_residue_line_count": sum(_int(stage, "prior_stage_residue_line_count") for stage in stages),
        "eager_char_count": sum(_int(stage, "eager_char_count") for stage in stages),
        "eager_line_count": sum(_int(stage, "eager_line_count") for stage in stages),
        "stage_eager_char_count": sum(_int(stage, "eager_char_count") for stage in stages),
        "stage_eager_line_count": sum(_int(stage, "eager_line_count") for stage in stages),
        "conditional_char_count": sum(_int(stage, "conditional_char_count") for stage in stages),
        "conditional_line_count": sum(_int(stage, "conditional_line_count") for stage in stages),
        "lazy_char_count": sum(_int(stage, "lazy_char_count") for stage in stages),
        "lazy_line_count": sum(_int(stage, "lazy_line_count") for stage in stages),
        "must_not_eager_load_violation_count": actionable_violation_count,
        "must_not_eager_load_actionable_violation_count": actionable_violation_count,
        "must_not_eager_load_prior_stage_residue_count": prior_stage_residue_count,
        "prior_stage_residue_count": prior_stage_residue_count,
        "repeated_prior_stage_residue_authority_count": len(repeated_residue_rows),
        "repeated_prior_stage_residue_occurrence_count": sum(
            _row_int(row, "occurrence_count") for row in repeated_residue_rows
        ),
        "repeated_prior_stage_residue_char_count": sum(
            _row_int(row, "expanded_char_count") for row in repeated_residue_rows
        ),
        "repeated_prior_stage_residue_line_count": sum(
            _row_int(row, "expanded_line_count") for row in repeated_residue_rows
        ),
        "must_not_eager_load_record_count": sum(
            len(getattr(stage, "must_not_eager_load_violations", ())) for stage in stages
        ),
        "selected_init_field_count": sum(_int(stage, "required_init_field_count") for stage in stages),
        "required_init_field_count": sum(_int(stage, "required_init_field_count") for stage in stages),
        "selected_init_content_field_count": sum(
            1
            for stage in stages
            for metric in getattr(stage, "required_init_field_metrics", ())
            if getattr(metric, "field_kind_guess", "") == "content"
        ),
        "high_pressure_init_field_count": sum(_int(stage, "high_pressure_init_field_count") for stage in stages),
        "likely_bulky_init_field_count": sum(_int(stage, "likely_bulky_init_field_count") for stage in stages),
        "likely_bulky_field_count": sum(_int(stage, "likely_bulky_init_field_count") for stage in stages),
    }


def _int(value: object, name: str) -> int:
    raw = getattr(value, name, 0)
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else 0


def _row_int(row: dict[str, object], name: str) -> int:
    raw = row.get(name, 0)
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
