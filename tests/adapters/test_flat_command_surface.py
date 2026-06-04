from __future__ import annotations

import json
from pathlib import Path

from gpd.adapters.flat_command_surface import (
    FlatCommandRenderContext,
    FlatCommandSurfacePolicy,
    copy_flattened_commands,
    load_tracked_generated_command_files,
    missing_flat_command_artifacts,
    remove_stale_generated_commands,
)
from gpd.adapters.install_utils import MANIFEST_NAME


def _policy() -> FlatCommandSurfacePolicy:
    return FlatCommandSurfacePolicy(runtime="synthetic", manifest_metadata_key="synthetic_generated_command_files")


def _write_manifest(target_dir: Path, payload: dict[str, object]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")


def test_load_tracked_generated_command_files_filters_dedupes_and_falls_back(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    _write_manifest(
        target_dir,
        {
            "synthetic_generated_command_files": [
                "gpd-help.md",
                "gpd-help.md",
                "gpd-nested-review.md",
                "help.md",
                "gpd-bad.txt",
                "nested/gpd-bad.md",
                7,
            ],
            "files": {
                "command/gpd-from-files.md": "hash",
                "command/user-owned.md": "hash",
                "agents/gpd-agent.md": "hash",
            },
        },
    )

    assert load_tracked_generated_command_files(target_dir, _policy()) == (
        "gpd-help.md",
        "gpd-nested-review.md",
        "gpd-from-files.md",
    )


def test_remove_stale_generated_commands_removes_only_tracked_flat_command_files(tmp_path: Path) -> None:
    command_dir = tmp_path / "command"
    command_dir.mkdir()
    for name in ("gpd-old.md", "gpd-keep.md", "gpd-user.md"):
        (command_dir / name).write_text(name, encoding="utf-8")

    removed = remove_stale_generated_commands(
        command_dir,
        ("gpd-old.md", "gpd-keep.md", "nested/gpd-bad.md", "user.md"),
        _policy(),
        keep_command_files=("gpd-keep.md",),
    )

    assert removed == ("gpd-old.md",)
    assert not (command_dir / "gpd-old.md").exists()
    assert (command_dir / "gpd-keep.md").is_file()
    assert (command_dir / "gpd-user.md").is_file()


def test_missing_flat_command_artifacts_reports_missing_files_and_surface_glob(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    command_dir = target_dir / "command"
    command_dir.mkdir(parents=True)
    (command_dir / "gpd-help.md").write_text("ok", encoding="utf-8")
    _write_manifest(
        target_dir,
        {"synthetic_generated_command_files": ["gpd-help.md", "gpd-missing.md"]},
    )

    assert missing_flat_command_artifacts(target_dir, _policy()) == (
        "command/gpd-missing.md",
        "command/gpd-*.md",
    )


def test_missing_flat_command_artifacts_requires_surface_when_no_tracked_files(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    _write_manifest(target_dir, {"synthetic_generated_command_files": []})

    assert missing_flat_command_artifacts(target_dir, _policy()) == ("command/gpd-*.md",)


def test_copy_flattened_commands_recurses_cleans_tracked_files_and_records_outputs(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    (source_dir / "workflow").mkdir(parents=True)
    (source_dir / "help.md").write_text("help", encoding="utf-8")
    (source_dir / "workflow" / "review.md").write_text("STAGED review", encoding="utf-8")
    (source_dir / "notes.txt").write_text("ignored", encoding="utf-8")

    target_dir = tmp_path / "target"
    command_dir = target_dir / "command"
    command_dir.mkdir(parents=True)
    (command_dir / "gpd-old.md").write_text("old", encoding="utf-8")
    (command_dir / "gpd-user.md").write_text("user", encoding="utf-8")
    _write_manifest(target_dir, {"synthetic_generated_command_files": ["gpd-old.md"]})

    def compact(content: str, context: FlatCommandRenderContext) -> str | None:
        if "STAGED" in content:
            return f"compact:{context.command_name}"
        return None

    def compile_command(content: str, context: FlatCommandRenderContext) -> str:
        return f"{content}\ncompiled:{context.path_prefix}"

    def render(content: str, context: FlatCommandRenderContext) -> str:
        return f"{context.runtime}:{context.dest_name}:{content}"

    managed: set[str] = set()
    count = copy_flattened_commands(
        source_dir,
        command_dir,
        _policy(),
        path_prefix="~/target/",
        managed_command_files=managed,
        render_command=render,
        compact_command=compact,
        compile_command=compile_command,
    )

    assert count == 2
    assert managed == {"gpd-help.md", "gpd-workflow-review.md"}
    assert not (command_dir / "gpd-old.md").exists()
    assert (command_dir / "gpd-user.md").read_text(encoding="utf-8") == "user"
    assert (command_dir / "gpd-help.md").read_text(encoding="utf-8") == (
        "synthetic:gpd-help.md:help\ncompiled:~/target/"
    )
    assert (command_dir / "gpd-workflow-review.md").read_text(encoding="utf-8") == (
        "synthetic:gpd-workflow-review.md:compact:workflow-review\ncompiled:~/target/"
    )
