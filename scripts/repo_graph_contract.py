"""Shared repo-graph contract helpers for tests and sync tooling."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

from scripts.generated_region_support import (
    GeneratedRegionSpec,
    check_region_inventory,
    marker_pair,
    render_region,
    replace_regions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = REPO_ROOT / "tests" / "README.md"
CONTRACT_PATH = REPO_ROOT / "tests" / "repo_graph_contract.json"
SCHEMA_VERSION = 1

GENERATED_ON_BLOCK_ID = "generated-on"
SCOPE_BLOCK_ID = "scope"
PROMPT_STEM_INVENTORY_BLOCK_ID = "prompt-stem-inventory"
SAME_STEM_COMMAND_WORKFLOW_BLOCK_ID = "same-stem-command-workflow"
REQUIRED_EDGES_BLOCK_ID = "required-edges"
REPO_GRAPH_BLOCK_IDS = (
    GENERATED_ON_BLOCK_ID,
    SCOPE_BLOCK_ID,
    PROMPT_STEM_INVENTORY_BLOCK_ID,
    SAME_STEM_COMMAND_WORKFLOW_BLOCK_ID,
    REQUIRED_EDGES_BLOCK_ID,
)
PROMPT_STEM_INVENTORY_KEYS = ("same_stems", "command_only_stems", "workflow_only_stems")

REPO_GRAPH_REGION_SPEC = GeneratedRegionSpec(
    marker_prefix="repo-graph",
    known_block_ids=lambda: REPO_GRAPH_BLOCK_IDS,
    block_label="repo graph generated block",
    marker_prefix_separator="-",
)

GENERATED_ON_START, GENERATED_ON_END = marker_pair(REPO_GRAPH_REGION_SPEC, GENERATED_ON_BLOCK_ID)
SCOPE_START, SCOPE_END = marker_pair(REPO_GRAPH_REGION_SPEC, SCOPE_BLOCK_ID)
PROMPT_STEM_INVENTORY_START, PROMPT_STEM_INVENTORY_END = marker_pair(
    REPO_GRAPH_REGION_SPEC, PROMPT_STEM_INVENTORY_BLOCK_ID
)
SAME_STEM_COMMAND_WORKFLOW_START, SAME_STEM_COMMAND_WORKFLOW_END = marker_pair(
    REPO_GRAPH_REGION_SPEC, SAME_STEM_COMMAND_WORKFLOW_BLOCK_ID
)
REQUIRED_EDGES_START, REQUIRED_EDGES_END = marker_pair(REPO_GRAPH_REGION_SPEC, REQUIRED_EDGES_BLOCK_ID)

COMMAND_PROMPT_PARENT = ("src", "gpd", "commands")
WORKFLOW_PROMPT_PARENT = ("src", "gpd", "specs", "workflows")


@dataclass(frozen=True, slots=True)
class GraphScopeSpec:
    label: str
    parent_parts: tuple[str, ...]
    suffix: str
    recursive: bool = False
    name_prefix: str = ""

    def matches_path(self, path: Path) -> bool:
        if path.suffix != self.suffix:
            return False
        if self.name_prefix and not path.name.startswith(self.name_prefix):
            return False
        if self.recursive:
            return _is_under(path, *self.parent_parts)
        return _has_parent(path, *self.parent_parts)


@dataclass(frozen=True, slots=True)
class GraphEdgeSpec:
    source: str
    target: str
    edge_type: str


GRAPH_SCOPE_SPECS = (
    GraphScopeSpec("`src/gpd/commands/*.md`", ("src", "gpd", "commands"), ".md"),
    GraphScopeSpec("`src/gpd/agents/*.md`", ("src", "gpd", "agents"), ".md"),
    GraphScopeSpec("`src/gpd/specs/workflows/*.md`", ("src", "gpd", "specs", "workflows"), ".md"),
    GraphScopeSpec("`src/gpd/specs/templates/**/*.md`", ("src", "gpd", "specs", "templates"), ".md", recursive=True),
    GraphScopeSpec("`src/gpd/specs/references/**/*.md`", ("src", "gpd", "specs", "references"), ".md", recursive=True),
    GraphScopeSpec("`src/gpd/adapters/*.py`", ("src", "gpd", "adapters"), ".py"),
    GraphScopeSpec("`src/gpd/hooks/*.py`", ("src", "gpd", "hooks"), ".py"),
    GraphScopeSpec("`src/gpd/mcp/*.py`", ("src", "gpd", "mcp"), ".py"),
    GraphScopeSpec("`src/gpd/mcp/integrations/*.py`", ("src", "gpd", "mcp", "integrations"), ".py"),
    GraphScopeSpec("`src/gpd/mcp/servers/*.py`", ("src", "gpd", "mcp", "servers"), ".py"),
    GraphScopeSpec("`infra/gpd-*.json`", ("infra",), ".json", name_prefix="gpd-"),
)

GRAPH_SCOPE_LABELS = tuple(spec.label for spec in GRAPH_SCOPE_SPECS)
_NORMALIZED_SCOPE_LABELS = {
    label[1:-1] if label.startswith("`") and label.endswith("`") else label: label for label in GRAPH_SCOPE_LABELS
}

REQUIRED_REPO_GRAPH_EDGES = (
    GraphEdgeSpec(".github/workflows/test.yml", "tests/ci_sharding.py", "authority"),
    GraphEdgeSpec(".github/workflows/test.yml", "actions/checkout@v6", "external-service"),
    GraphEdgeSpec(".github/workflows/test.yml", "actions/setup-node@v6", "external-service"),
    GraphEdgeSpec("src/gpd/mcp/builtin_servers.py", "src/gpd/mcp/descriptor_text.py", "hard-import"),
    GraphEdgeSpec("src/gpd/mcp/servers/skills_server.py", "src/gpd/mcp/descriptor_text.py", "hard-import"),
    GraphEdgeSpec(
        "pyproject.toml",
        (
            "src/gpd/mcp/servers/{arxiv_bridge,conventions_server,verification_server,protocols_server,"
            "errors_mcp,patterns_server,state_server,skills_server}.py"
        ),
        "authority",
    ),
    GraphEdgeSpec("pyproject.toml", "src/gpd/mcp/integrations/wolfram_bridge.py", "authority"),
    GraphEdgeSpec("src/gpd/hooks/statusline.py", "src/gpd/hooks/runtime_detect.py", "hard-import"),
    GraphEdgeSpec("src/gpd/hooks/statusline.py", "src/gpd/adapters/__init__.py", "hard-import"),
    GraphEdgeSpec("src/gpd/hooks/check_update.py", "src/gpd/hooks/runtime_detect.py", "hard-import"),
    GraphEdgeSpec("src/gpd/hooks/notify.py", "src/gpd/hooks/check_update.py", "spawn"),
    GraphEdgeSpec("src/gpd/hooks/notify.py", "src/gpd/hooks/runtime_detect.py", "hard-import"),
    GraphEdgeSpec(
        "src/gpd/cli.py::sync_phase_checkpoints",
        "src/gpd/core/checkpoints.py::sync_phase_checkpoints",
        "spawn",
    ),
    GraphEdgeSpec("src/gpd/core/phases.py", "src/gpd/core/checkpoints.py::sync_phase_checkpoints", "hard-import"),
    GraphEdgeSpec("src/gpd/core/state.py", "<cwd>/GPD/.state-write-intent", "generated-output"),
    GraphEdgeSpec(
        "src/gpd/core/checkpoints.py",
        "generated outputs {GPD/CHECKPOINTS.md, GPD/phase-checkpoints/*.md}",
        "generated-output",
    ),
    GraphEdgeSpec("src/gpd/core/checkpoints.py", "<cwd>/GPD/CHECKPOINTS.md", "generated-output"),
    GraphEdgeSpec("src/gpd/core/checkpoints.py", "<cwd>/GPD/phase-checkpoints/*.md", "generated-output"),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/execute-phase.md",
        (
            "src/gpd/specs/{references/orchestration/meta-orchestration.md,references/orchestration/"
            "artifact-surfacing.md,references/orchestration/checkpoints.md,references/verification/core/"
            "verification-core.md,templates/summary.md,templates/continuation-prompt.md,templates/paper/"
            "figure-tracker.md,templates/paper/experimental-comparison.md,templates/recovery-plan.md}"
        ),
        "include",
    ),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/execute-phase.md",
        (
            "src/gpd/specs/{references/orchestration/meta-orchestration.md,references/orchestration/"
            "checkpoints.md,references/orchestration/continuous-execution.md,references/verification/core/"
            "verification-core.md,templates/summary.md,templates/continuation-prompt.md,templates/paper/"
            "figure-tracker.md,templates/paper/experimental-comparison.md,templates/recovery-plan.md}"
        ),
        "include",
    ),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/execute-plan.md",
        (
            "src/gpd/specs/{references/execution/git-integration.md,references/execution/github-lifecycle.md,"
            "references/execution/execute-plan-recovery.md,references/execution/execute-plan-validation.md,"
            "references/execution/execute-plan-checkpoints.md,references/protocols/reproducibility.md,"
            "references/execution/executor-index.md,references/orchestration/context-budget.md,references/"
            "orchestration/checkpoints.md,templates/summary.md}"
        ),
        "include",
    ),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/plan-phase.md",
        "src/gpd/specs/templates/plan-contract-schema.md",
        "include",
    ),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/execute-plan.md",
        "src/gpd/specs/templates/contract-results-schema.md",
        "include",
    ),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/verify-work.md",
        "src/gpd/specs/templates/contract-results-schema.md",
        "include",
    ),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/verify-work.md",
        "src/gpd/specs/templates/plan-contract-schema.md",
        "include",
    ),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/write-paper.md",
        (
            "src/gpd/specs/templates/paper/{paper-config-schema.md,artifact-manifest-schema.md,"
            "bibliography-audit-schema.md,reproducibility-manifest.md}"
        ),
        "include",
    ),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/new-project.md",
        "src/gpd/specs/templates/project-contract-schema.md",
        "include",
    ),
    GraphEdgeSpec(
        "src/gpd/commands/peer-review.md",
        (
            "src/gpd/agents/{gpd-review-reader,gpd-review-literature,gpd-review-math,gpd-check-proof,"
            "gpd-review-physics,gpd-review-significance,gpd-referee}.md"
        ),
        "spawn",
    ),
    GraphEdgeSpec(
        "src/gpd/specs/workflows/peer-review.md",
        (
            "src/gpd/agents/{gpd-review-reader,gpd-review-literature,gpd-review-math,gpd-check-proof,"
            "gpd-review-physics,gpd-review-significance,gpd-referee}.md"
        ),
        "spawn",
    ),
    GraphEdgeSpec(
        (
            "src/gpd/agents/{gpd-review-reader,gpd-review-literature,gpd-review-math,gpd-check-proof,"
            "gpd-review-physics,gpd-review-significance,gpd-referee}.md"
        ),
        "src/gpd/specs/references/publication/peer-review-panel.md",
        "include",
    ),
)


@lru_cache(maxsize=1)
def _runtime_catalog_module():
    module_path = REPO_ROOT / "src" / "gpd" / "adapters" / "runtime_catalog.py"
    spec = importlib.util.spec_from_file_location("_gpd_runtime_catalog_bootstrap", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load runtime catalog from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


def iter_runtime_descriptors():
    return _runtime_catalog_module().iter_runtime_descriptors()


_LOCAL_RUNTIME_MIRROR_EXCLUDES = tuple(descriptor.config_dir_name for descriptor in iter_runtime_descriptors())

EXCLUDED_GRAPH_DIRS = (
    ".git",
    ".mcp.json",
    ".npm-cache",
    ".playwright-mcp",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "GPD",
    *_LOCAL_RUNTIME_MIRROR_EXCLUDES,
    "dist",
)


def read_graph_text() -> str:
    return GRAPH_PATH.read_text(encoding="utf-8")


def load_contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


_GRAPH_EDGE_RE = re.compile(r"^- `([^`\n]+?) -> ([^`\n]+?)`$", re.MULTILINE)


def iter_graph_edge_specs(graph_text: str | None = None) -> tuple[tuple[str, str], ...]:
    text = graph_text if graph_text is not None else read_graph_text()
    return tuple((match.group(1), match.group(2)) for match in _GRAPH_EDGE_RE.finditer(text))


@cache
def _expand_braced_edge_endpoint(endpoint: str) -> tuple[str, ...]:
    match = re.search(r"\{([^{}]+)\}", endpoint)
    if match is None:
        return (endpoint,)

    prefix = endpoint[: match.start()]
    suffix = endpoint[match.end() :]
    expansions: list[str] = []
    for option in (item.strip() for item in match.group(1).split(",")):
        if not option:
            continue
        for expanded_suffix in _expand_braced_edge_endpoint(suffix):
            expansions.append(f"{prefix}{option}{expanded_suffix}")
    return tuple(expansions)


def _edge_endpoint_matches(expected: str, rendered: str) -> bool:
    if expected == rendered:
        return True
    return expected in _expand_braced_edge_endpoint(rendered)


def graph_has_edge(source: str, target: str, graph_text: str | None = None) -> bool:
    for rendered_source, rendered_target in iter_graph_edge_specs(graph_text):
        if _edge_endpoint_matches(source, rendered_source) and _edge_endpoint_matches(target, rendered_target):
            return True
    return False


def graph_has_edge_containing(
    source_fragment: str,
    target_fragment: str,
    graph_text: str | None = None,
) -> bool:
    for rendered_source, rendered_target in iter_graph_edge_specs(graph_text):
        if source_fragment in rendered_source and target_fragment in rendered_target:
            return True
    return False


def _is_excluded_path(path: Path) -> bool:
    if not path.parts:
        return False
    return path.parts[0] in EXCLUDED_GRAPH_DIRS


def _tracked_repo_files(repo_root: Path) -> list[Path] | None:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    return [Path(relative_path) for relative_path in completed.stdout.decode("utf-8").split("\0") if relative_path]


def _untracked_repo_files(repo_root: Path) -> list[Path] | None:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    return [Path(relative_path) for relative_path in completed.stdout.decode("utf-8").split("\0") if relative_path]


def _repo_files_in_scope(repo_root: Path) -> list[Path]:
    tracked_files = _tracked_repo_files(repo_root)
    if tracked_files is not None:
        return [path for path in tracked_files if not _is_excluded_path(path) and (repo_root / path).is_file()]

    return [
        path.relative_to(repo_root)
        for path in repo_root.rglob("*")
        if path.is_file() and not _is_excluded_path(path.relative_to(repo_root))
    ]


def _is_graph_scope_path(path: Path) -> bool:
    return any(spec.matches_path(path) for spec in GRAPH_SCOPE_SPECS)


def untracked_graph_scope_files(repo_root: Path = REPO_ROOT) -> tuple[Path, ...]:
    untracked_files = _untracked_repo_files(repo_root)
    if untracked_files is None:
        return ()
    return tuple(
        sorted(
            (
                path
                for path in untracked_files
                if not _is_excluded_path(path) and _is_graph_scope_path(path) and (repo_root / path).is_file()
            ),
            key=lambda path: path.as_posix(),
        )
    )


def _is_under(path: Path, *parent_parts: str) -> bool:
    return path.parts[: len(parent_parts)] == parent_parts


def _has_parent(path: Path, *parent_parts: str) -> bool:
    return path.parts[:-1] == parent_parts


def canonical_scope_label(label: str) -> str:
    normalized = label.strip()
    if normalized.startswith("`") and normalized.endswith("`"):
        normalized = normalized[1:-1]
    return _NORMALIZED_SCOPE_LABELS.get(normalized, label)


def parse_scope_count(label: str) -> int:
    canonical_label = canonical_scope_label(label)
    scope_counts = load_contract()["scope_counts"]
    assert isinstance(scope_counts, dict), "repo graph contract scope counts must be a mapping"
    value = scope_counts.get(canonical_label)
    assert isinstance(value, int), f"Missing scope count for {canonical_label}"
    return value


def live_repo_file_count(repo_root: Path = REPO_ROOT) -> int:
    return len(_repo_files_in_scope(repo_root))


def expected_scope_counts(repo_root: Path = REPO_ROOT) -> dict[str, int]:
    repo_files = _repo_files_in_scope(repo_root)

    return {spec.label: sum(1 for path in repo_files if spec.matches_path(path)) for spec in GRAPH_SCOPE_SPECS}


def prompt_stem_inventory(repo_root: Path = REPO_ROOT) -> dict[str, tuple[str, ...]]:
    repo_files = _repo_files_in_scope(repo_root)
    command_stems = {
        path.stem for path in repo_files if _has_parent(path, *COMMAND_PROMPT_PARENT) and path.suffix == ".md"
    }
    workflow_stems = {
        path.stem for path in repo_files if _has_parent(path, *WORKFLOW_PROMPT_PARENT) and path.suffix == ".md"
    }

    return {
        "same_stems": tuple(sorted(command_stems & workflow_stems)),
        "command_only_stems": tuple(sorted(command_stems - workflow_stems)),
        "workflow_only_stems": tuple(sorted(workflow_stems - command_stems)),
    }


def _contract_prompt_stem_tuple(payload: object, key: str) -> tuple[str, ...]:
    assert isinstance(payload, list), f"prompt_stem_inventory.{key} must be a list"
    stems: list[str] = []
    for item in payload:
        assert isinstance(item, str), f"prompt_stem_inventory.{key} entries must be strings"
        stems.append(item)
    return tuple(stems)


def contract_prompt_stem_inventory(contract: dict[str, object]) -> dict[str, tuple[str, ...]]:
    payload = contract["prompt_stem_inventory"]
    assert isinstance(payload, dict), "prompt_stem_inventory must be a mapping"
    return {key: _contract_prompt_stem_tuple(payload.get(key), key) for key in PROMPT_STEM_INVENTORY_KEYS}


def _prompt_stem_contract_payload(repo_root: Path) -> dict[str, list[str]]:
    inventory = prompt_stem_inventory(repo_root)
    return {key: list(inventory[key]) for key in PROMPT_STEM_INVENTORY_KEYS}


def build_contract(
    repo_root: Path = REPO_ROOT,
) -> dict[str, object]:
    scope_counts = expected_scope_counts(repo_root)
    excluded_dirs = list(EXCLUDED_GRAPH_DIRS)

    return {
        "schema_version": SCHEMA_VERSION,
        "excluded_graph_dirs": excluded_dirs,
        "scope_counts": scope_counts,
        "prompt_stem_inventory": _prompt_stem_contract_payload(repo_root),
    }


def write_contract(contract: dict[str, object], contract_path: Path = CONTRACT_PATH) -> None:
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def _excluded_dir_readme_pattern(path_name: str) -> str:
    return path_name if path_name == ".mcp.json" else f"{path_name}/**"


def _render_generated_on_body(_contract: dict[str, object]) -> str:
    return "Only marked repo-graph blocks are generated from the current worktree via `uv run python scripts/sync_repo_graph_contract.py`."


def _render_scope_body(contract: dict[str, object]) -> str:
    scope_counts = contract["scope_counts"]
    excluded_dirs = contract["excluded_graph_dirs"]
    assert isinstance(scope_counts, dict), "scope_counts must be a mapping"
    assert isinstance(excluded_dirs, list), "excluded_graph_dirs must be a list"

    lines = [""]
    for label in GRAPH_SCOPE_LABELS:
        value = scope_counts.get(label)
        assert isinstance(value, int), f"Missing scope count for {label}"
        lines.append(f"- {label}: `{value}`")

    lines.extend(
        (
            "",
            "Excluded as noise from node counting, but still modeled where contractually relevant:",
            "",
        )
    )
    lines.extend(f"- `{_excluded_dir_readme_pattern(path_name)}`" for path_name in excluded_dirs)
    return "\n".join(lines)


def _render_compact_stem_list(stems: tuple[str, ...]) -> str:
    if not stems:
        return "`none`"
    return ", ".join(f"`{stem}`" for stem in stems)


def _render_prompt_stem_inventory_body(contract: dict[str, object]) -> str:
    inventory = contract_prompt_stem_inventory(contract)

    return "\n".join(
        (
            f"- Same-stem command/workflow prompt stems: `{len(inventory['same_stems'])}`",
            f"- Command-only prompt stems: {_render_compact_stem_list(inventory['command_only_stems'])}",
            f"- Workflow-only prompt stems: {_render_compact_stem_list(inventory['workflow_only_stems'])}",
        )
    )


def _render_same_stem_command_workflow_body(contract: dict[str, object]) -> str:
    same_stems = ",".join(contract_prompt_stem_inventory(contract)["same_stems"])

    return f"- `src/gpd/commands/{{{same_stems}}}.md -> src/gpd/specs/workflows/{{same stems}}.md`"


def _render_required_edges_body(_contract: dict[str, object]) -> str:
    lines: list[str] = []
    for edge in REQUIRED_REPO_GRAPH_EDGES:
        lines.append(f"- `{edge.source} -> {edge.target}`")
        lines.append(f"  `{edge.edge_type}`")
    return "\n".join(lines)


def _render_repo_graph_region_body(
    block_id: str,
    contract: dict[str, object],
) -> str:
    if block_id == GENERATED_ON_BLOCK_ID:
        return _render_generated_on_body(contract)
    if block_id == SCOPE_BLOCK_ID:
        return _render_scope_body(contract)
    if block_id == PROMPT_STEM_INVENTORY_BLOCK_ID:
        return _render_prompt_stem_inventory_body(contract)
    if block_id == SAME_STEM_COMMAND_WORKFLOW_BLOCK_ID:
        return _render_same_stem_command_workflow_body(contract)
    if block_id == REQUIRED_EDGES_BLOCK_ID:
        return _render_required_edges_body(contract)
    raise ValueError(f"Unknown repo graph generated block {block_id!r}")


def render_generated_on_block(contract: dict[str, object]) -> str:
    return render_region(REPO_GRAPH_REGION_SPEC, GENERATED_ON_BLOCK_ID, _render_generated_on_body(contract))


def render_scope_block(contract: dict[str, object]) -> str:
    return render_region(REPO_GRAPH_REGION_SPEC, SCOPE_BLOCK_ID, _render_scope_body(contract))


def render_prompt_stem_inventory_block(contract: dict[str, object]) -> str:
    return render_region(
        REPO_GRAPH_REGION_SPEC,
        PROMPT_STEM_INVENTORY_BLOCK_ID,
        _render_prompt_stem_inventory_body(contract),
    )


def render_same_stem_command_workflow_block(repo_root: Path = REPO_ROOT) -> str:
    contract = build_contract(repo_root)
    return render_region(
        REPO_GRAPH_REGION_SPEC,
        SAME_STEM_COMMAND_WORKFLOW_BLOCK_ID,
        _render_same_stem_command_workflow_body(contract),
    )


def render_required_edges_block(contract: dict[str, object]) -> str:
    return render_region(REPO_GRAPH_REGION_SPEC, REQUIRED_EDGES_BLOCK_ID, _render_required_edges_body(contract))


def sync_readme_text(readme_text: str, contract: dict[str, object], _repo_root: Path = REPO_ROOT) -> str:
    synced, block_ids = replace_regions(
        readme_text,
        spec=REPO_GRAPH_REGION_SPEC,
        render_body=lambda block_id: _render_repo_graph_region_body(block_id, contract),
        path=GRAPH_PATH,
    )
    inventory_diffs = check_region_inventory(
        block_ids,
        spec=REPO_GRAPH_REGION_SPEC,
        required_blocks=REPO_GRAPH_BLOCK_IDS,
        path=GRAPH_PATH,
        label="repo graph marker inventory",
    )
    if inventory_diffs:
        raise ValueError(inventory_diffs[0].diff.strip())
    return synced
