"""Typer-free command preflight routing helpers."""

from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Callable, Mapping
from difflib import SequenceMatcher
from pathlib import Path

from gpd.command_labels import canonical_command_label, parse_command_label
from gpd.core.command_arguments import (
    _PROJECT_AWARE_EXPLICIT_INPUT_PREDICATES,
    _has_simple_positional_inputs,
    _has_write_paper_external_authoring_intake,
    _split_command_arguments,
)
from gpd.core.command_subjects import (
    ResolvedCommandSubject,
    _build_resolved_command_subject,
    _command_allows_external_manuscript_targets,
    _command_allows_interactive_subject_intake,
    _command_context_manuscript_check,
    _command_effective_context_mode,
    _command_effective_project_reentry_mode,
    _command_explicit_input_labels_from_policy,
    _command_has_typed_subject_policy,
    _command_interactive_subject_detail,
    _command_output_policy,
    _command_required_file_patterns,
    _command_required_files_override_detail,
    _command_required_files_present,
    _command_requires_manuscript_context,
    _command_review_contract,
    _command_review_mode,
    _format_display_path,
    _resolved_subject_manuscript_entrypoint,
    _supported_manuscript_root_for_target,
)
from gpd.core.constants import PLANNING_DIR_NAME, PUBLICATION_DIR_NAME, PUBLICATION_MANUSCRIPT_DIR_NAME, ProjectLayout
from gpd.core.errors import GPDError
from gpd.core.peer_review_mode import PEER_REVIEW_INVALID_SUBJECT_MODE, resolve_peer_review_mode_details
from gpd.core.project_reentry import (
    ProjectReentryResolution,
    recoverable_project_context,
    resolve_project_reentry,
)
from gpd.core.public_surface_contract import local_cli_resume_recent_command
from gpd.core.root_resolution import resolve_project_root
from gpd.core.utils import normalize_ascii_slug


@dataclasses.dataclass(frozen=True)
class PublicationSubjectPreflightPolicy:
    """Publication preflight relaxations and scope overrides derived from the active subject."""

    active_scopes: frozenset[str] = frozenset()
    relaxed_checks: frozenset[str] = frozenset()
    optional_checks: frozenset[str] = frozenset()
    detail_overrides: Mapping[str, str] = dataclasses.field(default_factory=dict)
    required_outputs: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    blocking_conditions: tuple[str, ...] = ()

    def relaxes(self, check_name: str) -> bool:
        return check_name in self.relaxed_checks

    def makes_missing_optional(self, check_name: str) -> bool:
        return check_name in self.optional_checks

    def passes_when_missing(self, check_name: str) -> bool:
        return self.relaxes(check_name) or self.makes_missing_optional(check_name)

    def detail(self, check_name: str) -> str | None:
        return self.detail_overrides.get(check_name)

    def blocking(self, check_name: str, *, missing: bool = False, default: bool = True) -> bool:
        if self.relaxes(check_name):
            return False
        if missing and self.makes_missing_optional(check_name):
            return False
        return default

    def missing_detail(self, check_name: str, *, default: str) -> str:
        detail = self.detail(check_name)
        return detail if detail is not None else default


@dataclasses.dataclass(frozen=True)
class CommandContextCheck:
    name: str
    passed: bool
    blocking: bool
    detail: str


@dataclasses.dataclass(frozen=True)
class CommandContextPreflightResult:
    command: str
    context_mode: str
    passed: bool
    project_exists: bool
    explicit_inputs: list[str]
    guidance: str
    checks: list[CommandContextCheck]
    resolved_mode: str = ""
    mode_reason: str = ""
    validated_surface: str = "public_runtime_command_surface"
    public_runtime_command_prefix: str = ""
    local_cli_equivalence_guaranteed: bool = False
    dispatch_note: str = ""
    resolved_subject: ResolvedCommandSubject | None = None
    selected_publication_root: str | None = None
    selected_review_root: str | None = None


@dataclasses.dataclass(frozen=True)
class CommandRuntimeSurfaceMetadata:
    validated_surface: str = "public_runtime_command_surface"
    public_runtime_command_prefix: str = ""
    init_command: str = "the active runtime's `new-project` command"
    dispatch_note: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class CommandLookupSuggestion:
    command: str
    canonical_command: str
    slug: str
    reason: str = "closest registered command"


@dataclasses.dataclass(frozen=True, slots=True)
class CommandLookupAction:
    label: str
    command: str
    detail: str


@dataclasses.dataclass(frozen=True, slots=True)
class CommandLookupErrorPayload:
    ok: bool
    passed: bool
    error: str
    requested_command: str
    normalized_command: str
    canonical_command: str
    slug: str
    known_command: bool
    allowed_preview: list[str]
    suggestions: list[CommandLookupSuggestion]
    guidance: str
    primary_action: CommandLookupAction
    safe_alternatives: list[CommandLookupAction]
    debug_actions: list[CommandLookupAction]
    validated_surface: str = "public_runtime_command_surface"
    public_runtime_command_prefix: str = ""
    dispatch_note: str = ""


class CommandLookupError(GPDError):
    """User-facing registry lookup failure with machine-readable remediation."""

    def __init__(self, payload: CommandLookupErrorPayload) -> None:
        self.payload = payload
        super().__init__(format_command_lookup_error(payload))


_EXTERNAL_ARTIFACT_OPTIONAL_DETAILS = {
    "project_state": "external artifact review: project state is optional and is not required to start review",
    "roadmap": "external artifact review: roadmap is optional",
    "conventions": "external artifact review: project conventions are optional",
    "research_artifacts": "external artifact review: phase summaries or milestone digests are optional",
    "verification_reports": "external artifact review: verification reports are optional",
    "artifact_manifest": "no ARTIFACT-MANIFEST.json found near the manuscript; external artifact review can proceed without it",
    "bibliography_audit": "no BIBLIOGRAPHY-AUDIT.json found near the manuscript; external artifact review can proceed without it",
    "bibliography_audit_clean": "bibliography audit cleanliness is optional for external artifact review",
    "reproducibility_manifest": (
        "no reproducibility manifest found near the manuscript; external artifact review can proceed without it"
    ),
    "reproducibility_ready": "reproducibility readiness is optional for external artifact review",
    "manuscript_proof_review": (
        "prior staged manuscript proof review is optional in external artifact mode; "
        "theorem-bearing claims will be audited in this review round if detected"
    ),
}
_WRITE_PAPER_EXTERNAL_AUTHORING_OPTIONAL_DETAILS = {
    "project_state": "external authoring intake: project state is optional because the intake manifest is authoritative",
    "roadmap": "external authoring intake: roadmap is optional because the intake manifest supplies the draft scope",
    "conventions": "external authoring intake: project conventions are optional before the manuscript exists",
    "research_artifacts": (
        "external authoring intake: milestone digests and phase summaries are optional because claims and evidence "
        "come from the intake manifest"
    ),
    "verification_reports": (
        "external authoring intake: project verification reports are optional because claim-to-evidence bindings come "
        "from the intake manifest"
    ),
    "artifact_manifest": (
        "no ARTIFACT-MANIFEST.json found yet; the external authoring lane emits it after manuscript scaffolding"
    ),
    "bibliography_audit": (
        "no BIBLIOGRAPHY-AUDIT.json found yet; the external authoring lane emits it after bibliography scaffolding"
    ),
    "bibliography_audit_clean": "bibliography audit cleanliness is optional before the first external-authoring draft",
    "reproducibility_manifest": (
        "no reproducibility manifest found yet; the external authoring lane emits it after manuscript scaffolding"
    ),
    "reproducibility_ready": "reproducibility readiness is optional before the first external-authoring draft",
    "manuscript_proof_review": (
        "prior staged manuscript proof review is optional before the first external-authoring draft; "
        "proof review begins after the manuscript is authored"
    ),
}


