"""Provider-free project fixtures for Phase 4 persona replay rows."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gpd.core.state import default_state_dict, generate_state_markdown
from tests.return_skeleton_support import render_gpd_return_block as _render_gpd_return_block

PHASE = "02"
PHASE_NAME = "Analysis"
PHASE_DIR_REL = "GPD/phases/02-analysis"
FINAL_SUMMARY_REL = f"{PHASE_DIR_REL}/02-02-SUMMARY.md"


@dataclass(frozen=True, slots=True)
class PhaseProject:
    """Small temp project handle used by replay scorers."""

    root: Path
    phase_dir: Path
    phase: str = PHASE
    phase_name: str = PHASE_NAME

    @property
    def state_path(self) -> Path:
        return self.root / "GPD" / "state.json"

    @property
    def state_markdown_path(self) -> Path:
        return self.root / "GPD" / "STATE.md"

    def read_state_text(self) -> str:
        return self.state_path.read_text(encoding="utf-8")


def render_gpd_return_block(
    files_written: Sequence[str],
    *,
    status: str = "completed",
    extra: str = "",
) -> str:
    """Render one fenced return block without embedding provider transcript data."""

    return _render_gpd_return_block(files_written, status=status, extra_yaml=extra)


def write_phase_project(
    root: Path,
    *,
    status: str = "Ready to execute",
    current_plan: int = 2,
    total_plans: int = 2,
    summary_count: int | None = None,
    verification_status: str | None = None,
    bounded_segment: bool = False,
) -> PhaseProject:
    """Create the minimal GPD project needed by lifecycle replay scorers."""

    gpd_dir = root / "GPD"
    phase_dir = root / PHASE_DIR_REL
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n\n## Phase 2: Analysis\n", encoding="utf-8")

    completed_summaries = total_plans if summary_count is None else summary_count
    for index in range(1, total_plans + 1):
        (phase_dir / f"02-{index:02d}-PLAN.md").write_text(f"# Plan {index}\n", encoding="utf-8")
        if index <= completed_summaries:
            (phase_dir / f"02-{index:02d}-SUMMARY.md").write_text(f"# Summary {index}\n", encoding="utf-8")

    if verification_status is not None:
        (phase_dir / "02-VERIFICATION.md").write_text(
            f"---\nstatus: {verification_status}\nscore: persona replay\n---\n\n# Verification\n",
            encoding="utf-8",
        )

    state = default_state_dict()
    state["position"]["current_phase"] = PHASE
    state["position"]["current_phase_name"] = PHASE_NAME
    state["position"]["current_plan"] = str(current_plan)
    state["position"]["total_plans_in_phase"] = total_plans
    state["position"]["total_phases"] = 2
    state["position"]["status"] = status
    if bounded_segment:
        state["continuation"]["bounded_segment"] = {
            "resume_file": f"{PHASE_DIR_REL}/.continue-here.md",
            "phase": PHASE,
            "plan": f"{current_plan:02d}",
            "segment_id": f"seg-{PHASE}-{current_plan:02d}",
            "segment_status": "paused",
            "waiting_for_review": True,
        }

    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    return PhaseProject(root=root, phase_dir=phase_dir)


def write_replay_report(root: Path, relative_path: str, content: str) -> Path:
    """Write a synthetic class-only handoff report inside a temp project."""

    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_stale(path: Path, *, age: timedelta = timedelta(hours=2)) -> datetime:
    """Backdate an artifact and return a freshness cutoff that should reject it."""

    stale_time = datetime.now(tz=UTC) - age
    os.utime(path, (stale_time.timestamp(), stale_time.timestamp()))
    return datetime.now(tz=UTC) - timedelta(minutes=1)
