"""Metadata-only task overlay registry.

Task overlays are selected at workflow spawn callsites. The registry deliberately
stores pointers and one-line summaries, not overlay bodies, so staged init
payloads and base agent prompts stay body-free.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

__all__ = [
    "TASK_OVERLAY_REFERENCE_PATH",
    "TaskOverlay",
    "TaskOverlaySelectionError",
    "build_task_overlay_compatibility_manifest",
    "build_task_overlay_load_manifest",
    "get_task_overlay",
    "list_task_overlays",
    "validate_task_overlay_selection",
]

TASK_OVERLAY_REFERENCE_PATH = "references/orchestration/task-overlays.md"
_APPROVED_REFERENCE_PREFIXES = ("references/orchestration/", "templates/")


class TaskOverlaySelectionError(ValueError):
    """Raised when selected task overlay metadata is invalid."""


@dataclass(frozen=True, slots=True)
class TaskOverlay:
    """One body-free task overlay metadata entry."""

    overlay_id: str
    role: str
    path: str
    summary: str

    def as_manifest_entry(self) -> dict[str, object]:
        """Render this overlay as a metadata-only load-manifest entry."""
        return {
            **asdict(self),
            "portable_path": f"@{{GPD_INSTALL_DIR}}/{self.path}",
            "body_loaded": False,
        }


_TASK_OVERLAYS: tuple[TaskOverlay, ...] = (
    TaskOverlay(
        overlay_id="executor.proof_bearing",
        role="gpd-executor",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Proof-bearing executor specialization selected only for theorem or derivation plan IDs.",
    ),
    TaskOverlay(
        overlay_id="executor.bounded_segment",
        role="gpd-executor",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Bounded executor segment metadata for first-result, pre-fanout, or cadence-gated work.",
    ),
    TaskOverlay(
        overlay_id="planner.proof_bearing",
        role="gpd-planner",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Planner metadata for theorem, hypothesis, conclusion, and proof-artifact obligations.",
    ),
    TaskOverlay(
        overlay_id="checker.proof_obligation",
        role="gpd-plan-checker",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Plan-checker metadata for proof-bearing plan validation.",
    ),
    TaskOverlay(
        overlay_id="review.reader.claim_extraction",
        role="gpd-review-reader",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Peer-review reader metadata for claim and artifact extraction.",
    ),
    TaskOverlay(
        overlay_id="review.literature.novelty_positioning",
        role="gpd-review-literature",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Peer-review literature metadata for novelty and positioning checks.",
    ),
    TaskOverlay(
        overlay_id="review.math.soundness",
        role="gpd-review-math",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Peer-review math metadata for mathematical soundness checks.",
    ),
    TaskOverlay(
        overlay_id="review.physics.interpretation",
        role="gpd-review-physics",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Peer-review physics metadata for interpretation and physical consistency checks.",
    ),
    TaskOverlay(
        overlay_id="review.significance.venue_fit",
        role="gpd-review-significance",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Peer-review significance metadata for importance and venue-fit checks.",
    ),
    TaskOverlay(
        overlay_id="paper_writer.section_results",
        role="gpd-paper-writer",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Paper-writer metadata for results-section authoring.",
    ),
    TaskOverlay(
        overlay_id="paper_writer.section_methods",
        role="gpd-paper-writer",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Paper-writer metadata for methods-section authoring.",
    ),
    TaskOverlay(
        overlay_id="paper_writer.section_intro_discussion",
        role="gpd-paper-writer",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Paper-writer metadata for introduction and discussion authoring.",
    ),
    TaskOverlay(
        overlay_id="paper_writer.section_abstract_conclusion",
        role="gpd-paper-writer",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Paper-writer metadata for abstract and conclusion authoring.",
    ),
    TaskOverlay(
        overlay_id="paper_writer.figure_sensitive",
        role="gpd-paper-writer",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Paper-writer metadata for sections whose text depends on figure edits.",
    ),
    TaskOverlay(
        overlay_id="paper_writer.response_pair",
        role="gpd-paper-writer",
        path=TASK_OVERLAY_REFERENCE_PATH,
        summary="Paper-writer metadata for paired author-response and referee-response work.",
    ),
)
_TASK_OVERLAY_BY_ID = {overlay.overlay_id: overlay for overlay in _TASK_OVERLAYS}


def list_task_overlays(*, role: str | None = None) -> tuple[TaskOverlay, ...]:
    """Return known task overlays, optionally filtered by compatible agent role."""
    if role is None:
        return _TASK_OVERLAYS
    normalized_role = _normalize_role(role)
    return tuple(overlay for overlay in _TASK_OVERLAYS if overlay.role == normalized_role)


def get_task_overlay(overlay_id: str) -> TaskOverlay:
    """Return a known task overlay by ID."""
    try:
        return _TASK_OVERLAY_BY_ID[overlay_id]
    except KeyError as exc:
        raise TaskOverlaySelectionError(f"unknown task overlay ID: {overlay_id}") from exc


def validate_task_overlay_selection(selected_ids: list[str] | tuple[str, ...], *, role: str) -> tuple[TaskOverlay, ...]:
    """Validate selected overlay IDs for one child-agent role."""
    normalized_role = _normalize_role(role)
    seen: set[str] = set()
    duplicate_ids: list[str] = []
    selected: list[TaskOverlay] = []

    for overlay_id in selected_ids:
        if overlay_id in seen:
            duplicate_ids.append(overlay_id)
            continue
        seen.add(overlay_id)
        overlay = get_task_overlay(overlay_id)
        if overlay.role != normalized_role:
            raise TaskOverlaySelectionError(f"task overlay {overlay_id!r} is for {overlay.role}, not {normalized_role}")
        _validate_overlay_metadata(overlay)
        selected.append(overlay)

    if duplicate_ids:
        rendered = ", ".join(sorted(set(duplicate_ids)))
        raise TaskOverlaySelectionError(f"duplicate task overlay IDs: {rendered}")

    return tuple(selected)


def build_task_overlay_load_manifest(
    selected_ids: list[str] | tuple[str, ...],
    *,
    role: str,
    selection_source: str = "spawn_callsite",
) -> dict[str, object]:
    """Build a metadata-only manifest for selected task overlays."""
    selected = validate_task_overlay_selection(selected_ids, role=role)
    return {
        "schema_version": 1,
        "selection_source": _single_line(selection_source, field="selection_source"),
        "role": _normalize_role(role),
        "selected_task_overlay_ids": [overlay.overlay_id for overlay in selected],
        "overlay_count": len(selected),
        "overlays": [overlay.as_manifest_entry() for overlay in selected],
    }


def build_task_overlay_compatibility_manifest(*, role: str) -> dict[str, object]:
    """Build metadata-only compatibility entries for overlays available to an agent role."""
    normalized_role = _normalize_role(role)
    overlays = list_task_overlays(role=normalized_role)
    for overlay in overlays:
        _validate_overlay_metadata(overlay)
    return {
        "schema_version": 1,
        "role": normalized_role,
        "compatible_task_overlay_ids": [overlay.overlay_id for overlay in overlays],
        "overlay_count": len(overlays),
        "overlays": [overlay.as_manifest_entry() for overlay in overlays],
        "body_policy": "metadata_only",
    }


def _normalize_role(role: str) -> str:
    normalized = _single_line(role, field="role").strip()
    if not normalized.startswith("gpd-"):
        raise TaskOverlaySelectionError(f"role must be a gpd agent id, got {role!r}")
    return normalized


def _single_line(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise TaskOverlaySelectionError(f"{field} must be a string")
    if not value.strip():
        raise TaskOverlaySelectionError(f"{field} must not be empty")
    if "\n" in value or "\r" in value:
        raise TaskOverlaySelectionError(f"{field} must be one line")
    return value


def _validate_overlay_metadata(overlay: TaskOverlay) -> None:
    _single_line(overlay.overlay_id, field="overlay_id")
    _single_line(overlay.summary, field=f"{overlay.overlay_id}.summary")
    _validate_reference_path(overlay.path, field=f"{overlay.overlay_id}.path")
    _normalize_role(overlay.role)


def _validate_reference_path(path: str, *, field: str) -> None:
    normalized = _single_line(path, field=field).strip()
    if normalized.startswith(("~", "/")):
        raise TaskOverlaySelectionError(f"{field} must be a relative specs path")
    if "\\" in normalized:
        raise TaskOverlaySelectionError(f"{field} must use forward slashes")
    pure_path = PurePosixPath(normalized)
    if any(part == ".." for part in pure_path.parts):
        raise TaskOverlaySelectionError(f"{field} must stay within specs")
    if not normalized.endswith(".md"):
        raise TaskOverlaySelectionError(f"{field} must point to markdown")
    if not normalized.startswith(_APPROVED_REFERENCE_PREFIXES):
        raise TaskOverlaySelectionError(f"{field} must point under approved reference/template roots")
