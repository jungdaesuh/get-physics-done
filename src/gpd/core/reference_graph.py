"""Reference-list helpers for markdown-backed GPD surfaces."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from gpd import registry as content_registry
from gpd.core.prompt_markdown_scan import iter_unfenced_lines

_SPEC_ROOT = content_registry.SPECS_DIR.resolve()
_AGENT_ROOT = content_registry.AGENTS_DIR.resolve()
_COMMAND_ROOT = content_registry.COMMANDS_DIR.resolve()
_REPO_ROOT = _SPEC_ROOT.parents[2]
_REFERENCE_ROOT = _SPEC_ROOT / "references"
_RELATIVE_REFERENCE_PREFIXES = ("domains/",)


@dataclass(frozen=True, slots=True)
class ReferencePrefixSpec:
    raw_prefix: str
    portable_prefix: str
    root: Path
    kind: str
    allow_missing: bool = False


def _reference_prefix(name: str, *, kind: str = "reference") -> ReferencePrefixSpec:
    return ReferencePrefixSpec(
        f"{name}/",
        f"@{{GPD_INSTALL_DIR}}/references/{name}/",
        _REFERENCE_ROOT / name,
        kind,
    )


DEFAULT_REFERENCE_PREFIX_SPECS: tuple[ReferencePrefixSpec, ...] = (
    ReferencePrefixSpec("references/", "@{GPD_INSTALL_DIR}/references/", _REFERENCE_ROOT, "reference"),
    ReferencePrefixSpec("workflows/", "@{GPD_INSTALL_DIR}/workflows/", _SPEC_ROOT / "workflows", "workflow"),
    ReferencePrefixSpec("templates/", "@{GPD_INSTALL_DIR}/templates/", _SPEC_ROOT / "templates", "template"),
    ReferencePrefixSpec("bundles/", "@{GPD_INSTALL_DIR}/bundles/", _SPEC_ROOT / "bundles", "bundle"),
    _reference_prefix("shared"),
    _reference_prefix("execution"),
    _reference_prefix("verification"),
    _reference_prefix("conventions"),
    _reference_prefix("research"),
    _reference_prefix("publication"),
    _reference_prefix("protocols"),
    _reference_prefix("subfields"),
    _reference_prefix("orchestration"),
    ReferencePrefixSpec("commands/", "@{GPD_INSTALL_DIR}/commands/", _COMMAND_ROOT, "command"),
    ReferencePrefixSpec("agents/", "@{GPD_AGENTS_DIR}/", _AGENT_ROOT, "agent"),
    ReferencePrefixSpec("docs/", "@GPD/docs/", _REPO_ROOT / "docs", "docs", allow_missing=True),
)


@lru_cache(maxsize=16)
def _compile_markdown_reference_re(
    raw_prefixes: tuple[str, ...],
    relative_prefixes: tuple[str, ...],
) -> re.Pattern[str]:
    prefixes = "|".join(re.escape(prefix) for prefix in (*raw_prefixes, *relative_prefixes))
    return re.compile(
        r"(?<![A-Za-z0-9_}/.-])(?P<path>(?:@?\{GPD_(?:INSTALL|AGENTS)_DIR\}/|(?:\.\./|\.\/)?"
        rf"(?:{prefixes}|GPD/|src/gpd/))[^\s`\"')]+?\.md)"
    )


@dataclass(frozen=True, slots=True)
class ReferenceResolver:
    prefix_specs: tuple[ReferencePrefixSpec, ...] = DEFAULT_REFERENCE_PREFIX_SPECS
    relative_reference_prefixes: tuple[str, ...] = _RELATIVE_REFERENCE_PREFIXES
    spec_root: Path = _SPEC_ROOT
    agent_root: Path = _AGENT_ROOT
    repo_root: Path = _REPO_ROOT

    def markdown_reference_re(self) -> re.Pattern[str]:
        return _compile_markdown_reference_re(
            tuple(spec.raw_prefix for spec in self.prefix_specs),
            self.relative_reference_prefixes,
        )

    def reference_kind(self, path: str) -> str:
        for spec in self.prefix_specs:
            if path.startswith(spec.portable_prefix):
                return spec.kind
        if path.startswith("@GPD/"):
            return "project"
        return "spec"

    def portable_reference_path(
        self, raw_path: str, *, base_path: Path | None = None
    ) -> tuple[str, Path | None] | None:
        candidate = raw_path.rstrip(".,:;")
        if not candidate:
            return None

        def spec_for(candidate_path: str) -> ReferencePrefixSpec | None:
            return next((spec for spec in self.prefix_specs if candidate_path.startswith(spec.raw_prefix)), None)

        def normalize(resolved: Path) -> tuple[str, Path] | None:
            resolved = resolved.resolve()
            if not resolved.is_file():
                return None
            for spec in self.prefix_specs:
                try:
                    rel = resolved.relative_to(spec.root)
                except ValueError:
                    continue
                return f"{spec.portable_prefix}{rel.as_posix()}", resolved
            return None

        def missing(spec: ReferencePrefixSpec, relative: str) -> tuple[str, None] | None:
            normalized = relative.replace("\\", "/")
            if (
                not normalized
                or normalized.startswith("/")
                or any(part in {"", ".", ".."} for part in normalized.split("/"))
            ):
                return None
            return f"{spec.portable_prefix}{normalized}", None

        if candidate.startswith(("@{GPD_INSTALL_DIR}/", "{GPD_INSTALL_DIR}/")):
            relative = candidate.split("}/", 1)[1]
            spec = spec_for(relative)
            resolved = (spec.root / relative.removeprefix(spec.raw_prefix)) if spec else (self.spec_root / relative)
            return normalize(resolved)

        if candidate.startswith(("@{GPD_AGENTS_DIR}/", "{GPD_AGENTS_DIR}/")):
            return normalize(self.agent_root / candidate.split("}/", 1)[1])

        if candidate.startswith(("GPD/", "@GPD/")):
            return f"@{candidate.removeprefix('@')}", None

        if candidate.startswith("src/gpd/"):
            return normalize((self.repo_root / candidate).resolve()) or (candidate, None)

        raw_path_obj = Path(candidate)
        if raw_path_obj.is_absolute():
            return normalize(raw_path_obj)

        spec = spec_for(candidate)
        if spec is not None:
            relative = candidate.removeprefix(spec.raw_prefix)
            return normalize(spec.root / relative) or (missing(spec, relative) if spec.allow_missing else None)

        if base_path is not None:
            return normalize((base_path.parent / candidate).resolve())

        return None


@dataclass(frozen=True, slots=True)
class ReferenceSeed:
    raw_path: str
    source: str = "staged_loading"
    relationship: str = "stage_eager"
    stage: str | None = None
    conditional_when: str | None = None
    scan_body_for_metadata: bool = True


ResolveReferenceWithBase = Callable[..., tuple[str, Path | None] | None]
ReferenceKind = Callable[[str], str]
ContentTransform = Callable[[str], str]


def build_reference_lists(
    content: str,
    *,
    source_path: Path | None = None,
    seeds: tuple[ReferenceSeed, ...] = (),
    read_transitive_reference_bodies: bool = True,
    resolver: ReferenceResolver | None = None,
    resolve_reference: ResolveReferenceWithBase | None = None,
    reference_kind: ReferenceKind | None = None,
    content_transform: ContentTransform | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return direct and transitive markdown references from content plus explicit seeds."""

    active_resolver = resolver or ReferenceResolver()
    resolve = resolve_reference or active_resolver.portable_reference_path
    classify = reference_kind or active_resolver.reference_kind
    transform = content_transform or (lambda value: value)
    direct: dict[str, dict[str, object]] = {}
    transitive: dict[str, dict[str, object]] = {}
    scanned_paths: set[str] = set()

    def eager(raw_path: str, *, source: str, relationship: str, direct_reference: bool) -> bool:
        return (
            raw_path.startswith("@{GPD_")
            and not (direct_reference and source == "staged_loading")
            and relationship != "stage_lazy_declared"
        )

    def add_entry(
        table: dict[str, dict[str, object]],
        *,
        path: str,
        raw_path: str,
        depth: int,
        source: str,
        relationship: str,
        stage: str | None,
        conditional_when: str | None,
    ) -> None:
        if path in table:
            return
        entry: dict[str, object] = {"path": path, "kind": classify(path)}
        direct_reference = depth == 0
        if eager(raw_path, source=source, relationship=relationship, direct_reference=direct_reference):
            entry["eager"] = True
        if not direct_reference:
            entry["depth"] = depth
        if source != "content":
            entry["source"] = source
        if stage is not None:
            entry["stage"] = stage
        if relationship not in {"content", "transitive"}:
            entry["relationship"] = relationship
        if conditional_when is not None:
            entry["conditional_when"] = conditional_when
        table[path] = entry

    def collect(
        markdown: str,
        *,
        current_path: Path | None,
        depth: int,
        source: str,
        stage: str | None = None,
        conditional_when: str | None = None,
    ) -> None:
        relationship = "content" if depth == 0 else "transitive"
        for _line_number, line in iter_unfenced_lines(markdown):
            for match in active_resolver.markdown_reference_re().finditer(line):
                record(
                    match.group("path"),
                    current_path=current_path,
                    depth=depth,
                    source=source,
                    relationship=relationship,
                    stage=stage,
                    conditional_when=conditional_when,
                )

    def record(
        raw_path: str,
        *,
        current_path: Path | None,
        depth: int,
        source: str,
        relationship: str,
        stage: str | None = None,
        conditional_when: str | None = None,
        scan_body_for_metadata: bool = True,
    ) -> None:
        normalized = resolve(raw_path, base_path=current_path)
        if normalized is None:
            return
        path, referenced_path = normalized
        add_entry(
            direct if depth == 0 else transitive,
            path=path,
            raw_path=raw_path,
            depth=depth,
            source=source,
            relationship=relationship,
            stage=stage,
            conditional_when=conditional_when,
        )
        if (
            not scan_body_for_metadata
            or referenced_path is None
            or referenced_path.suffix != ".md"
            or not referenced_path.exists()
            or (depth > 0 and not read_transitive_reference_bodies)
            or path in scanned_paths
        ):
            return
        scanned_paths.add(path)
        try:
            nested = transform(referenced_path.read_text(encoding="utf-8"))
        except OSError:
            return
        collect(
            nested,
            current_path=referenced_path,
            depth=depth + 1,
            source=source,
            stage=stage,
            conditional_when=conditional_when,
        )

    collect(transform(content), current_path=source_path, depth=0, source="content")
    for seed in seeds:
        record(
            seed.raw_path,
            current_path=None,
            depth=0,
            source=seed.source,
            relationship=seed.relationship,
            stage=seed.stage,
            conditional_when=seed.conditional_when,
            scan_body_for_metadata=seed.scan_body_for_metadata,
        )
    return list(direct.values()), list(transitive.values())
