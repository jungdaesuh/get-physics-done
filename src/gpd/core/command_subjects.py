"""Typer-free command-subject and preflight policy helpers."""

from __future__ import annotations

import dataclasses
import glob
import re
from collections.abc import Collection, Mapping
from pathlib import Path

from gpd.core.command_arguments import (
    _flag_values,
    _has_write_paper_external_authoring_intake,
    _looks_like_digest_knowledge_arxiv_token,
    _looks_like_digest_knowledge_path_token,
    _looks_like_review_knowledge_id_token,
    _positional_tokens,
    _split_command_arguments,
)
from gpd.core.constants import (
    ProjectLayout,
)
from gpd.core.peer_review_mode import (
    ResolvedReviewManuscriptTarget,
    path_is_within_supported_manuscript_root,
    resolve_review_manuscript_target_details,
    resolve_supported_manuscript_root_for_target,
)
from gpd.core.utils import normalize_ascii_slug
from gpd.core.write_paper_intake import (
    WritePaperExternalAuthoringIntakeResolution,
    reject_write_paper_intake_inside_project_detail,
    resolve_write_paper_external_authoring_intake,
    write_paper_external_authoring_intake_argument,
)


@dataclasses.dataclass(frozen=True)
class ResolvedCommandSubject:
    """Shared command-subject resolution envelope for CLI preflight consumers."""

    command: str
    workspace_root: Path
    resolved_project_root: Path | None
    context_root: Path
    target_path: Path | None
    target_root: Path | None
    subject_kind: str
    ownership_mode: str
    status: str
    exists: bool
    explicit_input: bool = False
    project_root_source: str | None = None
    project_root_auto_selected: bool = False
    reentry_mode: str | None = None
    ancestor_walked_up: bool = False
    detail: str = ""


ResolvedManuscriptTarget = ResolvedReviewManuscriptTarget


@dataclasses.dataclass(frozen=True)
class ManuscriptIntakePolicy:
    """Static manuscript-subject intake rules for one command."""

    allowed_suffixes: frozenset[str]
    allow_external_targets: bool = False
    allow_interactive_standalone_intake: bool = False
    interactive_standalone_detail: str = ""


_SUPPORTED_MANUSCRIPT_ROOT_NAMES = frozenset({"paper", "manuscript", "draft"})
_PUBLICATION_INTERACTIVE_STANDALONE_DETAIL = (
    "no explicit review target supplied; interactive intake can prompt for a specific artifact path "
    "or use the current GPD project when available"
)
_WRITE_PAPER_EXTERNAL_AUTHORING_EXPLICIT_INPUTS = ["--intake path/to/write-paper-authoring-input.json"]
_WRITE_PAPER_EXTERNAL_AUTHORING_DETAIL = (
    "external authoring outside a project requires `--intake path/to/write-paper-authoring-input.json`"
)
_PROJECT_BACKED_ONLY_INTERACTIVE_SUBJECT_COMMANDS = frozenset({"gpd:literature-review"})


def _format_display_path(target: str | Path | None, *, cwd: Path) -> str:
    """Format a path for concise, user-facing preflight output."""

    if target is None:
        return ""
    raw_target = str(target)
    if not raw_target:
        return ""

    target_path = Path(raw_target).expanduser()
    if not target_path.is_absolute():
        target_path = cwd / target_path

    try:
        resolved_target = target_path.resolve(strict=False)
    except OSError:
        return target_path.as_posix()
    try:
        resolved_cwd = cwd.expanduser().resolve(strict=False)
    except OSError:
        resolved_cwd = cwd.expanduser()
    try:
        resolved_home = Path.home().expanduser().resolve(strict=False)
    except OSError:
        return resolved_target.as_posix()

    try:
        relative_to_cwd = resolved_target.relative_to(resolved_cwd)
    except ValueError:
        pass
    else:
        relative_text = relative_to_cwd.as_posix()
        return "." if relative_text in ("", ".") else f"./{relative_text}"

    try:
        relative_to_home = resolved_target.relative_to(resolved_home)
    except ValueError:
        return resolved_target.as_posix()

    relative_text = relative_to_home.as_posix()
    return "~" if relative_text in ("", ".") else f"~/{relative_text}"


def _resolve_subject_path(subject: str | None, *, base: Path) -> Path | None:
    """Resolve one raw subject string relative to *base* when possible."""

    if not isinstance(subject, str) or not subject.strip():
        return None
    target = Path(subject.strip()).expanduser()
    if not target.is_absolute():
        target = base / target
    return target.resolve(strict=False)


def _subject_is_relative_to(target: Path, base: Path) -> bool:
    """Return whether *target* stays under *base* after normalization."""

    try:
        target.resolve(strict=False).relative_to(base.resolve(strict=False))
    except ValueError:
        return False
    return True


def _supported_manuscript_root_for_target(project_root: Path, target: Path) -> Path | None:
    """Return the canonical manuscript root that owns *target*, when supported."""

    return resolve_supported_manuscript_root_for_target(project_root, target)


def _path_is_within_supported_manuscript_root(project_root: Path, target: Path) -> bool:
    """Return whether *target* lives under a supported manuscript root in *project_root*."""

    return path_is_within_supported_manuscript_root(project_root, target)


