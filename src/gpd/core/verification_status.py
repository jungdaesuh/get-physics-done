"""Canonical verification status reader.

This module intentionally reads only YAML frontmatter. Routing callers should
fail closed on any missing, malformed, or unknown status instead of inferring a
pass from report prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gpd.core.constants import PHASES_DIR_NAME, PLANNING_DIR_NAME, VERIFICATION_SUFFIX
from gpd.core.frontmatter import VERIFICATION_REPORT_STATUSES, FrontmatterParseError, extract_frontmatter

CANONICAL_VERIFICATION_STATUSES = frozenset(VERIFICATION_REPORT_STATUSES)


@dataclass(frozen=True, slots=True)
class VerificationStatus:
    path: str | None
    exists: bool
    readable: bool
    parseable: bool
    status: str | None
    session_status: str | None
    score: str | None
    source: str | None
    errors: tuple[str, ...] = ()

    @property
    def is_known(self) -> bool:
        return (
            self.exists
            and self.readable
            and self.parseable
            and self.status in CANONICAL_VERIFICATION_STATUSES
        )

    @property
    def routing_status(self) -> str:
        if not self.exists:
            return "missing"
        if not self.readable:
            return "unreadable"
        if not self.parseable:
            return "unparseable"
        if self.status is None:
            return "missing_status"
        if self.status not in CANONICAL_VERIFICATION_STATUSES:
            return "unknown_status"
        return self.status

    def model_dump(self) -> dict[str, object]:
        return {
            "path": self.path,
            "exists": self.exists,
            "readable": self.readable,
            "parseable": self.parseable,
            "status": self.status,
            "session_status": self.session_status,
            "score": self.score,
            "source": self.source,
            "errors": list(self.errors),
            "routing_status": self.routing_status,
        }


def _string_field(meta: dict[str, object], key: str) -> str | None:
    value = meta.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def read_verification_status(path: Path) -> VerificationStatus:
    """Read a verification report's canonical status from frontmatter only."""

    resolved = path.resolve(strict=False)
    path_text = resolved.as_posix()
    if not resolved.exists():
        return VerificationStatus(
            path=path_text,
            exists=False,
            readable=False,
            parseable=False,
            status=None,
            session_status=None,
            score=None,
            source=None,
            errors=("verification report missing",),
        )

    try:
        content = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return VerificationStatus(
            path=path_text,
            exists=True,
            readable=False,
            parseable=False,
            status=None,
            session_status=None,
            score=None,
            source=None,
            errors=(str(exc),),
        )

    try:
        meta, _body = extract_frontmatter(content)
    except FrontmatterParseError as exc:
        return VerificationStatus(
            path=path_text,
            exists=True,
            readable=True,
            parseable=False,
            status=None,
            session_status=None,
            score=None,
            source="frontmatter",
            errors=(str(exc),),
        )

    raw_status = _string_field(meta, "status")
    status = raw_status.lower() if raw_status is not None else None
    errors: list[str] = []
    if status is None:
        errors.append("missing verification frontmatter status")
    elif status not in CANONICAL_VERIFICATION_STATUSES:
        errors.append(
            "unknown verification frontmatter status "
            f"{status!r}; expected one of {', '.join(VERIFICATION_REPORT_STATUSES)}"
        )

    session_status = _string_field(meta, "session_status")
    return VerificationStatus(
        path=path_text,
        exists=True,
        readable=True,
        parseable=True,
        status=status,
        session_status=session_status.lower() if session_status is not None else None,
        score=_string_field(meta, "score"),
        source="frontmatter",
        errors=tuple(errors),
    )


def verification_path_for_phase(cwd: Path, phase: str) -> Path | None:
    """Return the first conventional verification report path for ``phase``."""

    phase_norm = str(phase).strip()
    if not phase_norm:
        return None

    phases_dir = cwd / PLANNING_DIR_NAME / PHASES_DIR_NAME
    if not phases_dir.exists():
        return None

    for phase_dir in sorted(phases_dir.iterdir(), key=lambda path: path.name):
        if not phase_dir.is_dir():
            continue
        head = phase_dir.name.split("-", 1)[0]
        if head != phase_norm and head.lstrip("0") != phase_norm.lstrip("0"):
            continue

        for candidate in (
            phase_dir / f"{head}{VERIFICATION_SUFFIX}",
            phase_dir / "VERIFICATION.md",
        ):
            if candidate.exists():
                return candidate

        verification_files = sorted(phase_dir.glob(f"*{VERIFICATION_SUFFIX}"))
        if verification_files:
            return verification_files[0]
        return None

    return None
