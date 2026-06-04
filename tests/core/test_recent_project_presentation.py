from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gpd.core.project_reentry import recent_project_row_sort_key, resolve_project_reentry
from gpd.core.recent_project_presentation import (
    annotate_recent_project_rows,
    build_recent_resume_summary_lines,
    load_recent_project_display_rows,
    normalize_recent_project_row,
    recent_project_recovery_view,
)
from gpd.core.recovery_advice import RecoveryAdvice


def test_load_recent_project_display_rows_ignores_additive_fields(tmp_path: Path, monkeypatch) -> None:
    project_root = (tmp_path / "recent-project").resolve(strict=False)
    project_root.mkdir(parents=True, exist_ok=True)
    row = SimpleNamespace(
        model_dump=lambda mode="json": {
            "project_root": str(project_root),
            "last_session_at": "2026-03-28T12:00:00+00:00",
            "available": True,
            "workspace_root": str(project_root),
            "future_field": {"nested": "value"},
        }
    )
    monkeypatch.setattr("gpd.core.recent_projects.list_recent_projects", lambda store_root=None, last=None: [row])

    rows = load_recent_project_display_rows(cwd=tmp_path)

    assert len(rows) == 1
    assert rows[0]["project_root"] == str(project_root)
    assert rows[0]["available"] is True
    assert "workspace_root" not in rows[0]
    assert "future_field" not in rows[0]


def test_normalize_recent_project_row_marks_unavailable_rows_without_command(tmp_path: Path) -> None:
    project_root = (tmp_path / "missing-project").resolve(strict=False)

    normalized = normalize_recent_project_row(
        {
            "project_root": str(project_root),
            "available": False,
            "resume_file": "GPD/phases/01/.continue-here.md",
        }
    )

    assert normalized is not None
    assert normalized["available"] is False
    assert normalized["command"] == "unavailable"


def test_recent_project_row_sort_key_matches_project_reentry_order(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    first_project = tmp_path / "recent-alpha"
    second_project = tmp_path / "recent-beta"
    for project in (first_project, second_project):
        handoff = project / "GPD" / "phases" / "01" / ".continue-here.md"
        handoff.parent.mkdir(parents=True, exist_ok=True)
        handoff.write_text("resume", encoding="utf-8")

    recent_rows = [
        {
            "schema_version": 1,
            "project_root": first_project.resolve(strict=False).as_posix(),
            "last_session_at": "2026-03-28T12:00:00+00:00",
            "source_recorded_at": "2026-03-29T12:00:00+00:00",
            "resume_file": "GPD/phases/01/.continue-here.md",
            "resumable": True,
        },
        {
            "schema_version": 1,
            "project_root": second_project.resolve(strict=False).as_posix(),
            "last_session_at": "2026-03-29T12:00:00+00:00",
            "source_recorded_at": "2026-03-28T12:00:00+00:00",
            "resume_file": "GPD/phases/01/.continue-here.md",
            "resumable": True,
        },
    ]

    display_rows = sorted(recent_rows, key=recent_project_row_sort_key, reverse=True)
    canonical_rows = resolve_project_reentry(workspace, recent_rows=recent_rows).candidates

    assert [Path(str(row["project_root"])).name for row in display_rows] == [
        Path(candidate.project_root).name for candidate in canonical_rows
    ]
    assert [Path(str(row["project_root"])).name for row in display_rows] == ["recent-alpha", "recent-beta"]


def test_recent_project_recovery_view_surfaces_introspection_failures(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "recent-project"
    gpd_dir = project_root / "GPD"
    gpd_dir.mkdir(parents=True, exist_ok=True)
    (gpd_dir / "STATE.md").write_text("# State\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")

    view = recent_project_recovery_view(
        {"project_root": str(project_root)},
        resume_loader=lambda _cwd: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert view is not None
    assert view["recovery_status"] == "recovery-error"
    assert view["recovery_status_label"] == "Recovery error"
    assert view["recovery_error_type"] == "RuntimeError"


def test_annotate_recent_project_rows_adds_core_recovery_view(tmp_path: Path) -> None:
    project_root = tmp_path / "recent-project"
    gpd_dir = project_root / "GPD"
    gpd_dir.mkdir(parents=True, exist_ok=True)
    (gpd_dir / "STATE.md").write_text("# State\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    resume_file = "GPD/phases/01/.continue-here.md"

    def _advice_builder(*_args, **_kwargs):
        return RecoveryAdvice(status="session-handoff")

    annotated = annotate_recent_project_rows(
        [{"project_root": str(project_root), "available": True, "resumable": True}],
        resume_loader=lambda _cwd: {
            "planning_exists": True,
            "state_exists": True,
            "roadmap_exists": True,
            "project_exists": True,
            "active_resume_origin": "continuation.handoff",
            "active_resume_pointer": resume_file,
        },
        recovery_advice_builder=_advice_builder,
    )

    assert annotated[0]["recovery_status"] == "session-handoff"
    assert annotated[0]["recovery_origin"] == "canonical continuation"
    assert str(annotated[0]["recovery_target"]).endswith("GPD/phases/01/.continue-here.md")


def test_recent_resume_summary_lines_keep_runtime_specific_commands_generic(tmp_path: Path) -> None:
    project_root = (tmp_path / "recent-project").resolve(strict=False)
    project_root.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "project_root": str(project_root),
            "available": True,
            "resumable": True,
            "last_session_at": "2026-03-28T12:00:00+00:00",
            "stopped_at": "Phase 1",
        }
    ]

    output = "\n".join(build_recent_resume_summary_lines(rows))

    assert "Recent Projects" in output
    assert "Select a workspace above" in output
    assert "resume-work" in output
    assert "suggest-next" in output
    assert "/gpd:resume-work" not in output
    assert "$gpd-resume-work" not in output
    assert "/gpd:suggest-next" not in output
    assert "$gpd-suggest-next" not in output


def test_resume_recent_requests_only_the_bounded_recent_picker_window(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_list_recent_projects(store_root=None, last=None):
        captured["last"] = last
        return []

    monkeypatch.setattr("gpd.core.recent_projects.list_recent_projects", _fake_list_recent_projects)

    rows = load_recent_project_display_rows(last=20)

    assert rows == []
    assert captured["last"] == 20


def test_load_recent_project_display_rows_rejects_malformed_helper_rows(tmp_path: Path, monkeypatch) -> None:
    canonical_row = SimpleNamespace(
        model_dump=lambda mode="json": {
            "workspace_root": (tmp_path / "recent-project").resolve(strict=False).as_posix(),
            "cwd": (tmp_path / "recent-project").resolve(strict=False).as_posix(),
            "path": (tmp_path / "recent-project").resolve(strict=False).as_posix(),
            "resume_file": "GPD/phases/02/.continue-here.md",
            "can_resume": True,
            "last_event_at": "2026-03-28T12:00:00+00:00",
        }
    )
    monkeypatch.setattr(
        "gpd.core.recent_projects.list_recent_projects", lambda store_root=None, last=None: [canonical_row]
    )

    with pytest.raises(ValueError, match="unexpected field"):
        load_recent_project_display_rows()