def _resolve_review_preflight_manuscript_target(
    cwd: Path,
    subject: str | None,
    *,
    allow_markdown: bool = True,
    restrict_to_supported_roots: bool = False,
    workspace_cwd: Path | None = None,
    allowed_suffixes: Collection[str] | None = None,
) -> ResolvedManuscriptTarget:
    """Resolve a review-preflight manuscript target with structured status details."""

    subject_base = (workspace_cwd or cwd).resolve(strict=False)
    return resolve_review_manuscript_target_details(
        cwd,
        subject,
        allow_markdown=allow_markdown,
        restrict_to_supported_roots=restrict_to_supported_roots,
        workspace_cwd=subject_base,
        allowed_suffixes=allowed_suffixes,
        display_cwd=subject_base,
    )


def _resolve_review_preflight_manuscript(
    cwd: Path,
    subject: str | None,
    *,
    allow_markdown: bool = True,
    restrict_to_supported_roots: bool = False,
    workspace_cwd: Path | None = None,
    allowed_suffixes: Collection[str] | None = None,
) -> tuple[Path | None, str]:
    """Resolve a review-preflight manuscript target from an explicit subject or defaults."""

    resolution = _resolve_review_preflight_manuscript_target(
        cwd,
        subject,
        allow_markdown=allow_markdown,
        restrict_to_supported_roots=restrict_to_supported_roots,
        workspace_cwd=workspace_cwd,
        allowed_suffixes=allowed_suffixes,
    )
    return resolution.manuscript, resolution.detail


def _command_review_contract(command: object) -> object | None:
    return getattr(command, "review_contract", None)


def _command_review_mode(command: object) -> str:
    return str(getattr(_command_review_contract(command), "review_mode", "") or "").strip()


def _command_subject_policy(command: object) -> object | None:
    command_policy = getattr(command, "command_policy", None)
    return getattr(command_policy, "subject_policy", None)


def _command_supporting_context_policy(command: object) -> object | None:
    command_policy = getattr(command, "command_policy", None)
    return getattr(command_policy, "supporting_context_policy", None)


def _command_policy_string_list(policy: object | None, field_name: str) -> list[str]:
    if policy is None:
        return []
    raw_value = getattr(policy, field_name, None)
    if not isinstance(raw_value, tuple | list):
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_value:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _command_policy_bool(policy: object | None, field_name: str) -> bool | None:
    if policy is None:
        return None
    value = getattr(policy, field_name, None)
    return value if isinstance(value, bool) else None


def _command_output_policy(command: object) -> object | None:
    command_policy = getattr(command, "command_policy", None)
    return getattr(command_policy, "output_policy", None)


def _command_subject_policy_string(command: object, field_name: str) -> str:
    subject_policy = _command_subject_policy(command)
    value = getattr(subject_policy, field_name, None) if subject_policy is not None else None
    return str(value or "").strip()


def _command_subject_resolution_mode(command: object) -> str:
    return _command_subject_policy_string(command, "resolution_mode")


def _command_subject_kind(command: object) -> str:
    return _command_subject_policy_string(command, "subject_kind")


def _command_has_typed_subject_policy(command: object) -> bool:
    return bool(_command_subject_resolution_mode(command))


def _command_effective_context_mode(command: object) -> str:
    """Return the runtime-authoritative context mode for one command."""

    if _command_review_mode(command) == "publication":
        supporting_context_policy = _command_supporting_context_policy(command)
        project_context_mode = str(getattr(supporting_context_policy, "project_context_mode", "") or "").strip()
        if project_context_mode:
            return project_context_mode
    return str(getattr(command, "context_mode", "project-required") or "project-required")


def _command_effective_project_reentry_mode(command: object) -> str:
    """Return the runtime-authoritative project re-entry mode for one command."""

    supporting_context_policy = _command_supporting_context_policy(command)
    project_reentry_mode = str(getattr(supporting_context_policy, "project_reentry_mode", "") or "").strip()
    if project_reentry_mode:
        return project_reentry_mode
    return "allowed" if bool(getattr(command, "project_reentry_capable", False)) else "disallowed"


_PUBLICATION_INPUT_KIND_LABELS = {
    "artifact_path": ["external artifact path"],
    "authoring_intake_manifest": _WRITE_PAPER_EXTERNAL_AUTHORING_EXPLICIT_INPUTS,
    "manuscript_path": ["manuscript path"],
    "manuscript_root": ["paper directory or managed manuscript root"],
    "paste": ["`paste`"],
    "paste_referee_report": ["`paste`"],
    "publication_artifact_path": ["external artifact path"],
    "referee_report_path": ["path to referee report"],
    "referee_report_source": ["path to referee report"],
}


def _publication_input_kind_labels(input_kind: str) -> list[str]:
    canonical = re.sub(r"[^a-z0-9]+", "_", input_kind.casefold()).strip("_")
    labels = _PUBLICATION_INPUT_KIND_LABELS.get(canonical)
    if labels is not None:
        return labels
    return [input_kind.replace("_", " ")]


def _command_explicit_input_labels_from_policy(command: object) -> list[str]:
    subject_policy = _command_subject_policy(command)
    labels: list[str] = []
    seen: set[str] = set()
    for input_kind in _command_policy_string_list(subject_policy, "explicit_input_kinds"):
        for label in _publication_input_kind_labels(input_kind):
            if label in seen:
                continue
            seen.add(label)
            labels.append(label)
    return labels


