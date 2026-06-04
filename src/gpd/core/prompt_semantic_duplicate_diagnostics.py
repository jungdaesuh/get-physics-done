"""Semantic duplicate invariant scanning for prompt diagnostics."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gpd.core import prompt_markdown_scan as _prompt_markdown_scan
from gpd.core.return_contract import RETURN_STATUS_ORDER

_body_without_frontmatter_with_line_offset = _prompt_markdown_scan.body_without_frontmatter_with_line_offset
_iter_unfenced_lines = _prompt_markdown_scan.iter_unfenced_lines
_relative_path = _prompt_markdown_scan.relative_path

_SEMANTIC_EXAMPLE_LIMIT = 10
_SEMANTIC_STATUS_PIPE_DISPLAY = " | ".join(RETURN_STATUS_ORDER)
_SEMANTIC_STATUS_SEQUENCE_RE = r".*".join(rf"\b{re.escape(status)}\b" for status in RETURN_STATUS_ORDER)
_SEMANTIC_STATUS_PIPE_RE = r"\s*\|\s*".join(rf"\b{re.escape(status)}\b" for status in RETURN_STATUS_ORDER)
_SEMANTIC_STATUS_VOCAB_RE = re.compile(
    rf"{_SEMANTIC_STATUS_SEQUENCE_RE}|{_SEMANTIC_STATUS_PIPE_RE}",
    re.IGNORECASE,
)
_SEMANTIC_ROUTE_STATUS_RE = re.compile(
    r"\b(route|accept|handle|read|consume)\b.{0,100}\b(gpd_return\.status|typed status|structured status)\b",
    re.IGNORECASE,
)
_SEMANTIC_FRESH_CONTINUATION_RE = re.compile(
    r"\b(fresh continuation|one-shot handoff|same spawned run|resume(?:d)? in place|resume-in-place)\b",
    re.IGNORECASE,
)
_SEMANTIC_CHECKPOINT_SPAWN_RE = re.compile(
    r"\bcheckpoint\b.{0,140}\b(present|collect|response|user input|ask(?:ing)? the user)\b"
    r".{0,140}\b(spawn|start|fresh continuation)\b",
    re.IGNORECASE,
)
_SEMANTIC_NO_WAIT_RE = re.compile(
    r"\bdo not\b.{0,100}\b(wait|keep .*alive|resume .*in place|let .*continue)\b",
    re.IGNORECASE,
)
_SEMANTIC_STALE_ARTIFACT_RE = re.compile(
    r"\b(stale|preexisting|already existed|existing .* before this run)\b",
    re.IGNORECASE,
)
_SEMANTIC_RUNTIME_NOT_PROOF_RE = re.compile(
    r"\b(do not trust|do not infer|not enough|recovery evidence only|cannot prove)\b.{0,140}"
    r"\b(runtime|handoff status|completion text|files? alone|preexisting files?)\b",
    re.IGNORECASE,
)
_SEMANTIC_FILES_WRITTEN_RE = re.compile(r"\bgpd_return\.files_written\b|\bfiles_written\b", re.IGNORECASE)
_SEMANTIC_FILE_GATE_RE = re.compile(
    r"\b(named|names|appears|listed|list|same path|fresh|exists|readable|present|allowed|allowlist|"
    r"actually written|expected artifacts?|artifact gate)\b",
    re.IGNORECASE,
)
_SEMANTIC_PRESENTATION_ONLY_RE = re.compile(
    r"\b(headings?|human-readable|marker strings?|prose|success text|labels?)\b.{0,140}"
    r"\b(presentation only|not enough|do not satisfy|do not route|route on|authority|authoritative)\b",
    re.IGNORECASE,
)
_SEMANTIC_ROUTE_NOT_PROSE_RE = re.compile(
    r"\broute\b.{0,100}\b(gpd_return\.status|frontmatter|artifact gate|structured status)\b.{0,140}"
    r"\bnot\b.{0,100}\b(headings?|marker strings?|prose|runtime text|labels?)\b",
    re.IGNORECASE,
)
_SEMANTIC_NO_SYNTH_CHILD_RETURN_RE = re.compile(
    r"\b(do not|never)\b.{0,100}"
    r"\b(synthesize|synthesized|synthetic|fabricate|patch|paste|hand-author)\b.{0,140}"
    r"\b(child|planner|checker|verifier|agent|gpd_return|return envelope)\b",
    re.IGNORECASE,
)
_SEMANTIC_MISSING_CHILD_RETURN_RE = re.compile(
    r"\b(child|planner|checker|verifier|agent)\b.{0,120}"
    r"\b(missing|invalid|malformed)\b.{0,120}\b(gpd_return|return envelope)\b.{0,120}"
    r"\b(retry|fallback|incomplete)\b",
    re.IGNORECASE,
)
_SEMANTIC_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class _SemanticDuplicateCategory:
    category: str
    label: str
    canonical_references: tuple[str, ...]
    suggested_action: str


_SEMANTIC_DUPLICATE_CATEGORIES: tuple[_SemanticDuplicateCategory, ...] = (
    _SemanticDuplicateCategory(
        category="status_handling",
        label="Runtime status routing and vocabulary",
        canonical_references=(
            "src/gpd/specs/references/orchestration/agent-infrastructure.md",
            "src/gpd/specs/references/verification/verification-status-authority.md",
        ),
        suggested_action=(
            "Keep local routing decisions, but reference the shared runtime status authority for generic vocabulary."
        ),
    ),
    _SemanticDuplicateCategory(
        category="fresh_continuation",
        label="Checkpoint stop and fresh continuation ownership",
        canonical_references=(
            "src/gpd/specs/references/orchestration/agent-delegation.md",
            "src/gpd/specs/references/orchestration/continuation-boundary.md",
        ),
        suggested_action=(
            "Keep callsite-specific checkpoint prompts, but reference continuation-boundary.md for generic restart rules."
        ),
    ),
    _SemanticDuplicateCategory(
        category="stale_artifact_rejection",
        label="Reject stale artifact and runtime-success evidence",
        canonical_references=(
            "src/gpd/specs/references/orchestration/child-artifact-gate.md",
            "src/gpd/specs/references/orchestration/continuation-boundary.md",
            "src/gpd/specs/references/publication/stage-recovery-gate.md",
        ),
        suggested_action=(
            "Keep local expected artifact names, but move generic stale-output rejection to the shared artifact gate."
        ),
    ),
    _SemanticDuplicateCategory(
        category="files_written_freshness",
        label="Fresh artifact proof via gpd_return.files_written",
        canonical_references=(
            "src/gpd/specs/references/orchestration/child-artifact-gate.md",
            "src/gpd/specs/references/orchestration/continuation-boundary.md",
        ),
        suggested_action=(
            "Keep callsite-specific expected artifacts, but replace generic freshness prose with child-artifact-gate.md."
        ),
    ),
    _SemanticDuplicateCategory(
        category="heading_prose_non_authority",
        label="Headings and prose are presentation, not routing authority",
        canonical_references=(
            "src/gpd/specs/references/orchestration/child-artifact-gate.md",
            "src/gpd/specs/references/verification/verification-status-authority.md",
            "src/gpd/specs/references/verification/core/verification-child-return-contract.md",
        ),
        suggested_action=("Keep user-facing labels where useful, but route on structured status and artifact gates."),
    ),
    _SemanticDuplicateCategory(
        category="no_synthesized_child_gpd_return",
        label="Do not synthesize child gpd_return envelopes",
        canonical_references=(
            "src/gpd/specs/references/orchestration/agent-delegation.md",
            "src/gpd/specs/references/orchestration/child-artifact-gate.md",
        ),
        suggested_action=(
            "Keep main-context fallback returns distinct from child returns; retry or fail closed on malformed child envelopes."
        ),
    ),
)
_SEMANTIC_DUPLICATE_CATEGORY_BY_ID = {category.category: category for category in _SEMANTIC_DUPLICATE_CATEGORIES}


@dataclass(frozen=True, slots=True)
class SemanticDuplicateOccurrence:
    path: str
    line: int
    category: str
    snippet: str
    matched_terms: tuple[str, ...]
    is_reference_or_template: bool


@dataclass(frozen=True, slots=True)
class SemanticDuplicateGroup:
    category: str
    label: str
    occurrence_count: int
    file_count: int
    non_reference_occurrence_count: int
    non_reference_file_count: int
    severity: Literal["info", "warn", "high"]
    canonical_references: tuple[str, ...]
    examples: tuple[SemanticDuplicateOccurrence, ...]
    suggested_action: str


def scan_semantic_duplicate_invariant_groups(
    paths: Iterable[Path],
    *,
    repo_root: Path,
) -> tuple[SemanticDuplicateGroup, ...]:
    """Scan selected prompt paths for semantic duplicate invariant prose."""

    root = repo_root.expanduser().resolve()
    occurrences_by_category: dict[str, list[SemanticDuplicateOccurrence]] = defaultdict(list)
    files_by_category: dict[str, set[str]] = defaultdict(set)
    non_reference_files_by_category: dict[str, set[str]] = defaultdict(set)

    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative_path = _relative_path(path, root)
        is_reference_or_template = _is_reference_or_template_path(relative_path)
        body, line_offset = _body_without_frontmatter_with_line_offset(text)
        for line_number, line in _iter_unfenced_lines(body):
            for clause in _semantic_logical_clauses(line):
                for category, matched_terms in _semantic_category_matches(clause):
                    occurrence = SemanticDuplicateOccurrence(
                        path=relative_path,
                        line=line_number + line_offset,
                        category=category,
                        snippet=_semantic_snippet(clause),
                        matched_terms=matched_terms,
                        is_reference_or_template=is_reference_or_template,
                    )
                    occurrences_by_category[category].append(occurrence)
                    files_by_category[category].add(relative_path)
                    if not is_reference_or_template:
                        non_reference_files_by_category[category].add(relative_path)

    category_order = {category.category: index for index, category in enumerate(_SEMANTIC_DUPLICATE_CATEGORIES)}
    severity_order = {"high": 0, "warn": 1, "info": 2}
    groups: list[SemanticDuplicateGroup] = []
    for category_id, occurrences in occurrences_by_category.items():
        category = _SEMANTIC_DUPLICATE_CATEGORY_BY_ID[category_id]
        file_count = len(files_by_category[category_id])
        non_reference_occurrence_count = sum(1 for occurrence in occurrences if not occurrence.is_reference_or_template)
        non_reference_file_count = len(non_reference_files_by_category[category_id])
        sorted_examples = tuple(
            sorted(
                occurrences,
                key=lambda occurrence: (
                    occurrence.is_reference_or_template,
                    occurrence.path,
                    occurrence.line,
                    occurrence.snippet,
                ),
            )[:_SEMANTIC_EXAMPLE_LIMIT]
        )
        groups.append(
            SemanticDuplicateGroup(
                category=category.category,
                label=category.label,
                occurrence_count=len(occurrences),
                file_count=file_count,
                non_reference_occurrence_count=non_reference_occurrence_count,
                non_reference_file_count=non_reference_file_count,
                severity=_semantic_duplicate_severity(category.category, non_reference_file_count),
                canonical_references=category.canonical_references,
                examples=sorted_examples,
                suggested_action=category.suggested_action,
            )
        )

    return tuple(
        sorted(
            groups,
            key=lambda group: (
                severity_order[group.severity],
                -group.non_reference_file_count,
                -group.occurrence_count,
                category_order[group.category],
            ),
        )
    )


def status_handling_terms(clause: str) -> tuple[str, ...]:
    folded = clause.casefold()
    has_gpd_status = "gpd_return.status" in folded
    has_runtime_vocab = bool(_SEMANTIC_STATUS_VOCAB_RE.search(clause))
    has_route_status = bool(_SEMANTIC_ROUTE_STATUS_RE.search(clause))
    if not (has_gpd_status or has_runtime_vocab or has_route_status):
        return ()
    if "verification_status" in folded and not has_gpd_status and not has_runtime_vocab:
        return ()
    terms: list[str] = []
    if has_gpd_status:
        terms.append("gpd_return.status")
    if has_runtime_vocab:
        terms.append(_SEMANTIC_STATUS_PIPE_DISPLAY)
    if has_route_status:
        terms.append("route on status")
    return tuple(terms)


def semantic_example_limit(top: int | None) -> int:
    if top is None or top <= 0:
        return _SEMANTIC_EXAMPLE_LIMIT
    return min(top, _SEMANTIC_EXAMPLE_LIMIT)


def _is_reference_or_template_path(relative_path: str) -> bool:
    return "/specs/references/" in f"/{relative_path}" or "/specs/templates/" in f"/{relative_path}"


def _semantic_logical_clauses(line: str) -> tuple[str, ...]:
    normalized = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", line).strip()
    normalized = normalized.strip("`*_ ")
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return ()
    clauses = tuple(part.strip(" -") for part in _SEMANTIC_CLAUSE_SPLIT_RE.split(normalized) if part.strip(" -"))
    return clauses or (normalized,)


def _semantic_category_matches(clause: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    matches: list[tuple[str, tuple[str, ...]]] = []
    for category, terms in (
        ("status_handling", status_handling_terms(clause)),
        ("fresh_continuation", _fresh_continuation_terms(clause)),
        ("stale_artifact_rejection", _stale_artifact_terms(clause)),
        ("files_written_freshness", _files_written_freshness_terms(clause)),
        ("heading_prose_non_authority", _heading_prose_non_authority_terms(clause)),
        ("no_synthesized_child_gpd_return", _no_synthesized_child_return_terms(clause)),
    ):
        if terms:
            matches.append((category, terms))
    return tuple(matches)


def _fresh_continuation_terms(clause: str) -> tuple[str, ...]:
    folded = clause.casefold()
    has_checkpoint = "checkpoint" in folded
    has_fresh = bool(_SEMANTIC_FRESH_CONTINUATION_RE.search(clause))
    has_spawn = bool(_SEMANTIC_CHECKPOINT_SPAWN_RE.search(clause))
    has_no_wait = bool(_SEMANTIC_NO_WAIT_RE.search(clause))
    orchestrator_starts_fresh = has_fresh and "orchestrator" in folded and "start" in folded
    if not (
        (has_checkpoint and (has_fresh or has_spawn or has_no_wait))
        or "one-shot handoff" in folded
        or orchestrator_starts_fresh
    ):
        return ()
    terms: list[str] = []
    if has_checkpoint:
        terms.append("checkpoint")
    if "fresh continuation" in folded:
        terms.append("fresh continuation")
    if "one-shot handoff" in folded:
        terms.append("one-shot handoff")
    if has_spawn or orchestrator_starts_fresh:
        terms.append("spawn continuation")
    if has_no_wait or "resume in place" in folded or "resuming in place" in folded:
        terms.append("not resumed in place")
    return tuple(terms)


def _stale_artifact_terms(clause: str) -> tuple[str, ...]:
    has_stale_word = bool(_SEMANTIC_STALE_ARTIFACT_RE.search(clause))
    has_runtime_not_proof = bool(_SEMANTIC_RUNTIME_NOT_PROOF_RE.search(clause))
    has_artifact_context = bool(
        re.search(r"\b(artifact|file|handoff|runtime|completion|success|evidence|output|report)\b", clause, re.I)
    )
    if not ((has_stale_word and has_artifact_context) or has_runtime_not_proof):
        return ()
    terms: list[str] = []
    folded = clause.casefold()
    for term in ("stale", "preexisting", "already existed", "before this run", "runtime", "files alone"):
        if term in folded:
            terms.append(term)
    if has_runtime_not_proof and "runtime" not in terms:
        terms.append("runtime not proof")
    return tuple(terms or ("stale artifact",))


def _files_written_freshness_terms(clause: str) -> tuple[str, ...]:
    if not (_SEMANTIC_FILES_WRITTEN_RE.search(clause) and _SEMANTIC_FILE_GATE_RE.search(clause)):
        return ()
    folded = clause.casefold()
    terms = ["files_written"]
    for term in (
        "fresh",
        "same path",
        "exists",
        "readable",
        "present",
        "allowed",
        "allowlist",
        "expected artifact",
        "artifact gate",
        "actually written",
        "named",
        "names",
        "appears",
    ):
        if term in folded:
            terms.append(term)
    return tuple(dict.fromkeys(terms))


def _heading_prose_non_authority_terms(clause: str) -> tuple[str, ...]:
    has_presentation = bool(_SEMANTIC_PRESENTATION_ONLY_RE.search(clause))
    has_route_not_prose = bool(_SEMANTIC_ROUTE_NOT_PROSE_RE.search(clause))
    if not (has_presentation or has_route_not_prose):
        return ()
    folded = clause.casefold()
    terms: list[str] = []
    for term in ("heading", "headings", "human-readable", "marker strings", "prose", "success text", "labels"):
        if term in folded:
            terms.append(term)
    if "presentation only" in folded:
        terms.append("presentation only")
    if has_route_not_prose:
        terms.append("route on structured status")
    return tuple(dict.fromkeys(terms or ["presentation only"]))


def _no_synthesized_child_return_terms(clause: str) -> tuple[str, ...]:
    has_synthetic_return = bool(_SEMANTIC_NO_SYNTH_CHILD_RETURN_RE.search(clause))
    has_missing_child_return = bool(_SEMANTIC_MISSING_CHILD_RETURN_RE.search(clause))
    if not (has_synthetic_return or has_missing_child_return):
        return ()
    folded = clause.casefold()
    terms: list[str] = []
    for term in (
        "synthesize",
        "synthesized",
        "synthetic",
        "fabricate",
        "patch",
        "paste",
        "hand-author",
        "child",
        "gpd_return",
        "return envelope",
        "retry",
        "incomplete",
    ):
        if term in folded:
            terms.append(term)
    return tuple(dict.fromkeys(terms or ["synthetic child gpd_return"]))


def _semantic_duplicate_severity(
    category: str,
    non_reference_file_count: int,
) -> Literal["info", "warn", "high"]:
    if non_reference_file_count == 0:
        return "info"
    if category == "no_synthesized_child_gpd_return" and non_reference_file_count >= 2:
        return "high"
    if non_reference_file_count >= 5:
        return "high"
    if non_reference_file_count >= 2:
        return "warn"
    return "info"


def _semantic_snippet(clause: str, max_chars: int = 220) -> str:
    normalized = re.sub(r"\s+", " ", clause).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


__all__ = [
    "SemanticDuplicateGroup",
    "SemanticDuplicateOccurrence",
    "scan_semantic_duplicate_invariant_groups",
    "semantic_example_limit",
    "status_handling_terms",
]
