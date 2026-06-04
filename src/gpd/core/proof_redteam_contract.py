"""Shared proof-redteam artifact contract for builders and review gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gpd.contracts import PROOF_AUDIT_REVIEWER
from gpd.core.frontmatter import FrontmatterParseError, extract_frontmatter
from gpd.core.publication_review_paths import resolve_review_manuscript_path

__all__ = [
    "PROOF_REDTEAM_COUNTEREXAMPLE_STATUS_VALUES",
    "PROOF_REDTEAM_OPEN_STATUS_VALUES",
    "PROOF_REDTEAM_QUANTIFIER_STATUS_VALUES",
    "PROOF_REDTEAM_REQUIRED_COVERAGE_SUBSECTIONS",
    "PROOF_REDTEAM_REQUIRED_SECTIONS",
    "PROOF_REDTEAM_SCOPE_STATUS_VALUES",
    "PROOF_REDTEAM_STATUS_VALUES",
    "ProofRedteamStructuredAudit",
    "read_proof_redteam_status",
]

PROOF_REDTEAM_STATUS_VALUES = ("passed", "gaps_found", "human_needed")
PROOF_REDTEAM_OPEN_STATUS_VALUES = ("gaps_found", "human_needed")
PROOF_REDTEAM_SCOPE_STATUS_VALUES = ("matched", "narrower_than_claim", "mismatched", "unclear")
PROOF_REDTEAM_QUANTIFIER_STATUS_VALUES = ("matched", "narrowed", "mismatched", "unclear")
PROOF_REDTEAM_COUNTEREXAMPLE_STATUS_VALUES = (
    "none_found",
    "counterexample_found",
    "not_attempted",
    "narrowed_claim",
)
PROOF_REDTEAM_REQUIRED_SECTIONS = (
    "# Proof Redteam",
    "## Proof Inventory",
    "## Coverage Ledger",
    "## Adversarial Probe",
    "## Verdict",
    "## Required Follow-Up",
)
PROOF_REDTEAM_REQUIRED_COVERAGE_SUBSECTIONS = (
    "### Named-Parameter Coverage",
    "### Hypothesis Coverage",
    "### Quantifier / Domain Coverage",
    "### Conclusion-Clause Coverage",
)

_PROOF_REDTEAM_STATUS_VALUE_SET = frozenset(PROOF_REDTEAM_STATUS_VALUES)
_PROOF_REDTEAM_SCOPE_STATUS_VALUE_SET = frozenset(PROOF_REDTEAM_SCOPE_STATUS_VALUES)
_PROOF_REDTEAM_QUANTIFIER_STATUS_VALUE_SET = frozenset(PROOF_REDTEAM_QUANTIFIER_STATUS_VALUES)
_PROOF_REDTEAM_COUNTEREXAMPLE_STATUS_VALUE_SET = frozenset(PROOF_REDTEAM_COUNTEREXAMPLE_STATUS_VALUES)


@dataclass(frozen=True, slots=True)
class ProofRedteamStructuredAudit:
    """Structured proof-redteam frontmatter values that can certify or block passed status."""

    missing_parameter_symbols: tuple[str, ...]
    missing_hypothesis_ids: tuple[str, ...]
    coverage_gaps: tuple[str, ...]
    scope_status: str
    quantifier_status: str
    counterexample_status: str


def read_proof_redteam_status(
    path: Path,
    *,
    project_root: Path,
    expected_manuscript_path: str | None = None,
    expected_manuscript_sha256: str | None = None,
    expected_round: int | None = None,
    expected_claim_ids: tuple[str, ...] = (),
    expected_proof_artifact_paths: tuple[str, ...] = (),
) -> tuple[str | None, str | None]:
    """Read and validate one proof-redteam artifact, returning ``(status, error)``."""

    try:
        meta, body = extract_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return None, str(exc)
    except FrontmatterParseError as exc:
        return None, str(exc)

    raw_status = meta.get("status")
    if not isinstance(raw_status, str) or not raw_status.strip():
        return None, "top-level frontmatter `status` is missing"
    status = raw_status.strip().lower()
    if status not in _PROOF_REDTEAM_STATUS_VALUE_SET:
        allowed = ", ".join(PROOF_REDTEAM_STATUS_VALUES)
        return None, f"top-level frontmatter `status` must be one of: {allowed}"

    reviewer = meta.get("reviewer")
    if reviewer != PROOF_AUDIT_REVIEWER:
        return None, f"top-level frontmatter `reviewer` must be `{PROOF_AUDIT_REVIEWER}`"

    claim_ids = meta.get("claim_ids")
    if not isinstance(claim_ids, list) or any(not isinstance(item, str) or not item.strip() for item in claim_ids):
        return None, "top-level frontmatter `claim_ids` must be a list of strings"
    normalized_claim_ids = tuple(dict.fromkeys(item.strip() for item in claim_ids))
    if expected_claim_ids and set(normalized_claim_ids) != set(expected_claim_ids):
        return None, "top-level frontmatter `claim_ids` does not match the theorem-bearing claims under review"

    proof_artifact_paths = meta.get("proof_artifact_paths")
    if (
        not isinstance(proof_artifact_paths, list)
        or not proof_artifact_paths
        or any(not isinstance(item, str) or not item.strip() for item in proof_artifact_paths)
    ):
        return None, "top-level frontmatter `proof_artifact_paths` must be a non-empty list of strings"
    normalized_proof_artifact_paths = tuple(dict.fromkeys(item.strip() for item in proof_artifact_paths))
    for proof_artifact_path in normalized_proof_artifact_paths:
        resolved_proof_artifact_path = resolve_review_manuscript_path(project_root, proof_artifact_path)
        if not resolved_proof_artifact_path.exists() or not resolved_proof_artifact_path.is_file():
            return None, f"proof_artifact_paths entry does not resolve to a readable file: {proof_artifact_path}"
    if expected_proof_artifact_paths:
        missing_expected_paths = sorted(
            expected_path
            for expected_path in expected_proof_artifact_paths
            if expected_path not in normalized_proof_artifact_paths
        )
        if missing_expected_paths:
            return None, "proof_artifact_paths does not cover the expected proof artifacts under review"

    if expected_manuscript_path is not None:
        raw_manuscript_path = meta.get("manuscript_path")
        if not isinstance(raw_manuscript_path, str) or not raw_manuscript_path.strip():
            return None, "top-level frontmatter `manuscript_path` is missing"
        resolved_artifact_path = resolve_review_manuscript_path(project_root, raw_manuscript_path.strip())
        resolved_expected_path = resolve_review_manuscript_path(project_root, expected_manuscript_path)
        if resolved_artifact_path != resolved_expected_path:
            return None, "top-level frontmatter `manuscript_path` does not match the active manuscript"

    if expected_manuscript_sha256 is not None:
        raw_manuscript_sha256 = meta.get("manuscript_sha256")
        if not isinstance(raw_manuscript_sha256, str) or len(raw_manuscript_sha256.strip()) != 64:
            return None, "top-level frontmatter `manuscript_sha256` must be a lowercase 64-hex digest"
        if raw_manuscript_sha256.strip().lower() != expected_manuscript_sha256.lower():
            return None, "top-level frontmatter `manuscript_sha256` does not match the active manuscript"

    if expected_round is not None:
        raw_round = meta.get("round")
        try:
            round_number = int(raw_round)
        except (TypeError, ValueError):
            return None, "top-level frontmatter `round` must be an integer"
        if round_number != expected_round:
            return None, "top-level frontmatter `round` does not match the active review round"

    structured_audit, structured_audit_error = _read_proof_redteam_structured_audit(meta)
    if structured_audit_error is not None:
        return None, structured_audit_error

    missing_sections = [section for section in PROOF_REDTEAM_REQUIRED_SECTIONS if section not in body]
    if missing_sections:
        return None, f"proof-redteam body is missing required sections: {', '.join(missing_sections)}"

    exact_claim_line = _first_meaningful_line(_section_body(body, "## Proof Inventory"))
    if exact_claim_line is None or not exact_claim_line.lower().startswith("- exact claim / theorem text:"):
        return None, "proof-redteam Proof Inventory must start with the exact claim / theorem text"
    if exact_claim_line.rstrip().endswith(":"):
        return None, "proof-redteam exact claim / theorem text must not be blank"

    for subsection in PROOF_REDTEAM_REQUIRED_COVERAGE_SUBSECTIONS:
        if not _section_has_substantive_content(body, subsection):
            return None, f"proof-redteam coverage subsection is empty: {subsection}"

    adversarial_probe_body = _section_body(body, "## Adversarial Probe")
    if "Probe type:" not in adversarial_probe_body or "Result:" not in adversarial_probe_body:
        return None, "proof-redteam Adversarial Probe must record both probe type and result"

    verdict_body = _section_body(body, "## Verdict")
    if (
        "Scope status:" not in verdict_body
        or "Quantifier status:" not in verdict_body
        or "Counterexample status:" not in verdict_body
    ):
        return None, "proof-redteam Verdict must include scope, quantifier, and counterexample status lines"

    if status == "passed":
        structured_failures: list[str] = []
        if structured_audit.missing_parameter_symbols:
            structured_failures.append(
                "missing_parameter_symbols=" + ", ".join(structured_audit.missing_parameter_symbols)
            )
        if structured_audit.missing_hypothesis_ids:
            structured_failures.append("missing_hypothesis_ids=" + ", ".join(structured_audit.missing_hypothesis_ids))
        if structured_audit.coverage_gaps:
            structured_failures.append("coverage_gaps=" + ", ".join(structured_audit.coverage_gaps[:3]))
        if structured_audit.scope_status != "matched":
            structured_failures.append(f"scope_status={structured_audit.scope_status}")
        if structured_audit.quantifier_status != "matched":
            structured_failures.append(f"quantifier_status={structured_audit.quantifier_status}")
        if structured_audit.counterexample_status != "none_found":
            structured_failures.append(f"counterexample_status={structured_audit.counterexample_status}")
        if structured_failures:
            return None, (
                "proof-redteam `status: passed` is inconsistent with structured audit fields: "
                + "; ".join(structured_failures)
            )

    return status, None


def _read_proof_redteam_structured_audit(
    meta: dict[str, object],
) -> tuple[ProofRedteamStructuredAudit | None, str | None]:
    missing_parameter_symbols, error = _read_proof_redteam_string_list(meta, "missing_parameter_symbols")
    if error is not None:
        return None, error
    missing_hypothesis_ids, error = _read_proof_redteam_string_list(meta, "missing_hypothesis_ids")
    if error is not None:
        return None, error
    coverage_gaps, error = _read_proof_redteam_string_list(meta, "coverage_gaps")
    if error is not None:
        return None, error
    scope_status, error = _read_proof_redteam_status_value(
        meta, "scope_status", _PROOF_REDTEAM_SCOPE_STATUS_VALUE_SET
    )
    if error is not None:
        return None, error
    quantifier_status, error = _read_proof_redteam_status_value(
        meta,
        "quantifier_status",
        _PROOF_REDTEAM_QUANTIFIER_STATUS_VALUE_SET,
    )
    if error is not None:
        return None, error
    counterexample_status, error = _read_proof_redteam_status_value(
        meta,
        "counterexample_status",
        _PROOF_REDTEAM_COUNTEREXAMPLE_STATUS_VALUE_SET,
    )
    if error is not None:
        return None, error
    return (
        ProofRedteamStructuredAudit(
            missing_parameter_symbols=missing_parameter_symbols,
            missing_hypothesis_ids=missing_hypothesis_ids,
            coverage_gaps=coverage_gaps,
            scope_status=scope_status,
            quantifier_status=quantifier_status,
            counterexample_status=counterexample_status,
        ),
        None,
    )


def _read_proof_redteam_string_list(meta: dict[str, object], field_name: str) -> tuple[tuple[str, ...], str | None]:
    if field_name not in meta:
        return (), f"top-level frontmatter `{field_name}` is missing"
    value = meta.get(field_name)
    if not isinstance(value, list):
        return (), f"top-level frontmatter `{field_name}` must be a list of strings"
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return (), f"top-level frontmatter `{field_name}` must be a list of strings"
    return tuple(dict.fromkeys(item.strip() for item in value)), None


def _read_proof_redteam_status_value(
    meta: dict[str, object],
    field_name: str,
    allowed_values: frozenset[str],
) -> tuple[str, str | None]:
    if field_name not in meta:
        return "", f"top-level frontmatter `{field_name}` is missing"
    value = meta.get(field_name)
    if not isinstance(value, str) or not value.strip():
        allowed = ", ".join(sorted(allowed_values))
        return "", f"top-level frontmatter `{field_name}` must be one of: {allowed}"
    normalized = value.strip().lower()
    if normalized not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        return "", f"top-level frontmatter `{field_name}` must be one of: {allowed}"
    return normalized, None


def _section_body(body: str, heading: str) -> str:
    start = body.find(heading)
    if start < 0:
        return ""
    start += len(heading)
    remaining = body[start:]
    next_heading_offsets = [offset for marker in ("\n## ", "\n### ", "\n# ") if (offset := remaining.find(marker)) >= 0]
    if not next_heading_offsets:
        return remaining
    return remaining[: min(next_heading_offsets)]


def _first_meaningful_line(section_body: str) -> str | None:
    for raw_line in section_body.splitlines():
        line = raw_line.strip()
        if line:
            return line
    return None


def _section_has_substantive_content(body: str, heading: str) -> bool:
    section_body = _section_body(body, heading)
    pipe_lines = 0
    for raw_line in section_body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in {"| --- | --- | --- | --- |", "| --- | --- | --- | --- | --- |"}:
            continue
        if line.startswith("|"):
            pipe_lines += 1
            continue
        if line.startswith("-"):
            return True
    return pipe_lines >= 2
