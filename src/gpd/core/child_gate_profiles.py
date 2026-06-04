"""Named source-format profiles for strict child gate tuple expansion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from gpd.core.return_contract import normalize_return_status
from gpd.core.return_skeleton import normalize_return_profile_id

if TYPE_CHECKING:  # pragma: no cover - imported only for static typing.
    from gpd.core.child_handoff import ChildGateTuple


def _normalize_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _profile_key(value: object) -> str:
    return _normalize_text(value, field_name="profile").casefold().replace("-", "_")


_TOKEN_ARTIFACT = "$ARTIFACT"
_TOKEN_ALLOWED_ROOT = "$ALLOWED_ROOT"
_TOKEN_FRESHNESS_MARKER = "$FRESHNESS_MARKER"
_TOKEN_APPLICATOR_TARGET = "$APPLICATOR_TARGET"

_PROFILE_PAYLOAD_KEYS = frozenset(
    (
        "id",
        "profile",
        "artifact",
        "artifact_path",
        "expected_artifacts",
        "allowed_root",
        "allowed_roots",
        "freshness_marker",
        "freshness",
        "role",
        "return_profile",
        "required_status",
        "validators",
        "applicator",
        "applicator_target",
        "failure_route",
        "status_route",
        "write_allowlist",
        "allowed_write_paths",
        "overrides",
    )
)
_OVERRIDE_KEYS = frozenset(
    (
        "applicator_target",
        "write_allowlist",
        "allowed_write_paths",
    )
)


@dataclass(frozen=True)
class ChildGateProfile:
    """A compact prompt-local child gate source format."""

    profile_id: str
    aliases: tuple[str, ...]
    role: str
    return_profile: str
    required_status: str
    validators: tuple[str, ...]
    applicator_command: str = "none"
    applicator_require_passed_true: bool = False
    failure_route: tuple[tuple[str, str], ...] | str = ()
    status_route: tuple[tuple[str, str], ...] = ()
    write_allowlist: tuple[str, ...] = ()
    artifact_kind: Literal["path", "glob"] = "path"
    artifact_required: bool = True
    artifact_must_be_named_in_files_written: bool = True
    freshness_preexisting_artifacts: str = "recovery_evidence_only"

    def __post_init__(self) -> None:
        _normalize_text(self.profile_id, field_name="profile_id")
        _normalize_text(self.role, field_name="role")
        normalized_profile = normalize_return_profile_id(self.return_profile)
        if normalized_profile != self.return_profile:
            raise ValueError(f"child_gate profile {self.profile_id!r} uses non-canonical return_profile")
        normalized_status = normalize_return_status(self.required_status, field_name="required_status")
        if normalized_status != self.required_status:
            raise ValueError(f"child_gate profile {self.profile_id!r} uses non-canonical required_status")
        for alias in self.aliases:
            _normalize_text(alias, field_name=f"{self.profile_id}.aliases")
        for validator in self.validators:
            _normalize_text(validator, field_name=f"{self.profile_id}.validators")
        _normalize_text(self.applicator_command, field_name=f"{self.profile_id}.applicator_command")
        if self.applicator_command == "none" and self.applicator_require_passed_true:
            raise ValueError("applicator require_passed_true requires a command")

    def registry_payload(self) -> dict[str, object]:
        """Return immutable registry data as plain copies."""

        payload: dict[str, object] = {
            "profile_id": self.profile_id,
            "aliases": list(self.aliases),
            "role": self.role,
            "return_profile": self.return_profile,
            "required_status": self.required_status,
            "artifact": {
                "kind": self.artifact_kind,
                "required": self.artifact_required,
                "must_be_named_in_files_written": self.artifact_must_be_named_in_files_written,
            },
            "freshness": {
                "require_mtime_at_or_after_marker": True,
                "preexisting_artifacts": self.freshness_preexisting_artifacts,
            },
            "validators": list(self.validators),
            "applicator": {
                "command": self.applicator_command,
                "require_passed_true": self.applicator_require_passed_true,
            },
            "write_allowlist": list(self.write_allowlist),
        }
        payload["failure_route"] = (
            dict(self.failure_route) if isinstance(self.failure_route, tuple) else self.failure_route
        )
        if self.status_route:
            payload["status_route"] = dict(self.status_route)
        return payload


_WAVE_STATUS_ROUTE: tuple[tuple[str, str], ...] = (
    ("checkpoint", "checkpoint_resume"),
    ("blocked", "wave_failure_menu"),
    ("failed", "wave_failure_menu"),
)

_EXECUTOR_FAILURE_ROUTE: tuple[tuple[str, str], ...] = (
    ("return_missing", "repair_prompt_once"),
    ("return_malformed_repairable", "repair_prompt_once"),
    ("return_malformed_blocking", "wave_failure_menu"),
    ("return_status_route", "status_route"),
    ("artifact_missing", "retry_once_or_main_context_fallback"),
    ("artifact_stale", "retry_once"),
    ("artifact_path_repairable", "repair_path_once"),
    ("artifact_root_blocked", "wave_failure_menu"),
    ("validator_failed", "wave_failure_menu"),
    ("applicator_failed", "fail_closed_with_mutation_report"),
)

_PROOF_CRITIC_FAILURE_ROUTE: tuple[tuple[str, str], ...] = (
    ("return_missing", "repair_prompt_once"),
    ("return_malformed_repairable", "repair_prompt_once"),
    ("return_malformed_blocking", "wave_failure_menu"),
    ("return_status_route", "status_route"),
    ("artifact_missing", "retry_once_then_wave_failure_menu"),
    ("artifact_stale", "retry_once_then_wave_failure_menu"),
    ("artifact_path_repairable", "repair_path_once"),
    ("artifact_root_blocked", "wave_failure_menu"),
    ("validator_failed", "wave_failure_menu"),
    ("applicator_failed", "wave_failure_menu"),
)

CHILD_GATE_PROFILES: dict[str, ChildGateProfile] = {
    "execute.executor_summary.v1": ChildGateProfile(
        profile_id="execute.executor_summary.v1",
        aliases=(
            "execute_phase_executor_summary_v1",
            "execute_phase.executor_summary.v1",
            "execute_phase.executor_summary_completed",
        ),
        role="gpd-executor",
        return_profile="executor",
        required_status="completed",
        validators=(
            "gpd validate handoff-artifacts - --expected '$ARTIFACT' --allowed-root '$ALLOWED_ROOT' --required-suffix=-SUMMARY.md --require-status completed --require-files-written --fresh-after \"$FRESHNESS_MARKER\"",
            "SUMMARY key-files.created / key-files.modified required/final deliverables exist",
            "no Self-Check: FAILED or Validation: FAILED marker",
            "proof-redteam artifact exists and reports status: passed when proof-bearing",
        ),
        applicator_command="gpd --raw apply-return-updates $APPLICATOR_TARGET",
        applicator_require_passed_true=True,
        failure_route=_EXECUTOR_FAILURE_ROUTE,
        status_route=_WAVE_STATUS_ROUTE,
        write_allowlist=(
            "$ARTIFACT",
            "$ALLOWED_ROOT/**",
        ),
    ),
    "execute.proof_critic_report.v1": ChildGateProfile(
        profile_id="execute.proof_critic_report.v1",
        aliases=(
            "execute_phase_proof_critic_report_v1",
            "execute_phase.proof_critic_report.v1",
            "execute_phase.proof_redteam_completed",
            "execute.proof_redteam.v1",
        ),
        role="gpd-check-proof",
        return_profile="verifier",
        required_status="completed",
        validators=(
            "gpd validate handoff-artifacts - --expected '$ARTIFACT' --allowed-root '$ALLOWED_ROOT' --require-status completed --require-files-written --fresh-after \"$FRESHNESS_MARKER\"",
            "gpd validate proof-redteam $ARTIFACT",
            "frontmatter status: passed before executor wave success",
        ),
        failure_route=_PROOF_CRITIC_FAILURE_ROUTE,
        status_route=_WAVE_STATUS_ROUTE,
        write_allowlist=("$ARTIFACT",),
    ),
    "execute.verification_report.v1": ChildGateProfile(
        profile_id="execute.verification_report.v1",
        aliases=(
            "execute_phase_verification_report_v1",
            "execute_phase.verification_report.v1",
            "execute_phase.verification_report_completed",
        ),
        role="gpd-verifier",
        return_profile="verifier",
        required_status="completed",
        validators=(
            "gpd validate handoff-artifacts - --expected '$ARTIFACT' --allowed-root '$ALLOWED_ROOT' --required-suffix=-VERIFICATION.md --require-status completed --require-files-written --fresh-after \"$FRESHNESS_MARKER\"",
            "gpd validate verification-contract $ARTIFACT",
            "verification-status-authority.md status rules",
            "proof-redteam status: passed for proof-bearing work",
        ),
        applicator_command="none; closeout/update_roadmap is allowed only after verifier and consistency gates pass",
        failure_route=(
            "fail_closed -> gpd:verify-work {PHASE_NUMBER} | repair_prompt_once | retry_once_then_gpd_verify_work"
        ),
    ),
    "execute.gap_reverification_report.v1": ChildGateProfile(
        profile_id="execute.gap_reverification_report.v1",
        aliases=(
            "execute_phase_gap_reverification_report_v1",
            "execute_phase.gap_reverification_report.v1",
            "execute_phase.gap_reverification_report_completed",
        ),
        role="gpd-verifier",
        return_profile="verifier",
        required_status="completed",
        validators=(
            "gpd validate handoff-artifacts - --expected '$ARTIFACT' --allowed-root '$ALLOWED_ROOT' --required-suffix=-VERIFICATION.md --require-status completed --require-files-written --fresh-after \"$FRESHNESS_MARKER\"",
            "gpd validate verification-contract $ARTIFACT",
            "verification-status-authority.md status rules",
            "proof-redteam status: passed for proof-bearing work",
        ),
        applicator_command=(
            "none; closeout/update_roadmap is allowed only after re-verifier and consistency gates pass"
        ),
        failure_route=(
            "fail_closed -> gpd:verify-work {PHASE_NUMBER} | repair_prompt_once | retry_once_then_verify_work"
        ),
    ),
    "execute.consistency_report.v1": ChildGateProfile(
        profile_id="execute.consistency_report.v1",
        aliases=(
            "execute_phase_consistency_report_v1",
            "execute_phase.consistency_report.v1",
            "execute_phase.single_report_artifact_completed",
        ),
        role="gpd-consistency-checker",
        return_profile="checker",
        required_status="completed",
        validators=(
            'gpd validate handoff-artifacts - --expected $ARTIFACT --allowed-root $ALLOWED_ROOT --required-suffix=CONSISTENCY-CHECK.md --require-status completed --require-files-written --fresh-after "$FRESHNESS_MARKER"',
            "readable artifact check",
        ),
        failure_route="fail_closed -> gpd:validate-conventions | repair_prompt_once | retry_once",
    ),
}

_PROFILE_ALIASES: dict[str, str] = {_profile_key(profile_id): profile_id for profile_id in CHILD_GATE_PROFILES}
for _profile in CHILD_GATE_PROFILES.values():
    for _alias in _profile.aliases:
        _PROFILE_ALIASES[_profile_key(_alias)] = _profile.profile_id


def normalize_child_gate_profile_id(value: object) -> str:
    """Normalize a child gate profile id or alias to its canonical id."""

    raw = _normalize_text(value, field_name="profile")
    profile_id = _PROFILE_ALIASES.get(_profile_key(raw))
    if profile_id is None:
        known = ", ".join(sorted(CHILD_GATE_PROFILES))
        raise ValueError(f"unknown child_gate profile {raw!r}. Must be one of: {known}")
    return profile_id


def list_child_gate_profiles() -> dict[str, object]:
    """Return registry metadata as detached plain data."""

    return {
        "profiles": {
            profile_id: profile.registry_payload() for profile_id, profile in sorted(CHILD_GATE_PROFILES.items())
        },
        "aliases": {
            alias: profile_id
            for alias, profile_id in sorted(_PROFILE_ALIASES.items())
            if alias != _profile_key(profile_id)
        },
    }


def expand_child_gate_profile_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Expand a compact child gate profile payload to a full child gate tuple payload."""

    candidate = _unwrap_child_gate_payload(payload)
    if "profile" not in candidate:
        raise ValueError("child_gate profile payload requires a profile field")

    candidate = _merge_overrides(candidate)
    unknown = sorted(set(candidate) - _PROFILE_PAYLOAD_KEYS)
    if unknown:
        raise ValueError(f"unknown child_gate profile field(s): {', '.join(unknown)}")

    profile = CHILD_GATE_PROFILES[normalize_child_gate_profile_id(candidate["profile"])]
    gate_id = _normalize_text(candidate.get("id"), field_name="id")
    artifact_path = _profile_artifact_path(candidate, profile)
    allowed_root = _profile_allowed_root(candidate)
    freshness_marker = _profile_freshness_marker(candidate, profile)
    applicator_target = _profile_applicator_target(candidate, artifact_path, profile)

    expanded: dict[str, object] = {
        "id": gate_id,
        "role": profile.role,
        "return_profile": profile.return_profile,
        "required_status": profile.required_status,
        "expected_artifacts": [
            {
                "path": artifact_path,
                "kind": profile.artifact_kind,
                "required": profile.artifact_required,
                "must_be_named_in_files_written": profile.artifact_must_be_named_in_files_written,
            }
        ],
        "allowed_roots": [allowed_root],
        "freshness": {
            "marker": freshness_marker,
            "require_mtime_at_or_after_marker": True,
            "preexisting_artifacts": profile.freshness_preexisting_artifacts,
        },
        "validators": [
            _render_template(
                validator,
                artifact_path=artifact_path,
                allowed_root=allowed_root,
                freshness_marker=freshness_marker,
                applicator_target=applicator_target,
            )
            for validator in profile.validators
        ],
        "applicator": {
            "command": _render_template(
                profile.applicator_command,
                artifact_path=artifact_path,
                allowed_root=allowed_root,
                freshness_marker=freshness_marker,
                applicator_target=applicator_target,
            ),
            "require_passed_true": profile.applicator_require_passed_true,
        },
    }
    if profile.write_allowlist:
        expanded["write_allowlist"] = [
            _render_template(
                pattern,
                artifact_path=artifact_path,
                allowed_root=allowed_root,
                freshness_marker=freshness_marker,
                applicator_target=applicator_target,
            )
            for pattern in profile.write_allowlist
        ]
    expanded["failure_route"] = (
        dict(profile.failure_route) if isinstance(profile.failure_route, tuple) else profile.failure_route
    )
    if profile.status_route:
        expanded["status_route"] = dict(profile.status_route)

    _validate_profile_owned_passthrough(candidate, expanded, profile)
    return expanded


