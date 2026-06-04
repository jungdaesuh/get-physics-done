"""Proof-review freshness helpers for phase verification and manuscript math review."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from gpd.contracts import statement_looks_theorem_like
from gpd.core.artifact_text import ArtifactTextError, load_artifact_text_surface
from gpd.core.constants import (
    PLANNING_DIR_NAME,
    PUBLICATION_DIR_NAME,
    PUBLICATION_MANUSCRIPT_DIR_NAME,
    ProjectLayout,
)
from gpd.core.manuscript_artifacts import resolve_current_manuscript_entrypoint, resolve_explicit_publication_subject
from gpd.core.proof_redteam_contract import read_proof_redteam_status as _read_proof_redteam_status
from gpd.core.publication_review_paths import resolve_review_manuscript_path, review_artifact_round
from gpd.core.referee_policy import validate_stage_review_artifact_alignment
from gpd.core.reproducibility import compute_sha256
from gpd.core.utils import normalize_ascii_slug
from gpd.mcp.paper.review_artifacts import read_claim_index, read_stage_review_report

__all__ = [
    "MANUSCRIPT_PROOF_REVIEW_MANIFEST_NAME",
    "ProofReviewStatus",
    "manuscript_has_theorem_bearing_claim_inventory",
    "manuscript_has_theorem_bearing_language",
    "manuscript_has_theorem_bearing_review_anchor",
    "manuscript_requires_theorem_bearing_review",
    "publication_lineage_mode",
    "publication_lineage_roots",
    "manuscript_proof_review_manifest_path",
    "phase_proof_review_manifest_path",
    "publication_subject_slug",
    "resolve_manuscript_proof_review_status",
    "resolve_phase_proof_review_status",
]

MANUSCRIPT_PROOF_REVIEW_MANIFEST_NAME = "PROOF-REVIEW-MANIFEST.json"
_PHASE_PROOF_REVIEW_MANIFEST_SUFFIX = "-PROOF-REVIEW-MANIFEST.json"
_PHASE_PROOF_AFFECTING_EXTENSIONS = frozenset(
    {
        ".md",
        ".tex",
        ".txt",
        ".py",
        ".ipynb",
        ".jl",
        ".f90",
        ".m",
        ".wl",
        ".wls",
        ".nb",
        ".yaml",
        ".yml",
        ".bib",
    }
)
_MANUSCRIPT_PROOF_AFFECTING_EXTENSIONS = frozenset(
    {
        ".csv",
        ".docx",
        ".md",
        ".pdf",
        ".eps",
        ".jpg",
        ".jpeg",
        ".png",
        ".svg",
        ".tex",
        ".tsv",
        ".bib",
        ".bst",
        ".sty",
        ".cls",
        ".txt",
        ".xlsx",
        ".xlsm",
    }
)
_STAGE_MATH_FILENAME_RE = re.compile(r"^STAGE-math(?P<round_suffix>-R(?P<round>\d+))?\.json$")
_CLAIMS_FILENAME_RE = re.compile(r"^CLAIMS(?P<round_suffix>-R(?P<round>\d+))?\.json$")
_THEOREM_STYLE_MANUSCRIPT_RE = re.compile(
    r"(\\begin\{(?:theorem|lemma|corollary|proposition|claim|proof)\})"
    r"|(\\newtheorem\{)"
    r"|(^\s{0,3}\#{1,6}\s*(?:theorem|lemma|corollary|proposition|claim|proof)\b)"
    r"|(^\s*(?:theorem|lemma|corollary|proposition|claim|proof)\b[\s.:])",
    re.IGNORECASE | re.MULTILINE,
)
_PROJECT_LOCAL_MANUSCRIPT_ROOT_NAMES = frozenset({"paper", "manuscript", "draft"})


@dataclass(frozen=True, slots=True)
class _MathReviewAnchor:
    stage_artifact: Path
    claim_index_artifact: Path
    round_number: int
    round_suffix: str
    proof_bearing: bool
    theorem_claim_ids: tuple[str, ...]
    proof_artifact_paths: tuple[str, ...]
    validation_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProofReviewStatus:
    """Freshness status for prior proof review over a file set."""

    scope: str
    state: str
    can_rely_on_prior_review: bool
    detail: str
    manifest_path: Path | None = None
    anchor_artifact: Path | None = None
    watched_files: tuple[Path, ...] = ()
    changed_files: tuple[Path, ...] = ()
    manifest_bootstrapped: bool = False

    def to_context_dict(self, project_root: Path) -> dict[str, object]:
        return {
            "scope": self.scope,
            "state": self.state,
            "can_rely_on_prior_review": self.can_rely_on_prior_review,
            "detail": self.detail,
            "manifest_path": _relative_path(project_root, self.manifest_path),
            "anchor_artifact": _relative_path(project_root, self.anchor_artifact),
            "watched_files": [_relative_path(project_root, path) for path in self.watched_files],
            "watched_file_count": len(self.watched_files),
            "changed_files": [_relative_path(project_root, path) for path in self.changed_files],
            "changed_file_count": len(self.changed_files),
            "manifest_bootstrapped": self.manifest_bootstrapped,
        }


def phase_proof_review_manifest_path(verification_path: Path) -> Path:
    """Return the canonical proof-review manifest path for a phase verification artifact."""

    if verification_path.name.endswith("-VERIFICATION.md"):
        stem = verification_path.name[: -len("-VERIFICATION.md")]
        return verification_path.with_name(f"{stem}{_PHASE_PROOF_REVIEW_MANIFEST_SUFFIX}")
    return verification_path.with_name(MANUSCRIPT_PROOF_REVIEW_MANIFEST_NAME)


def manuscript_proof_review_manifest_path(
    manuscript_entrypoint: Path,
    *,
    project_root: Path | None = None,
) -> Path:
    """Return the canonical proof-review manifest path for one manuscript subject."""

    if project_root is None or _uses_project_local_manuscript_manifest(project_root, manuscript_entrypoint):
        return manuscript_entrypoint.parent / MANUSCRIPT_PROOF_REVIEW_MANIFEST_NAME
    return _managed_publication_proof_review_manifest_path(project_root, manuscript_entrypoint)


def _uses_project_local_manuscript_manifest(project_root: Path, manuscript_entrypoint: Path) -> bool:
    """Return whether one manuscript subject should keep its proof manifest beside the manuscript."""

    try:
        relative = manuscript_entrypoint.resolve(strict=False).relative_to(project_root.resolve(strict=False))
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] in _PROJECT_LOCAL_MANUSCRIPT_ROOT_NAMES


def _managed_publication_proof_review_manifest_path(project_root: Path, manuscript_entrypoint: Path) -> Path:
    """Return the managed proof-review manifest path for one publication subject."""

    layout = ProjectLayout(project_root)
    return (
        layout.publication_proof_review_dir(publication_subject_slug(project_root, manuscript_entrypoint))
        / MANUSCRIPT_PROOF_REVIEW_MANIFEST_NAME
    )


def _is_project_managed_publication_lane(relative: Path | None) -> bool:
    return (
        relative is not None
        and len(relative.parts) >= 4
        and relative.parts[0] == PLANNING_DIR_NAME
        and relative.parts[1] == PUBLICATION_DIR_NAME
        and relative.parts[3] == PUBLICATION_MANUSCRIPT_DIR_NAME
    )


def publication_lineage_mode(project_root: Path, manuscript_entrypoint: Path) -> str:
    """Return whether review/response lineage stays global or becomes subject-owned."""

    try:
        relative = manuscript_entrypoint.resolve(strict=False).relative_to(project_root.resolve(strict=False))
    except ValueError:
        relative = None
    if relative is not None and relative.parts and relative.parts[0] in _PROJECT_LOCAL_MANUSCRIPT_ROOT_NAMES:
        return "global_gpd"
    if _is_project_managed_publication_lane(relative):
        return "subject_owned"
    return "subject_owned"


def _uses_global_publication_lineage(project_root: Path, manuscript_entrypoint: Path) -> bool:
    """Return whether review/response lineage should remain on the global GPD roots."""

    return publication_lineage_mode(project_root, manuscript_entrypoint) == "global_gpd"


def publication_lineage_roots(project_root: Path, manuscript_entrypoint: Path) -> tuple[Path, Path]:
    """Return the publication root and review root for one manuscript subject."""

    layout = ProjectLayout(project_root)
    if _uses_global_publication_lineage(project_root, manuscript_entrypoint):
        publication_root = layout.gpd
    else:
        subject_slug = publication_subject_slug(project_root, manuscript_entrypoint)
        publication_root = layout.publication_subject_dir(subject_slug)
        return publication_root, layout.publication_review_dir(subject_slug)
    return publication_root, layout.review_dir


def publication_subject_slug(project_root: Path, manuscript_entrypoint: Path) -> str:
    """Return the managed publication subject slug for one resolved manuscript subject."""

    resolved_root = project_root.resolve(strict=False)
    resolved_entrypoint = manuscript_entrypoint.resolve(strict=False)
    try:
        relative = resolved_entrypoint.relative_to(resolved_root)
    except ValueError:
        relative = None
    if _is_project_managed_publication_lane(relative):
        return relative.parts[2]
    label = relative.as_posix() if relative is not None else resolved_entrypoint.as_posix()
    slug_source = label[: -len(resolved_entrypoint.suffix)] if resolved_entrypoint.suffix else label
    slug = normalize_ascii_slug(slug_source.replace("/", "-")) or "manuscript"
    slug = slug[:48].rstrip("-") or "manuscript"
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def manuscript_has_theorem_bearing_review_anchor(
    project_root: Path,
    manuscript_entrypoint: Path | None = None,
) -> bool:
    """Return whether the latest matching staged math review marks the manuscript as theorem-bearing."""

    entrypoint = manuscript_entrypoint or resolve_current_manuscript_entrypoint(project_root, allow_markdown=True)
    if entrypoint is None:
        return False
    anchor = _latest_matching_math_review_anchor(project_root, entrypoint)
    return bool(anchor and anchor.proof_bearing)


def manuscript_has_theorem_bearing_claim_inventory(
    project_root: Path,
    manuscript_entrypoint: Path | None = None,
) -> bool:
    """Return whether the latest matching staged claim inventory is theorem-bearing."""

    entrypoint = manuscript_entrypoint or resolve_current_manuscript_entrypoint(project_root, allow_markdown=True)
    if entrypoint is None:
        return False

    _publication_root, review_dir = publication_lineage_roots(project_root, entrypoint)
    if not review_dir.exists():
        return False

    resolved_manuscript = resolve_review_manuscript_path(project_root, entrypoint.as_posix())
    matches: list[tuple[int, int, bool]] = []
    for path in sorted(review_dir.glob("CLAIMS*.json")):
        match = _claim_round_details(path)
        if match is None:
            continue
        round_number, _round_suffix = match
        try:
            claim_index = read_claim_index(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, PydanticValidationError):
            continue
        if resolve_review_manuscript_path(project_root, claim_index.manuscript_path) != resolved_manuscript:
            continue
        matches.append(
            (
                round_number,
                path.stat().st_mtime_ns,
                any(claim.theorem_bearing for claim in claim_index.claims),
            )
        )

    if not matches:
        return False
    _, _, theorem_bearing = max(matches)
    return theorem_bearing


def manuscript_has_theorem_bearing_language(
    project_root: Path,
    manuscript_entrypoint: Path | None = None,
) -> bool:
    """Return whether manuscript text itself looks theorem-bearing."""

    entrypoint = manuscript_entrypoint or resolve_current_manuscript_entrypoint(project_root, allow_markdown=True)
    if entrypoint is None or not entrypoint.exists():
        return False

    manuscript_paths: list[Path] = [entrypoint]
    if entrypoint.suffix.lower() in {".tex", ".md"}:
        for candidate in sorted(entrypoint.parent.rglob("*")):
            if candidate == entrypoint or not candidate.is_file():
                continue
            if candidate.suffix.lower() not in {".tex", ".md"}:
                continue
            manuscript_paths.append(candidate)

    for manuscript_path in manuscript_paths:
        try:
            content = load_artifact_text_surface(manuscript_path).text
        except ArtifactTextError:
            continue
        if _THEOREM_STYLE_MANUSCRIPT_RE.search(content):
            return True
        if statement_looks_theorem_like(content):
            return True
    return False


def manuscript_requires_theorem_bearing_review(
    project_root: Path,
    manuscript_entrypoint: Path | None = None,
) -> bool:
    """Return whether a manuscript should be treated as theorem-bearing."""

    entrypoint = manuscript_entrypoint or resolve_current_manuscript_entrypoint(project_root, allow_markdown=True)
    return entrypoint is not None and (
        manuscript_has_theorem_bearing_language(project_root, entrypoint)
        or manuscript_has_theorem_bearing_review_anchor(project_root, entrypoint)
        or manuscript_has_theorem_bearing_claim_inventory(project_root, entrypoint)
    )


def _resolve_review_artifacts(project_root: Path, artifact_paths: tuple[str, ...]) -> tuple[Path, ...]:
    """Resolve review artifact paths against the project root."""

    return tuple(resolve_review_manuscript_path(project_root, path) for path in artifact_paths if path.strip())


def resolve_phase_proof_review_status(
    project_root: Path,
    phase_dir: Path | None,
    *,
    persist_manifest: bool = False,
) -> ProofReviewStatus:
    """Resolve freshness for a phase-scoped proof review."""

    if phase_dir is None or not phase_dir.exists():
        return ProofReviewStatus(
            scope="phase",
            state="not_reviewed",
            can_rely_on_prior_review=False,
            detail="phase directory not found; no prior proof review artifact is available",
        )

    verification_path = _latest_phase_verification_artifact(phase_dir)
    if verification_path is None:
        return ProofReviewStatus(
            scope="phase",
            state="not_reviewed",
            can_rely_on_prior_review=False,
            detail="no prior phase verification artifact is available to anchor proof review freshness",
        )

    manifest_path = phase_proof_review_manifest_path(verification_path)
    watched_files = _collect_phase_watched_files(phase_dir, verification_path, manifest_path)
    return _resolve_status(
        project_root,
        scope="phase",
        anchor_artifact=verification_path,
        manifest_path=manifest_path,
        watched_files=watched_files,
        persist_manifest=persist_manifest,
    )


def resolve_manuscript_proof_review_status(
    project_root: Path,
    manuscript_entrypoint: Path | None = None,
    *,
    persist_manifest: bool = False,
) -> ProofReviewStatus:
    """Resolve freshness for manuscript-scoped proof review."""

    entrypoint = manuscript_entrypoint or resolve_current_manuscript_entrypoint(project_root, allow_markdown=True)
    if entrypoint is None:
        return ProofReviewStatus(
            scope="manuscript",
            state="not_reviewed",
            can_rely_on_prior_review=False,
            detail="no manuscript entrypoint is available to anchor proof review freshness",
        )

    review_anchor = _latest_matching_math_review_anchor(project_root, entrypoint)
    actual_manuscript_sha256 = compute_sha256(entrypoint)
    manuscript_watch_root = _resolved_manuscript_watch_root(project_root, entrypoint)
    watched_files = _collect_manuscript_watched_files(manuscript_watch_root)
    manifest_path = manuscript_proof_review_manifest_path(entrypoint, project_root=project_root)
    if review_anchor is None:
        return ProofReviewStatus(
            scope="manuscript",
            state="not_reviewed",
            can_rely_on_prior_review=False,
            detail="no prior staged math review artifact matches the active manuscript",
            manifest_path=manifest_path,
            watched_files=watched_files,
        )
    if review_anchor.validation_errors:
        return ProofReviewStatus(
            scope="manuscript",
            state="invalid_required_artifact",
            can_rely_on_prior_review=False,
            detail=(
                f"{_relative_path(project_root, review_anchor.stage_artifact)} is not a valid proof-review anchor: "
                + "; ".join(review_anchor.validation_errors[:3])
            ),
            manifest_path=manifest_path,
            anchor_artifact=review_anchor.stage_artifact,
            watched_files=_with_extra_watched_files(
                watched_files,
                review_anchor.stage_artifact,
                review_anchor.claim_index_artifact,
            ),
        )

    anchor_artifact = review_anchor.stage_artifact
    watched_files = _with_extra_watched_files(
        watched_files,
        review_anchor.stage_artifact,
        review_anchor.claim_index_artifact,
    )
    watched_files = _with_extra_watched_files(
        watched_files,
        _resolve_review_artifacts(project_root, review_anchor.proof_artifact_paths),
    )
    if review_anchor.proof_bearing:
        _publication_root, review_dir = publication_lineage_roots(project_root, entrypoint)
        proof_redteam_path = review_dir / f"PROOF-REDTEAM{review_anchor.round_suffix}.md"
        watched_files = _with_extra_watched_files(watched_files, proof_redteam_path)
        if not proof_redteam_path.exists():
            return ProofReviewStatus(
                scope="manuscript",
                state="missing_required_artifact",
                can_rely_on_prior_review=False,
                detail=(
                    "proof-bearing manuscript review requires "
                    f"{_relative_path(project_root, proof_redteam_path)} to exist with `status: passed`"
                ),
                manifest_path=manifest_path,
                anchor_artifact=proof_redteam_path,
                watched_files=watched_files,
            )
        proof_redteam_status, proof_redteam_error = _read_proof_redteam_status(
            proof_redteam_path,
            project_root=project_root,
            expected_manuscript_path=_relative_path(project_root, entrypoint),
            expected_manuscript_sha256=actual_manuscript_sha256,
            expected_round=review_anchor.round_number,
            expected_claim_ids=review_anchor.theorem_claim_ids,
            expected_proof_artifact_paths=review_anchor.proof_artifact_paths,
        )
        if proof_redteam_error is not None:
            return ProofReviewStatus(
                scope="manuscript",
                state="invalid_required_artifact",
                can_rely_on_prior_review=False,
                detail=f"{_relative_path(project_root, proof_redteam_path)} is invalid: {proof_redteam_error}",
                manifest_path=manifest_path,
                anchor_artifact=proof_redteam_path,
                watched_files=watched_files,
            )
        if proof_redteam_status != "passed":
            return ProofReviewStatus(
                scope="manuscript",
                state="open_required_artifact",
                can_rely_on_prior_review=False,
                detail=(
                    f"{_relative_path(project_root, proof_redteam_path)} reports status `{proof_redteam_status}`; "
                    "proof-bearing manuscript review requires `status: passed`"
                ),
                manifest_path=manifest_path,
                anchor_artifact=proof_redteam_path,
                watched_files=watched_files,
            )
        anchor_artifact = proof_redteam_path

    return _resolve_status(
        project_root,
        scope="manuscript",
        anchor_artifact=anchor_artifact,
        manifest_path=manifest_path,
        watched_files=watched_files,
        persist_manifest=persist_manifest,
    )


def _resolve_status(
    project_root: Path,
    *,
    scope: str,
    anchor_artifact: Path,
    manifest_path: Path,
    watched_files: tuple[Path, ...],
    persist_manifest: bool,
) -> ProofReviewStatus:
    current_hashes = {_relative_path(project_root, path): compute_sha256(path) for path in watched_files}

    if manifest_path.exists():
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_records = _manifest_records(manifest_payload, scope=scope)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return ProofReviewStatus(
                scope=scope,
                state="invalid_manifest",
                can_rely_on_prior_review=False,
                detail=f"proof-review manifest is invalid: {exc}",
                manifest_path=manifest_path,
                anchor_artifact=anchor_artifact,
                watched_files=watched_files,
            )

        expected_hashes = manifest_records["hashes"]
        changed_labels = sorted(
            path
            for path in expected_hashes.keys() & current_hashes.keys()
            if expected_hashes[path] != current_hashes[path]
        )
        missing_labels = sorted(path for path in expected_hashes.keys() - current_hashes.keys())
        unexpected_labels = sorted(path for path in current_hashes.keys() - expected_hashes.keys())
        changed_files = tuple(project_root / path for path in [*changed_labels, *missing_labels, *unexpected_labels])

        if changed_files:
            return ProofReviewStatus(
                scope=scope,
                state="stale",
                can_rely_on_prior_review=False,
                detail=(
                    f"proof-review manifest is stale: {', '.join([*changed_labels, *missing_labels, *unexpected_labels][:3])}"
                ),
                manifest_path=manifest_path,
                anchor_artifact=anchor_artifact,
                watched_files=watched_files,
                changed_files=changed_files,
            )

        return ProofReviewStatus(
            scope=scope,
            state="fresh",
            can_rely_on_prior_review=True,
            detail=(
                f"{_relative_path(project_root, manifest_path)} matches {len(watched_files)} proof-affecting file(s)"
            ),
            manifest_path=manifest_path,
            anchor_artifact=anchor_artifact,
            watched_files=watched_files,
        )

    anchor_mtime = anchor_artifact.stat().st_mtime_ns
    changed_files = tuple(path for path in watched_files if path.stat().st_mtime_ns > anchor_mtime)
    if changed_files:
        return ProofReviewStatus(
            scope=scope,
            state="stale",
            can_rely_on_prior_review=False,
            detail=(
                f"{len(changed_files)} proof-affecting file(s) changed after {_relative_path(project_root, anchor_artifact)}: "
                + ", ".join(_relative_path(project_root, path) for path in changed_files[:3])
            ),
            manifest_path=manifest_path,
            anchor_artifact=anchor_artifact,
            watched_files=watched_files,
            changed_files=changed_files,
        )

    manifest_bootstrapped = False
    if persist_manifest:
        _write_manifest(
            manifest_path,
            scope=scope,
            anchor_artifact=anchor_artifact,
            watched_files=current_hashes,
        )
        manifest_bootstrapped = True

    detail = (
        f"{_relative_path(project_root, manifest_path)} bootstrapped from {_relative_path(project_root, anchor_artifact)}"
        if manifest_bootstrapped
        else (
            f"no proof-review manifest yet, but {len(watched_files)} proof-affecting file(s) are not newer than "
            f"{_relative_path(project_root, anchor_artifact)}"
        )
    )
    return ProofReviewStatus(
        scope=scope,
        state="fresh",
        can_rely_on_prior_review=True,
        detail=detail,
        manifest_path=manifest_path,
        anchor_artifact=anchor_artifact,
        watched_files=watched_files,
        manifest_bootstrapped=manifest_bootstrapped,
    )


def _write_manifest(
    manifest_path: Path,
    *,
    scope: str,
    anchor_artifact: Path,
    watched_files: dict[str, str],
) -> None:
    manifest_payload = {
        "version": 1,
        "scope": scope,
        "created_at": datetime.now(UTC).isoformat(),
        "anchor_artifact": anchor_artifact.as_posix(),
        "watched_files": [{"path": path, "sha256": sha256} for path, sha256 in sorted(watched_files.items())],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")


def _manifest_records(payload: object, *, scope: str) -> dict[str, dict[str, str]]:
    if not isinstance(payload, dict):
        raise ValueError("manifest payload must be a JSON object")
    if payload.get("version") != 1:
        raise ValueError("manifest version must be 1")
    if payload.get("scope") != scope:
        raise ValueError(f'manifest scope must be "{scope}"')
    watched_files = payload.get("watched_files")
    if not isinstance(watched_files, list):
        raise ValueError("manifest watched_files must be a list")

    hashes: dict[str, str] = {}
    for record in watched_files:
        if not isinstance(record, dict):
            raise ValueError("manifest watched_files entries must be objects")
        rel_path = str(record.get("path") or "").strip()
        sha256 = str(record.get("sha256") or "").strip().lower()
        if not rel_path:
            raise ValueError("manifest watched_files entries must include a non-empty path")
        if len(sha256) != 64:
            raise ValueError(f"manifest watched_files entry for {rel_path} is missing a valid sha256")
        hashes[rel_path] = sha256
    return {"hashes": hashes}


def _latest_phase_verification_artifact(phase_dir: Path) -> Path | None:
    candidates = sorted(path for path in phase_dir.glob("*VERIFICATION.md") if path.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _collect_phase_watched_files(phase_dir: Path, verification_path: Path, manifest_path: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for path in sorted(phase_dir.rglob("*")):
        if not path.is_file():
            continue
        if path == verification_path or path == manifest_path:
            continue
        if path.name.startswith("."):
            continue
        if path.name.endswith("-VERIFICATION.md") or path.name.endswith("-VALIDATION.md"):
            continue
        if path.suffix.lower() not in _PHASE_PROOF_AFFECTING_EXTENSIONS:
            continue
        files.append(path)
    return tuple(files)


def _collect_manuscript_watched_files(manuscript_root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for path in sorted(manuscript_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == MANUSCRIPT_PROOF_REVIEW_MANIFEST_NAME or path.name.startswith("."):
            continue
        if path.suffix.lower() not in _MANUSCRIPT_PROOF_AFFECTING_EXTENSIONS:
            continue
        files.append(path)
    return tuple(files)


def _resolved_manuscript_watch_root(project_root: Path, manuscript_entrypoint: Path) -> Path:
    subject = resolve_explicit_publication_subject(project_root, manuscript_entrypoint, allow_markdown=True)
    return subject.artifact_base or subject.manuscript_root or manuscript_entrypoint.parent


def _with_extra_watched_files(*groups: tuple[Path, ...] | Path) -> tuple[Path, ...]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for group in groups:
        if isinstance(group, Path):
            candidates = (group,)
        else:
            candidates = group
        for path in candidates:
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            ordered.append(path)
    return tuple(ordered)


def _latest_matching_math_review_anchor(project_root: Path, manuscript_entrypoint: Path) -> _MathReviewAnchor | None:
    _publication_root, review_dir = publication_lineage_roots(project_root, manuscript_entrypoint)
    if not review_dir.exists():
        return None

    matches: list[tuple[int, int, _MathReviewAnchor]] = []
    resolved_manuscript = resolve_review_manuscript_path(project_root, manuscript_entrypoint.as_posix())
    expected_manuscript_path = _relative_path(project_root, manuscript_entrypoint)
    for path in sorted(review_dir.glob("STAGE-math*.json")):
        round_details = _math_review_round_details(path)
        if round_details is None:
            continue
        round_number, round_suffix = round_details
        claim_index_path = review_dir / f"CLAIMS{round_suffix}.json"
        theorem_claim_ids: list[str] = []
        proof_artifact_paths: list[str] = []
        validation_errors: list[str] = []
        claim_index = None
        claim_index_matches_current = False
        try:
            claim_index = read_claim_index(claim_index_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, PydanticValidationError) as exc:
            validation_errors.append(f"{claim_index_path.name} could not be loaded: {exc}")
        else:
            claim_index_matches_current = (
                resolve_review_manuscript_path(project_root, claim_index.manuscript_path) == resolved_manuscript
            )
            if claim_index_matches_current:
                theorem_claim_ids = sorted(claim.claim_id for claim in claim_index.claims if claim.theorem_bearing)
                proof_artifact_paths = sorted(
                    {
                        claim.artifact_path
                        for claim in claim_index.claims
                        if claim.claim_id in theorem_claim_ids and claim.artifact_path.strip()
                    }
                )
                if expected_manuscript_path is not None and expected_manuscript_path not in proof_artifact_paths:
                    proof_artifact_paths.append(expected_manuscript_path)

        try:
            report = read_stage_review_report(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, PydanticValidationError) as exc:
            if not claim_index_matches_current:
                continue
            validation_errors.append(f"{path.name} could not be loaded: {exc}")
            matches.append(
                (
                    round_number,
                    path.stat().st_mtime_ns,
                    _MathReviewAnchor(
                        stage_artifact=path,
                        claim_index_artifact=claim_index_path,
                        round_number=round_number,
                        round_suffix=round_suffix,
                        proof_bearing=bool(theorem_claim_ids),
                        theorem_claim_ids=tuple(theorem_claim_ids),
                        proof_artifact_paths=tuple(path_text for path_text in proof_artifact_paths if path_text),
                        validation_errors=tuple(validation_errors),
                    ),
                )
            )
            continue
        report_matches_current = (
            resolve_review_manuscript_path(project_root, report.manuscript_path) == resolved_manuscript
        )
        if not report_matches_current and not claim_index_matches_current:
            continue
        if claim_index is not None:
            validation_errors.extend(
                validate_stage_review_artifact_alignment(
                    report,
                    artifact_path=path,
                    claim_index=claim_index,
                    expected_manuscript_path=expected_manuscript_path,
                    expected_manuscript_label="active manuscript",
                )
            )
            if theorem_claim_ids:
                missing_reviewed_claims = sorted(
                    claim_id for claim_id in theorem_claim_ids if claim_id not in set(report.claims_reviewed)
                )
                if missing_reviewed_claims:
                    validation_errors.append(
                        f"{path.name} theorem-bearing claims must appear in claims_reviewed: "
                        + ", ".join(missing_reviewed_claims)
                    )
        proof_bearing = bool(report.proof_audits) or bool(theorem_claim_ids)
        matches.append(
            (
                round_number,
                path.stat().st_mtime_ns,
                _MathReviewAnchor(
                    stage_artifact=path,
                    claim_index_artifact=claim_index_path,
                    round_number=round_number,
                    round_suffix=round_suffix,
                    proof_bearing=proof_bearing,
                    theorem_claim_ids=tuple(theorem_claim_ids),
                    proof_artifact_paths=tuple(path_text for path_text in proof_artifact_paths if path_text),
                    validation_errors=tuple(validation_errors),
                ),
            )
        )

    if not matches:
        return None
    _, _, latest = max(matches)
    return latest


def _math_review_round_details(path: Path) -> tuple[int, str] | None:
    return review_artifact_round(path, pattern=_STAGE_MATH_FILENAME_RE)


def _claim_round_details(path: Path) -> tuple[int, str] | None:
    return review_artifact_round(path, pattern=_CLAIMS_FILENAME_RE)


def _relative_path(project_root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()
