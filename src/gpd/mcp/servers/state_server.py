"""MCP server for GPD project state management.

Thin MCP wrapper around gpd.core.state, gpd.core.config, and
gpd.core.health. Exposes state queries, phase info, progress, and
health validation as MCP tools for solver agents.

Usage:
    python -m gpd.mcp.servers.state_server
    # or via entry point:
    gpd-mcp-state
"""

from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import WithJsonSchema

from gpd.core.command_run_hints import COMMAND_RUN_HINT_EXECUTION, build_command_run_hint
from gpd.core.config import load_config
from gpd.core.errors import GPDError
from gpd.core.health import run_health
from gpd.core.observability import gpd_span
from gpd.core.phases import progress_render
from gpd.core.root_resolution import resolve_project_root
from gpd.core.state import (
    _project_contract_runtime_payload_for_state,
    peek_state_json,
    state_advance_plan,
    state_validate,
)
from gpd.core.suggest import Recommendation
from gpd.core.suggest import suggest_next as core_suggest_next
from gpd.core.utils import is_phase_complete, matching_phase_artifact_count
from gpd.mcp.servers import (
    ABSOLUTE_PROJECT_DIR_SCHEMA,
    configure_mcp_logging,
    mutating_tool_annotations,
    read_only_tool_annotations,
    resolve_absolute_project_dir,
    stable_mcp_error,
    stable_mcp_response,
    tighten_registered_tool_contracts,
)

logger = configure_mcp_logging("gpd-state")

mcp = FastMCP("gpd-state")

AbsoluteProjectDirInput = Annotated[str, WithJsonSchema(ABSOLUTE_PROJECT_DIR_SCHEMA)]
SuggestLimitInput = Annotated[
    int,
    WithJsonSchema(
        {
            "type": "integer",
            "default": 3,
            "minimum": 1,
            "maximum": 10,
            "description": "Maximum number of next-action suggestions to return. Values outside 1-10 are clamped.",
        }
    ),
]
FixModeInput = Annotated[
    bool,
    WithJsonSchema(
        {
            "type": "boolean",
            "default": False,
            "description": "If true, attempt auto-fixes and allow the health check to modify project files.",
        }
    ),
]

_PROJECT_MUTATION_TOOL_ANNOTATIONS = mutating_tool_annotations(destructive=False, idempotent=False)
_PROJECT_FIX_TOOL_ANNOTATIONS = mutating_tool_annotations(destructive=True, idempotent=False)
_SUGGEST_NEXT_SOURCE = "gpd-state.suggest_next"
_SUGGEST_NEXT_DEFAULT_LIMIT = 3
_SUGGEST_NEXT_MAX_LIMIT = 10


def _normalize_suggest_next_limit(limit: object) -> tuple[int | None, str | None]:
    if limit is None:
        return _SUGGEST_NEXT_DEFAULT_LIMIT, None
    if isinstance(limit, bool):
        return None, "limit must be an integer"
    try:
        requested = int(limit)
    except (TypeError, ValueError):
        return None, "limit must be an integer"
    if requested < 1:
        return 1, None
    if requested > _SUGGEST_NEXT_MAX_LIMIT:
        return _SUGGEST_NEXT_MAX_LIMIT, None
    return requested, None


def _recommendation_payload(recommendation: Recommendation, *, source: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "action": recommendation.action,
        "priority": recommendation.priority,
        "reason": recommendation.reason,
        "command": recommendation.command,
        "phase": recommendation.phase,
    }
    run_hint = build_command_run_hint(
        command=recommendation.command,
        source=source,
        action=recommendation.action,
        phase=recommendation.phase,
    )
    if run_hint is not None:
        payload["run_hint"] = run_hint
    return payload


def load_state_json(cwd: Path) -> dict | None:
    """Return visible project state for MCP consumers.

    Keep a module-local loader so tool behavior and test patch points stay
    stable even when the underlying state read path evolves.
    """

    project_root = resolve_project_root(cwd, require_layout=True) or cwd.expanduser().resolve(strict=False)

    state_obj, _issues, state_source = peek_state_json(
        project_root,
        recover_intent=False,
        surface_blocked_project_contract=True,
        acquire_lock=False,
    )
    if state_obj is None:
        return None

    project_contract_load_info, project_contract_validation, project_contract_gate = (
        _project_contract_runtime_payload_for_state(
            project_root,
            state_obj=state_obj,
            state_source=state_source,
        )
    )
    merged_state = dict(state_obj)
    merged_state.pop("session", None)
    merged_state["project_contract_load_info"] = project_contract_load_info
    merged_state["project_contract_validation"] = project_contract_validation
    merged_state["project_contract_gate"] = project_contract_gate
    return merged_state