def _command_required_file_patterns(command: object) -> list[str]:
    """Return runtime-authoritative required file patterns for one command."""

    if _command_review_mode(command) == "publication":
        supporting_context_policy = _command_supporting_context_policy(command)
        if supporting_context_policy is not None:
            return _command_policy_string_list(supporting_context_policy, "required_file_patterns")
    requires = getattr(command, "requires", None)
    if not isinstance(requires, Mapping):
        return []
    raw_patterns = requires.get("files")
    if isinstance(raw_patterns, str):
        candidates = [raw_patterns]
    elif isinstance(raw_patterns, list):
        candidates = [item for item in raw_patterns if isinstance(item, str)]
    else:
        return []
    return [pattern.strip() for pattern in candidates if pattern.strip()]


def _command_required_files_present(
    project_root: Path,
    command: object,
) -> tuple[bool, list[str], list[str]]:
    """Return whether command-required files exist under *project_root*."""

    patterns = _command_required_file_patterns(command)
    if not patterns:
        return True, [], []

    matched_literals: list[str] = []
    matched_globs: list[str] = []
    missing_literals: list[str] = []
    missing_globs: list[str] = []
    for pattern in patterns:
        if glob.has_magic(pattern):
            try:
                if any(project_root.glob(pattern)):
                    matched_globs.append(pattern)
                else:
                    missing_globs.append(pattern)
            except ValueError:
                missing_globs.append(pattern)
            continue

        candidate = Path(pattern)
        resolved = candidate if candidate.is_absolute() else project_root / candidate
        if resolved.exists():
            matched_literals.append(pattern)
        else:
            missing_literals.append(pattern)

    glob_passed = not missing_globs or bool(matched_globs)
    passed = not missing_literals and glob_passed
    matched = [*matched_literals, *matched_globs]
    missing = [*missing_literals, *missing_globs]
    return passed, matched, missing


def _review_contract_declared_preflight_checks(contract: object) -> set[str]:
    """Return every preflight check declared directly or conditionally on one review contract."""

    declared_checks = set(getattr(contract, "preflight_checks", []) or [])
    for requirement in list(getattr(contract, "conditional_requirements", []) or []):
        declared_checks.update(list(getattr(requirement, "preflight_checks", []) or []))
        declared_checks.update(list(getattr(requirement, "blocking_preflight_checks", []) or []))
    return declared_checks


def _review_contract_requests_check(contract: object, check_name: str) -> bool:
    """Return whether the review contract explicitly asks the CLI to execute one check."""

    return check_name in _review_contract_declared_preflight_checks(contract)


def _command_explicit_manuscript_subject_kinds(command: object) -> set[str]:
    """Return explicit input kinds that can carry a manuscript subject."""

    subject_policy = _command_subject_policy(command)
    return set(_command_policy_string_list(subject_policy, "explicit_input_kinds")).intersection(
        {"artifact_path", "manuscript_path", "manuscript_root", "publication_artifact_path"}
    )


def _command_requires_manuscript_context(command: object) -> bool:
    """Return whether command context should use canonical manuscript resolution."""

    contract = getattr(command, "review_contract", None)
    preflight_checks = getattr(contract, "preflight_checks", ())
    return isinstance(preflight_checks, tuple | list) and "manuscript" in preflight_checks


def _command_requires_compiled_manuscript(command: object) -> bool:
    """Return whether manuscript checks must resolve to a compiled-submission surface."""

    contract = getattr(command, "review_contract", None)
    return _review_contract_requests_check(contract, "compiled_manuscript")


def _command_supports_positional_manuscript_subject(command: object) -> bool:
    """Return whether one command reads a positional argument as manuscript input."""

    contract = getattr(command, "review_contract", None)
    if not _command_requires_manuscript_context(command):
        return False
    if _review_contract_requests_check(contract, "referee_report_source"):
        return False
    return bool(_command_explicit_manuscript_subject_kinds(command) or _command_required_file_patterns(command))


def _command_supports_explicit_manuscript_subject(command: object) -> bool:
    """Return whether one command accepts manuscript-subject intake in any form."""

    if not _command_requires_manuscript_context(command):
        return False
    return bool(_command_explicit_manuscript_subject_kinds(command) or _command_required_file_patterns(command))


def _command_explicit_manuscript_argument(command: object, arguments: str | None) -> str | None:
    """Extract an explicit manuscript target from command arguments when present."""

    if not isinstance(arguments, str) or not arguments.strip():
        return None

    flagged = _flag_values(arguments, "--manuscript")
    if flagged:
        return flagged[-1]

    if not _command_supports_positional_manuscript_subject(command):
        return None

    positionals = _positional_tokens(arguments, flags_with_values=("--manuscript", "--report"))
    return positionals[0] if positionals else None


def _command_referee_report_arguments(command: object, arguments: str | None) -> tuple[str, ...]:
    """Extract explicit referee-report sources from command arguments when present."""

    contract = getattr(command, "review_contract", None)
    if not _review_contract_requests_check(contract, "referee_report_source"):
        return ()
    if not isinstance(arguments, str) or not arguments.strip():
        return ()

    flagged = tuple(value for value in _flag_values(arguments, "--report") if value and value != "paste")
    if flagged:
        return flagged

    positionals = _positional_tokens(arguments, flags_with_values=("--manuscript", "--report"))
    return tuple(token for token in positionals if token and token != "paste")


