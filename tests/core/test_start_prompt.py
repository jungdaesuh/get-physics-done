from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.registry import get_command, list_commands
from tests.assertion_taxonomy_support import FragmentMode, semantic_anchor
from tests.doc_surface_contracts import assert_start_workflow_router_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"


def _normalized(content: str) -> str:
    return " ".join(content.split())


def _extract_step(workflow: str, step_name: str) -> str:
    start = workflow.index(f'<step name="{step_name}">')
    end = workflow.index("</step>", start)
    return workflow[start:end]


def _extract_between(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


def _displayed_choice_labels(workflow: str) -> set[str]:
    offer_step = _extract_step(workflow, "offer_relevant_choices")
    labels: set[str] = set()
    for line in offer_step.splitlines():
        match = re.match(r"\s*(?:\d+\.|-)\s+(.+?)\s+- use `", line)
        if match is not None:
            labels.add(match.group(1))
    return labels


def _routed_choice_labels(workflow: str) -> set[str]:
    route_step = _extract_step(workflow, "route_choice")
    labels: set[str] = set()
    for match in re.finditer(r"\*\*If the researcher chooses (?P<body>.*?):\*\*", route_step):
        labels.update(re.findall(r"`([^`]+)`", match.group("body")))
    return labels


def _route_for_option(workflow: str, option_id: str) -> str:
    route_step = _extract_step(workflow, "route_choice")
    start_marker = f"**If the researcher chooses option_id `{option_id}`"
    start = route_step.index(start_marker)
    next_route = re.search(r"\n\*\*If the researcher chooses option_id `", route_step[start + 1 :])
    if next_route is None:
        return route_step[start:]
    return route_step[start : start + 1 + next_route.start()]


def _numbered_choices(section: str) -> list[str]:
    return [line.strip() for line in section.splitlines() if re.match(r"\s*\d+\.\s+", line)]


def _numbered_choice_entries(section: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in _numbered_choices(section):
        match = re.match(r"\d+\.\s+(?P<label>.+?)\s+- use `(?P<command>gpd:[^`]+)`\.", line)
        if match is not None:
            entries.append((match.group("label"), match.group("command")))
    return entries


def _bold_section_headings(section: str) -> list[str]:
    return re.findall(r"(?m)^\*\*(.+?)\*\*$", section)


def _assert_anchor(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments).check(text)


def _assert_absent(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments, mode=FragmentMode.ABSENT).check(text)


def _assert_same_message_choice_boundary(text: str) -> None:
    _assert_anchor(
        text,
        "same-message start choice boundary",
        (
            "same-message explicit choice",
            "chooser answer",
            "not downstream write approval",
            "downstream intake",
            "scope approval",
            "file creation",
            "git initialization",
            "state repair",
            "map creation",
            "mapper spawning",
            "progress writes",
        ),
    )


def _assert_reopen_recent_boundary(text: str) -> None:
    _assert_anchor(
        text,
        "reopen recent terminal/runtime boundary",
        (
            "gpd resume --recent",
            "recent-project picker",
            "advisory",
            "gpd:resume-work",
        ),
    )


def test_start_command_is_registered_and_projectless() -> None:
    assert "start" in list_commands()
    command = get_command("gpd:start")
    assert command.name == "gpd:start"
    assert command.context_mode == "projectless"


def test_start_command_references_workflow() -> None:
    raw_command_prompt = (COMMANDS_DIR / "start.md").read_text(encoding="utf-8")
    command_prompt = expand_at_includes(raw_command_prompt, SOURCE_ROOT, PATH_PREFIX)

    assert "@{GPD_INSTALL_DIR}/workflows/start.md" in raw_command_prompt
    assert "@{GPD_INSTALL_DIR}/references/onboarding/beginner-command-taxonomy.md" in raw_command_prompt
    assert "gpd resume" in command_prompt
    assert "gpd resume --recent" in command_prompt
    assert "gpd:resume-work" in command_prompt
    assert "gpd:suggest-next" in command_prompt
    _assert_anchor(raw_command_prompt, "start passes argument context through", ("Requested choice", "$ARGUMENTS"))
    _assert_reopen_recent_boundary(command_prompt)
    semantic_anchor(
        "start recovery ladder command ordering",
        (
            "`gpd resume`",
            "current-workspace recovery snapshot",
            "`gpd resume --recent`",
            "advisory recent-project picker",
            "`gpd:suggest-next`",
            "fastest post-resume next command",
        ),
        mode=FragmentMode.ORDERED,
    ).check(command_prompt)


def test_start_command_same_message_choice_is_not_downstream_write_approval() -> None:
    raw_command_prompt = (COMMANDS_DIR / "start.md").read_text(encoding="utf-8")
    prompt = _normalized(raw_command_prompt)

    _assert_same_message_choice_boundary(prompt)
    _assert_anchor(
        prompt, "same-message choice does not execute recommendations", "executing a recommended next action"
    )


def test_start_workflow_routes_to_existing_entrypoints() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")

    assert_start_workflow_router_contract(workflow)
    assert "START_CONTEXT=$(gpd --raw init start-context)" in workflow
    assert "START_CONTEXT=$(gpd --raw init new-project)" not in workflow
    assert "gpd --raw init new-project --stage scope_intake" not in workflow
    detect_step = _extract_step(workflow, "detect_workspace_state")
    explain_step = _extract_step(workflow, "explain_current_state")
    offer_step = _extract_step(workflow, "offer_relevant_choices")

    _assert_anchor(
        detect_step,
        "start classifier uses thin raw workspace-bound preflight",
        ("thin raw CLI start-context classifier", "workspace-bound", "read-only classifier", "invoked folder"),
    )
    _assert_anchor(
        detect_step,
        "start classifier uses normalized folder state",
        ("folder_state", "initialized_project", "partial_project", "research_map", "existing_research", "fresh"),
    )
    _assert_anchor(
        detect_step,
        "interrupted init progress routes away from fresh setup",
        ("init_progress.exists=true", "setup was interrupted", "recovery/inspection", "fresh setup"),
    )
    _assert_anchor(
        detect_step + explain_step,
        "research file samples are classifier-provided context",
        ("research_file_samples", "sorted", "bounded", "project-relative", "show those sample files"),
    )
    assert "read-only file search" not in workflow
    assert "HAS_GPD_PROJECT=false" not in workflow
    assert "RESEARCH_FILE_COUNT" not in workflow

    _assert_anchor(
        explain_step,
        "start explains folder states in official beginner terms",
        (
            "GPD project",
            "research map",
            "map-research",
            "inspect an existing folder",
            "new-project",
            "project scaffolding",
        ),
    )
    folder_state_headings = _bold_section_headings(offer_step)
    assert len(folder_state_headings) == 5
    _assert_anchor(
        "\n".join(folder_state_headings),
        "start chooser covers each folder-state family",
        (
            "saved GPD work",
            "GPD project",
            "partial/recoverable GPD state",
            "research map",
            "research files",
            "not set up",
            "new",
            "mostly empty",
        ),
    )
    _assert_anchor(
        "\n".join(_displayed_choice_labels(workflow)),
        "start chooser labels preserve action concepts without exact menu prose",
        (
            "Resume",
            "recommended",
            "Review",
            "Map",
            "brand-new",
            "Fast start",
            "Full guided setup",
            "full GPD project",
        ),
    )
    assert {
        "gpd:resume-work",
        "gpd:progress",
        "gpd:tour",
        "gpd:new-project",
        "gpd:new-project --minimal",
        "gpd:map-research",
        "gpd:sync-state",
    } <= set(re.findall(r"`(gpd:[^`]+)`", offer_step))
    _assert_anchor(
        offer_step,
        "start first chooser stays short and state-specific",
        ("safest next steps first", "broader options second", "Keep the numbered list short", "first chooser"),
    )
    _assert_same_message_choice_boundary(offer_step)
    _assert_anchor(
        offer_step,
        "same-message chooser visible reply instruction",
        ("Reply with the number or the option name.", "Do not treat surrounding goals"),
    )
    _assert_reopen_recent_boundary(workflow)
    guardrails = _extract_step(workflow, "guardrails")
    _assert_anchor(
        guardrails,
        "start guardrails preserve chooser boundary",
        (
            "chooser",
            "not a second implementation",
            "Do not silently create project files",
            "Do not silently switch",
            "prefer `map-research`",
            "official GPD terms",
        ),
    )

    _assert_absent(workflow, "quoted internal numbered-list rule leak", "- `Keep the numbered list short.")
    _assert_absent(
        workflow,
        "old internal structuring rule leak",
        "this is an internal structuring rule, not a line to show the researcher",
    )
    _assert_absent(workflow, "start chooser excludes a secondary options menu", "Other useful options")

    assert "Read `{GPD_INSTALL_DIR}/workflows/new-project.md` with the file-read tool." not in workflow
    assert "Read `{GPD_INSTALL_DIR}/workflows/help.md` with the file-read tool." not in workflow
    assert "Read `{GPD_INSTALL_DIR}/workflows/tour.md` with the file-read tool." not in workflow
    _assert_anchor(
        offer_step,
        "partial state choices are filtered by recoverable fields",
        ("command-context preflight", "roadmap_exists=true", "state_exists=true", "next numbered choice"),
    )
    partial_state_choices = _extract_between(
        workflow,
        "**This folder has partial/recoverable GPD state**",
        "**This folder already has GPD's folder summary",
    )
    _assert_anchor(partial_state_choices, "partial state choices are renumbered after filtering", "contiguously")
    _assert_absent(
        partial_state_choices,
        "partial state choices do not preserve stale absolute numbering",
        ("1. Inspect recovery state", "2. Reconcile state files"),
    )
    _assert_anchor(
        offer_step, "partial state excludes progress route", ("Do not list", "gpd:progress", "partial state")
    )
    _assert_absent(offer_step, "partial state excludes visible progress menu prose", "Review visible progress")


def test_start_workflow_existing_research_unmapped_first_chooser_is_only_three_choices() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    existing_research_choices = _extract_between(
        workflow,
        "**This folder already has research files, but GPD is not set up here yet**",
        "**This folder looks new or mostly empty**",
    )

    choice_entries = _numbered_choice_entries(existing_research_choices)
    assert len(choice_entries) == 3
    assert [command for _label, command in choice_entries] == [
        "gpd:map-research",
        "gpd:tour",
        "gpd:new-project --minimal",
    ]
    _assert_anchor(
        "\n".join(label for label, _command in choice_entries),
        "existing research chooser offers map, tour, and explicit new-project escape hatch",
        ("Map", "recommended", "tour", "brand-new GPD project"),
    )
    assert not re.search(r"(?m)^\s*-\s+.+\s+- use `gpd:", existing_research_choices)
    _assert_absent(
        existing_research_choices,
        "existing research first chooser excludes broad help/capability detours",
        (
            "Other useful options",
            "capabilities menu",
            "help menu",
            "gpd:help",
            "gpd:quick",
            "gpd:explain",
            "gpd:suggest-next",
        ),
    )


def test_start_workflow_displayed_choice_labels_route_verbatim() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")

    displayed_labels = _displayed_choice_labels(workflow)
    routed_labels = _routed_choice_labels(workflow)

    assert displayed_labels
    assert displayed_labels <= routed_labels
    assert "Do one small bounded task" not in displayed_labels
    assert "Do one small bounded task" not in routed_labels
    assert "tour" in routed_labels


def test_start_workflow_same_message_choice_is_only_chooser_authority() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    offer_step = _normalized(_extract_step(workflow, "offer_relevant_choices"))

    _assert_same_message_choice_boundary(offer_step)
    _assert_anchor(
        offer_step,
        "same-message choice does not execute next action",
        "permission to execute a recommended next action",
    )


def test_start_workflow_route_choice_has_general_downstream_write_gate_boundary() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    raw_route_step = _extract_step(workflow, "route_choice")
    route_step = _normalized(raw_route_step)

    _assert_anchor(
        route_step,
        "start route choice has typed downstream write gate",
        (
            "start-menu choice authorizes only routing into that command",
            "write-capable routes",
            "opened command",
            "no downstream writes approved",
            "next downstream approval/confirmation",
        ),
    )
    for machine_fragment in (
        "route_boundary:",
        "route_allowed=true",
        "downstream_write_approved",
        "next_user_decision",
        "```text",
    ):
        assert machine_fragment not in raw_route_step


def test_start_workflow_write_capable_routes_render_plain_language_handoffs() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    expectations = {
        "new_project_minimal": {
            "selected_command": "gpd:new-project --minimal",
            "next_required_decision": "downstream minimal-project scope approval",
            "boundary": (
                "Route boundary for `new_project_minimal`",
                "do not create `GPD/`",
                "initialize git",
                "write state",
                "write progress files",
                "explicit downstream intake/scope approval after this start route",
            ),
        },
        "new_project_full": {
            "selected_command": "gpd:new-project",
            "next_required_decision": "downstream full-project scope approval",
            "boundary": (
                "Route boundary for `new_project_full`",
                "do not create `GPD/`",
                "initialize git",
                "write state",
                "write progress files",
                "explicit downstream intake/scope approval after this start route",
            ),
        },
        "map_research": {
            "selected_command": "gpd:map-research",
            "next_required_decision": "explicit durable-write confirmation",
            "boundary": (
                "Route boundary for `map_research`",
                "creating, archiving, or updating `GPD/research-map/`",
                "spawning mapper agents",
                "writing summaries",
                "explicit durable-write confirmation after the route handoff",
            ),
        },
        "sync_state": {
            "selected_command": "gpd:sync-state",
            "next_required_decision": "explicit sync/repair confirmation",
            "boundary": (
                "Route boundary for `sync_state`",
                "do not run `gpd state repair-sync`",
                "promote backups",
                "rewrite `GPD/STATE.md`",
                "rewrite `GPD/state.json`",
                "separate exact sync/repair confirmation inside `gpd:sync-state`",
            ),
        },
        "progress": {
            "selected_command": "gpd:progress",
            "next_required_decision": "explicit progress reconcile confirmation",
            "boundary": (
                "Route boundary for `progress`",
                "default/report mode only",
                "Do not switch to `--reconcile`",
                "execute the recommended next action",
                "compact state",
                "write progress/state files",
            ),
        },
    }

    for option_id, expectation in expectations.items():
        route = _route_for_option(workflow, option_id)
        _assert_anchor(
            route,
            f"{option_id} route renders compact plain-language handoff",
            (
                f"Opening `{expectation['selected_command']}`",
                "`gpd:start` approves no",
                "Next gate",
                expectation["next_required_decision"],
            ),
        )
        assert "route_boundary:" not in route
        assert "downstream_write_approved" not in route
        _assert_anchor(
            route,
            f"{option_id} route denies downstream writes until named decision",
            expectation["boundary"],
        )