def expand_child_gate_profile(payload: Mapping[str, object]) -> ChildGateTuple:
    """Expand and validate a profile payload as a normal ``ChildGateTuple``."""

    from gpd.core.child_handoff import ChildGateTuple

    return ChildGateTuple.model_validate(expand_child_gate_profile_payload(payload))


def _unwrap_child_gate_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    if "child_gate" not in payload:
        return payload
    candidate = payload["child_gate"]
    if not isinstance(candidate, Mapping):
        raise ValueError("child_gate payload must be a mapping")
    return candidate


def _merge_overrides(payload: Mapping[str, object]) -> dict[str, object]:
    merged = dict(payload)
    raw_overrides = merged.pop("overrides", None)
    if raw_overrides is None:
        return merged
    if not isinstance(raw_overrides, Mapping):
        raise ValueError("child_gate profile overrides must be a mapping")
    unknown = sorted(set(raw_overrides) - _OVERRIDE_KEYS)
    if unknown:
        raise ValueError(f"unknown child_gate profile override field(s): {', '.join(unknown)}")
    for key, value in raw_overrides.items():
        if key in merged:
            raise ValueError(f"child_gate profile override {key!r} duplicates a top-level field")
        merged[key] = value
    return merged


def _profile_artifact_path(payload: Mapping[str, object], profile: ChildGateProfile) -> str:
    artifact_sources = [key for key in ("artifact", "artifact_path", "expected_artifacts") if key in payload]
    if not artifact_sources:
        raise ValueError("child_gate profile payload requires artifact or expected_artifacts")
    if len(artifact_sources) > 1:
        raise ValueError("child_gate profile payload must specify only one artifact source")

    source = artifact_sources[0]
    raw_artifact = payload[source]
    if source == "artifact_path":
        return _normalize_text(raw_artifact, field_name="artifact_path")
    if source == "expected_artifacts":
        artifacts = _normalize_sequence(raw_artifact, field_name="expected_artifacts")
        if len(artifacts) != 1:
            raise ValueError("child_gate profile expected_artifacts must contain exactly one artifact")
        raw_artifact = artifacts[0]
    return _artifact_path(raw_artifact, profile, field_name=source)