@mcp.tool(annotations=read_only_tool_annotations())
def get_state(project_dir: AbsoluteProjectDirInput) -> dict:
    """Get the current project state.

    Returns the structured project state from `state.json`.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    cwd = resolve_absolute_project_dir(project_dir)
    if cwd is None:
        return stable_mcp_error("project_dir must be an absolute path")
    with gpd_span("mcp.state.get", phase=""):
        try:
            state_obj = load_state_json(cwd)
            if state_obj is None:
                return stable_mcp_error(
                    "No project state found. Run the active runtime's new-project command to initialize a GPD project state."
                )
            return stable_mcp_response(state_obj)
        except (GPDError, OSError, ValueError, TimeoutError) as exc:
            return stable_mcp_error(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope
            return stable_mcp_error(exc)


@mcp.tool(annotations=read_only_tool_annotations())
def suggest_next(project_dir: AbsoluteProjectDirInput, limit: SuggestLimitInput = _SUGGEST_NEXT_DEFAULT_LIMIT) -> dict:
    """Get read-only next-action suggestions with non-executing run hints.

    Args:
        project_dir: Absolute path to the project root directory.
        limit: Maximum number of suggestions to return. Values outside 1-10 are clamped.
    """

    cwd = resolve_absolute_project_dir(project_dir)
    if cwd is None:
        return stable_mcp_error("project_dir must be an absolute path")
    normalized_limit, limit_error = _normalize_suggest_next_limit(limit)
    if limit_error is not None or normalized_limit is None:
        return stable_mcp_error(limit_error or "limit must be an integer")
    with gpd_span("mcp.state.suggest_next", phase=""):
        try:
            result = core_suggest_next(cwd, limit=normalized_limit)
            suggestions = [
                _recommendation_payload(recommendation, source=_SUGGEST_NEXT_SOURCE)
                for recommendation in result.suggestions
            ]
            top_action = (
                _recommendation_payload(result.top_action, source=_SUGGEST_NEXT_SOURCE)
                if result.top_action is not None
                else None
            )
            return stable_mcp_response(
                {
                    "status": "ok",
                    "project_dir": str(cwd),
                    "execution": COMMAND_RUN_HINT_EXECUTION,
                    "limit": normalized_limit,
                    "suggestions": suggestions,
                    "total_suggestions": result.total_suggestions,
                    "suggestion_count": result.suggestion_count,
                    "top_action": top_action,
                    "context": {
                        "current_phase": result.context.current_phase,
                        "status": result.context.status,
                        "progress_percent": result.context.progress_percent,
                        "paused_at": result.context.paused_at,
                        "phase_count": result.context.phase_count,
                        "completed_phases": result.context.completed_phases,
                        "active_blockers": result.context.active_blockers,
                        "unverified_results": result.context.unverified_results,
                        "open_questions": result.context.open_questions,
                        "active_calculations": result.context.active_calculations,
                        "pending_todos": result.context.pending_todos,
                        "missing_conventions": list(result.context.missing_conventions),
                        "has_paper": result.context.has_paper,
                        "has_literature_review": result.context.has_literature_review,
                        "has_referee_report": result.context.has_referee_report,
                        "autonomy": result.context.autonomy,
                        "research_mode": result.context.research_mode,
                        "adaptive_approach_locked": result.context.adaptive_approach_locked,
                    },
                }
            )
        except (GPDError, OSError, ValueError, TimeoutError) as exc:
            return stable_mcp_error(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope
            return stable_mcp_error(exc)


@mcp.tool(annotations=read_only_tool_annotations())
def get_phase_info(project_dir: AbsoluteProjectDirInput, phase: str) -> dict:
    """Get detailed information about a specific phase.

    Args:
        project_dir: Absolute path to the project root directory.
        phase: Phase number (e.g., "01", "02.1").
    """
    from gpd.core.phases import find_phase

    cwd = resolve_absolute_project_dir(project_dir)
    if cwd is None:
        return stable_mcp_error("project_dir must be an absolute path")
    with gpd_span("mcp.state.phase_info", phase=phase):
        try:
            info = find_phase(cwd, phase)
            if info is None:
                return stable_mcp_error(f"Phase {phase} not found")
            plan_count = len(info.plans)
            summary_count = matching_phase_artifact_count(info.plans, info.summaries)
            return stable_mcp_response(
                {
                    "phase_number": info.phase_number,
                    "phase_name": info.phase_name,
                    "directory": info.directory,
                    "phase_slug": info.phase_slug,
                    "plan_count": plan_count,
                    "summary_count": summary_count,
                    "complete": is_phase_complete(plan_count, summary_count),
                }
            )
        except (GPDError, OSError, ValueError, TimeoutError) as exc:
            return stable_mcp_error(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope
            return stable_mcp_error(exc)


@mcp.tool(annotations=_PROJECT_MUTATION_TOOL_ANNOTATIONS)
def advance_plan(project_dir: AbsoluteProjectDirInput) -> dict:
    """Advance the project state to the next plan.

    Updates the current plan counter and related state fields.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    cwd = resolve_absolute_project_dir(project_dir)
    if cwd is None:
        return stable_mcp_error("project_dir must be an absolute path")
    with gpd_span("mcp.state.advance_plan"):
        try:
            return stable_mcp_response(state_advance_plan(cwd).model_dump())
        except (GPDError, OSError, ValueError, TimeoutError) as exc:
            return stable_mcp_error(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope
            return stable_mcp_error(exc)


@mcp.tool(annotations=read_only_tool_annotations())
def get_progress(project_dir: AbsoluteProjectDirInput) -> dict:
    """Get overall project progress summary.

    Returns the computed progress summary without surfacing checkpoint shelf
    artifacts. Works even when STATE.md is missing.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    cwd = resolve_absolute_project_dir(project_dir)
    if cwd is None:
        return stable_mcp_error("project_dir must be an absolute path")
    with gpd_span("mcp.state.progress"):
        try:
            return stable_mcp_response(progress_render(cwd, "json").model_dump())
        except (GPDError, OSError, ValueError, TimeoutError) as exc:
            return stable_mcp_error(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope
            return stable_mcp_error(exc)


@mcp.tool(annotations=read_only_tool_annotations())
def validate_state(project_dir: AbsoluteProjectDirInput) -> dict:
    """Run comprehensive state validation checks.

    Validates state.json against STATE.md, checks schema completeness,
    convention lock, phase format, and more. Returns issues and warnings.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    cwd = resolve_absolute_project_dir(project_dir)
    if cwd is None:
        return stable_mcp_error("project_dir must be an absolute path")
    with gpd_span("mcp.state.validate"):
        try:
            result = state_validate(
                cwd,
                recover_intent=False,
                surface_blocked_project_contract=True,
                acquire_lock=False,
            )
            return stable_mcp_response(result.model_dump())
        except (GPDError, OSError, ValueError, TimeoutError) as exc:
            return stable_mcp_error(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope
            return stable_mcp_error(exc)


@mcp.tool(annotations=_PROJECT_FIX_TOOL_ANNOTATIONS)
def run_health_check(project_dir: AbsoluteProjectDirInput, fix: FixModeInput = False) -> dict:
    """Run the full project health dashboard.

    Checks environment, project structure, storage-path policy, state validity,
    compaction, roadmap consistency, orphans, conventions, frontmatter,
    return envelopes, config, checkpoint tags, and git status.

    Args:
        project_dir: Absolute path to the project root directory.
        fix: If True, attempt auto-fixes for common issues.
    """
    cwd = resolve_absolute_project_dir(project_dir)
    if cwd is None:
        return stable_mcp_error("project_dir must be an absolute path")
    with gpd_span("mcp.state.health", fix=str(fix)):
        try:
            report = run_health(cwd, fix=fix)
            return stable_mcp_response(report.model_dump())
        except (GPDError, OSError, ValueError, TimeoutError) as exc:
            return stable_mcp_error(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope
            return stable_mcp_error(exc)


@mcp.tool(annotations=read_only_tool_annotations())
def get_config(project_dir: AbsoluteProjectDirInput) -> dict:
    """Get the project GPD configuration.

    Returns the resolved config including model profile, autonomy mode,
    research mode, workflow toggles, and branching strategy.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    cwd = resolve_absolute_project_dir(project_dir)
    if cwd is None:
        return stable_mcp_error("project_dir must be an absolute path")
    with gpd_span("mcp.state.config"):
        try:
            config = load_config(cwd)
            return stable_mcp_response(config.model_dump())
        except (GPDError, OSError, ValueError, TimeoutError) as exc:
            return stable_mcp_error(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope
            return stable_mcp_error(exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the gpd-state MCP server."""
    from gpd.mcp.servers import run_mcp_server

    run_mcp_server(mcp, "GPD State MCP Server")


tighten_registered_tool_contracts(mcp)


if __name__ == "__main__":
    main()
