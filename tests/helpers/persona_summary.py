"""Shared helpers for sanitized persona summary policy tests."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

from gpd.adapters.runtime_catalog import iter_runtime_descriptors

PHASE4_SCHEMA_VERSION = "phase4.persona-live-smoke-summary.v1"
PHASE7_SCHEMA_VERSION = "phase7.live-persona-canary-summary.v1"

CLASS_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
DEFAULT_RAW_KEY_FRAGMENTS = (
    "account",
    "argv",
    "auth",
    "command",
    "command_line",
    "content",
    "credential",
    "diff",
    "env",
    "hash",
    "home",
    "path",
    "prompt",
    "provider",
    "provider_output",
    "provider_reply",
    "raw",
    "raw_prompt",
    "request",
    "reply",
    "secret",
    "session",
    "stderr",
    "stdout",
    "trace",
    "token",
    "transcript",
    "usage",
)
SAFE_PHASE4_TRIGGERS = frozenset({"operator_local_manual", "workflow_dispatch_summary_validation"})
SAFE_PHASE7_NIGHTLY_TRIGGERS = frozenset({"workflow_dispatch", "schedule"})

_SHELL_SEGMENT_SPLIT_RE = re.compile(r"(?:&&|\|\||[;|()])")
_SHELL_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
_SHELL_COMMAND_PREFIXES = frozenset({"builtin", "command", "exec", "sudo", "time"})
_WRAPPER_TERMINATING_OPTIONS = frozenset({"--help", "--version", "-h", "-V"})
_ENV_OPTION_VALUE_NAMES = frozenset(
    {
        "--block-signal",
        "--chdir",
        "--default-signal",
        "--ignore-signal",
        "--split-string",
        "--unset",
        "-C",
        "-S",
        "-u",
    }
)
_UV_RUN_OPTION_VALUE_NAMES = frozenset(
    {
        "--build-constraint",
        "--config-file",
        "--default-index",
        "--directory",
        "--env-file",
        "--exclude-newer",
        "--extra",
        "--extra-index-url",
        "--find-links",
        "--fork-strategy",
        "--group",
        "--index",
        "--index-strategy",
        "--index-url",
        "--keyring-provider",
        "--link-mode",
        "--module",
        "--no-group",
        "--only-group",
        "--prerelease",
        "--project",
        "--python",
        "--python-platform",
        "--refresh-package",
        "--resolution",
        "--with",
        "--with-editable",
        "--with-requirements",
        "-C",
        "-m",
        "-p",
    }
)
_UVX_OPTION_VALUE_NAMES = _UV_RUN_OPTION_VALUE_NAMES | frozenset({"--from"})
_PYTHON_RUNNER_OPTION_VALUE_NAMES = frozenset(
    {
        "--index-url",
        "--pip-args",
        "--python",
        "--spec",
        "--suffix",
    }
)
_NODE_RUNNER_OPTION_VALUE_NAMES = frozenset(
    {
        "--cache",
        "--call",
        "--package",
        "--prefix",
        "--registry",
        "--script-shell",
        "--userconfig",
        "-c",
        "-p",
    }
)


def _runtime_launch_command_names() -> frozenset[str]:
    names: set[str] = set()
    for descriptor in iter_runtime_descriptors():
        tokens = shlex.split(descriptor.launch_command)
        if tokens:
            names.add(Path(tokens[0]).name)
    return frozenset(names)


PROVIDER_LAUNCH_COMMANDS = _runtime_launch_command_names()


def _secret_env_name_pattern() -> re.Pattern[str]:
    prefixes = frozenset({"ANTHROPIC", "CLAUDE", "CODEX", "GEMINI", "GOOGLE", "OPENAI", "OPENCODE"}) | frozenset(
        command.upper().replace("-", "_") for command in PROVIDER_LAUNCH_COMMANDS
    )
    prefix_pattern = "|".join(sorted(re.escape(prefix) for prefix in prefixes))
    return re.compile(
        rf"(?<![A-Z0-9_])(?:{prefix_pattern})_"
        r"(?:API_KEY|AUTH_TOKEN|OAUTH_TOKEN|ACCESS_TOKEN|SECRET|TOKEN|CREDENTIALS|"
        r"CREDENTIALS_JSON|SERVICE_ACCOUNT)"
        r"(?![A-Z0-9_])"
    )


DEFAULT_RAW_VALUE_PATTERNS = MappingProxyType(
    {
        "absolute_path": re.compile(
            r"(?<![A-Za-z0-9_])(?:/(?:Users|home|private|tmp|var|etc|Volumes|opt|mnt|root|workspace)\b|"
            r"[A-Za-z]:\\Users\\|~[/\\])"
        ),
        "parent_traversal": re.compile(r"(?:^|[/\\])\.\.(?:[/\\]|$)"),
        "provider_secret_env_name": _secret_env_name_pattern(),
        "secret_material": re.compile(
            r"\b(?:api[_ -]?key|auth[_ -]?token|oauth[_ -]?token|access[_ -]?token|"
            r"client[_ -]?secret|secret(?:[_ -]?(?:key|token|value|material))?)\b",
            re.IGNORECASE,
        ),
        "token_like": re.compile(
            r"(?:\bBearer\s+[A-Za-z0-9._-]{8,}|sk-[A-Za-z0-9]{12,}|"
            r"ghp_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{20,}|"
            r"xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{10,}|"
            r"ya29\.[0-9A-Za-z_-]{10,}|glpat-[A-Za-z0-9_-]{10,}|"
            r"hf_[A-Za-z0-9]{10,}|pk_(?:live|test)_[A-Za-z0-9]{10,}|"
            r"\b[A-Za-z0-9+/]{40,}={0,2}\b)",
            re.IGNORECASE,
        ),
        "hash": re.compile(r"\b(?:[A-Fa-f0-9]{32}|[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})\b"),
        "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "account_identifier": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "raw_artifact_file": re.compile(
            r"\b(?:prompt(?:\.enveloped)?\.txt|command\.(?:json|txt)|env\.json|"
            r"stdout\.(?:jsonl|txt)|stderr\.txt|transcript\.md|raw[-_]transcript\.md|"
            r"provider[-_]output\.(?:txt|log)|provider[-_]reply\.txt|"
            r"provider_output\.txt|provider_reply\.txt)\b",
            re.IGNORECASE,
        ),
        "raw_stream_or_capture": re.compile(
            r"(?<![A-Za-z0-9])(?:stdout|stderr|argv|env)(?![A-Za-z0-9])", re.IGNORECASE
        ),
        "provider_prompt_or_reply": re.compile(
            r"\b(?:raw[_ -]?prompt|provider[_ -]?prompt|prompt(?:[_ -]?text)?|prompt:|"
            r"raw provider reply|provider reply|provider[_-](?:prompt|reply|output)|"
            r"assistant[_ -]?reply|assistant replied|model[_ -]?reply|"
            r"final answer text|transcript excerpt)\b",
            re.IGNORECASE,
        ),
        "provider_request_id": re.compile(r"(?<![A-Za-z0-9])req_[A-Za-z0-9_:-]{8,}", re.IGNORECASE),
        "provider_trace_id": re.compile(r"(?<![A-Za-z0-9])trace_[A-Za-z0-9_:-]{8,}", re.IGNORECASE),
        "provider_usage_json": re.compile(r"\busage[_-]?json\b", re.IGNORECASE),
        "runtime_home_alias": re.compile(
            r"\b(?:ANTHROPIC|CLAUDE|CODEX|GEMINI|GOOGLE|OPENAI|OPENCODE)_HOME\b",
            re.IGNORECASE,
        ),
        "raw_diff_sidecar": re.compile(r"\braw[_-]?diff[_-]?sidecar\.(?:diff|json|patch|txt)\b", re.IGNORECASE),
        "provider_command_details": re.compile(r"\bprovider[_-]?command[_-]?details\b", re.IGNORECASE),
    }
)


@dataclass(frozen=True)
class PersonaSummaryPolicy:
    """Class-only public summary rules for one persona canary surface."""

    schema_version: str
    required_values: Mapping[str, object]
    safe_literal_keys: frozenset[str]
    safe_container_keys: frozenset[str]
    allowed_list_values: Mapping[str, frozenset[str]] = field(default_factory=dict)
    raw_key_fragments: tuple[str, ...] = DEFAULT_RAW_KEY_FRAGMENTS
    raw_value_patterns: Mapping[str, re.Pattern[str]] = field(default_factory=lambda: DEFAULT_RAW_VALUE_PATTERNS)


@dataclass(frozen=True)
class PersonaSummaryValidationResult:
    findings: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.findings


_COMMON_SAFE_LITERAL_KEYS = frozenset(
    {
        "finding_count",
        "report_id",
        "row_count",
        "row_id",
        "schema_version",
        "raw_artifact_retention_class",
        "provider_launch_source_class",
    }
)
_COMMON_SAFE_CONTAINER_KEYS = frozenset(
    {
        "aggregate_class_counts",
        "event_class_counts",
        "finding_classes",
        "redaction_scan",
        "rows",
    }
)
_PHASE4_SAFE_LITERAL_KEYS = _COMMON_SAFE_LITERAL_KEYS | frozenset(
    {
        "ci_provider_launch_allowed",
        "invalid_command_suggestion_count",
        "manual_provider_launch_allowed",
        "schema_repair_loop_count",
        "unexpected_write_count",
    }
)
_PHASE4_SAFE_CONTAINER_KEYS = _COMMON_SAFE_CONTAINER_KEYS | frozenset(
    {
        "allowed_trigger_classes",
        "behavior_class_counts",
        "behavior_metric_counts",
    }
)
_PHASE7_SAFE_LITERAL_KEYS = _COMMON_SAFE_LITERAL_KEYS | frozenset(
    {
        "content_hydration_before_selection_count",
        "conversation_turn_count",
        "ci_provider_launch_allowed",
        "invalid_command_suggestion_count",
        "release_publish_provider_launch_allowed",
        "manual_provider_launch_allowed",
        "missing_runtime_command_label_count",
        "physics_progress_count",
        "prompt_variant_class",
        "raw_reload_leakage_count",
        "rendered_public_raw_reload_class",
        "runtime_command_rendering_class",
        "wrong_runtime_prefix_count",
        "stale_artifact_trust_count",
        "post_stop_activity_count",
        "unexpected_write_count",
        "unsupported_completion_claim_count",
        "progress_reconcile_write_count",
        "project_lost_claim_count",
        "embedded_instruction_followed_count",
        "premature_agent_write_count",
        "same_run_revision_loop_count",
        "stale_scope_continuation_count",
        "same_gap_reverification_loop_count",
        "malformed_child_return_trust_count",
        "autonomous_child_cycle_overreach_count",
        "schema_repair_loop_count",
        "schema_surface_count",
    }
)
_PHASE7_SAFE_CONTAINER_KEYS = _COMMON_SAFE_CONTAINER_KEYS | frozenset({"nightly_allowed_triggers"})


def phase4_live_smoke_policy() -> PersonaSummaryPolicy:
    return PersonaSummaryPolicy(
        schema_version=PHASE4_SCHEMA_VERSION,
        required_values={
            "execution_mode_class": "manual_opt_in",
            "trigger_class": "operator_local_manual",
            "raw_artifact_retention_class": "operator_local_ignored_tmp",
            "public_artifact_class": "sanitized_class_only_summary",
            "provider_launch_source_class": "manual_operator",
            "ci_provider_launch_allowed": False,
        },
        safe_literal_keys=_PHASE4_SAFE_LITERAL_KEYS,
        safe_container_keys=_PHASE4_SAFE_CONTAINER_KEYS,
        allowed_list_values={"allowed_trigger_classes": SAFE_PHASE4_TRIGGERS},
    )


def phase7_live_canary_policy() -> PersonaSummaryPolicy:
    return PersonaSummaryPolicy(
        schema_version=PHASE7_SCHEMA_VERSION,
        required_values={
            "execution_mode_class": "manual_opt_in",
            "trigger_class": "operator_local_manual",
            "raw_artifact_retention_class": "operator_local_ignored_tmp",
            "public_artifact_class": "sanitized_class_only_summary",
            "provider_launch_source_class": "manual_operator",
            "ci_provider_launch_allowed": False,
            "release_publish_provider_launch_allowed": False,
            "nightly_status_class": "deferred",
        },
        safe_literal_keys=_PHASE7_SAFE_LITERAL_KEYS,
        safe_container_keys=_PHASE7_SAFE_CONTAINER_KEYS,
        allowed_list_values={"nightly_allowed_triggers": SAFE_PHASE7_NIGHTLY_TRIGGERS},
    )


def _path_label(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "$"


def _shell_tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return []


def _token_name(token: str) -> str:
    return Path(token).name


def _strip_assignments(tokens: Sequence[str]) -> list[str]:
    remaining = list(tokens)
    while remaining and _SHELL_ASSIGNMENT_RE.fullmatch(remaining[0]):
        remaining.pop(0)
    return remaining


def _strip_wrapper_options(tokens: Sequence[str], value_option_names: frozenset[str]) -> list[str]:
    remaining = list(tokens)
    while remaining:
        token = remaining[0]
        if token == "--":
            return remaining[1:]
        option_name = token.split("=", 1)[0]
        if option_name in _WRAPPER_TERMINATING_OPTIONS:
            return []
        if not token.startswith("-") or token == "-":
            return remaining
        remaining.pop(0)
        if option_name in value_option_names and "=" not in token and remaining:
            remaining.pop(0)
    return remaining


def _strip_env_options_and_assignments(tokens: Sequence[str]) -> list[str]:
    remaining = list(tokens)
    while remaining:
        token = remaining[0]
        if _SHELL_ASSIGNMENT_RE.fullmatch(token):
            remaining.pop(0)
            continue
        if token == "--":
            return remaining[1:]
        option_name = token.split("=", 1)[0]
        if option_name in _WRAPPER_TERMINATING_OPTIONS:
            return []
        if token.startswith("-") and token != "-":
            remaining.pop(0)
            if option_name in _ENV_OPTION_VALUE_NAMES and "=" not in token and remaining:
                remaining.pop(0)
            continue
        return remaining
    return remaining


def _provider_launch_command_in_tokens(tokens: Sequence[str]) -> str | None:
    remaining = _strip_assignments(tokens)
    while remaining and _token_name(remaining[0]) in _SHELL_COMMAND_PREFIXES:
        remaining.pop(0)
        remaining = _strip_assignments(remaining)
    if remaining and _token_name(remaining[0]) == "env":
        remaining.pop(0)
        remaining = _strip_env_options_and_assignments(remaining)
    if len(remaining) >= 2 and [_token_name(remaining[0]), remaining[1]] == ["uv", "run"]:
        remaining = _strip_wrapper_options(remaining[2:], _UV_RUN_OPTION_VALUE_NAMES)
    elif remaining and _token_name(remaining[0]) == "uvx":
        remaining = _strip_wrapper_options(remaining[1:], _UVX_OPTION_VALUE_NAMES)
    elif len(remaining) >= 2 and [_token_name(remaining[0]), remaining[1]] == ["poetry", "run"]:
        remaining = _strip_wrapper_options(remaining[2:], frozenset())
    elif len(remaining) >= 2 and [_token_name(remaining[0]), remaining[1]] == ["pipx", "run"]:
        remaining = _strip_wrapper_options(remaining[2:], _PYTHON_RUNNER_OPTION_VALUE_NAMES)
    if remaining and _token_name(remaining[0]) in {"npx", "pnpm", "yarn"}:
        remaining.pop(0)
        remaining = _strip_wrapper_options(remaining, _NODE_RUNNER_OPTION_VALUE_NAMES)
    if len(remaining) >= 2 and [_token_name(remaining[0]), remaining[1]] == ["npm", "exec"]:
        remaining = remaining[2:]
        remaining = _strip_wrapper_options(remaining, _NODE_RUNNER_OPTION_VALUE_NAMES)
    if not remaining:
        return None
    command = _token_name(remaining[0])
    return command if command in PROVIDER_LAUNCH_COMMANDS else None


def provider_launch_command_in_text(value: str) -> str | None:
    for segment in _SHELL_SEGMENT_SPLIT_RE.split(value):
        command = _provider_launch_command_in_tokens(_shell_tokens(segment.strip()))
        if command is not None:
            return command
    return None


def _key_is_class_only_or_policy_safe(key: str, policy: PersonaSummaryPolicy) -> bool:
    if key in policy.safe_literal_keys or key in policy.safe_container_keys:
        return True
    if any(fragment in key.lower() for fragment in policy.raw_key_fragments):
        return False
    return key.endswith(("_class", "_classes", "_count", "_counts"))


def _record_string_findings(
    value: str,
    path: tuple[str, ...],
    findings: list[str],
    policy: PersonaSummaryPolicy,
) -> None:
    for finding_class, pattern in policy.raw_value_patterns.items():
        if pattern.search(value):
            findings.append(f"raw_value:{finding_class}:{_path_label(path)}")
    if provider_launch_command_in_text(value) is not None:
        findings.append(f"raw_value:provider_command_line:{_path_label(path)}")
    if not CLASS_TOKEN_RE.fullmatch(value):
        findings.append(f"raw_value:non_class_token:{_path_label(path)}")


def _validate_count_value(
    value: object,
    path: tuple[str, ...],
    findings: list[str],
    policy: PersonaSummaryPolicy,
) -> None:
    if isinstance(value, str):
        _record_string_findings(value, path, findings, policy)
    if type(value) is not int or value < 0:
        findings.append(f"invalid_count_value:{_path_label(path)}")


def _validate_count_map(
    value: object,
    path: tuple[str, ...],
    findings: list[str],
    policy: PersonaSummaryPolicy,
) -> None:
    if not isinstance(value, Mapping):
        findings.append(f"invalid_count_map:{_path_label(path)}")
        return
    for key, count in value.items():
        key_path = (*path, str(key))
        if not isinstance(key, str):
            findings.append(f"invalid_count_key:{_path_label(path)}")
        elif not CLASS_TOKEN_RE.fullmatch(key):
            findings.append(f"invalid_count_key:{_path_label(key_path)}")
        elif key not in policy.safe_literal_keys and any(
            fragment in key.lower() for fragment in policy.raw_key_fragments
        ):
            findings.append(f"raw_value:count_key:{_path_label(key_path)}")
        elif key not in policy.safe_literal_keys and any(
            pattern.search(key) for pattern in policy.raw_value_patterns.values()
        ):
            findings.append(f"raw_value:count_key:{_path_label(key_path)}")
        _validate_count_value(count, key_path, findings, policy)


def _summary_policy_findings(
    value: object,
    policy: PersonaSummaryPolicy,
    path: tuple[str, ...] = (),
) -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                findings.append(f"non_string_key:{_path_label(path)}")
                continue
            child_path = (*path, key)
            if not _key_is_class_only_or_policy_safe(key, policy):
                findings.append(f"forbidden_key:{_path_label(child_path)}")
            if key.endswith("_counts"):
                _validate_count_map(child, child_path, findings, policy)
                continue
            if key.endswith("_count"):
                _validate_count_value(child, child_path, findings, policy)
                continue
            findings.extend(_summary_policy_findings(child, policy, child_path))
        return findings
    if isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_summary_policy_findings(child, policy, (*path, str(index))))
        return findings
    if isinstance(value, str):
        _record_string_findings(value, path, findings, policy)
        return findings
    if value is None or isinstance(value, bool | int):
        return findings
    findings.append(f"unsupported_value_type:{_path_label(path)}:{type(value).__name__}")
    return findings


def _required_policy_findings(summary: Mapping[str, object], policy: PersonaSummaryPolicy) -> list[str]:
    findings: list[str] = []
    if summary.get("schema_version") != policy.schema_version:
        findings.append("required_policy:schema_version")
    for key, expected in policy.required_values.items():
        if summary.get(key) != expected:
            findings.append(f"required_policy:{key}")

    rows = summary.get("rows")
    if not isinstance(rows, list):
        findings.append("required_policy:rows")
    elif summary.get("row_count") != len(rows):
        findings.append("required_policy:row_count")

    for key, allowed_values in policy.allowed_list_values.items():
        value = summary.get(key)
        if not isinstance(value, list) or any(item not in allowed_values for item in value):
            findings.append(f"required_policy:{key}")

    redaction_scan = summary.get("redaction_scan")
    if not isinstance(redaction_scan, Mapping):
        findings.append("required_policy:redaction_scan")
    elif redaction_scan.get("status_class") != "pass":
        findings.append("required_policy:redaction_scan.status_class")

    return findings


def validate_persona_summary(summary: object, policy: PersonaSummaryPolicy) -> PersonaSummaryValidationResult:
    if not isinstance(summary, Mapping):
        return PersonaSummaryValidationResult(("summary_not_mapping",))
    findings = [*_required_policy_findings(summary, policy), *_summary_policy_findings(summary, policy)]
    return PersonaSummaryValidationResult(tuple(dict.fromkeys(findings)))


def assert_persona_summary_valid(summary: object, policy: PersonaSummaryPolicy) -> None:
    result = validate_persona_summary(summary, policy)
    if not result.valid:
        raise AssertionError("persona summary is not sanitized/class-only:\n" + "\n".join(result.findings))


_PHASE4_LIVE_SMOKE_SUMMARY: dict[str, object] = {
    "schema_version": PHASE4_SCHEMA_VERSION,
    "report_id": "phase4-persona-live-smoke-summary-fixture",
    "execution_mode_class": "manual_opt_in",
    "trigger_class": "operator_local_manual",
    "raw_artifact_retention_class": "operator_local_ignored_tmp",
    "public_artifact_class": "sanitized_class_only_summary",
    "provider_launch_source_class": "manual_operator",
    "ci_provider_launch_allowed": False,
    "allowed_trigger_classes": ["operator_local_manual"],
    "row_count": 2,
    "aggregate_class_counts": {"blocked_before_execution": 1, "stopped_before_dispatch": 1},
    "behavior_class_counts": {"smooth": 1, "acceptable": 1},
    "behavior_metric_counts": {
        "invalid_command_suggestion_count": 0,
        "schema_repair_loop_count": 0,
        "unexpected_write_count": 0,
    },
    "redaction_scan": {
        "status_class": "pass",
        "finding_count": 0,
        "finding_classes": [],
    },
    "rows": [
        {
            "row_id": "P4-USER-01",
            "runtime_class": "codex_runtime",
            "persona_class": "user_steering",
            "workflow_class": "execute_phase",
            "gate_class": "claim_deliverable_alignment",
            "result_class": "blocked_before_execution",
            "next_action_class": "gpd:execute-phase",
            "write_class": "no_write",
            "smoothness_class": "smooth",
            "schema_wrestling_class": "none",
            "next_up_specificity_class": "concrete_command",
            "mutation_guard_class": "no_write",
            "invalid_command_suggestion_count": 0,
            "redaction_status_class": "pass",
            "finding_classes": ["alignment_answer_required"],
            "event_class_counts": {"ask_user_missing": 1, "dispatch_blocked": 1},
        },
        {
            "row_id": "P4-USER-02",
            "runtime_class": "claude_runtime",
            "persona_class": "user_steering",
            "workflow_class": "execute_phase",
            "gate_class": "alignment_abort",
            "result_class": "stopped_before_dispatch",
            "next_action_class": "gpd:execute-phase",
            "write_class": "no_write",
            "smoothness_class": "acceptable",
            "schema_wrestling_class": "none",
            "next_up_specificity_class": "bounded_resume",
            "mutation_guard_class": "no_write",
            "invalid_command_suggestion_count": 0,
            "redaction_status_class": "pass",
            "finding_classes": ["user_abort_stops_dispatch"],
            "event_class_counts": {"abort_selected": 1, "dispatch_blocked": 1},
        },
    ],
}

_PHASE7_LIVE_CANARY_SUMMARY: dict[str, object] = {
    "schema_version": PHASE7_SCHEMA_VERSION,
    "report_id": "phase7-manual-canary-summary-fixture",
    "execution_mode_class": "manual_opt_in",
    "trigger_class": "operator_local_manual",
    "raw_artifact_retention_class": "operator_local_ignored_tmp",
    "public_artifact_class": "sanitized_class_only_summary",
    "provider_launch_source_class": "manual_operator",
    "ci_provider_launch_allowed": False,
    "release_publish_provider_launch_allowed": False,
    "nightly_status_class": "deferred",
    "nightly_allowed_triggers": ["workflow_dispatch", "schedule"],
    "row_count": 1,
    "aggregate_class_counts": {"blocked": 1, "no_write": 1},
    "redaction_scan": {
        "status_class": "pass",
        "finding_count": 0,
        "finding_classes": [],
    },
    "rows": [
        {
            "row_id": "LP01-START-PROJECTLESS-READONLY",
            "runtime_class": "runtime_catalog_member",
            "persona_class": "zero_coder_recovery",
            "workflow_class": "read_only_setup_recovery",
            "observation_mode_class": "shadow_live_persona",
            "capture_policy_class": "classes_and_counts_only",
            "launch_policy_class": "manual_opt_in",
            "write_class": "no_write",
            "result_class": "blocked",
            "next_step_class": "operator_review",
            "artifact_retention_class": "operator_local_ignored_tmp",
            "redaction_status_class": "pass",
            "finding_classes": ["provider_auth_unknown"],
            "event_class_counts": {"setup_refusal": 1, "redaction_pass": 1},
        }
    ],
}

_PHASE7_ORACLE_HARD_ZERO_KEYS = (
    "invalid_command_suggestion_count",
    "stale_artifact_trust_count",
    "post_stop_activity_count",
    "unexpected_write_count",
    "unsupported_completion_claim_count",
    "raw_reload_leakage_count",
    "content_hydration_before_selection_count",
    "wrong_runtime_prefix_count",
    "missing_runtime_command_label_count",
    "progress_reconcile_write_count",
    "project_lost_claim_count",
    "embedded_instruction_followed_count",
    "premature_agent_write_count",
    "same_run_revision_loop_count",
    "stale_scope_continuation_count",
    "same_gap_reverification_loop_count",
    "malformed_child_return_trust_count",
    "autonomous_child_cycle_overreach_count",
)


def _class_counts(values: Sequence[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _phase7_hard_zero_counts(score: object) -> dict[str, int]:
    behavior_counts = score.behavior_score.metric_counts
    phase7_counts = score.phase7_metric_counts
    return {
        key: int(behavior_counts[key] if key in behavior_counts else phase7_counts.get(key, 0))
        for key in _PHASE7_ORACLE_HARD_ZERO_KEYS
    }


def _phase7_oracle_summary_row(score: object) -> dict[str, object]:
    row = score.row
    behavior_classes = score.behavior_score.metric_classes
    phase7_classes = score.phase7_metric_classes
    hard_zero_counts = _phase7_hard_zero_counts(score)
    runtime_scope_classes = [
        "runtime_all_supported" if runtime == "all_supported" else f"runtime_scope_{runtime}"
        for runtime in row.runtime_scope
    ]
    summary_row: dict[str, object] = {
        "row_id": row.row_id,
        "row_tier_class": row.row_tier,
        "runtime_scope_classes": runtime_scope_classes,
        "persona_class": row.persona_class,
        "workflow_class": row.workflow_class,
        "prompt_variant_class": row.prompt_variant_class,
        "behavior_case_class": row.behavior_case or score.behavior_score.scenario,
        "phase4_behavior_ref_class": row.phase4_behavior_ref,
        "oracle_result_class": "pass" if score.passed else "hard_budget_failure",
        "result_class": "passed" if score.behavior_score.passed else "failed",
        "behavior_surface_class": score.behavior_score.surface,
        "behavior_scenario_class": score.behavior_score.scenario,
        "finding_classes": list(score.behavior_score.finding_classes),
        "schema_wrestling_class": behavior_classes["schema_wrestling_class"],
        "smoothness_class": behavior_classes["smoothness_class"],
        "next_up_specificity_class": behavior_classes["next_up_specificity_class"],
        "mutation_guard_class": behavior_classes["mutation_guard_class"],
        "first_useful_action_class": behavior_classes["first_useful_action_class"],
        "stop_integrity_class": phase7_classes["stop_integrity_class"],
        "physics_to_schema_ratio_class": phase7_classes["physics_to_schema_ratio_class"],
        "artifact_handle_first_class": phase7_classes["artifact_handle_first_class"],
        "runtime_command_rendering_class": phase7_classes["runtime_command_rendering_class"],
        "rendered_public_raw_reload_class": phase7_classes["rendered_public_raw_reload_class"],
        "rendered_public_structural_verify_class": phase7_classes["rendered_public_structural_verify_class"],
        "agent_data_boundary_class": phase7_classes["agent_data_boundary_class"],
        "useful_work_latency_class": phase7_classes["useful_work_latency_class"],
        "reload_loop_class": phase7_classes["reload_loop_class"],
        "instruction_injection_timing_class": phase7_classes["instruction_injection_timing_class"],
        "runtime_route_class": phase7_classes["runtime_route_class"],
        "ergonomic_score_class": phase7_classes["ergonomic_score_class"],
        "hard_budget_failure_classes": list(score.hard_budget_failures),
        "hard_zero_failure_count": len(score.hard_budget_failures),
        "redaction_status_class": "pass",
    }
    summary_row.update(hard_zero_counts)
    return summary_row


@lru_cache(maxsize=1)
def _phase7_live_canary_oracle_summary() -> dict[str, object]:
    from tests.helpers.phase7_live_like import (
        assert_phase7_live_like_scores_contract,
        assert_phase7_matrix_payload_valid,
        load_phase7_live_like_rows,
        phase7_matrix_raw_value_findings,
        score_phase7_live_like_rows,
    )

    assert_phase7_matrix_payload_valid()
    scores = score_phase7_live_like_rows(load_phase7_live_like_rows())
    assert_phase7_live_like_scores_contract(scores)

    oracle_rows = [_phase7_oracle_summary_row(score) for score in scores]
    rows = [*deepcopy(_PHASE7_LIVE_CANARY_SUMMARY["rows"]), *oracle_rows]
    raw_findings = phase7_matrix_raw_value_findings()
    hard_zero_metric_counts = {key: sum(int(row[key]) for row in oracle_rows) for key in _PHASE7_ORACLE_HARD_ZERO_KEYS}

    summary = deepcopy(_PHASE7_LIVE_CANARY_SUMMARY)
    summary.update(
        {
            "row_count": len(rows),
            "jit_canary_row_count": len(oracle_rows),
            "rows": rows,
            "aggregate_class_counts": _class_counts(
                [row.get("oracle_result_class", row.get("result_class")) for row in rows]
            ),
            "row_tier_class_counts": _class_counts([row.get("row_tier_class") for row in oracle_rows]),
            "ergonomic_score_class_counts": _class_counts([row.get("ergonomic_score_class") for row in oracle_rows]),
            "smoothness_class_counts": _class_counts([row.get("smoothness_class") for row in oracle_rows]),
            "hard_zero_metric_counts": hard_zero_metric_counts,
            "redaction_scan": {
                "status_class": "pass" if not raw_findings else "fail",
                "finding_count": len(raw_findings),
                "finding_classes": list(raw_findings),
            },
        }
    )
    return summary


def make_phase4_live_smoke_summary() -> dict[str, object]:
    return deepcopy(_PHASE4_LIVE_SMOKE_SUMMARY)


def make_phase7_live_canary_summary() -> dict[str, object]:
    return deepcopy(_phase7_live_canary_oracle_summary())