def _artifact_path(raw_artifact: object, profile: ChildGateProfile, *, field_name: str) -> str:
    if isinstance(raw_artifact, str):
        return _normalize_text(raw_artifact, field_name=field_name)
    if not isinstance(raw_artifact, Mapping):
        raise ValueError(f"{field_name} must be a string or mapping")
    path = _normalize_text(raw_artifact.get("path"), field_name=f"{field_name}.path")
    _require_optional_literal(raw_artifact, "kind", profile.artifact_kind, field_name=field_name)
    _require_optional_literal(raw_artifact, "required", profile.artifact_required, field_name=field_name)
    _require_optional_literal(
        raw_artifact,
        "must_be_named_in_files_written",
        profile.artifact_must_be_named_in_files_written,
        field_name=field_name,
    )
    unknown = sorted(
        set(raw_artifact)
        - {
            "path",
            "kind",
            "required",
            "must_be_named_in_files_written",
        }
    )
    if unknown:
        raise ValueError(f"unknown {field_name} field(s): {', '.join(unknown)}")
    return path


def _profile_allowed_root(payload: Mapping[str, object]) -> str:
    if "allowed_root" in payload and "allowed_roots" in payload:
        raise ValueError("child_gate profile payload must specify only one allowed root source")
    if "allowed_root" in payload:
        return _normalize_text(payload["allowed_root"], field_name="allowed_root")
    if "allowed_roots" not in payload:
        raise ValueError("child_gate profile payload requires allowed_root or allowed_roots")
    roots = _normalize_text_sequence(payload["allowed_roots"], field_name="allowed_roots")
    if len(roots) != 1:
        raise ValueError("child_gate profile allowed_roots must contain exactly one root")
    return roots[0]