def _command_manuscript_intake_policy(command: object) -> ManuscriptIntakePolicy:
    """Return manuscript-target intake rules derived from command metadata."""

    subject_policy = _command_subject_policy(command)
    allowed_suffixes = set(_command_policy_string_list(subject_policy, "allowed_suffixes"))
    if not allowed_suffixes:
        allowed_suffixes = {".tex"}
        if not _command_requires_compiled_manuscript(command):
            allowed_suffixes.add(".md")
    allow_external_targets = _command_policy_bool(subject_policy, "allow_external_subjects")
    allow_interactive_without_subject = _command_policy_bool(
        subject_policy,
        "allow_interactive_without_subject",
    )
    return ManuscriptIntakePolicy(
        allowed_suffixes=frozenset(allowed_suffixes),
        allow_external_targets=bool(allow_external_targets),
        allow_interactive_standalone_intake=bool(allow_interactive_without_subject),
        interactive_standalone_detail=(
            _PUBLICATION_INTERACTIVE_STANDALONE_DETAIL if allow_interactive_without_subject else ""
        ),
    )


def _command_explicit_manuscript_suffixes(command: object) -> frozenset[str]:
    """Return the allowed explicit manuscript suffixes for one command."""

    return _command_manuscript_intake_policy(command).allowed_suffixes


def _command_allows_external_manuscript_targets(command: object) -> bool:
    """Return whether a command may accept explicit manuscript targets outside supported roots."""

    return _command_manuscript_intake_policy(command).allow_external_targets


def _command_allows_interactive_standalone_intake(command: object) -> bool:
    """Return whether a project-aware command may prompt for standalone inputs after launch."""

    return _command_manuscript_intake_policy(command).allow_interactive_standalone_intake


def _command_explicit_manuscript_subject_uses_supported_roots(command: object) -> bool:
    """Return whether explicit manuscript arguments must stay under supported manuscript roots."""

    if not _command_supports_explicit_manuscript_subject(command):
        return False
    if _command_allows_external_manuscript_targets(command):
        return False
    subject_policy = _command_subject_policy(command)
    supported_roots = {root for root in _command_policy_string_list(subject_policy, "supported_roots") if root}
    if not supported_roots:
        supported_roots = {
            Path(pattern).parts[0] for pattern in _command_required_file_patterns(command) if Path(pattern).parts
        }
    return bool(supported_roots) and supported_roots <= _SUPPORTED_MANUSCRIPT_ROOT_NAMES


def _command_allows_manuscript_bootstrap(command: object) -> bool:
    """Return whether missing manuscript roots are expected to be bootstrapped."""

    subject_policy = _command_subject_policy(command)
    bootstrap_allowed = _command_policy_bool(subject_policy, "bootstrap_allowed")
    if bootstrap_allowed is not None:
        return bootstrap_allowed
    contract = getattr(command, "review_contract", None)
    if getattr(command, "name", "") == "gpd:peer-review":
        return False
    return (
        _command_requires_manuscript_context(command)
        and not _command_required_file_patterns(command)
        and not _review_contract_requests_check(contract, "compiled_manuscript")
        and not _review_contract_requests_check(contract, "referee_report_source")
    )


def _command_allows_interactive_subject_intake(command: object) -> bool:
    """Return whether a command may launch without a concrete subject and ask interactively."""

    if _command_requires_manuscript_context(command):
        return _command_allows_interactive_standalone_intake(command)
    subject_policy = _command_subject_policy(command)
    return bool(_command_policy_bool(subject_policy, "allow_interactive_without_subject"))


def _command_allows_standalone_interactive_subject_intake(command: object) -> bool:
    """Return whether empty standalone command-context may defer subject selection to interaction."""

    if not _command_allows_interactive_subject_intake(command):
        return False
    return str(getattr(command, "name", "") or "") not in _PROJECT_BACKED_ONLY_INTERACTIVE_SUBJECT_COMMANDS


def _command_interactive_subject_detail(command: object, explicit_inputs: list[str]) -> str:
    """Return the standardized detail string for interactive subject intake."""

    if _command_requires_manuscript_context(command):
        return _command_manuscript_intake_policy(command).interactive_standalone_detail
    if not explicit_inputs:
        explicit_inputs = ["a concrete subject"]
    if len(explicit_inputs) == 1:
        subject_text = explicit_inputs[0]
    elif len(explicit_inputs) == 2:
        subject_text = f"{explicit_inputs[0]} or {explicit_inputs[1]}"
    else:
        subject_text = ", ".join(explicit_inputs[:-1]) + f", or {explicit_inputs[-1]}"
    return f"no explicit subject supplied; interactive intake can prompt for {subject_text}"


def _command_required_files_override_detail(
    project_root: Path,
    command: object,
    arguments: str | None,
    *,
    workspace_cwd: Path | None = None,
    resolved_subject: ResolvedCommandSubject | None = None,
) -> str | None:
    """Return a detail string when explicit review inputs satisfy required-file gating."""

    display_cwd = (workspace_cwd or project_root).resolve(strict=False)
    if not _command_supports_explicit_manuscript_subject(command):
        return None
    if resolved_subject is not None:
        if (
            not resolved_subject.explicit_input
            or resolved_subject.subject_kind != "manuscript"
            or resolved_subject.status != "resolved"
            or resolved_subject.ownership_mode not in {"project_backed", "project_reentry_selected"}
            or resolved_subject.target_path is None
            or resolved_subject.target_path.is_dir()
        ):
            return None
        return (
            "explicit manuscript target satisfies command context: "
            f"{_format_display_path(resolved_subject.target_path, cwd=display_cwd)}"
        )
    if not isinstance(arguments, str) or not arguments.strip():
        return None

    manuscript_argument = _command_explicit_manuscript_argument(command, arguments)
    if manuscript_argument is None:
        return None

    manuscript, _ = _resolve_review_preflight_manuscript(
        project_root,
        manuscript_argument,
        allow_markdown=not _command_requires_compiled_manuscript(command),
        restrict_to_supported_roots=_command_explicit_manuscript_subject_uses_supported_roots(command),
        workspace_cwd=workspace_cwd,
        allowed_suffixes=_command_explicit_manuscript_suffixes(command),
    )
    if manuscript is None:
        return None
    return f"explicit manuscript target satisfies command context: {_format_display_path(manuscript, cwd=display_cwd)}"


