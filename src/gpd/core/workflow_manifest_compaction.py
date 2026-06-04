"""Canonicalization for compact workflow stage manifest source payloads."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

_COMPACT_TOP_LEVEL_KEYS = frozenset(
    {
        "authority_groups",
        "cold_authority_policy",
        "derived_init_field_rules",
        "stage_defaults",
    }
)
_COMPACT_STAGE_KEYS = frozenset({"must_not_eager_load_groups"})
_STAGE_DEFAULT_KEYS = frozenset(
    {
        "mode_paths",
        "required_init_field_groups",
        "required_init_fields",
        "loaded_authorities",
        "conditional_authorities",
        "must_not_eager_load",
        "must_not_eager_load_groups",
        "allowed_tools",
        "writes_allowed",
        "produced_state",
        "next_stages",
        "checkpoints",
    }
)
_REQUIRED_INIT_FIELD_RULE_PROTOCOL_BUNDLE_LOAD_MANIFEST = (
    "protocol_bundle_load_manifest_for_protocol_context"
)
_SUPPORTED_DERIVED_INIT_FIELD_RULES = frozenset(
    {
        _REQUIRED_INIT_FIELD_RULE_PROTOCOL_BUNDLE_LOAD_MANIFEST,
    }
)
_DEFAULT_DERIVED_INIT_FIELD_RULES = (_REQUIRED_INIT_FIELD_RULE_PROTOCOL_BUNDLE_LOAD_MANIFEST,)
_COLD_AUTHORITY_POLICY_WORKFLOW_STAGE_AUTHORITIES = "workflow_stage_authorities_cold_except_eager"
_SUPPORTED_COLD_AUTHORITY_POLICIES = frozenset({_COLD_AUTHORITY_POLICY_WORKFLOW_STAGE_AUTHORITIES})


def canonicalize_workflow_stage_manifest_payload(raw: object) -> object:
    """Return an expanded schema-v1 manifest payload for strict validation.

    This is intentionally IO-free: authority path normalization, existence checks,
    allowed-tool validation, topology validation, and eager/lazy overlap checks
    remain owned by ``workflow_staging`` after this expansion pass.
    """

    if not isinstance(raw, dict):
        return raw

    payload = deepcopy(raw)
    required_init_field_groups = _string_groups(
        payload.get("required_init_field_groups"),
        label="required_init_field_groups",
        allow_empty_entries=False,
    )
    authority_groups = _string_groups(payload.get("authority_groups"), label="authority_groups")
    stage_defaults = _stage_defaults(payload.get("stage_defaults"))
    derived_init_field_rules = _derived_init_field_rules(payload.get("derived_init_field_rules"))
    cold_authority_policy = _cold_authority_policy(payload.get("cold_authority_policy"))

    stages = payload.get("stages")
    if isinstance(stages, list):
        expanded_stages = _canonicalize_stages(
            stages,
            stage_defaults=stage_defaults,
            required_init_field_groups=required_init_field_groups,
            authority_groups=authority_groups,
            derived_init_field_rules=derived_init_field_rules,
            cold_authority_policy=cold_authority_policy,
        )
        payload["stages"] = expanded_stages

    for key in (*_COMPACT_TOP_LEVEL_KEYS, "required_init_field_groups"):
        payload.pop(key, None)
    return payload


def _canonicalize_stages(
    stages: list[object],
    *,
    stage_defaults: dict[str, object],
    required_init_field_groups: dict[str, tuple[str, ...]],
    authority_groups: dict[str, tuple[str, ...]],
    derived_init_field_rules: tuple[str, ...],
    cold_authority_policy: str | None,
) -> list[object]:
    merged_stages = [
        _merge_stage_defaults(stage, stage_defaults=stage_defaults) if isinstance(stage, dict) else stage
        for stage in stages
    ]
    workflow_stage_authorities = _workflow_stage_authorities(merged_stages) if cold_authority_policy else ()

    expanded_stages: list[object] = []
    for index, stage in enumerate(merged_stages):
        if not isinstance(stage, dict):
            expanded_stages.append(stage)
            continue
        expanded_stages.append(
            _canonicalize_stage(
                stage,
                index=index,
                required_init_field_groups=required_init_field_groups,
                authority_groups=authority_groups,
                derived_init_field_rules=derived_init_field_rules,
                cold_authority_policy=cold_authority_policy,
                workflow_stage_authorities=workflow_stage_authorities,
            )
        )
    return expanded_stages


def _merge_stage_defaults(stage: dict[object, object], *, stage_defaults: dict[str, object]) -> dict[object, object]:
    if not stage_defaults:
        return deepcopy(stage)
    merged: dict[object, object] = deepcopy(stage_defaults)
    merged.update(deepcopy(stage))
    return merged


def _canonicalize_stage(
    stage: dict[object, object],
    *,
    index: int,
    required_init_field_groups: dict[str, tuple[str, ...]],
    authority_groups: dict[str, tuple[str, ...]],
    derived_init_field_rules: tuple[str, ...],
    cold_authority_policy: str | None,
    workflow_stage_authorities: tuple[str, ...],
) -> dict[object, object]:
    expanded = deepcopy(stage)
    if "required_init_field_groups" in expanded or "required_init_fields" in expanded:
        expanded["required_init_fields"] = list(
            _expand_required_init_fields(
                expanded,
                index=index,
                groups=required_init_field_groups,
                derived_init_field_rules=derived_init_field_rules,
            )
        )
    expanded.pop("required_init_field_groups", None)

    must_not_eager_load = _expand_must_not_eager_load(
        expanded,
        index=index,
        authority_groups=authority_groups,
        cold_authority_policy=cold_authority_policy,
        workflow_stage_authorities=workflow_stage_authorities,
    )
    if must_not_eager_load is not None:
        expanded["must_not_eager_load"] = list(must_not_eager_load)
    expanded.pop("must_not_eager_load_groups", None)
    return expanded


def _expand_required_init_fields(
    stage: dict[object, object],
    *,
    index: int,
    groups: dict[str, tuple[str, ...]],
    derived_init_field_rules: tuple[str, ...],
) -> tuple[str, ...]:
    fields: list[str] = []
    for group_name in _string_sequence(
        stage.get("required_init_field_groups", []),
        label=f"stages[{index}].required_init_field_groups",
        allow_empty=True,
    ):
        group_fields = groups.get(group_name)
        if group_fields is None:
            raise ValueError(f"stages[{index}].required_init_field_groups references unknown group: {group_name}")
        fields.extend(group_fields)

    fields.extend(
        _string_sequence(
            stage.get("required_init_fields", []),
            label=f"stages[{index}].required_init_fields",
            allow_empty=True,
        )
    )

    if _REQUIRED_INIT_FIELD_RULE_PROTOCOL_BUNDLE_LOAD_MANIFEST in derived_init_field_rules:
        fields = _with_protocol_bundle_load_manifest(fields)
    return tuple(fields)


def _with_protocol_bundle_load_manifest(fields: list[str]) -> list[str]:
    if "protocol_bundle_context" not in fields or "protocol_bundle_load_manifest" in fields:
        return fields
    expanded = list(fields)
    for anchor in ("protocol_bundle_count", "selected_protocol_bundle_ids"):
        if anchor in expanded:
            expanded.insert(expanded.index(anchor) + 1, "protocol_bundle_load_manifest")
            return expanded
    expanded.insert(expanded.index("protocol_bundle_context"), "protocol_bundle_load_manifest")
    return expanded


def _expand_must_not_eager_load(
    stage: dict[object, object],
    *,
    index: int,
    authority_groups: dict[str, tuple[str, ...]],
    cold_authority_policy: str | None,
    workflow_stage_authorities: tuple[str, ...],
) -> tuple[str, ...] | None:
    if (
        "must_not_eager_load" not in stage
        and "must_not_eager_load_groups" not in stage
        and cold_authority_policy is None
    ):
        return None

    authorities = list(
        _string_sequence(
            stage.get("must_not_eager_load", []),
            label=f"stages[{index}].must_not_eager_load",
            allow_empty=True,
        )
    )
    for group_name in _string_sequence(
        stage.get("must_not_eager_load_groups", []),
        label=f"stages[{index}].must_not_eager_load_groups",
        allow_empty=True,
    ):
        group_authorities = authority_groups.get(group_name)
        if group_authorities is None:
            raise ValueError(f"stages[{index}].must_not_eager_load_groups references unknown group: {group_name}")
        authorities.extend(group_authorities)

    if cold_authority_policy == _COLD_AUTHORITY_POLICY_WORKFLOW_STAGE_AUTHORITIES:
        unconditional_eager = set(
            _string_sequence(stage.get("mode_paths", []), label=f"stages[{index}].mode_paths", allow_empty=True)
        )
        unconditional_eager.update(
            _string_sequence(
                stage.get("loaded_authorities", []),
                label=f"stages[{index}].loaded_authorities",
                allow_empty=True,
            )
        )
        for authority in workflow_stage_authorities:
            if authority not in unconditional_eager:
                authorities.append(authority)
    return tuple(authorities)


def _workflow_stage_authorities(stages: Iterable[object]) -> tuple[str, ...]:
    authorities: list[str] = []
    seen: set[str] = set()
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue
        for authority in _string_sequence(
            stage.get("mode_paths", []),
            label=f"stages[{index}].mode_paths",
            allow_empty=True,
        ):
            if authority in seen:
                continue
            seen.add(authority)
            authorities.append(authority)
    return tuple(authorities)


def _stage_defaults(raw: object) -> dict[str, object]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("stage_defaults must be an object")
    unknown_keys = sorted(str(key) for key in raw if str(key) not in _STAGE_DEFAULT_KEYS)
    if unknown_keys:
        raise ValueError(f"stage_defaults contains unexpected key(s): {', '.join(unknown_keys)}")
    return {str(key): deepcopy(value) for key, value in raw.items()}


def _string_groups(raw: object, *, label: str, allow_empty_entries: bool = True) -> dict[str, tuple[str, ...]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    groups: dict[str, tuple[str, ...]] = {}
    for raw_name, raw_values in raw.items():
        name = _required_string(raw_name, label=f"{label} key")
        groups[name] = _string_sequence(
            raw_values,
            label=f"{label}.{name}",
            allow_empty=allow_empty_entries,
        )
    return groups


def _derived_init_field_rules(raw: object) -> tuple[str, ...]:
    rules = (
        _DEFAULT_DERIVED_INIT_FIELD_RULES
        if raw is None
        else _string_sequence(raw, label="derived_init_field_rules", allow_empty=True)
    )
    unknown_rules = sorted(rule for rule in rules if rule not in _SUPPORTED_DERIVED_INIT_FIELD_RULES)
    if unknown_rules:
        raise ValueError(f"derived_init_field_rules contains unknown rule(s): {', '.join(unknown_rules)}")
    return tuple(rules)


def _cold_authority_policy(raw: object) -> str | None:
    if raw is None:
        return None
    policy = _required_string(raw, label="cold_authority_policy")
    if policy not in _SUPPORTED_COLD_AUTHORITY_POLICIES:
        raise ValueError(
            "cold_authority_policy must be one of: "
            f"{', '.join(sorted(_SUPPORTED_COLD_AUTHORITY_POLICIES))}"
        )
    return policy


def _string_sequence(raw: object, *, label: str, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{label} must be a list")
    values: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        value = _required_string(item, label=f"{label}[{index}]")
        if value in seen:
            raise ValueError(f"{label} must not contain duplicate entries")
        seen.add(value)
        values.append(value)
    if not values and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    return tuple(values)


def _required_string(raw: object, *, label: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{label} must be a non-empty string")
    value = raw.strip()
    if not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


__all__ = ["canonicalize_workflow_stage_manifest_payload"]
