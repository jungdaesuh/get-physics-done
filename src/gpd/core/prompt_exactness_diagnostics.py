"""Prompt-test exactness diagnostics for prompt surface reports."""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, NamedTuple, cast

from gpd.core import prompt_markdown_scan as _prompt_markdown_scan
from gpd.core.prompt_exactness_migration import (
    bounded_exactness_migration as _bounded_exactness_migration,
)
from gpd.core.prompt_exactness_migration import (
    exactness_migration_diagnostics as _exactness_migration_diagnostics,
)
from gpd.core.prompt_exactness_migration import (
    exactness_migration_file_row as _exactness_migration_file_row,
)

_relative_path = _prompt_markdown_scan.relative_path

_MACHINE_CONTRACT_RE = re.compile(
    r"(?:"
    r"\b[A-Za-z0-9_.{}$-]+/[A-Za-z0-9_./{}$-]+|"
    r"\b[A-Za-z0-9_.-]+\.(?:md|json|ya?ml|toml|tex|pdf|py)\b|"
    r"--[a-z0-9][a-z0-9-]*\b|"
    r"\$gpd-[a-z0-9-]+|"
    r"\bgpd(?:[: -][a-z0-9-]+|_return| --raw)\b|"
    r"\b(?:schema_version|frontmatter|gpd_return|contract_results|files_written|next_actions|project_contract)\b|"
    r"\b[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)+\b|"
    r"@\{GPD_INSTALL_DIR\}|"
    r"<!--\s*@\s*include\b|"
    r"<[A-Za-z][A-Za-z0-9_-]*(?:\s+[^>\n]*)?>"
    r")",
    re.IGNORECASE,
)
_SCHEMA_KEY_LITERAL_RE = re.compile(
    r"^\s*(?:schema_version|gpd_return|status|summary|files_written|issues|next_actions|contract_results|"
    r"project_contract|claims|references|artifacts|path|kind|id|name|description|stage|round|source|target|"
    r"verified_at):(?:\s|$)",
    re.IGNORECASE,
)
_FIELD_PATH_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)+\b")
_STRUCTURED_PROMPT_MARKER_RE = re.compile(
    r"^\s*(?:"
    r"<[A-Za-z][A-Za-z0-9_-]*(?:\s+[^>\n]*)?>|"
    r"</[A-Za-z][A-Za-z0-9_-]*>|"
    r"<!--\s*@\s*include\b.*-->"
    r")\s*$"
)
_PUBLIC_UX_LITERAL_RE = re.compile(
    r"(?:"
    r"^\s*#+\s*(?:Command Index|Choose this runtime if|Quick Start|Install|Uninstall|Warnings)\b|"
    r"^\s*(?:Command Index|Quick Start|Choose this runtime if|Available commands|Usage|Examples?)\s*$|"
    r"\[Y/n/e\]|"
    r"Start a fresh context window, then run|"
    r"Runtime readiness preflight|"
    r"No GPD project found|"
    r"Choose one:"
    r")",
    re.IGNORECASE,
)
_PUBLIC_UX_TEST_PATH_RE = re.compile(
    r"(?:^|/)tests/(?:core/)?(?:"
    r"test_cli(?:_commands)?|"
    r"test_.*(?:help|start|tour|onboarding|install|uninstall|diagnostics|checkpoint)"
    r")\.py$"
)
_SHORT_MACHINE_CONTRACT_LITERALS = frozenset(
    (
        "must_haves",
        "verification_inputs",
        "peer_review_stage",
        "execution_segment",
        "schema_version",
        "frontmatter",
        "gpd_return",
    )
)
_SHORT_PUBLIC_UX_LITERALS = frozenset({"Quick Start", "[Y/n/e]"})
_EXACT_ASSERTION_EXAMPLES_PER_CATEGORY = 5
EXACT_ASSERTION_THRESHOLDS: dict[str, dict[str, int]] = {
    "brittle_prose_assertions": {"warn": 1100, "fail": 1150},
    "max_brittle_prose_assertions_per_file": {"warn": 50, "fail": 75},
    "max_brittle_prose_assertions_in_test_prompt_wiring": {"warn": 240, "fail": 260},
    "public_ux_exact_assertions": {"warn": 700, "fail": 750},
    "machine_contract_exact_assertions": {"warn": 6000, "fail": 6200},
    "exact_assertion_count": {"warn": 7700, "fail": 7900},
}
_TAXONOMY_HELPER_USAGE_SCHEMA_VERSION = "taxonomy_helper_usage.v1"
_TAXONOMY_HELPER_NAMES = tuple(
    "assert_fragments assert_prompt_contracts forbidden_duplicate fragment_count machine_exact public_exact "
    "semantic_anchor semantic_concept".split()
)
_TAXONOMY_HELPER_ALIASES = {"_assert_prompt_contracts": "assert_prompt_contracts"}
_SEMANTIC_TAXONOMY_HELPER_NAMES = frozenset(("semantic_anchor", "semantic_concept"))
_SEMANTIC_HELPER_LONG_PROSE_MIN_WORDS = 8
_SEMANTIC_HELPER_LONG_PROSE_EXAMPLES_PER_FILE = 5