def _profile_freshness_marker(payload: Mapping[str, object], profile: ChildGateProfile) -> str:
    if "freshness_marker" in payload and "freshness" in payload:
        raise ValueError("child_gate profile payload must specify only one freshness source")
    if "freshness_marker" in payload:
        return _normalize_freshness_marker(payload["freshness_marker"])
    if "freshness" not in payload:
        raise ValueError("child_gate profile payload requires freshness_marker or freshness")
    raw_freshness = payload["freshness"]
    if not isinstance(raw_freshness, Mapping):
        raise ValueError("freshness must be a mapping")
    marker = _normalize_text(raw_freshness.get("marker"), field_name="freshness.marker")
    _require_optional_literal(
        raw_freshness,
        "require_mtime_at_or_after_marker",
        True,
        field_name="freshness",
    )
    _require_optional_literal(
        raw_freshness,
        "preexisting_artifacts",
        profile.freshness_preexisting_artifacts,
        field_name="freshness",
    )
    unknown = sorted(
        set(raw_freshness)
        - {
            "marker",
            "require_mtime_at_or_after_marker",
            "preexisting_artifacts",
        }
    )
    if unknown:
        raise ValueError(f"unknown freshness field(s): {', '.join(unknown)}")
    return marker


def _profile_applicator_target(
    payload: Mapping[str, object],
    artifact_path: str,
    profile: ChildGateProfile,
) -> str:
    if "applicator_target" not in payload:
        return artifact_path
    if _TOKEN_APPLICATOR_TARGET not in profile.applicator_command:
        raise ValueError(f"profile {profile.profile_id!r} does not accept applicator_target")
    return _normalize_text(payload["applicator_target"], field_name="applicator_target")