def _publication_subject_slug_for_manuscript_entrypoint(
    project_root: Path,
    manuscript_entrypoint: Path,
) -> str:
    """Return the managed publication slug for one manuscript entrypoint."""

    manuscript_root = _supported_manuscript_root_for_target(project_root, manuscript_entrypoint)
    if manuscript_root is not None:
        try:
            relative_root = manuscript_root.resolve(strict=False).relative_to(project_root.resolve(strict=False))
        except ValueError:
            relative_root = None
        if (
            relative_root is not None
            and len(relative_root.parts) == 4
            and relative_root.parts[0] == PLANNING_DIR_NAME
            and relative_root.parts[1] == PUBLICATION_DIR_NAME
            and relative_root.parts[3] == PUBLICATION_MANUSCRIPT_DIR_NAME
        ):
            return relative_root.parts[2]

    resolved_root = project_root.resolve(strict=False)
    resolved_entrypoint = manuscript_entrypoint.resolve(strict=False)
    try:
        label = resolved_entrypoint.relative_to(resolved_root).as_posix()
    except ValueError:
        label = resolved_entrypoint.as_posix()
    slug_source = label[: -len(resolved_entrypoint.suffix)] if resolved_entrypoint.suffix else label
    slug = normalize_ascii_slug(slug_source.replace("/", "-")) or "manuscript"
    slug = slug[:48].rstrip("-") or "manuscript"
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def _managed_publication_slug_for_target(project_root: Path, target: Path | None) -> str | None:
    """Return the existing managed publication slug for a target under GPD/publication."""

    if target is None:
        return None
    try:
        relative = target.resolve(strict=False).relative_to(project_root.resolve(strict=False))
    except ValueError:
        return None
    parts = relative.parts
    if (
        len(parts) >= 4
        and parts[0] == PLANNING_DIR_NAME
        and parts[1] == PUBLICATION_DIR_NAME
        and parts[3] == PUBLICATION_MANUSCRIPT_DIR_NAME
    ):
        return parts[2]
    return None


def _command_context_publication_roots(
    project_root: Path,
    command: object,
    resolved_subject: ResolvedCommandSubject | None,
) -> tuple[str | None, str | None]:
    """Return selected response roots exposed by command-context preflight."""

    if _command_review_mode(command) != "publication":
        return None, None
    if resolved_subject is not None and resolved_subject.ownership_mode == "external_authoring_intake":
        managed_slug = _managed_publication_slug_for_target(
            project_root,
            resolved_subject.target_root or resolved_subject.target_path,
        )
        if managed_slug is None:
            return None, None
        publication_root = f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/{managed_slug}"
        return publication_root, f"{publication_root}/review"
    if resolved_subject is None or resolved_subject.subject_kind != "manuscript":
        return PLANNING_DIR_NAME, f"{PLANNING_DIR_NAME}/review"

    managed_slug = _managed_publication_slug_for_target(project_root, resolved_subject.target_path)
    if managed_slug is not None:
        publication_root = f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/{managed_slug}"
    elif resolved_subject.ownership_mode == "external_artifact" and resolved_subject.target_path is not None:
        publication_root = (
            f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/"
            f"{_publication_subject_slug_for_manuscript_entrypoint(project_root, resolved_subject.target_path)}"
        )
    else:
        publication_root = PLANNING_DIR_NAME
    return publication_root, f"{publication_root}/review"


def _is_respond_to_referees_command(command: object) -> bool:
    return str(getattr(command, "name", "") or "") == "gpd:respond-to-referees"


def _respond_to_referees_has_report_source(arguments: str | None) -> bool:
    """Return whether launch arguments include a referee report source or paste intake."""

    tokens = _split_command_arguments(arguments)
    skip_next = False
    for index, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if token == "--":
            continue
        if token == "--manuscript":
            skip_next = True
            continue
        if token.startswith("--manuscript="):
            continue
        if token == "--report":
            if index + 1 < len(tokens):
                next_token = tokens[index + 1].strip()
                return bool(next_token and not next_token.startswith("-"))
            return False
        if token.startswith("--report="):
            return bool(token.partition("=")[2].strip())
        if token == "paste":
            return True
        if token.startswith("--"):
            continue
        return True
    return False


def _project_relative_path(project_root: Path, target: Path | None) -> str | None:
    """Return *target* relative to *project_root* when possible."""

    if target is None:
        return None
    try:
        return target.resolve(strict=False).relative_to(project_root.resolve(strict=False)).as_posix()
    except ValueError:
        return target.resolve(strict=False).as_posix()


def _review_preflight_publication_routing(
    *,
    project_root: Path,
    command: object,
    resolved_subject: ResolvedCommandSubject | None,
    manuscript: Path | None,
    context_preflight: object,
) -> dict[str, str | None]:
    """Return publication routing fields emitted by raw review-preflight."""

    selected_publication_root = getattr(context_preflight, "selected_publication_root", None)
    selected_review_root = getattr(context_preflight, "selected_review_root", None)
    manuscript_root = (
        _supported_manuscript_root_for_target(project_root, manuscript) if manuscript is not None else None
    )
    if manuscript is not None and manuscript_root is None:
        manuscript_root = manuscript.parent

    publication_subject_slug = None
    publication_lane_kind = None
    managed_publication_root = None
    if (
        resolved_subject is not None
        and resolved_subject.ownership_mode == "external_authoring_intake"
        and _command_review_mode(command) == "publication"
    ):
        managed_slug = _managed_publication_slug_for_target(
            project_root,
            resolved_subject.target_root or resolved_subject.target_path,
        )
        if managed_slug is not None:
            publication_subject_slug = managed_slug
            publication_lane_kind = "managed_publication_manuscript"
            managed_publication_root = f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/{publication_subject_slug}"
            manuscript_root = resolved_subject.target_root
    if manuscript is not None and _command_review_mode(command) == "publication":
        managed_slug = _managed_publication_slug_for_target(project_root, manuscript)
        publication_subject_slug = managed_slug or _publication_subject_slug_for_manuscript_entrypoint(
            project_root,
            manuscript,
        )
        managed_publication_root = f"{PLANNING_DIR_NAME}/{PUBLICATION_DIR_NAME}/{publication_subject_slug}"
        if managed_slug is not None:
            publication_lane_kind = "managed_publication_manuscript"
        elif (
            resolved_subject is not None
            and resolved_subject.ownership_mode == "external_artifact"
            and resolved_subject.explicit_input
        ):
            publication_lane_kind = "external_artifact"
        else:
            publication_lane_kind = "canonical_project_manuscript"

    return {
        "publication_subject_slug": publication_subject_slug,
        "publication_lane_kind": publication_lane_kind,
        "managed_publication_root": managed_publication_root,
        "selected_publication_root": selected_publication_root,
        "selected_review_root": selected_review_root,
        "manuscript_root": _project_relative_path(project_root, manuscript_root),
        "manuscript_entrypoint": _project_relative_path(project_root, manuscript),
    }