ExactAssertionCategory = Literal["machine_contract", "public_ux", "brittle_prose"]
ExactAssertionPolarity = Literal["required", "forbidden", "counted", "indexed"]
ExactAssertionShape = Literal["assert_contains", "assert_not_contains", "count", "index"]
ExactAssertionSeverity = Literal["info", "warn", "high"]


class _ExactPromptAssertion(NamedTuple):
    literal: str
    line: int
    assertion_shape: ExactAssertionShape
    polarity: ExactAssertionPolarity


def scan_exact_assertion_diagnostics(repo_root: Path) -> dict[str, object]:
    tests_root = repo_root / "tests"
    if not tests_root.is_dir():
        return empty_exact_assertion_diagnostics()

    file_rows: list[dict[str, object]] = []
    taxonomy_usage_rows: list[dict[str, object]] = []
    migration_rows: list[dict[str, object]] = []
    files_scanned = 0
    for path in sorted(tests_root.rglob("*.py")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue

        files_scanned += 1
        relative_path = _relative_path(path, repo_root)
        taxonomy_usage = _taxonomy_helper_usage_for_tree(tree, path=relative_path)
        if taxonomy_usage:
            taxonomy_usage_rows.append(taxonomy_usage)
        assertions = _prompt_exact_assertions(tree)
        if assertions:
            file_rows.append(_file_row(relative_path, assertions))
        if assertions or taxonomy_usage:
            migration_rows.append(
                _exactness_migration_file_row(
                    relative_path,
                    [_exact_assertion_to_dict(assertion, path=relative_path) for assertion in assertions],
                    taxonomy_usage,
                    examples_per_category=_EXACT_ASSERTION_EXAMPLES_PER_CATEGORY,
                )
            )

    file_rows.sort(
        key=lambda entry: (
            -cast(int, entry["brittle_prose_assertions"]),
            -cast(float, entry["brittle_prose_density"]),
            -cast(int, entry["exact_assertion_count"]),
            cast(str, entry["path"]),
        )
    )
    return _diagnostics_payload(files_scanned, file_rows, taxonomy_usage_rows, migration_rows)


def empty_exact_assertion_diagnostics() -> dict[str, object]:
    return _diagnostics_payload(0, (), (), ())


def exact_prose_assertion_files_from_diagnostics(
    diagnostics: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    entries: list[Mapping[str, object]] = []
    for row in exact_assertion_file_rows(diagnostics, None):
        examples = cast(Mapping[str, object], row.get("examples", {}))
        sample_literals = [
            str(example.get("literal", ""))
            for category in ("brittle_prose", "public_ux", "machine_contract")
            for example in cast(Sequence[Mapping[str, object]], examples.get(category, ()))
        ]
        entries.append(
            {
                "path": row.get("path", ""),
                "exact_assertion_count": row.get("exact_assertion_count", 0),
                "prose_contract_assertions": cast(int, row.get("public_ux_exact_assertions", 0))
                + cast(int, row.get("brittle_prose_assertions", 0)),
                "machine_contract_assertions": row.get("machine_contract_exact_assertions", 0),
                "public_ux_exact_assertions": row.get("public_ux_exact_assertions", 0),
                "brittle_prose_assertions": row.get("brittle_prose_assertions", 0),
                "examples": tuple(sample_literals[:5]),
            }
        )
    return tuple(
        sorted(
            entries,
            key=lambda entry: (
                -cast(int, entry["prose_contract_assertions"]),
                -cast(int, entry["exact_assertion_count"]),
                cast(str, entry["path"]),
            ),
        )
    )


def exact_assertion_file_rows(
    diagnostics: Mapping[str, object],
    top: int | None,
) -> tuple[Mapping[str, object], ...]:
    files = tuple(cast(Sequence[Mapping[str, object]], diagnostics.get("files", ())))
    if top is None or top <= 0:
        return files
    return files[:top]


def bounded_exact_assertion_diagnostics(
    diagnostics: Mapping[str, object],
    top: int | None,
) -> Mapping[str, object]:
    limit = _top_limit(top)
    if limit is None:
        return diagnostics

    payload = dict(diagnostics)
    payload["files"] = [dict(row) for row in exact_assertion_file_rows(diagnostics, top)]
    taxonomy_helper_usage = diagnostics.get("taxonomy_helper_usage")
    if isinstance(taxonomy_helper_usage, Mapping):
        payload["taxonomy_helper_usage"] = _bounded_taxonomy_helper_usage(taxonomy_helper_usage, top)
    migration = diagnostics.get("migration")
    if isinstance(migration, Mapping):
        payload["migration"] = _bounded_exactness_migration(migration, top)
    return payload


def _diagnostics_payload(
    files_scanned: int,
    file_rows: Sequence[Mapping[str, object]],
    taxonomy_usage_rows: Sequence[Mapping[str, object]],
    migration_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "exact_assertions.v1",
        "totals": _exact_assertion_totals(files_scanned, file_rows),
        "thresholds": EXACT_ASSERTION_THRESHOLDS,
        "files": list(file_rows),
        "taxonomy_helper_usage": _taxonomy_helper_usage_diagnostics(files_scanned, taxonomy_usage_rows),
        "migration": _exactness_migration_diagnostics(migration_rows),
    }


def _file_row(path: str, assertions: Sequence[_ExactPromptAssertion]) -> dict[str, object]:
    classified = [_exact_assertion_to_dict(assertion, path=path) for assertion in assertions]
    by_category = {
        category: [entry for entry in classified if entry["category"] == category]
        for category in ("machine_contract", "public_ux", "brittle_prose")
    }
    exact_count = len(classified)
    brittle_count = len(by_category["brittle_prose"])
    brittle_density = brittle_count / exact_count if exact_count else 0.0
    return {
        "path": path,
        "exact_assertion_count": exact_count,
        "machine_contract_exact_assertions": len(by_category["machine_contract"]),
        "public_ux_exact_assertions": len(by_category["public_ux"]),
        "brittle_prose_assertions": brittle_count,
        "brittle_prose_density": round(brittle_density, 6),
        "severity": _exact_assertion_file_severity(brittle_count, brittle_density),
        "examples": {
            category: entries[:_EXACT_ASSERTION_EXAMPLES_PER_CATEGORY] for category, entries in by_category.items()
        },
    }


def _exact_assertion_totals(files_scanned: int, file_rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    return {
        "files_scanned": files_scanned,
        "exact_assertion_file_count": len(file_rows),
        "exact_assertion_count": sum(cast(int, row["exact_assertion_count"]) for row in file_rows),
        "machine_contract_exact_assertions": sum(
            cast(int, row["machine_contract_exact_assertions"]) for row in file_rows
        ),
        "public_ux_exact_assertions": sum(cast(int, row["public_ux_exact_assertions"]) for row in file_rows),
        "brittle_prose_assertions": sum(cast(int, row["brittle_prose_assertions"]) for row in file_rows),
        "brittle_prose_file_count": sum(1 for row in file_rows if cast(int, row["brittle_prose_assertions"]) > 0),
    }


def _taxonomy_helper_usage_for_tree(tree: ast.AST, *, path: str) -> dict[str, object] | None:
    helper_counts: dict[str, int] = dict.fromkeys(_TAXONOMY_HELPER_NAMES, 0)
    semantic_fragment_count = 0
    long_prose_examples: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (helper_name := _taxonomy_helper_name(node.func)) is not None:
            helper_counts[helper_name] += 1
            if helper_name in _SEMANTIC_TAXONOMY_HELPER_NAMES:
                for fragment in _semantic_helper_literal_fragments(node, helper_name=helper_name):
                    semantic_fragment_count += 1
                    if _is_long_semantic_helper_prose(fragment["literal"]):
                        fragment["reason"] = "long_semantic_helper_prose_fragment"
                        long_prose_examples.append(fragment)

    used_helpers = {helper_name: count for helper_name, count in helper_counts.items() if count}
    if not used_helpers:
        return None
    semantic_helper_call_count = sum(
        used_helpers.get(helper_name, 0) for helper_name in _SEMANTIC_TAXONOMY_HELPER_NAMES
    )
    return {
        "path": path,
        "helper_call_count": sum(used_helpers.values()),
        "helpers": used_helpers,
        "semantic_helper_call_count": semantic_helper_call_count,
        "semantic_helper_literal_fragment_count": semantic_fragment_count,
        "semantic_helper_long_prose_fragment_count": len(long_prose_examples),
        "semantic_helper_long_prose_examples": long_prose_examples[:_SEMANTIC_HELPER_LONG_PROSE_EXAMPLES_PER_FILE],
    }


def _taxonomy_helper_name(node: ast.AST) -> str | None:
    raw_name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
    helper_name = _TAXONOMY_HELPER_ALIASES.get(raw_name or "", raw_name or "")
    return helper_name if helper_name in _TAXONOMY_HELPER_NAMES else None


def _taxonomy_helper_usage_diagnostics(
    files_scanned: int,
    file_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    sorted_rows = tuple(
        sorted(file_rows, key=lambda row: (-cast(int, row["helper_call_count"]), cast(str, row["path"])))
    )
    totals: dict[str, int] = {
        "files_scanned": files_scanned,
        "taxonomy_helper_file_count": len(sorted_rows),
        "taxonomy_helper_call_count": sum(cast(int, row["helper_call_count"]) for row in sorted_rows),
        "semantic_helper_literal_fragment_count": sum(
            cast(int, row.get("semantic_helper_literal_fragment_count", 0)) for row in sorted_rows
        ),
        "semantic_helper_long_prose_file_count": sum(
            1 for row in sorted_rows if cast(int, row.get("semantic_helper_long_prose_fragment_count", 0)) > 0
        ),
        "semantic_helper_long_prose_fragment_count": sum(
            cast(int, row.get("semantic_helper_long_prose_fragment_count", 0)) for row in sorted_rows
        ),
    }
    for helper_name in _TAXONOMY_HELPER_NAMES:
        totals[helper_name] = sum(
            cast(int, cast(Mapping[str, object], row.get("helpers", {})).get(helper_name, 0)) for row in sorted_rows
        )
    return {
        "schema_version": _TAXONOMY_HELPER_USAGE_SCHEMA_VERSION,
        "totals": totals,
        "files": [dict(row) for row in sorted_rows],
    }


def _semantic_helper_literal_fragments(node: ast.Call, *, helper_name: str) -> tuple[dict[str, object], ...]:
    if helper_name == "semantic_anchor":
        fragment_nodes = _semantic_anchor_fragment_nodes(node)
    elif helper_name == "semantic_concept":
        fragment_nodes = _semantic_concept_fragment_nodes(node)
    else:
        return ()

    fragments: list[dict[str, object]] = []
    for field, fragment_node in fragment_nodes:
        for literal in _literal_fragment_strings(fragment_node):
            fragments.append(
                {
                    "line": getattr(fragment_node, "lineno", getattr(node, "lineno", 0)),
                    "helper": helper_name,
                    "field": field,
                    "literal": literal,
                    "word_count": _english_word_count(literal),
                }
            )
    return tuple(fragments)


def _semantic_anchor_fragment_nodes(node: ast.Call) -> tuple[tuple[str, ast.AST], ...]:
    fragment_nodes: list[tuple[str, ast.AST]] = []
    if len(node.args) >= 2:
        fragment_nodes.append(("fragments", node.args[1]))
    fragment_nodes.extend(("fragments", keyword.value) for keyword in node.keywords if keyword.arg == "fragments")
    return tuple(fragment_nodes)


def _semantic_concept_fragment_nodes(node: ast.Call) -> tuple[tuple[str, ast.AST], ...]:
    fragment_nodes: list[tuple[str, ast.AST]] = []
    for keyword in node.keywords:
        field = keyword.arg
        if field is None or field not in {"required", "forbidden"}:
            continue
        fragment_nodes.append((field, keyword.value))
    return tuple(fragment_nodes)


def _literal_fragment_strings(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        fragments: list[str] = []
        for item in node.elts:
            fragments.extend(_literal_fragment_strings(item))
        return tuple(fragments)
    return ()


def _is_long_semantic_helper_prose(literal: str) -> bool:
    stripped = literal.strip()
    if not stripped:
        return False
    return _english_word_count(stripped) >= _SEMANTIC_HELPER_LONG_PROSE_MIN_WORDS


def _exact_assertion_to_dict(assertion: _ExactPromptAssertion, *, path: str) -> dict[str, object]:
    category, reason = _classify_exact_assertion(assertion.literal, path=path, polarity=assertion.polarity)
    return {
        "path": path,
        "line": assertion.line,
        "literal": assertion.literal,
        "assertion_shape": assertion.assertion_shape,
        "polarity": assertion.polarity,
        "category": category,
        "reason": reason,
    }


def _exact_assertion_file_severity(
    brittle_prose_assertions: int,
    brittle_prose_density: float,
) -> ExactAssertionSeverity:
    if brittle_prose_assertions >= 50 or (brittle_prose_assertions >= 20 and brittle_prose_density >= 0.45):
        return "high"
    if brittle_prose_assertions >= 20 or (brittle_prose_assertions >= 10 and brittle_prose_density >= 0.30):
        return "warn"
    return "info"


def _prompt_exact_assertions(tree: ast.AST) -> tuple[_ExactPromptAssertion, ...]:
    assertions: list[_ExactPromptAssertion] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            assertions.extend(_assert_exact_assertions(node.test))
        elif isinstance(node, ast.Call):
            assertions.extend(_method_exact_assertions(node))
    return tuple(assertion for assertion in assertions if _is_prompt_literal(assertion.literal))


def _assert_exact_assertions(node: ast.AST) -> tuple[_ExactPromptAssertion, ...]:
    if not isinstance(node, ast.Compare):
        return ()

    assertions: list[_ExactPromptAssertion] = []
    for op in node.ops:
        if not isinstance(op, (ast.In, ast.NotIn)):
            continue
        shape: ExactAssertionShape = "assert_not_contains" if isinstance(op, ast.NotIn) else "assert_contains"
        polarity: ExactAssertionPolarity = "forbidden" if isinstance(op, ast.NotIn) else "required"
        for literal in _string_constants((node.left, *node.comparators)):
            assertions.append(
                _ExactPromptAssertion(
                    literal=literal,
                    line=getattr(node, "lineno", 0),
                    assertion_shape=shape,
                    polarity=polarity,
                )
            )
    return tuple(assertions)


def _method_exact_assertions(node: ast.Call) -> tuple[_ExactPromptAssertion, ...]:
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in {"count", "index"}:
        return ()
    shape = cast(ExactAssertionShape, node.func.attr)
    polarity: ExactAssertionPolarity = "counted" if node.func.attr == "count" else "indexed"
    return tuple(
        _ExactPromptAssertion(
            literal=literal,
            line=getattr(node, "lineno", 0),
            assertion_shape=shape,
            polarity=polarity,
        )
        for literal in _string_constants(node.args[:1])
    )


def _string_constants(nodes: Sequence[ast.AST]) -> tuple[str, ...]:
    return tuple(node.value for node in nodes if isinstance(node, ast.Constant) and isinstance(node.value, str))


def _is_prompt_literal(literal: str) -> bool:
    stripped = literal.strip()
    if len(stripped) < 12:
        return stripped in _SHORT_MACHINE_CONTRACT_LITERALS or stripped in _SHORT_PUBLIC_UX_LITERALS
    if "\n" in stripped:
        return True
    return bool(
        re.search(r"[A-Za-z]{3,}\s+[A-Za-z]{3,}", stripped)
        or _MACHINE_CONTRACT_RE.search(stripped)
        or _SCHEMA_KEY_LITERAL_RE.search(stripped)
        or _PUBLIC_UX_LITERAL_RE.search(stripped)
    )


def _classify_exact_assertion(
    literal: str,
    *,
    path: str,
    polarity: ExactAssertionPolarity,
) -> tuple[ExactAssertionCategory, str]:
    if machine_reason := _machine_contract_exact_reason(literal, polarity=polarity):
        return "machine_contract", machine_reason
    if public_reason := _public_ux_exact_reason(literal, path=path):
        return "public_ux", public_reason
    if _english_word_count(literal) >= 5:
        return "brittle_prose", "long_internal_prompt_prose"
    return "machine_contract", "short_prompt_literal"


def _machine_contract_exact_reason(literal: str, *, polarity: ExactAssertionPolarity) -> str | None:
    stripped = literal.strip()
    if stripped in _SHORT_PUBLIC_UX_LITERALS:
        return None
    if stripped in _SHORT_MACHINE_CONTRACT_LITERALS:
        return "machine_regression_token"
    if _STRUCTURED_PROMPT_MARKER_RE.search(stripped):
        return "structured_prompt_marker"
    if re.search(r"\bgpd\s+--raw\b|\bgpd:[a-z0-9-]+\b|\$gpd-[a-z0-9-]+\b|--[a-z0-9][a-z0-9-]*\b", stripped):
        return "gpd_command_or_flag"
    if re.search(r"\b[A-Za-z0-9_.{}$-]+/[A-Za-z0-9_./{}$-]+", stripped) or re.search(
        r"\b[A-Za-z0-9_.-]+\.(?:md|json|ya?ml|toml|tex|pdf|py)\b",
        stripped,
        re.IGNORECASE,
    ):
        return "path_or_artifact"
    if _FIELD_PATH_RE.search(stripped) or _SCHEMA_KEY_LITERAL_RE.search(stripped):
        return "schema_or_field_path"
    if _MACHINE_CONTRACT_RE.search(stripped):
        return "machine_token"
    if polarity == "forbidden" and any(token in stripped for token in _SHORT_MACHINE_CONTRACT_LITERALS):
        return "forbidden_stale_alias"
    return None


def _public_ux_exact_reason(literal: str, *, path: str) -> str | None:
    stripped = literal.strip()
    if stripped in _SHORT_PUBLIC_UX_LITERALS or _PUBLIC_UX_LITERAL_RE.search(stripped):
        return "public_ux_copy"
    if _PUBLIC_UX_TEST_PATH_RE.search(path) and _english_word_count(stripped) >= 2:
        return "public_ux_surface"
    return None


def _english_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z][A-Za-z'-]*", text))


def _bounded_taxonomy_helper_usage(
    diagnostics: Mapping[str, object],
    top: int | None,
) -> Mapping[str, object]:
    limit = _top_limit(top)
    if limit is None:
        return diagnostics

    files = tuple(cast(Sequence[Mapping[str, object]], diagnostics.get("files", ())))
    payload = dict(diagnostics)
    payload["files"] = [dict(row) for row in files[:limit]]
    return payload


def _top_limit(top: int | None) -> int | None:
    if top is None or top <= 0:
        return None
    return top