def _validate_profile_owned_passthrough(
    payload: Mapping[str, object],
    expanded: Mapping[str, object],
    profile: ChildGateProfile,
) -> None:
    _require_optional_text(payload, "role", profile.role)
    if "return_profile" in payload:
        normalized = normalize_return_profile_id(payload["return_profile"])
        if normalized != profile.return_profile:
            raise ValueError(f"profile {profile.profile_id!r} requires return_profile {profile.return_profile!r}")
    if "required_status" in payload:
        normalized = normalize_return_status(payload["required_status"], field_name="required_status")
        if normalized != profile.required_status:
            raise ValueError(f"profile {profile.profile_id!r} requires required_status {profile.required_status!r}")
    _require_optional_text_sequence(payload, "validators", expanded["validators"])
    if "applicator" in payload:
        _require_applicator(payload["applicator"], expanded["applicator"], profile)
    if "failure_route" in payload:
        if payload["failure_route"] != expanded["failure_route"]:
            raise ValueError(f"profile {profile.profile_id!r} owns failure_route")
    if "status_route" in payload:
        if payload["status_route"] != expanded.get("status_route", {}):
            raise ValueError(f"profile {profile.profile_id!r} owns status_route")
    if "write_allowlist" in payload and "allowed_write_paths" in payload:
        raise ValueError("child_gate profile payload must specify only one write allowlist source")
    if "write_allowlist" in payload:
        _require_optional_text_sequence(payload, "write_allowlist", expanded.get("write_allowlist", ()))
    if "allowed_write_paths" in payload:
        _require_optional_text_sequence(payload, "allowed_write_paths", expanded.get("write_allowlist", ()))