def _resolved_subject_manuscript_entrypoint(
    resolved_subject: ResolvedCommandSubject | None,
) -> Path | None:
    """Return the resolved manuscript file for subject-scoped commands."""

    if (
        resolved_subject is None
        or resolved_subject.subject_kind != "manuscript"
        or resolved_subject.status != "resolved"
        or resolved_subject.target_path is None
        or resolved_subject.target_path.is_dir()
    ):
        return None
    return resolved_subject.target_path


def _command_manuscript_bootstrap_detail() -> str:
    """Return the canonical bootstrap detail for manuscript-scaffolding commands."""

    return (
        "no manuscript entrypoint found under paper/, manuscript/, or draft/; "
        "fresh bootstrap is allowed and will scaffold a topic-specific manuscript stem under ./paper/"
    )


def _resolved_project_root_for_subject(context_root: Path) -> Path | None:
    """Return the project root bound to one subject-resolution context, if any."""

    candidate = context_root.resolve(strict=False)
    return candidate if ProjectLayout(candidate).project_md.exists() else None


def _command_subject_base_ownership_mode(
    *,
    resolved_project_root: Path | None,
    project_root_source: str | None,
    project_root_auto_selected: bool,
) -> str:
    """Return the default subject ownership mode before explicit-target overrides."""

    if (
        resolved_project_root is not None
        and project_root_auto_selected
        and str(project_root_source or "").strip() == "recent_project"
    ):
        return "project_reentry_selected"
    if resolved_project_root is not None:
        return "project_backed"
    return "workspace_locked"


def _resolve_review_knowledge_target(
    context_root: Path,
    subject: str | None,
    *,
    workspace_cwd: Path | None = None,
) -> tuple[str, Path | None, str]:
    """Resolve one canonical review-knowledge target under ``GPD/knowledge``."""

    workspace_root = (workspace_cwd or context_root).resolve(strict=False)
    if not isinstance(subject, str) or not subject.strip():
        return "missing", None, "missing explicit knowledge target"

    tokens = _split_command_arguments(subject)
    candidate = next((token for token in tokens if token and not token.startswith("-")), "")
    if not candidate:
        return "missing", None, "missing explicit knowledge target"

    knowledge_dir = context_root / "GPD" / "knowledge"
    if _looks_like_review_knowledge_id_token(candidate):
        target_path = (knowledge_dir / f"{candidate}.md").resolve(strict=False)
        return (
            "resolved",
            target_path,
            f"canonical knowledge id resolves to {_format_display_path(target_path, cwd=workspace_root)}",
        )

    if not _looks_like_digest_knowledge_path_token(candidate):
        return "invalid", None, "review target must be a canonical K-* id or GPD/knowledge/{knowledge_id}.md path"

    target_path = (_resolve_subject_path(candidate, base=workspace_root) or (workspace_root / candidate)).resolve(
        strict=False
    )
    try:
        relative = target_path.relative_to(context_root.resolve(strict=False))
    except ValueError:
        return "invalid", target_path, "review target must resolve under the current workspace's GPD/knowledge/"

    if not (
        len(relative.parts) == 3
        and relative.parts[0] == "GPD"
        and relative.parts[1] == "knowledge"
        and target_path.suffix.lower() == ".md"
        and target_path.stem.startswith("K-")
        and normalize_ascii_slug(target_path.stem[2:]) == target_path.stem[2:]
    ):
        return "invalid", target_path, "review target must resolve to canonical GPD/knowledge/{knowledge_id}.md"
    return (
        "resolved",
        target_path,
        f"canonical knowledge target {_format_display_path(target_path, cwd=workspace_root)}",
    )


def _nonpublication_subject_ownership_mode(
    *,
    target_path: Path | None,
    resolved_project_root: Path | None,
    base_ownership_mode: str,
) -> str:
    """Return ownership mode for a non-publication resolved subject."""

    if target_path is None:
        return base_ownership_mode
    if resolved_project_root is None:
        return "workspace_locked"
    try:
        target_path.resolve(strict=False).relative_to(resolved_project_root.resolve(strict=False))
    except ValueError:
        return "external_subject"
    return base_ownership_mode