def _resolved_subject_uses_managed_publication_root(resolved_subject: ResolvedCommandSubject | None) -> bool:
    return (
        resolved_subject is not None
        and resolved_subject.subject_kind == "manuscript"
        and _managed_publication_slug_for_target(resolved_subject.context_root, resolved_subject.target_path)
        is not None
    )


def _command_managed_output_bindings(
    *,
    project_root: Path,
    resolved_subject: ResolvedCommandSubject | None,
) -> dict[str, str]:
    """Return dynamic managed-output subtree bindings for the active subject."""

    if resolved_subject is not None and resolved_subject.ownership_mode == "external_authoring_intake":
        managed_slug = _managed_publication_slug_for_target(
            project_root,
            resolved_subject.target_root or resolved_subject.target_path,
        )
        return {"subject_slug": managed_slug} if managed_slug is not None else {}
    manuscript_entrypoint = _resolved_subject_manuscript_entrypoint(resolved_subject)
    if manuscript_entrypoint is None:
        return {}
    return {"subject_slug": _publication_subject_slug_for_manuscript_entrypoint(project_root, manuscript_entrypoint)}


def _command_managed_output_policy(
    command: object,
    *,
    project_root: Path | None = None,
    resolved_subject: ResolvedCommandSubject | None = None,
):
    """Return a storage-path managed-output policy derived from command metadata."""

    from gpd.core.storage_paths import (
        ManagedOutputClass,
        ManagedOutputMatchMode,
        ManagedOutputPolicy,
        ManagedOutputRootKind,
        StageArtifactPolicy,
    )

    output_policy = _command_output_policy(command)
    if output_policy is None:
        return None

    managed_root_raw = str(getattr(output_policy, "managed_root_kind", "") or "").strip().casefold()
    if not managed_root_raw:
        return None
    if managed_root_raw in {"gpd", "gpd_managed_durable", "gpd_internal_other"}:
        managed_root_kind = ManagedOutputRootKind.GPD
        output_class = ManagedOutputClass.GPD_MANAGED_DURABLE
    elif managed_root_raw in {"project", "user_export_durable", "project_local_other"}:
        managed_root_kind = ManagedOutputRootKind.PROJECT
        output_class = ManagedOutputClass.USER_EXPORT_DURABLE
    else:
        return None

    subtree = str(getattr(output_policy, "default_output_subtree", "") or "").strip()
    if not subtree:
        return None
    subtree = subtree.replace("\\", "/")
    if managed_root_kind == ManagedOutputRootKind.GPD:
        if subtree == PLANNING_DIR_NAME:
            subtree = ""
        elif subtree.startswith(f"{PLANNING_DIR_NAME}/"):
            subtree = subtree[len(PLANNING_DIR_NAME) + 1 :]
    elif managed_root_kind == ManagedOutputRootKind.PROJECT and subtree.startswith("./"):
        subtree = subtree[2:]
    subtree_components = tuple(component for component in subtree.split("/") if component and component != ".")

    stage_policy_raw = str(getattr(output_policy, "stage_artifact_policy", "") or "").strip().casefold()
    stage_artifact_policy = (
        StageArtifactPolicy.ALLOWED
        if stage_policy_raw in {"allowed", "gpd_owned_outputs_only"}
        else StageArtifactPolicy.DISALLOWED
    )

    output_mode = str(getattr(output_policy, "output_mode", "") or "").strip().casefold()
    match_mode = ManagedOutputMatchMode.EXACT if output_mode == "exact" else ManagedOutputMatchMode.SUBTREE

    try:
        policy = ManagedOutputPolicy(
            output_class=output_class,
            managed_root_kind=managed_root_kind,
            default_output_subtree=subtree_components,
            match_mode=match_mode,
            stage_artifact_policy=stage_artifact_policy,
        )
    except ValueError:
        return None

    if not any(re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", component) for component in policy.default_output_subtree):
        return policy
    if project_root is None:
        return None
    try:
        return policy.bind_output_subtree_placeholders(
            _command_managed_output_bindings(project_root=project_root, resolved_subject=resolved_subject)
        )
    except ValueError:
        return None


def _command_managed_output_root(
    command: object,
    *,
    project_root: Path,
    resolved_subject: ResolvedCommandSubject | None = None,
) -> Path | None:
    """Return the effective managed output root for one command, when typed policy declares it."""

    from gpd.core.storage_paths import ProjectStorageLayout

    policy = _command_managed_output_policy(
        command,
        project_root=project_root,
        resolved_subject=resolved_subject,
    )
    if policy is None:
        return None
    return ProjectStorageLayout(project_root).managed_output_path(policy)


def _command_managed_output_context_root(
    *,
    workspace_root: Path,
    context_root: Path,
    project_exists: bool,
) -> Path:
    """Choose the root that owns managed outputs for one command-context preflight."""

    return context_root if project_exists else workspace_root


def _normalize_review_scope_selector(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _resolved_subject_scope_selectors(resolved_subject: ResolvedCommandSubject | None) -> frozenset[str]:
    if resolved_subject is None:
        return frozenset()

    selectors: set[str] = set()
    ownership_mode = _normalize_review_scope_selector(resolved_subject.ownership_mode)
    if ownership_mode:
        selectors.add(ownership_mode)
    status = _normalize_review_scope_selector(resolved_subject.status)
    if status:
        selectors.add(status)
    if resolved_subject.explicit_input:
        selectors.add("explicit_input")
        if resolved_subject.subject_kind == "manuscript":
            selectors.add("explicit_manuscript")
    if resolved_subject.ancestor_walked_up:
        selectors.add("ancestor_project")
    if resolved_subject.ownership_mode in {"project_backed", "project_reentry_selected"}:
        selectors.add("project_backed")
    if _resolved_subject_uses_managed_publication_root(resolved_subject):
        selectors.add("managed_publication_subject")
    if resolved_subject.ownership_mode == "external_artifact":
        selectors.update(
            {
                "explicit_artifact",
                "explicit_external_manuscript",
                "explicit_external_subject",
                "external_artifact",
            }
        )
    if resolved_subject.ownership_mode == "external_authoring_intake":
        selectors.update(
            {
                "external_authoring_intake",
                "explicit_intake_manifest",
                "authoring_intake",
            }
        )
    if resolved_subject.status == "interactive":
        selectors.update({"interactive", "interactive_standalone"})
    return frozenset(selectors)


def _active_review_contract_scope_variants(
    contract: object,
    *,
    resolved_subject: ResolvedCommandSubject | None,
) -> list[object]:
    active_selectors = _resolved_subject_scope_selectors(resolved_subject)
    active_variants: list[object] = []
    for variant in list(getattr(contract, "scope_variants", []) or []):
        scope = _normalize_review_scope_selector(str(getattr(variant, "scope", "") or ""))
        if scope and scope in active_selectors:
            active_variants.append(variant)
    return active_variants


def _effective_review_contract_scope_overrides(
    contract: object,
    *,
    active_scope_variants: list[object],
) -> tuple[list[str], list[str], list[str]]:
    required_outputs = list(getattr(contract, "required_outputs", []) or [])
    required_evidence = list(getattr(contract, "required_evidence", []) or [])
    blocking_conditions = list(getattr(contract, "blocking_conditions", []) or [])
    for variant in active_scope_variants:
        outputs_override = list(getattr(variant, "required_outputs_override", []) or [])
        if outputs_override:
            required_outputs = outputs_override
        evidence_override = list(getattr(variant, "required_evidence_override", []) or [])
        if evidence_override:
            required_evidence = evidence_override
        blocking_override = list(getattr(variant, "blocking_conditions_override", []) or [])
        if blocking_override:
            blocking_conditions = blocking_override
    return required_outputs, required_evidence, blocking_conditions


def _publication_subject_preflight_policy(
    command: object,
    *,
    resolved_subject: ResolvedCommandSubject | None,
) -> PublicationSubjectPreflightPolicy:
    """Return publication preflight relaxations derived from the shared subject envelope."""

    contract = _command_review_contract(command)
    if _command_review_mode(command) != "publication":
        return PublicationSubjectPreflightPolicy()

    active_scopes = _resolved_subject_scope_selectors(resolved_subject)
    active_scope_variants = _active_review_contract_scope_variants(
        contract,
        resolved_subject=resolved_subject,
    )
    relaxed_checks: set[str] = set()
    optional_checks: set[str] = set()
    detail_overrides: dict[str, str] = {}
    for variant in active_scope_variants:
        relaxed_checks.update(list(getattr(variant, "relaxed_preflight_checks", []) or []))
        optional_checks.update(list(getattr(variant, "optional_preflight_checks", []) or []))

    if active_scopes.intersection({"external_authoring_intake", "explicit_intake_manifest", "authoring_intake"}):
        for check_name, detail in _WRITE_PAPER_EXTERNAL_AUTHORING_OPTIONAL_DETAILS.items():
            if check_name in relaxed_checks or check_name in optional_checks:
                detail_overrides.setdefault(check_name, detail)

    if active_scopes.intersection({"explicit_artifact", "external_artifact"}):
        for check_name, detail in _EXTERNAL_ARTIFACT_OPTIONAL_DETAILS.items():
            if check_name in relaxed_checks or check_name in optional_checks:
                detail_overrides.setdefault(check_name, detail)

    required_outputs, required_evidence, blocking_conditions = _effective_review_contract_scope_overrides(
        contract,
        active_scope_variants=active_scope_variants,
    )
    return PublicationSubjectPreflightPolicy(
        active_scopes=active_scopes,
        relaxed_checks=frozenset(relaxed_checks),
        optional_checks=frozenset(optional_checks),
        detail_overrides=detail_overrides,
        required_outputs=tuple(required_outputs),
        required_evidence=tuple(required_evidence),
        blocking_conditions=tuple(blocking_conditions),
    )


def _read_only_project_scoped_cwd(cwd: Path) -> Path:
    workspace_cwd = cwd.expanduser().resolve(strict=False)
    resolved = resolve_project_root(workspace_cwd)
    return resolved if resolved is not None and (resolved / PLANNING_DIR_NAME).is_dir() else workspace_cwd


def command_preflight_cwd(
    command: object,
    *,
    cwd: Path,
    project_reentry_resolver: Callable[[Path], ProjectReentryResolution] | None = None,
) -> Path:
    workspace_cwd = cwd.expanduser().resolve(strict=False)
    reentry_resolver = project_reentry_resolver or resolve_project_reentry
    effective_context_mode = _command_effective_context_mode(command)
    if effective_context_mode == "global":
        return workspace_cwd
    if effective_context_mode == "projectless" or not command_supports_project_reentry(command):
        return _read_only_project_scoped_cwd(workspace_cwd)

    reentry_policy = _command_effective_project_reentry_mode(command).casefold()
    if reentry_policy in {"current-workspace", "current_workspace", "current-workspace-only", "current_workspace_only"}:
        return _read_only_project_scoped_cwd(workspace_cwd)
    reentry = reentry_resolver(workspace_cwd)
    return reentry.resolved_project_root or workspace_cwd


def _progress_reconcile_requested(command: object, arguments: str | None) -> bool:
    return str(getattr(command, "name", "") or "") == "gpd:progress" and "--reconcile" in _split_command_arguments(
        arguments
    )


def _progress_reconcile_confirmation_check(command: object) -> tuple[bool, str]:
    allowed_tools = set(getattr(command, "allowed_tools", []) or [])
    if "ask_user" in allowed_tools:
        return True, "ask_user is available before progress reconciliation writes state"
    return (
        False,
        "progress --reconcile requires ask_user or an explicit typed-confirmation contract before state writes",
    )


def _runtime_command_argument_check(command: object, arguments: str | None) -> tuple[bool, str] | None:
    if str(getattr(command, "name", "") or "") != "gpd:progress":
        return None

    supplied_flags = [token for token in _split_command_arguments(arguments) if token in {"--watch", "-w"}]
    if not supplied_flags:
        return None

    supplied = ", ".join(supplied_flags)
    return (
        False,
        f"{supplied} is local CLI only for runtime progress; use `gpd progress json --watch` from a terminal.",
    )


def _build_project_aware_guidance(explicit_inputs: list[str], *, init_command: str) -> str:
    init_guidance = (
        f"initialize a project with `{init_command}` in the runtime surface or `gpd init new-project` in the local CLI"
    )
    if not explicit_inputs:
        return f"Either provide explicit inputs for this command, or {init_guidance}."
    requirement_text = explicit_inputs[0]
    if len(explicit_inputs) == 2:
        requirement_text = f"{explicit_inputs[0]} and {explicit_inputs[1]}"
    elif len(explicit_inputs) > 2:
        requirement_text = ", ".join(explicit_inputs[:-1]) + f", and {explicit_inputs[-1]}"
    return f"Either provide {requirement_text} explicitly, or {init_guidance}."


def _build_recoverable_workspace_guidance(*, init_command: str) -> str:
    return (
        "This command requires a recoverable GPD workspace. "
        f"Open the right project, use `{local_cli_resume_recent_command()}` to rediscover it, or "
        f"initialize a new project with `{init_command}` in the runtime surface or `gpd init new-project` in the local CLI."
    )


def _explicit_inputs_for_command(command: object) -> list[str]:
    if explicit_inputs := _command_explicit_input_labels_from_policy(command):
        return explicit_inputs
    argument_hint = str(getattr(command, "argument_hint", "") or "").strip()
    return [argument_hint] if argument_hint else ["explicit command inputs"]


def _required_files_status(
    project_root: Path,
    command: object,
    arguments: str | None,
    *,
    workspace_cwd: Path,
    resolved_subject: ResolvedCommandSubject | None,
) -> tuple[bool, str]:
    required_files_present, matched_patterns, missing_patterns = _command_required_files_present(
        project_root,
        command,
    )
    if not required_files_present:
        override_detail = _command_required_files_override_detail(
            project_root,
            command,
            arguments,
            workspace_cwd=workspace_cwd,
            resolved_subject=resolved_subject,
        )
        if override_detail is not None:
            return True, override_detail
    detail = "matching required files present: " + ", ".join(matched_patterns)
    if not required_files_present:
        detail = "missing required files or unmatched patterns: " + ", ".join(missing_patterns)
    return required_files_present, detail


def command_label_lookup_and_arguments(command_name: str, arguments: str | None = None) -> tuple[str, str | None]:
    parsed = parse_command_label(command_name)
    merged_arguments = " ".join(part for part in (parsed.inline_args, arguments or "") if part)
    return parsed.command or command_name.strip(), merged_arguments or None


def command_supports_project_reentry(command: object) -> bool:
    project_reentry_mode = _command_effective_project_reentry_mode(command).casefold()
    return project_reentry_mode not in {"", "disallowed", "false", "none"}


def _render_public_command_label(canonical_label: str, *, public_prefix: str) -> str:
    parsed = parse_command_label(canonical_label)
    if not parsed.slug:
        return canonical_label
    return f"{public_prefix}{parsed.slug}" if public_prefix else canonical_label


def _allowed_command_preview(known_commands: list[str], *, limit: int) -> list[str]:
    preview: list[str] = []
    for command_name in ("gpd:help", *known_commands):
        if command_name in preview:
            continue
        preview.append(command_name)
        if len(preview) >= limit:
            break
    return preview


def _lookup_suggestions(
    parsed_command: str,
    *,
    known_commands: list[str],
    public_prefix: str,
    limit: int,
) -> list[CommandLookupSuggestion]:
    if not parsed_command:
        return []

    candidates: list[tuple[float, str, str]] = []
    requested = parsed_command.casefold()
    for canonical_label in known_commands:
        parsed = parse_command_label(canonical_label)
        candidate_values = (parsed.slug.casefold(), canonical_label.casefold())
        score = max(SequenceMatcher(None, requested, candidate).ratio() for candidate in candidate_values)
        if score >= 0.62:
            candidates.append((score, canonical_label, parsed.slug))

    suggestions: list[CommandLookupSuggestion] = []
    seen: set[str] = set()
    for _score, canonical_label, slug in sorted(candidates, key=lambda item: (-item[0], item[1])):
        if canonical_label in seen:
            continue
        seen.add(canonical_label)
        suggestions.append(
            CommandLookupSuggestion(
                command=_render_public_command_label(canonical_label, public_prefix=public_prefix),
                canonical_command=canonical_label,
                slug=slug,
            )
        )
        if len(suggestions) >= limit:
            break
    return suggestions


def build_command_lookup_error_payload(
    command_name: str,
    *,
    runtime_surface_metadata: CommandRuntimeSurfaceMetadata | None = None,
    preview_limit: int = 12,
    suggestion_limit: int = 3,
) -> CommandLookupErrorPayload:
    """Return the shared fail-closed payload for an unknown registry command."""

    from gpd import registry as content_registry

    runtime = runtime_surface_metadata or CommandRuntimeSurfaceMetadata()
    parsed = parse_command_label(command_name)
    normalized_command = parsed.command or command_name.strip()
    canonical_command = parsed.canonical_command
    public_prefix = runtime.public_runtime_command_prefix or ""
    known_commands = list(content_registry.list_commands(name_format="label"))
    suggestions = _lookup_suggestions(
        parsed.slug,
        known_commands=known_commands,
        public_prefix=public_prefix or "gpd:",
        limit=suggestion_limit,
    )
    primary_command = f"{public_prefix}help --all" if public_prefix else "gpd --raw help --all"
    guidance = f"Unknown GPD command. Run `{primary_command}` for the compact command index."
    safe_alternatives = [
        CommandLookupAction(
            label="Inspect local raw help index",
            command="gpd --raw help --all",
            detail="Read the compact registry index without running any workflow.",
        ),
        CommandLookupAction(
            label="Inspect local CLI help",
            command="gpd --help",
            detail="Check terminal-only `gpd` subcommands when the request may be local CLI syntax.",
        ),
    ]
    if suggestions:
        safe_alternatives.insert(
            0,
            CommandLookupAction(
                label="Inspect closest command help",
                command=f"gpd --raw help --command {suggestions[0].canonical_command}",
                detail="Read detailed metadata for the closest registered command suggestion.",
            ),
        )
    safe_alternatives = [action for action in safe_alternatives if action.command != primary_command]

    debug_target = suggestions[0].canonical_command if suggestions else "gpd:help"
    return CommandLookupErrorPayload(
        ok=False,
        passed=False,
        error="unknown_command",
        requested_command=command_name,
        normalized_command=normalized_command,
        canonical_command=canonical_command,
        slug=parsed.slug,
        known_command=False,
        allowed_preview=_allowed_command_preview(known_commands, limit=preview_limit),
        suggestions=suggestions,
        guidance=guidance,
        primary_action=CommandLookupAction(
            label="Open compact command index",
            command=primary_command,
            detail="Use the registry-backed help index to choose one valid public runtime command.",
        ),
        safe_alternatives=safe_alternatives,
        debug_actions=[
            CommandLookupAction(
                label="Replay lookup preflight",
                command=f"gpd --raw validate command-context {canonical_command}",
                detail="Confirm the command lookup failure through the read-only command-context validator.",
            ),
            CommandLookupAction(
                label="Inspect known command fields",
                command=f"gpd --raw command field-access {debug_target}",
                detail="Inspect the stable command-context fields for a registered command.",
            ),
        ],
        validated_surface=runtime.validated_surface,
        public_runtime_command_prefix=runtime.public_runtime_command_prefix,
        dispatch_note=runtime.dispatch_note,
    )


def format_command_lookup_error(payload: CommandLookupErrorPayload) -> str:
    message = f"Unknown GPD command: {payload.canonical_command}. {payload.guidance}"
    if payload.suggestions:
        rendered = ", ".join(suggestion.command for suggestion in payload.suggestions)
        message += f" Suggestions: {rendered}"
    return message


def resolve_registry_command(command_name: str) -> tuple[object, str]:
    from gpd import registry as content_registry

    try:
        return content_registry.get_command(command_name), canonical_command_label(command_name)
    except KeyError as exc:
        raise CommandLookupError(build_command_lookup_error_payload(command_name)) from exc


def build_command_context_preflight(
    command_name: str,
    *,
    cwd: Path,
    arguments: str | None = None,
    command_resolver: Callable[[str], tuple[object, str]] | None = None,
    project_reentry_resolver: Callable[[Path], ProjectReentryResolution] | None = None,
    runtime_surface_metadata: CommandRuntimeSurfaceMetadata | None = None,
) -> CommandContextPreflightResult:
    launch_cwd = cwd.expanduser().resolve(strict=False)
    reentry_resolver = project_reentry_resolver or resolve_project_reentry
    runtime = runtime_surface_metadata or CommandRuntimeSurfaceMetadata()
    command_name, arguments = command_label_lookup_and_arguments(command_name, arguments)
    resolver = command_resolver or resolve_registry_command
    command, public_command_name = resolver(command_name)
    context_cwd = command_preflight_cwd(
        command,
        cwd=launch_cwd,
        project_reentry_resolver=reentry_resolver,
    )
    layout = ProjectLayout(context_cwd)
    project_exists = layout.project_md.exists()
    effective_context_mode = _command_effective_context_mode(command)

    checks: list[CommandContextCheck] = []

    def add_check(name: str, passed: bool, detail: str, *, blocking: bool = True) -> None:
        checks.append(CommandContextCheck(name=name, passed=passed, detail=detail, blocking=blocking))

    def display(target: str | Path | None) -> str:
        return _format_display_path(target, cwd=launch_cwd)

    def build_result(
        *,
        passed: bool,
        project_exists: bool,
        explicit_inputs: list[str],
        guidance: str,
        resolved_mode: str = "",
        mode_reason: str = "",
        resolved_subject: ResolvedCommandSubject | None = None,
        selected_publication_root: str | None = None,
        selected_review_root: str | None = None,
    ) -> CommandContextPreflightResult:
        return CommandContextPreflightResult(
            command=public_command_name,
            context_mode=effective_context_mode,
            passed=passed,
            project_exists=project_exists,
            explicit_inputs=explicit_inputs,
            guidance=guidance,
            checks=checks,
            resolved_mode=resolved_mode,
            mode_reason=mode_reason,
            validated_surface=runtime.validated_surface,
            public_runtime_command_prefix=runtime.public_runtime_command_prefix,
            dispatch_note=runtime.dispatch_note,
            resolved_subject=resolved_subject,
            selected_publication_root=selected_publication_root,
            selected_review_root=selected_review_root,
        )

    add_check("context_mode", True, f"context_mode={effective_context_mode}", blocking=False)
    runtime_argument_check = _runtime_command_argument_check(command, arguments)
    if runtime_argument_check is not None:
        runtime_arguments_passed, runtime_arguments_detail = runtime_argument_check
        add_check(
            "runtime_arguments",
            runtime_arguments_passed,
            runtime_arguments_detail,
            blocking=True,
        )
        if not runtime_arguments_passed:
            return build_result(
                passed=False,
                project_exists=project_exists,
                explicit_inputs=[],
                guidance=runtime_arguments_detail,
            )

    if effective_context_mode == "global":
        add_check("project_context", True, "command runs without project context", blocking=False)
        return build_result(
            passed=True,
            project_exists=project_exists,
            explicit_inputs=[],
            guidance="",
        )

    if effective_context_mode == "projectless":
        add_check(
            "project_context",
            True,
            ("initialized project detected" if project_exists else "no initialized project required"),
            blocking=False,
        )
        return build_result(
            passed=True,
            project_exists=project_exists,
            explicit_inputs=[],
            guidance="",
        )

    if effective_context_mode == "project-required":
        required_file_patterns = _command_required_file_patterns(command)
        if command_supports_project_reentry(command):
            reentry_policy = _command_effective_project_reentry_mode(command).casefold()
            current_workspace_reentry_only = reentry_policy in {
                "current-workspace",
                "current_workspace",
                "current-workspace-only",
                "current_workspace_only",
            }
            reentry = reentry_resolver(launch_cwd)
            current_workspace_candidate = next(
                (
                    candidate
                    for candidate in reentry.candidates
                    if candidate.source == "current_workspace" and candidate.recoverable
                ),
                None,
            )
            selected_candidate = current_workspace_candidate or (
                None if current_workspace_reentry_only else reentry.selected_candidate
            )
            if selected_candidate is not None:
                selected_root = Path(selected_candidate.project_root).expanduser().resolve(strict=False)
                selected_root_source = selected_candidate.source
            elif current_workspace_reentry_only:
                selected_root = context_cwd
                selected_root_source = "workspace"
            else:
                selected_root = reentry.resolved_project_root or context_cwd
                selected_root_source = reentry.source or "workspace"
            selected_root_auto_selected = (
                current_workspace_candidate is None and not current_workspace_reentry_only and reentry.auto_selected
            )
            selected_root_requires_user_selection = (
                current_workspace_candidate is None
                and not current_workspace_reentry_only
                and reentry.requires_user_selection
            )
            selected_reentry_mode = (
                "current-workspace"
                if current_workspace_candidate is not None or current_workspace_reentry_only
                else reentry.mode
            )
            resume_work_requires_reopened_workspace = (
                public_command_name == "gpd:resume-work"
                and selected_root_auto_selected
                and selected_root_source == "recent_project"
            )
            layout = ProjectLayout(selected_root)
            state_exists, roadmap_exists, project_exists = recoverable_project_context(selected_root)
            resolved_subject = _build_resolved_command_subject(
                selected_root,
                command,
                arguments,
                workspace_cwd=launch_cwd,
                project_root_source=selected_root_source,
                project_root_auto_selected=selected_root_auto_selected,
                reentry_mode=selected_reentry_mode,
            )
            explicit_inputs = _explicit_inputs_for_command(command)
            subject_required = _command_has_typed_subject_policy(command)
            subject_context_ready = resolved_subject is not None and resolved_subject.status in {
                "resolved",
                "bootstrap",
            }
            if subject_required:
                add_check(
                    "explicit_inputs",
                    subject_context_ready,
                    (
                        resolved_subject.detail
                        if resolved_subject is not None
                        else f"missing explicit standalone inputs ({', '.join(explicit_inputs)})"
                    ),
                    blocking=True,
                )
            if current_workspace_candidate is not None:
                add_check(
                    "project_reentry",
                    True,
                    "current workspace or ancestor project root is recoverable",
                    blocking=False,
                )
            elif current_workspace_reentry_only:
                add_check(
                    "project_reentry",
                    False,
                    "no recoverable current-workspace project target found",
                    blocking=False,
                )
            elif resume_work_requires_reopened_workspace:
                add_check(
                    "project_reentry",
                    False,
                    (
                        "unique recoverable recent project found, but resume-work will not switch runtime "
                        "workspaces silently"
                    ),
                    blocking=False,
                )
            elif reentry.auto_selected and reentry.project_root:
                add_check(
                    "project_reentry",
                    True,
                    f"auto-selected recoverable recent project {display(reentry.project_root)}",
                    blocking=False,
                )
            elif reentry.requires_user_selection:
                add_check(
                    "project_reentry",
                    False,
                    "multiple recoverable recent projects are available; explicit selection required",
                    blocking=False,
                )
            elif reentry.has_current_workspace_candidate:
                add_check(
                    "project_reentry",
                    True,
                    "current workspace or ancestor project root is recoverable",
                    blocking=False,
                )
            else:
                add_check(
                    "project_reentry",
                    False,
                    "no recoverable current-workspace or uniquely recoverable recent-project target found",
                    blocking=False,
                )
            add_check(
                "state_exists",
                state_exists,
                (
                    "recoverable state present"
                    if state_exists
                    else (f"missing {display(layout.state_json)} and {display(layout.state_md)}")
                ),
                blocking=False,
            )
            add_check(
                "roadmap_exists",
                roadmap_exists,
                (f"{display(layout.roadmap)} present" if roadmap_exists else f"missing {display(layout.roadmap)}"),
                blocking=False,
            )
            add_check(
                "project_exists",
                project_exists,
                (
                    f"{display(layout.project_md)} present"
                    if project_exists
                    else f"missing {display(layout.project_md)}"
                ),
                blocking=False,
            )
            required_files_present = True
            manuscript_context_passed = True
            manuscript_context_detail = ""
            if required_file_patterns:
                required_files_present, required_files_detail = _required_files_status(
                    selected_root,
                    command,
                    arguments,
                    workspace_cwd=launch_cwd,
                    resolved_subject=resolved_subject,
                )
                add_check(
                    "required_files",
                    required_files_present,
                    required_files_detail,
                    blocking=False,
                )
            manuscript_context = _command_context_manuscript_check(
                selected_root,
                command,
                arguments,
                workspace_cwd=launch_cwd,
                resolved_subject=resolved_subject,
            )
            if manuscript_context is not None:
                manuscript_context_passed, manuscript_context_detail = manuscript_context
                add_check(
                    "manuscript",
                    manuscript_context_passed,
                    manuscript_context_detail,
                    blocking=False,
                )
            reconcile_confirmation_passed = True
            if _progress_reconcile_requested(command, arguments):
                reconcile_confirmation_passed, reconcile_confirmation_detail = _progress_reconcile_confirmation_check(
                    command
                )
                add_check(
                    "reconcile_confirmation",
                    reconcile_confirmation_passed,
                    reconcile_confirmation_detail,
                    blocking=True,
                )
            recoverable = (
                (state_exists or roadmap_exists or project_exists)
                and required_files_present
                and manuscript_context_passed
                and reconcile_confirmation_passed
                and (not subject_required or subject_context_ready)
                and not selected_root_requires_user_selection
                and not resume_work_requires_reopened_workspace
            )
            guidance = (
                ""
                if recoverable
                else (
                    "This command found multiple recoverable recent GPD projects and will not switch silently. "
                    f"Use `{local_cli_resume_recent_command()}` to pick the right project explicitly, then reopen it in the runtime."
                    if selected_root_requires_user_selection
                    else (
                        "This command found a unique recoverable recent GPD project, but resume-work will not "
                        "continue from an unrelated runtime workspace. "
                        f"Use `{local_cli_resume_recent_command()}` to verify the target, then open that project "
                        "folder in the runtime and rerun resume-work."
                        if resume_work_requires_reopened_workspace
                        else (
                            _build_recoverable_workspace_guidance(init_command=runtime.init_command)
                            if not (state_exists or roadmap_exists or project_exists)
                            else (
                                resolved_subject.detail
                                if resolved_subject is not None
                                else f"Either provide {', '.join(explicit_inputs)} explicitly."
                            )
                            if subject_required and not subject_context_ready
                            else manuscript_context_detail
                            if not manuscript_context_passed
                            else "This command requires one of the declared required files: "
                            + ", ".join(required_file_patterns)
                        )
                    )
                )
            )
            selected_publication_root, selected_review_root = _command_context_publication_roots(
                selected_root,
                command,
                resolved_subject,
            )
            return build_result(
                passed=recoverable,
                project_exists=project_exists,
                explicit_inputs=[],
                guidance=guidance,
                resolved_subject=resolved_subject,
                selected_publication_root=selected_publication_root,
                selected_review_root=selected_review_root,
            )
        add_check(
            "project_exists",
            project_exists,
            (f"{display(layout.project_md)} present" if project_exists else f"missing {display(layout.project_md)}"),
        )
        required_file_patterns = _command_required_file_patterns(command)
        resolved_subject = _build_resolved_command_subject(
            context_cwd,
            command,
            arguments,
            workspace_cwd=launch_cwd,
            project_root_source="workspace",
            project_root_auto_selected=False,
            reentry_mode="current-workspace" if project_exists else None,
        )
        explicit_inputs = _explicit_inputs_for_command(command)
        subject_required = _command_has_typed_subject_policy(command)
        subject_context_ready = resolved_subject is not None and resolved_subject.status in {"resolved", "bootstrap"}
        if subject_required:
            add_check(
                "explicit_inputs",
                subject_context_ready,
                (
                    resolved_subject.detail
                    if resolved_subject is not None
                    else f"missing explicit standalone inputs ({', '.join(explicit_inputs)})"
                ),
            )
        manuscript_context = _command_context_manuscript_check(
            context_cwd,
            command,
            arguments,
            workspace_cwd=launch_cwd,
            resolved_subject=resolved_subject,
        )
        if required_file_patterns:
            required_files_present, required_files_detail = _required_files_status(
                context_cwd,
                command,
                arguments,
                workspace_cwd=launch_cwd,
                resolved_subject=resolved_subject,
            )
            add_check(
                "required_files",
                required_files_present,
                required_files_detail,
            )
        else:
            required_files_present = True
        manuscript_context_passed = True
        manuscript_context_detail = ""
        if manuscript_context is not None:
            manuscript_context_passed, manuscript_context_detail = manuscript_context
            add_check(
                "manuscript",
                manuscript_context_passed,
                manuscript_context_detail,
            )
        reconcile_confirmation_passed = True
        if _progress_reconcile_requested(command, arguments):
            reconcile_confirmation_passed, reconcile_confirmation_detail = _progress_reconcile_confirmation_check(
                command
            )
            add_check(
                "reconcile_confirmation",
                reconcile_confirmation_passed,
                reconcile_confirmation_detail,
            )
        passed = (
            project_exists
            and required_files_present
            and manuscript_context_passed
            and reconcile_confirmation_passed
            and (not subject_required or subject_context_ready)
        )
        guidance = (
            ""
            if passed
            else (
                "This command requires an initialized GPD project."
                if not project_exists
                else (
                    resolved_subject.detail
                    if resolved_subject is not None
                    else f"Either provide {', '.join(explicit_inputs)} explicitly."
                )
                if subject_required and not subject_context_ready
                else manuscript_context_detail
                if not manuscript_context_passed
                else "This command requires one of the declared required files: " + ", ".join(required_file_patterns)
            )
        )
        selected_publication_root, selected_review_root = _command_context_publication_roots(
            context_cwd,
            command,
            resolved_subject,
        )
        return build_result(
            passed=passed,
            project_exists=project_exists,
            explicit_inputs=[],
            guidance=guidance,
            resolved_subject=resolved_subject,
            selected_publication_root=selected_publication_root,
            selected_review_root=selected_review_root,
        )

    explicit_inputs = _explicit_inputs_for_command(command)
    predicate = _PROJECT_AWARE_EXPLICIT_INPUT_PREDICATES.get(
        str(getattr(command, "name", "") or ""),
        _has_simple_positional_inputs,
    )
    resolved_subject = _build_resolved_command_subject(
        context_cwd,
        command,
        arguments,
        workspace_cwd=launch_cwd,
        project_root_source="workspace" if project_exists else None,
        project_root_auto_selected=False,
        reentry_mode="current-workspace" if project_exists else None,
    )
    resolved_mode = ""
    mode_reason = ""
    explicit_inputs_detail = "explicit standalone inputs detected"
    peer_review_has_explicit_target = command.name == "gpd:peer-review" and _has_simple_positional_inputs(arguments)
    external_publication_subject_disallowed = (
        _command_requires_manuscript_context(command)
        and not _command_allows_external_manuscript_targets(command)
        and resolved_subject is not None
        and resolved_subject.explicit_input
        and resolved_subject.ownership_mode == "external_artifact"
        and resolved_subject.status in {"resolved", "bootstrap"}
    )
    invalid_explicit_publication_subject = (
        _command_requires_manuscript_context(command)
        and not _command_allows_external_manuscript_targets(command)
        and resolved_subject is not None
        and resolved_subject.explicit_input
        and (external_publication_subject_disallowed or resolved_subject.status not in {"resolved", "bootstrap"})
    )
    invalid_explicit_publication_subject_detail = (
        "explicit manuscript target must resolve inside an initialized GPD project for this command"
        if external_publication_subject_disallowed
        else resolved_subject.detail
        if invalid_explicit_publication_subject and resolved_subject is not None
        else ""
    )
    respond_to_referees_context = _is_respond_to_referees_command(command)
    manuscript_context_passed = True
    manuscript_context_detail = ""
    if respond_to_referees_context:
        manuscript_context = _command_context_manuscript_check(
            context_cwd,
            command,
            arguments,
            workspace_cwd=launch_cwd,
            resolved_subject=resolved_subject,
        )
        if manuscript_context is not None:
            manuscript_context_passed, manuscript_context_detail = manuscript_context
        if not project_exists and not (resolved_subject is not None and resolved_subject.explicit_input):
            manuscript_context_passed = False
            manuscript_context_detail = (
                "respond-to-referees outside a project requires `--manuscript PATH`; "
                "report path or `paste` shorthand only works after a project manuscript resolves"
            )
    if resolved_subject is not None and not _command_requires_manuscript_context(command):
        explicit_inputs_ok = resolved_subject.status == "resolved"
        interactive_intake_allowed = resolved_subject.status == "interactive"
    else:
        explicit_inputs_ok = predicate(arguments)
        if invalid_explicit_publication_subject:
            explicit_inputs_ok = False
        if str(getattr(command, "name", "") or "") == "gpd:write-paper" and _has_write_paper_external_authoring_intake(
            arguments
        ):
            explicit_inputs_ok = bool(
                resolved_subject is not None
                and resolved_subject.ownership_mode == "external_authoring_intake"
                and resolved_subject.status in {"resolved", "bootstrap"}
            )
        if command.name == "gpd:peer-review":
            peer_review_mode = resolve_peer_review_mode_details(context_cwd, arguments, workspace_cwd=launch_cwd)
            resolved_mode = peer_review_mode.resolved_mode
            mode_reason = peer_review_mode.mode_reason
            if peer_review_has_explicit_target:
                explicit_inputs_ok = peer_review_mode.resolved_mode != PEER_REVIEW_INVALID_SUBJECT_MODE
                explicit_inputs_detail = (
                    peer_review_mode.resolution_detail
                    if explicit_inputs_ok
                    else f"invalid explicit review target: {peer_review_mode.mode_reason}"
                )
        if respond_to_referees_context:
            report_source_supplied = _respond_to_referees_has_report_source(arguments)
            explicit_inputs_ok = bool(
                manuscript_context_passed
                and report_source_supplied
                and (project_exists or (resolved_subject is not None and resolved_subject.explicit_input))
            )
            if not manuscript_context_passed:
                explicit_inputs_detail = manuscript_context_detail
            elif not report_source_supplied:
                explicit_inputs_detail = "missing referee report source (`--report PATH`, report path, or `paste`)"
        interactive_intake_allowed = (
            _command_allows_interactive_subject_intake(command)
            and not explicit_inputs_ok
            and not _has_simple_positional_inputs(arguments)
        )
    subject_required = _command_has_typed_subject_policy(command)
    subject_context_ready = resolved_subject is not None and resolved_subject.status in {"resolved", "bootstrap"}
    if respond_to_referees_context:
        subject_context_ready = subject_context_ready and manuscript_context_passed
    project_context_satisfies = project_exists and (
        not invalid_explicit_publication_subject
        and (not subject_required or explicit_inputs_ok or interactive_intake_allowed or subject_context_ready)
    )
    add_check(
        "project_exists",
        project_exists,
        (f"{display(layout.project_md)} present" if project_exists else f"missing {display(layout.project_md)}"),
        blocking=False,
    )
    if respond_to_referees_context:
        add_check(
            "manuscript",
            manuscript_context_passed,
            manuscript_context_detail,
            blocking=True,
        )
    add_check(
        "explicit_inputs",
        explicit_inputs_ok or interactive_intake_allowed,
        (
            "validated external authoring intake manifest"
            if (
                explicit_inputs_ok
                and str(getattr(command, "name", "") or "") == "gpd:write-paper"
                and _has_write_paper_external_authoring_intake(arguments)
            )
            else "explicit standalone inputs detected"
            if explicit_inputs_ok
            else invalid_explicit_publication_subject_detail
            if (
                invalid_explicit_publication_subject
                or str(getattr(command, "name", "") or "") == "gpd:write-paper"
                and _has_write_paper_external_authoring_intake(arguments)
                and resolved_subject is not None
                and resolved_subject.ownership_mode == "external_authoring_intake"
            )
            else explicit_inputs_detail
            if (
                explicit_inputs_ok
                or (command.name == "gpd:peer-review" and peer_review_has_explicit_target)
                or respond_to_referees_context
            )
            else (
                _command_interactive_subject_detail(command, explicit_inputs)
                if interactive_intake_allowed
                else f"missing explicit standalone inputs ({', '.join(explicit_inputs)})"
            )
        ),
        blocking=(
            peer_review_has_explicit_target
            if command.name == "gpd:peer-review"
            else invalid_explicit_publication_subject or (not project_exists and not interactive_intake_allowed)
        ),
    )
    managed_output_context_root = _command_managed_output_context_root(
        workspace_root=launch_cwd,
        context_root=context_cwd,
        project_exists=project_exists,
    )
    managed_output_root = _command_managed_output_root(
        command,
        project_root=managed_output_context_root,
        resolved_subject=resolved_subject,
    )
    if managed_output_root is not None:
        add_check(
            "managed_output_root",
            True,
            f"GPD-authored outputs resolve under {display(managed_output_root)}",
            blocking=False,
        )
    passed = project_context_satisfies or explicit_inputs_ok or interactive_intake_allowed
    guidance = (
        ""
        if passed
        else (
            invalid_explicit_publication_subject_detail
            if invalid_explicit_publication_subject
            else manuscript_context_detail
            if respond_to_referees_context and not manuscript_context_passed
            else explicit_inputs_detail
            if respond_to_referees_context and not explicit_inputs_ok
            else _build_project_aware_guidance(explicit_inputs, init_command=runtime.init_command)
        )
    )
    if command.name == "gpd:peer-review" and peer_review_has_explicit_target and not explicit_inputs_ok:
        guidance = explicit_inputs_detail
    selected_publication_root, selected_review_root = _command_context_publication_roots(
        managed_output_context_root,
        command,
        resolved_subject,
    )
    return build_result(
        passed=passed,
        project_exists=project_exists,
        explicit_inputs=explicit_inputs,
        guidance=guidance,
        resolved_mode=resolved_mode,
        mode_reason=mode_reason,
        resolved_subject=resolved_subject,
        selected_publication_root=selected_publication_root,
        selected_review_root=selected_review_root,
    )
