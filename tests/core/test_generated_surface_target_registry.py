"""Inventory guardrails for generated public/help/repo-graph surfaces."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

from gpd.core.public_surface_renderer import (
    public_surface_context,
    runtime_doc_filename,
    runtime_quickstart_block_id,
)
from scripts.render_help_surface import (
    HELP_DETAIL_REFERENCE_PATH,
    HELP_WORKFLOW_PATH,
    help_detail_surface_block_ids,
    help_surface_block_ids,
)
from scripts.render_public_surface import default_target_contracts
from scripts.repo_graph_contract import (
    CONTRACT_PATH,
    GRAPH_PATH,
    REPO_GRAPH_BLOCK_IDS,
    REPO_ROOT,
    load_contract,
)


def _relative_path_key(path: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.relative_to(REPO_ROOT).as_posix()
    return candidate.as_posix()


def _public_target_inventory() -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    return tuple(
        (
            _relative_path_key(target.path),
            target.required_blocks,
            target.allowed_duplicate_blocks,
        )
        for target in default_target_contracts()
    )


def test_current_public_surface_generated_target_inventory_is_explicit() -> None:
    context = public_surface_context()
    os_doc_blocks = (
        "runtime-doc-links",
        "os-install-matrix",
        "supported-runtimes-table",
        "os-next-steps-table",
        "recovery-note",
    )
    expected_runtime_docs = tuple(
        (
            f"docs/{runtime_doc_filename(surface)}",
            (runtime_quickstart_block_id(surface),),
            (),
        )
        for surface in context.runtime_surfaces
    )

    assert _public_target_inventory() == (
        (
            "README.md",
            (
                "terminal-runtime-bridge",
                "beginner-startup-ladder",
                "recovery-note",
                "local-cli-bridge-summary",
                "supported-runtimes-table",
                "recovery-note",
                "local-cli-bridge-summary",
            ),
            ("recovery-note", "local-cli-bridge-summary"),
        ),
        (
            "docs/README.md",
            (
                "beginner-preflight",
                "beginner-caveats",
                "beginner-startup-ladder",
                "recovery-note",
                "terminal-runtime-bridge",
                "post-start-settings",
            ),
            (),
        ),
        ("docs/macos.md", os_doc_blocks, ()),
        ("docs/linux.md", os_doc_blocks, ()),
        ("docs/windows.md", os_doc_blocks, ()),
        *expected_runtime_docs,
        (
            "src/gpd/specs/workflows/help.md",
            ("local-cli-bridge-summary", "recovery-note"),
            (),
        ),
    )


def test_current_help_surface_generated_target_inventory_is_explicit() -> None:
    assert _relative_path_key(HELP_WORKFLOW_PATH) == "src/gpd/specs/workflows/help.md"
    assert help_surface_block_ids() == (
        "quick-start",
        "command-index",
        "detailed-command-reference",
        "default",
    )
    assert _relative_path_key(HELP_DETAIL_REFERENCE_PATH) == (
        "src/gpd/specs/references/help/detailed-command-reference.md"
    )
    assert help_detail_surface_block_ids() == ("detailed-command-reference",)


def test_current_repo_graph_generated_target_inventory_is_explicit() -> None:
    assert _relative_path_key(GRAPH_PATH) == "tests/README.md"
    assert _relative_path_key(CONTRACT_PATH) == "tests/repo_graph_contract.json"
    assert REPO_GRAPH_BLOCK_IDS == (
        "generated-on",
        "scope",
        "prompt-stem-inventory",
        "same-stem-command-workflow",
        "required-edges",
    )


def test_future_generated_surface_target_registry_matches_current_inventory() -> None:
    if importlib.util.find_spec("scripts.generated_surface_targets") is None:
        pytest.skip("Phase 9 generated-surface target registry has not landed yet")

    target_registry = importlib.import_module("scripts.generated_surface_targets")
    required_api = (
        "GeneratedRegionTarget",
        "GeneratedTextTarget",
        "public_surface_region_targets",
        "help_surface_region_targets",
        "repo_graph_region_targets",
        "repo_graph_text_targets",
    )
    missing = [name for name in required_api if not hasattr(target_registry, name)]
    assert missing == []

    public_targets = target_registry.public_surface_region_targets()
    assert (
        tuple(
            (
                _relative_path_key(target.path),
                tuple(target.required_blocks),
                tuple(target.allowed_duplicate_blocks),
            )
            for target in public_targets
        )
        == _public_target_inventory()
    )

    help_targets = target_registry.help_surface_region_targets()
    assert tuple((_relative_path_key(target.path), tuple(target.required_blocks)) for target in help_targets) == (
        ("src/gpd/specs/workflows/help.md", help_surface_block_ids()),
        (
            "src/gpd/specs/references/help/detailed-command-reference.md",
            help_detail_surface_block_ids(),
        ),
    )

    contract = load_contract()
    repo_region_targets = target_registry.repo_graph_region_targets(contract)
    repo_text_targets = target_registry.repo_graph_text_targets(contract)
    assert tuple(
        (_relative_path_key(target.path), tuple(target.required_blocks)) for target in repo_region_targets
    ) == (("tests/README.md", REPO_GRAPH_BLOCK_IDS),)
    assert tuple(_relative_path_key(target.path) for target in repo_text_targets) == ("tests/repo_graph_contract.json",)