def _require_applicator(
    raw_applicator: object,
    expected_applicator: object,
    profile: ChildGateProfile,
) -> None:
    if not isinstance(expected_applicator, Mapping):  # pragma: no cover - internal invariant.
        raise ValueError("expected applicator must be a mapping")
    if isinstance(raw_applicator, str):
        normalized = {"command": _normalize_text(raw_applicator, field_name="applicator")}
    elif isinstance(raw_applicator, Mapping):
        normalized = dict(raw_applicator)
    else:
        raise ValueError("applicator must be a string or mapping")
    command = _normalize_text(normalized.get("command"), field_name="applicator.command")
    require_passed_true = normalized.get("require_passed_true", False)
    if not isinstance(require_passed_true, bool):
        raise ValueError("applicator.require_passed_true must be a boolean")
    if {
        "command": command,
        "require_passed_true": require_passed_true,
    } != dict(expected_applicator):
        raise ValueError(f"profile {profile.profile_id!r} owns applicator policy")


def _require_optional_literal(
    payload: Mapping[str, object],
    key: str,
    expected: object,
    *,
    field_name: str,
) -> None:
    if key in payload and payload[key] != expected:
        raise ValueError(f"{field_name}.{key} must be {expected!r}")


def _require_optional_text(payload: Mapping[str, object], key: str, expected: str) -> None:
    if key in payload and _normalize_text(payload[key], field_name=key) != expected:
        raise ValueError(f"profile-owned field {key} must be {expected!r}")


def _require_optional_text_sequence(
    payload: Mapping[str, object],
    key: str,
    expected: object,
) -> None:
    if key not in payload:
        return
    value = _normalize_text_sequence(payload[key], field_name=key)
    expected_value = tuple(_normalize_text_sequence(expected, field_name=key))
    if value != expected_value:
        raise ValueError(f"profile owns {key}")


def _render_template(
    value: str,
    *,
    artifact_path: str,
    allowed_root: str,
    freshness_marker: str,
    applicator_target: str,
) -> str:
    return (
        value.replace(_TOKEN_ARTIFACT, artifact_path)
        .replace(_TOKEN_ALLOWED_ROOT, allowed_root)
        .replace(_TOKEN_FRESHNESS_MARKER, freshness_marker)
        .replace(_TOKEN_APPLICATOR_TARGET, applicator_target)
    )


def _normalize_text_sequence(value: object, *, field_name: str) -> tuple[str, ...]:
    return tuple(
        _normalize_text(item, field_name=field_name) for item in _normalize_sequence(value, field_name=field_name)
    )


def _normalize_sequence(value: object, *, field_name: str) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a sequence")
    return tuple(value)


def _normalize_freshness_marker(value: object) -> str:
    marker = _normalize_text(value, field_name="freshness_marker")
    if marker.casefold().startswith("after "):
        return marker[6:].strip()
    return marker


__all__ = [
    "CHILD_GATE_PROFILES",
    "ChildGateProfile",
    "expand_child_gate_profile",
    "expand_child_gate_profile_payload",
    "list_child_gate_profiles",
    "normalize_child_gate_profile_id",
]