def _build_nonpublication_resolved_command_subject(
    project_root: Path,
    command: object,
    subject: str | None,
    *,
    workspace_cwd: Path | None = None,
    project_root_source: str | None = None,
    project_root_auto_selected: bool = False,
    reentry_mode: str | None = None,
) -> ResolvedCommandSubject | None:
    """Resolve the shared subject envelope for typed non-publication commands."""

    if _command_requires_manuscript_context(command):
        return None
    resolution_mode = _command_subject_resolution_mode(command)
    if not resolution_mode:
        return None

    workspace_root = (workspace_cwd or project_root).resolve(strict=False)
    context_root = project_root.resolve(strict=False)
    resolved_project_root = _resolved_project_root_for_subject(context_root)
    resolved_project_root_source = project_root_source or ("workspace" if resolved_project_root is not None else None)
    ancestor_walked_up = (
        resolved_project_root is not None
        and resolved_project_root != workspace_root
        and _subject_is_relative_to(workspace_root, resolved_project_root)
    )
    base_ownership_mode = _command_subject_base_ownership_mode(
        resolved_project_root=resolved_project_root,
        project_root_source=resolved_project_root_source,
        project_root_auto_selected=project_root_auto_selected,
    )
    explicit_inputs = _command_explicit_input_labels_from_policy(command)
    subject_kind = _command_subject_kind(command) or "subject"

    allow_interactive_without_subject = _command_allows_interactive_subject_intake(command) and (
        resolved_project_root is not None or _command_allows_standalone_interactive_subject_intake(command)
    )

    if not (isinstance(subject, str) and subject.strip()) and allow_interactive_without_subject:
        return ResolvedCommandSubject(
            command=str(getattr(command, "name", "") or ""),
            workspace_root=workspace_root,
            resolved_project_root=resolved_project_root,
            context_root=context_root,
            target_path=None,
            target_root=None,
            subject_kind=subject_kind,
            ownership_mode=base_ownership_mode,
            status="interactive",
            exists=False,
            explicit_input=False,
            project_root_source=resolved_project_root_source,
            project_root_auto_selected=project_root_auto_selected,
            reentry_mode=reentry_mode,
            ancestor_walked_up=ancestor_walked_up,
            detail=_command_interactive_subject_detail(command, explicit_inputs),
        )

    tokens: list[str]
    if resolution_mode in {"phase_number", "phase_or_topic"}:
        tokens = _positional_tokens(subject, flags_with_values=("--depth", "-d"))
    else:
        tokens = _positional_tokens(subject)
    if not tokens:
        if allow_interactive_without_subject:
            return ResolvedCommandSubject(
                command=str(getattr(command, "name", "") or ""),
                workspace_root=workspace_root,
                resolved_project_root=resolved_project_root,
                context_root=context_root,
                target_path=None,
                target_root=None,
                subject_kind=subject_kind,
                ownership_mode=base_ownership_mode,
                status="interactive",
                exists=False,
                explicit_input=False,
                project_root_source=resolved_project_root_source,
                project_root_auto_selected=project_root_auto_selected,
                reentry_mode=reentry_mode,
                ancestor_walked_up=ancestor_walked_up,
                detail=_command_interactive_subject_detail(command, explicit_inputs),
            )
        return ResolvedCommandSubject(
            command=str(getattr(command, "name", "") or ""),
            workspace_root=workspace_root,
            resolved_project_root=resolved_project_root,
            context_root=context_root,
            target_path=None,
            target_root=None,
            subject_kind=subject_kind,
            ownership_mode=base_ownership_mode,
            status="missing",
            exists=False,
            explicit_input=False,
            project_root_source=resolved_project_root_source,
            project_root_auto_selected=project_root_auto_selected,
            reentry_mode=reentry_mode,
            ancestor_walked_up=ancestor_walked_up,
            detail=f"missing explicit subject ({', '.join(explicit_inputs or ['subject'])})",
        )

    target_path: Path | None = None
    target_root: Path | None = None
    detail = "explicit subject supplied"
    status = "resolved"

    if resolution_mode in {"knowledge_review_target", "explicit_current_workspace_canonical_target"}:
        status, target_path, detail = _resolve_review_knowledge_target(
            context_root,
            subject,
            workspace_cwd=workspace_root,
        )
        if target_path is not None:
            target_root = target_path.parent
    elif resolution_mode == "knowledge_input":
        first = tokens[0]
        if _looks_like_digest_knowledge_path_token(first):
            target_path = (_resolve_subject_path(first, base=workspace_root) or (workspace_root / first)).resolve(
                strict=False
            )
            target_root = target_path if target_path.is_dir() else target_path.parent
            detail = f"explicit knowledge input path {_format_display_path(target_path, cwd=workspace_root)}"
        elif _looks_like_digest_knowledge_arxiv_token(first):
            detail = f"explicit arXiv knowledge input {first}"
        else:
            detail = "explicit knowledge topic supplied"
    elif resolution_mode in {"compare_subject", "compare_experiment_subject"}:
        first = tokens[0]
        if _looks_like_digest_knowledge_path_token(first):
            target_path = (_resolve_subject_path(first, base=workspace_root) or (workspace_root / first)).resolve(
                strict=False
            )
            target_root = target_path if target_path.is_dir() else target_path.parent
            detail = f"explicit comparison target {_format_display_path(target_path, cwd=workspace_root)}"
        else:
            detail = "explicit comparison target supplied"
    elif resolution_mode == "explanation_input":
        first = tokens[0]
        if _looks_like_digest_knowledge_path_token(first):
            target_path = (_resolve_subject_path(first, base=workspace_root) or (workspace_root / first)).resolve(
                strict=False
            )
            target_root = target_path if target_path.is_dir() else target_path.parent
            detail = f"explicit explanation anchor {_format_display_path(target_path, cwd=workspace_root)}"
        else:
            detail = "explicit explanation subject supplied"
    elif resolution_mode == "phase_number":
        first = tokens[0]
        subject_kind = "phase"
        if re.fullmatch(r"\d+(?:\.\d+)*", first):
            detail = f"explicit phase subject {first}"
        else:
            status = "invalid"
            detail = f"invalid phase-number subject {first!r}"
    elif resolution_mode == "phase_or_topic":
        first = tokens[0]
        if re.fullmatch(r"\d+(?:\.\d+)*", first):
            subject_kind = "phase"
            detail = f"explicit phase subject {first}"
        else:
            detail = "explicit discovery topic supplied"
    elif resolution_mode == "literature_topic":
        detail = "explicit literature-review topic supplied"

    ownership_mode = _nonpublication_subject_ownership_mode(
        target_path=target_path,
        resolved_project_root=resolved_project_root,
        base_ownership_mode=base_ownership_mode,
    )

    return ResolvedCommandSubject(
        command=str(getattr(command, "name", "") or ""),
        workspace_root=workspace_root,
        resolved_project_root=resolved_project_root,
        context_root=context_root,
        target_path=target_path,
        target_root=target_root,
        subject_kind=subject_kind,
        ownership_mode=ownership_mode,
        status=status,
        exists=target_path.exists() if target_path is not None else False,
        explicit_input=True,
        project_root_source=resolved_project_root_source,
        project_root_auto_selected=project_root_auto_selected,
        reentry_mode=reentry_mode,
        ancestor_walked_up=ancestor_walked_up,
        detail=detail,
    )


