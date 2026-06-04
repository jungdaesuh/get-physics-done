"""Guardrails for the checked-in repository graph README."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from gpd.registry import LOCAL_CLI_BRIDGE_WORKFLOW_EXEMPT_COMMANDS
from scripts.generated_region_support import marker_start_counts
from scripts.repo_graph_contract import (
    EXCLUDED_GRAPH_DIRS,
    GENERATED_ON_END,
    GENERATED_ON_START,
    GRAPH_SCOPE_LABELS,
    GRAPH_SCOPE_SPECS,
    PROMPT_STEM_INVENTORY_END,
    PROMPT_STEM_INVENTORY_START,
    REPO_GRAPH_BLOCK_IDS,
    REPO_GRAPH_REGION_SPEC,
    REPO_ROOT,
    REQUIRED_EDGES_END,
    REQUIRED_EDGES_START,
    REQUIRED_REPO_GRAPH_EDGES,
    SAME_STEM_COMMAND_WORKFLOW_END,
    SAME_STEM_COMMAND_WORKFLOW_START,
    SCOPE_END,
    SCOPE_START,
    GraphEdgeSpec,
    _is_excluded_path,
    build_contract,
    canonical_scope_label,
    contract_prompt_stem_inventory,
    expected_scope_counts,
    graph_has_edge,
    graph_has_edge_containing,
    iter_runtime_descriptors,
    live_repo_file_count,
    load_contract,
    parse_scope_count,
    prompt_stem_inventory,
    read_graph_text,
    render_generated_on_block,
    render_prompt_stem_inventory_block,
    render_required_edges_block,
    render_same_stem_command_workflow_block,
    render_scope_block,
    sync_readme_text,
    untracked_graph_scope_files,
)
from scripts.sync_repo_graph_contract import check_generated_artifacts


def test_graph_same_stem_command_workflow_inventory_matches_tree() -> None:
    graph = read_graph_text()
    match = re.search(
        r"src/gpd/commands/\{([^}]*)\}\.md -> src/gpd/specs/workflows/\{same stems\}\.md",
        graph,
    )
    assert match is not None, "Missing same-stem command/workflow edge inventory"

    graph_stems = [stem.strip() for stem in match.group(1).split(",") if stem.strip()]
    actual_stems = list(prompt_stem_inventory()["same_stems"])

    assert graph_stems == actual_stems


def test_workflow_only_and_command_only_prompt_inventory_is_explicit() -> None:
    live_inventory = prompt_stem_inventory()
    contract_inventory = contract_prompt_stem_inventory(load_contract())

    assert contract_inventory == live_inventory
    assert contract_inventory["command_only_stems"] == tuple(sorted(LOCAL_CLI_BRIDGE_WORKFLOW_EXEMPT_COMMANDS))


def test_graph_same_stem_inventory_ignores_untracked_matching_files(tmp_path: Path) -> None:
    tmp_root = tmp_path / "repo"
    commands_dir = tmp_root / "src" / "gpd" / "commands"
    workflows_dir = tmp_root / "src" / "gpd" / "specs" / "workflows"
    commands_dir.mkdir(parents=True)
    workflows_dir.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=tmp_root, check=True, capture_output=True, text=True)

    for directory in (commands_dir, workflows_dir):
        (directory / "tracked.md").write_text("tracked\n", encoding="utf-8")
        (directory / "scratch.md").write_text("untracked\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "src/gpd/commands/tracked.md", "src/gpd/specs/workflows/tracked.md"],
        cwd=tmp_root,
        check=True,
        capture_output=True,
        text=True,
    )

    block = render_same_stem_command_workflow_block(tmp_root)

    assert "{tracked}" in block
    assert "scratch" not in block


def _required_edge_id(edge: GraphEdgeSpec) -> str:
    return f"{edge.source} -> {edge.target}"


@pytest.mark.parametrize("edge", REQUIRED_REPO_GRAPH_EDGES, ids=_required_edge_id)
def test_graph_captures_required_high_value_edges(edge: GraphEdgeSpec) -> None:
    graph = read_graph_text()

    assert graph_has_edge(edge.source, edge.target, graph)


def test_graph_rejects_retired_ci_action_versions() -> None:
    graph = read_graph_text()

    assert not graph_has_edge(".github/workflows/test.yml", "actions/checkout@v5", graph)
    assert not graph_has_edge(".github/workflows/test.yml", "actions/setup-node@v5", graph)


def test_graph_edge_matching_expands_braces_without_substring_matches() -> None:
    graph = "\n".join(
        (
            "- `src/{alpha,beta}.py -> tests/{alpha,beta}.py`",
            "- `src/long-runtime-name.py -> tests/long-runtime-name.py`",
        )
    )

    assert graph_has_edge("src/alpha.py", "tests/beta.py", graph)
    assert graph_has_edge("src/beta.py", "tests/alpha.py", graph)
    assert not graph_has_edge("src/alpha.py", "tests/bet.py", graph)
    assert not graph_has_edge("src/long-runtime.py", "tests/long-runtime.py", graph)
    assert graph_has_edge_containing("long-runtime", "long-runtime", graph)


def test_graph_does_not_claim_notify_adapter_wiring() -> None:
    graph = read_graph_text()

    assert not graph_has_edge("src/gpd/hooks/notify.py", "src/gpd/adapters/__init__.py", graph)


def test_graph_keeps_state_runtime_out_of_checkpoint_sync_edges() -> None:
    graph = read_graph_text()

    assert not graph_has_edge("src/gpd/core/state.py", "src/gpd/core/checkpoints.py::sync_phase_checkpoints", graph)


def test_graph_contract_scope_counts_match_live_inventory() -> None:
    expected = expected_scope_counts()

    mismatches = [
        f"{label}: graph={parse_scope_count(label)} live={count}"
        for label, count in expected.items()
        if parse_scope_count(label) != count
    ]

    assert not mismatches, "Graph scope counts are stale:\n" + "\n".join(mismatches)
    assert load_contract()["scope_counts"] == expected
    assert GRAPH_SCOPE_LABELS == tuple(spec.label for spec in GRAPH_SCOPE_SPECS)
    for label in GRAPH_SCOPE_LABELS:
        assert canonical_scope_label(label) == label
        assert canonical_scope_label(label.strip("`")) == label


def test_graph_readme_generated_blocks_match_contract() -> None:
    contract = load_contract()
    graph_text = read_graph_text()

    assert marker_start_counts(graph_text, spec=REPO_GRAPH_REGION_SPEC) == dict.fromkeys(REPO_GRAPH_BLOCK_IDS, 1)
    assert sync_readme_text(graph_text, contract) == graph_text


def test_graph_readme_inventory_rejects_missing_and_duplicate_generated_blocks() -> None:
    contract = load_contract()
    graph_text = read_graph_text()
    start = graph_text.index(GENERATED_ON_START)
    end = graph_text.index(GENERATED_ON_END, start) + len(GENERATED_ON_END)
    generated_on_region = graph_text[start:end]

    with pytest.raises(ValueError, match="missing 1 expected marker\\(s\\) for 'generated-on'"):
        sync_readme_text(graph_text[:start] + graph_text[end:], contract)

    with pytest.raises(ValueError, match="duplicate marker for 'generated-on' is not allowed"):
        sync_readme_text(graph_text + "\n" + generated_on_region, contract)


def test_graph_check_detects_stale_generated_contract_without_mutation(tmp_path: Path) -> None:
    graph_path = tmp_path / "README.md"
    contract_path = tmp_path / "repo_graph_contract.json"
    contract = load_contract()
    stale_contract = dict(contract)
    stale_contract["scope_counts"] = {label: int(value) + 1 for label, value in contract["scope_counts"].items()}
    graph_path.write_text(read_graph_text(), encoding="utf-8")
    contract_path.write_text(json.dumps(stale_contract, indent=2) + "\n", encoding="utf-8")

    before_graph = graph_path.read_text(encoding="utf-8")
    before_contract = contract_path.read_text(encoding="utf-8")

    diffs = check_generated_artifacts(graph_path=graph_path, contract_path=contract_path)

    assert any("repo_graph_contract.json" in diff for diff in diffs)
    assert graph_path.read_text(encoding="utf-8") == before_graph
    assert contract_path.read_text(encoding="utf-8") == before_contract


def test_graph_check_detects_untracked_scope_files_without_mutation(tmp_path: Path) -> None:
    tmp_root = tmp_path / "repo"
    tmp_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=tmp_root, check=True, capture_output=True, text=True)

    tracked_file = tmp_root / "src" / "gpd" / "commands" / "tracked.md"
    tracked_file.parent.mkdir(parents=True)
    tracked_file.write_text("tracked\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", tracked_file.relative_to(tmp_root).as_posix()],
        cwd=tmp_root,
        check=True,
        capture_output=True,
        text=True,
    )

    graph_path = tmp_path / "README.md"
    contract_path = tmp_path / "repo_graph_contract.json"
    contract = build_contract(tmp_root)
    graph_template = "\n".join(
        (
            GENERATED_ON_START,
            GENERATED_ON_END,
            SCOPE_START,
            SCOPE_END,
            PROMPT_STEM_INVENTORY_START,
            PROMPT_STEM_INVENTORY_END,
            SAME_STEM_COMMAND_WORKFLOW_START,
            SAME_STEM_COMMAND_WORKFLOW_END,
            REQUIRED_EDGES_START,
            REQUIRED_EDGES_END,
            "",
        )
    )
    graph_path.write_text(sync_readme_text(graph_template, contract, tmp_root), encoding="utf-8")
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")

    untracked_file = tmp_root / "src" / "gpd" / "commands" / "untracked.md"
    untracked_file.write_text("untracked\n", encoding="utf-8")
    before_graph = graph_path.read_text(encoding="utf-8")
    before_contract = contract_path.read_text(encoding="utf-8")

    diffs = check_generated_artifacts(graph_path=graph_path, contract_path=contract_path, repo_root=tmp_root)

    assert untracked_graph_scope_files(tmp_root) == (Path("src/gpd/commands/untracked.md"),)
    assert any(
        "Untracked repo graph scoped files" in diff and "src/gpd/commands/untracked.md" in diff for diff in diffs
    )
    assert graph_path.read_text(encoding="utf-8") == before_graph
    assert contract_path.read_text(encoding="utf-8") == before_contract


def test_graph_sync_repairs_stale_marked_blocks() -> None:
    original = read_graph_text()
    contract = load_contract()
    stale_contract = dict(contract)
    stale_contract["scope_counts"] = {label: int(value) + 1 for label, value in contract["scope_counts"].items()}

    stale = original.replace(
        render_generated_on_block(contract),
        "\n".join((GENERATED_ON_START, "Generated from an outdated contract.", GENERATED_ON_END)),
        1,
    )
    stale = stale.replace(
        render_scope_block(contract),
        render_scope_block(stale_contract),
        1,
    )
    stale = stale.replace(
        render_prompt_stem_inventory_block(contract),
        "\n".join(
            (
                PROMPT_STEM_INVENTORY_START,
                "- Workflow-only prompt stems: `stale`",
                PROMPT_STEM_INVENTORY_END,
            )
        ),
        1,
    )
    stale = stale.replace(
        render_same_stem_command_workflow_block(),
        "\n".join(
            (
                SAME_STEM_COMMAND_WORKFLOW_START,
                "- `src/gpd/commands/old.md -> src/gpd/specs/workflows/old.md`",
                SAME_STEM_COMMAND_WORKFLOW_END,
            )
        ),
        1,
    )
    stale = stale.replace(
        render_required_edges_block(contract),
        "\n".join(
            (
                REQUIRED_EDGES_START,
                "- `stale.py -> stale-target.py`",
                REQUIRED_EDGES_END,
            )
        ),
        1,
    )

    repaired = sync_readme_text(stale, contract)

    assert repaired == original


def test_live_repo_file_count_ignores_worktree_artifacts(tmp_path: Path) -> None:
    tmp_root = tmp_path / "repo"
    tmp_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=tmp_root, check=True, capture_output=True, text=True)

    tracked_file = tmp_root / "tracked.txt"
    tracked_file.write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", tracked_file.name], cwd=tmp_root, check=True, capture_output=True, text=True)

    untracked_file = tmp_root / "docs" / "scratch.md"
    untracked_file.parent.mkdir(parents=True, exist_ok=True)
    untracked_file.write_text("untracked\n", encoding="utf-8")

    assert live_repo_file_count(tmp_root) == 1

    tracked_file.unlink()
    assert live_repo_file_count(tmp_root) == 0

    excluded_sentinels: list[Path] = []
    for excluded_name in EXCLUDED_GRAPH_DIRS:
        if excluded_name == ".git":
            continue
        if excluded_name == ".mcp.json":
            path = tmp_root / excluded_name
        else:
            path = tmp_root / excluded_name / "sentinel.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime mirror sentinel\n", encoding="utf-8")
        excluded_sentinels.append(path)

    subprocess.run(
        ["git", "add", *[path.relative_to(tmp_root).as_posix() for path in excluded_sentinels]],
        cwd=tmp_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert live_repo_file_count(tmp_root) == 0


def test_graph_exclusions_apply_only_at_repo_root() -> None:
    runtime_config_dirs = {descriptor.config_dir_name for descriptor in iter_runtime_descriptors()}

    assert _is_excluded_path(Path("GPD/state.json"))
    assert _is_excluded_path(Path("dist/wheel.whl"))
    assert not _is_excluded_path(Path("src/gpd/GPD/state.py"))
    assert not _is_excluded_path(Path("src/gpd/dist/build.py"))
    assert runtime_config_dirs <= set(EXCLUDED_GRAPH_DIRS)
    for config_dir_name in runtime_config_dirs:
        assert _is_excluded_path(Path(config_dir_name) / "config.toml")
        assert not _is_excluded_path(Path("docs") / config_dir_name / "reference.md")


def test_graph_test_file_references_exist() -> None:
    missing = sorted(
        {ref for ref in re.findall(r"tests/[A-Za-z0-9_./-]+\.py", read_graph_text()) if not (REPO_ROOT / ref).is_file()}
    )

    assert missing == []


def test_graph_docs_file_references_exist() -> None:
    missing = sorted(
        {ref for ref in re.findall(r"docs/[A-Za-z0-9_./-]+\.md", read_graph_text()) if not (REPO_ROOT / ref).is_file()}
    )

    assert missing == []
