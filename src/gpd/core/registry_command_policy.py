"""Command policy parsing helpers used by the registry facade."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path

from gpd.core.model_visible_text import (
    COMMAND_POLICY_FRONTMATTER_KEY,
    COMMAND_POLICY_PROMPT_WRAPPER_KEY,
    VALID_CONTEXT_MODES,
)
from gpd.core.registry_types import (
    CommandOutputPolicy,
    CommandPolicy,
    CommandSubjectPolicy,
    CommandSupportingContextPolicy,
    ReviewCommandContract,
)

_COMMAND_POLICY_FIELD_ORDER = (
    "schema_version",
    "subject_policy",
    "supporting_context_policy",
    "output_policy",
)
_COMMAND_POLICY_SUBJECT_FIELD_ORDER = (
    "subject_kind",
    "resolution_mode",
    "explicit_input_kinds",
    "allow_external_subjects",
    "allow_interactive_without_subject",
    "supported_roots",
    "allowed_suffixes",
    "bootstrap_allowed",
)
_COMMAND_POLICY_SUPPORTING_CONTEXT_FIELD_ORDER = (
    "project_context_mode",
    "project_reentry_mode",
    "required_file_patterns",
    "optional_file_patterns",
)
_COMMAND_POLICY_OUTPUT_FIELD_ORDER = (
    "output_mode",
    "managed_root_kind",
    "default_output_subtree",
    "stage_artifact_policy",
)
_COMMAND_POLICY_KEYS = frozenset(_COMMAND_POLICY_FIELD_ORDER)
_COMMAND_POLICY_SUBJECT_KEYS = frozenset(_COMMAND_POLICY_SUBJECT_FIELD_ORDER)
_COMMAND_POLICY_SUPPORTING_CONTEXT_KEYS = frozenset(_COMMAND_POLICY_SUPPORTING_CONTEXT_FIELD_ORDER)
_COMMAND_POLICY_OUTPUT_KEYS = frozenset(_COMMAND_POLICY_OUTPUT_FIELD_ORDER)


def _normalize_command_policy_string(
    value: object,
    *,
    field_name: str,
    command_name: str,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} for {command_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} for {command_name} must be a non-empty string")
    return normalized


def _normalize_command_policy_bool(
    value: object,
    *,
    field_name: str,
    command_name: str,
) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} for {command_name} must be a boolean")


def _normalize_command_policy_string_list(
    value: object,
    *,
    field_name: str,
    command_name: str,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} for {command_name} must be a list of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} for {command_name} must contain only strings")
        entry = item.strip()
        if not entry:
            raise ValueError(f"{field_name} for {command_name} must not contain blank entries")
        if entry in seen:
            raise ValueError(f"{field_name} for {command_name} must not contain duplicates")
        seen.add(entry)
        normalized.append(entry)
    return normalized


def _normalize_command_policy_context_mode(
    value: object,
    *,
    field_name: str,
    command_name: str,
) -> str:
    normalized = _normalize_command_policy_string(
        value,
        field_name=field_name,
        command_name=command_name,
    ).lower()
    if normalized not in VALID_CONTEXT_MODES:
        valid = ", ".join(VALID_CONTEXT_MODES)
        raise ValueError(f"{field_name} for {command_name} must be one of: {valid}")
    return normalized


def _command_policy_frontmatter_value(
    meta: dict[str, object],
    *,
    command_name: str,
) -> tuple[object, bool]:
    """Return the canonical command-policy frontmatter payload and whether it was explicit."""

    if COMMAND_POLICY_PROMPT_WRAPPER_KEY in meta:
        raise ValueError(
            f"command-policy for {command_name} must use the canonical frontmatter key "
            f"'{COMMAND_POLICY_FRONTMATTER_KEY}'"
        )
    if COMMAND_POLICY_FRONTMATTER_KEY not in meta:
        return None, False
    return meta.get(COMMAND_POLICY_FRONTMATTER_KEY), True


def _command_policy_supporting_context_from_frontmatter(
    *,
    context_mode: str,
    project_reentry_capable: bool,
    requires: dict[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_context_mode": context_mode,
        "project_reentry_mode": "allowed" if project_reentry_capable else "disallowed",
    }
    required_files = requires.get("files")
    if isinstance(required_files, list) and required_files:
        payload["required_file_patterns"] = list(required_files)
    return payload


def _command_policy_requests_check(
    review_contract: ReviewCommandContract | None,
    check_name: str,
) -> bool:
    if review_contract is None:
        return False
    return check_name in list(getattr(review_contract, "preflight_checks", []) or [])


def _command_policy_is_publication_contract(review_contract: ReviewCommandContract | None) -> bool:
    return str(getattr(review_contract, "review_mode", "") or "").strip() == "publication"


def _command_policy_supported_roots_from_patterns(patterns: list[str]) -> list[str]:
    supported_roots: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        parts = Path(pattern).parts
        if not parts:
            continue
        root = parts[0].strip()
        if not root or root in seen:
            continue
        seen.add(root)
        supported_roots.append(root)
    return supported_roots


def _publication_contract_mentions_external_artifact(review_contract: ReviewCommandContract | None) -> bool:
    if review_contract is None:
        return False
    textual_cues = [
        *(str(item) for item in list(getattr(review_contract, "required_evidence", []) or [])),
        *(str(item) for item in list(getattr(review_contract, "blocking_conditions", []) or [])),
    ]
    return any("external-artifact review" in cue.casefold() for cue in textual_cues)


def _publication_subject_policy_defaults(
    *,
    review_contract: ReviewCommandContract | None,
    frontmatter_supporting_context: dict[str, object],
) -> dict[str, object] | None:
    if not _command_policy_is_publication_contract(review_contract):
        return None
    if not _command_policy_requests_check(review_contract, "manuscript"):
        return None

    required_patterns = [
        str(pattern).strip()
        for pattern in list(frontmatter_supporting_context.get("required_file_patterns", []) or [])
        if str(pattern).strip()
    ]
    supported_roots = _command_policy_supported_roots_from_patterns(required_patterns)
    allow_external_subjects = _publication_contract_mentions_external_artifact(review_contract)
    bootstrap_allowed = (
        not required_patterns
        and not _command_policy_requests_check(review_contract, "compiled_manuscript")
        and not _command_policy_requests_check(review_contract, "referee_report_source")
    )

    explicit_input_kinds: list[str] = []
    if _command_policy_requests_check(review_contract, "referee_report_source"):
        explicit_input_kinds.extend(["referee_report_path", "paste_referee_report"])
    elif supported_roots:
        explicit_input_kinds.extend(["manuscript_root", "manuscript_path"])
    if allow_external_subjects:
        explicit_input_kinds.append("publication_artifact_path")

    allowed_suffixes = [".tex"]
    if not _command_policy_requests_check(review_contract, "compiled_manuscript"):
        allowed_suffixes.append(".md")
    if allow_external_subjects:
        for suffix in (".txt", ".pdf"):
            if suffix not in allowed_suffixes:
                allowed_suffixes.append(suffix)

    resolution_mode = "project_manuscript"
    if bootstrap_allowed:
        resolution_mode = "project_manuscript_or_bootstrap"
    elif _command_policy_requests_check(review_contract, "referee_report_source"):
        resolution_mode = "project_manuscript_with_report_source"
    elif explicit_input_kinds:
        resolution_mode = "explicit_or_project_manuscript"

    payload: dict[str, object] = {
        "subject_kind": "publication",
        "resolution_mode": resolution_mode,
        "allowed_suffixes": allowed_suffixes,
    }
    if explicit_input_kinds:
        payload["explicit_input_kinds"] = explicit_input_kinds
    if supported_roots:
        payload["supported_roots"] = supported_roots
    if allow_external_subjects:
        payload["allow_external_subjects"] = True
    if (
        allow_external_subjects
        and str(frontmatter_supporting_context.get("project_context_mode", "")).strip() == "project-aware"
    ):
        payload["allow_interactive_without_subject"] = True
    if bootstrap_allowed:
        payload["bootstrap_allowed"] = True
    return payload


def _merge_command_policy_defaults(
    explicit_mapping: dict[str, object] | None,
    default_mapping: dict[str, object] | None,
) -> dict[str, object] | None:
    if default_mapping is None:
        return dict(explicit_mapping) if explicit_mapping is not None else None
    if explicit_mapping is None:
        return dict(default_mapping)
    merged = dict(default_mapping)
    merged.update(explicit_mapping)
    return merged


def _merge_command_policy_submapping(
    explicit_mapping: dict[str, object] | None,
    companion_mapping: dict[str, object] | None,
    *,
    field_name: str,
    command_name: str,
    allow_explicit_override: bool = False,
) -> dict[str, object] | None:
    if explicit_mapping is None:
        if companion_mapping:
            return dict(companion_mapping)
        return None
    if not companion_mapping:
        return dict(explicit_mapping)

    merged = dict(companion_mapping)
    for key, value in explicit_mapping.items():
        companion_value = merged.get(key)
        if companion_value is None or companion_value == []:
            merged[key] = value
            continue
        if allow_explicit_override:
            merged[key] = value
            continue
        if value != companion_value:
            raise ValueError(f"{field_name}.{key} for {command_name} must stay aligned with companion command metadata")
    return merged


def _normalize_command_subject_policy(
    raw: object,
    *,
    command_name: str,
) -> dict[str, object] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(f"command_policy.subject_policy for {command_name} must be a mapping")
    raw_mapping = dict(raw)
    unknown_keys = sorted(str(key) for key in raw_mapping if str(key) not in _COMMAND_POLICY_SUBJECT_KEYS)
    if unknown_keys:
        formatted = ", ".join(unknown_keys)
        raise ValueError(f"Unknown command-policy field(s): subject_policy.{formatted}")

    normalized: dict[str, object] = {}
    for field_name in ("subject_kind", "resolution_mode"):
        if field_name in raw_mapping:
            normalized[field_name] = _normalize_command_policy_string(
                raw_mapping.get(field_name),
                field_name=f"command_policy.subject_policy.{field_name}",
                command_name=command_name,
            )
    for field_name in ("allow_external_subjects", "allow_interactive_without_subject", "bootstrap_allowed"):
        if field_name in raw_mapping:
            normalized[field_name] = _normalize_command_policy_bool(
                raw_mapping.get(field_name),
                field_name=f"command_policy.subject_policy.{field_name}",
                command_name=command_name,
            )
    for field_name in ("explicit_input_kinds", "supported_roots", "allowed_suffixes"):
        if field_name in raw_mapping:
            normalized[field_name] = _normalize_command_policy_string_list(
                raw_mapping.get(field_name),
                field_name=f"command_policy.subject_policy.{field_name}",
                command_name=command_name,
            )
    allowed_suffixes = normalized.get("allowed_suffixes")
    if isinstance(allowed_suffixes, list):
        invalid_suffixes = [suffix for suffix in allowed_suffixes if not suffix.startswith(".")]
        if invalid_suffixes:
            formatted = ", ".join(repr(item) for item in invalid_suffixes)
            raise ValueError(
                f"command_policy.subject_policy.allowed_suffixes for {command_name} "
                f"must contain dotted suffixes like '.tex'; got {formatted}"
            )
    return normalized or None


def _normalize_command_supporting_context_policy(
    raw: object,
    *,
    command_name: str,
) -> dict[str, object] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(f"command_policy.supporting_context_policy for {command_name} must be a mapping")
    raw_mapping = dict(raw)
    unknown_keys = sorted(str(key) for key in raw_mapping if str(key) not in _COMMAND_POLICY_SUPPORTING_CONTEXT_KEYS)
    if unknown_keys:
        formatted = ", ".join(unknown_keys)
        raise ValueError(f"Unknown command-policy field(s): supporting_context_policy.{formatted}")

    normalized: dict[str, object] = {}
    if "project_context_mode" in raw_mapping:
        normalized["project_context_mode"] = _normalize_command_policy_context_mode(
            raw_mapping.get("project_context_mode"),
            field_name="command_policy.supporting_context_policy.project_context_mode",
            command_name=command_name,
        )
    if "project_reentry_mode" in raw_mapping:
        normalized["project_reentry_mode"] = _normalize_command_policy_string(
            raw_mapping.get("project_reentry_mode"),
            field_name="command_policy.supporting_context_policy.project_reentry_mode",
            command_name=command_name,
        )
    for field_name in ("required_file_patterns", "optional_file_patterns"):
        if field_name in raw_mapping:
            normalized[field_name] = _normalize_command_policy_string_list(
                raw_mapping.get(field_name),
                field_name=f"command_policy.supporting_context_policy.{field_name}",
                command_name=command_name,
            )
    return normalized or None


def _normalize_command_output_policy(
    raw: object,
    *,
    command_name: str,
) -> dict[str, object] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(f"command_policy.output_policy for {command_name} must be a mapping")
    raw_mapping = dict(raw)
    unknown_keys = sorted(str(key) for key in raw_mapping if str(key) not in _COMMAND_POLICY_OUTPUT_KEYS)
    if unknown_keys:
        formatted = ", ".join(unknown_keys)
        raise ValueError(f"Unknown command-policy field(s): output_policy.{formatted}")

    normalized: dict[str, object] = {}
    for field_name in _COMMAND_POLICY_OUTPUT_FIELD_ORDER:
        if field_name in raw_mapping:
            normalized[field_name] = _normalize_command_policy_string(
                raw_mapping.get(field_name),
                field_name=f"command_policy.output_policy.{field_name}",
                command_name=command_name,
            )
    return normalized or None


def _command_policy_payload(command_policy: object) -> dict[str, object] | None:
    def _strip_none_fields(value: object) -> object:
        if isinstance(value, dict):
            return {key: _strip_none_fields(item) for key, item in value.items() if item is not None}
        if isinstance(value, list):
            return [_strip_none_fields(item) for item in value]
        return value

    if command_policy is None:
        return None
    if isinstance(command_policy, Mapping):
        return dict(_strip_none_fields(dict(command_policy)))
    if dataclasses.is_dataclass(command_policy):
        payload = _strip_none_fields(dataclasses.asdict(command_policy))
        return payload if isinstance(payload, dict) else None
    raise ValueError("command policy must be a mapping or dataclass instance")


def _normalize_command_policy_payload(
    command_policy: object,
    *,
    command_name: str,
    context_mode: str,
    project_reentry_capable: bool,
    requires: dict[str, object],
    review_contract: ReviewCommandContract | None = None,
    explicit: bool = False,
) -> dict[str, object]:
    frontmatter_supporting_context = _command_policy_supporting_context_from_frontmatter(
        context_mode=context_mode,
        project_reentry_capable=project_reentry_capable,
        requires=requires,
    )
    default_subject_policy = _publication_subject_policy_defaults(
        review_contract=review_contract,
        frontmatter_supporting_context=frontmatter_supporting_context,
    )
    inferred_payload: dict[str, object] = {
        "schema_version": 1,
        "subject_policy": default_subject_policy,
        "supporting_context_policy": frontmatter_supporting_context,
    }

    payload = _command_policy_payload(command_policy)
    if payload is None:
        if explicit:
            raise ValueError("command policy must set schema_version")
        return inferred_payload
    if not isinstance(payload, dict):
        raise ValueError(f"command policy for {command_name} must be a mapping")

    unknown_keys = sorted(str(key) for key in payload if str(key) not in _COMMAND_POLICY_KEYS)
    if unknown_keys:
        formatted = ", ".join(unknown_keys)
        raise ValueError(f"Unknown command-policy field(s): {formatted}")

    if "schema_version" not in payload:
        raise ValueError("command policy must set schema_version")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ValueError("command policy schema_version must be the integer 1")
    if schema_version != 1:
        raise ValueError("command policy schema_version must be 1")

    subject_policy = _merge_command_policy_defaults(
        _normalize_command_subject_policy(payload.get("subject_policy"), command_name=command_name),
        default_subject_policy,
    )
    supporting_context_policy = _normalize_command_supporting_context_policy(
        payload.get("supporting_context_policy"),
        command_name=command_name,
    )
    effective_frontmatter_supporting_context = frontmatter_supporting_context
    if (
        supporting_context_policy is not None
        and supporting_context_policy.get("project_reentry_mode") == "current-workspace"
        and frontmatter_supporting_context.get("project_reentry_mode") == "allowed"
    ):
        effective_frontmatter_supporting_context = dict(frontmatter_supporting_context)
        effective_frontmatter_supporting_context["project_reentry_mode"] = "current-workspace"
    output_policy = _normalize_command_output_policy(payload.get("output_policy"), command_name=command_name)

    return {
        "schema_version": schema_version,
        "subject_policy": subject_policy,
        "supporting_context_policy": _merge_command_policy_submapping(
            supporting_context_policy,
            effective_frontmatter_supporting_context,
            field_name="command_policy.supporting_context_policy",
            command_name=command_name,
            allow_explicit_override=_command_policy_is_publication_contract(review_contract),
        ),
        "output_policy": output_policy,
    }


def _render_command_policy_submapping(
    payload: dict[str, object] | None,
    *,
    field_order: tuple[str, ...],
) -> dict[str, object] | None:
    if not payload:
        return None
    rendered: dict[str, object] = {}
    for field_name in field_order:
        if field_name not in payload:
            continue
        value = payload[field_name]
        if isinstance(value, list):
            if value:
                rendered[field_name] = value
            continue
        if isinstance(value, bool):
            rendered[field_name] = value
            continue
        if value is not None:
            rendered[field_name] = value
    return rendered or None


def _render_command_policy_payload(
    command_policy: CommandPolicy | dict[str, object] | None,
) -> dict[str, object] | None:
    payload = _command_policy_payload(command_policy)
    if not payload:
        return None

    rendered: dict[str, object] = {"schema_version": int(payload["schema_version"])}
    subject_policy = payload.get("subject_policy")
    if isinstance(subject_policy, dict):
        rendered_subject = _render_command_policy_submapping(
            subject_policy,
            field_order=_COMMAND_POLICY_SUBJECT_FIELD_ORDER,
        )
        if rendered_subject:
            rendered["subject_policy"] = rendered_subject
    supporting_context_policy = payload.get("supporting_context_policy")
    if isinstance(supporting_context_policy, dict):
        rendered_supporting_context = _render_command_policy_submapping(
            supporting_context_policy,
            field_order=_COMMAND_POLICY_SUPPORTING_CONTEXT_FIELD_ORDER,
        )
        if rendered_supporting_context:
            rendered["supporting_context_policy"] = rendered_supporting_context
    output_policy = payload.get("output_policy")
    if isinstance(output_policy, dict):
        rendered_output = _render_command_policy_submapping(
            output_policy,
            field_order=_COMMAND_POLICY_OUTPUT_FIELD_ORDER,
        )
        if rendered_output:
            rendered["output_policy"] = rendered_output
    return rendered


def _parse_command_policy(
    raw: object,
    *,
    command_name: str,
    context_mode: str,
    project_reentry_capable: bool,
    requires: dict[str, object],
    review_contract: ReviewCommandContract | None = None,
    explicit: bool = False,
) -> CommandPolicy:
    if isinstance(raw, CommandPolicy):
        return raw
    try:
        payload = _normalize_command_policy_payload(
            raw,
            command_name=command_name,
            context_mode=context_mode,
            project_reentry_capable=project_reentry_capable,
            requires=requires,
            review_contract=review_contract,
            explicit=explicit,
        )
    except ValueError as exc:
        raise ValueError(f"command-policy for {command_name}: {exc}") from exc

    subject_policy_payload = payload.get("subject_policy")
    supporting_context_payload = payload.get("supporting_context_policy")
    output_policy_payload = payload.get("output_policy")
    return CommandPolicy(
        schema_version=int(payload["schema_version"]),
        subject_policy=(
            CommandSubjectPolicy(**subject_policy_payload) if isinstance(subject_policy_payload, dict) else None
        ),
        supporting_context_policy=(
            CommandSupportingContextPolicy(**supporting_context_payload)
            if isinstance(supporting_context_payload, dict)
            else None
        ),
        output_policy=(
            CommandOutputPolicy(**output_policy_payload) if isinstance(output_policy_payload, dict) else None
        ),
    )


__all__ = [
    "_COMMAND_POLICY_FIELD_ORDER",
    "_COMMAND_POLICY_KEYS",
    "_COMMAND_POLICY_OUTPUT_FIELD_ORDER",
    "_COMMAND_POLICY_OUTPUT_KEYS",
    "_COMMAND_POLICY_SUBJECT_FIELD_ORDER",
    "_COMMAND_POLICY_SUBJECT_KEYS",
    "_COMMAND_POLICY_SUPPORTING_CONTEXT_FIELD_ORDER",
    "_COMMAND_POLICY_SUPPORTING_CONTEXT_KEYS",
    "_command_policy_frontmatter_value",
    "_command_policy_is_publication_contract",
    "_parse_command_policy",
    "_render_command_policy_payload",
]
