"""Compatibility facade for stage-aware prompt diagnostics."""

from gpd.core import stage_prompt_totals as _stage_prompt_totals
from gpd.core.stage_manifest_duplicate_diagnostics import *  # noqa: F403
from gpd.core.stage_prompt_diagnostics import *  # noqa: F403

stage_diagnostics_totals = _stage_prompt_totals.stage_diagnostics_totals