def _resolve_write_paper_external_authoring_intake(
    project_root: Path,
    arguments: str | None,
    *,
    workspace_cwd: Path | None = None,
) -> WritePaperExternalAuthoringIntakeResolution | None:
    """Validate the bounded external-authoring intake manifest for ``gpd:write-paper``."""

    return resolve_write_paper_external_authoring_intake(
        project_root,
        arguments,
        workspace_cwd=workspace_cwd,
    )


def _build_resolved_command_subject(
    project_root: Path,
    command: object,
    subject: str | None,
    *,
    workspace_cwd: Path | None = None,
    project_root_source: str | None = None,
    project_root_auto_selected: bool = False,
    reentry_mode: str | None = None,
) -> ResolvedCommandSubject | None:
    """Resolve the shared subject envelope for publication/manuscript-aware commands."""

    generic_resolution = _build_nonpublication_resolved_command_subject(
        project_root,
        command,
        subject,
        workspace_cwd=workspace_cwd,
        project_root_source=project_root_source,
        project_root_auto_selected=project_root_auto_selected,
        reentry_mode=reentry_mode,
    )
    if generic_resolution is not None:
        return generic_resolution

    if not _command_requires_manuscript_context(command):
        return None

    workspace_root = (workspace_cwd or project_root).resolve(strict=False)
    context_root = project_root.resolve(strict=False)
    resolved_project_root = _resolved_project_root_for_subject(context_root)
    resolved_project_root_source = project_root_source or ("workspace" if resolved_project_root is not None else None)
    ancestor_walked_up = (
        resolved_project_root is not None
        and resolved_project_root != workspace_root
        and _subject_is_relative_to(workspace_root, resolved_project_root)
    )
    base_ownership_mode = _command_subject_base_ownership_mode(
        resolved_project_root=resolved_project_root,
        project_root_source=resolved_project_root_source,
        project_root_auto_selected=project_root_auto_selected,
    )
    if (
        str(getattr(command, "name", "") or "") == "gpd:write-paper"
        and resolved_project_root is not None
        and _has_write_paper_external_authoring_intake(subject)
    ):
        intake_argument = write_paper_external_authoring_intake_argument(subject)
        intake_path = _resolve_subject_path(intake_argument, base=workspace_root) if intake_argument else None
        return ResolvedCommandSubject(
            command=str(getattr(command, "name", "") or ""),
            workspace_root=workspace_root,
            resolved_project_root=resolved_project_root,
            context_root=context_root,
            target_path=intake_path,
            target_root=None,
            subject_kind="publication",
            ownership_mode="external_authoring_intake",
            status="invalid",
            exists=intake_path.exists() if intake_path is not None else False,
            explicit_input=True,
            project_root_source=resolved_project_root_source,
            project_root_auto_selected=project_root_auto_selected,
            reentry_mode=reentry_mode,
            ancestor_walked_up=ancestor_walked_up,
            detail=reject_write_paper_intake_inside_project_detail(),
        )

    if str(getattr(command, "name", "") or "") == "gpd:write-paper" and resolved_project_root is None:
        intake_resolution = _resolve_write_paper_external_authoring_intake(
            context_root,
            subject,
            workspace_cwd=workspace_root,
        )
        if intake_resolution is None:
            return ResolvedCommandSubject(
                command=str(getattr(command, "name", "") or ""),
                workspace_root=workspace_root,
                resolved_project_root=resolved_project_root,
                context_root=context_root,
                target_path=None,
                target_root=None,
                subject_kind="publication",
                ownership_mode=base_ownership_mode,
                status="missing",
                exists=False,
                explicit_input=False,
                project_root_source=resolved_project_root_source,
                project_root_auto_selected=project_root_auto_selected,
                reentry_mode=reentry_mode,
                ancestor_walked_up=ancestor_walked_up,
                detail=_WRITE_PAPER_EXTERNAL_AUTHORING_DETAIL,
            )

        intake_target_root = (
            intake_resolution.manuscript_root
            or intake_resolution.intake_root
            or (intake_resolution.intake_path.parent if intake_resolution.intake_path is not None else None)
        )
        if intake_resolution.status == "resolved":
            return ResolvedCommandSubject(
                command=str(getattr(command, "name", "") or ""),
                workspace_root=workspace_root,
                resolved_project_root=resolved_project_root,
                context_root=context_root,
                target_path=intake_resolution.intake_path,
                target_root=intake_resolution.manuscript_root,
                subject_kind="publication",
                ownership_mode="external_authoring_intake",
                status="bootstrap",
                exists=intake_resolution.intake_path is not None and intake_resolution.intake_path.exists(),
                explicit_input=True,
                project_root_source=resolved_project_root_source,
                project_root_auto_selected=project_root_auto_selected,
                reentry_mode=reentry_mode,
                ancestor_walked_up=ancestor_walked_up,
                detail=intake_resolution.detail,
            )

        return ResolvedCommandSubject(
            command=str(getattr(command, "name", "") or ""),
            workspace_root=workspace_root,
            resolved_project_root=resolved_project_root,
            context_root=context_root,
            target_path=intake_resolution.intake_path,
            target_root=intake_target_root,
            subject_kind="publication",
            ownership_mode="external_authoring_intake",
            status=intake_resolution.status,
            exists=intake_resolution.intake_path is not None and intake_resolution.intake_path.exists(),
            explicit_input=True,
            project_root_source=resolved_project_root_source,
            project_root_auto_selected=project_root_auto_selected,
            reentry_mode=reentry_mode,
            ancestor_walked_up=ancestor_walked_up,
            detail=intake_resolution.detail,
        )
    manuscript_subject = _command_explicit_manuscript_argument(command, subject)

    if (
        _command_supports_explicit_manuscript_subject(command)
        and not (isinstance(subject, str) and subject.strip())
        and _command_allows_interactive_standalone_intake(command)
        and not ProjectLayout(context_root).project_md.exists()
    ):
        return ResolvedCommandSubject(
            command=str(getattr(command, "name", "") or ""),
            workspace_root=workspace_root,
            resolved_project_root=resolved_project_root,
            context_root=context_root,
            target_path=None,
            target_root=None,
            subject_kind="manuscript",
            ownership_mode=base_ownership_mode,
            status="interactive",
            exists=False,
            explicit_input=False,
            project_root_source=resolved_project_root_source,
            project_root_auto_selected=project_root_auto_selected,
            reentry_mode=reentry_mode,
            ancestor_walked_up=ancestor_walked_up,
            detail=_command_manuscript_intake_policy(command).interactive_standalone_detail,
        )

    target_resolution = _resolve_review_preflight_manuscript_target(
        context_root,
        manuscript_subject if _command_supports_explicit_manuscript_subject(command) else None,
        allow_markdown=not _command_requires_compiled_manuscript(command),
        restrict_to_supported_roots=_command_explicit_manuscript_subject_uses_supported_roots(command),
        workspace_cwd=workspace_root,
        allowed_suffixes=_command_explicit_manuscript_suffixes(command),
    )
    target_path = target_resolution.manuscript or target_resolution.requested_target
    target_root = target_resolution.manuscript_root
    if target_root is None and target_path is not None:
        target_root = target_path if target_path.is_dir() else target_path.parent

    status = target_resolution.status
    detail = target_resolution.detail
    if (
        _command_allows_manuscript_bootstrap(command)
        and target_resolution.requested_target is None
        and status == "missing"
    ):
        status = "bootstrap"
        detail = _command_manuscript_bootstrap_detail()
        target_root = context_root / "paper"

    ownership_mode = base_ownership_mode
    ownership_target = target_resolution.manuscript or target_resolution.requested_target
    if ownership_target is not None and (
        resolved_project_root is None
        or not _path_is_within_supported_manuscript_root(resolved_project_root, ownership_target)
    ):
        ownership_mode = "external_artifact"

    return ResolvedCommandSubject(
        command=str(getattr(command, "name", "") or ""),
        workspace_root=workspace_root,
        resolved_project_root=resolved_project_root,
        context_root=context_root,
        target_path=target_path,
        target_root=target_root,
        subject_kind="manuscript",
        ownership_mode=ownership_mode,
        status=status,
        exists=target_path.exists() if target_path is not None else False,
        explicit_input=target_resolution.requested_target is not None,
        project_root_source=resolved_project_root_source,
        project_root_auto_selected=project_root_auto_selected,
        reentry_mode=reentry_mode,
        ancestor_walked_up=ancestor_walked_up,
        detail=detail,
    )


def _command_context_manuscript_check(
    project_root: Path,
    command: object,
    arguments: str | None,
    *,
    workspace_cwd: Path | None = None,
    resolved_subject: ResolvedCommandSubject | None = None,
) -> tuple[bool, str] | None:
    """Return a canonical manuscript-context check for publication commands."""

    if not _command_requires_manuscript_context(command):
        return None
    subject_resolution = resolved_subject or _build_resolved_command_subject(
        project_root,
        command,
        arguments,
        workspace_cwd=workspace_cwd,
    )
    if subject_resolution is None:
        return None
    return subject_resolution.status in {"resolved", "bootstrap"}, subject_resolution.detail
