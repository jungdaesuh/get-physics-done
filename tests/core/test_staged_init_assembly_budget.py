"""Budget contracts for the optional staged-init assembly helper."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGED_INIT_ASSEMBLY_PATH = REPO_ROOT / "src" / "gpd" / "core" / "staged_init_assembly.py"
STAGED_INIT_ASSEMBLY_LOC_CAP = 170
FORBIDDEN_IMPORT_PREFIXES = (
    "gpd.adapters",
    "gpd.cli",
    "gpd.core.context",
    "gpd.core.manuscript_artifacts",
    "gpd.core.prompt_diagnostics",
    "gpd.core.publication_runtime",
    "gpd.core.stage_prompt_diagnostics",
    "gpd.registry",
)


def _source_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _module_imports(tree: ast.AST) -> tuple[str, ...]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return tuple(imports)


def _matches_forbidden_prefix(module_name: str) -> bool:
    return any(
        module_name == forbidden_prefix or module_name.startswith(f"{forbidden_prefix}.")
        for forbidden_prefix in FORBIDDEN_IMPORT_PREFIXES
    )


def _is_workflow_id_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "workflow_id"


def _workflow_id_branch_lines(tree: ast.AST) -> tuple[int, ...]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(operator, (ast.Eq, ast.NotEq)) for operator in node.ops):
            continue
        compared_nodes: Iterable[ast.AST] = (node.left, *node.comparators)
        if any(_is_workflow_id_name(compared_node) for compared_node in compared_nodes):
            lines.append(getattr(node, "lineno", 0))
    return tuple(lines)


def test_staged_init_assembly_helper_stays_small_if_present() -> None:
    if not STAGED_INIT_ASSEMBLY_PATH.exists():
        return

    assert _source_line_count(STAGED_INIT_ASSEMBLY_PATH) <= STAGED_INIT_ASSEMBLY_LOC_CAP


def test_staged_init_assembly_helper_keeps_core_boundaries_if_present() -> None:
    if not STAGED_INIT_ASSEMBLY_PATH.exists():
        return

    tree = ast.parse(STAGED_INIT_ASSEMBLY_PATH.read_text(encoding="utf-8"))
    forbidden_imports = sorted(
        module_name for module_name in _module_imports(tree) if _matches_forbidden_prefix(module_name)
    )

    assert forbidden_imports == []
    assert _workflow_id_branch_lines(tree) == ()
