"""Structured visible choices for the projectless start context."""

from __future__ import annotations

from collections.abc import Mapping

from gpd.core.context_roots import _start_folder_state

__all__ = ["start_visible_choices"]


_ROUTE_WRITE_POLICY_IDS = {
    "resume_work": "start_route_resume_work_no_start_write",
    "sync_state": "start_route_sync_state_requires_repair_confirmation",
    "progress": "start_route_progress_report_only_no_reconcile",
    "map_research": "start_route_map_research_requires_durable_write_confirmation",
    "new_project_minimal": "start_route_new_project_minimal_requires_scope_approval",
    "new_project_full": "start_route_new_project_full_requires_scope_approval",
    "tour": "start_route_tour_read_only",
}


def _choice(option_id: str, label: str, command: str, *, recommended: bool = False) -> dict[str, object]:
    return {
        "option_id": option_id,
        "label": label,
        "command": command,
        "recommended": recommended,
        "route_write_policy_id": _ROUTE_WRITE_POLICY_IDS[option_id],
    }


def start_visible_choices(classifier: Mapping[str, object]) -> list[dict[str, object]]:
    """Return start-router choices that are already safe to show for this workspace."""

    folder_state = _start_folder_state(classifier)
    if folder_state == "initialized_project":
        return [
            _choice("resume_work", "Resume this project", "gpd:resume-work", recommended=True),
            _choice("progress", "Review the project status first", "gpd:progress"),
            _choice("tour", "Take a guided tour first", "gpd:tour"),
        ]
    if folder_state == "research_map":
        return [
            _choice("new_project_full", "Turn this into a full GPD project", "gpd:new-project", recommended=True),
            _choice("map_research", "Refresh the research map", "gpd:map-research"),
            _choice("tour", "Take a guided tour first", "gpd:tour"),
        ]
    if folder_state == "existing_research":
        return [
            _choice("map_research", "Map this folder first", "gpd:map-research", recommended=True),
            _choice("tour", "Take a guided tour first", "gpd:tour"),
            _choice("new_project_minimal", "Start a brand-new GPD project anyway", "gpd:new-project --minimal"),
        ]
    if folder_state == "fresh":
        return [
            _choice("new_project_minimal", "Fast start", "gpd:new-project --minimal", recommended=True),
            _choice("new_project_full", "Full guided setup", "gpd:new-project"),
            _choice("tour", "Take a guided tour first", "gpd:tour"),
        ]

    choices: list[dict[str, object]] = []
    if classifier.get("roadmap_exists") is True:
        choices.append(_choice("resume_work", "Inspect recovery state", "gpd:resume-work", recommended=True))
    if classifier.get("state_exists") is True:
        choices.append(_choice("sync_state", "Reconcile state files", "gpd:sync-state"))
    if not choices and classifier.get("init_progress_exists") is True:
        choices.append(
            _choice(
                "new_project_minimal",
                "Inspect interrupted setup",
                "gpd:new-project --minimal",
                recommended=True,
            )
        )
    return choices
